"""Conservative worker help based on the player's observations of the battlefield.

Unknown ground is blocked. Resource choice, the outward route, and the trip to
an owned depot must all fit inside remembered ground away from known threats.
Commands still belong to the player: this module only fills an empty order queue.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

from warband import path as pathing
from warband.model import TOUCH, Build, Deposit, Harvest, Point, Pos, Unit, World, rect_gap, tile_center
from warband.rules import BUILDINGS, GOLD_PER_TRIP, LUMBER_PER_TRIP, SIM_DT, UNITS, UNIT_RADIUS, BuildingType, Resource, Terrain


@dataclass(frozen=True)
class _Site:
    target: int | Pos
    resource: Resource
    position: Point
    access: tuple[Pos, ...]


def _navigation(world: World, player: int) -> bytearray:
    """Remember static terrain and towers; only visible mobile enemies add danger."""
    blocked = bytearray(world.worker_knowledge[player].blocked)
    threats = [(building.center, building.threat_range, (building.x, building.y, building.size, building.size))
               for building in world.worker_knowledge[player].threats if building.player != player]
    for unit in world.units.values():
        if unit.player != player and not unit.hidden and world.is_visible(player, unit.tile) and unit.hp > 0 and unit.info.damage:
            threats.append((unit.pos, max(2.5, unit.info.range + 1.5), None))
    for building in world.buildings.values():
        if building.player != player and not any(world.is_visible(player, tile) for tile in building.tiles()):
            continue
        for x, y in building.tiles():
            blocked[y * world.width + x] = 1
    width = world.width
    for center, radius, rect in threats:
        cx, cy = center
        if rect is None:
            # A unit's threat: the tiles whose centre lies within radius of it, one slice per row.
            r2 = radius * radius
            for y in range(max(0, math.floor(cy - radius)), min(world.height, math.ceil(cy + radius) + 1)):
                dy = y + 0.5 - cy
                if dy * dy > r2:
                    continue
                half = math.sqrt(r2 - dy * dy)
                lo, hi = max(0, math.ceil(cx - half - 0.5)), min(width, math.floor(cx + half - 0.5) + 1)
                if lo < hi:
                    blocked[y * width + lo:y * width + hi] = b"\x01" * (hi - lo)
            continue
        extent = radius + max(rect[2:]) / 2
        for y in range(max(0, math.floor(cy - extent)), min(world.height, math.ceil(cy + extent) + 1)):
            for x in range(max(0, math.floor(cx - extent)), min(width, math.ceil(cx + extent) + 1)):
                if rect_gap(tile_center((x, y)), rect) <= radius:
                    blocked[y * width + x] = 1
    return blocked


class _View:
    """One shared route map and depot-distance search per player per decision tick."""

    def __init__(self, world: World, player: int):
        self.world, self.player = world, player
        self.blocked = safe_navigation(world, player)
        depots = world.player_buildings(player, done=True)
        self.depot_distance = {
            resource: self._distances({tile for depot in depots if resource in depot.info.deposits
                                       for tile in self.access(depot.rect)})
            for resource in Resource
        }
        self.sites = []
        knowledge = world.worker_knowledge[player]
        for mine in knowledge.mines.values():
            if mine.gold > 0:
                self.sites.append(_Site(mine.id, Resource.GOLD, mine.center, self.access(mine.rect)))
        for index, terrain in enumerate(knowledge.terrain):
            y, x = divmod(index, world.width)
            if terrain is Terrain.TREES:
                self.sites.append(_Site((x, y), Resource.LUMBER, tile_center((x, y)), self.access((x, y, 1, 1))))

    def passable(self, x: int, y: int) -> bool:
        return 0 <= x < self.world.width and 0 <= y < self.world.height and not self.blocked[y * self.world.width + x]

    def access(self, rect: tuple[int, int, int, int]) -> tuple[Pos, ...]:
        x, y, width, height = rect
        return tuple((tx, ty) for ty in range(y - 1, y + height + 1) for tx in range(x - 1, x + width + 1)
                     if self.passable(tx, ty) and rect_gap(tile_center((tx, ty)), rect) <= TOUCH + UNIT_RADIUS)

    def _distances(self, starts: set[Pos]) -> list[float]:
        """Walking distance from the nearest of *starts* to every tile (flat indices; infinity where none)."""
        width = self.world.width
        return pathing.distance_field((y * width + x for x, y in starts), self.blocked, width, self.world.height)

    def depot_distance_at(self, tile: Pos, resource: Resource) -> float:
        """How far *tile* is from a depot taking *resource*; infinity when no safe walk leads to one."""
        return self.depot_distance[resource][tile[1] * self.world.width + tile[0]]

    def choose(self, worker: Unit, resource: Resource, loads: Counter) -> _Site | None:
        if not self.passable(*worker.tile):
            return None
        goals, owners = {}, {}
        for site in self.sites:
            if site.resource is not resource or (resource is Resource.LUMBER and loads[site.target]):
                continue
            if isinstance(site.target, int):
                mine = self.world.worker_knowledge[self.player].mines.get(site.target)
                if mine is None or mine.gold <= 0:
                    continue
            elif self.world.worker_knowledge[self.player].terrain[site.target[1] * self.world.width + site.target[0]] is not Terrain.TREES:
                continue
            for tile in site.access:
                distance = self.depot_distance_at(tile, resource)
                if distance < math.inf:
                    cost = 2 * distance + loads[site.target] * 1.5
                    if tile not in goals or (cost, site.position) < (goals[tile], owners[tile].position):
                        goals[tile], owners[tile] = cost, site
        route = pathing.find_work_path(worker.tile, goals, self.blocked, self.world.width, self.world.height)
        return owners[route[-1] if route else worker.tile] if route is not None else None


def _view(world: World, player: int) -> _View:
    cached = world._worker_ai_views.get(player)
    if cached is None or cached[0] != world.tick:
        snapshot = _View(world, player)
        world._worker_ai_views[player] = (world.tick, snapshot)
        return snapshot
    return cached[1]


def safe_navigation(world: World, player: int) -> bytearray:
    """Read-only automatic-work grid; refreshed each model tick and vision update."""
    cached = world._worker_ai_navigation.get(player)
    if cached is None or cached[0] != world.tick:
        blocked = _navigation(world, player)
        world._worker_ai_navigation[player] = (world.tick, blocked)
        return blocked
    return cached[1]


def _assignments(workers: list[Unit]) -> tuple[Counter, Counter]:
    crews, loads = Counter(), Counter()
    for worker in workers:
        harvest = next((order for order in worker.orders if isinstance(order, Harvest)), None)
        if harvest is not None:
            crews[Resource.GOLD if isinstance(harvest.target, int) else Resource.LUMBER] += 1
            loads[harvest.target] += 1
        elif worker.carrying is not None:
            crews[worker.carrying] += 1
    return crews, loads


def _reserves(world: World, player: int, workers: list[Unit]) -> dict[Resource, int]:
    # Reserve a farm and two units that the player's existing producers offer.
    production = [UNITS[unit].cost for building in world.player_buildings(player, done=True) for unit in building.info.trains]
    farm = BUILDINGS[BuildingType.FARM].cost
    gold = max([farm.gold] + [2 * cost.gold for cost in production])
    lumber = max([farm.lumber] + [2 * cost.lumber for cost in production])
    planned = [BUILDINGS[order.type].cost for worker in workers for order in worker.orders
               if isinstance(order, Build) and order.building is None]
    return {Resource.GOLD: max(gold, sum(cost.gold for cost in planned)),
            Resource.LUMBER: max(lumber, sum(cost.lumber for cost in planned))}


def assign_idle_workers(world: World, player: int) -> None:
    """Fill empty queues once per second; never interrupt a player's active job."""
    previous = world._worker_ai_checks.get(player)
    if previous is not None and world.tick - previous < round(1 / SIM_DT):
        return
    world._worker_ai_checks[player] = world.tick
    workers = sorted((unit for unit in world.player_units(player) if unit.is_worker), key=lambda unit: unit.id)
    idle = [worker for worker in workers if worker.auto_work and not worker.orders and not worker.hidden and worker.hp > 0]
    if not idle:
        return
    view = _view(world, player)
    reserves = _reserves(world, player, workers)
    crews, loads = _assignments(workers)
    stock = {Resource.GOLD: world.players[player].gold, Resource.LUMBER: world.players[player].lumber}
    trip = {Resource.GOLD: GOLD_PER_TRIP, Resource.LUMBER: LUMBER_PER_TRIP}
    for worker in idle:
        if worker.carrying is not None:
            if view.depot_distance_at(worker.tile, worker.carrying) < math.inf:
                worker.orders.append(Deposit(auto=True))
            continue
        choices = sorted(Resource, key=lambda resource: (stock[resource] + crews[resource] * trip[resource] * 3) / reserves[resource])
        for resource in choices:
            site = view.choose(worker, resource, loads)
            if site is not None:
                world._issue(worker, Harvest(site.target, auto=True))
                crews[resource] += 1
                loads[site.target] += 1
                break


def choose_replacement(world: World, worker: Unit, resource: Resource) -> int | Pos | None:
    """Continue an exhausted resource job using the same information and safety limits."""
    workers = [unit for unit in world.player_units(worker.player) if unit.is_worker and unit.id != worker.id]
    _, loads = _assignments(workers)
    site = _view(world, worker.player).choose(worker, resource, loads)
    return site.target if site is not None else None
