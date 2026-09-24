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
from warband.sim.model import AttackMove, Move, World
from warband.sim.rules import SIM_DT, UNITS, BuildingType, Difficulty, Race, Terrain, UnitType

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
    worst = min((math.dist(a.pos, b.pos) - a.radius - b.radius for a in crowd for b in crowd if a.id < b.id and a.flying == b.flying),
                default=0.0)  # a flyer overhead takes no room on the ground; flyers keep theirs from each other
    assert worst > -0.05, f"bodies overlap by {-worst:.2f} tiles at rest"


def test_a_crowd_packed_on_one_spot_pushes_itself_apart():
    """Twenty-one units spawned on the same point -- what a rally point and a loaded save can produce --
    unstack instead of staying one body."""
    world = field()
    crowd = [world.spawn_unit(0, unit_type, (20.0, 12.0)) for unit_type in UnitType for _ in range(3)]
    play(world, 30.0, Watch())
    worst = min(math.dist(a.pos, b.pos) - a.radius - b.radius for a in crowd for b in crowd if a.id < b.id and a.flying == b.flying)
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


def test_attackers_held_out_of_reach_by_their_own_crowd_wait_their_turn_instead_of_pressing_into_it():
    """Fuzz seed 81 at 8 min 46 s (180×132): seven archers sent at a barracks across a band of trees, where the one
    tile on their side from which it is in reach is the nearest their route can end (the barracks' side of the trees is
    another region).  The first archers on it shoot; the rest pressed towards it through them in the move state for as
    long as the barracks stood, which the fuzz watchdog reads as a wedged unit.  They wait their turn now, and try the
    way in again after a while.  The seed's tiles cut out round the choke opened a way round the trees that the whole
    map closes, so this is the choke itself: the trees, the barracks and the one tile of the seed."""
    terrain = [[Terrain.GRASS] * 30 for _ in range(20)]
    for y in range(20):
        for x in range(9, 14):
            if (x, y) != (9, 9):  # the one tile in reach
                terrain[y][x] = Terrain.TREES
    world = World(30, 20, terrain, 2)
    for player in world.players[:world.seats]:
        player.human = True
    barracks = world.place_building(1, BuildingType.BARRACKS, (14, 8))
    archers = [world.spawn_unit(0, UnitType.ARCHER, (3.5 + (i % 3) * 0.9, 7.5 + (i // 3) * 0.9)) for i in range(7)]
    world.reveal_all(0)
    world.attack([u.id for u in archers], barracks.id)
    pressing = {u.id: 0.0 for u in archers}
    worst = 0.0
    for _ in range(round(90.0 / SIM_DT)):
        world.step()
        for u in archers:
            pressing[u.id] = pressing[u.id] + SIM_DT if u.state == "move" else 0.0
            worst = max(worst, pressing[u.id])
    assert worst < 15.0, f"an archer pressed into its own crowd for {worst:.1f} s"
    assert barracks.hp < barracks.max_hp / 2, "the ones in reach shoot, and take turns"


# Fuzz seed 81 (six players, 180×132) on main as it was at 07cb63d, 405 to 410 s in: a Grandmaster army of dwarves
# (player 2 there) had chased a raider along the one-tile passage at row 6, between a barracks going up at (121, 3)
# and the trees below it.  The soldiers that got there were walking home and the rest were still on their way out,
# both ways through the passage at once, and a few had been pushed down the notch at (121, 7), a dead end one tile
# across.  The ground is the seed's from x = 110 and y = 0, a building's tiles as rock; at each moment every soldier
# stands where the seed had it, facing its way, holding its order (a group order's pace and slot are state the seed
# left, not an order, so they are set as they were).
NOTCH_WINDOW = (110, 0)
NOTCH_GROUND = (
    "ttttttttttttttttttgggggrrggggg", "ttgggttttttggggggtgggggrrggggg", "ttgggttttttggggtttggggggggrrrg", "gggggggttttrrrgtgtrrrggrrgrrrg",
    "gggggggttttrrrggggrrrggrrgrrrg", "gggggggggggrrrtgggrrrggggggggg", "gggggggggggggggggggggggggggggg", "ttttggggtttgtggggggggggrrrgrrg",
    "ttttggggtttttgtrrgrrrggrrrgrrg", "ttttggggtttttgtrrgrrrggrrrgggg", "ttttggggttttggtgggrrrggggggrrg", "trttwggttttgggttgggggggggggrrg",
    "ttttwgggtttgrrrtgggggggrrggggg", "tttggggttttgrrrggggggggrrgrrrg", "tttggggtttttrrrrgggwwgggggrrrg", "tttggggtttttgggrgggggwwrrgrrrg",
    "ttggggggttttgggrrrgrrggrrggggt", "ggggggggttttggggrrgrrggggggggg", "grggttttttttgggggggggggggggggg",
)
NOTCH_ARMY = {
    405.0: [
        (UnitType.FOOTMAN, (121.68903995468, 6.035277673311853), 2.2477591131186916, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (118.56540737725976, 5.565407377259755), -0.7547789556014446, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.FOOTMAN, (119.70501309145534, 5.8755487132510735), 0.754993028752353, Move((133.42586930464364, 11.744986452490018))),
        (UnitType.FOOTMAN, (123.30412831184483, 6.021205136028691), 2.6900114411350415,
         AttackMove((121.13515931207587, 6.724483699525185), pace=1.45, offset=(0.20030500875270035, -0.4581243318888232))),
        (UnitType.FOOTMAN, (119.17257953347449, 6.704935798812876), -0.18488045418009913, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (121.1920928991784, 6.508183186103031), -0.006256621223195671, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (124.17113903267827, 6.969787496947467), 1.1068152364402497, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (121.00235190320223, 7.810748549748448), -0.9937997041170923, Move((129.5, 13.5))),
        (UnitType.FOOTMAN, (120.50836665289415, 5.827939495258431), 0.8660289335365672, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (122.9992730237984, 6.635745007273938), -2.9627870099159574, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (121.9833980863028, 7.350191711449146), -2.0877889398545575, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (124.05607584010626, 7.94887023441519), -1.1527571435875745, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (118.38739234758953, 6.94825174730331), -0.2758420212103689, AttackMove((119.12058696244277, 6.761987567448734), pace=1.45)),
        (UnitType.CATAPULT, (125.08691453276147, 5.699793706681119), 1.0240112421752183, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (120.57729148444292, 6.994675961423739), -0.49211887027053797, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (119.79329587252543, 6.997299031023762), -0.6129241249262297, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CLERIC, (121.48047358873248, 7.099622597955433), -1.538243328488309, Move((128.5, 11.5))),
        (UnitType.CATAPULT, (122.41649631172663, 6.007148531973607), 2.6332570021889907, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (125.0219589317869, 6.424890093309843), 3.1204370750375556, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (121.76316803160073, 7.999996584794263), -1.744474468776355, Move((131.5, 14.5))),  # 938, the one fuzz reported
        (UnitType.CLERIC, (120.2155627300141, 6.445024882811716), 0.03760480821729573, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CATAPULT, (127.50583191201311, 8.059504111899207), -1.5812193079623582, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (124.05017209096398, 6.083336129002335), 2.493093873482321, AttackMove((120.83047646502041, 6.949252930598359), pace=1.85)),
        (UnitType.CLERIC, (130.82779309329032, 13.24498645249002), -0.1465370016088272, None),
    ],
    406.0: [
        (UnitType.FOOTMAN, (121.66360541609362, 6.004088856641201), 0.5351938742131069, Move((131.5, 14.5))),
        (UnitType.FOOTMAN, (118.29642792554395, 6.424175251464226), 0.11924986615921328, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.FOOTMAN, (119.85152905435757, 6.186687729752838), 1.3599001540053148, Move((133.42586930464364, 11.744986452490018))),
        (UnitType.FOOTMAN, (123.0418098719264, 6.32788181221158), 2.81774044769598,
         AttackMove((121.13515931207587, 6.724483699525185), pace=1.45, offset=(0.20030500875270035, -0.4581243318888232))),
        (UnitType.FOOTMAN, (119.3430352320707, 6.481946993275755), 0.015602499118121452, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (121.1920928991784, 6.508183186103031), -0.006256621223195671, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (126.33216922969278, 7.560652581593801), -0.053812856942830695, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (121.03989537652474, 7.697452924442023), -1.2039529558944526, Move((129.5, 13.5))),
        (UnitType.FOOTMAN, (119.11999777054717, 5.9286335197625935), 0.41002778941724904, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (122.60983835500355, 6.860795134026077), -3.0513986484576723, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (121.9833980863028, 7.350191711449146), -2.0877889398545575, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (127.51899006243339, 7.765778350990202), -0.24701970908511062, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (118.84645345095105, 6.95523605363952), -0.4848288085707645, AttackMove((119.12058696244277, 6.761987567448734), pace=1.45)),
        (UnitType.CATAPULT, (124.46869121547903, 6.158290237179487), 2.421174565629846, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (120.57729148444292, 6.994675961423739), -0.49211887027053797, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (119.79320652092741, 6.999577953216421), -0.6152905581327809, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CLERIC, (121.48047358873248, 7.099622597955433), -1.538243328488309, Move((128.5, 11.5))),
        (UnitType.CATAPULT, (122.39159636140775, 6.000457942069233), 2.6188171381606185, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (123.805733164809, 6.536587365303555), -3.1188021481278647, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (121.76316803160073, 7.999996584794263), -1.744474468776355, Move((131.5, 14.5))),  # 938, the one fuzz reported
        (UnitType.CLERIC, (120.40215016317235, 6.360412989476301), 0.2649222462481149, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CATAPULT, (127.31553317585704, 6.554657524948815), -3.0583965760987164, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (123.56475799315994, 6.000233968140163), 2.7027474635181505, AttackMove((120.83047646502041, 6.949252930598359), pace=1.85)),
        (UnitType.CLERIC, (130.82779309329032, 13.24498645249002), -0.1465370016088272, None),
    ],
    410.0: [
        (UnitType.FOOTMAN, (121.66360541609362, 6.004088856641201), 0.5351938742131069, Move((131.5, 14.5))),
        (UnitType.FOOTMAN, (118.4975499083742, 6.288703867187263), 0.2504833432893588, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.FOOTMAN, (119.17046452248519, 6.729087252194039), -0.21486137348054085, Move((133.42586930464364, 11.744986452490018))),
        (UnitType.FOOTMAN, (126.235492901528, 7.925584385671622), -0.39042128990814895, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.FOOTMAN, (119.97825905228399, 6.337218247370593), 0.3017586133898835, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (121.18621827021366, 6.497074180716429), 0.0022270171522902585, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (131.81176577288176, 11.516909926939089), -0.2981639059549308, None),
        (UnitType.KNIGHT, (121.07749636443789, 7.694522962255405), -1.230828461137656, Move((129.5, 13.5))),
        (UnitType.FOOTMAN, (118.55379599618742, 6.874007529917736), -0.34934133347279245, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (125.28863596344404, 7.82183133762124), -0.24240337102568377, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.FOOTMAN, (121.99951425045899, 7.318390060792867), -2.118800177227475, Move((131.82779309329032, 11.512935644921143))),
        (UnitType.KNIGHT, (132.4405385356067, 12.44375663101439), 1.337679758635926, None),
        (UnitType.KNIGHT, (119.21325091711842, 6.044422864019592), 0.3694649137230538, Move((128.5, 11.5))),
        (UnitType.CATAPULT, (123.80948856881889, 6.088755550778452), 2.81358267812252, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.KNIGHT, (120.58476523213318, 6.999976003126887), -0.4999839870546468, Move((129.82779309329032, 13.24498645249002))),
        (UnitType.KNIGHT, (119.80076524095648, 6.999858381184142), -0.6206328911450836, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CLERIC, (121.49236442788451, 7.080905203459453), -1.5576528183900016, Move((128.5, 11.5))),
        (UnitType.CATAPULT, (122.37635995404744, 6.176637288401178), 2.0714281768798717, Move((130.82779309329032, 12.24498645249002))),
        (UnitType.FOOTMAN, (127.04628966538439, 7.9151239813843794), -0.5985073979964315, Move((128.5, 13.5))),
        (UnitType.KNIGHT, (121.80871491573609, 7.977322237780225), -1.7768010999710466, Move((131.5, 14.5))),  # 938, the one fuzz reported
        (UnitType.CLERIC, (120.52797717511896, 6.230400714040182), 0.2601754135022775, Move((132.5598439008592, 14.24498645249002))),
        (UnitType.CATAPULT, (124.89680220186366, 6.018809160500628), 2.8785978370546172, AttackMove((121.13515931207587, 6.724483699525185), pace=1.45)),
        (UnitType.FOOTMAN, (123.0855314753518, 6.012138797919291), 2.4469367234152135, AttackMove((120.83047646502041, 6.949252930598359), pace=1.85)),
        (UnitType.CLERIC, (130.82779309329032, 13.24498645249002), -0.1465370016088272, None),
    ],
}


@pytest.mark.parametrize("moment", sorted(NOTCH_ARMY))
def test_an_army_going_both_ways_past_a_notch_off_a_one_tile_passage_gets_home(moment):
    """Knight 938 stood 20 s at the bottom of the notch, holding a Move home whose path was the passage.

    With no brain to re-order anybody, the jam of 405 s left four soldiers wedged for good once the rest had gone: a
    footman in the passage heading east, and a knight at the notch's mouth heading out past it, their centres exactly
    their core apart.  Each step the footman slid a stride round the knight's core and the crowd step put it back to
    the float, because a walker steps to its right so that two meeting head-on pass, and the knight was on its right.
    A walker that is going nowhere no longer steps into a body on that side.  Going nowhere had to mean it: the
    progress watchdog restarted at every plan round the crowd, so a soldier stuck for seconds read as getting
    somewhere most of the time.  Either half alone fails at 410 s: without the step, twelve soldiers wedge in the
    passage for good; without the watchdog, the notch stands still for 29 s.
    """
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    ground = [[Terrain.GRASS] * 140 for _ in range(len(NOTCH_GROUND))]
    for dy, row in enumerate(NOTCH_GROUND):
        for dx, letter in enumerate(row):
            ground[NOTCH_WINDOW[1] + dy][NOTCH_WINDOW[0] + dx] = letters[letter]
    world = World(140, len(NOTCH_GROUND), ground, 2, human=None, races=(Race.DWARF, Race.HUMAN))
    army = []
    for unit_type, pos, facing, order in NOTCH_ARMY[moment]:
        soldier = world.spawn_unit(0, unit_type, pos)
        soldier.facing = facing
        if order is not None:
            (world.move if isinstance(order, Move) else world.attack_move)([soldier.id], order.target)
            soldier.orders[0] = order
        army.append(soldier)
    watch = Watch()
    play(world, 40.0, watch)
    assert len(watch.walkers) > 20, "a jam where nothing walked would pass the watchdog without testing it"
    assert not any(u.orders for u in army), [(u.type.value, round(u.x, 2), round(u.y, 2)) for u in army if u.orders]
