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
from typing import Final

from warband.sim import path as pathing
from warband.sim.model import TOUCH, Build, Deposit, Harvest, Point, Pos, Salvage, Unit, World, hypot, rect_gap, tile_center
from warband.sim.worker_knowledge import WorkerKnowledge, _Building
from warband.sim.rules import BUILDINGS, GOLD_PER_TRIP, LUMBER_PER_TRIP, MINE_SLOTS, SIM_DT, UNITS, BuildingType, Resource, Terrain, UnitType

try:
    from warband.sim import _native  # threat painting in C, built only with the compiled simulation (warband/league/fastsim.py)
except ImportError:  # the source runs, as it does in the game
    _native = None  # type: ignore[assignment]


@dataclass(frozen=True)
class _Site:
    target: int | Pos
    position: Point
    access: tuple[Pos, ...]


_REACH: Final[dict[tuple[int, int], tuple[tuple[int, int], ...]]] = {}


def _reach(width: int, height: int) -> tuple[tuple[int, int], ...]:
    """Offsets from a footprint's corner whose tile centre is close enough to work it from, in scan order.

    A peasant's own body, since a peasant is who works: the gap :meth:`World._gap` measures is from
    its edge, so a tile it can reach from is one whose centre is within TOUCH of the rect plus that body."""
    found = _REACH.get((width, height))
    if found is None:
        found = tuple((dx, dy) for dy in range(-1, height + 1) for dx in range(-1, width + 1)
                      if rect_gap(tile_center((dx, dy)), (0, 0, width, height)) <= TOUCH + UNITS[UnitType.PEASANT].radius)
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
        known = knowledge.buildings
        found: set[tuple[int, int, int]] = set()
        for building in world.buildings.values():
            if building.id in known:
                continue
            x, y, size = building.x, building.y, building.size
            if building.player is not None and building.player == player or knowledge.sees(visible, x, y, size):
                found.add((x, y, size))
        footprints = frozenset(found)
        world._worker_ai_footprints[player] = (epochs, footprints)
    routes: _Routes | None = world._worker_ai_routes.get(player)
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
    for building in knowledge.threats:
        if building.player != player:
            for index in _tower_ground(building, width, height):
                blocked[index] = 1
    return blocked


_TOWER_GROUND: Final[dict[tuple[_Building, int, int], tuple[int, ...]]] = {}


def _tower_ground(tower: _Building, width: int, height: int) -> tuple[int, ...]:
    """The flat indices of the tiles whose centre lies within a known tower's threat range of its footprint.
    A remembered tower never moves, so its ground is worked out once per record and map size."""
    key = (tower, width, height)
    ground = _TOWER_GROUND.get(key)
    if ground is None:
        found: list[int] = []
        cx, cy = tower.center
        radius = tower.threat_range
        rx, ry, rw, rh = tower.x, tower.y, tower.size, tower.size
        extent = radius + max(rw, rh) / 2
        columns = range(max(0, math.floor(cx - extent)), min(width, math.ceil(cx + extent) + 1))
        for y in range(max(0, math.floor(cy - extent)), min(height, math.ceil(cy + extent) + 1)):
            py = y + 0.5
            dy = max(ry - py, 0.0, py - (ry + rh))
            row = y * width
            for x in columns:
                px = x + 0.5
                if hypot(max(rx - px, 0.0, px - (rx + rw)), dy) <= radius:
                    found.append(row + x)
        if len(_TOWER_GROUND) >= 4096:  # a ladder plays thousands of matches: remember the recent towers only
            _TOWER_GROUND.clear()
        ground = _TOWER_GROUND[key] = tuple(found)
    return ground


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


    def ruin(self, worker: Unit) -> int | None:
        """The ruin the policy should put *worker* on: the id of one it remembers standing whole and nobody's, whose
        working edge is safe ground within :data:`SALVAGE_REACH` of a depot, cheapest for *worker* to walk to; None
        when it remembers none it can reach.  The ruin is remembered, not seen, exactly as a mine is: a record of one
        somebody razed since costs one wasted walk and is then forgotten."""
        knowledge = self.world.worker_knowledge[self.player]
        field, width = self._depot_field(Resource.GOLD), self.world.width
        goals: dict[Pos, float] = {}
        owners: dict[Pos, int] = {}
        for building in knowledge.buildings.values():
            if not building.ruin:
                continue
            for tile in self.access(building.rect):
                distance = field[tile[1] * width + tile[0]]
                if distance > SALVAGE_REACH:
                    continue
                cost = 2 * distance
                held = goals.get(tile)  # the cheaper claim on a tile wins, the older building on a tie
                if held is None or cost < held or (cost == held and building.id < owners[tile]):
                    goals[tile], owners[tile] = cost, building.id
        if not goals:
            return None
        route = pathing.find_work_path(worker.tile, goals, self.blocked, width, self.world.height)
        if route is None:
            return None
        return owners[route[-1] if route else worker.tile]  # a route ends on a claimed tile, as every work path does


def _choose_tree(start: Pos, trees: Sequence[int], felling: set[int], remembered: list[Terrain | None], field: Sequence[float],
                 blocked: bytes | bytearray, width: int, height: int) -> Pos | None:
    """The tree a worker at *start* should fell next, or None.  Every remembered tree nobody is felling (*trees* and
    *felling* are flat indices) offers the open tiles a worker can chop it from at twice their walk to a depot
    (*field*); a tile goes to the cheaper tree, and to the one nearer the map's top left on a tie; the worker takes
    the claim cheapest to walk to (:func:`~warband.sim.path.find_work_path`).  The compiled simulation does this in C."""
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


def _salvagers(workers: list[Unit]) -> int:
    """How many of *workers* the policy has put on a ruin."""
    return sum(1 for worker in workers for order in worker.orders if isinstance(order, Salvage) and order.auto)


SALVAGE_REACH: Final = 24.0  # tiles of safe walking from a depot; a ruin further off is not the policy's to fetch
SALVAGE_CREW: Final = 6  # workers a player needs before the policy can spare one of them for a ruin

# -- Hands off a worker its player is using (WB-059) ----------------------------
#
# The policy used to take any idle peasant, wherever it stood.  Send one across the map to raise a forward tower
# and the second it finished the policy walked it home to a mine: the player's intention, overruled without a
# word.  So a worker its player has had in hand is left alone for a while, and how long is how far from home it
# stands -- the same safe walk to a depot the gatherers route by, not a straight line to a point.
HOME_REACH: Final = 8.0  # tiles of safe walking from a depot: inside the base, where an idle peasant is plainly spare
AUTO_REACH: Final = 24.0  # and out here it is plainly not; the hold ramps between the two and holds at the far one
MANUAL_HOLD: Final = 45.0  # seconds the policy leaves a worker commanded AUTO_REACH or further from home alone


def manual_hold(distance: float) -> float:
    """Seconds the policy keeps its hands off a worker its player last had in hand, *distance* tiles of safe walking
    from the nearest depot (infinity when no safe walk leads to one, which is as far from home as it gets).

    Nothing at all inside :data:`HOME_REACH`: a peasant that put up a farm beside the hall and went back to the mine
    is what everybody wants and what the whole policy is for, and the complaint was never about it.  From there the
    hold ramps to :data:`MANUAL_HOLD` at :data:`AUTO_REACH`, which is a base's reach and where a peasant is
    obviously away on business of its own.  Forty-five seconds is long enough to place a second tower without the
    policy interfering and short enough that a peasant its player forgot is not lost for the match; a peasant meant
    to stand for good is what Stop and Hold are for (``Unit.auto_work``), and those hold it unconditionally.
    """
    if distance >= AUTO_REACH:
        return MANUAL_HOLD
    if distance <= HOME_REACH:
        return 0.0
    return MANUAL_HOLD * (distance - HOME_REACH) / (AUTO_REACH - HOME_REACH)


def _held(view: _View, worker: Unit, now: float) -> bool:
    """Whether *worker* is still its player's to command rather than the policy's to place."""
    commanded = worker.commanded
    if commanded is None:
        return False
    since = now - commanded
    if since >= MANUAL_HOLD:
        return False  # past the longest hold there is: no depot field need be walked to know it
    return since < manual_hold(view.depot_distance_at(worker.tile, Resource.GOLD))


def assign_idle_workers(world: World, player: int) -> None:
    """Fill empty queues once per second; never interrupt a player's active job.

    A ruin within reach is taken apart too, by one hand and no more: it pays about a third of what a peasant
    earns at a mine, so it is work for a crew that can spare somebody (:data:`SALVAGE_CREW`) and never work the
    mine and the trees give up.  The hand comes back to the resources the moment the ruin is gone, and
    :func:`rebalance_workers` never touches it: only a harvest the policy placed changes jobs.
    """
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
    spare = _salvagers(workers) == 0 and len(workers) >= SALVAGE_CREW
    for worker in idle:
        if worker.carrying is not None:
            if view.depot_distance_at(worker.tile, worker.carrying) < math.inf:
                worker.orders.append(Deposit(auto=True))  # a load in hand goes home whoever sent it for it
            continue
        if _held(view, worker, world.time):
            continue  # its player has it: not the policy's to send anywhere
        if spare:
            ruin = view.ruin(worker)
            if ruin is not None:
                world._issue(worker, Salvage(ruin, auto=True), manual=False)
                spare = False
                continue
        choices = sorted(Resource, key=lambda resource: (stock[resource] + crews[resource] * trip[resource] * 3) / reserves[resource])
        for resource in choices:
            target = view.choose(worker, resource, loads)
            if target is not None:
                world._issue(worker, Harvest(target, auto=True, placed=True), manual=False)
                crews[resource] += 1
                loads[target] += 1
                break


REBALANCE_EVERY: Final = 5.0  # seconds between a player's looks at how its automatic gatherers are split
REBALANCE_RATIO: Final = 4.0  # a resource this many times better served than the other gives up a hand


def rebalance_workers(world: World, player: int) -> None:
    """Move one automatic gatherer from the resource the policy finds far better served to the one it finds starved.

    The policy places a peasant once, when it is idle, and a peasant keeps its job for good.  Raiders at the mine
    send every miner to the trees, the one safe job left, and when the raiders were gone the miners stayed there: a
    base that had held ended the game with four thousand lumber, a hundred gold and nobody at the mine.  So the
    split is looked at again every :data:`REBALANCE_EVERY` seconds by the rule that placed them, and when one
    resource is :data:`REBALANCE_RATIO` times better served a hand with nothing in it changes jobs, if a safe
    walk leads to the other.  Only jobs the policy gave: a harvest a player or a brain ordered is theirs.
    """
    workers = sorted((unit for unit in world.player_units(player) if unit.is_worker), key=lambda unit: unit.id)
    crews, loads = _assignments(workers)
    reserves = _reserves(world, player, workers)
    stock = {Resource.GOLD: world.players[player].gold, Resource.LUMBER: world.players[player].lumber}
    trip = {Resource.GOLD: GOLD_PER_TRIP, Resource.LUMBER: LUMBER_PER_TRIP}
    served = {resource: (stock[resource] + crews[resource] * trip[resource] * 3) / reserves[resource] for resource in Resource}
    rich = max(Resource, key=lambda resource: served[resource])
    poor = Resource.LUMBER if rich is Resource.GOLD else Resource.GOLD
    if crews[rich] <= 1 or served[rich] < REBALANCE_RATIO * served[poor]:
        return
    view = _view(world, player)
    for worker in workers:
        order = worker.order
        if (not isinstance(order, Harvest) or not order.placed or worker.carrying is not None or worker.hidden or worker.hp <= 0
                or (rich is Resource.GOLD) != isinstance(order.target, int)):
            continue
        target = view.choose(worker, poor, loads)
        if target is None:
            return  # no safe walk to the other resource from here: the raiders are still about
        world._issue(worker, Harvest(target, auto=True, placed=True), manual=False)
        return


def choose_replacement(world: World, worker: Unit, resource: Resource) -> int | Pos | None:
    """Continue an exhausted resource job using the same information and safety limits."""
    workers = [unit for unit in world.player_units(worker.player) if unit.is_worker and unit.id != worker.id]
    _, loads = _assignments(workers)
    return _view(world, worker.player).choose(worker, resource, loads)
