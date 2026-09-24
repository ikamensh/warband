"""A crowd is never slower than its members one at a time, and bodies never stand inside each other.

Two contracts on how units move together.  **Efficiency:** a group sent through a choke (a gate, a corridor,
idle friends standing in the way, open ground) finishes no later than its members would one after another,
each on its own (the sum of their solo times), and in fact no later than the slowest of them alone plus the
time the whole group takes to file past a point twice over, bodies touching (``queue``).  **The core:** no
walk, shove or slide ever brings a unit's centre nearer another's than :data:`CORE` of their two bodies, so
a crowd is never one overlapping mass (``docs/unit-motion.md`` part 9).

The scenarios are drawn from a seed: the width and depth of the choke, whether there is one at all, the
size and make-up of the group, where it starts and where it is sent, move or attack-move, and friends idling
in the gate.  Every seed held both contracts when they were written; before, the same draws showed
bodies at a fiftieth of their width apart, sixteen knights circling their first waypoint for good, a
marching line three times slower down a corridor than a file of peasants, and groups that stopped on the
wrong side of a wall.  The explicit cases below keep each of those shapes.
"""

import math
import random

import pytest

from warband.sim.model import CORE, World
from warband.brains.ai import make_brain
from warband.sim import mapgen
from warband.sim.rules import MAX_UNIT_RADIUS, SIM_DT, UNITS, Difficulty, Terrain, UnitType

WIDTH, HEIGHT = 48, 32
WALL = 20  # the choke's near face
#: What a group is drawn from: every unit a player trains.  The flyer took the scout rider's place in the list, so each
#: seed draws the group it always drew with a flying machine for the rider: the walkers must go through as fast with
#: one in their midst, and nothing of it holds them up.
KINDS = (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.FLYING_MACHINE, UnitType.KNIGHT, UnitType.CATAPULT,
         UnitType.CLERIC)


class Core:
    """Watches every pair of bodies on the field, every step: a pair outside its core never comes inside it, and a
    pair that came onto the field inside it (spawned on one spot, a trained unit set down, a peasant out of a mine,
    a builder stepping out of its site: every set-down happens while the unit is off the map) only draws apart.
    A flyer has no body on the ground, and none of the core: it is left out of every pair."""

    def __init__(self) -> None:
        self.inside: dict[tuple[int, int], float] = {}
        self.seen: set[int] = set()
        self.pairs = 0

    def look(self, world: World) -> None:
        bodies = sorted((u for u in world.units.values() if not u.hidden and not u.flying), key=lambda u: u.x)
        reach = 2 * CORE * MAX_UNIT_RADIUS
        inside: dict[tuple[int, int], float] = {}
        for i, a in enumerate(bodies):
            for b in bodies[i + 1:]:
                if b.x - a.x >= reach:
                    break
                d = math.dist(a.pos, b.pos)
                core = CORE * (a.radius + b.radius)
                self.pairs += 1
                if d >= core - 1e-9:
                    continue
                key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
                was = self.inside.get(key)
                if was is None and (a.id not in self.seen or b.id not in self.seen):
                    was = d  # set down inside: from here on it may only draw apart
                assert was is not None and d >= was - 1e-9, (
                    f"{a.type.value} {a.id} at {a.pos} and {b.type.value} {b.id} at {b.pos} came {d:.3f} apart, "
                    f"inside their core of {core:.3f}" + ("" if was is None else f" (they were {was:.3f})"))
                inside[key] = d
        self.inside = inside
        self.seen = {u.id for u in bodies}


def field(walls=frozenset()) -> World:
    terrain = [[Terrain.GRASS] * WIDTH for _ in range(HEIGHT)]
    for x, y in walls:
        terrain[y][x] = Terrain.ROCK
    return World(WIDTH, HEIGHT, terrain, 2, rng=random.Random(1))


def choke(width: int, depth: int, low: int) -> frozenset[tuple[int, int]]:
    """A rock wall *depth* tiles thick at x = WALL with *width* tiles open from row *low*: a gate, or a corridor."""
    return frozenset((x, y) for x in range(WALL, WALL + depth) for y in range(HEIGHT) if not low <= y < low + width)


def block(types, at, cols: int, gap: float = 1.4, jitter=None) -> list[tuple[UnitType, tuple[float, float]]]:
    return [(t, (at[0] + (i % cols) * gap + (jitter.uniform(-0.2, 0.2) if jitter else 0.0),
                 at[1] + (i // cols) * gap + (jitter.uniform(-0.2, 0.2) if jitter else 0.0))) for i, t in enumerate(types)]


class Scenario:
    def __init__(self, walls, far: float, group, target, order: str = "move", idle=()) -> None:
        self.walls, self.far, self.group, self.target, self.order, self.idle = walls, far, list(group), target, order, list(idle)

    @classmethod
    def drawn(cls, seed: int) -> "Scenario":
        rng = random.Random(seed)
        width = rng.choice([1, 1, 2, 3])
        depth = rng.choice([0, 1, 1, 3, 8])  # 0 is open ground
        low = rng.randrange(8, HEIGHT - 8 - width)
        walls = choke(width, depth, low) if depth else frozenset()
        far = WALL + max(depth, 1)
        n = rng.randint(3, 12)
        mix = [rng.choice(KINDS)] if rng.random() < 0.5 else rng.sample(KINDS, rng.randint(2, 4))
        cols = rng.randint(2, 5)
        at = (rng.uniform(3, 8), rng.uniform(3, HEIGHT - 3 - (n // cols + 1) * 1.4))
        group = block([rng.choice(mix) for _ in range(n)], at, cols, jitter=rng)
        target = (rng.uniform(far + 3, WIDTH - 3), rng.uniform(3, HEIGHT - 3))
        order = rng.choice(["move", "attack_move"])
        idle = []
        if depth and rng.random() < 0.3:
            idle = [(UnitType.FOOTMAN, (x + 0.5, y + 0.5)) for x in (WALL - 2, WALL - 1, far, far + 1)
                    for y in range(low - 1, low + width + 1) if rng.random() < 0.6 and (x, y) not in walls]
        return cls(walls, far, group, target, order, idle)

    def play(self, group=None, *, core: Core | None = None, limit: float = 240.0) -> tuple[list[float], World, list]:
        """Each unit's time to stand past the choke with its order done (inf if it never did), the world and the units."""
        world = field(self.walls)
        for unit_type, point in self.idle:
            world.spawn_unit(0, unit_type, point)
        units = [world.spawn_unit(0, unit_type, point) for unit_type, point in (self.group if group is None else group)]
        getattr(world, self.order)([u.id for u in units], self.target)
        done: dict[int, float] = {}
        for _ in range(int(limit / SIM_DT)):
            world.step()
            world.take_events()
            if core is not None:
                core.look(world)
            for u in units:
                if u.id not in done and u.x > self.far + 0.5 and not u.orders:
                    done[u.id] = world.time
            if len(done) == len(units):
                break
        return [done.get(u.id, math.inf) for u in units], world, units

    def judge(self) -> None:
        core = Core()
        times, world, units = self.play(core=core)
        stuck = [(u.type.value, round(u.x, 1), round(u.y, 1), u.order) for u, t in zip(units, times) if t == math.inf]
        assert not stuck, f"never got through: {stuck}"
        solos = [self.play([member])[0][0] for member in self.group]
        assert max(solos) < math.inf, "a lone unit that cannot get through is a broken scenario, not a crowd"
        group = max(times)
        assert group <= sum(solos), f"the group took {group:.1f} s, its members one by one {sum(solos):.1f} s"
        pace = min(world.speed_of(u) for u in units)
        queue = sum(2 * u.radius for u in units) / pace  # the group filing past a point, bodies touching
        assert group <= max(solos) + 2 * queue, (
            f"the group took {group:.1f} s: its slowest member alone takes {max(solos):.1f} s, and filing past twice over {2 * queue:.1f} s")
        assert core.pairs > 0 or sum(not u.flying for u in units) < 2  # the watcher leaves flyers out: a flight has no pairs


@pytest.mark.parametrize("seed", range(24))
def test_a_group_is_no_slower_than_its_members_one_by_one(seed):
    Scenario.drawn(seed).judge()


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(24, 160))
def test_many_more_groups_are_no_slower_than_their_members_one_by_one(seed):
    """The same contract over a hundred and thirty-six more draws: half a minute of processor time together,
    the slow tier.  The fast tier's two dozen catch a regression; these are what make a pass worth trusting."""
    Scenario.drawn(seed).judge()


def test_sixteen_knights_do_not_circle_their_first_waypoint():
    """Sixteen knights in a block on open ground share one path.  Four of them used to walk round and round
    its first tile centre, each heading at the middle the others held and sidestepping round them, for as
    long as the order lasted.  A waypoint whose successor is a clear step away counts as passed."""
    Scenario(frozenset(), WALL + 1, block([UnitType.KNIGHT] * 16, (5.0, 8.0), 4, gap=1.3), (35.5, 15.5)).judge()


def test_a_marching_line_files_down_a_corridor_at_walking_pace():
    """Twelve footmen form a marching line, and a unit ahead of its row walks slower until the row catches up.
    Down a one-tile corridor nobody can stand abreast, so the front waited for a row that could never form and
    held the file behind it: 45 s where peasants took 16.  The row now dresses only on open ground."""
    Scenario(choke(1, 10, 14), WALL + 10, block([UnitType.FOOTMAN] * 12, (5.0, 10.0), 4, gap=1.3), (36.5, 14.5)).judge()


def test_a_muster_just_past_a_gate_gathers_on_its_far_side():
    """Sent two tiles past a one-tile gate, twelve footmen pile up at the spot.  A unit held back by the pile
    used to count as arrived by looking along the straight line to the spot, through the rock, and stood
    down on the near side of the wall for good.  Across a wall, the way in is the unit's route."""
    walls = choke(1, 1, 14)
    times, world, units = Scenario(walls, WALL + 1, block([UnitType.FOOTMAN] * 12, (8.0, 10.0), 4, gap=1.3), (22.5, 14.5)).play(limit=60.0)
    assert all(int(u.x) > WALL for u in units), [(round(u.x, 1), round(u.y, 1)) for u in units if int(u.x) <= WALL]
    assert not any(u.orders for u in units)


def test_idle_friends_standing_in_a_gate_let_a_group_through():
    """Friends idle in and around a one-tile gate.  A unit stalled behind them plans again around standing
    units, which found no way (they fill the gate), walked to the nearest tile the search reached and
    ended its order there, on the wrong side of the wall.  It now presses on through, and they make way."""
    walls = choke(1, 1, 14)
    idle = [(UnitType.FOOTMAN, (x + 0.5, y + 0.5)) for x in (18, 19, 20, 21) for y in (13, 14, 15) if (x, y) not in walls]
    Scenario(walls, WALL + 1, block([UnitType.FOOTMAN] * 8, (6.0, 11.0), 4, gap=1.3), (34.5, 14.5), idle=idle).judge()


@pytest.mark.parametrize("pair", [(UnitType.CATAPULT, UnitType.CATAPULT), (UnitType.KNIGHT, UnitType.CATAPULT)])
def test_the_biggest_bodies_pass_each_other_head_on_in_a_one_tile_corridor(pair):
    """The core is as big as it can be while two catapults still squeeze past each other down a one-tile
    corridor: :data:`CORE` of their two bodies is under a tile."""
    assert CORE * 2 * UNITS[UnitType.CATAPULT].radius < 0.9
    world = field(choke(1, 6, 14))
    a = world.spawn_unit(0, pair[0], (12.5, 14.5))
    b = world.spawn_unit(0, pair[1], (34.5, 14.5))
    world.move([a.id], (38.5, 14.5))
    world.move([b.id], (8.5, 14.5))
    core = Core()
    for _ in range(int(30 / SIM_DT)):
        world.step()
        core.look(world)
        if not a.orders and not b.orders:
            break
    assert not a.orders and not b.orders, (a.pos, b.pos)


def test_two_armies_in_melee_never_stand_inside_each_other():
    """The core holds in a brawl too: ten footmen against ten, attack-moving through each other."""
    world = field()
    ours = [world.spawn_unit(0, t, p) for t, p in block([UnitType.FOOTMAN] * 10, (10.0, 12.0), 2, gap=1.0)]
    theirs = [world.spawn_unit(1, t, p) for t, p in block([UnitType.FOOTMAN] * 10, (30.0, 12.0), 2, gap=1.0)]
    world.attack_move([u.id for u in ours], (32.0, 14.0))
    world.attack_move([u.id for u in theirs], (10.0, 14.0))
    core = Core()
    for _ in range(int(25 / SIM_DT)):
        world.step()
        world.take_events()
        core.look(world)
    assert any(u.id not in world.units for u in ours + theirs), "nobody fell: the armies never met"


def test_a_pile_spawned_on_one_spot_only_draws_apart():
    """Twenty-one bodies set down on one point (a rally point, a loaded save) start inside each other's cores;
    no pair of them may come nearer again while they unstack."""
    world = field()
    crowd = [world.spawn_unit(0, unit_type, (20.0, 12.0)) for unit_type in KINDS for _ in range(3)]
    core = Core()
    core.inside = {(a.id, b.id): math.dist(a.pos, b.pos) for i, a in enumerate(crowd) for b in crowd[i + 1:]}
    for _ in range(int(20 / SIM_DT)):
        world.step()
        core.look(world)
    assert not core.inside, f"{len(core.inside)} pairs still inside their core after twenty seconds"


@pytest.mark.slow
@pytest.mark.parametrize("seed", [81, 83])
def test_no_two_bodies_come_inside_each_others_core_in_a_played_match(seed):
    """Five minutes of two brains playing a whole match: training, mining, building, marching and fighting, the
    slow tier.  Every pair of bodies on the map is looked at every step."""
    rng = random.Random(seed)
    world = mapgen.generate(seed=seed, width=64, height=64, players=2, human=None)
    brains = [make_brain(p.id, rng.choice(list(Difficulty)), seed) for p in world.players[:world.seats]]
    core = Core()
    for _ in range(int(300 / SIM_DT)):
        for brain in brains:
            brain.think(world, world.rng)
        world.step()
        world.take_events()
        core.look(world)
    assert len(world.units) > 20, "a match with a handful of units would pass without testing the crowd"
