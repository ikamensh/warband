"""A soldier sent to a spot the army is already standing on.

Fuzz seed 92 (four players, 80×64, minute 11) on 2026-09-21: footman 164 of player 3 was sent to a muster
post a knight was standing on, a tile and a bit away, and was still a tile and a bit away twenty seconds
later.  Its brain let go of the order at one distance and sent it after the post again at another, twice a
second, so the footman shuffled on the spot for the rest of the match.  The ground there is open grass; the
crowd was the whole of the obstacle, which is why a Move to it could never finish.
"""

import random

from warband.brains.ai import make_brain
from warband.sim.model import ARRIVE, SIM_DT, Unit, World, dist
from warband.sim.rules import BuildingType, Difficulty, Race, Terrain, UnitType

# The neighbourhood as the seed left it: the six buildings whose ground comes within five tiles of the
# spot, and every unit standing within five tiles of it.  Positions are the seed's own, absolute on the
# 80×64 map; there is no rock, water or tree within six tiles, so only the bodies are in the way.
BUILDINGS = [
    (BuildingType.LUMBER_MILL, (8, 45)),
    (BuildingType.FARM, (12, 46)),
    (BuildingType.FARM, (15, 46)),
    (BuildingType.BARRACKS, (8, 49)),
    (BuildingType.TOWER, (16, 49)),
    (BuildingType.FARM, (11, 53)),
]
CROWD = [
    (UnitType.KNIGHT, (11.350418448588012, 49.44020130545803)),      # standing on the spot itself
    (UnitType.FOOTMAN, (12.431161475340636, 49.427108788749464)),
    (UnitType.FOOTMAN, (11.880455175110868, 50.20087894107082)),
    (UnitType.KNIGHT, (11.395641518058156, 48.30499514421677)),
    (UnitType.KNIGHT, (12.517106529342497, 48.4822948117109)),
    (UnitType.KNIGHT, (12.832766097904313, 50.29052248782467)),
    (UnitType.FOOTMAN, (13.258379349907052, 49.34048507726955)),
    (UnitType.KNIGHT, (11.001550869223648, 50.573981063138355)),
    (UnitType.ARCHER, (11.867999638989714, 51.01685408390474)),
    (UnitType.FOOTMAN, (13.312368092935278, 48.006455359988685)),
    (UnitType.ARCHER, (13.827640062388612, 49.95025528655091)),
    (UnitType.FOOTMAN, (13.838150419694028, 48.6328246980231)),
    (UnitType.ARCHER, (13.17442135298944, 51.13440621882923)),
    (UnitType.FOOTMAN, (11.0003465472819, 51.64048102223486)),
    (UnitType.FOOTMAN, (12.587716865555869, 51.752882978021276)),
    (UnitType.FOOTMAN, (13.912269376091153, 50.77462002711684)),
    (UnitType.FOOTMAN, (11.777550461598205, 51.882794330133706)),
    (UnitType.ARCHER, (14.716984243206868, 48.868006390389645)),
    (UnitType.FOOTMAN, (14.738267956800119, 49.704771798118465)),
    (UnitType.KNIGHT, (13.49822987867921, 51.95046008849608)),
    (UnitType.KNIGHT, (14.630851622548688, 51.31977283073492)),
    (UnitType.KNIGHT, (9.602431756459785, 52.001277241679816)),
    (UnitType.ARCHER, (12.45213976113332, 52.74890422363367)),
    (UnitType.KNIGHT, (11.521299921121171, 52.9966303112164)),
    (UnitType.ARCHER, (15.3507244104775, 50.6060978028474)),
    (UnitType.ARCHER, (13.19911772019588, 52.849467542348265)),
    (UnitType.FOOTMAN, (15.649126610184316, 49.10834172985035)),
    (UnitType.ARCHER, (14.390093631422458, 52.21442197011314)),
    (UnitType.ARCHER, (15.999518244733908, 49.86495898421507)),
    (UnitType.ARCHER, (13.991947536324478, 53.03756355715995)),
    (UnitType.KNIGHT, (13.000318173565303, 53.758430232379055)),
    (UnitType.ARCHER, (9.617835661328419, 53.36161654181232)),
    (UnitType.ARCHER, (14.698099037391323, 52.912459183631974)),
]
STALLED = (10.685283684897035, 48.848182978959784)  # the footman, where twenty seconds of shuffling left it
SPOT = (11.809144736654323, 49.31414914384108)  # its place around the muster point, as its brain works it out
PLAYER = 3  # the orcs of that game; every unit here is theirs


def muster(*, garrison: bool = False) -> tuple[World, Unit]:
    """The seed's crowd, with the stalled footman the last to arrive.  With *garrison*, the hall it was
    posted in front of and an enemy hall to face, which is what a brain needs to work its muster out."""
    world = World(80, 64, [[Terrain.GRASS] * 80 for _ in range(64)], 4,
                  human=None, races=(Race.HUMAN, Race.ELF, Race.DWARF, Race.ORC))
    for building_type, pos in BUILDINGS:
        world.place_building(PLAYER, building_type, pos)
    if garrison:
        world.place_building(PLAYER, BuildingType.TOWN_HALL, (7, 54))
        world.place_building(PLAYER, BuildingType.STABLES, (4, 49))
        world.place_building(0, BuildingType.TOWN_HALL, (70, 8))
    for unit_type, pos in CROWD:
        world.spawn_unit(PLAYER, unit_type, pos)
    return world, world.spawn_unit(PLAYER, UnitType.FOOTMAN, STALLED)


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_every_soldier_of_an_army_sent_to_one_coordinate_ends_its_walk() -> None:
    """A muster point is one coordinate and a coordinate holds one body, so most of an army sent to one can
    never arrive.  Until the walk ended on the bodies in the way rather than on a distance of the unit's
    own, three of these thirty-four knights held a Move they could not finish for the rest of the match,
    standing in the crowd within a tile and a half of the spot, taking no further part in the game."""
    world, footman = muster()
    army = list(world.units.values())
    world.move([u.id for u in army], SPOT)
    run(world, 15.0)
    holding = [(u.id, u.type.value, round(dist(u.pos, SPOT), 2)) for u in army if u.orders]
    assert not holding, holding
    assert dist(footman.pos, SPOT) < 2.0, footman.pos  # they crowd around the spot, not give up on the way


def test_no_soldier_of_a_mustering_army_is_ordered_about_without_getting_anywhere() -> None:
    """The livelock fuzz caught.  The brain let go of a Move within 1.5 tiles of its target and sent the
    soldier after its post again beyond 1.0 of it, so a soldier the crowd held in between was cancelled and
    re-ordered twice a second: it walked two ticks, was released, drifted back eight, and was sent again,
    for the four minutes that match had left.  Both sides ask the world now, so there is one answer.

    Under the seed's own brain this crowd churned two of its thirty-four soldiers that way: six orders in
    forty seconds and a quarter of a tile walked between them.
    """
    world, _ = muster(garrison=True)
    for i in range(5):  # peasants, so the brain has an economy to think about rather than a recovery
        world.spawn_unit(PLAYER, UnitType.PEASANT, (6.5 + i, 58.5))
    world.players[PLAYER].gold = world.players[PLAYER].lumber = 2000
    brain, rng = make_brain(PLAYER, Difficulty.GRANDMASTER, 92), random.Random(92)

    army = [u for u in world.units.values() if not u.is_worker]
    start = {u.id: u.pos for u in army}
    ordered: dict[int, int] = dict.fromkeys(start, 0)
    last: dict[int, object] = dict.fromkeys(start)
    for _ in range(round(40.0 / SIM_DT)):
        brain.think(world, rng)
        for unit in army:
            if unit.orders and unit.orders[0] is not last[unit.id]:
                ordered[unit.id], last[unit.id] = ordered[unit.id] + 1, unit.orders[0]
        world.step()
        world.take_events()
    churning = [(u.id, u.type.value, ordered[u.id], round(dist(start[u.id], u.pos), 2))
                for u in army if ordered[u.id] > 1 and dist(start[u.id], u.pos) < 1.0]
    assert not churning, churning


def test_a_soldier_walks_the_last_stride_to_a_spot_nobody_is_standing_on() -> None:
    """The same distance over open ground: arriving still means the point itself, not a tolerance round it."""
    world = World(80, 64, [[Terrain.GRASS] * 80 for _ in range(64)], 4,
                  human=None, races=(Race.HUMAN, Race.ELF, Race.DWARF, Race.ORC))
    footman = world.spawn_unit(PLAYER, UnitType.FOOTMAN, STALLED)
    assert not world.stands_at(footman, SPOT), "an empty spot a stride away is somewhere to walk to"
    world.move([footman.id], SPOT)
    run(world, 5.0)
    assert dist(footman.pos, SPOT) <= ARRIVE, footman.pos
    assert not footman.orders and footman.state == "idle"
