"""Conservative worker help based on the player's observations of the battlefield.

Unknown ground is blocked. Resource choice, the outward route, and the trip to
an owned depot must all fit inside remembered ground away from known threats.
Commands still belong to the player: this module only fills an empty order queue.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
import math

from warband import path as pathing
from warband.model import TOUCH, Build, Deposit, Harvest, Point, Pos, Unit, World, hypot, rect_gap, tile_center
from warband.worker_knowledge import WorkerKnowledge
from warband.rules import BUILDINGS, GOLD_PER_TRIP, LUMBER_PER_TRIP, MINE_SLOTS, SIM_DT, UNITS, UNIT_RADIUS, BuildingType, Resource, Terrain

try:
    from warband import _native  # threat painting in C, built only with the compiled simulation (warband/fastsim.py)
except ImportError:  # the source runs, as it does in the game
    _native = None  # type: ignore[assignment]


@dataclass(frozen=True)
class _Site:
    target: int | Pos
    position: Point
    access: tuple[Pos, ...]


_REACH: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}


def _reach(width: int, height: int) -> tuple[tuple[int, int], ...]:
    """Offsets from a footprint's corner whose tile centre is close enough to work it from, in scan order."""
    found = _REACH.get((width, height))
    if found is None:
        found = tuple((dx, dy) for dy in range(-1, height + 1) for dx in range(-1, width + 1)
                      if rect_gap(tile_center((dx, dy)), (0, 0, width, height)) <= TOUCH + UNIT_RADIUS)
        _REACH[(width, height)] = found
    return found


class _Routes:
    """A player's automatic-work grid and everything it was stamped from.

    The grid is a pure function of these inputs, so while they stay as they
    were (no wall or tower newly remembered, no structure newly seen, no armed
    enemy in sight moving) the grid made last time is the grid, and a tick
    returns it rather than stamping every threat again.  Callers only read it.
    """

    def __init__(self, knowledge: WorkerKnowledge, footprints: frozenset[tuple[int, int, int]], base: bytearray) -> None:
        self.knowledge = knowledge          # whose remembered grid and armed structures the base was stamped from,
        self.version = knowledge.version    # as they stood at this stamping of them
        self.footprints = footprints  # structures seen but not yet in the knowledge, stamped on the base
        self.base = base
        self.units: tuple[tuple[float, float, float], ...] = ()  # the visible armed enemies stamped on the grid
        self.grid = base


def _navigation(world: World, player: int) -> bytearray:
    """Remember static terrain and towers; only visible mobile enemies add danger."""
    knowledge = world.worker_knowledge[player]
    width, height = world.width, world.height
    visible = world.visible[player]
    units: list[tuple[float, float, float]] = []
    for unit in world.units.values():
        if unit.player == player:
            continue
        x, y = int(unit.x), int(unit.y)
        if not (0 <= x < width and 0 <= y < height and visible[y * width + x]):
            continue
        if unit.hp <= 0 or unit.inside is not None or unit.constructing is not None:
            continue
        info = unit.info
        if info.damage:
            units.append((unit.x, unit.y, max(2.5, info.range + 1.5)))
    # Only a footprint the remembered grid does not already block still needs stamping, which is usually none.
    # Which footprints those are changes only with what the player sees (the knowledge is refreshed with it)
    # and with what stands on the map, so the answer is kept until one of the two moves on.
    epochs = (world._vision_epoch, world._building_epoch)
    kept = world._worker_ai_footprints.get(player)
    if kept is not None and kept[0] == epochs:
        footprints = kept[1]
    else:
        found: set[tuple[int, int, int]] = set()
        for bid in world.buildings.keys() - knowledge.buildings.keys():
            building = world.buildings[bid]
            x, y, size = building.x, building.y, building.size
            if building.player == player or knowledge.sees(visible, x, y, size):
                found.add((x, y, size))
        footprints = frozenset(found)
        world._worker_ai_footprints[player] = (epochs, footprints)
    routes = world._worker_ai_routes.get(player)
    if (routes is None or routes.knowledge is not knowledge or routes.version != knowledge.version
            or (routes.footprints is not footprints and routes.footprints != footprints)):
        routes = _Routes(knowledge, footprints, _stamp_structures(world, player, footprints))
        world._worker_ai_routes[player] = routes
    stamped = tuple(units)
    if stamped != routes.units:
        grid = routes.base
        if stamped:
            grid = bytearray(grid)
            _stamp_units(grid, stamped, width, height)
        routes.units, routes.grid = stamped, grid
    return routes.grid


def _stamp_structures(world: World, player: int, footprints: frozenset[tuple[int, int, int]]) -> bytearray:
    """The remembered grid with *footprints* blocked and the ground under every known enemy tower forbidden."""
    knowledge = world.worker_knowledge[player]
    blocked = bytearray(knowledge.blocked)
    width, height = world.width, world.height
    for x, y, size in footprints:
        for start, stop in knowledge.spans(x, y, size):
            blocked[start:stop] = b"\x01" * (stop - start)
    floor, ceil = math.floor, math.ceil
    for building in knowledge.threats:
        if building.player == player:
            continue
        # A tower's threat: the tiles whose centre lies within radius of its footprint.
        cx, cy = building.center
        radius = building.threat_range
        rx, ry, rw, rh = building.x, building.y, building.size, building.size
        extent = radius + max(rw, rh) / 2
        columns = range(max(0, floor(cx - extent)), min(width, ceil(cx + extent) + 1))
        for y in range(max(0, floor(cy - extent)), min(height, ceil(cy + extent) + 1)):
            py = y + 0.5
            dy = max(ry - py, 0.0, py - (ry + rh))
            row = y * width
            for x in columns:
                px = x + 0.5
                if hypot(max(rx - px, 0.0, px - (rx + rw)), dy) <= radius:
                    blocked[row + x] = 1
    return blocked


def _stamp_units(blocked: bytearray, units: tuple[tuple[float, float, float], ...], width: int, height: int) -> None:
    """Forbid the tiles whose centre lies within each unit's threat radius of it, one slice per row."""
    if _native is not None:
        _native.stamp_threats(blocked, units, width, height)
        return
    floor, ceil, sqrt = math.floor, math.ceil, math.sqrt
    for cx, cy, radius in units:
        r2 = radius * radius
        for y in range(max(0, floor(cy - radius)), min(height, ceil(cy + radius) + 1)):
            dy = y + 0.5 - cy
            offset = dy * dy
            if offset > r2:
                continue
            half = sqrt(r2 - offset)
            lo, hi = max(0, ceil(cx - half - 0.5)), min(width, floor(cx + half - 0.5) + 1)
            if lo < hi:
                blocked[y * width + lo:y * width + hi] = b"\x01" * (hi - lo)


class _View:
    """One shared route map and depot-distance search per player per decision tick.

    The searches and the site lists are built on first use: a decision usually
    only ever asks about one resource, and each field is a whole-map walk.
    """

    def __init__(self, world: World, player: int):
        self.world, self.player = world, player
        self.blocked = safe_navigation(world, player)
        self._depot_distance: dict[Resource, Sequence[float]] = {}
        self._sites: dict[Resource, list[_Site]] = {}

    def passable(self, x: int, y: int) -> bool:
        return 0 <= x < self.world.width and 0 <= y < self.world.height and not self.blocked[y * self.world.width + x]

    def access(self, rect: tuple[int, int, int, int]) -> tuple[Pos, ...]:
        x, y, width, height = rect
        blocked, map_width, map_height = self.blocked, self.world.width, self.world.height
        return tuple((x + dx, y + dy) for dx, dy in _reach(width, height)
                     if 0 <= x + dx < map_width and 0 <= y + dy < map_height
                     and not blocked[(y + dy) * map_width + x + dx])

    def _sites_for(self, resource: Resource) -> list[_Site]:
        """Every remembered source of *resource* with the tiles a worker can work it from, in map order."""
        found = self._sites.get(resource)
        if found is not None:
            return found
        knowledge = self.world.worker_knowledge[self.player]
        found = []
        if resource is Resource.GOLD:
            for mine in knowledge.mines.values():
                if mine.gold > 0:
                    found.append(_Site(mine.id, mine.center, self.access(mine.rect)))
        else:
            width = self.world.width
            for index in knowledge.trees:
                y, x = divmod(index, width)
                found.append(_Site((x, y), tile_center((x, y)), self.access((x, y, 1, 1))))
        self._sites[resource] = found
        return found

    def _depot_field(self, resource: Resource) -> Sequence[float]:
        """Walking distance from the nearest depot taking *resource* to every tile (flat indices; infinity where none)."""
        field = self._depot_distance.get(resource)
        if field is None:
            width = self.world.width
            starts = {tile for depot in self.world.player_buildings(self.player, done=True)
                      if resource in depot.info.deposits for tile in self.access(depot.rect)}
            field = pathing.distance_field((y * width + x for x, y in starts), self.blocked, width, self.world.height)
            self._depot_distance[resource] = field
        return field

    def depot_distance_at(self, tile: Pos, resource: Resource) -> float:
        """How far *tile* is from a depot taking *resource*; infinity when no safe walk leads to one."""
        return self._depot_field(resource)[tile[1] * self.world.width + tile[0]]

    def choose(self, worker: Unit, resource: Resource, loads: Counter) -> int | Pos | None:
        """The source *worker* should work next: a mine's id or a tree's tile; None when no safe walk leads to one."""
        if not self.passable(*worker.tile):
            return None
        knowledge = self.world.worker_knowledge[self.player]
        field, width = self._depot_field(resource), self.world.width
        if resource is Resource.LUMBER:
            felling = {target[1] * width + target[0] for target, count in loads.items() if count and not isinstance(target, int)}
            return _choose_tree(worker.tile, knowledge.trees, felling, knowledge.terrain, field, self.blocked, width, self.world.height)
        goals: dict[Pos, float] = {}
        owners: dict[Pos, _Site] = {}
        for site in self._sites_for(resource):
            target = site.target
            load = loads.get(target, 0)  # what loads[target] is, without a call to Counter.__missing__
            mine = knowledge.mines.get(target)  # type: ignore[arg-type]
            if mine is None or mine.gold <= 0:
                continue
            if load >= MINE_SLOTS:
                continue  # every place at that face is spoken for; another hand there would only queue
            penalty = load * 1.5
            for tile in site.access:
                distance = field[tile[1] * width + tile[0]]
                if distance < math.inf:
                    cost = 2 * distance + penalty
                    held = goals.get(tile)  # the cheaper claim on a tile wins, the one nearer the map's top left on a tie
                    if held is None or cost < held or (cost == held and site.position < owners[tile].position):
                        goals[tile], owners[tile] = cost, site
        route = pathing.find_work_path(worker.tile, goals, self.blocked, self.world.width, self.world.height)
        return owners[route[-1] if route else worker.tile].target if route is not None else None


def _choose_tree(start: Pos, trees: Sequence[int], felling: set[int], remembered: list[Terrain | None], field: Sequence[float],
                 blocked: bytes | bytearray, width: int, height: int) -> Pos | None:
    """The tree a worker at *start* should fell next, or None.  Every remembered tree nobody is felling (*trees* and
    *felling* are flat indices) offers the open tiles a worker can chop it from at twice their walk to a depot
    (*field*); a tile goes to the cheaper tree, and to the one nearer the map's top left on a tie; the worker takes
    the claim cheapest to walk to (:func:`~warband.path.find_work_path`).  The compiled simulation does this in C."""
    reach = _reach(1, 1)
    if _native is not None:
        return _native.choose_tree(start, trees, felling, remembered, Terrain.TREES, field, blocked, reach, width, height)
    goals: dict[Pos, float] = {}
    owners: dict[Pos, Pos] = {}
    for index in trees:
        if index in felling or remembered[index] is not Terrain.TREES:
            continue
        y, x = divmod(index, width)
        tree = (x, y)
        for dx, dy in reach:
            tx, ty = x + dx, y + dy
            if not (0 <= tx < width and 0 <= ty < height) or blocked[ty * width + tx]:
                continue
            distance = field[ty * width + tx]
            if distance < math.inf:
                tile, cost = (tx, ty), 2 * distance
                held = goals.get(tile)
                if held is None or cost < held or (cost == held and tree < owners[tile]):
                    goals[tile], owners[tile] = cost, tree
    route = pathing.find_work_path(start, goals, blocked, width, height)
    return owners[route[-1] if route else start] if route is not None else None


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
    crews: Counter[Resource] = Counter()
    loads: Counter[int | Pos] = Counter()
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
            target = view.choose(worker, resource, loads)
            if target is not None:
                world._issue(worker, Harvest(target, auto=True))
                crews[resource] += 1
                loads[target] += 1
                break


def choose_replacement(world: World, worker: Unit, resource: Resource) -> int | Pos | None:
    """Continue an exhausted resource job using the same information and safety limits."""
    workers = [unit for unit in world.player_units(worker.player) if unit.is_worker and unit.id != worker.id]
    _, loads = _assignments(workers)
    return _view(world, worker.player).choose(worker, resource, loads)
