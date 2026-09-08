"""World state, orders and the simulation that advances them.

Pure Python — no rendering, and no randomness beyond the ``Random`` the
world is given for damage rolls.  The scene and the AI drive the game
only through :class:`World` commands (``move``, ``attack``, ``harvest``,
``build``, ``train``…) and read the :class:`Event` list the simulation
appends to, so every rule lives in one place.

Positions: tiles are integer ``(x, y)`` with ``(0, 0)`` top-left; units
stand at float points measured in tiles, a tile's centre being
``(x + 0.5, y + 0.5)``.  Buildings occupy a square of tiles from their
top-left tile.  :meth:`World.step` advances exactly ``SIM_DT`` seconds.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator

from warband import path as pathing
from warband.worker_knowledge import WorkerKnowledge
from warband.rules import (
    REPAIR_CHUNK, REPAIR_RATE, repair_cost,
    ARMOR_BONUS, ARROWS_BONUS, BLADES_BONUS, BLESSING_BONUS, BUILDINGS, CHOP_TIME, GOLD_PER_TRIP, HIT_VARIANCE, HORSES_BONUS,
    LEASH, LUMBER_PER_TRIP, MINE_GOLD, MINE_TIME, PLAYERS, SIEGE_DAMAGE_BONUS, SIEGE_RANGE_BONUS, SIM_DT, SPLASH_FRACTION,
    STARTING_GOLD, STARTING_LUMBER, UNDER_ATTACK_COOLDOWN, UNIT_RADIUS, UNITS, UPGRADES, VISION_EVERY, BuildingInfo,
    BuildingType, Cost, MapTheme, Resource, Terrain, UnitInfo, UnitType, Upgrade,
)

Pos = tuple[int, int]
Point = tuple[float, float]

BLOCKING = frozenset({Terrain.WATER, Terrain.TREES, Terrain.ROCK})
ARRIVE = 0.12  # a unit is "there" within this many tiles of its target point
TOUCH = 0.4  # gap at which a peasant can enter a mine, deliver, or start building (a diagonal neighbour counts)
STUCK_AFTER = 0.8  # seconds without progress before a unit paths again around the units in its way
REPLAN_EVERY = 0.6  # a unit plans at most this often unless it gets a new order (a melee would otherwise plan every tick)
STEER_RANGE = 4.0  # within this many tiles a unit walks straight at its target when the line is clear, without A*
LOCAL_EXPANSIONS = 700  # A* budget for the detours around other units; those goals are close
SETTLE_WITHIN = 1.0  # a plain walk counts as arrived when a crowd keeps the unit this close to its spot without progress
MINE_CLEARANCE = 2  # tiles kept free around a gold mine so peasants can get in and out
SIDESTEP = 0.6  # lateral share of the push when walking units collide
MAX_PUSH = 0.25  # tiles a crowd can shove a unit in one step; eight overlapping units once summed to a jump over a tree wall


class RuleError(Exception):
    """An order the rules forbid.  The message says why."""


# -- Orders --------------------------------------------------------------------


@dataclass
class Move:
    target: Point


@dataclass
class AttackMove:
    target: Point


@dataclass
class Attack:
    target: int
    auto: bool = False  # picked up on its own; the unit gives up when it strays past the leash


@dataclass
class Harvest:
    target: int | Pos  # a gold mine's id, or a tree tile
    auto: bool = False  # Automatic jobs use known safe ground for both trips.


@dataclass
class Deposit:
    """Carry the load to a reachable depot (the simulation queues it)."""

    target: int | None = None
    auto: bool = False


@dataclass
class Build:
    type: BuildingType
    pos: Pos
    building: int | None = None  # set once construction has started


@dataclass
class Hold:
    """Stand here; fight what comes in range but never chase."""


@dataclass
class Heal:
    target: int
    auto: bool = False


@dataclass
class Repair:
    target: int  # the building


@dataclass
class Patrol:
    """Walk between two points forever, fighting (or healing) whatever turns up."""

    start: Point
    end: Point
    outbound: bool = True


Order = Move | AttackMove | Attack | Harvest | Deposit | Build | Hold | Heal | Patrol | Repair

_ORDER_TYPES: dict[str, type] = {cls.__name__: cls for cls in (Move, AttackMove, Attack, Harvest, Deposit, Build, Hold, Heal, Patrol, Repair)}


# -- Entities ------------------------------------------------------------------


@dataclass
class Player:
    id: int
    name: str
    color: tuple[int, int, int]
    human: bool = False
    gold: int = STARTING_GOLD
    lumber: int = STARTING_LUMBER
    alive: bool = True
    last_alert: float = -1000.0
    upgrades: set[Upgrade] = field(default_factory=set)


@dataclass
class Unit:
    id: int
    type: UnitType
    player: int
    x: float
    y: float
    hp: int
    facing: float = math.pi / 2  # radians, 0 = +x, pi/2 = +y (down the screen)
    orders: deque[Order] = field(default_factory=deque)
    path: list[Pos] = field(default_factory=list)
    path_goal: Pos | None = None
    exact: Point | None = None  # the point to stop at once the last path tile is reached
    cooldown: float = 0.0
    carrying: Resource | None = None
    carry: int = 0
    timer: float = 0.0
    inside: int | None = None  # the mine this peasant is in
    constructing: int | None = None
    home: Point | None = None  # where an auto-acquired chase started
    state: str = "idle"  # idle | move | attack | chop | build
    progress: float = 0.0
    last_distance: float = math.inf
    charge: float = 0.0  # healing accumulated below one hit point
    replan_at: float = 0.0  # simulation time from which the unit may plan again
    auto_work: bool = True  # Stop/Hold parks a worker until another order is given.

    @property
    def pos(self) -> Point:
        return (self.x, self.y)

    @property
    def tile(self) -> Pos:
        return (int(self.x), int(self.y))

    @property
    def info(self) -> UnitInfo:
        return UNITS[self.type]

    @property
    def max_hp(self) -> int:
        return self.info.hp

    @property
    def radius(self) -> float:
        return UNIT_RADIUS

    @property
    def hidden(self) -> bool:
        """Inside a mine or a building under construction: not on the map."""
        return self.inside is not None or self.constructing is not None

    @property
    def is_worker(self) -> bool:
        return self.type is UnitType.PEASANT

    @property
    def order(self) -> Order | None:
        return self.orders[0] if self.orders else None


@dataclass
class Building:
    id: int
    type: BuildingType
    player: int | None  # None: a gold mine
    x: int
    y: int
    hp: int
    progress: float = 0.0
    queue: list[UnitType] = field(default_factory=list)
    train_progress: float = 0.0
    rally: Point | None = None
    gold: int = 0
    builder: int | None = None
    cooldown: float = 0.0
    research: Upgrade | None = None
    research_progress: float = 0.0

    @property
    def info(self) -> BuildingInfo:
        return BUILDINGS[self.type]

    @property
    def size(self) -> int:
        return self.info.size

    @property
    def max_hp(self) -> int:
        return self.info.hp

    @property
    def done(self) -> bool:
        return self.progress >= self.info.build_time

    @property
    def pos(self) -> Pos:
        return (self.x, self.y)

    @property
    def center(self) -> Point:
        return (self.x + self.size / 2, self.y + self.size / 2)

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.size, self.size)

    def tiles(self) -> Iterator[Pos]:
        for dy in range(self.size):
            for dx in range(self.size):
                yield (self.x + dx, self.y + dy)

    def contains(self, point: Point) -> bool:
        return self.x <= point[0] < self.x + self.size and self.y <= point[1] < self.y + self.size


Entity = Unit | Building


@dataclass
class Event:
    """Something the simulation did that a viewer may want to show."""

    kind: str
    pos: Point
    player: int | None = None
    entity: int | None = None
    other: int | None = None
    amount: int = 0
    text: str = ""
    # Strike-time facts survive removal of either participant and network snapshots.
    source_type: str = ""
    target_type: str = ""
    target_armor: int = 0
    target_complete: bool = True


# -- Geometry helpers ------------------------------------------------------------


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def rect_gap(point: Point, rect: tuple[int, int, int, int]) -> float:
    """Distance from *point* to the nearest point of *rect* (0 inside)."""
    x, y, w, h = rect
    dx = max(x - point[0], 0.0, point[0] - (x + w))
    dy = max(y - point[1], 0.0, point[1] - (y + h))
    return math.hypot(dx, dy)


def rects_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """Tiles of clearance between two tile rectangles (Chebyshev; 0 when they touch or overlap)."""
    dx = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), 0)
    dy = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]), 0)
    return max(dx, dy)


def tile_center(pos: Pos) -> Point:
    return (pos[0] + 0.5, pos[1] + 0.5)


def _sight_offsets(radius: int) -> list[Pos]:
    return [(dx, dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1) if dx * dx + dy * dy <= radius * radius + radius]


_SIGHT: dict[int, list[Pos]] = {}


def sight_offsets(radius: int) -> list[Pos]:
    if radius not in _SIGHT:
        _SIGHT[radius] = _sight_offsets(radius)
    return _SIGHT[radius]


# -- World ---------------------------------------------------------------------


class World:
    def __init__(self, width: int, height: int, terrain: list[list[Terrain]], player_count: int, *,
                 human: int | None = 0, rng: random.Random | None = None, theme: MapTheme = MapTheme.SUMMER) -> None:
        if len(terrain) != height or any(len(row) != width for row in terrain):
            raise ValueError("terrain must be height rows of width tiles")
        self.width = width
        self.height = height
        self.terrain = terrain
        self.theme = theme
        self.players = [Player(i, PLAYERS[i].name, PLAYERS[i].color, human=(i == human)) for i in range(player_count)]
        self.units: dict[int, Unit] = {}
        self.buildings: dict[int, Building] = {}
        self.rng = rng if rng is not None else random.Random(0)
        self.time = 0.0
        self.tick = 0
        self.events: list[Event] = []
        self.winner: int | None = None
        self._next_id = 1
        self._blocked = bytearray(width * height)
        for y in range(height):
            for x in range(width):
                if terrain[y][x] in BLOCKING:
                    self._blocked[y * width + x] = 1
        self.explored = [bytearray(width * height) for _ in self.players]
        self.visible = [bytearray(width * height) for _ in self.players]
        self._buckets: dict[Pos, list[Unit]] = {}
        self.worker_knowledge = [WorkerKnowledge(width, height) for _ in self.players]
        self._worker_ai_checks: dict[int, int] = {}
        self._worker_ai_views: dict[int, tuple[int, Any]] = {}
        self._worker_ai_navigation: dict[int, tuple[int, bytearray]] = {}

    # -- Ids and lookups -----------------------------------------------------------

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def in_bounds(self, pos: Pos) -> bool:
        return 0 <= pos[0] < self.width and 0 <= pos[1] < self.height

    def terrain_at(self, pos: Pos) -> Terrain:
        return self.terrain[pos[1]][pos[0]]

    def passable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and not self._blocked[y * self.width + x]

    def entity(self, entity_id: int) -> Entity | None:
        return self.units.get(entity_id) or self.buildings.get(entity_id)

    def building_at(self, pos: Pos) -> Building | None:
        for building in self.buildings.values():
            if building.x <= pos[0] < building.x + building.size and building.y <= pos[1] < building.y + building.size:
                return building
        return None

    def unit_at(self, point: Point, radius: float = 0.5, *, player: int | None = None, visible_to: int | None = None) -> Unit | None:
        """The nearest unit whose body is within *radius* of *point*."""
        best, best_d = None, math.inf
        for unit in self.units_near(point, radius + UNIT_RADIUS):
            if unit.hidden or (player is not None and unit.player != player):
                continue
            if visible_to is not None and not self.is_visible(visible_to, unit.tile):
                continue
            d = dist(point, unit.pos) - unit.radius
            if d <= radius and d < best_d:
                best, best_d = unit, d
        return best

    def entity_at(self, point: Point, *, visible_to: int | None = None) -> Entity | None:
        """What a click at *point* means: the unit under it, else the building, else nothing."""
        unit = self.unit_at(point, 0.35, visible_to=visible_to)
        if unit is not None:
            return unit
        tile = (int(point[0]), int(point[1]))
        if not self.in_bounds(tile):
            return None
        if visible_to is not None and not self.explored[visible_to][tile[1] * self.width + tile[0]]:
            return None
        return self.building_at(tile)

    def units_in_rect(self, x0: float, y0: float, x1: float, y1: float, *, player: int | None = None) -> list[Unit]:
        left, right = min(x0, x1), max(x0, x1)
        top, bottom = min(y0, y1), max(y0, y1)
        return [u for u in self.units.values()
                if not u.hidden and (player is None or u.player == player) and left <= u.x <= right and top <= u.y <= bottom]

    def player_units(self, player: int) -> list[Unit]:
        return [u for u in self.units.values() if u.player == player]

    def player_buildings(self, player: int, building_type: BuildingType | None = None, *, done: bool | None = None) -> list[Building]:
        return [b for b in self.buildings.values() if b.player == player
                and (building_type is None or b.type is building_type) and (done is None or b.done == done)]

    def mines(self) -> list[Building]:
        return [b for b in self.buildings.values() if b.type is BuildingType.GOLD_MINE]

    def units_near(self, point: Point, radius: float) -> Iterator[Unit]:
        """Units whose centre lies within *radius* tiles of *point* (via the spatial buckets of the current step)."""
        r = int(radius) + 1
        cx, cy = int(point[0]), int(point[1])
        r2 = radius * radius
        for bx in range(cx - r, cx + r + 1):
            for by in range(cy - r, cy + r + 1):
                for unit in self._buckets.get((bx, by), ()):
                    dx, dy = unit.x - point[0], unit.y - point[1]
                    if dx * dx + dy * dy <= r2:
                        yield unit

    def _index_units(self) -> None:
        buckets: dict[Pos, list[Unit]] = {}
        for unit in self.units.values():
            buckets.setdefault(unit.tile, []).append(unit)
        self._buckets = buckets

    # -- Vision ----------------------------------------------------------------

    def is_visible(self, player: int, pos: Pos) -> bool:
        return self.in_bounds(pos) and bool(self.visible[player][pos[1] * self.width + pos[0]])

    def is_explored(self, player: int, pos: Pos) -> bool:
        return self.in_bounds(pos) and bool(self.explored[player][pos[1] * self.width + pos[0]])

    def update_vision(self) -> None:
        self._worker_ai_views.clear()
        self._worker_ai_navigation.clear()
        width, height = self.width, self.height
        for player in self.players:
            visible = self.visible[player.id]
            explored = self.explored[player.id]
            for i in range(len(visible)):
                visible[i] = 0
            for unit in self.units.values():
                if unit.player == player.id:
                    self._reveal(visible, unit.tile, unit.info.sight)
            for building in self.buildings.values():
                if building.player == player.id:
                    cx, cy = building.center
                    self._reveal(visible, (int(cx), int(cy)), building.info.sight + building.size // 2)
            for i in range(width * height):
                if visible[i]:
                    explored[i] = 1
            self.worker_knowledge[player.id].refresh(self, player.id)

    def _reveal(self, visible: bytearray, at: Pos, radius: int) -> None:
        width, height = self.width, self.height
        x0, y0 = at
        for dx, dy in sight_offsets(radius):
            x, y = x0 + dx, y0 + dy
            if 0 <= x < width and 0 <= y < height:
                visible[y * width + x] = 1

    def reveal_all(self, player: int) -> None:
        """Explore (and, until the next vision update, see) the whole map."""
        self._worker_ai_views.pop(player, None)
        self._worker_ai_navigation.pop(player, None)
        for i in range(self.width * self.height):
            self.explored[player][i] = 1
            self.visible[player][i] = 1
        self.worker_knowledge[player].refresh(self, player)

    # -- Stats with upgrades applied ----------------------------------------------------

    def _has(self, player: int | None, upgrade: Upgrade) -> bool:
        return player is not None and upgrade in self.players[player].upgrades

    def damage_of(self, entity: Entity) -> int:
        """Listed damage plus every upgrade its owner has researched."""
        info = entity.info
        damage = info.damage
        if damage == 0:
            return 0
        if isinstance(entity, Unit) and info.melee and not entity.is_worker:
            damage += BLADES_BONUS * (self._has(entity.player, Upgrade.BLADES_1) + self._has(entity.player, Upgrade.BLADES_2))
        if (isinstance(entity, Building) or info.ranged) and entity.type is not UnitType.CATAPULT:
            damage += ARROWS_BONUS * (self._has(entity.player, Upgrade.ARROWS_1) + self._has(entity.player, Upgrade.ARROWS_2))
        if isinstance(entity, Unit) and entity.type is UnitType.CATAPULT and self._has(entity.player, Upgrade.SIEGE):
            damage = int(round(damage * SIEGE_DAMAGE_BONUS))
        return damage

    def armor_of(self, entity: Entity) -> int:
        armor = entity.info.armor
        if isinstance(entity, Unit) and not entity.is_worker:
            armor += ARMOR_BONUS * (self._has(entity.player, Upgrade.ARMOR_1) + self._has(entity.player, Upgrade.ARMOR_2))
        return armor

    def range_of(self, unit: Unit) -> float:
        reach = unit.info.range
        if unit.type is UnitType.CATAPULT and self._has(unit.player, Upgrade.SIEGE):
            reach += SIEGE_RANGE_BONUS
        return reach

    def speed_of(self, unit: Unit) -> float:
        speed = unit.info.speed
        if unit.info.mounted and self._has(unit.player, Upgrade.HORSES):
            speed += HORSES_BONUS
        return speed

    def heal_rate(self, unit: Unit) -> float:
        rate = float(unit.info.heal)
        if rate and self._has(unit.player, Upgrade.BLESSING):
            rate *= BLESSING_BONUS
        return rate

    # -- Economy queries -----------------------------------------------------------

    def can_afford(self, player: int, cost: Cost) -> str | None:
        p = self.players[player]
        if p.gold < cost.gold:
            return f"Not enough gold ({cost.gold} needed)"
        if p.lumber < cost.lumber:
            return f"Not enough lumber ({cost.lumber} needed)"
        return None

    def _pay(self, player: int, cost: Cost) -> None:
        p = self.players[player]
        p.gold -= cost.gold
        p.lumber -= cost.lumber

    def _refund(self, player: int, cost: Cost) -> None:
        p = self.players[player]
        p.gold += cost.gold
        p.lumber += cost.lumber

    def supply(self, player: int) -> tuple[int, int]:
        """``(used, cap)``: units alive plus units queued, against finished farms and halls."""
        used = len(self.player_units(player)) + sum(len(b.queue) for b in self.player_buildings(player))
        cap = sum(b.info.supply for b in self.player_buildings(player, done=True))
        return used, cap

    def can_train(self, building: Building, unit_type: UnitType) -> str | None:
        info = UNITS[unit_type]
        if building.player is None or not building.done:
            return "Still under construction"
        if info.trained_at is not building.type:
            return f"{info.name}s are trained at the {BUILDINGS[info.trained_at].name}"
        if len(building.queue) >= 5:
            return "Queue is full"
        if building.research is not None:
            return f"Researching {UPGRADES[building.research].name}"
        reason = self.can_afford(building.player, info.cost)
        if reason is not None:
            return reason
        used, cap = self.supply(building.player)
        if used + 1 > cap:
            return "Not enough farms"
        return None

    def can_research(self, building: Building, upgrade: Upgrade) -> str | None:
        info = UPGRADES[upgrade]
        if building.player is None or not building.done:
            return "Still under construction"
        if upgrade not in building.info.researches:
            return f"{info.name} is not researched here"
        player = self.players[building.player]
        if upgrade in player.upgrades:
            return "Already researched"
        if any(b.research is upgrade for b in self.player_buildings(building.player)):
            return "Already being researched"
        if info.requires is not None and info.requires not in player.upgrades:
            return f"Requires {UPGRADES[info.requires].name}"
        if building.research is not None:
            return f"Researching {UPGRADES[building.research].name}"
        if building.queue:
            return "Training in progress"
        return self.can_afford(building.player, info.cost)

    def research(self, building_id: int, upgrade: Upgrade) -> None:
        building = self.buildings.get(building_id)
        if building is None:
            raise RuleError("No such building")
        reason = self.can_research(building, upgrade)
        if reason is not None:
            raise RuleError(reason)
        assert building.player is not None
        self._pay(building.player, UPGRADES[upgrade].cost)
        building.research = upgrade
        building.research_progress = 0.0

    def cancel_research(self, building_id: int) -> None:
        building = self.buildings.get(building_id)
        if building is None or building.research is None:
            raise RuleError("Nothing to cancel")
        assert building.player is not None
        self._refund(building.player, UPGRADES[building.research].cost)
        building.research = None
        building.research_progress = 0.0

    def can_place(self, building_type: BuildingType, pos: Pos, player: int, *, builder: int | None = None) -> str | None:
        info = BUILDINGS[building_type]
        if info.requires is not None and not self.player_buildings(player, info.requires, done=True):
            return f"Requires a {BUILDINGS[info.requires].name}"
        size = info.size
        for dy in range(size):
            for dx in range(size):
                tile = (pos[0] + dx, pos[1] + dy)
                if not self.in_bounds(tile):
                    return "Off the map"
                if self.terrain_at(tile) is not Terrain.GRASS:
                    return "Needs open ground"
                if self._blocked[tile[1] * self.width + tile[0]]:
                    return "Something is in the way"
                if not self.is_explored(player, tile):
                    return "Unexplored"
        for unit in self.units.values():
            if unit.id == builder or unit.hidden:
                continue
            if pos[0] - unit.radius < unit.x < pos[0] + size + unit.radius and pos[1] - unit.radius < unit.y < pos[1] + size + unit.radius:
                return "A unit is in the way"
        for mine in self.mines():
            if rects_gap((pos[0], pos[1], size, size), mine.rect) < MINE_CLEARANCE:
                return "Too close to the gold mine"
        return None

    # -- Commands ------------------------------------------------------------------

    def _own_units(self, unit_ids: list[int], player: int | None = None) -> list[Unit]:
        units = []
        for uid in unit_ids:
            unit = self.units.get(uid)
            if unit is None:
                continue
            if player is not None and unit.player != player:
                raise RuleError("Not your unit")
            units.append(unit)
        return units

    def _clamp(self, point: Point) -> Point:
        return (min(max(point[0], 0.05), self.width - 0.05), min(max(point[1], 0.05), self.height - 0.05))

    def _issue(self, unit: Unit, order: Order, *, queue: bool = False) -> None:
        if unit.inside is not None and queue and isinstance(unit.order, Harvest):
            unit.orders.popleft()  # Finish this trip, then obey the pending manual command.
        if unit.constructing is not None:
            self._abandon_construction(unit)
        unit.auto_work = not isinstance(order, Hold)
        if not queue:
            unit.orders.clear()
            unit.path = []
            unit.path_goal = None
        unit.orders.append(order)
        unit.home = None
        unit.state = "idle"

    def move(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        target = self._clamp(target)
        for unit in self._own_units(unit_ids):
            self._issue(unit, Move(target), queue=queue)

    def attack_move(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        target = self._clamp(target)
        for unit in self._own_units(unit_ids):
            self._issue(unit, AttackMove(target) if not unit.is_worker else Move(target), queue=queue)

    def patrol(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        """Patrol between where each unit stands and *target*."""
        target = self._clamp(target)
        for unit in self._own_units(unit_ids):
            if unit.is_worker:
                self._issue(unit, Move(target), queue=queue)
            else:
                self._issue(unit, Patrol(unit.pos, target), queue=queue)

    def attack(self, unit_ids: list[int], target_id: int, *, queue: bool = False) -> None:
        target = self.entity(target_id)
        if target is None:
            raise RuleError("No such target")
        if isinstance(target, Building) and target.type is BuildingType.GOLD_MINE:
            raise RuleError("A gold mine cannot be attacked")
        for unit in self._own_units(unit_ids):
            if target.player == unit.player:
                raise RuleError("Cannot attack your own")
            if unit.info.damage == 0:
                self._issue(unit, Move(self._target_point(target)), queue=queue)  # a healer follows the fight instead
            else:
                self._issue(unit, Attack(target_id), queue=queue)

    def stop(self, unit_ids: list[int]) -> None:
        for unit in self._own_units(unit_ids):
            unit.auto_work = False
            if unit.constructing is not None:
                self._abandon_construction(unit)
            unit.orders.clear()
            unit.path = []
            unit.path_goal = None
            unit.state = "idle"
            unit.home = None

    def hold(self, unit_ids: list[int]) -> None:
        for unit in self._own_units(unit_ids):
            self._issue(unit, Hold())

    def harvest(self, unit_ids: list[int], target: int | Pos, *, queue: bool = False) -> None:
        if isinstance(target, int):
            mine = self.buildings.get(target)
            if mine is None or mine.type is not BuildingType.GOLD_MINE:
                raise RuleError("Not a gold mine")
        elif not self.in_bounds(target) or self.terrain_at(target) is not Terrain.TREES:
            raise RuleError("No trees there")
        for unit in self._own_units(unit_ids):
            if not unit.is_worker:
                raise RuleError("Only peasants can harvest")
            self._issue(unit, Harvest(target), queue=queue)

    def build(self, unit_id: int, building_type: BuildingType, pos: Pos, *, queue: bool = False) -> None:
        unit = self.units.get(unit_id)
        if unit is None or not unit.is_worker:
            raise RuleError("Only peasants can build")
        info = BUILDINGS[building_type]
        if building_type is BuildingType.GOLD_MINE:
            raise RuleError("Gold mines cannot be built")
        reason = self.can_afford(unit.player, info.cost) or self.can_place(building_type, pos, unit.player, builder=unit.id)
        if reason is not None:
            raise RuleError(reason)
        self._issue(unit, Build(building_type, pos), queue=queue)

    def repair(self, unit_ids: list[int], building_id: int, *, queue: bool = False) -> None:
        """Peasants among *unit_ids* mend one of their own finished, damaged buildings."""
        workers = [u for u in self._own_units(unit_ids) if u.is_worker]
        if not workers:
            raise RuleError("Only peasants can repair")
        b = self.buildings.get(building_id)
        if b is None or b.player != workers[0].player or b.type is BuildingType.GOLD_MINE:
            raise RuleError("Peasants repair your own buildings")
        if not b.done:
            raise RuleError("Finish building it first")
        if b.hp >= b.max_hp:
            raise RuleError("Nothing to repair")
        for u in workers:
            self._issue(u, Repair(b.id), queue=queue)

    def train(self, building_id: int, unit_type: UnitType) -> None:
        building = self.buildings.get(building_id)
        if building is None:
            raise RuleError("No such building")
        reason = self.can_train(building, unit_type)
        if reason is not None:
            raise RuleError(reason)
        assert building.player is not None
        self._pay(building.player, UNITS[unit_type].cost)
        building.queue.append(unit_type)

    def cancel_train(self, building_id: int, index: int = -1) -> None:
        building = self.buildings.get(building_id)
        if building is None or not building.queue:
            raise RuleError("Nothing to cancel")
        assert building.player is not None
        unit_type = building.queue.pop(index)
        self._refund(building.player, UNITS[unit_type].cost)
        if index in (0, -len(building.queue) - 1) or not building.queue:
            building.train_progress = 0.0

    def set_rally(self, building_id: int, point: Point | None) -> None:
        building = self.buildings.get(building_id)
        if building is None or building.player is None:
            raise RuleError("No such building")
        building.rally = self._clamp(point) if point is not None else None

    def smart(self, unit_ids: list[int], point: Point, *, queue: bool = False) -> str:
        """What a right-click means for these units at *point*; returns the verb used."""
        units = self._own_units(unit_ids)
        if not units:
            return "none"
        player = units[0].player
        target = self.entity_at(point, visible_to=player)
        tile = (int(point[0]), int(point[1]))
        if target is not None and target.player is not None and target.player != player:
            self.attack(unit_ids, target.id, queue=queue)
            return "attack"
        workers = [u.id for u in units if u.is_worker]
        others = [u.id for u in units if not u.is_worker]
        if workers and isinstance(target, Building) and target.player == player and not target.done:
            self.resume_construction(workers, target.id)
            if others:
                self.move(others, point, queue=queue)
            return "build"
        if workers and isinstance(target, Building) and target.player == player and target.done and target.hp < target.max_hp and target.type is not BuildingType.GOLD_MINE:
            self.repair(workers, target.id, queue=queue)
            if others:
                self.move(others, point, queue=queue)
            return "repair"
        if workers and isinstance(target, Building) and target.type is BuildingType.GOLD_MINE:
            self.harvest(workers, target.id, queue=queue)
            if others:
                self.move(others, point, queue=queue)
            return "harvest"
        if workers and self.in_bounds(tile) and self.terrain_at(tile) is Terrain.TREES and self.is_explored(player, tile):
            self.harvest(workers, tile, queue=queue)
            if others:
                self.move(others, point, queue=queue)
            return "harvest"
        self.move(unit_ids, point, queue=queue)
        return "move"

    # -- Spawning ------------------------------------------------------------------

    def spawn_unit(self, player: int, unit_type: UnitType, point: Point) -> Unit:
        unit = Unit(self._new_id(), unit_type, player, point[0], point[1], UNITS[unit_type].hp)
        self.units[unit.id] = unit
        self._buckets.setdefault(unit.tile, []).append(unit)
        return unit

    def place_building(self, player: int | None, building_type: BuildingType, pos: Pos, *, done: bool = True) -> Building:
        info = BUILDINGS[building_type]
        building = Building(self._new_id(), building_type, player, pos[0], pos[1], info.hp if done else max(1, info.hp // 10))
        if done:
            building.progress = info.build_time
        if building_type is BuildingType.GOLD_MINE:
            building.gold = MINE_GOLD
        self.buildings[building.id] = building
        self._set_blocked(building, True)
        footprint = set(building.tiles())
        for unit in self.units.values():
            if any(tile in footprint for tile in unit.path):
                unit.path = []
                unit.path_goal = None  # the order plans again on its next step
        return building

    def _set_blocked(self, building: Building, flag: bool) -> None:
        for x, y in building.tiles():
            if self.in_bounds((x, y)):
                self._blocked[y * self.width + x] = 1 if flag else 0

    def free_tile_near(self, rect: tuple[int, int, int, int], *, prefer: Point | None = None) -> Pos | None:
        """A passable tile adjacent to *rect*, nearest *prefer* (default: the rect's front)."""
        x, y, w, h = rect
        ring = [(x + dx, y + dy) for dx in range(-1, w + 1) for dy in range(-1, h + 1) if dx in (-1, w) or dy in (-1, h)]
        candidates = [p for p in ring if self.passable(*p)]
        if not candidates:
            return pathing.nearest_passable((x + w // 2, y + h), self.passable)
        anchor = prefer if prefer is not None else (x + w / 2, y + h + 0.5)
        return min(candidates, key=lambda p: dist(tile_center(p), anchor))

    # -- Simulation ------------------------------------------------------------------

    def step(self) -> None:
        """Advance the world by :data:`SIM_DT`."""
        dt = SIM_DT
        self.time += dt
        self.tick += 1
        self._index_units()
        for building in list(self.buildings.values()):
            self._update_building(building, dt)
        for unit in list(self.units.values()):
            if unit.id in self.units:
                self._update_unit(unit, dt)
        self._separate()
        self._bury_the_dead()
        if self.tick % VISION_EVERY == 0:
            self.update_vision()
        self._check_elimination()

    def take_events(self) -> list[Event]:
        events, self.events = self.events, []
        return events

    # -- Buildings -------------------------------------------------------------------

    def _update_building(self, b: Building, dt: float) -> None:
        if b.type is BuildingType.GOLD_MINE or b.player is None:
            return
        info = b.info
        if not b.done:
            builder = self.units.get(b.builder) if b.builder is not None else None
            if builder is not None and builder.constructing == b.id:
                b.progress = min(info.build_time, b.progress + dt)
                b.hp = max(b.hp, int(info.hp * b.progress / info.build_time))
                if b.done:
                    b.hp = info.hp
                    self._finish_construction(b, builder)
            return
        if b.queue:
            unit_type = b.queue[0]
            b.train_progress += dt
            if b.train_progress >= UNITS[unit_type].build_time:
                b.queue.pop(0)
                b.train_progress = 0.0
                self._deliver_unit(b, unit_type)
        elif b.research is not None:
            b.research_progress += dt
            if b.research_progress >= UPGRADES[b.research].time:
                upgrade, b.research, b.research_progress = b.research, None, 0.0
                self.players[b.player].upgrades.add(upgrade)
                self.events.append(Event("researched", b.center, player=b.player, entity=b.id, text=UPGRADES[upgrade].name))
        if info.damage:
            self._tower_shoot(b, dt)

    def _finish_construction(self, b: Building, builder: Unit) -> None:
        builder.constructing = None
        if builder.orders and isinstance(builder.orders[0], Build):
            builder.orders.popleft()
        spot = self.free_tile_near(b.rect)
        if spot is not None:
            builder.x, builder.y = tile_center(spot)
        b.builder = None
        assert b.player is not None
        self.events.append(Event("built", b.center, player=b.player, entity=b.id, text=f"{b.info.name} complete"))

    def _deliver_unit(self, b: Building, unit_type: UnitType) -> None:
        assert b.player is not None
        spot = self.free_tile_near(b.rect, prefer=b.rally)
        if spot is None:
            spot = (b.x, b.y + b.size)
        unit = self.spawn_unit(b.player, unit_type, tile_center(spot))
        self.events.append(Event("trained", unit.pos, player=b.player, entity=unit.id, other=b.id, text=f"{unit.info.name} ready"))
        if b.rally is not None:
            self.smart([unit.id], b.rally)

    def _tower_shoot(self, b: Building, dt: float) -> None:
        b.cooldown = max(0.0, b.cooldown - dt)
        if b.cooldown > 0:
            return
        info = b.info
        target = self._nearest_enemy(b.player, b.center, info.range + b.size / 2, units_only=True)  # type: ignore[arg-type]
        if target is None:
            return
        self._hit(b, target, self.damage_of(b))
        b.cooldown = info.cooldown

    def _abandon_construction(self, unit: Unit) -> None:
        """A builder ordered away leaves the site; the shell stays for another peasant to finish (or to be cancelled)."""
        b = self.buildings.get(unit.constructing) if unit.constructing is not None else None
        unit.constructing = None
        if b is not None and b.builder == unit.id:
            b.builder = None
            spot = self.free_tile_near(b.rect)
            if spot is not None:
                unit.x, unit.y = tile_center(spot)

    def cancel_building(self, building_id: int) -> None:
        """Tear down an unfinished building; the whole cost comes back."""
        b = self.buildings.get(building_id)
        if b is None or b.player is None:
            raise RuleError("No such building")
        if b.done:
            raise RuleError("Finished buildings cannot be cancelled")
        builder = self.units.get(b.builder) if b.builder is not None else None
        if builder is not None:
            self._abandon_construction(builder)
            if builder.orders and isinstance(builder.orders[0], Build):
                builder.orders.popleft()
        self._refund(b.player, b.info.cost)
        self._remove_building(b, reason="cancelled")

    def resume_construction(self, unit_ids: list[int], building_id: int) -> None:
        b = self.buildings.get(building_id)
        if b is None or b.done:
            raise RuleError("Nothing to resume")
        for unit in self._own_units(unit_ids):
            if not unit.is_worker:
                raise RuleError("Only peasants can build")
            self._issue(unit, Build(b.type, b.pos, building=b.id))

    # -- Units ----------------------------------------------------------------------

    def _update_unit(self, u: Unit, dt: float) -> None:
        u.cooldown = max(0.0, u.cooldown - dt)
        if u.inside is not None:
            self._mine_inside(u, dt)
            return
        if u.constructing is not None:
            u.state = "build"
            return
        order = u.order
        if order is None:
            self._idle(u)
            return
        if isinstance(order, Move):
            self._do_move(u, order, dt)
        elif isinstance(order, AttackMove):
            self._do_attack_move(u, order, dt)
        elif isinstance(order, Attack):
            self._do_attack(u, order, dt)
        elif isinstance(order, Harvest):
            self._do_harvest(u, order, dt)
        elif isinstance(order, Deposit):
            self._do_deposit(u, dt)
        elif isinstance(order, Build):
            self._do_build(u, order, dt)
        elif isinstance(order, Hold):
            self._do_hold(u)
        elif isinstance(order, Heal):
            self._do_heal(u, order, dt)
        elif isinstance(order, Patrol):
            self._do_patrol(u, order, dt)
        elif isinstance(order, Repair):
            self._do_repair(u, order, dt)

    def _finish_order(self, u: Unit) -> None:
        if u.orders:
            u.orders.popleft()
        u.path = []
        u.path_goal = None
        u.exact = None
        u.state = "idle"
        u.last_distance = math.inf
        u.progress = 0.0

    def _idle(self, u: Unit) -> None:
        u.state = "idle"
        if u.is_worker:
            if u.auto_work and self.tick % round(1 / SIM_DT) == 0:
                from warband.worker_ai import assign_idle_workers

                assign_idle_workers(self, u.player)
            return
        if self.tick % 5:
            return
        if u.info.heal:
            patient = self._nearest_wounded(u, u.info.sight)
            if patient is not None:
                u.home = u.pos
                u.orders.appendleft(Heal(patient.id, auto=True))
            return
        target = self._nearest_enemy(u.player, u.pos, u.info.sight)
        if target is not None:
            u.home = u.pos
            u.orders.appendleft(Attack(target.id, auto=True))

    def _nearest_wounded(self, healer: Unit, radius: float) -> Unit | None:
        best, best_d = None, math.inf
        for unit in self.units_near(healer.pos, radius + UNIT_RADIUS):
            if unit is healer or unit.player != healer.player or unit.hidden or unit.hp >= unit.max_hp or unit.hp <= 0:
                continue
            d = dist(healer.pos, unit.pos)
            if d < best_d:
                best, best_d = unit, d
        return best

    def _do_heal(self, u: Unit, order: Heal, dt: float) -> None:
        patient = self.units.get(order.target)
        if patient is None or patient.hp <= 0 or patient.hp >= patient.max_hp or patient.hidden:
            self._finish_order(u)
            if order.auto and u.home is not None and not u.orders and dist(u.pos, u.home) > 1.0:
                u.orders.append(Move(u.home))
            return
        if order.auto and u.home is not None and dist(u.pos, u.home) > LEASH:
            self._finish_order(u)
            u.orders.appendleft(Move(u.home))
            return
        if self._gap(u, patient) <= self.range_of(u) + 0.05:
            u.path = []
            u.path_goal = None
            self._face(u, patient.pos)
            u.state = "attack"
            u.charge += self.heal_rate(u) * dt
            u.timer += dt
            if u.charge >= 1.0:
                amount = min(int(u.charge), patient.max_hp - patient.hp)
                u.charge -= int(u.charge)
                patient.hp += amount
                if u.timer >= 0.5:
                    u.timer = 0.0
                    self.events.append(Event("heal", patient.pos, player=u.player, entity=u.id, other=patient.id, amount=amount))
            return
        if self._steer(u, patient.pos, dt):
            return
        goal = patient.tile
        if u.path_goal is None or (dist(tile_center(u.path_goal), tile_center(goal)) > 1.5 and self.time >= u.replan_at):
            self._plan(u, goal, patient.pos)
        if self._follow(u, dt) and u.path_goal != goal and self.time >= u.replan_at:
            self._plan(u, goal, patient.pos)

    def _do_hold(self, u: Unit) -> None:
        u.state = "idle"
        u.path = []
        if u.is_worker or self.tick % 5:
            return
        if u.info.damage == 0:
            return
        target = self._nearest_enemy(u.player, u.pos, self.range_of(u) + 1.0)
        if target is not None and self._in_range(u, target):
            self._face(u, self._target_point(target))
            if u.cooldown <= 0:
                self._strike(u, target)
                u.cooldown = u.info.cooldown
            u.state = "attack"

    def _do_move(self, u: Unit, order: Move, dt: float) -> None:
        if self._walk_to(u, order.target, dt, settle=True):
            self._finish_order(u)

    def _engage(self, u: Unit) -> bool:
        """Pick up a fight (or a patient) in sight while on the move; True if one was found."""
        if self.tick % 5:
            return False
        if u.info.heal:
            patient = self._nearest_wounded(u, u.info.sight)
            if patient is None:
                return False
            u.orders.appendleft(Heal(patient.id))
        else:
            target = self._nearest_enemy(u.player, u.pos, u.info.sight)
            if target is None:
                return False
            u.orders.appendleft(Attack(target.id))
        u.path = []
        u.path_goal = None
        return True

    def _do_attack_move(self, u: Unit, order: AttackMove, dt: float) -> None:
        if self._engage(u):
            return
        if self._walk_to(u, order.target, dt, settle=True):
            self._finish_order(u)

    def _do_patrol(self, u: Unit, order: Patrol, dt: float) -> None:
        if self._engage(u):
            return
        if self._walk_to(u, order.end if order.outbound else order.start, dt, settle=True):
            order.outbound = not order.outbound
            u.path = []
            u.path_goal = None
            u.exact = None

    def _do_attack(self, u: Unit, order: Attack, dt: float) -> None:
        target = self.entity(order.target)
        if target is None or target.hp <= 0 or (isinstance(target, Building) and target.type is BuildingType.GOLD_MINE):
            self._finish_order(u)
            if order.auto and u.home is not None and not u.orders:
                u.orders.append(Move(u.home))
            return
        if order.auto and u.home is not None and dist(u.pos, u.home) > LEASH:
            self._finish_order(u)
            u.orders.appendleft(Move(u.home))
            return
        if self._in_range(u, target):
            u.path = []
            u.path_goal = None
            self._face(u, self._target_point(target))
            u.state = "attack"
            if u.cooldown <= 0:
                self._strike(u, target)
                u.cooldown = u.info.cooldown
            return
        aim = self._target_point(target)
        if isinstance(target, Building):
            x, y, w, h = target.rect
            aim = (min(max(u.x, x + 0.5), x + w - 0.5), min(max(u.y, y + 0.5), y + h - 0.5))  # the nearest wall
        if self._steer(u, aim, dt):
            return
        goal_tile = (int(aim[0]), int(aim[1]))
        if u.path_goal is None or (dist(tile_center(u.path_goal), tile_center(goal_tile)) > 1.5 and self.time >= u.replan_at):
            self._plan(u, goal_tile, aim)
        if self._follow(u, dt) and u.path_goal != goal_tile and self.time >= u.replan_at:
            self._plan(u, goal_tile, aim)

    def _do_harvest(self, u: Unit, order: Harvest, dt: float) -> None:
        if u.carrying is not None:
            u.orders.appendleft(Deposit())
            u.path = []
            u.path_goal = None
            return
        remembered = self.worker_knowledge[u.player].resource_rect(order.target)
        if remembered is not None:
            x, y, width, height = remembered
            if not any(self.is_visible(u.player, (tx, ty)) for ty in range(y, y + height) for tx in range(x, x + width)):
                # Revisit the last observed site before discovering a depleted
                # mine or felled tree. Hidden changes cannot alter this route.
                if self._approach_work(u, remembered, dt, self._worker_navigation(u)):
                    self._finish_order(u)
                return
        if isinstance(order.target, int):
            mine = self.buildings.get(order.target)
            if mine is None or mine.gold <= 0:
                from warband.worker_ai import choose_replacement
                replacement = choose_replacement(self, u, Resource.GOLD)
                if replacement is None:
                    self._finish_order(u)
                    return
                order.target, order.auto = replacement, True
                u.path_goal = None
                return  # a remembered replacement may still be hidden by fog
            navigation = self._worker_navigation(u)
            if rect_gap(u.pos, mine.rect) - u.radius <= TOUCH and not navigation[u.tile[1] * self.width + u.tile[0]]:
                u.inside = mine.id
                u.timer = MINE_TIME
                u.path = []
                u.path_goal = None
                u.state = "idle"
                return
            if self._approach_work(u, mine.rect, dt, navigation):
                self._finish_order(u)
            return
        tile = order.target
        if self.terrain_at(tile) is not Terrain.TREES:
            from warband.worker_ai import choose_replacement
            replacement = choose_replacement(self, u, Resource.LUMBER)
            if replacement is None:
                self._finish_order(u)
                return
            order.target = tile = replacement
            order.auto = True
            u.path = []
            u.path_goal = None
            return
        navigation = self._worker_navigation(u)
        rect = (tile[0], tile[1], 1, 1)
        if rect_gap(u.pos, rect) - u.radius <= TOUCH and not navigation[u.tile[1] * self.width + u.tile[0]]:
            u.path = []
            u.state = "chop"
            self._face(u, tile_center(tile))
            u.timer += dt
            if u.timer >= CHOP_TIME:
                u.timer = 0.0
                self.terrain[tile[1]][tile[0]] = Terrain.GRASS
                self._blocked[tile[1] * self.width + tile[0]] = 0
                u.carrying, u.carry = Resource.LUMBER, LUMBER_PER_TRIP
                self.events.append(Event("tree_felled", tile_center(tile), player=u.player, entity=u.id))
                u.orders.appendleft(Deposit())
            return
        u.timer = 0.0
        if self._approach_work(u, rect, dt, navigation):
            self._finish_order(u)

    def _mine_inside(self, u: Unit, dt: float) -> None:
        mine = self.buildings.get(u.inside) if u.inside is not None else None
        u.timer -= dt
        if mine is None:
            u.inside = None
            return
        if u.timer > 0:
            return
        taken = min(GOLD_PER_TRIP, mine.gold)
        mine.gold -= taken
        u.carrying, u.carry = Resource.GOLD, taken
        u.inside = None
        # Emerge where this worker entered. Teleporting every miner to the same
        # depot-facing tile creates a pile-up and can cross a separating wall.
        if not u.orders and u.auto_work:
            u.orders.append(Deposit(auto=True))
        elif isinstance(u.order, Harvest):
            u.orders.appendleft(Deposit(auto=u.order.auto))
        if mine.gold <= 0:
            self._remove_building(mine, reason="exhausted")

    def _do_deposit(self, u: Unit, dt: float) -> None:
        if u.carrying is None:
            self._finish_order(u)
            return
        order = u.orders[0]
        assert isinstance(order, Deposit)
        navigation = self._worker_navigation(u)
        hall = self.buildings.get(order.target)
        if hall is None or not hall.done or u.carrying not in hall.info.deposits or u.path_goal is None:
            if self.time < u.replan_at:
                u.state = "idle"
                return
            depots = {b.id: b.rect for b in self.player_buildings(u.player, done=True) if u.carrying in b.info.deposits}
            order.target = self._plan_work_route(u, depots, navigation)
            hall = self.buildings.get(order.target)
        if hall is None:
            u.state = "idle"
            return
        if rect_gap(u.pos, hall.rect) - u.radius <= TOUCH:
            player = self.players[u.player]
            if u.carrying is Resource.GOLD:
                player.gold += u.carry
            else:
                player.lumber += u.carry
            self.events.append(Event("deposit", u.pos, player=u.player, entity=u.id, amount=u.carry, text=u.carrying.value))
            u.carrying, u.carry = None, 0
            self._finish_order(u)
            return
        if self._approach_work(u, hall.rect, dt, navigation):
            order.target = None  # a new wall or threat may require another depot

    def _worker_navigation(self, u: Unit) -> bytearray:
        if any(isinstance(order, (Harvest, Deposit)) and order.auto for order in u.orders):
            from warband.worker_ai import safe_navigation
            return safe_navigation(self, u.player)
        return self._blocked


    def _plan_work_route(self, u: Unit, targets: dict[int, tuple[int, int, int, int]],
                         navigation: bytearray) -> int | None:
        """Choose a reachable interaction edge by travel distance and local crowding."""
        owners: dict[Pos, int] = {}
        costs: dict[Pos, float] = {}
        for target, rect in targets.items():
            x, y, w, h = rect
            for ty in range(max(0, y - 1), min(self.height, y + h + 1)):
                for tx in range(max(0, x - 1), min(self.width, x + w + 1)):
                    tile = (tx, ty)
                    point = tile_center(tile)
                    if navigation[ty * self.width + tx] or rect_gap(point, rect) - u.radius > TOUCH:
                        continue
                    owners[tile] = target
                    costs[tile] = sum(max(0.0, 1.0 - dist(v.pos, point)) * 2
                                      for v in self.units_near(point, 1.0)
                                      if v is not u and not v.hidden and v.player == u.player)
        route = pathing.find_work_path(u.tile, costs, navigation, self.width, self.height)
        u.replan_at = self.time + REPLAN_EVERY
        u.progress, u.last_distance = 0.0, math.inf
        u.path, u.path_goal, u.exact = [], None, None
        if route is None:
            return None
        goal = route[-1] if route else u.tile
        u.path, u.path_goal, u.exact = route, goal, tile_center(goal)
        return owners[goal]


    def _approach_work(self, u: Unit, rect: tuple[int, int, int, int], dt: float,
                       navigation: bytearray) -> bool:
        """Walk to a useful work position; True only when no route exists."""
        goal = u.path_goal
        if (goal is None or navigation[goal[1] * self.width + goal[0]]
                or rect_gap(tile_center(goal), rect) - u.radius > TOUCH or self._next_waypoint(u, precise=True) is None):
            if self.time < u.replan_at:
                u.state = "idle"
                return False
            if self._plan_work_route(u, {0: rect}, navigation) is None:
                u.state = "idle"
                return True
        self._follow(u, dt, navigation=navigation, precise=True)
        return False


    def _do_build(self, u: Unit, order: Build, dt: float) -> None:
        if order.building is not None:
            b = self.buildings.get(order.building)
            if b is None or b.done:
                self._finish_order(u)
                return
            if rect_gap(u.pos, b.rect) - u.radius <= TOUCH:
                self._start_building(u, b)
                return
            if self._approach(u, (b.x + b.size // 2, b.y + b.size // 2), b.center, dt):
                self._finish_order(u)
            return
        size = BUILDINGS[order.type].size
        rect = (order.pos[0], order.pos[1], size, size)
        if rect_gap(u.pos, rect) - u.radius <= TOUCH:
            reason = self.can_afford(u.player, BUILDINGS[order.type].cost) or self.can_place(order.type, order.pos, u.player, builder=u.id)
            if reason is not None:
                self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text=f"Cannot build: {reason}"))
                self._finish_order(u)
                return
            self._pay(u.player, BUILDINGS[order.type].cost)
            b = self.place_building(u.player, order.type, order.pos, done=False)
            order.building = b.id
            self.events.append(Event("construction", b.center, player=u.player, entity=b.id))
            self._start_building(u, b)
            return
        if self._approach(u, (order.pos[0] + size // 2, order.pos[1] + size // 2), (order.pos[0] + size / 2, order.pos[1] + size / 2), dt):
            self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text="Cannot reach the building site"))
            self._finish_order(u)

    def _do_repair(self, u: Unit, order: Repair, dt: float) -> None:
        b = self.buildings.get(order.target)
        if b is None or not b.done or b.hp >= b.max_hp:
            u.charge = 0.0
            self._finish_order(u)
            return
        if rect_gap(u.pos, b.rect) - u.radius > TOUCH:
            if self._approach(u, (b.x + b.size // 2, b.y + b.size // 2), b.center, dt):
                self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text="Cannot reach the building"))
                self._finish_order(u)
            return
        u.path = []
        u.path_goal = None
        u.state = "repair"
        self._face(u, b.center)
        u.charge += REPAIR_RATE * dt
        if u.charge < REPAIR_CHUNK:
            return
        u.charge -= REPAIR_CHUNK
        amount = min(REPAIR_CHUNK, b.max_hp - b.hp)
        cost = repair_cost(b.info, amount, b.max_hp)
        reason = self.can_afford(u.player, cost)
        if reason is not None:
            self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text=f"Cannot repair: {reason}"))
            u.charge = 0.0
            self._finish_order(u)
            return
        self._pay(u.player, cost)
        b.hp += amount
        if b.hp >= b.max_hp:
            u.charge = 0.0
            self._finish_order(u)

    def _start_building(self, u: Unit, b: Building) -> None:
        b.builder = u.id
        u.constructing = b.id
        u.x, u.y = b.center
        u.path = []
        u.path_goal = None
        u.state = "build"

    # -- Movement --------------------------------------------------------------------

    def _plan(self, u: Unit, goal: Pos, exact: Point | None = None, *, around_units: bool = False,
              navigation: bytearray | None = None) -> None:
        """Path from the unit's tile to *goal*; the last step aims at *exact* when the goal tile is open."""
        start = u.tile
        grid = self._blocked if navigation is None else navigation
        def passable(x: int, y: int) -> bool:
            return 0 <= x < self.width and 0 <= y < self.height and not grid[y * self.width + x]
        if not passable(*start):
            nearest = pathing.nearest_passable(start, passable)
            if nearest is not None:
                start = nearest
        target = goal
        if not passable(*goal):
            # A blocked goal (a building, a tree, water) would make A* explore everything it can reach
            # before settling for the nearest tile; aim at that tile from the start.
            nearest = pathing.nearest_passable(goal, passable, prefer=start)
            if nearest is not None:
                target = nearest
        u.replan_at = self.time + REPLAN_EVERY
        if around_units:
            blocked = bytearray(grid)
            width = self.width
            for v in self.units.values():
                if v is not u and not v.hidden and v.state in ("idle", "attack", "chop", "repair") and (navigation is None or v.player == u.player or self.is_visible(u.player, v.tile)):
                    tx, ty = v.tile
                    if (tx, ty) != target and 0 <= tx < width and 0 <= ty < self.height:
                        blocked[ty * width + tx] = 1
            u.path = pathing.find_path_grid(start, target, blocked, width, self.height, max_expansions=LOCAL_EXPANSIONS)
        else:
            u.path = pathing.find_path_grid(start, target, grid, self.width, self.height)
        u.path_goal = goal  # the goal as asked, so a repeated request is recognised
        u.last_distance = math.inf
        u.progress = 0.0
        u.exact = None
        if exact is not None:
            goal_tile = (int(exact[0]), int(exact[1]))
            reached = (u.path[-1] if u.path else start) == goal_tile
            if reached and passable(*goal_tile):
                u.exact = exact

    def _walk_to(self, u: Unit, target: Point, dt: float, *, settle: bool = False) -> bool:
        """Move towards *target*; True once there is nothing left to walk (arrived, or as near as the
        map allows).  With *settle*, a crowd holding the unit within SETTLE_WITHIN of the spot also
        counts as arrived: a plain walk ends there, while a peasant keeps pressing for its mine."""
        return self._approach(u, (int(target[0]), int(target[1])), target, dt, settle=settle)

    def _approach(self, u: Unit, goal: Pos, exact: Point, dt: float, *, settle: bool = False) -> bool:
        """Plan (once) and walk towards *goal*; True when the path is exhausted."""
        if u.path_goal != goal:
            self._plan(u, goal, exact)
        return self._follow(u, dt, settle=settle)

    def _next_waypoint(self, u: Unit, *, precise: bool = False) -> Point | None:
        if u.path:
            if len(u.path) == 1 and u.exact is not None and u.path[0] != u.tile:
                return u.exact
            return tile_center(u.path[0])  # a detour back to the unit's own tile centre is walked first
        # Work requires contact, so the walking tolerance cannot discard a
        # final step that would put the worker inside interaction range.
        if u.exact is not None and dist(u.pos, u.exact) > (1e-6 if precise else ARRIVE):
            return u.exact
        return None

    def _follow(self, u: Unit, dt: float, *, settle: bool = False, navigation: bytearray | None = None,
                precise: bool = False) -> bool:
        """Step along the path; True when there was nothing left to walk."""
        waypoint = self._next_waypoint(u, precise=precise)
        if waypoint is None:
            u.state = "idle"
            return True
        u.state = "move"
        grid = self._blocked if navigation is None else navigation
        if u.path and u.path_goal is not None:
            tx, ty = u.tile
            if grid[u.path[0][1] * self.width + u.path[0][0]] or max(abs(u.path[0][0] - tx), abs(u.path[0][1] - ty)) > 1:
                # Something was built across the path, or a crowd pushed the unit off it.
                if self.time >= u.replan_at:
                    self._plan(u, u.path_goal, u.exact, around_units=True, navigation=navigation)
                    return False
                u.path.insert(0, u.tile)
        dx, dy = waypoint[0] - u.x, waypoint[1] - u.y
        d = math.hypot(dx, dy)
        step = self.speed_of(u) * dt
        if d <= step or d <= ARRIVE:
            if navigation is not None and not self._line_clear(u.pos, waypoint, navigation=navigation):
                u.path_goal = None
                return False
            u.x, u.y = waypoint
            if u.path:
                u.path.pop(0)
            if u.exact is not None and dist(u.pos, u.exact) <= ARRIVE:
                u.exact = None
            u.last_distance = math.inf
            return False
        u.facing = math.atan2(dy, dx)
        nx, ny = u.x + dx / d * step, u.y + dy / d * step
        if (grid[int(ny) * self.width + int(nx)] or (navigation is not None and not self._line_clear(u.pos, (nx, ny), navigation=navigation))) and self.passable(*u.tile):
            if u.path and u.path[0] != u.tile:
                # Pushed off course so that the straight line to the next tile crosses a blocked
                # one: go back to this tile's centre first, which is always possible.
                u.path.insert(0, u.tile)
            elif u.path_goal is not None and self.time >= u.replan_at:
                # Even from the centre the straight step to the exact spot crosses a blocked tile: it
                # lies across a corner.  Plan again; the planner never cuts corners, so the path comes
                # in from an open side, or there is none and the walk ends here.
                self._plan(u, u.path_goal, u.exact, navigation=navigation)
            return False
        u.x, u.y = nx, ny
        # Progress watchdog: closing on the goal resets it; a stretch without progress paths
        # again around the units in the way.
        remaining = dist(u.pos, u.exact if u.exact is not None else tile_center(u.path_goal)) if u.path_goal is not None else 0.0
        if remaining < u.last_distance - 0.02:
            u.last_distance = remaining
            u.progress = 0.0
        else:
            u.progress += dt
            if u.progress >= STUCK_AFTER and u.path_goal is not None:
                if settle and remaining <= SETTLE_WITHIN:
                    u.path = []
                    u.exact = None
                    u.state = "idle"
                    return True
                if self.time >= u.replan_at:
                    self._plan(u, u.path_goal, u.exact, around_units=True, navigation=navigation)
                    u.last_distance = remaining
        return False

    def _line_clear(self, a: Point, b: Point, *, navigation: bytearray | None = None) -> bool:
        """No blocked tile on the straight line from *a* to *b*.

        Every tile the segment crosses is visited (a grid walk, not sampling: a
        sample every quarter tile can skip the corner tile a unit standing at a
        building's corner would step into).  Passing exactly through a corner
        needs both tiles beside it free, as a diagonal step in the pathfinder does.
        """
        # Check continuous coordinates before int() can turn -0.1 into tile zero.
        if not (0 <= a[0] < self.width and 0 <= a[1] < self.height
                and 0 <= b[0] < self.width and 0 <= b[1] < self.height):
            return False
        x, y = int(a[0]), int(a[1])
        end_x, end_y = int(b[0]), int(b[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        # Fraction of the segment at which the next vertical / horizontal grid line is crossed.
        next_x = ((x + (step_x > 0)) - a[0]) / dx if dx else math.inf
        next_y = ((y + (step_y > 0)) - a[1]) / dy if dy else math.inf
        per_x, per_y = (abs(1 / dx) if dx else math.inf), (abs(1 / dy) if dy else math.inf)
        if navigation is None:
            passable = self.passable
        else:
            def passable(x: int, y: int) -> bool:
                return 0 <= x < self.width and 0 <= y < self.height and not navigation[y * self.width + x]
        for _ in range(abs(end_x - x) + abs(end_y - y) + 1):
            if not passable(x, y):
                return False
            if x == end_x and y == end_y:
                return True
            if abs(next_x - next_y) < 1e-9:
                if not (passable(x + step_x, y) and passable(x, y + step_y)):
                    return False
                x, y = x + step_x, y + step_y
                next_x, next_y = next_x + per_x, next_y + per_y
            elif next_x < next_y:
                x, next_x = x + step_x, next_x + per_x
            else:
                y, next_y = y + step_y, next_y + per_y
        return passable(x, y)

    def _steer(self, u: Unit, target: Point, dt: float) -> bool:
        """Walk straight at *target* when it is near and the line is clear; True if that was possible."""
        if dist(u.pos, target) > STEER_RANGE or not self._line_clear(u.pos, target):
            return False
        dx, dy = target[0] - u.x, target[1] - u.y
        d = math.hypot(dx, dy)
        if d >= 1e-6:
            step = min(d, self.speed_of(u) * dt)
            u.facing = math.atan2(dy, dx)
            u.x, u.y = u.x + dx / d * step, u.y + dy / d * step  # on the segment, so on a tile just checked
        u.path = []
        u.path_goal = None
        u.exact = None
        u.state = "move"
        return True

    def _separate(self) -> None:
        """Push overlapping units apart, never into blocked tiles."""
        moves: dict[int, tuple[float, float]] = {}
        for u in self.units.values():
            if u.hidden:
                continue
            px = py = 0.0
            for v in self.units_near(u.pos, 2 * UNIT_RADIUS):
                if v is u or v.hidden:
                    continue
                dx, dy = u.x - v.x, u.y - v.y
                d = math.hypot(dx, dy)
                overlap = u.radius + v.radius - d
                if overlap <= 0:
                    continue
                if d < 1e-6:
                    angle = (u.id * 2.399) % (2 * math.pi)
                    dx, dy, d = math.cos(angle), math.sin(angle), 1.0
                weight = 0.5 if v.state == "move" or u.state != "move" else 0.2
                px += dx / d * overlap * weight
                py += dy / d * overlap * weight
                if u.state == "move":
                    # Walking units also step to their own right, so two meeting head-on pass
                    # each other instead of pushing each other back along the same line forever.
                    hx, hy = math.cos(u.facing), math.sin(u.facing)
                    px += -hy * overlap * SIDESTEP
                    py += hx * overlap * SIDESTEP
            if px or py:
                moves[u.id] = (px, py)
        for uid, (px, py) in moves.items():
            u = self.units[uid]
            self._nudge(u, px, py)

    def _nudge(self, u: Unit, px: float, py: float) -> None:
        """Shove *u* by at most MAX_PUSH, never through a blocked tile or across a blocked corner."""
        length = math.hypot(px, py)
        if length > MAX_PUSH:
            px, py = px / length * MAX_PUSH, py / length * MAX_PUSH
        own_tile_open = self.passable(*u.tile)
        for dx, dy in ((px, py), (px, 0.0), (0.0, py)):
            nx, ny = self._clamp((u.x + dx, u.y + dy))
            if self._line_clear(u.pos, (nx, ny)) if own_tile_open else self.passable(int(nx), int(ny)):
                u.x, u.y = nx, ny
                return

    # -- Combat ----------------------------------------------------------------------

    def _target_point(self, target: Entity) -> Point:
        return target.pos if isinstance(target, Unit) else target.center

    def _face(self, u: Unit, point: Point) -> None:
        dx, dy = point[0] - u.x, point[1] - u.y
        if dx or dy:
            u.facing = math.atan2(dy, dx)

    def _gap(self, source: Entity, target: Entity) -> float:
        """Distance between the edges of two entities."""
        if isinstance(source, Unit):
            if isinstance(target, Unit):
                return dist(source.pos, target.pos) - source.radius - target.radius
            return rect_gap(source.pos, target.rect) - source.radius
        if isinstance(target, Unit):
            return rect_gap(target.pos, source.rect) - target.radius
        return dist(source.center, target.center) - source.size / 2 - target.size / 2

    def _in_range(self, u: Unit, target: Entity) -> bool:
        if isinstance(target, Unit) and target.hidden:
            return False
        return self._gap(u, target) <= self.range_of(u) + 0.05

    def _nearest_enemy(self, player: int, point: Point, radius: float, *, units_only: bool = False) -> Entity | None:
        best: Entity | None = None
        best_d = math.inf
        for unit in self.units_near(point, radius + UNIT_RADIUS):
            if unit.player == player or unit.hidden or unit.hp <= 0:
                continue
            d = dist(point, unit.pos)
            if d <= radius + unit.radius and d < best_d:
                best, best_d = unit, d
        if best is not None or units_only:
            return best
        for building in self.buildings.values():
            if building.player is None or building.player == player or building.hp <= 0:
                continue
            d = rect_gap(point, building.rect)
            if d <= radius and d + 0.5 < best_d:  # a unit in reach beats a building
                best, best_d = building, d + 0.5
        return best

    def _strike(self, u: Unit, target: Entity) -> None:
        """One blow (or shot) from *u* at *target*, with splash for siege engines."""
        damage = self.damage_of(u)
        self._hit(u, target, damage)
        if u.info.splash > 0:
            centre = self._impact_point(u, target)
            for other in list(self.units_near(centre, u.info.splash + UNIT_RADIUS)):
                if other is not target and other.player != u.player and not other.hidden and other.hp > 0:
                    self._hit(u, other, int(damage * SPLASH_FRACTION))
            for building in list(self.buildings.values()):
                if building is not target and building.player not in (None, u.player) and building.hp > 0 and rect_gap(centre, building.rect) <= u.info.splash:
                    self._hit(u, building, int(damage * SPLASH_FRACTION))

    def _impact_point(self, u: Unit, target: Entity) -> Point:
        """Where a shot lands: on a unit, or on the wall of a building nearest the shooter."""
        if isinstance(target, Unit):
            return target.pos
        x, y, w, h = target.rect
        return (min(max(u.x, x), x + w), min(max(u.y, y), y + h))

    def _hit(self, source: Entity, target: Entity, damage: int) -> None:
        armor = self.armor_of(target)
        if isinstance(source, Unit) and isinstance(target, Building):
            damage = int(round(damage * source.info.siege))
        roll = damage * self.rng.uniform(1 - HIT_VARIANCE, 1 + HIT_VARIANCE)
        dealt = max(1, int(round(roll)) - armor)
        target.hp -= dealt
        ranged = source.info.range >= 1
        self.events.append(Event("hit", self._target_point(target), player=target.player, entity=source.id, other=target.id,
                                 amount=dealt, text="ranged" if ranged else "melee", source_type=source.type.value,
                                 target_type=target.type.value, target_armor=armor,
                                 target_complete=not isinstance(target, Building) or target.done))
        if target.player is not None:
            victim = self.players[target.player]
            if self.time - victim.last_alert >= UNDER_ATTACK_COOLDOWN:
                victim.last_alert = self.time
                self.events.append(Event("under_attack", self._target_point(target), player=target.player, entity=target.id))
        if isinstance(target, Unit) and target.hp > 0 and not target.orders and not target.is_worker and target.info.damage > 0:
            attacker_alive = source.id in self.units or source.id in self.buildings
            if attacker_alive and not (isinstance(source, Building)):
                target.home = target.pos
                target.orders.append(Attack(source.id, auto=True))

    def _bury_the_dead(self) -> None:
        for unit in [u for u in self.units.values() if u.hp <= 0]:
            self._remove_unit(unit)
        for building in [b for b in self.buildings.values() if b.hp <= 0 and b.type is not BuildingType.GOLD_MINE]:
            self._remove_building(building, reason="destroyed")

    def _remove_unit(self, unit: Unit) -> None:
        del self.units[unit.id]
        if unit.constructing is not None:
            b = self.buildings.get(unit.constructing)
            if b is not None and b.builder == unit.id:
                b.builder = None
        self.events.append(Event("death", unit.pos, player=unit.player, entity=unit.id, text=unit.type.value))

    def _remove_building(self, b: Building, *, reason: str) -> None:
        del self.buildings[b.id]
        self._set_blocked(b, False)
        for unit in self.units.values():
            if unit.inside == b.id:
                unit.inside = None
                unit.timer = 0.0
            if unit.constructing == b.id:
                unit.constructing = None
                if unit.orders and isinstance(unit.orders[0], Build):
                    unit.orders.popleft()
        self.events.append(Event(reason, b.center, player=b.player, entity=b.id, text=b.type.value))

    # -- Helpers for orders ----------------------------------------------------------


    def _nearest_mine(self, point: Point, max_distance: float = 14.0) -> Building | None:
        mines = [m for m in self.mines() if m.gold > 0 and dist(m.center, point) <= max_distance]
        return min(mines, key=lambda m: dist(m.center, point)) if mines else None

    def nearest_tree(self, point: Point, radius: int) -> Pos | None:
        cx, cy = int(point[0]), int(point[1])
        best, best_d = None, math.inf
        for y in range(max(0, cy - radius), min(self.height, cy + radius + 1)):
            for x in range(max(0, cx - radius), min(self.width, cx + radius + 1)):
                if self.terrain[y][x] is Terrain.TREES:
                    d = dist(point, tile_center((x, y)))
                    if d < best_d and self._reachable_edge((x, y)):
                        best, best_d = (x, y), d
        return best

    def _reachable_edge(self, tile: Pos) -> bool:
        """A tree a peasant can stand next to."""
        x, y = tile
        return any(self.passable(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)

    # -- Outcome ---------------------------------------------------------------------

    def _check_elimination(self) -> None:
        for player in self.players:
            if player.alive and not self.player_units(player.id) and not self.player_buildings(player.id):
                player.alive = False
                self.events.append(Event("eliminated", (0.0, 0.0), player=player.id, text=f"{player.name} has fallen"))
        alive = [p for p in self.players if p.alive]
        if self.winner is None and len(alive) == 1 and len(self.players) > 1:
            self.winner = alive[0].id
            self.events.append(Event("victory", (0.0, 0.0), player=self.winner, text=f"{alive[0].name} wins"))

    # -- Serialisation ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width, "height": self.height, "theme": self.theme.value,
            "terrain": ["".join(t.value[0] for t in row) for row in self.terrain],
            "players": [{"id": p.id, "human": p.human, "gold": p.gold, "lumber": p.lumber, "alive": p.alive, "last_alert": p.last_alert,
                         "upgrades": sorted(u.value for u in p.upgrades)} for p in self.players],
            "units": [_unit_to_dict(u) for u in self.units.values()],
            "buildings": [_building_to_dict(b) for b in self.buildings.values()],
            "explored": [bytes(e).hex() for e in self.explored],
            "worker_knowledge": [knowledge.to_dict() for knowledge in self.worker_knowledge],
            "time": self.time, "tick": self.tick, "next_id": self._next_id, "winner": self.winner,
            "rng": self.rng.getstate(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> World:
        letters = {t.value[0]: t for t in Terrain}
        terrain = [[letters[c] for c in row] for row in data["terrain"]]
        human = next((p["id"] for p in data["players"] if p["human"]), None)
        world = cls(data["width"], data["height"], terrain, len(data["players"]), human=human, theme=MapTheme(data["theme"]))
        for p, saved in zip(world.players, data["players"]):
            p.human = saved["human"]
            p.gold, p.lumber, p.alive, p.last_alert = saved["gold"], saved["lumber"], saved["alive"], saved["last_alert"]
            p.upgrades = {Upgrade(u) for u in saved["upgrades"]}
        for saved in data["buildings"]:
            b = _building_from_dict(saved)
            world.buildings[b.id] = b
            world._set_blocked(b, True)
        for saved in data["units"]:
            u = _unit_from_dict(saved)
            world.units[u.id] = u
        world.explored = [bytearray(bytes.fromhex(e)) for e in data["explored"]]
        if "worker_knowledge" in data:
            world.worker_knowledge = [WorkerKnowledge.from_dict(knowledge) for knowledge in data["worker_knowledge"]]
        world.time, world.tick, world._next_id, world.winner = data["time"], data["tick"], data["next_id"], data["winner"]
        state = data["rng"]
        world.rng.setstate((state[0], tuple(state[1]), state[2]))
        world._index_units()
        world.update_vision()
        return world


def _order_to_dict(order: Order) -> dict[str, Any]:
    # Keep player-order fields compatible with existing warband-v1 clients.
    # Automatic routing metadata lives beside the queue in each unit record.
    if isinstance(order, Harvest):
        return {"kind": "Harvest", "target": list(order.target) if isinstance(order.target, tuple) else order.target}
    if isinstance(order, Deposit):
        return {"kind": "Deposit"}
    d: dict[str, Any] = {"kind": type(order).__name__}
    for key, value in vars(order).items():
        d[key] = value.value if hasattr(value, "value") else (list(value) if isinstance(value, tuple) else value)
    return d


def _order_from_dict(d: dict[str, Any]) -> Order:
    kind = _ORDER_TYPES[d["kind"]]
    fields = {k: v for k, v in d.items() if k != "kind"}
    if kind is Build:
        fields["type"] = BuildingType(fields["type"])
        fields["pos"] = tuple(fields["pos"])
    elif kind is Harvest and isinstance(fields["target"], list):
        fields["target"] = tuple(fields["target"])
    elif kind in (Move, AttackMove):
        fields["target"] = tuple(fields["target"])
    elif kind is Patrol:
        fields["start"], fields["end"] = tuple(fields["start"]), tuple(fields["end"])
    return kind(**fields)


def _unit_to_dict(u: Unit) -> dict[str, Any]:
    return {
        "id": u.id, "type": u.type.value, "player": u.player, "x": u.x, "y": u.y, "hp": u.hp, "facing": u.facing,
        "orders": [_order_to_dict(o) for o in u.orders], "cooldown": u.cooldown,
        "worker_orders": [{"index": index, "auto": order.auto,
                           **({"target": order.target} if isinstance(order, Deposit) else {})}
                          for index, order in enumerate(u.orders) if isinstance(order, (Harvest, Deposit))],
        "carrying": u.carrying.value if u.carrying else None, "carry": u.carry, "timer": u.timer,
        "inside": u.inside, "constructing": u.constructing, "home": list(u.home) if u.home else None, "state": u.state,
        "charge": u.charge, "auto_work": u.auto_work,
    }


def _unit_from_dict(d: dict[str, Any]) -> Unit:
    u = Unit(d["id"], UnitType(d["type"]), d["player"], d["x"], d["y"], d["hp"], facing=d["facing"], cooldown=d["cooldown"],
             carrying=Resource(d["carrying"]) if d["carrying"] else None, carry=d["carry"], timer=d["timer"],
             inside=d["inside"], constructing=d["constructing"], home=tuple(d["home"]) if d["home"] else None, state=d["state"],
             charge=d["charge"], auto_work=d.get("auto_work", True))
    u.orders = deque(_order_from_dict(o) for o in d["orders"])
    for state in d.get("worker_orders", []):
        order = u.orders[state["index"]]
        if not isinstance(order, (Harvest, Deposit)):
            raise ValueError("Worker metadata must refer to a harvest or deposit order")
        order.auto = state["auto"]
        if isinstance(order, Deposit):
            order.target = state["target"]
    return u


def _building_to_dict(b: Building) -> dict[str, Any]:
    return {
        "id": b.id, "type": b.type.value, "player": b.player, "x": b.x, "y": b.y, "hp": b.hp, "progress": b.progress,
        "queue": [t.value for t in b.queue], "train_progress": b.train_progress, "rally": list(b.rally) if b.rally else None,
        "gold": b.gold, "builder": b.builder, "cooldown": b.cooldown,
        "research": b.research.value if b.research else None, "research_progress": b.research_progress,
    }


def _building_from_dict(d: dict[str, Any]) -> Building:
    return Building(d["id"], BuildingType(d["type"]), d["player"], d["x"], d["y"], d["hp"], progress=d["progress"],
                    queue=[UnitType(t) for t in d["queue"]], train_progress=d["train_progress"],
                    rally=tuple(d["rally"]) if d["rally"] else None, gold=d["gold"], builder=d["builder"], cooldown=d["cooldown"],
                    research=Upgrade(d["research"]) if d["research"] else None, research_progress=d["research_progress"])
