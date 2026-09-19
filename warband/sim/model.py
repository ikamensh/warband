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

import functools
import math
import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from types import FunctionType
from typing import Any, Final, Iterable, Iterator, Literal

from warband.sim import path as pathing
from warband.sim.races import RACES
try:
    from warband.sim import _native  # vision's painting in C, built only with the compiled simulation (warband/league/fastsim.py)
except ImportError:  # the source runs, as it does in the game
    _native = None  # type: ignore[assignment]
_any_lit: Final = None if _native is None else _native.any_lit  # looked up once: any_visible is asked often

from warband.sim.settlement import Plan, Settlement
from warband.sim.worker_knowledge import WorkerKnowledge
from warband.sim.rules import (
    Layout,
    REPAIR_CHUNK, REPAIR_RATE, repair_cost,
    ARMOR_BONUS, ARROWS_BONUS, BLADES_BONUS, BLASTING_POWDER_BONUS, BLESSING_BONUS, BLOODLUST_BONUS, BUILDINGS, CHOP_TIME, DEEP_MINING_TRIP,
    FRENZY_BONUS, GOLD_PER_TRIP, HIT_VARIANCE, HORSES_BONUS, LEASH, LONGBOWS_BONUS, LUMBER_PER_TRIP, MINE_GOLD, MINE_SLOTS, MINE_TIME, PLAYERS,
    PLUNDER_SHARE, REGROWTH_SECONDS, SIEGE_DAMAGE_BONUS, SIEGE_RANGE_BONUS, SIM_DT, SPLASH_FRACTION, STARTING_GOLD, STARTING_LUMBER,
    ARROW_SPEED, DIRECT_HIT, FRIENDLY_MARGIN, SIEGE_BUILDING_WORTH, SIEGE_STEP, SIEGE_WORTH, STONE_MIN_FLIGHT, STONE_SPEED, WINDUP_SLACK,
    MAX_QUEUED_ORDERS, UNDER_ATTACK_COOLDOWN, UNIT_RADIUS, UNITS, UPGRADES, VISION_EVERY, BuildingInfo, BuildingType, Cost, MapTheme, Race, Resource,
    Terrain, UnitInfo, UnitType, Upgrade, ArmorClass, AttackType, damage_factor,
)

#: The fastest any unit of any race moves, with every upgrade: how far off a friend can be and still walk under a stone
#: before it lands.
_FASTEST: Final = max(info.speed for race in RACES.values() for info in race.units.values()) + HORSES_BONUS
Pos = tuple[int, int]
Point = tuple[float, float]

# Bound once: compiled code (warband/league/fastsim.py) would otherwise look it up in math at every call.
_atan2: Final = math.atan2
_math_hypot: Final = math.hypot
_VELTKAMP: Final = 134217729.0  # 2 ** 27 + 1, which splits a double into halves whose products are exact


def _two_product(a: float, b: float) -> tuple[float, float]:
    """``(a * b, the exact rounding error of that product)``, as CPython's ``dl_mul`` gets it from fma():
    Shewchuk's TwoProduct, exact wherever nothing underflows."""
    product = a * b
    t = a * _VELTKAMP
    a_hi = t - (t - a)
    a_lo = a - a_hi
    t = b * _VELTKAMP
    b_hi = t - (t - b)
    b_lo = b - b_hi
    error = product - a_hi * b_hi
    error = error - a_lo * b_hi
    error = error - a_hi * b_lo
    return product, a_lo * b_lo - error


def hypot(x: float, y: float) -> float:
    """``math.hypot(x, y)``, worked out step for step as CPython 3.13 does it (``vector_norm`` in
    Modules/mathmodule.c), so that the compiled simulation (warband/league/fastsim.py) has it as arithmetic in C
    rather than as a call into the math module.  Run from source, this name is ``math.hypot`` itself (below).

    Magnitudes outside 2**-1000..2**1000, a coordinate so much smaller than the other that its square would
    underflow, zeros, infinities and NaNs go to math.hypot.  ``tests/warband/test_fastsim.py`` compares the two."""
    x = math.fabs(x)
    y = math.fabs(y)
    big = x if x > 0.0 else 0.0  # CPython's running maximum over the coordinates, from 0.0
    if y > big:
        big = y
    small = y if big == x else x
    if (not 9.332636185032189e-302 <= big <= 1.0715086071862673e+301  # 2**-1000 and 2**1000
            or 0.0 < small < big * 3.054936363499605e-151 or x != x or y != y):  # 2**-500
        return _math_hypot(x, y)
    scale = 1.0  # frexp's power of two: big * scale in [0.5, 1)
    while big * scale >= 1.0:
        scale *= 0.5
    while big * scale < 0.5:
        scale *= 2.0
    csum = 1.0
    frac1 = 0.0
    frac2 = 0.0
    square, error = _two_product(x * scale, x * scale)  # the coordinates in CPython's order, squared exactly,
    total = csum + square                                # summed with compensation
    frac2 += (csum - total) + square
    csum = total
    frac1 += error
    square, error = _two_product(y * scale, y * scale)
    total = csum + square
    frac2 += (csum - total) + square
    csum = total
    frac1 += error
    h = math.sqrt(csum - 1.0 + (frac1 + frac2))
    square, error = _two_product(-h, h)
    total = csum + square
    frac2 += (csum - total) + square
    csum = total
    frac1 += error
    x = csum - 1.0 + (frac1 + frac2)
    h += x / (2.0 * h)  # the differential correction
    return h / scale


hypot_port: Final = hypot  # the port itself, whichever hypot runs, for the test that compares it with math.hypot
if isinstance(hypot, FunctionType):  # run from source: math.hypot is far quicker than this port interpreted
    hypot = math.hypot  # type: ignore[assignment]  # noqa: F811

BLOCKING: Final = frozenset({Terrain.WATER, Terrain.TREES, Terrain.ROCK})
ARRIVE: Final = 0.12  # a unit is "there" within this many tiles of its target point
TOUCH: Final = 0.4  # gap at which a peasant can enter a mine, deliver, or start building (a diagonal neighbour counts)
STUCK_AFTER: Final = 0.8  # seconds without progress before a unit paths again around the units in its way
REPLAN_EVERY: Final = 0.6  # a unit plans at most this often unless it gets a new order (a melee would otherwise plan every tick)
REPLAN_STAGGER: Final = 8  # ticks over which units spread their next plans by id, so a crowd does not plan in lockstep
STEER_RANGE: Final = 4.0  # within this many tiles a unit walks straight at its target when the line is clear, without A*
LOCAL_EXPANSIONS: Final = 700  # A* budget for the detours around other units; those goals are close
SETTLE_WITHIN: Final = 1.0  # a plain walk counts as arrived when a crowd keeps the unit this close to its spot without progress
MINE_CLEARANCE: Final = 2  # tiles kept free around a gold mine so peasants can get in and out
SIDESTEP: Final = 0.6  # lateral share of the push when walking units collide
MAX_PUSH: Final = 0.25  # tiles a crowd can shove a unit in one step; eight overlapping units once summed to a jump over a tree wall
# Standing at ease (docs/unit-motion.md part 5): units that are neither fighting nor working keep a little
# elbow room, and a unit hemmed in by its neighbours takes a short step away from them now and then.
SPACING: Final = 0.2  # tiles of clearance beyond touching that units at ease keep between each other; a soft push
SPACING_WEIGHT: Final = 0.15  # share of the missing clearance closed per step, gentler than the overlap push
EASE_SPACE: Final = 1.0  # a standing unit with a neighbour's centre closer than this feels crowded
EASE_EVERY: Final = 5  # ticks between a crowded unit's chances to step away
EASE_CHANCE: Final = 0.12  # that a crowded unit steps away at one of those chances: about once every two seconds
EASE_STEP: Final = 0.4  # tiles of the step, give or take EASE_STEP_VARIANCE
EASE_STEP_VARIANCE: Final = 0.3
EASE_JITTER: Final = 0.7  # radians either side of straight away from the crowd the step may veer
EASE_GAIN: Final = 0.1  # tiles more room the spot must offer than where the unit stands, so nobody steps into a neighbour
AUTO_EVERY: Final = round(1 / SIM_DT)  # ticks between an idle building's looks at its endless recruits: the settlement's second


def recorded(method):
    """An order the world takes from a player.

    While :attr:`World.orders` is a list, every call from outside the simulation
    is appended to it as ``[tick, name, args, kwargs]`` in plain JSON values
    before it runs, so a replay can give the same order at the same tick (and
    meet the same rule error).  Orders the simulation gives itself, while
    stepping or while carrying out another order, are that step's or order's
    own business and are not logged.
    """
    name = method.__name__

    @functools.wraps(method)
    def order(self, *args, **kwargs):
        if self._order_depth == 0 and self.orders is not None:
            self.orders.append([self.tick, name, _plain(args), _plain(kwargs)])
        self._order_depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._order_depth -= 1

    order.is_order = True  # what :data:`warband.records.replay.ORDERS` is built from; a plain wrapper flag would also match staticmethods
    return order


def _plain(value: Any) -> Any:
    """*value* as the JSON types a log can hold: enums by value, tuples as lists, copies of lists and dicts."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


class RuleError(Exception):
    """An order the rules forbid.  The message says why."""


# -- Orders --------------------------------------------------------------------


@dataclass
class Move:
    target: Point
    pace: float | None = None  # slowest speed_of in the group at issue time; None: walk at full speed


@dataclass
class AttackMove:
    target: Point
    pace: float | None = None  # as Move.pace


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
    plan_if_short: bool = False  # a site the builder cannot pay for on arrival is left as a settlement plan, not refused


@dataclass
class Hold:
    """Stand here; fight what comes in range but never chase."""

    target: int | None = None  # what the unit is winding up against, while it stays in reach


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
AT_EASE_ORDERS: Final = (Move, AttackMove, Patrol)  # walked at ease: no target to close on, no work to press for

_ORDER_TYPES: Final[dict[str, type]] = {cls.__name__: cls for cls in (Move, AttackMove, Attack, Harvest, Deposit, Build, Hold, Heal, Patrol, Repair)}


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
    surrendered: bool = False
    last_alert: float = -1000.0
    upgrades: set[Upgrade] = field(default_factory=set)
    assembly: Point | None = None
    race: Race = Race.HUMAN
    stats: dict[str, int] = field(default_factory=lambda: {
        "units_killed": 0, "units_lost": 0, "buildings_razed": 0, "buildings_lost": 0, "destroyed_value": 0,
    })  # the battle record; kills belong to the force that struck the lethal blow


@dataclass
class Unit:
    id: int
    type: UnitType
    player: int
    x: float
    y: float
    hp: int
    race: Race = Race.HUMAN  # its owner's; the race's UnitInfo is what this unit reports
    facing: float = math.pi / 2  # radians, 0 = +x, pi/2 = +y (down the screen)
    orders: deque[Order] = field(default_factory=deque)
    path: list[Pos] = field(default_factory=list)
    path_goal: Pos | None = None
    exact: Point | None = None  # the point to stop at once the last path tile is reached
    cooldown: float = 0.0
    windup: float = 0.0  # seconds left of the blow being drawn back; the unit stands committed while it is above zero
    vx: float = 0.0  # tiles per second the unit moved of its own accord last step, for leading it with a stone
    vy: float = 0.0
    carrying: Resource | None = None
    carry: int = 0
    timer: float = 0.0
    inside: int | None = None  # the mine this peasant is in
    constructing: int | None = None
    home: Point | None = None  # where an auto-acquired chase started
    ease: Point | None = None  # where a unit standing at ease is stepping to for elbow room
    state: str = "idle"  # idle | move | attack | chop | build
    progress: float = 0.0
    last_distance: float = math.inf
    charge: float = 0.0  # healing accumulated below one hit point
    replan_at: float = 0.0  # simulation time from which the unit may plan again
    auto_work: bool = True  # Stop/Hold parks a worker until another order is given.

    radius = UNIT_RADIUS

    def __post_init__(self) -> None:
        # Type and race are fixed for life, so the stats they select are read once
        # rather than through RACES on every one of a match's millions of lookups.
        self.info: UnitInfo = RACES[self.race].units[self.type]
        self.max_hp: int = self.info.hp
        self.is_worker: bool = self.type is UnitType.PEASANT

    @property
    def pos(self) -> Point:
        return (self.x, self.y)

    @property
    def tile(self) -> Pos:
        return (int(self.x), int(self.y))

    @property
    def hidden(self) -> bool:
        """Inside a mine or a building under construction: not on the map."""
        return self.inside is not None or self.constructing is not None

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
    abandoned: bool = False  # left behind by a resigned or surrendered player: nobody's, attackable, inert
    race: Race = Race.HUMAN  # its owner's; a gold mine is nobody's
    auto: list[UnitType] = field(default_factory=list)  # trained endlessly, in turn: the next one first (set_auto_train)

    def __post_init__(self) -> None:
        # Type, race and position are fixed once a building is placed, so its stats and
        # its footprint are worked out here: vision, navigation grids and worker routing
        # read them millions of times a match.
        self.info: BuildingInfo = RACES[self.race].buildings[self.type]
        size = self.size = self.info.size
        self.max_hp: int = self.info.hp
        self._build_time: float = self.info.build_time
        self.pos: Pos = (self.x, self.y)
        self.center: Point = (self.x + size / 2, self.y + size / 2)
        self.rect: tuple[int, int, int, int] = (self.x, self.y, size, size)
        self._tiles: tuple[Pos, ...] = tuple((self.x + dx, self.y + dy) for dy in range(size) for dx in range(size))

    @property
    def done(self) -> bool:
        return self.progress >= self._build_time

    def tiles(self) -> tuple[Pos, ...]:
        return self._tiles

    def contains(self, point: Point) -> bool:
        return self.x <= point[0] < self.x + self.size and self.y <= point[1] < self.y + self.size


Entity = Unit | Building


@dataclass
class Projectile:
    """A shot in the air.  An arrow (``target`` set) follows its mark and strikes it when it arrives;
    a siege stone (``target`` None) comes down on ``aim``, the ground it was fired at, on whoever
    stands there by then.  The shooter may be dead before the shot lands: what the blow needs of
    it is copied here."""

    id: int
    player: int
    source: int  # the shooter's id
    source_type: str  # its UnitType or BuildingType value, for the blow's event
    kind: str  # "arrow" | "stone"
    start: Point
    aim: Point  # where it was fired at
    target: int | None
    launched: float  # simulation time
    flight: float  # seconds in the air
    damage: int
    splash: float = 0.0
    attack: AttackType = AttackType.NORMAL

    @property
    def lands_at(self) -> float:
        return self.launched + self.flight


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
    # Strike-time facts survive removal of either participant and network snapshots; a recruit's
    # training and a building's start and completion name its type the same way: either can fall the step it appears.
    source_type: str = ""
    target_type: str = ""
    target_armor: int = 0
    target_complete: bool = True


# -- Geometry helpers ------------------------------------------------------------


def dist(a: Point, b: Point) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def rect_gap(point: Point, rect: tuple[int, int, int, int]) -> float:
    """Distance from *point* to the nearest point of *rect* (0 inside)."""
    x, y, w, h = rect
    px, py = point
    dx = x - px if px < x else px - (x + w)  # at most one of the two sides can be overshot
    dy = y - py if py < y else py - (y + h)
    return hypot(dx if dx > 0.0 else 0.0, dy if dy > 0.0 else 0.0)


def rects_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """Tiles of clearance between two tile rectangles (Chebyshev; 0 when they touch or overlap)."""
    dx = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), 0)
    dy = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]), 0)
    return max(dx, dy)


def shell_hp(info: BuildingInfo, progress: float) -> int:
    """Hit points *progress* seconds of building have earned a shell: a tenth to start with, the rest at the build rate.

    Construction only ever adds the difference between two readings, so blows taken meanwhile stay taken."""
    start = max(1, info.hp // 10)
    return start + int((info.hp - start) * min(progress, info.build_time) / info.build_time)


def tile_center(pos: Pos) -> Point:
    return (pos[0] + 0.5, pos[1] + 0.5)


def _sight_spans(radius: int) -> list[tuple[int, int, bytes]]:
    """Per row offset of a sight disc: how far it reaches sideways (the largest dx with
    dx² + dy² ≤ r² + r) and the run of flags that paints the row."""
    halves = [math.isqrt(radius * radius + radius - dy * dy) for dy in range(-radius, radius + 1)]
    return [(dy, half, b"\x01" * (2 * half + 1)) for dy, half in zip(range(-radius, radius + 1), halves)]


_SIGHT: Final[dict[int, list[tuple[int, int, bytes]]]] = {}


def sight_spans(radius: int) -> list[tuple[int, int, bytes]]:
    if radius not in _SIGHT:
        _SIGHT[radius] = _sight_spans(radius)
    return _SIGHT[radius]


def or_into(target: bytearray, source: bytes | bytearray) -> None:
    """``target[i] |= source[i]`` for every byte of two flag grids, done in C through big integers."""
    if _native is not None:
        _native.or_into(target, source)
        return
    target[:] = (int.from_bytes(target, "little") | int.from_bytes(source, "little")).to_bytes(len(target), "little")


# -- World ---------------------------------------------------------------------


class World:
    def __init__(self, width: int, height: int, terrain: list[list[Terrain]], player_count: int, *,
                 human: int | None = 0, rng: random.Random | None = None, theme: MapTheme = MapTheme.SUMMER,
                 races: list[Race] | tuple[Race, ...] | None = None, layout: Layout = Layout.PLAINS,
                 scripted: bool = False) -> None:
        if len(terrain) != height or any(len(row) != width for row in terrain):
            raise ValueError("terrain must be height rows of width tiles")
        if races is not None and len(races) != player_count:
            raise ValueError(f"{player_count} players need {player_count} races, not {len(races)}")
        self.width = width
        self.height = height
        self.terrain = terrain
        self.theme = theme
        self.layout = layout
        self.scripted = scripted  # a mission decides the outcome: elimination still happens, but nobody surrenders and no winner is declared
        self.players = [Player(i, PLAYERS[i].name, PLAYERS[i].color, human=(i == human), race=races[i] if races is not None else Race.HUMAN)
                        for i in range(player_count)]
        self.regrowth: list[tuple[Pos, float]] = []  # (felled tree tile, simulation time it grows back) — the elven art
        self.units: dict[int, Unit] = {}
        self.buildings: dict[int, Building] = {}
        self.projectiles: dict[int, Projectile] = {}
        self.rng = rng if rng is not None else random.Random(0)
        self.time = 0.0
        self.tick = 0
        self.events: list[Event] = []
        self.winner: int | None = None
        self.orders: list[list[Any]] | None = None  # the order log a replay is made of, see :func:`recorded`
        self._order_depth = 0
        self._next_id = 1
        self._blocked = bytearray(width * height)
        for y in range(height):
            for x in range(width):
                if terrain[y][x] in BLOCKING:
                    self._blocked[y * width + x] = 1
        self.explored = [bytearray(width * height) for _ in self.players]
        self.visible = [bytearray(width * height) for _ in self.players]
        # Units by tile, refilled each step.  Every tile keeps its list for the world's life, so that indexing
        # the units allocates nothing but room for the tiles someone stands on.
        self._buckets: list[list[Unit]] = [[] for _ in range(width * height)]
        self._occupied: list[int] = []  # the tiles of _buckets whose list is not empty
        self._mine_crews: dict[int, int] = {}  # mine id → peasants at its face; kept as they enter and leave
        self.worker_knowledge = [WorkerKnowledge(width, height) for _ in self.players]
        self._worker_ai_checks: dict[int, int] = {}
        self._worker_ai_views: dict[int, tuple[int, Any]] = {}
        self._worker_ai_navigation: dict[int, tuple[int, bytearray]] = {}
        self._worker_ai_routes: dict[int, Any] = {}  # worker_ai._Routes per player, kept across ticks
        self._sight_layers: dict[int, tuple[frozenset[tuple[Pos, int]], bytes]] = {}  # per player, see update_vision()
        # Counters of the only two ways what a player can see and what stands on the map change, so that
        # what is worked out from them can be kept until one moves: update_vision (or reveal_all) runs,
        # a building is placed or removed.
        self._vision_epoch = 0
        self._building_epoch = 0
        self._worker_ai_footprints: dict[int, tuple[tuple[int, int], frozenset[tuple[int, int, int]]]] = {}
        self.settlement = Settlement(self)
        self._exposed: set[int] = set()  # players whose last holdings stand revealed
        self._region_map: pathing.Regions | None = None  # walkable regions of the static grid, see _regions()
        self._pace_groups: dict[tuple[int, Point, float], bool] = {}  # per step, see _group_together()
        self._dangers: dict[int, float] = {}  # per step, see _danger_to()

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

    def shot_mark(self, p: Projectile) -> Point:
        """Where shot *p* is headed: its mark as the mark stands now (an arrow), or the ground it was fired at (a stone)."""
        if p.target is not None:
            target = self.entity(p.target)
            if target is not None:
                return target.pos if isinstance(target, Unit) else target.center
        return p.aim

    def shot_ground(self, p: Projectile, now: float) -> Point:
        """Where shot *p* is over the ground at simulation time *now*, on the line from where it was loosed to its mark."""
        t = max(0.0, min(1.0, (now - p.launched) / p.flight))
        end = self.shot_mark(p)
        return p.start[0] + (end[0] - p.start[0]) * t, p.start[1] + (end[1] - p.start[1]) * t

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
        # The owner is narrowed to an int before it is compared: compiled, two ints compare natively, and an
        # int | None only through Python's ==.
        return [b for b in self.buildings.values() if (building_type is None or b.type is building_type)
                and b.player is not None and b.player == player and not b.abandoned and (done is None or b.done == done)]

    def mines(self) -> list[Building]:
        return [b for b in self.buildings.values() if b.type is BuildingType.GOLD_MINE]

    def units_near(self, point: Point, radius: float) -> list[Unit]:
        """Units whose centre lies within *radius* tiles of *point* (via the spatial buckets of the current step)."""
        px, py = point
        reach = int(radius) + 1
        x0, x1 = max(0, int(px) - reach), min(self.width - 1, int(px) + reach)
        y0, y1 = max(0, int(py) - reach), min(self.height - 1, int(py) + reach)
        r2 = radius * radius
        width, buckets = self.width, self._buckets
        near: list[Unit] = []
        span = x1 - x0 + 1
        # Cell by cell rather than filter(None, a slice of the row): the compiled simulation (warband/league/fastsim.py)
        # runs this loop without making a Python object, which costs the interpreter a little over a slice.
        for y in range(y0, y1 + 1):
            row = y * width + x0
            for index in range(row, row + span):
                cell = buckets[index]
                if cell:
                    for unit in cell:
                        dx, dy = unit.x - px, unit.y - py
                        if dx * dx + dy * dy <= r2:
                            near.append(unit)
        return near

    def _index_units(self) -> None:
        buckets, occupied = self._buckets, self._occupied
        for index in occupied:  # emptied where last step's units stood, rather than all of them
            buckets[index].clear()
        occupied.clear()
        width = self.width
        for unit in self.units.values():
            index = int(unit.y) * width + int(unit.x)
            cell = buckets[index]
            if not cell:
                occupied.append(index)
            cell.append(unit)

    def _bucket(self, unit: Unit) -> None:
        index = int(unit.y) * self.width + int(unit.x)
        cell = self._buckets[index]
        if not cell:
            self._occupied.append(index)
        cell.append(unit)

    # -- Vision ----------------------------------------------------------------

    def is_visible(self, player: int, pos: Pos) -> bool:
        x, y = pos
        width = self.width
        return 0 <= x < width and 0 <= y < self.height and bool(self.visible[player][y * width + x])

    def is_explored(self, player: int, pos: Pos) -> bool:
        x, y = pos
        width = self.width
        return 0 <= x < width and 0 <= y < self.height and bool(self.explored[player][y * width + x])

    def any_visible(self, player: int, rect: tuple[int, int, int, int]) -> bool:
        """Whether *player* sees any tile of *rect*, testing whole rows of the flag grid at a time."""
        x, y, w, h = rect
        width, visible = self.width, self.visible[player]
        if _any_lit is not None:
            return _any_lit(visible, x, y, w, h, width, self.height)
        lo, hi = max(0, x), min(width, x + w)
        if lo >= hi:
            return False
        return any(any(visible[row * width + lo:row * width + hi])
                   for row in range(max(0, y), min(self.height, y + h)))

    def update_vision(self) -> None:
        self._worker_ai_views.clear()
        self._worker_ai_navigation.clear()
        # Collect each player's sight discs first: everything on one tile with one sight radius
        # reveals the very same tiles, and a crowd around a mine or in a battle line is common.
        # Buildings never move, so what they see is painted once and kept until one goes up,
        # comes down or is abandoned; the units' discs go on top of that every time.
        standing: list[set[tuple[Pos, int]]] = [set() for _ in self.players]
        for building in self.buildings.values():
            if building.player is not None and not building.abandoned:
                cx, cy = building.center
                standing[building.player].add(((int(cx), int(cy)), building.info.sight + building.size // 2))
        moving: list[set[tuple[Pos, int]]] = [set() for _ in self.players]
        for unit in self.units.values():
            moving[unit.player].add((unit.tile, unit.info.sight))
        for player in self.players:
            visible = self.visible[player.id]
            discs = standing[player.id]
            layer = self._sight_layers.get(player.id)
            if layer is not None and layer[0] == discs:
                visible[:] = layer[1]
            else:
                visible[:] = bytes(len(visible))
                self._paint(visible, discs)
                self._sight_layers[player.id] = (frozenset(discs), bytes(visible))
            self._paint(visible, moving[player.id] - discs)
            or_into(self.explored[player.id], visible)
            self.worker_knowledge[player.id].refresh(self, player.id)
        self._reveal_last_standings()
        self._vision_epoch += 1

    def _is_exposed(self, player_id: int) -> bool:
        """Alive but with no completed hall and no completed building that trains units."""
        player = self.players[player_id]
        if not player.alive:
            return False
        for b in self.buildings.values():
            if b.player == player_id and b.done:
                if b.type is BuildingType.TOWN_HALL or b.info.trains:
                    return False
        return any(b.player == player_id for b in self.buildings.values())

    def _exposed_players(self) -> set[int]:
        return {p.id for p in self.players if self._is_exposed(p.id)}

    def _reveal_last_standings(self) -> None:
        for exposed_id in sorted(self._exposed_players()):
            holdings = [b for b in self.buildings.values() if b.player == exposed_id]
            if not holdings:
                continue
            for viewer in self.players:
                if viewer.id == exposed_id:
                    continue
                visible = self.visible[viewer.id]
                for b in holdings:
                    for tile in b.tiles():
                        self._reveal(visible, tile, 1)
                or_into(self.explored[viewer.id], visible)
            if exposed_id not in self._exposed:
                self._exposed.add(exposed_id)
                self.events.append(Event("exposed", holdings[0].center, player=exposed_id,
                                         text=self.players[exposed_id].name))

    def _paint(self, visible: bytearray, discs: set[tuple[Pos, int]]) -> None:
        """:meth:`_reveal` every one of *discs*, each a ``(tile, radius)``."""
        if _native is not None:
            _native.stamp_discs(visible, discs, self.width, self.height)
            return
        for at, sight in discs:
            self._reveal(visible, at, sight)

    def _reveal(self, visible: bytearray, at: Pos, radius: int) -> None:
        width, height = self.width, self.height
        x0, y0 = at
        if radius <= x0 < width - radius and radius <= y0 < height - radius:
            # No row of the disc reaches an edge, so every row's run goes in whole.
            centre = (y0 - radius) * width + x0
            for _dy, half, run in sight_spans(radius):
                visible[centre - half:centre + half + 1] = run
                centre += width
            return
        for dy, half, run in sight_spans(radius):
            y = y0 + dy
            if 0 <= y < height:
                lo, hi = x0 - half, x0 + half + 1
                if lo < 0:
                    lo = 0
                if hi > width:
                    hi = width
                if lo < hi:
                    visible[y * width + lo:y * width + hi] = run[:hi - lo]

    def reveal_all(self, player: int) -> None:
        """Explore (and, until the next vision update, see) the whole map."""
        self._worker_ai_views.pop(player, None)
        self._worker_ai_navigation.pop(player, None)
        for i in range(self.width * self.height):
            self.explored[player][i] = 1
            self.visible[player][i] = 1
        self.worker_knowledge[player].refresh(self, player)
        self._vision_epoch += 1

    # -- Stats with upgrades applied ----------------------------------------------------

    def _has(self, player: int | None, upgrade: Upgrade) -> bool:
        return player is not None and upgrade in self.players[player].upgrades

    def race_of(self, player: int | None) -> Race:
        return self.players[player].race if player is not None else Race.HUMAN

    def unit_info(self, player: int | None, unit_type: UnitType) -> UnitInfo:
        """What *unit_type* is for *player*'s race: its name, numbers and training time."""
        return RACES[self.race_of(player)].units[unit_type]

    def building_info(self, player: int | None, building_type: BuildingType) -> BuildingInfo:
        return RACES[self.race_of(player)].buildings[building_type]

    def damage_of(self, entity: Entity) -> int:
        """Listed damage plus every upgrade its owner has researched, and an orc's frenzy."""
        info = entity.info
        damage = info.damage
        if damage == 0:
            return 0
        if isinstance(entity, Unit) and entity.info.melee and not entity.is_worker:
            damage += BLADES_BONUS * (self._has(entity.player, Upgrade.BLADES_1) + self._has(entity.player, Upgrade.BLADES_2))
        if (isinstance(entity, Building) or entity.info.ranged) and entity.type is not UnitType.CATAPULT:
            damage += ARROWS_BONUS * (self._has(entity.player, Upgrade.ARROWS_1) + self._has(entity.player, Upgrade.ARROWS_2))
        if isinstance(entity, Unit) and entity.type is UnitType.CATAPULT and self._has(entity.player, Upgrade.SIEGE):
            damage = int(round(damage * SIEGE_DAMAGE_BONUS))
        if isinstance(entity, Unit) and self.frenzied(entity):
            damage = int(round(damage * (BLOODLUST_BONUS if self._has(entity.player, Upgrade.BLOODLUST) else FRENZY_BONUS)))
        return damage

    def frenzied(self, unit: Unit) -> bool:
        """An orc soldier below half health fights in a frenzy."""
        return unit.race is Race.ORC and not unit.is_worker and unit.info.soldier and unit.hp * 2 < unit.max_hp

    def armor_class_of(self, entity: Entity) -> ArmorClass:
        return ArmorClass.FORTIFIED if isinstance(entity, Building) else entity.info.armor_class

    def armor_of(self, entity: Entity) -> int:
        """A building still going up wears no armour: a frame is scaffolding, so peasants can pull it down."""
        if isinstance(entity, Building) and not entity.done:
            return 0
        armor = entity.info.armor
        if isinstance(entity, Unit) and not entity.is_worker:
            armor += ARMOR_BONUS * (self._has(entity.player, Upgrade.ARMOR_1) + self._has(entity.player, Upgrade.ARMOR_2))
        return armor

    def range_of(self, unit: Unit) -> float:
        reach = unit.info.range
        if unit.type is UnitType.CATAPULT and self._has(unit.player, Upgrade.SIEGE):
            reach += SIEGE_RANGE_BONUS
        if unit.type is UnitType.ARCHER and self._has(unit.player, Upgrade.LONGBOWS):
            reach += LONGBOWS_BONUS
        return reach

    def building_range(self, building: Building) -> float:
        reach = building.info.range
        if reach and self._has(building.player, Upgrade.LONGBOWS):
            reach += LONGBOWS_BONUS
        return reach

    def splash_of(self, unit: Unit) -> float:
        radius = unit.info.splash
        if radius and self._has(unit.player, Upgrade.BLASTING_POWDER):
            radius *= BLASTING_POWDER_BONUS
        return radius

    def gold_per_trip(self, player: int) -> int:
        return DEEP_MINING_TRIP if self._has(player, Upgrade.DEEP_MINING) else GOLD_PER_TRIP

    def speed_of(self, unit: Unit) -> float:
        info = unit.info
        speed = info.speed
        if info.mounted and self._has(unit.player, Upgrade.HORSES):
            speed += HORSES_BONUS
        return speed

    def heal_amount(self, unit: Unit) -> int:
        """Hit points one of *unit*'s casts restores."""
        amount = unit.info.heal
        if amount and self._has(unit.player, Upgrade.BLESSING):
            amount = int(round(amount * BLESSING_BONUS))
        return amount

    def heal_rate(self, unit: Unit) -> float:
        """Hit points per second *unit* restores while it has a patient: one cast each wind-up and cooldown."""
        return self.heal_amount(unit) / unit.info.period if unit.info.heal else 0.0

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
        info = self.unit_info(building.player, unit_type)
        if building.player is None or not building.done:
            return "Still under construction"
        if info.trained_at is not building.type:
            return f"{info.name}s are trained at the {self.building_info(building.player, info.trained_at).name}"
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
        if not RACES[player.race].upgrade_allowed(upgrade):
            return f"{info.name} is a {RACES[info.race].adjective} art"  # type: ignore[index]
        if upgrade in player.upgrades:
            return "Already researched"
        if any(b.research is upgrade and b.player == building.player and not b.abandoned for b in self.buildings.values()):
            return "Already being researched"
        if info.requires is not None and info.requires not in player.upgrades:
            return f"Requires {UPGRADES[info.requires].name}"
        if building.research is not None:
            return f"Researching {UPGRADES[building.research].name}"
        if building.queue:
            return "Training in progress"
        return self.can_afford(building.player, info.cost)

    @recorded
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

    @recorded
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
        if info.requires is not None and not any(b.player == player and b.type is info.requires and b.done
                                                 for b in self.buildings.values()):
            return f"Requires a {self.building_info(player, info.requires).name}"
        return self._placement_reason(building_type, pos, player, builder=builder)

    def placement_blockers(self, building_type: BuildingType, player: int
                           ) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]] | None:
        """What :meth:`placeable` holds a spot against besides its ground: the units standing on the map as
        ``(x, y, radius)`` and the gold mines' rectangles; None when *building_type*'s prerequisite is missing,
        so that no spot will do."""
        info = BUILDINGS[building_type]
        if info.requires is not None and not any(b.player == player and b.type is info.requires and b.done
                                                 for b in self.buildings.values()):
            return None
        standing = [(unit.x, unit.y, unit.radius) for unit in self.units.values() if not unit.hidden]
        mines = [building.rect for building in self.buildings.values() if building.type is BuildingType.GOLD_MINE]
        return standing, mines

    def placeable(self, building_type: BuildingType, player: int, positions: Iterable[Pos]) -> Iterator[Pos]:
        """Those of *positions*, in their order, where :meth:`can_place` would let *player* put *building_type*
        with no builder.  Everything that does not depend on the position is looked at once, for a search
        that tries hundreds of spots; ``tests/warband/test_placement.py`` holds the two to the same answers."""
        blockers = self.placement_blockers(building_type, player)
        if blockers is None:
            return
        # No name here stands for two types: mypyc keeps all of a generator's variables in one environment.
        standing, mines = blockers
        size = BUILDINGS[building_type].size
        width, height = self.width, self.height
        terrain, blocked, explored = self.terrain, self._blocked, self.explored[player]
        grass = Terrain.GRASS
        for pos in positions:
            left, top = pos
            if left < 0 or top < 0 or left + size > width or top + size > height:
                continue
            ground = True
            for y in range(top, top + size):
                row, base = terrain[y], y * width
                for x in range(left, left + size):
                    if row[x] is not grass or blocked[base + x] or not explored[base + x]:
                        ground = False
                        break
                if not ground:
                    break
            if not ground:
                continue
            right, bottom = left + size, top + size
            if any(left - r < ux < right + r and top - r < uy < bottom + r for ux, uy, r in standing):
                continue
            rect = (left, top, size, size)
            if any(rects_gap(rect, mine) < MINE_CLEARANCE for mine in mines):
                continue
            yield pos

    def _placement_reason(self, building_type: BuildingType, pos: Pos, player: int, *,
                          builder: int | None = None, ignore_units: bool = False) -> str | None:
        size = BUILDINGS[building_type].size
        left, top = pos
        width, height = self.width, self.height
        terrain, blocked, explored = self.terrain, self._blocked, self.explored[player]
        for y in range(top, top + size):
            for x in range(left, left + size):
                if not (0 <= x < width and 0 <= y < height):
                    return "Off the map"
                if terrain[y][x] is not Terrain.GRASS:
                    return "Needs open ground"
                index = y * width + x
                if blocked[index]:
                    return "Something is in the way"
                if not explored[index]:
                    return "Unexplored"
        if not ignore_units:
            for unit in self.units.values():
                if unit.id == builder or unit.hidden:
                    continue
                if left - unit.radius < unit.x < left + size + unit.radius and top - unit.radius < unit.y < top + size + unit.radius:
                    return "A unit is in the way"
        rect = (left, top, size, size)
        for mine in self.buildings.values():
            if mine.type is BuildingType.GOLD_MINE and rects_gap(rect, mine.rect) < MINE_CLEARANCE:
                return "Too close to the gold mine"
        return None

    def can_plan_building(self, building_type: BuildingType, pos: Pos, player: int) -> str | None:
        """Check a blueprint's ground; resources, prerequisites and workers may arrive later."""
        return self.settlement.can_plan_building(building_type, pos, player)

    @recorded
    def plan_building(self, player: int, building_type: BuildingType, pos: Pos) -> int:
        """Schedule construction without selecting a worker; pay when construction starts."""
        return self.settlement.plan_building(player, building_type, pos)

    def player_plans(self, player: int) -> list[Plan]:
        """Pending settlement requests and active construction, in request order."""
        return self.settlement.player_plans(player)

    @recorded
    def order_unit(self, player: int, unit_type: UnitType) -> int:
        """Request a recruit; an available compatible producer is chosen automatically."""
        return self.settlement.order_unit(player, unit_type)

    @recorded
    def order_upgrade(self, player: int, upgrade: Upgrade) -> int:
        """Request research; prerequisites, resources and a free researcher may arrive later."""
        return self.settlement.order_upgrade(player, upgrade)

    @recorded
    def cancel_plan(self, player: int, plan_id: int) -> None:
        """Cancel pending work or refund an unfinished planned building at the normal rate."""
        self.settlement.cancel_plan(player, plan_id)

    @recorded
    def set_assembly(self, player: int, point: Point | None) -> None:
        """Set the fallback destination for new combat recruits across the settlement."""
        self.players[player].assembly = self._clamp(point) if point is not None else None

    # -- Commands ------------------------------------------------------------------

    def _own_units(self, unit_ids: list[int], player: int | None = None, *, queue: bool = False) -> list[Unit]:
        """The living units among *unit_ids*; with *queue*, only if each has room for one more order behind its own."""
        units = []
        for uid in unit_ids:
            unit = self.units.get(uid)
            if unit is None:
                continue
            if player is not None and unit.player != player:
                raise RuleError("Not your unit")
            if queue and len(unit.orders) >= MAX_QUEUED_ORDERS:
                raise RuleError(f"Too many queued orders (a unit takes {MAX_QUEUED_ORDERS})")
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
            unit.windup = 0.0  # a blow being drawn back is broken off
        unit.orders.append(order)
        unit.home = None
        unit.ease = None
        unit.state = "idle"

    @recorded
    def move(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        target = self._clamp(target)
        units = self._own_units(unit_ids, queue=queue)
        pace = min((self.speed_of(u) for u in units), default=None) if len(units) > 1 and not queue else None
        for unit in units:
            self._issue(unit, Move(target, pace=pace), queue=queue)

    @recorded
    def attack_move(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        target = self._clamp(target)
        units = self._own_units(unit_ids, queue=queue)
        pace = min((self.speed_of(u) for u in units), default=None) if len(units) > 1 and not queue else None
        for unit in units:
            self._issue(unit, AttackMove(target, pace=pace) if not unit.is_worker else Move(target, pace=pace), queue=queue)

    @recorded
    def patrol(self, unit_ids: list[int], target: Point, *, queue: bool = False) -> None:
        """Patrol between where each unit stands and *target*."""
        target = self._clamp(target)
        for unit in self._own_units(unit_ids, queue=queue):
            if unit.is_worker:
                self._issue(unit, Move(target), queue=queue)
            else:
                self._issue(unit, Patrol(unit.pos, target), queue=queue)

    @recorded
    def attack(self, unit_ids: list[int], target_id: int, *, queue: bool = False) -> None:
        target = self.entity(target_id)
        if target is None:
            raise RuleError("No such target")
        if isinstance(target, Building) and target.type is BuildingType.GOLD_MINE:
            raise RuleError("A gold mine cannot be attacked")
        units = self._own_units(unit_ids, queue=queue)
        if any(target.player == unit.player for unit in units):
            raise RuleError("Cannot attack your own")
        for unit in units:
            if unit.info.damage == 0:
                self._issue(unit, Move(self._target_point(target)), queue=queue)  # a healer follows the fight instead
            else:
                self._issue(unit, Attack(target_id), queue=queue)

    @recorded
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

    @recorded
    def hold(self, unit_ids: list[int]) -> None:
        for unit in self._own_units(unit_ids):
            self._issue(unit, Hold())

    @recorded
    def release_workers(self, unit_ids: list[int]) -> None:
        """Take peasants off the job they are on and leave the automatic policy to place them again.

        Unlike :meth:`stop` this keeps ``auto_work``: the point is to be given
        new work, not to be left standing. A caller that knows a peasant should
        be somewhere else but not exactly where — the brain pulling hands off
        the trees once the wood is piled up — says so this way rather than
        naming a destination it may be remembering wrongly.
        """
        units = self._own_units(unit_ids)
        if not all(unit.is_worker for unit in units):
            raise RuleError("Only peasants gather")  # before any is let go: a refused order leaves no trace
        for unit in units:
            unit.orders.clear()
            unit.path = []
            unit.path_goal = None
            unit.state = "idle"

    @recorded
    def harvest(self, unit_ids: list[int], target: int | Pos, *, queue: bool = False) -> None:
        if isinstance(target, int):
            mine = self.buildings.get(target)
            if mine is None or mine.type is not BuildingType.GOLD_MINE:
                raise RuleError("Not a gold mine")
        elif not self.in_bounds(target) or self.terrain_at(target) is not Terrain.TREES:
            raise RuleError("No trees there")
        units = self._own_units(unit_ids, queue=queue)
        if not all(unit.is_worker for unit in units):
            raise RuleError("Only peasants can harvest")
        for unit in units:
            self._issue(unit, Harvest(target), queue=queue)

    @recorded
    def build(self, unit_id: int, building_type: BuildingType, pos: Pos, *, queue: bool = False, plan_if_short: bool = False) -> None:
        """Send a peasant to put up *building_type* at *pos*; it pays when it gets there.

        With *plan_if_short* it sets out whatever the purse holds, and a site it cannot pay for on arrival is left
        to the settlement as a plan, built by a free worker once the money is there, rather than refused: what a
        player places is built (a row of farms placed with Shift, say)."""
        unit = self.units.get(unit_id)
        if unit is None or not unit.is_worker:
            raise RuleError("Only peasants can build")
        self._own_units([unit_id], queue=queue)
        info = BUILDINGS[building_type]
        if building_type is BuildingType.GOLD_MINE:
            raise RuleError("Gold mines cannot be built")
        reason = (None if plan_if_short else self.can_afford(unit.player, info.cost)) or self.can_place(building_type, pos, unit.player, builder=unit.id)
        if reason is not None:
            raise RuleError(reason)
        self._issue(unit, Build(building_type, pos, plan_if_short=plan_if_short), queue=queue)

    @recorded
    def repair(self, unit_ids: list[int], building_id: int, *, queue: bool = False) -> None:
        """Peasants among *unit_ids* mend one of their own finished, damaged buildings."""
        workers = [u for u in self._own_units(unit_ids, queue=queue) if u.is_worker]
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

    @recorded
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

    @recorded
    def cancel_train(self, building_id: int, index: int = -1) -> None:
        building = self.buildings.get(building_id)
        if building is None or not building.queue:
            raise RuleError("Nothing to cancel")
        if not -len(building.queue) <= index < len(building.queue):
            raise RuleError("No such place in the training queue")
        assert building.player is not None
        unit_type = building.queue.pop(index)
        self._refund(building.player, UNITS[unit_type].cost)
        if index in (0, -len(building.queue) - 1) or not building.queue:
            building.train_progress = 0.0

    @recorded
    def set_rally(self, building_id: int, point: Point | None) -> None:
        building = self.buildings.get(building_id)
        if building is None or building.player is None:
            raise RuleError("No such building")
        building.rally = self._clamp(point) if point is not None else None

    @recorded
    def set_auto_train(self, building_id: int, unit_type: UnitType, on: bool) -> None:
        """Have a building train *unit_type* endlessly (*on*), or stop; several types at one building take turns.

        A standing order, which a site still going up keeps until it stands.  It starts a recruit whenever the
        building stands idle and its owner can pay from what their unpaid orders have not claimed
        (:meth:`committed`), so what a player asked for comes before what they left running."""
        building = self.buildings.get(building_id)
        if building is None or building.player is None or building.abandoned:
            raise RuleError("No such building")
        if unit_type not in building.info.trains:
            info = self.unit_info(building.player, unit_type)
            raise RuleError(f"{info.name}s are trained at the {self.building_info(building.player, info.trained_at).name}")
        if on and unit_type not in building.auto:
            building.auto.append(unit_type)
        elif not on and unit_type in building.auto:
            building.auto.remove(unit_type)

    def committed(self, player: int) -> Cost:
        """What *player*'s unpaid orders will cost: the sites builders are on their way to, and the plans whose
        prerequisites stand (one that cannot start yet claims nothing).  Endless training spends only the rest."""
        gold = lumber = 0
        walking: set[tuple[BuildingType, Pos]] = set()
        for unit in self.player_units(player):
            for order in unit.orders:
                if isinstance(order, Build) and order.building is None:
                    cost = BUILDINGS[order.type].cost
                    gold, lumber = gold + cost.gold, lumber + cost.lumber
                    walking.add((order.type, order.pos))
        standing = {b.type for b in self.player_buildings(player, done=True)}
        researched = self.players[player].upgrades
        for plan in self.settlement.player_plans(player):
            if plan.kind == "building":
                assert isinstance(plan.type, BuildingType)
                info = BUILDINGS[plan.type]
                if plan.building is not None or (plan.type, plan.pos) in walking or (info.requires is not None and info.requires not in standing):
                    continue
                cost = info.cost
            elif plan.kind == "unit":
                assert isinstance(plan.type, UnitType)
                if UNITS[plan.type].trained_at not in standing:
                    continue
                cost = UNITS[plan.type].cost
            else:
                assert isinstance(plan.type, Upgrade)
                upgrade = UPGRADES[plan.type]
                if (not any(plan.type in BUILDINGS[kind].researches for kind in standing)
                        or (upgrade.requires is not None and upgrade.requires not in researched)):
                    continue
                cost = upgrade.cost
            gold, lumber = gold + cost.gold, lumber + cost.lumber
        return Cost(gold, lumber)

    def auto_train_blocker(self, building: Building) -> str | None:
        """Why *building* cannot start its next endless recruit now (None when it can): the reasons :meth:`can_train`
        gives, gold and lumber the player's unpaid orders claim, or research planned here, which goes first."""
        if not building.auto:
            return "Nothing to train endlessly"
        assert building.player is not None
        unit_type = building.auto[0]
        reason = self.can_train(building, unit_type)
        if reason is not None:
            return reason
        for plan in self.settlement.player_plans(building.player):
            if plan.kind == "upgrade" and isinstance(plan.type, Upgrade) and plan.type in building.info.researches \
                    and self.can_research(building, plan.type) in (None, "Training in progress"):
                return f"Research first: {UPGRADES[plan.type].name}"
        cost, held = self.unit_info(building.player, unit_type).cost, self.committed(building.player)
        player = self.players[building.player]
        # Per resource: a plan short of lumber claims no gold beyond its price, so a recruit paid in gold alone may go.
        if max(0, player.gold - held.gold) < cost.gold or max(0, player.lumber - held.lumber) < cost.lumber:
            return "Your plans are paid first"
        return None

    @recorded
    def smart(self, unit_ids: list[int], point: Point, *, queue: bool = False,
              target_id: int | None | Literal["at_point"] = "at_point") -> str:
        """Resolve a context order; return the verb used.

        A displayed target can be supplied by ID, or None for empty ground.
        Omission picks at the model point, preserving AI and recorded orders.
        """
        units = self._own_units(unit_ids, queue=queue)  # room for every unit now, whichever order each ends up with
        if not units:
            return "none"
        player = units[0].player
        if target_id == "at_point":
            target = self.entity_at(point, visible_to=player)
        else:
            target = self.entity(target_id) if target_id is not None else None
        if target_id not in ("at_point", None) and target is None:
            raise RuleError("No such target")
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
        race = self.race_of(player)
        unit = Unit(self._new_id(), unit_type, player, point[0], point[1], RACES[race].units[unit_type].hp, race=race)
        self.units[unit.id] = unit
        self._bucket(unit)
        self.players[player].alive = True  # a side cleared by a mission comes back with its first unit
        return unit

    def place_building(self, player: int | None, building_type: BuildingType, pos: Pos, *, done: bool = True) -> Building:
        race = self.race_of(player)
        info = RACES[race].buildings[building_type]
        building = Building(self._new_id(), building_type, player, pos[0], pos[1], info.hp if done else shell_hp(info, 0.0), race=race)
        if done:
            building.progress = info.build_time
        if building_type is BuildingType.GOLD_MINE:
            building.gold = MINE_GOLD
        self.buildings[building.id] = building
        self._building_epoch += 1
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
        self._order_depth += 1
        try:
            self._step()
        finally:
            self._order_depth -= 1

    def _step(self) -> None:
        dt = SIM_DT
        self.time += dt
        self.tick += 1
        self._pace_groups.clear()
        self._dangers.clear()
        self._index_units()
        self.settlement.update()
        for building in list(self.buildings.values()):
            self._update_building(building, dt)
        for unit in list(self.units.values()):
            if unit.id in self.units:
                self._update_unit(unit, dt)
        self._land_projectiles()
        self._separate()
        self._bury_the_dead()
        if self.regrowth and self.tick % round(1 / SIM_DT) == 0:
            self._regrow()
        if self.tick % VISION_EVERY == 0:
            self.update_vision()
        self._check_elimination()

    def _regrow(self) -> None:
        """Trees the elves felled grow back once their time is up, unless something stands there."""
        pending = []
        for tile, when in self.regrowth:
            x, y = tile
            if self.time < when:
                pending.append((tile, when))
                continue
            if self.terrain[y][x] is not Terrain.GRASS or self._blocked[y * self.width + x] or any(
                    not u.hidden and u.tile == tile for u in self.units_near(tile_center(tile), 1.0)):
                pending.append((tile, self.time + 5.0))  # try again shortly
                continue
            self.terrain[y][x] = Terrain.TREES
            self._blocked[y * self.width + x] = 1
            for unit in self.units.values():
                if tile in unit.path:
                    unit.path = []
                    unit.path_goal = None  # the order plans again on its next step
            self.events.append(Event("tree_grown", tile_center(tile)))
        self.regrowth = pending

    def take_events(self) -> list[Event]:
        events, self.events = self.events, []
        return events

    # -- Buildings -------------------------------------------------------------------

    def _update_building(self, b: Building, dt: float) -> None:
        if b.type is BuildingType.GOLD_MINE or b.player is None or b.abandoned:  # a ruin nobody owns builds, trains and shoots nothing
            return
        info = b.info
        if not b.done:
            builder = self.units.get(b.builder) if b.builder is not None else None
            if builder is not None and builder.constructing == b.id:
                b.hp += shell_hp(info, b.progress + dt) - shell_hp(info, b.progress)
                b.progress = min(info.build_time, b.progress + dt)
                if b.done:
                    self._finish_construction(b, builder)
            return
        delivered = False
        if b.queue:
            unit_type = b.queue[0]
            b.train_progress += dt
            if b.train_progress >= self.unit_info(b.player, unit_type).build_time:
                b.queue.pop(0)
                b.train_progress = 0.0
                self._deliver_unit(b, unit_type)
                delivered = True
        elif b.research is not None:
            b.research_progress += dt
            if b.research_progress >= UPGRADES[b.research].time:
                upgrade, b.research, b.research_progress = b.research, None, 0.0
                self.players[b.player].upgrades.add(upgrade)
                self.events.append(Event("researched", b.center, player=b.player, entity=b.id, text=UPGRADES[upgrade].name))
        # Endless training looks when a recruit walks out, and otherwise once a second after the plans have had theirs.
        if b.auto and not b.queue and b.research is None and (delivered or self.tick % AUTO_EVERY == 0):
            self._auto_train(b)
        if info.damage:
            self._tower_shoot(b, dt)

    def _auto_train(self, b: Building) -> None:
        """Start the next of *b*'s endless recruits, when nothing stands in its way; the next type then waits its turn."""
        if self.auto_train_blocker(b) is not None:
            return
        assert b.player is not None
        unit_type = b.auto.pop(0)
        b.auto.append(unit_type)
        self._pay(b.player, self.unit_info(b.player, unit_type).cost)
        b.queue.append(unit_type)

    def _finish_construction(self, b: Building, builder: Unit) -> None:
        builder.constructing = None
        if builder.orders and isinstance(builder.orders[0], Build):
            builder.orders.popleft()
        spot = self.free_tile_near(b.rect)
        if spot is not None:
            builder.x, builder.y = tile_center(spot)
        b.builder = None
        assert b.player is not None
        self.events.append(Event("built", b.center, player=b.player, entity=b.id, text=f"{b.info.name} complete",
                                 target_type=b.type.value))

    def _deliver_unit(self, b: Building, unit_type: UnitType) -> None:
        assert b.player is not None
        assembly = self.players[b.player].assembly if unit_type is not UnitType.PEASANT else None
        spot = self.free_tile_near(b.rect, prefer=b.rally if b.rally is not None else assembly)
        if spot is None:
            spot = (b.x, b.y + b.size)
        unit = self.spawn_unit(b.player, unit_type, tile_center(spot))
        self.events.append(Event("trained", unit.pos, player=b.player, entity=unit.id, other=b.id, text=f"{unit.info.name} ready",
                                     target_type=unit.type.value))
        if b.rally is not None:
            self.smart([unit.id], b.rally)
        elif assembly is not None:
            self.move([unit.id], assembly)

    def _tower_shoot(self, b: Building, dt: float) -> None:
        b.cooldown = max(0.0, b.cooldown - dt)
        if b.cooldown > 0:
            return
        info = b.info
        target = self._nearest_enemy(b.player, b.center, self.building_range(b) + b.size / 2, units_only=True)  # type: ignore[arg-type]
        if target is None:
            return
        self._launch_arrow(b, target, self.damage_of(b))
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

    @recorded
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

    @recorded
    def resume_construction(self, unit_ids: list[int], building_id: int) -> None:
        b = self.buildings.get(building_id)
        if b is None or b.done:
            raise RuleError("Nothing to resume")
        units = self._own_units(unit_ids)
        if not all(unit.is_worker for unit in units):
            raise RuleError("Only peasants can build")
        for unit in units:
            self._issue(unit, Build(b.type, b.pos, building=b.id))

    # -- Units ----------------------------------------------------------------------

    def _update_unit(self, u: Unit, dt: float) -> None:
        cooldown = u.cooldown - dt
        u.cooldown = cooldown if cooldown > 0.0 else 0.0
        x, y = u.x, u.y
        self._act(u, dt)
        u.vx, u.vy = (u.x - x) / dt, (u.y - y) / dt  # its own walking, before the crowd shoves it

    def _act(self, u: Unit, dt: float) -> None:
        if u.inside is not None:
            self._mine_inside(u, dt)
            return
        if u.constructing is not None:
            u.state = "build"
            return
        order = u.order
        if order is None:
            self._idle(u, dt)
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
            self._do_hold(u, order, dt)
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
        u.windup = 0.0
        u.last_distance = math.inf
        u.progress = 0.0

    def _idle(self, u: Unit, dt: float) -> None:
        u.state = "idle"
        if u.is_worker:
            second = self.tick % round(1 / SIM_DT) == 0
            if u.auto_work and second:
                worker_ai.assign_idle_workers(self, u.player)
            if not u.orders and u.auto_work and (second or u.path_goal is not None):
                if self._take_cover(u, dt, worker_ai.safe_navigation(self, u.player)):
                    return
                u.path, u.path_goal, u.exact = [], None, None
        elif self.tick % 5 == 0:
            patient = self._healing_patient(u, u.info.sight) if u.info.heal else None
            if patient is not None:
                u.home = u.pos
                u.orders.appendleft(Heal(patient.id, auto=True))
            else:
                target = self._auto_target(u)
                if target is not None:
                    u.home = u.pos
                    u.orders.appendleft(Attack(target.id, auto=True))
        if not u.orders:
            self._ease(u, dt)

    def _auto_target(self, u: Unit) -> Entity | None:
        """The enemy a fighter that is left to itself takes on: a siege crew the best clear stone in reach or a
        short roll forward, anyone else the first to fight in sight."""
        if u.info.splash:
            return self._siege_choice(u, SIEGE_STEP)
        return self._nearest_enemy(u.player, u.pos, u.info.sight, min_radius=u.info.min_range)

    def _ease(self, u: Unit, dt: float) -> None:
        """Standing at ease: a unit hemmed in by its neighbours takes a short step away from them now
        and then, so a crowd that arrived as a clump loosens to arm's length.  No order is involved:
        the unit stays idle to the AI, to Tab and to the player."""
        if u.ease is None:
            if self.tick % EASE_EVERY or self.rng.random() >= EASE_CHANCE:
                return
            u.ease = self._elbow_room(u)
            if u.ease is None:
                return
            u.last_distance = math.inf
        left = dist(u.pos, u.ease)
        if left > ARRIVE and left < u.last_distance - 1e-3 and self._steer(u, u.ease, dt):
            u.last_distance = left  # still walking: the step gains ground and the line is clear
            return
        u.ease = None
        u.last_distance = math.inf
        u.state = "idle"

    def _elbow_room(self, u: Unit) -> Point | None:
        """A spot a short step away from the neighbours crowding *u*, or None when it has room already,
        is boxed in, or the step would end nearer to someone else than where it stands."""
        ax = ay = 0.0
        for v in self.units_near(u.pos, EASE_SPACE):
            if v is u or v.hidden:
                continue
            dx, dy = u.x - v.x, u.y - v.y
            d = hypot(dx, dy)
            if d < 1e-6:
                angle = (u.id * 2.399) % (2 * math.pi)
                dx, dy, d = math.cos(angle), math.sin(angle), 1.0
            weight = (EASE_SPACE - d) / d  # the closer, the more it counts
            ax += dx * weight
            ay += dy * weight
        if not (ax or ay):
            return None
        angle = _atan2(ay, ax) + self.rng.uniform(-EASE_JITTER, EASE_JITTER)
        step = EASE_STEP + self.rng.uniform(-EASE_STEP_VARIANCE, EASE_STEP_VARIANCE)
        spot = self._clamp((u.x + math.cos(angle) * step, u.y + math.sin(angle) * step))
        if not self.passable(int(spot[0]), int(spot[1])) or not self._line_clear(u.pos, spot):
            return None
        return spot if self._room(u, spot) >= self._room(u, u.pos) + EASE_GAIN else None

    def _room(self, u: Unit, point: Point) -> float:
        """How far *point* is from the nearest unit other than *u*, as far as EASE_SPACE plus the
        gain a step must make matters: anything beyond is all the room a standing unit asks for."""
        return min((dist(point, v.pos) for v in self.units_near(point, EASE_SPACE + EASE_GAIN) if v is not u and not v.hidden),
                   default=math.inf)

    def _danger_to(self, patient: Unit) -> float:
        """Hits per second the visible enemies in reach of *patient* could land on it.  Memoised for the
        step: every healer weighing the same patients would otherwise sum it again."""
        danger = self._dangers.get(patient.id)
        if danger is None:
            danger = 0.0
            player = patient.player
            for enemy in self.units_near(patient.pos, 9):
                if enemy.player == player or enemy.hidden or enemy.hp <= 0 or not self.is_visible(player, enemy.tile):
                    continue
                if enemy.info.damage and self._gap(enemy, patient) <= self.range_of(enemy) + .75:
                    danger += max(1, self.damage_of(enemy) - self.armor_of(patient)) / enemy.info.period
            for tower in self.buildings.values():
                if tower.player in (None, player) or not tower.done or not tower.info.damage:
                    continue
                if any(self.is_visible(player, tile) for tile in tower.tiles()) and self._gap(tower, patient) <= self.building_range(tower) + .75:
                    danger += max(1, self.damage_of(tower) - self.armor_of(patient)) / tower.info.cooldown
            self._dangers[patient.id] = danger
        return danger

    def _healing_priority(self, healer: Unit, patient: Unit) -> float:
        """Weigh missing health and visible pressure against travel before treatment."""
        danger = self._danger_to(patient)
        value = self.damage_of(patient) / patient.info.period + self.heal_rate(patient) + 1
        missing_fraction = (patient.max_hp - patient.hp) / patient.max_hp
        urgency = 1 + min(3, 4 * danger / patient.hp)
        travel = max(0, self._gap(healer, patient) - self.range_of(healer)) / self.speed_of(healer)
        return value * (.25 + missing_fraction) * urgency / (1 + travel)

    def _healing_patient(self, healer: Unit, radius: float, *, local: bool = False) -> Unit | None:
        """The wounded ally most worth treating: under fire first, then the most hurt, then the nearest."""
        patients = [unit for unit in self.units_near(healer.pos, radius + UNIT_RADIUS)
                    if unit is not healer and unit.player == healer.player and not unit.hidden
                    and 0 < unit.hp < unit.max_hp
                    and (not local or self._gap(healer, unit) <= self.range_of(healer) + .05)]
        return max(patients, key=lambda unit: (self._healing_priority(healer, unit), -dist(healer.pos, unit.pos), -unit.id), default=None)

    def _do_heal(self, u: Unit, order: Heal, dt: float) -> None:
        patient = self.units.get(order.target)
        if patient is None or patient.hp <= 0 or patient.hp >= patient.max_hp or patient.hidden:
            self._finish_order(u)
            if order.auto and u.home is not None and not u.orders and dist(u.pos, u.home) > 1.0:
                u.orders.append(Move(u.home))
            return
        if order.auto and u.windup <= 0.0 and self.tick % 5 == 0:  # a cast once begun goes to its patient
            nearby = self._healing_patient(u, u.info.sight, local=True)
            if nearby is not None and nearby is not patient and self._healing_priority(u, nearby) > self._healing_priority(u, patient) * 1.25:
                order.target, patient = nearby.id, nearby
        if order.auto and u.home is not None and dist(u.pos, u.home) > LEASH:
            self._finish_order(u)
            u.orders.appendleft(Move(u.home))
            return
        if u.windup > 0.0 or self._gap(u, patient) <= self.range_of(u) + 0.05:
            self._cast(u, patient, dt)
            return
        if self._steer(u, patient.pos, dt):
            return
        goal = patient.tile
        if u.path_goal is None or (dist(tile_center(u.path_goal), tile_center(goal)) > 1.5 and self.time >= u.replan_at):
            self._plan(u, goal, patient.pos)
        if self._follow(u, dt) and u.path_goal != goal and self.time >= u.replan_at:
            self._plan(u, goal, patient.pos)

    def _cast(self, u: Unit, patient: Unit, dt: float) -> None:
        """A healer in reach faces its patient, winds up, and restores :meth:`heal_amount` at once; then its
        cooldown.  A patient that walked off beyond reach and :data:`WINDUP_SLACK` meanwhile is not reached."""
        u.path = []
        u.path_goal = None
        faced = self._turn_toward(u, patient.pos, dt)
        u.state = "attack"
        if u.windup > 0.0:
            u.windup -= dt
            if u.windup > 1e-9:
                return
            u.windup = 0.0
            u.cooldown = u.info.cooldown
            if self._gap(u, patient) > self.range_of(u) + WINDUP_SLACK:
                return
            amount = min(self.heal_amount(u), patient.max_hp - patient.hp)
            patient.hp += amount
            self.events.append(Event("heal", patient.pos, player=u.player, entity=u.id, other=patient.id, amount=amount))
            return
        if faced and u.cooldown <= 0.0:
            u.windup = u.info.windup

    def _do_hold(self, u: Unit, order: Hold, dt: float) -> None:
        u.state = "idle"
        u.path = []
        if u.is_worker or u.info.damage == 0:
            return
        target = self.entity(order.target) if order.target is not None else None
        if target is not None and (target.hp <= 0 or (u.windup <= 0.0 and not self._in_range(u, target))):
            target = order.target = None
        if target is None:
            if self.tick % 5:
                return
            target = (self._siege_choice(u, 0.0) if u.info.splash
                      else self._nearest_enemy(u.player, u.pos, self.range_of(u) + 1.0, min_radius=u.info.min_range))
            if target is None or not self._in_range(u, target):
                return
            order.target = target.id
        self._fight(u, target, dt, auto=True)

    def _do_move(self, u: Unit, order: Move, dt: float) -> None:
        if self._walk_to(u, order.target, dt, settle=True):
            self._finish_order(u)

    def _engage(self, u: Unit) -> bool:
        """Pick up a fight (or a patient) in sight while on the move; True if one was found."""
        if self.tick % 5:
            return False
        patient = self._healing_patient(u, u.info.sight) if u.info.heal else None
        if patient is not None:
            u.orders.appendleft(Heal(patient.id, auto=True))
        else:
            target = self._auto_target(u)
            if target is None:
                return False
            u.orders.appendleft(Attack(target.id, auto=True))
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
        if (target is None or target.hp <= 0 or (isinstance(target, Unit) and target.hidden)
                or (isinstance(target, Building) and target.type is BuildingType.GOLD_MINE)):
            self._finish_order(u)
            if order.auto and u.home is not None and not u.orders:
                u.orders.append(Move(u.home))
            return
        if u.windup > 0.0:
            self._fight(u, target, dt, auto=order.auto, chase=True)  # committed: the blow is drawn back, whatever else moves
            return
        if order.auto and u.home is not None and dist(u.pos, u.home) > LEASH:
            self._finish_order(u)
            u.orders.appendleft(Move(u.home))
            return
        if order.auto and u.info.heal and self.tick % 5 == 0:
            patient = self._healing_patient(u, u.info.sight)
            if patient is not None:  # a healer strikes only while no one needs it
                home = u.home
                self._finish_order(u)
                u.home = home
                u.orders.appendleft(Heal(patient.id, auto=True))
                return
        if order.auto and u.info.splash and self.tick % 5 == 0:
            if (u.info.min_range and self._gap(u, target) < u.info.min_range) or not self._in_range(u, target) \
                    or self._aim_point(u, target, auto=True) is None:
                better = self._siege_choice(u, SIEGE_STEP)  # no clear stone at this one: look for one that is
                if better is not None and better is not target:
                    target = better
                    self._retarget(u, order, better)
        elif order.auto and self.tick % 5 == 0:
            threat = self._threat(target)
            if threat > 0:
                # A bystander or a building holds a unit's attention only until something more dangerous shows up.
                better = self._nearest_enemy(u.player, u.pos, u.info.sight, min_radius=u.info.min_range)
                if better is not None and self._threat(better) < threat:
                    target = better
                    self._retarget(u, order, better)
        if order.auto and u.type is UnitType.ARCHER and u.cooldown > 0 and self._ranged_retreat(u, target, dt):
            return
        if order.auto and u.cooldown <= 0 and self.range_of(u) < 1:
            # Finish a reachable wounded opponent when ready to strike, unless it matters less than the
            # target.  Keep the target during recovery, and preserve explicit focus fire.
            nearby = self._melee_opponent(u)
            if nearby is not None and self._in_range(u, nearby) and self._threat(nearby) <= self._threat(target):
                target = nearby
                order.target = target.id
        if u.info.min_range and self._gap(u, target) < u.info.min_range:
            if not self._back_off(u, target, dt):
                u.state = "idle"  # cornered: the crew can do nothing about this one until it moves
            return
        if self._in_range(u, target) and not self._siege_creeps(u, target, order.auto):
            self._fight(u, target, dt, auto=order.auto, chase=True)
            return
        aim = self._target_point(target)
        if self.range_of(u) < 1:
            aim = self._melee_position(u, target)
        elif isinstance(target, Building):
            x, y, w, h = target.rect
            aim = (min(max(u.x, x + 0.5), x + w - 0.5), min(max(u.y, y + 0.5), y + h - 0.5))  # the nearest wall
        if self._steer(u, aim, dt):
            return
        goal_tile = (int(aim[0]), int(aim[1]))
        if u.path_goal is None or (dist(tile_center(u.path_goal), tile_center(goal_tile)) > 1.5 and self.time >= u.replan_at):
            self._plan(u, goal_tile, aim)
        if self._follow(u, dt) and u.path_goal != goal_tile and self.time >= u.replan_at:
            self._plan(u, goal_tile, aim)

    def _fight(self, u: Unit, target: Entity, dt: float, *, auto: bool, chase: bool = False) -> None:
        """Face *target*, wind up and strike.  The blow at the end of the wind-up lands if the target is
        still within reach and :data:`WINDUP_SLACK`, and costs the cooldown either way.  A shooter stands
        through its wind-up; a melee unit that may *chase* swings on the run, so a target merely walking
        away is still caught."""
        u.path = []
        u.path_goal = None
        faced = self._turn_toward(u, self._target_point(target), dt)
        if u.windup > 0.0:
            if chase and u.info.melee and not self._in_range(u, target):
                self._steer(u, self._melee_position(u, target), dt)
            u.state = "attack"
            u.windup -= dt
            if u.windup > 1e-9:
                return
            u.windup = 0.0
            self._release(u, target, auto=auto)
        else:
            u.state = "attack"
            if not faced or u.cooldown > 0.0:
                return
            if u.info.splash and self._aim_point(u, target, auto=auto) is None:
                return  # no clear shot: the crew waits rather than drop a stone on its own side
            u.windup = u.info.windup  # drawn back from now; the blow lands that many seconds on
            if u.windup <= 0.0:
                self._release(u, target, auto=auto)

    def _release(self, u: Unit, target: Entity, *, auto: bool) -> None:
        """The blow at the end of a wind-up."""
        if target.hp <= 0 or (isinstance(target, Unit) and target.hidden) or self._gap(u, target) > self.range_of(u) + WINDUP_SLACK:
            u.cooldown = u.info.cooldown  # swung at air
            return
        if u.info.splash:
            aim = self._aim_point(u, target, auto=auto)
            if aim is None:
                return  # friends walked under the shot while the arm was cranked: wait for a clear one
            self._launch_stone(u, aim)
        else:
            self._strike(u, target)
        u.cooldown = u.info.cooldown

    def _back_off(self, u: Unit, target: Entity, dt: float) -> bool:
        """Step straight away from a target inside the engine's minimum range; True if there was room."""
        px, py = self._target_point(target)
        dx, dy = u.x - px, u.y - py
        d = hypot(dx, dy) or 1e-6
        return self._steer(u, self._clamp((u.x + dx / d, u.y + dy / d)), dt)

    def _ranged_retreat(self, u: Unit, target: Entity, dt: float) -> bool:
        """An automatic archer recovering its shot steps away from visible melee, keeping the target in range."""
        if not isinstance(target, Unit) or not self.is_visible(u.player, target.tile) or not self._in_range(u, target):
            return False
        threats = [enemy for enemy in self.units_near(u.pos, 4.75)
                   if enemy.player != u.player and not enemy.hidden and enemy.hp > 0
                   and self.is_visible(u.player, enemy.tile) and enemy.info.damage > 0 and self.range_of(enemy) < 1]
        if not threats:
            return False
        nearest = min(threats, key=lambda enemy: (self._gap(u, enemy), enemy.id))
        clearance = self._gap(u, nearest)
        if clearance >= 2.75:
            return False
        angle = _atan2(u.y - nearest.y, u.x - nearest.x)
        allies = [ally for ally in self.units_near(u.pos, 2) if ally is not u and ally.player == u.player and not ally.hidden]
        known = self.worker_knowledge[u.player].blocked
        best, best_score = None, clearance + .1
        for offset in (0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2):
            point = (u.x + math.cos(angle + offset) * .85, u.y + math.sin(angle + offset) * .85)
            if not self.is_visible(u.player, (int(point[0]), int(point[1]))) or not self._line_clear(u.pos, point, navigation=known):
                continue
            if u.home is not None and dist(point, u.home) > LEASH:
                continue
            if dist(point, target.pos) - u.radius - target.radius > self.range_of(u):
                continue
            gap = min(dist(point, enemy.pos) - u.radius - enemy.radius for enemy in threats)
            crowd = sum(max(0, u.radius + ally.radius + .2 - dist(point, ally.pos)) for ally in allies)
            score = gap - 1.5 * crowd
            if score > best_score:
                best, best_score = point, score
        return best is not None and self._steer(u, best, dt)

    def _melee_position(self, u: Unit, target: Entity) -> Point:
        """Aim for contact in open ground, rather than the occupied target tile."""
        if isinstance(target, Building):
            spot = self._siege_spot(u, target)
            if spot is not None:
                return spot
            x, y, w, h = target.rect
            point = (min(max(u.x, x), x + w), min(max(u.y, y), y + h))
            radius = 0.0
        else:
            point, radius = target.pos, target.radius
        dx, dy = u.x - point[0], u.y - point[1]
        distance = hypot(dx, dy) or 1e-6
        reach = radius + u.radius + self.range_of(u) * .8
        # The spot is on the attacker's side of the target, so a target at the edge of the map puts it
        # off the map — and a tile lookup truncates x=-0.04 to tile 0, so nothing on the way would notice.
        return self._clamp((point[0] + dx / distance * reach, point[1] + dy / distance * reach))

    def _siege_spot(self, u: Unit, target: Building) -> Point | None:
        """The centre of the open tile round *target* nearest *u*, one nobody else stands on first; None when the
        whole ring is closed.

        The point on the attacker's side of a building is a tree or a wall when that side is closed, and a path
        cannot end there: the attacker stopped a path's end short of it for good. Twelve peasants sent at a tower
        in a clearing stood so, ten of them idle, and it lost a point a second where they could take twelve
        (WB-037). A melee blow reaches from any tile of the ring, diagonals included."""
        x, y, w, h = target.rect
        width, height, blocked = self.width, self.height, self._blocked
        occupied = {(int(other.x), int(other.y)) for other in self.units_near(target.center, max(w, h) / 2 + 1.5)
                    if other is not u and not other.hidden}
        best: Point | None = None
        best_taken, best_d = True, math.inf
        for ty in range(max(0, y - 1), min(height, y + h + 1)):
            for tx in range(max(0, x - 1), min(width, x + w + 1)):
                if blocked[ty * width + tx] or x <= tx < x + w and y <= ty < y + h:
                    continue
                centre = (tx + 0.5, ty + 0.5)
                taken = (tx, ty) in occupied
                d = hypot(u.x - centre[0], u.y - centre[1])
                if (not taken and best_taken) or (taken == best_taken and d < best_d):
                    best, best_taken, best_d = centre, taken, d
        return best

    def _melee_opponent(self, u: Unit) -> Entity | None:
        """Finish visible opponents already in reach before pursuing another target."""
        radius = self.range_of(u) + u.radius + UNIT_RADIUS + .05
        opponents = [enemy for enemy in self.units_near(u.pos, radius)
                     if enemy.player != u.player and not enemy.hidden and enemy.hp > 0
                     and self.is_visible(u.player, enemy.tile) and self._in_range(u, enemy)]
        if opponents:
            return min(opponents, key=lambda enemy: (self._threat(enemy), enemy.hp, dist(u.pos, enemy.pos), enemy.id))
        return self._nearest_enemy(u.player, u.pos, self.range_of(u) + u.radius + .05)

    def _do_harvest(self, u: Unit, order: Harvest, dt: float) -> None:
        if u.carrying is not None:
            u.orders.appendleft(Deposit())
            u.path = []
            u.path_goal = None
            return
        remembered = self.worker_knowledge[u.player].resource_rect(order.target)
        if remembered is not None:
            if not self.any_visible(u.player, remembered):
                # Revisit the last observed site before discovering a depleted
                # mine or felled tree. Hidden changes cannot alter this route.
                if self._approach_work(u, remembered, dt, self._worker_navigation(u)):
                    self._finish_order(u)
                return
        if isinstance(order.target, int):
            mine = self.buildings.get(order.target)
            if mine is None or mine.gold <= 0:
                replacement = worker_ai.choose_replacement(self, u, Resource.GOLD)
                if replacement is None:
                    self._finish_order(u)
                    return
                order.target, order.auto = replacement, True
                u.path_goal = None
                return  # a remembered replacement may still be hidden by fog
            navigation = self._worker_navigation(u)
            if rect_gap(u.pos, mine.rect) - u.radius <= TOUCH and not navigation[u.tile[1] * self.width + u.tile[0]]:
                if self._mine_crews.get(mine.id, 0) >= MINE_SLOTS:
                    u.path = []
                    u.path_goal = None
                    u.state = "idle"  # every place at the face is taken: wait at the mouth for one to free
                    return
                self._mine_crews[mine.id] = self._mine_crews.get(mine.id, 0) + 1
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
            replacement = worker_ai.choose_replacement(self, u, Resource.LUMBER)
            if replacement is None:
                self._finish_order(u)
                return
            order.target = replacement  # a tree's replacement is a tree
            order.auto = True
            u.path = []
            u.path_goal = None
            return
        navigation = self._worker_navigation(u)
        rect = (tile[0], tile[1], 1, 1)
        if rect_gap(u.pos, rect) - u.radius <= TOUCH and not navigation[u.tile[1] * self.width + u.tile[0]]:
            u.path = []
            u.state = "chop"
            self._turn_toward(u, tile_center(tile), dt)
            u.timer += dt
            if u.timer >= CHOP_TIME:
                u.timer = 0.0
                self.terrain[tile[1]][tile[0]] = Terrain.GRASS
                self._blocked[tile[1] * self.width + tile[0]] = 0
                u.carrying, u.carry = Resource.LUMBER, LUMBER_PER_TRIP
                if self._has(u.player, Upgrade.REGROWTH):
                    self.regrowth.append((tile, self.time + REGROWTH_SECONDS))
                self.events.append(Event("tree_felled", tile_center(tile), player=u.player, entity=u.id))
                u.orders.appendleft(Deposit())
            return
        u.timer = 0.0
        if self._approach_work(u, rect, dt, navigation):
            self._finish_order(u)

    def _leave_mine(self, u: Unit) -> None:
        """Give up this peasant's place at the face, so a waiting one can take it."""
        if u.inside is None:
            return
        crew = self._mine_crews.get(u.inside, 0) - 1
        if crew > 0:
            self._mine_crews[u.inside] = crew
        else:
            self._mine_crews.pop(u.inside, None)
        u.inside = None

    def _mine_inside(self, u: Unit, dt: float) -> None:
        mine = self.buildings.get(u.inside) if u.inside is not None else None
        u.timer -= dt
        if mine is None:
            self._leave_mine(u)
            return
        if u.timer > 0:
            return
        taken = min(self.gold_per_trip(u.player), mine.gold)
        mine.gold -= taken
        u.carrying, u.carry = Resource.GOLD, taken
        self._leave_mine(u)
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
        hall = self.buildings.get(order.target) if order.target is not None else None
        if hall is None or not hall.done or u.carrying not in hall.info.deposits or u.path_goal is None:
            depots = [b for b in self.buildings.values()
                      if b.player == u.player and b.done and u.carrying in b.info.deposits]
            hall = next((b for b in depots if rect_gap(u.pos, b.rect) - u.radius <= TOUCH), None)
            if hall is None:
                if self.time < u.replan_at:
                    if not self._take_cover(u, dt, navigation):
                        u.state = "idle"
                    return
                order.target = self._plan_work_route(u, {b.id: b.rect for b in depots}, navigation)
                hall = self.buildings.get(order.target) if order.target is not None else None
        if hall is None:
            if not self._take_cover(u, dt, navigation):
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

    def _take_cover(self, u: Unit, dt: float, navigation: bytearray) -> bool:
        """Walk an automatic worker caught on ground its safe map forbids out to the nearest ground it allows, even
        when its work cannot be reached from there; True while it is on its way.

        Its trip would go through the escape when the work lay beyond; when nothing it could work or deliver to is
        safe (a tower beside the hall), standing still waiting for the danger to pass is standing in the fire:
        a tower by the hall killed every carrier holding gold beside it, one by one (WB-037)."""
        width = self.width
        tx, ty = u.tile
        if navigation is self._blocked or not navigation[ty * width + tx]:
            return False
        goal = u.path_goal
        if goal is None or navigation[goal[1] * width + goal[0]] or self._next_waypoint(u, precise=True) is None:
            escape = self._way_out(u.tile, navigation)
            if escape is None:
                return False  # no way out: nothing to do but wait for the danger to pass
            u.path, u.path_goal, u.exact = escape, escape[-1], tile_center(escape[-1])
        self._follow(u, dt, navigation=navigation, precise=True)
        return True

    def _worker_navigation(self, u: Unit) -> bytearray:
        for order in u.orders:
            if isinstance(order, (Harvest, Deposit)) and order.auto:
                return worker_ai.safe_navigation(self, u.player)
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
        start, escape = u.tile, []
        u.replan_at = self.time + REPLAN_EVERY
        u.progress, u.last_distance = 0.0, math.inf
        u.path, u.path_goal, u.exact = [], None, None
        if navigation[start[1] * self.width + start[0]]:
            found = self._way_out(start, navigation)
            if found is None:
                return None  # forbidden ground with no way out: wait for the danger to pass
            escape, start = found, found[-1]
        route = pathing.find_work_path(start, costs, navigation, self.width, self.height)
        if route is None:
            return None
        route = escape + route
        goal = route[-1] if route else u.tile
        u.path, u.path_goal, u.exact = route, goal, tile_center(goal)
        return owners[goal]


    def _approach_work(self, u: Unit, rect: tuple[int, int, int, int], dt: float,
                       navigation: bytearray) -> bool:
        """Walk to a useful work position; True only when no route exists."""
        goal = u.path_goal
        if (goal is None or navigation[goal[1] * self.width + goal[0]]
                or rect_gap((goal[0] + 0.5, goal[1] + 0.5), rect) - u.radius > TOUCH
                or self._next_waypoint(u, precise=True) is None):
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
            short = self.can_afford(u.player, BUILDINGS[order.type].cost)
            placement = self.can_place(order.type, order.pos, u.player, builder=u.id)
            if short is not None and placement is None and order.plan_if_short and self._leave_plan(u, order, short):
                self._finish_order(u)
                return
            reason = short or placement
            if reason is not None:
                self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text=f"Cannot build: {reason}"))
                self._finish_order(u)
                return
            self._pay(u.player, BUILDINGS[order.type].cost)
            b = self.place_building(u.player, order.type, order.pos, done=False)
            order.building = b.id
            self.events.append(Event("construction", b.center, player=u.player, entity=b.id, target_type=b.type.value))
            self._start_building(u, b)
            return
        if self._approach(u, (order.pos[0] + size // 2, order.pos[1] + size // 2), (order.pos[0] + size / 2, order.pos[1] + size / 2), dt):
            self.events.append(Event("refused", u.pos, player=u.player, entity=u.id, text="Cannot reach the building site"))
            self._finish_order(u)

    def _leave_plan(self, u: Unit, order: Build, short: str) -> bool:
        """Leave the site *u* cannot pay for to the settlement; False when no plan can be made there (plans full,
        or one already on the ground), and the site is refused as any other."""
        try:
            self.settlement.plan_building(u.player, order.type, order.pos)
        except RuleError:
            return False
        name = self.building_info(u.player, order.type).name
        self.events.append(Event("deferred", u.pos, player=u.player, entity=u.id, text=f"{short}: the {name} waits as a plan",
                                 target_type=order.type.value))
        return True

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
        self._turn_toward(u, b.center, dt)
        u.charge += REPAIR_RATE * dt
        if u.charge < REPAIR_CHUNK:
            return
        u.charge -= REPAIR_CHUNK
        amount = min(REPAIR_CHUNK, b.max_hp - b.hp)
        cost = repair_cost(b.info, b.hp, b.hp + amount, b.max_hp)
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
        escape: list[Pos] = []
        if not passable(*start):
            nearest = pathing.nearest_passable(start, passable)
            if nearest is not None:
                if navigation is not None:
                    escape = self._escape(start, nearest) or []
                start = nearest
        target = goal
        if not passable(*goal):
            # A blocked goal (a building, a tree, water) would make A* explore everything it can reach
            # before settling for the nearest tile; aim at that tile from the start.
            nearest = pathing.nearest_passable(goal, passable, prefer=start)
            if nearest is not None:
                target = nearest
        # A goal beyond water or a tree wall: aim at the nearest tile on this side of it, where a search
        # would end anyway after flooding everything it can reach.
        target = self._regions().reachable_goal(start, target)
        u.replan_at = self.time + REPLAN_EVERY + (u.id % REPLAN_STAGGER) * SIM_DT
        if around_units:
            blocked = bytearray(grid)
            width = self.width
            for v in self.units.values():
                if v is not u and not v.hidden and v.state in ("idle", "attack", "chop", "repair") and (navigation is None or v.player == u.player or self.is_visible(u.player, v.tile)):
                    tx, ty = v.tile
                    if (tx, ty) != target and 0 <= tx < width and 0 <= ty < self.height:
                        blocked[ty * width + tx] = 1
            u.path = escape + pathing.find_path_grid(start, target, blocked, width, self.height, max_expansions=LOCAL_EXPANSIONS)
        else:
            u.path = escape + pathing.find_path_grid(start, target, grid, self.width, self.height)
        u.path_goal = goal  # the goal as asked, so a repeated request is recognised
        u.last_distance = math.inf
        u.progress = 0.0
        u.exact = None
        if exact is not None:
            goal_tile = (int(exact[0]), int(exact[1]))
            reached = (u.path[-1] if u.path else start) == goal_tile
            if reached and passable(*goal_tile):
                u.exact = exact

    def _regions(self) -> pathing.Regions:
        """The walkable regions of the static grid, rebuilt after a building or a tree changed it."""
        if self._region_map is None or self._region_map.grid != self._blocked:
            self._region_map = pathing.Regions(self._blocked, self.width, self.height)
        return self._region_map

    def _way_out(self, start: Pos, navigation: bytearray) -> list[Pos] | None:
        """Real-ground steps from *start*, which *navigation* forbids, to the nearest tile it allows; None when no
        such tile is near or real ground does not lead there."""
        width, height = self.width, self.height

        def allowed(x: int, y: int) -> bool:
            return 0 <= x < width and 0 <= y < height and not navigation[y * width + x]
        nearest = pathing.nearest_passable(start, allowed)
        return self._escape(start, nearest) if nearest is not None else None

    def _escape(self, start: Pos, nearest: Pos) -> list[Pos] | None:
        """Real-ground steps from *start*, which the safe map forbids (an enemy came close), to *nearest*, which it
        allows; None when real ground does not lead there (a wall between, or too far for the local budget)."""
        if not self.passable(*start):
            return None
        route = pathing.find_path_grid(start, nearest, self._blocked, self.width, self.height, max_expansions=LOCAL_EXPANSIONS)
        return route if route and route[-1] == nearest else None

    def _effective_speed(self, u: Unit) -> float:
        """How fast *u* walks right now: its own speed, capped to its order's group pace.

        The cap holds only while a paced Move/AttackMove is the current order (an
        engaged unit fights at full speed), and releases once the group stretches
        more than 6 tiles from its leading unit, so a stuck unit never holds the rest.
        """
        base = self.speed_of(u)
        order = u.order
        if not isinstance(order, (Move, AttackMove)) or order.pace is None or order.pace >= base:
            return base
        return order.pace if self._group_together(u.player, order.target, order.pace) else base

    def _group_together(self, player: int, target: Point, pace: float) -> bool:
        """Whether every unit of *player* pacing towards *target* is within 6 tiles of the one leading the
        way.  Memoised for the step: a group of a hundred would otherwise be scanned a hundred times."""
        key = (player, target, pace)
        together = self._pace_groups.get(key)
        if together is None:
            mates = [v for v in self.units.values()
                     if v.player == player and not v.hidden and v.hp > 0 and isinstance(v.order, (Move, AttackMove))
                     and v.order.pace == pace and v.order.target == target]
            leader = min(mates, key=lambda v: (dist(v.pos, target), v.id)).pos if mates else target
            together = self._pace_groups[key] = all(dist(m.pos, leader) <= 6.0 for m in mates)
        return together

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
        path = u.path
        if path:
            ahead = path[0]
            if len(path) == 1 and u.exact is not None:
                return u.exact  # straight to the spot from anywhere on its tile: the centre first would overshoot and come back
            return (ahead[0] + 0.5, ahead[1] + 0.5)  # a detour back to the unit's own tile centre is walked first
        # Work requires contact, so the walking tolerance cannot discard a
        # final step that would put the worker inside interaction range.
        exact = u.exact
        if exact is not None and hypot(u.x - exact[0], u.y - exact[1]) > (1e-6 if precise else ARRIVE):
            return exact
        return None

    def _follow(self, u: Unit, dt: float, *, settle: bool = False, navigation: bytearray | None = None,
                precise: bool = False, spent: float = 0.0) -> bool:
        """Step along the path; True when there was nothing left to walk.  *spent* is the travel this tick
        already used before the current waypoint, so a walk keeps its pace through the corners of its path."""
        waypoint = self._next_waypoint(u, precise=precise)
        if waypoint is None:
            u.state = "idle"
            return True
        u.state = "move"
        width = self.width
        tile = tx, ty = int(u.x), int(u.y)  # nothing below moves the unit until the very last step
        if navigation is not None and navigation[ty * width + tx]:
            navigation = None  # caught on forbidden ground: any real step out is better than standing still
        grid = self._blocked if navigation is None else navigation
        if u.path and u.path_goal is not None:
            ahead_x, ahead_y = u.path[0]
            if (grid[ahead_y * width + ahead_x] or max(abs(ahead_x - tx), abs(ahead_y - ty)) > 1
                    or (ahead_x != tx and ahead_y != ty and (grid[ty * width + ahead_x] or grid[ahead_y * width + tx]))):
                # Something was built across the path, or a crowd pushed the unit off it: further than a
                # step, or onto the diagonal neighbour whose corner it cannot cut (going back to the
                # centre first would only bring it to the same corner again).
                if self.time >= u.replan_at:
                    self._plan(u, u.path_goal, u.exact, around_units=True, navigation=navigation)
                    return False
                centre = tile_center(tile)
                if dist(u.pos, centre) <= ARRIVE:
                    # At the centre already: wait there for the plan, rather than spend the tick's leftover
                    # travel towards the refused tile and walk back next tick.
                    u.x, u.y = centre
                    u.last_distance = math.inf
                    return False
                u.path.insert(0, tile)
        dx, dy = waypoint[0] - u.x, waypoint[1] - u.y
        d = hypot(dx, dy)
        speed = self._effective_speed(u)
        step = speed * dt - spent  # what is left of this tick's travel
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
            if step - d > 1e-9 and self._next_waypoint(u, precise=precise) is not None:
                # The tick's travel is not used up at a waypoint: the rest goes on towards the next one.
                return self._follow(u, dt, settle=settle, navigation=navigation, precise=precise, spent=spent + d)
            return False
        self._turn_toward(u, waypoint, step / speed if speed else dt)
        nx, ny = u.x + dx / d * step, u.y + dy / d * step
        if ((grid[int(ny) * width + int(nx)] or (navigation is not None and not self._line_clear(u.pos, (nx, ny), navigation=navigation)))
                and 0 <= tx < width and 0 <= ty < self.height and not self._blocked[ty * width + tx]):
            if u.path and u.path[0] != tile:
                # Pushed off course so that the straight line to the next tile crosses a blocked
                # one: go back to this tile's centre first, which is always possible.
                u.path.insert(0, tile)
            elif u.path_goal is not None and self.time >= u.replan_at:
                # Even from the centre the straight step to the exact spot crosses a blocked tile: it
                # lies across a corner.  Plan again; the planner never cuts corners, so the path comes
                # in from an open side, or there is none and the walk ends here.
                self._plan(u, u.path_goal, u.exact, navigation=navigation)
            return False
        u.x, u.y = nx, ny
        # Progress watchdog: closing on the goal resets it; a stretch without progress paths
        # again around the units in the way.
        if u.path_goal is None:
            remaining = 0.0
        else:
            aim = u.exact if u.exact is not None else (u.path_goal[0] + 0.5, u.path_goal[1] + 0.5)
            remaining = hypot(nx - aim[0], ny - aim[1])
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
        width, height = self.width, self.height
        if not (0 <= a[0] < width and 0 <= a[1] < height
                and 0 <= b[0] < width and 0 <= b[1] < height):
            return False
        grid = self._blocked if navigation is None else navigation
        x, y = int(a[0]), int(a[1])
        end_x, end_y = int(b[0]), int(b[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        # Fraction of the segment at which the next vertical / horizontal grid line is crossed.
        next_x = ((x + (step_x > 0)) - a[0]) / dx if dx else math.inf
        next_y = ((y + (step_y > 0)) - a[1]) / dy if dy else math.inf
        per_x, per_y = (abs(1 / dx) if dx else math.inf), (abs(1 / dy) if dy else math.inf)
        # The walk never leaves the box spanned by the two endpoints, so only the two
        # tiles beside a corner need their own bounds test.
        row = y * width
        for _ in range(abs(end_x - x) + abs(end_y - y) + 1):
            if grid[row + x]:
                return False
            if x == end_x and y == end_y:
                return True
            if abs(next_x - next_y) < 1e-9:
                beside_x, beside_y = x + step_x, y + step_y
                if not 0 <= beside_x < width or grid[row + beside_x]:
                    return False
                if not 0 <= beside_y < height or grid[beside_y * width + x]:
                    return False
                x, y, row = beside_x, beside_y, beside_y * width
                next_x, next_y = next_x + per_x, next_y + per_y
            elif next_x < next_y:
                x, next_x = x + step_x, next_x + per_x
            else:
                y, next_y, row = y + step_y, next_y + per_y, row + step_y * width
        return not grid[row + x]

    def _steer(self, u: Unit, target: Point, dt: float) -> bool:
        """Walk straight at *target* when it is near and the line is clear; True if that was possible."""
        if dist(u.pos, target) > STEER_RANGE or not self._line_clear(u.pos, target):
            return False
        dx, dy = target[0] - u.x, target[1] - u.y
        d = hypot(dx, dy)
        if d >= 1e-6:
            step = min(d, self._effective_speed(u) * dt)
            self._turn_toward(u, target, dt)
            u.x, u.y = u.x + dx / d * step, u.y + dy / d * step  # on the segment, so on a tile just checked
        u.path = []
        u.path_goal = None
        u.exact = None
        u.state = "move"
        return True

    def _separate(self) -> None:
        """Push overlapping units apart, never into blocked tiles."""
        # The neighbour scan is :meth:`units_near` inlined: it runs for every unit on every
        # step, and the bucket rows it walks are only ever three cells wide.
        moves: list[tuple[Unit, float, float]] = []
        width, height, buckets = self.width, self.height, self._buckets
        radius = 2 * UNIT_RADIUS + SPACING
        reach, r2 = int(radius) + 1, radius * radius
        for u in self.units.values():
            if u.hidden:
                continue
            px = py = 0.0
            ux, uy = u.x, u.y
            moving = u.state == "move"
            at_ease: bool | None = None  # asked only of a unit with a neighbour just out of touch
            hx, hy = (math.cos(u.facing), math.sin(u.facing)) if moving else (0.0, 0.0)
            x0, x1 = max(0, int(ux) - reach), min(width - 1, int(ux) + reach)
            y0, y1 = max(0, int(uy) - reach), min(height - 1, int(uy) + reach)
            span = x1 - x0 + 1
            for y in range(y0, y1 + 1):
                row = y * width + x0
                for index in range(row, row + span):
                    cell = buckets[index]
                    if not cell:
                        continue
                    for v in cell:
                        dx, dy = ux - v.x, uy - v.y
                        if dx * dx + dy * dy > r2 or v is u or v.hidden:
                            continue
                        d = hypot(dx, dy)
                        overlap = u.radius + v.radius - d
                        if overlap <= 0:
                            if at_ease is None and overlap > -SPACING:
                                at_ease = self._at_ease(u)
                            if at_ease and overlap > -SPACING:
                                # Elbow room: a unit at ease eases off a neighbour it is not quite touching.
                                weight = (0.5 if v.state == "move" or not moving else 0.2) * SPACING_WEIGHT
                                px += dx / d * (overlap + SPACING) * weight
                                py += dy / d * (overlap + SPACING) * weight
                            continue
                        if d < 1e-6:
                            angle = (u.id * 2.399) % (2 * math.pi)
                            dx, dy, d = math.cos(angle), math.sin(angle), 1.0
                        weight = 0.5 if v.state == "move" or not moving else 0.2
                        px += dx / d * overlap * weight
                        py += dy / d * overlap * weight
                        if moving:
                            # Walking units also step to their own right, so two meeting head-on pass
                            # each other instead of pushing each other back along the same line forever.
                            px += -hy * overlap * SIDESTEP
                            py += hx * overlap * SIDESTEP
            if px or py:
                moves.append((u, px, py))
        for u, px, py in moves:
            self._nudge(u, px, py)

    @staticmethod
    def _at_ease(u: Unit) -> bool:
        """Neither fighting, working nor holding: standing, or walking somewhere without a target."""
        order = u.order
        return u.windup <= 0.0 and u.state != "attack" and (order is None or type(order) in AT_EASE_ORDERS)

    def _nudge(self, u: Unit, px: float, py: float) -> None:
        """Shove *u* by at most MAX_PUSH, never through a blocked tile or across a blocked corner."""
        length = hypot(px, py)
        if length > MAX_PUSH:
            px, py = px / length * MAX_PUSH, py / length * MAX_PUSH
        own_tile_open = self.passable(int(u.x), int(u.y))
        # The whole shove, else its x part alone, else its y part alone.
        if not self._shove(u, px, py, own_tile_open) and not self._shove(u, px, 0.0, own_tile_open):
            self._shove(u, 0.0, py, own_tile_open)

    def _shove(self, u: Unit, dx: float, dy: float, own_tile_open: bool) -> bool:
        """Move *u* by (dx, dy), kept on the map, if nothing blocks the way; whether it moved."""
        nx, ny = min(max(u.x + dx, 0.05), self.width - 0.05), min(max(u.y + dy, 0.05), self.height - 0.05)  # _clamp's
        if self._line_clear((u.x, u.y), (nx, ny)) if own_tile_open else self.passable(int(nx), int(ny)):
            u.x, u.y = nx, ny
            return True
        return False

    # -- Combat ----------------------------------------------------------------------

    def _target_point(self, target: Entity) -> Point:
        return target.pos if isinstance(target, Unit) else target.center

    def _turn_toward(self, u: Unit, point: Point, dt: float) -> bool:
        """Pivot *u* toward *point* at its turn rate; True once it faces it."""
        dx, dy = point[0] - u.x, point[1] - u.y
        if not (dx or dy):
            return True
        wanted = _atan2(dy, dx)
        delta = (wanted - u.facing + math.pi) % (2 * math.pi) - math.pi
        step = u.info.turn * dt
        if -step <= delta <= step:
            u.facing = wanted
            return True
        u.facing = (u.facing + (step if delta > 0 else -step) + math.pi) % (2 * math.pi) - math.pi
        return False

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
        return u.info.min_range <= self._gap(u, target) <= self.range_of(u) + 0.05

    def _threat(self, entity: Entity) -> int:
        """Whom to fight first, lowest first: soldiers, other units (workers, healers), towers, other buildings."""
        if isinstance(entity, Unit):
            return 0 if entity.info.soldier and not entity.is_worker else 1
        return 2 if entity.info.damage and entity.done else 3

    def _retarget(self, u: Unit, order: Attack, target: Entity) -> None:
        order.target = target.id
        u.path = []
        u.path_goal = None

    def _nearest_enemy(self, player: int, point: Point, radius: float, *, units_only: bool = False,
                       min_radius: float = 0.0) -> Entity | None:
        """The visible enemy within *radius* (and beyond *min_radius*) to fight first: by :meth:`_threat`, then the nearest."""
        best: Entity | None = None
        # The best (threat, distance) so far, compared as the tuple would be; no threat is as high as 4.
        best_threat, best_d = 4, math.inf
        px, py = point
        visible, width, height = self.visible[player], self.width, self.height
        for unit in self.units_near(point, radius + UNIT_RADIUS):
            if unit.player == player or unit.hidden or unit.hp <= 0:
                continue
            x, y = int(unit.x), int(unit.y)
            if not (0 <= x < width and 0 <= y < height and visible[y * width + x]):  # is_visible's test
                continue
            d = hypot(px - unit.x, py - unit.y)
            if d > radius + unit.radius or d - unit.radius < min_radius:
                continue
            threat = self._threat(unit)
            if threat < best_threat or threat == best_threat and d < best_d:
                best, best_threat, best_d = unit, threat, d
        if best is not None or units_only:
            return best
        for building in self.buildings.values():
            if building.player is None or building.player == player or building.hp <= 0 or building.abandoned:
                continue  # a ruin is razed on an explicit order, never picked up in passing
            bx, by, bw, bh = building.rect
            if not (bx - radius <= px <= bx + bw + radius and by - radius <= py <= by + bh + radius):
                continue  # too far on one axis alone, so the real gap cannot be within reach
            d = rect_gap(point, building.rect)
            if d > radius or d < min_radius:
                continue
            threat = self._threat(building)
            if ((threat < best_threat or threat == best_threat and d < best_d)
                    and any(self.is_visible(player, tile) for tile in building.tiles())):
                best, best_threat, best_d = building, threat, d
        return best

    def _strike(self, u: Unit, target: Entity) -> None:
        """One blow from *u* at *target*: a melee hit lands now, an arrow goes up and lands when it arrives."""
        damage = self.damage_of(u)
        if u.info.melee:
            self._hit(target, damage, player=u.player, source=u.id, source_type=u.type.value, attack=u.info.attack)
        else:
            self._launch_arrow(u, target, damage)

    def _launch_arrow(self, shooter: Entity, target: Entity, damage: int) -> Projectile:
        start = self._target_point(shooter)
        aim = self._target_point(target)
        attack = shooter.info.attack if isinstance(shooter, Unit) else AttackType.NORMAL  # a tower's arrow strikes a normal blow
        return self._launch(shooter, "arrow", start, aim, target.id, damage, max(SIM_DT, dist(start, aim) / ARROW_SPEED), attack=attack)

    def _launch_stone(self, u: Unit, aim: Point) -> Projectile:
        return self._launch(u, "stone", u.pos, aim, None, self.damage_of(u), self._stone_flight(u.pos, aim),
                            splash=self.splash_of(u), attack=u.info.attack)

    def _launch(self, shooter: Entity, kind: str, start: Point, aim: Point, target: int | None, damage: int, flight: float, *,
                splash: float = 0.0, attack: AttackType = AttackType.NORMAL) -> Projectile:
        assert shooter.player is not None
        p = Projectile(self._new_id(), shooter.player, shooter.id, shooter.type.value, kind, start, aim, target, self.time, flight, damage,
                       splash=splash, attack=attack)
        self.projectiles[p.id] = p
        return p

    def _stone_flight(self, start: Point, aim: Point) -> float:
        return max(STONE_MIN_FLIGHT, dist(start, aim) / STONE_SPEED)

    def _aim_point(self, u: Unit, target: Entity, *, auto: bool) -> Point | None:
        """Where a siege crew drops its stone on *target*: the nearest wall of a building, or ahead of a
        marching unit by the stone's flight so it comes down where the unit will be.  None when there is
        no shot: every landing point is inside the engine's minimum range, or the crew is firing on its
        own judgement (*auto*) and its own side stands where the stone would fall.  On its own judgement
        a crew may also drop the stone a tile beyond a unit, from where the splash still reaches it: a
        soldier locked with the crew's own line is caught that way without a stone on the line.  A crew
        ordered to fire by the player fires, and the player answers for the splash."""
        if isinstance(target, Building):
            x, y, w, h = target.rect
            spots = [(min(max(u.x, x), x + w), min(max(u.y, y), y + h))]
        else:
            here = target.pos
            spots = [here]
            if target.vx or target.vy:
                flight = self._stone_flight(u.pos, here)
                lead = self._clamp((here[0] + target.vx * flight, here[1] + target.vy * flight))
                reach, far = self.range_of(u) + u.radius, dist(u.pos, lead)
                if far > reach:  # never beyond where the engine can throw
                    lead = (u.x + (lead[0] - u.x) / far * reach, u.y + (lead[1] - u.y) / far * reach)
                spots.insert(0, lead)
            off = dist(u.pos, here)
            if auto and off > 0.0:
                # The stone lands this far past the unit and still catches it, but never beyond where the engine can throw.
                beyond = min(self.splash_of(u) - target.radius, self.range_of(u) + u.radius - off)
                if beyond > 0.0:
                    spots.append(self._clamp((here[0] + (here[0] - u.x) / off * beyond, here[1] + (here[1] - u.y) / off * beyond)))
        spots = [spot for spot in spots if dist(u.pos, spot) - u.radius >= u.info.min_range]
        if not spots:
            return None
        for spot in spots:
            if self._clear_of_friends(u, spot):
                return spot
        return None if auto else spots[-1]

    def _clear_of_friends(self, u: Unit, spot: Point) -> bool:
        """Whether a stone from *u* coming down on *spot* stays off its own side: no friend stands within its splash
        and :data:`FRIENDLY_MARGIN`, is walking into it before the stone lands, or is on its way to fight an enemy within arm's
        length of it (a soldier after an archer that steps back between its shots)."""
        keep_clear = self.splash_of(u) + FRIENDLY_MARGIN
        flight = self._stone_flight(u.pos, spot)
        sx, sy = spot
        for ally in self.units_near(spot, keep_clear + UNIT_RADIUS + _FASTEST * flight):
            if ally.player != u.player or ally is u or ally.hidden or ally.hp <= 0:
                continue
            if dist(spot, ally.pos) - ally.radius <= keep_clear:
                return False
            if hypot(ally.x + ally.vx * flight - sx, ally.y + ally.vy * flight - sy) - ally.radius <= keep_clear:
                return False
            order = ally.order
            if isinstance(order, Attack):
                foe = self.entity(order.target)
                # It will stand at arm's length of its foe, on whichever side it comes from.
                if (isinstance(foe, Unit) and not self._in_range(ally, foe)
                        and dist(spot, foe.pos) - foe.radius - self.range_of(ally) - 2 * ally.radius <= keep_clear):
                    return False
        return True

    def _siege_choice(self, u: Unit, step: float) -> Entity | None:
        """What a siege crew on its own judgement throws at next: of the enemies it can see within its reach
        plus *step* tiles, the one whose clear stone is worth the most (:meth:`_stone_worth`), a walk to
        reach it counting against it.  None when no stone can fall clear of its own side."""
        reach = self.range_of(u) + u.radius
        radius = reach + step
        best: Entity | None = None
        best_worth = 0.0
        for enemy in self.units_near(u.pos, radius + UNIT_RADIUS):
            if enemy.player == u.player or enemy.hidden or enemy.hp <= 0 or not self.is_visible(u.player, enemy.tile):
                continue
            walk = dist(u.pos, enemy.pos) - reach
            if walk > step:
                continue
            spot = self._aim_point(u, enemy, auto=True)
            if spot is None:
                continue
            worth = self._stone_worth(u, spot) / (1.0 + max(0.0, walk))
            if worth > best_worth:
                best, best_worth = enemy, worth
        if best is not None:
            return best
        for building in self.buildings.values():
            if building.player is None or building.player == u.player or building.hp <= 0 or building.abandoned:
                continue
            walk = rect_gap(u.pos, building.rect) - reach
            if walk > step or not any(self.is_visible(u.player, tile) for tile in building.tiles()):
                continue
            spot = self._aim_point(u, building, auto=True)
            if spot is None:
                continue
            worth = SIEGE_BUILDING_WORTH * (2.0 if building.info.damage and building.done else 1.0) / (1.0 + max(0.0, walk))
            if worth > best_worth:
                best, best_worth = building, worth
        return best

    def _siege_creeps(self, u: Unit, target: Entity, auto: bool) -> bool:
        """A crew on its own judgement whose target, though in reach, has no clear stone rolls closer: from nearer, the
        stone can come down beyond the target, clear of its own side.  It stops two splashes outside its minimum range."""
        return (auto and u.info.splash > 0.0 and isinstance(target, Unit) and u.windup <= 0.0
                and self._gap(u, target) > u.info.min_range + 2 * self.splash_of(u)
                and self._aim_point(u, target, auto=True) is None)

    def _stone_worth(self, u: Unit, spot: Point) -> float:
        """What a stone from *u* landing on *spot* would do to the enemy units it can see there: each counts its
        :data:`SIEGE_WORTH`, in full within :data:`DIRECT_HIT` and :data:`SPLASH_FRACTION` of it out to the splash."""
        splash = self.splash_of(u)
        worth = 0.0
        for enemy in self.units_near(spot, splash + UNIT_RADIUS):
            if enemy.player == u.player or enemy.hidden or enemy.hp <= 0 or not self.is_visible(u.player, enemy.tile):
                continue
            gap = dist(spot, enemy.pos) - enemy.radius
            if gap <= splash:
                worth += SIEGE_WORTH.get(enemy.type, 1.0) * (1.0 if gap <= DIRECT_HIT else SPLASH_FRACTION)
        return worth

    def _land_projectiles(self) -> None:
        if not self.projectiles:
            return
        now = self.time
        for p in [p for p in self.projectiles.values() if p.lands_at <= now]:
            del self.projectiles[p.id]
            if p.target is None:
                self._land_stone(p)
                continue
            target = self.entity(p.target)
            if target is not None and target.hp > 0 and not (isinstance(target, Unit) and target.hidden):
                self._hit(target, p.damage, player=p.player, source=p.source, source_type=p.source_type, attack=p.attack, ranged=True)

    def _land_stone(self, p: Projectile) -> None:
        """A stone comes down: its full damage within DIRECT_HIT of the point and SPLASH_FRACTION of it out
        to the splash radius, on every unit standing there, friend or foe, and on the enemy's buildings."""
        self.events.append(Event("impact", p.aim, player=p.player, entity=p.source, text=p.kind, source_type=p.source_type))
        splash = int(p.damage * SPLASH_FRACTION)
        for unit in list(self.units_near(p.aim, p.splash + UNIT_RADIUS)):
            if unit.hidden or unit.hp <= 0:
                continue
            gap = dist(p.aim, unit.pos) - unit.radius
            if gap <= p.splash:
                self._hit(unit, p.damage if gap <= DIRECT_HIT else splash, player=p.player, source=p.source, source_type=p.source_type,
                          attack=p.attack, ranged=True)
        for building in list(self.buildings.values()):
            if building.player in (None, p.player) or building.hp <= 0:
                continue
            gap = rect_gap(p.aim, building.rect)
            if gap <= p.splash:
                self._hit(building, p.damage if gap <= DIRECT_HIT else splash, player=p.player, source=p.source, source_type=p.source_type,
                          attack=p.attack, ranged=True)

    def _hit(self, target: Entity, damage: int, *, player: int, source: int, source_type: str,
             attack: AttackType = AttackType.NORMAL, ranged: bool = False) -> None:
        """*damage* from *player*'s *source* (a unit or building, possibly gone by now) lands on *target*."""
        if target.hp <= 0:
            return  # already down this step (a siege splash after the killing blow)
        armor = self.armor_of(target)
        factor = damage_factor(attack, self.armor_class_of(target))
        if factor != 1.0:
            damage = int(round(damage * factor))
        roll = damage * self.rng.uniform(1 - HIT_VARIANCE, 1 + HIT_VARIANCE)
        dealt = max(1, int(round(roll)) - armor)
        target.hp -= dealt
        own = target.player == player
        abandoned = isinstance(target, Building) and target.abandoned
        if target.hp <= 0 and target.player is not None and not own and not abandoned:
            stats = self.players[player].stats
            stats["units_killed" if isinstance(target, Unit) else "buildings_razed"] += 1
            stats["destroyed_value"] += target.info.cost.gold + target.info.cost.lumber
        self.events.append(Event("hit", self._target_point(target), player=target.player, entity=source, other=target.id,
                                 amount=dealt, text="ranged" if ranged else "melee", source_type=source_type,
                                 target_type=target.type.value, target_armor=armor,
                                 target_complete=not isinstance(target, Building) or target.done))
        if own or abandoned:
            return  # a stone on one's own side hurts, but is no attack to answer or to raise the alarm for; nobody answers for a ruin
        if target.player is not None:
            victim = self.players[target.player]
            if self.time - victim.last_alert >= UNDER_ATTACK_COOLDOWN:
                victim.last_alert = self.time
                self.events.append(Event("under_attack", self._target_point(target), player=target.player, entity=target.id))
        if isinstance(target, Building) and target.hp <= 0 and self._has(player, Upgrade.PLUNDER):
            loot = int(target.info.cost.gold * PLUNDER_SHARE)
            if loot:
                self.players[player].gold += loot
                self.events.append(Event("plunder", target.center, player=player, entity=source, other=target.id, amount=loot))
        striker = self.units.get(source)
        if striker is not None and isinstance(target, Unit) and target.hp > 0 and self._threat(target) == 0:
            current = target.order
            if current is None:
                target.home = target.pos
                target.orders.append(Attack(striker.id, auto=True))
            elif isinstance(current, Attack) and current.auto:
                busy_with = self.entity(current.target)
                if busy_with is None or self._threat(striker) < self._threat(busy_with):
                    self._retarget(target, current, striker)  # a soldier busy on a bystander or a building answers whoever hits it

    def _bury_the_dead(self) -> None:
        for unit in [u for u in self.units.values() if u.hp <= 0]:
            self._remove_unit(unit)
        for building in [b for b in self.buildings.values() if b.hp <= 0 and b.type is not BuildingType.GOLD_MINE]:
            self._remove_building(building, reason="destroyed")

    def _remove_unit(self, unit: Unit) -> None:
        self._leave_mine(unit)
        del self.units[unit.id]
        self.players[unit.player].stats["units_lost"] += 1
        if unit.constructing is not None:
            b = self.buildings.get(unit.constructing)
            if b is not None and b.builder == unit.id:
                b.builder = None
        self.events.append(Event("death", unit.pos, player=unit.player, entity=unit.id, text=unit.type.value))

    def _remove_building(self, b: Building, *, reason: str) -> None:
        del self.buildings[b.id]
        self._building_epoch += 1
        if reason == "destroyed" and b.player is not None:
            self.players[b.player].stats["buildings_lost"] += 1
        self._set_blocked(b, False)
        self._mine_crews.pop(b.id, None)
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

    def recovery_recruit(self, player: int) -> tuple[Building, UnitType] | None:
        """A recruit affordable after cancelling unfinished work, with existing supply.

        Used only for a player without units: there is no worker to earn more or
        finish construction.  Prefer a worker to restart the economy.
        """
        owner = self.players[player]
        buildings = self.player_buildings(player)
        refunds = [b.info.cost for b in buildings if not b.done]
        refunds += [UPGRADES[b.research].cost for b in buildings if b.research is not None]
        gold = owner.gold + sum(c.gold for c in refunds)
        lumber = owner.lumber + sum(c.lumber for c in refunds)
        used, cap = self.supply(player)
        if used >= cap:
            return None
        candidates = [(b, u) for b in buildings if b.done for u in b.info.trains
                      if UNITS[u].cost.gold <= gold and UNITS[u].cost.lumber <= lumber]
        return min(candidates, key=lambda pair: (pair[1] is not UnitType.PEASANT,
                   UNITS[pair[1]].cost.gold + UNITS[pair[1]].cost.lumber, pair[0].id)) if candidates else None

    @recorded
    def assign_workers(self, player: int) -> None:
        """Send *player*'s idle peasants to work now, as the simulation does for everyone once a second.

        A computer player asks for this as soon as it has thought, so it is an order like its others.
        """
        worker_ai.assign_idle_workers(self, player)

    def clear_player(self, player: int) -> None:
        """Take everything *player* owns off the map without a fight and mark them out: a mission's
        setup, not a defeat, so no event, no statistic and no elimination is recorded.  A later
        :meth:`spawn_unit` for the player puts them back in play (a mission's ``place`` does the same)."""
        for unit in self.player_units(player):
            del self.units[unit.id]
        for building in self.player_buildings(player):
            del self.buildings[building.id]
            self._set_blocked(building, False)
        self.players[player].alive = False
        self._index_units()

    def can_resign(self, player: int) -> str | None:
        """Why *player* cannot concede, or None when resigning is allowed."""
        if self.winner is not None:
            return "the match is over"
        if not self.players[player].alive:
            return f"{self.players[player].name} is already out"
        return None

    @recorded
    def resign(self, player: int) -> None:
        """Concede the match: remove everything *player* owns, then eliminate them."""
        reason = self.can_resign(player)
        if reason is not None:
            raise RuleError(reason)
        halls = self.player_buildings(player, BuildingType.TOWN_HALL)
        owned = self.player_buildings(player)
        units = self.player_units(player)
        if halls:
            pos = halls[0].center
        elif owned:
            pos = owned[0].center
        elif units:
            pos = units[0].pos
        else:
            pos = (0.0, 0.0)
        for unit in units:
            self._remove_unit(unit)
        for building in owned:
            if len(self.players) >= 3:
                self._abandon(building)  # the others fight on around what is left
            else:
                self._remove_building(building, reason="resigned")
        self.events.append(Event("resigned", pos, player=player, text=self.players[player].name))
        self._check_elimination()

    def _abandon(self, b: Building) -> None:
        """Leave *b* standing as nobody's: its footprint and hit points stay, everything it did stops."""
        b.abandoned = True
        b.queue.clear()
        b.train_progress = 0.0
        b.research, b.research_progress = None, 0.0
        b.rally = None
        b.auto.clear()
        for unit in self.units.values():
            if unit.inside == b.id:
                unit.inside = None
                unit.timer = 0.0
            if unit.constructing == b.id:
                unit.constructing = None
        self.events.append(Event("abandoned", b.center, player=b.player, entity=b.id, text=b.type.value))

    def _check_elimination(self) -> None:
        for player in self.players:
            if not player.alive or any(unit.player == player.id for unit in self.units.values()):
                continue
            buildings = self.player_buildings(player.id)
            if not buildings:
                player.alive = False
                self.events.append(Event("eliminated", (0.0, 0.0), player=player.id, text=f"{player.name} has fallen"))
            elif not player.human and not self.scripted and not any(b.done and b.queue for b in buildings) and self.recovery_recruit(player.id) is None:
                # An AI with no units, nothing in training and no affordable recruit cannot come back.  A mission's
                # sides fight to the last building: its camps have no brain to give up, and its objectives say "every".
                player.alive = False
                player.surrendered = True
                for building in buildings:
                    if len(self.players) >= 3:
                        self._abandon(building)
                    else:
                        self._remove_building(building, reason="abandoned")
                self.events.append(Event("surrendered", (0.0, 0.0), player=player.id,
                                         text=f"{player.name} surrenders: no units and no way to recruit"))
        alive = [p for p in self.players if p.alive]
        if self.winner is None and not self.scripted and len(alive) == 1 and len(self.players) > 1:
            self.winner = alive[0].id
            self.events.append(Event("victory", (0.0, 0.0), player=self.winner, text=f"{alive[0].name} wins"))

    # -- Serialisation ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width, "height": self.height, "theme": self.theme.value, "layout": self.layout.value,
            "terrain": ["".join(t.value[0] for t in row) for row in self.terrain],
            "players": [{"id": p.id, "name": p.name, "human": p.human, "race": p.race.value, "gold": p.gold, "lumber": p.lumber, "alive": p.alive,
                         "surrendered": p.surrendered, "stats": dict(p.stats), "last_alert": p.last_alert,
                         "upgrades": sorted(u.value for u in p.upgrades),
                         "assembly": list(p.assembly) if p.assembly is not None else None} for p in self.players],
            "regrowth": [[list(tile), when] for tile, when in self.regrowth],
            "units": [_unit_to_dict(u) for u in self.units.values()],
            "buildings": [_building_to_dict(b) for b in self.buildings.values()],
            "projectiles": [_projectile_to_dict(p) for p in self.projectiles.values()],
            "explored": [bytes(e).hex() for e in self.explored],
            "worker_knowledge": [knowledge.to_dict() for knowledge in self.worker_knowledge],
            "settlement": self.settlement.to_dict(),
            "time": self.time, "tick": self.tick, "next_id": self._next_id, "winner": self.winner, "scripted": self.scripted,
            "rng": self.rng.getstate(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> World:
        letters = {t.value[0]: t for t in Terrain}
        terrain = [[letters[c] for c in row] for row in data["terrain"]]
        human = next((p["id"] for p in data["players"] if p["human"]), None)
        world = cls(data["width"], data["height"], terrain, len(data["players"]), human=human, theme=MapTheme(data["theme"]),
                    races=[Race(p.get("race", Race.HUMAN.value)) for p in data["players"]], layout=Layout(data["layout"]),
                    scripted=data.get("scripted", False))
        world.regrowth = [((tile[0], tile[1]), when) for tile, when in data.get("regrowth", [])]
        for p, saved in zip(world.players, data["players"]):
            p.human = saved["human"]
            p.name = saved.get("name", p.name)
            p.gold, p.lumber, p.alive, p.last_alert = saved["gold"], saved["lumber"], saved["alive"], saved["last_alert"]
            p.upgrades = {Upgrade(u) for u in saved["upgrades"]}
            p.assembly = tuple(saved["assembly"]) if saved.get("assembly") is not None else None
            p.surrendered = saved.get("surrendered", False)
            p.stats.update(saved.get("stats", {}))
        for saved in data["buildings"]:
            b = _building_from_dict(saved, world.race_of(saved["player"]))
            world.buildings[b.id] = b
            world._set_blocked(b, True)
        for saved in data["units"]:
            u = _unit_from_dict(saved, world.race_of(saved["player"]))
            world.units[u.id] = u
            if u.inside is not None:  # the crews are counted, not stored: a load rebuilds them
                world._mine_crews[u.inside] = world._mine_crews.get(u.inside, 0) + 1
        for saved in data.get("projectiles", []):
            shot = _projectile_from_dict(saved)
            world.projectiles[shot.id] = shot
        world.explored = [bytearray(bytes.fromhex(e)) for e in data["explored"]]
        if "worker_knowledge" in data:
            world.worker_knowledge = [WorkerKnowledge.from_dict(knowledge) for knowledge in data["worker_knowledge"]]
        if "settlement" in data:
            world.settlement.restore(data["settlement"])
        world.time, world.tick, world._next_id, world.winner = data["time"], data["tick"], data["next_id"], data["winner"]
        state = data["rng"]
        world.rng.setstate((state[0], tuple(state[1]), state[2]))
        world._index_units()
        world._exposed = world._exposed_players()
        world.update_vision()
        world.events.clear()
        return world


def _order_to_dict(order: Order) -> dict[str, Any]:
    # Keep player-order fields stable: online clients read them straight from the snapshot.
    # Automatic routing metadata lives beside the queue in each unit record.
    if isinstance(order, Harvest):
        return {"kind": "Harvest", "target": list(order.target) if isinstance(order.target, tuple) else order.target}
    if isinstance(order, Deposit):
        return {"kind": "Deposit"}
    d: dict[str, Any] = {"kind": type(order).__name__}
    for key, value in vars(order).items():
        if key == "plan_if_short" and not value:
            continue  # only a player's own placements carry it: a build as every brain gives it reads as before
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
        fields.setdefault("pace", None)  # saves from before the group pace existed
    elif kind is Patrol:
        fields["start"], fields["end"] = tuple(fields["start"]), tuple(fields["end"])
    return kind(**fields)


def _unit_to_dict(u: Unit) -> dict[str, Any]:
    return {
        "id": u.id, "type": u.type.value, "player": u.player, "x": u.x, "y": u.y, "hp": u.hp, "facing": u.facing,
        "orders": [_order_to_dict(o) for o in u.orders], "cooldown": u.cooldown, "windup": u.windup, "vx": u.vx, "vy": u.vy,
        "worker_orders": [{"index": index, "auto": order.auto,
                           **({"target": order.target} if isinstance(order, Deposit) else {})}
                          for index, order in enumerate(u.orders) if isinstance(order, (Harvest, Deposit))],
        "carrying": u.carrying.value if u.carrying else None, "carry": u.carry, "timer": u.timer,
        "inside": u.inside, "constructing": u.constructing, "home": list(u.home) if u.home else None, "state": u.state,
        "ease": list(u.ease) if u.ease else None, "charge": u.charge, "auto_work": u.auto_work,
    }


def _unit_from_dict(d: dict[str, Any], race: Race) -> Unit:
    u = Unit(d["id"], UnitType(d["type"]), d["player"], d["x"], d["y"], d["hp"], race=race, facing=d["facing"], cooldown=d["cooldown"],
             windup=d.get("windup", 0.0), vx=d.get("vx", 0.0), vy=d.get("vy", 0.0), carrying=Resource(d["carrying"]) if d["carrying"] else None, carry=d["carry"], timer=d["timer"],
             inside=d["inside"], constructing=d["constructing"], home=tuple(d["home"]) if d["home"] else None, state=d["state"],
             ease=tuple(d["ease"]) if d.get("ease") else None, charge=d["charge"], auto_work=d.get("auto_work", True))
    u.orders = deque(_order_from_dict(o) for o in d["orders"])
    for state in d.get("worker_orders", []):
        order = u.orders[state["index"]]
        if not isinstance(order, (Harvest, Deposit)):
            raise ValueError("Worker metadata must refer to a harvest or deposit order")
        order.auto = state["auto"]
        if isinstance(order, Deposit):
            order.target = state["target"]
    return u


def _projectile_to_dict(p: Projectile) -> dict[str, Any]:
    d = dict(vars(p))
    d["start"], d["aim"], d["attack"] = list(p.start), list(p.aim), p.attack.value
    return d


def _projectile_from_dict(d: dict[str, Any]) -> Projectile:
    d = {**d, "start": tuple(d["start"]), "aim": tuple(d["aim"])}
    if "siege" in d:  # saved before WB-049, which carried the building multiplier: a stone sieges, an archer's arrow pierces
        siege = d.pop("siege")
        d["attack"] = (AttackType.SIEGE if siege != 1.0 else AttackType.PIERCING if d["source_type"] == UnitType.ARCHER.value
                       else AttackType.NORMAL)
    else:
        d["attack"] = AttackType(d["attack"])
    return Projectile(**d)


def _building_to_dict(b: Building) -> dict[str, Any]:
    return {
        "id": b.id, "type": b.type.value, "player": b.player, "x": b.x, "y": b.y, "hp": b.hp, "progress": b.progress,
        "queue": [t.value for t in b.queue], "train_progress": b.train_progress, "rally": list(b.rally) if b.rally else None,
        "gold": b.gold, "builder": b.builder, "cooldown": b.cooldown,
        "research": b.research.value if b.research else None, "research_progress": b.research_progress, "abandoned": b.abandoned,
        "auto": [t.value for t in b.auto],
    }


def _building_from_dict(d: dict[str, Any], race: Race) -> Building:
    return Building(d["id"], BuildingType(d["type"]), d["player"], d["x"], d["y"], d["hp"], race=race, progress=d["progress"],
                    queue=[UnitType(t) for t in d["queue"]], train_progress=d["train_progress"],
                    rally=tuple(d["rally"]) if d["rally"] else None, gold=d["gold"], builder=d["builder"], cooldown=d["cooldown"],
                    research=Upgrade(d["research"]) if d["research"] else None, research_progress=d["research_progress"],
                    abandoned=d.get("abandoned", False), auto=[UnitType(t) for t in d.get("auto", [])])  # saves from before endless training


# At the end, as it imports this module: the automatic worker policy the simulation consults.
from warband.sim import worker_ai  # noqa: E402
