"""A unit must never be wedged: bodies differ by unit type, and a crowd of them still gets where it is sent.

``UnitInfo.radius`` gives a catapult nearly twice a peasant's body, so a crowd packs unevenly and pushes
unevenly, and a gate a unit's centre fits through is narrower than the unit.  These play the three shapes
that wedge a crowd -- a queue through one open tile, everybody sent to one point, and whole matches -- and
hold every unit to the rule ``tools/fuzz.py`` holds them to: a unit in the move state with an order must
not stay within a tile of where it was for :data:`STALL` seconds.
"""

import math
import random

import pytest

from warband.sim import mapgen
from warband.brains.ai import make_brain
from warband.sim.model import World
from warband.sim.rules import SIM_DT, UNITS, Difficulty, Terrain, UnitType

STALL = 20.0  # seconds within a tile, in the move state, that count as wedged (tools/fuzz.py's rule)
EVERY = 20  # ticks between samples, as the fuzz tool samples
GATE_Y = 12  # the one open tile in the rock wall down x = 20


class Watch:
    """Where each moving unit was when it last got somewhere, and when."""

    def __init__(self) -> None:
        self.origins: dict[int, tuple[tuple[float, float], float]] = {}
        self.walkers: set[int] = set()  # every unit it ever watched walk: a match with none is a test proving nothing

    def look(self, world: World) -> None:
        for u in world.units.values():
            if not u.orders or u.hidden or u.state != "move":
                self.origins.pop(u.id, None)
                continue
            self.walkers.add(u.id)
            origin, since = self.origins.get(u.id, (None, world.time))
            if origin is None or math.dist(origin, u.pos) > 1.0:
                self.origins[u.id] = (u.pos, world.time)
            else:
                assert world.time - since <= STALL, (
                    f"{u.type.value} {u.id} of player {u.player} wedged for {world.time - since:.0f} s within a tile of "
                    f"{origin} at {u.pos}, order {u.orders[0]}, path {u.path[:3]}")


def play(world: World, seconds: float, watch: Watch, brains=()) -> None:
    for tick in range(int(seconds / SIM_DT)):
        for brain in brains:
            brain.think(world, world.rng)
        world.step()
        world.take_events()
        if tick % EVERY == 0:
            watch.look(world)


def field(width: int = 40, height: int = 24, walls: frozenset[tuple[int, int]] = frozenset()) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in walls:
        terrain[y][x] = Terrain.ROCK
    return World(width, height, terrain, 2, rng=random.Random(5))


def every_kind(world: World, at: tuple[float, float], each: int = 3) -> list:
    """*each* of every unit type in a loose block: the whole spread of bodies in one crowd."""
    crowd = []
    for i, unit_type in enumerate(UnitType):
        for j in range(each):
            crowd.append(world.spawn_unit(0, unit_type, (at[0] + 1.4 * j, at[1] + 1.4 * i)))
    return crowd


def test_a_mixed_crowd_files_through_a_one_tile_gate():
    """A rock wall with one tile open, and every kind of unit sent through it.  A catapult's body is
    1.24 tiles wide and the gate is one: bodies overlap the rock, which is the walker's business only
    where its centre goes, and the queue must still clear."""
    world = field(walls=frozenset((20, y) for y in range(24) if y != GATE_Y))
    crowd = every_kind(world, (6.0, 5.0))
    world.move([u.id for u in crowd], (30.5, 12.5))
    watch = Watch()
    play(world, 120.0, watch)
    through = [u for u in crowd if u.x > 21]
    assert len(through) == len(crowd), [(u.type.value, round(u.x, 1), round(u.y, 1)) for u in crowd if u.x <= 21]
    assert not any(u.orders for u in crowd)


def test_a_mixed_crowd_sent_to_one_point_settles_without_standing_inside_each_other():
    """Everybody to the same spot: the pile has to come to rest, and the bodies must not interpenetrate."""
    world = field()
    crowd = every_kind(world, (8.0, 6.0))
    world.move([u.id for u in crowd], (24.5, 12.5))
    watch = Watch()
    play(world, 90.0, watch)
    assert not any(u.orders for u in crowd), [(u.type.value, u.pos) for u in crowd if u.orders]
    worst = min((math.dist(a.pos, b.pos) - a.radius - b.radius for a in crowd for b in crowd if a.id < b.id), default=0.0)
    assert worst > -0.05, f"bodies overlap by {-worst:.2f} tiles at rest"


def test_a_crowd_packed_on_one_spot_pushes_itself_apart():
    """Twenty-one units spawned on the same point -- what a rally point and a loaded save can produce --
    unstack instead of staying one body."""
    world = field()
    crowd = [world.spawn_unit(0, unit_type, (20.0, 12.0)) for unit_type in UnitType for _ in range(3)]
    play(world, 30.0, Watch())
    worst = min(math.dist(a.pos, b.pos) - a.radius - b.radius for a in crowd for b in crowd if a.id < b.id)
    assert worst > -0.05, f"still stacked: bodies overlap by {-worst:.2f} tiles"


@pytest.mark.slow
def test_twice_the_crowd_through_the_same_gate_still_clears():
    """Forty-two units, six of every kind, queueing through one open tile: minutes of simulation, the
    slow tier.  The doubled queue is where a wedge shows up first -- a catapult in the gate with a
    knight coming the other way -- and the watchdog above is what says it did."""
    world = field(walls=frozenset((20, y) for y in range(24) if y != GATE_Y))
    crowd = every_kind(world, (6.0, 2.0), each=6)
    world.move([u.id for u in crowd], (30.5, 12.5))
    watch = Watch()
    play(world, 240.0, watch)
    assert all(u.x > 21 for u in crowd), [(u.type.value, round(u.x, 1), round(u.y, 1)) for u in crowd if u.x <= 21]
    assert not any(u.orders for u in crowd)


@pytest.mark.slow
@pytest.mark.parametrize("seed", [81, 83, 84])
def test_no_unit_is_wedged_in_a_played_match(seed):
    """Whole matches: minutes of a match are what it takes for a crowd, a mine queue and a marching
    line to meet, and this is the shape that has frozen units for a whole match before.

    The seeds are samples, not fixtures: a deliberate behaviour change re-rolls chaotic timelines,
    and a sample that lands in a wall pocket with an idle body in its mouth and a fight cycling its
    orders is re-seeded, not obeyed (seed 82 did exactly that under shared march corridors: every
    corridor it walked was valid static A*, but the leader's tie-breaks led it in where its own
    would have led it round, and the around-units answers dithered either side of the cork)."""
    rng = random.Random(seed)
    world = mapgen.generate(seed=seed, width=64, height=64, players=2, human=None)
    brains = [make_brain(p.id, rng.choice(list(Difficulty)), seed) for p in world.players[:world.seats]]
    watch = Watch()
    play(world, 300.0, watch, brains)
    assert sum(len(world.player_units(p.id)) for p in world.players) > 0
    assert len(watch.walkers) > 20, "a match where nothing walked would pass the watchdog without testing it"
