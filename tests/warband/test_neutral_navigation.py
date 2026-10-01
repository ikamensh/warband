"""Exact fuzz geometries keep encounter avoidance from trapping ordinary marches."""

import random

import pytest

from warband.sim import camps
from warband.sim.model import World, dist, rect_gap
from warband.sim.rules import CAMP_WATCH, BuildingType, Race, Terrain, UnitType


@pytest.mark.parametrize("visible_guards", [False, True], ids=["no-warning-control", "observed-guard-warning"])
def test_a_march_can_leave_an_unremembered_guards_warning_and_continue(visible_guards: bool) -> None:
    """Seed82: the broad warning around partially observed guards prematurely ended a far march near its start.

    This retains the captured terrain/positions, with only the two buildings needed to see both guards.
    Removing the warning is the control: the same footman can cross this forest without a neutral fight.
    """
    rows = (
        "ttggggggggggggtttttttttttttttt",
        "tggggggggggggggttttttttttttttt",
        "tgggggggggggggggtttttttttttttt",
        "gggggggggggggggggttggggggggttt",
        "gggggggggggggggggttwwwwwwwwwww",
        "gggggggggggggggggtttwwwwwwwwww",
        "ggggggggggggggggttttwwwwgggwww",
        "gggggggggggggggggtttttggggggww",
        "gggggggggggggggggtttttgggggggw",
        "gggggggggggggggggtttttgggggggw",
        "gggggggggggggggttttttttggggggw",
        "gggggggggggggggtttttttttttgggw",
        "gggggggggggggggttttrrtttttgggg",
        "ggggggggggggggtttttrrgggtggggg",
        "ggggggggggggggttttgggggggggggg",
        "ggggggggggggttttttgggggggggggg",
        "tggggggggggttttttggggggggggggg",
        "tttttgggggttttttgggggggggggggg",
        "tttttgggggttttgggggggggggggggg",
        "tttgwttgggttgggggggrwggggggttt",
        "tttgwwwttggggggggggwwwgggggttt",
        "tgtgwwwttggggggggggwwwgggggttt",
        "tgtggwwtttgggggggggwwwggggggtt",
        "tttggggggggggttggggwwgggrggggg",
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(30, 24, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.ELF, Race.HUMAN], rng=random.Random(82), scripted=True, magic=True)
    world.place_building(0, BuildingType.TOWER, (8, 15))
    world.place_building(0, BuildingType.MAGE_TOWER, (7, 18))
    if visible_guards:
        camp = camps.place(world, (20, 15), [UnitType.SPIDER, UnitType.WOLF], 1500)
        # Fixture placement retains the two surviving guards' exact captured positions and home posts.
        camp.posts = [(18.375860616707566, 16.6386064438633), (20.330627244803253, 14.61803681260735)]
        for uid, post in zip(camp.guards, camp.posts):
            world.units[uid].x, world.units[uid].y = post
    else:
        world.place_building(world.neutral, BuildingType.LAIR, (20, 15))
    origin = (16.64495384175752, 8.059738212962422)
    footman = world.spawn_unit(0, UnitType.FOOTMAN, origin)
    world.update_vision()
    if visible_guards:
        assert all(world.is_visible(0, world.units[uid].tile) for uid in camp.guards)
        assert camp.lair not in world.worker_knowledge[0].buildings
    world.attack_move([footman.id], (29.5, 23.5))
    for _ in range(300):
        world.step()
    assert dist(origin, footman.pos) > 5.0, (footman.pos, footman.order)


@pytest.mark.parametrize("march", ["move", "attack_move"])
def test_a_queued_expedition_keeps_the_current_march_outside_the_camp(march: str) -> None:
    """Queueing a later camp attack must not opt the current ordinary march into that fight."""
    world = World(30, 24, [[Terrain.GRASS] * 30 for _ in range(24)], 2,
                  rng=random.Random(11), scripted=True)
    camp = camps.place(world, (13, 10), [UnitType.WOLF], 1200)
    archer = world.spawn_unit(0, UnitType.ARCHER, (3.5, 11.5))
    destination = (25.5, 11.5)
    world.reveal_all(0)
    if march == "move":
        world.move([archer.id], destination)
    else:
        world.attack_move([archer.id], destination)
    first_march = archer.order
    world.attack([archer.id], camp.guards[0], queue=True)

    for _ in range(800):
        world.step()
        if first_march not in archer.orders:
            break
        assert not camp.roused, "a later expedition must not expose the current march"
        assert not world.to_dict()["camps"][0]["credit"], "a later expedition must not trigger early combat"
    else:
        pytest.fail("the first march never reached its destination")
    assert dist(archer.pos, destination) < 1.0

    for _ in range(300):
        world.step()
        if world.to_dict()["camps"][0]["credit"]:
            break
    assert world.to_dict()["camps"][0]["credit"], "the queued explicit expedition must still fight afterward"


def test_a_manual_mining_order_uses_the_bypass_around_a_remembered_camp() -> None:
    """Choosing a safe mine beyond a camp is a work order; its worker must route around the whole watch."""
    world = World(34, 24, [[Terrain.GRASS] * 34 for _ in range(24)], 2,
                  rng=random.Random(11), scripted=True)
    camp = camps.place(world, (13, 10), [UnitType.WOLF], 1200)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (27, 10))
    worker = world.spawn_unit(0, UnitType.PEASANT, (3.5, 11.5))
    world.reveal_all(0)
    world.harvest([worker.id], mine.id)

    for _ in range(800):
        world.step()
        assert not camp.roused, "choosing a safe mine must not order an incidental camp fight"
        assert worker.id in world.units
        if worker.inside == mine.id:
            break
    else:
        pytest.fail("the manual miner never reached the safe mine")


def test_a_completed_farm_exits_its_builder_outside_a_remembered_watch() -> None:
    """Seed1003 Bastion: farm1850's front exit put builder1641 in camp23's avoided margin.

    These are the captured tiles at x35..50/y31..47, translated by (35,31).
    The captured builder stood at (43,37) inside the farm at (42,36).
    A safe physical east/north exit exists; finishing construction must use it.
    """
    rows = (
        "gggggggggggggggg",
        "gggggggggggggggg",
        "gggggggggggggggg",
        "gggggggggggggggg",
        "gggggggrrggggggg",
        "ggggggggggtggggg",
        "gggtttgggttggggg",
        "gtgggggggtgggggg",
        "tggggggggtgggggg",
        "gggggggggtgggggg",
        "gggggggggtgggggg",
        "gggggggwwttggggg",
        "gggggggwwwtggggg",
        "tggggggttttggggg",
        "ttgggggggttttggg",
        "ttttttgggttttggg",
        "tttttttttttttttg",
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(16, 17, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.DWARF, Race.HUMAN], rng=random.Random(1003), scripted=True)
    camp = camps.place_encounter(world, (3, 10), "spider_nest")
    world.place_building(0, BuildingType.FARM, (11, 6))  # captured farm1679
    builder = world.spawn_unit(0, UnitType.PEASANT, (8.0, 6.0))
    world.reveal_all(0)
    world.build(builder.id, BuildingType.FARM, (7, 5))

    for _ in range(600):
        world.step()
        finished = next((world.buildings[event.entity] for event in world.take_events() if event.kind == "built"), None)
        if finished is not None:
            break
    else:
        pytest.fail("the captured farm never finished")
    assert builder.constructing is None
    assert world.passable(*builder.tile)
    assert rect_gap(builder.pos, finished.rect) <= 1.0, "a builder must leave at an actual adjacent exit"
    assert dist(builder.pos, camps.centre(world, camp)) > CAMP_WATCH + builder.radius
    assert not camp.roused


@pytest.mark.parametrize("intent", ["ordinary", "explicit", "unseen"])
def test_a_crowd_shove_respects_known_watches_and_explicit_encounter_intent(intent: str) -> None:
    """Seed1003 Forest: the overlapping archers78/172 shoved archer78 across camp17's exact watch.

    This keeps the captured x14..31/y0..15 terrain and the two archers' exact
    positions, translated by (14,0). Hold isolates their physical crowd shove.
    """
    rows = (
        "tttttttttttttttttt",
        "gttttttggggttttttt",
        "gtttttggggggtttttt",
        "ggtttggggggggttttt",
        "gggttggggggggttttt",
        "gggttggggggggttttt",
        "ggtttggggggggttttt",
        "ggtttgggggggtttttt",
        "gggggggggggttttttt",
        "gggggggggttttttttt",
        "gggttggggttttttttt",
        "ggggtggggttttttttt",
        "gggttggggttttttttt",
        "gggttggggttttttttt",
        "ggtttggggggttttttt",
        "ggtttggggggggttttt",
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(18, 16, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.HUMAN, Race.DWARF], rng=random.Random(1003), scripted=True)
    camp = camps.place_encounter(world, (7, 3), "spider_nest")
    archer = world.spawn_unit(1, UnitType.ARCHER, (7.298893011530193, 9.354219451297256))
    pusher = world.spawn_unit(1, UnitType.ARCHER, (7.602816478756747, 10.131050629875453))
    if intent != "unseen":
        world.reveal_all(1)
    world.hold([archer.id, pusher.id])
    if intent == "explicit":
        world.attack([archer.id], camp.guards[0])
    assert dist(archer.pos, camps.centre(world, camp)) > CAMP_WATCH

    if intent != "ordinary":
        world.step()
        assert dist(archer.pos, camps.centre(world, camp)) < CAMP_WATCH
        if intent == "unseen":
            assert camp.lair not in world.worker_knowledge[1].encounters
        return
    for _ in range(5):
        world.step()
        assert dist(archer.pos, camps.centre(world, camp)) >= CAMP_WATCH
        assert not camp.roused


def test_a_march_in_watch_padding_escapes_outward_instead_of_aiming_at_its_tile_centre() -> None:
    """Seed1003 Forest: archer120's saved current-tile waypoint lay inside the remembered watch.

    The x0..31/y0..23 crop retains the captured archer position/path and the
    surrounding bypass. The private route fixture keeps
    the current-tile waypoint and its remembered navigation identity: saves
    discard those caches, which would otherwise silently replan away this bug.
    """
    rows = (
        'ggggggggggggggtttttttttttttttttt',
        'gggggggggggggggttttttggggttttttt',
        'gggggggggggggggtttttggggggtttttt',
        'ggggggggggggggggtttggggggggttttt',
        'gggggggggggggggggttggggggggttttt',
        'gggggggggggggggggttggggggggttttt',
        'ggggggggggggggggtttggggggggttttt',
        'ggggggggggggggggtttgggggggtttttt',
        'gggggggggggggggggggggggggttttttt',
        'gggggggggggggggggggggggttttttttt',
        'gggggggggggggggggttggggttttttttt',
        'ggggggggggggggggggtggggttttttttt',
        'gggggggggggggggggttggggttttttttt',
        'gggggggggggggggggttggggttttttttt',
        'ggggggggggggggggtttggggggttttttt',
        'ggggggggggggggggtttggggggggttttt',
        'ggggggggggggggtttttggggggggttttt',
        'gggggggggggggtttttgggggggggggggg',
        'gggggggggggggtttttgggggggggggggg',
        'gggggggggggtttttttgggggggggggggg',
        'ggggggggggttttttttgggggggggggggg',
        'ggggggggggtttttttttggggggggggggg',
        'gggggggggttttttttttggggggggggggg',
        'ggggggggttttttttttttgggggttggggg',
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(32, 24, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.HUMAN, Race.DWARF], rng=random.Random(1003), scripted=True)
    camp = camps.place_encounter(world, (21, 3), "spider_nest")
    archer = world.spawn_unit(1, UnitType.ARCHER, (20.2015917784056, 8.981973315192391))
    world.reveal_all(1)
    world.attack_move([archer.id], (17.0, 9.0))
    archer.path, archer.path_goal, archer.exact = [(20, 8), (19, 10)], (17, 9), None
    world._camp_path_grids[archer.id] = world._movement_ground(archer)
    for _ in range(120):
        world.step()
        assert dist(archer.pos, camps.centre(world, camp)) >= CAMP_WATCH
        assert not camp.roused
        if not archer.orders:
            break
    assert not archer.orders, "the safe march must continue after leaving the margin"
    assert dist(archer.pos, (17.0, 9.0)) < 1.0


def test_standing_exactly_on_a_known_watch_does_not_grant_entry_to_a_crowd_shove() -> None:
    world = World(16, 16, [[Terrain.GRASS] * 16 for _ in range(16)], 2, scripted=True)
    camp = camps.place_encounter(world, (7, 3), "spider_nest")
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 8.5))
    pusher = world.spawn_unit(0, UnitType.ARCHER, (5.14, 8.98))
    world.reveal_all(0)
    world.hold([archer.id, pusher.id])
    assert dist(archer.pos, camps.centre(world, camp)) == CAMP_WATCH
    for _ in range(5):
        world.step()
        assert dist(archer.pos, camps.centre(world, camp)) >= CAMP_WATCH
        assert not camp.roused


def _captured_crossings_exit_world() -> tuple[World, camps.Camp]:
    rows = (
        "ggggggggggggggg", "ggggggggggggggg", "ggggggggtgggggg",
        "ggggggggtgggggg", "ggggggggtgggggg", "ggggggggtttgggg",
        "ggggggggtttgggg", "gggggggtttggrrr", "ggggggggggggrrr",
        "gggggggggggggrg", "tggggggggggwwwg", "tgggggggggggggg",
        "ggggggggggggggw", "gggggggggggttww", "ggggggggggtttww",
        "ggggggggggtttww", "gggggggggggttww",
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(15, 17, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.HUMAN, Race.ORC], rng=random.Random(1001), scripted=True)
    camp = camps.place_encounter(world, (4, 10), "troll_mound")
    world.place_building(0, BuildingType.TOWN_HALL, (5, 1))  # captured Human hall84
    return world, camp


@pytest.mark.parametrize("intent", ["ordinary", "rally"])
def test_a_trained_worker_leaves_the_captured_hall_outside_known_watches(intent: str) -> None:
    """Medium1001 Crossings: hall197 delivered worker277 straight into remembered Troll32.

    Exact x11..25/y17..33 crop, translated by (11,17), retains the neighboring
    Human hall and trees that leave a safe west exit beside the Orc hall.
    """
    world, camp = _captured_crossings_exit_world()
    hall = world.place_building(1, BuildingType.TOWN_HALL, (5, 4))  # captured Orc hall197
    world.reveal_all(1)
    if intent == "rally":
        world.set_rally(hall.id, camps.centre(world, camp))
    world.train(hall.id, UnitType.PEASANT)
    for _ in range(400):
        world.step()
        trained = next((event for event in world.take_events() if event.kind == "trained"), None)
        if trained is not None:
            break
    else:
        pytest.fail("the captured hall never delivered its worker")
    assert rect_gap(trained.pos, hall.rect) <= 1.0
    if intent == "ordinary":
        worker = world.units[trained.entity]
        assert dist(trained.pos, camps.centre(world, camp)) > CAMP_WATCH + worker.radius
        for _ in range(10):
            world.step()
            assert not camp.roused
    else:
        assert dist(trained.pos, camps.centre(world, camp)) < CAMP_WATCH


def test_cancelling_the_captured_hall_also_releases_its_builder_outside_known_watches() -> None:
    world, camp = _captured_crossings_exit_world()
    builder = world.spawn_unit(1, UnitType.PEASANT, (6.5, 5.5))
    world.players[1].gold = world.players[1].lumber = 2000
    world.reveal_all(1)
    world.build(builder.id, BuildingType.TOWN_HALL, (5, 4))
    world.step()
    assert builder.constructing is not None
    site = world.buildings[builder.constructing]
    world.cancel_building(site.id)
    assert builder.constructing is None
    assert rect_gap(builder.pos, site.rect) <= 1.0
    assert dist(builder.pos, camps.centre(world, camp)) > CAMP_WATCH + builder.radius
    assert not camp.roused


def test_a_march_past_the_captured_fog_edge_keeps_its_guard_detour() -> None:
    """Fuzz232: a golem appeared and vanished each time the footman approached its fog edge.

    Exact x38..79/y6..68 terrain crop and the two captured unit positions retain
    the northern river crossing, so warning padding has a real reachable bypass.
    The hidden lair and other actors are unnecessary: its partially seen golem
    alone switched the old route between NW and SE forever. A public single-unit
    march also reproduces it, without the original formation offset or cached path.
    """
    rows = (
        'gggggggggggggggggtgggttgggtggggggggggggggg',
        'ggggggggggggggggggggggggggtggggggggggggggg',
        'ggggggggggggggggggggggggggtggggggggggggggg',
        'gggggggggggggggtttttgttgtgttgggggggggggggg',
        'gggggggggggggttttttttttgtgttgggggggggggggg',
        'gtgggggggggggttttttttttttgttgggggggggggggg',
        'gtgggggggggggttttttttttttggtgggggggggggggg',
        'gtggggggggggtttttttttttttggtgggggggggggggg',
        'ttggggggggggtttttttttttttgggttgggggggggggg',
        'ttggggwgggggttttttttttttgggggttggggggwwggg',
        'tggggwwwgggggttttttttttgggggggtggggggggtgg',
        'ggggggwgggggggggtttttttggggggggtttgggggtgg',
        'grggggggggggggggtttttttggggggggggtggggttgg',
        'rrgggggggggggrgggttttttgggggggggggrrrggggg',
        'grgggggggggggrggwgtttttttggggtttggrrrrrrgg',
        'gggggggggggggggwwwgttttttggggtttggrrrggggg',
        'gggggggggggggggwwwgttttttggggttggggggggggg',
        'gggggggggggggggggggtttttgggggggggggggggggg',
        'gggggggggggggggggggtttttgtttggrggggggggggt',
        'gggggggggggggggggggtttttggggggggggggggggtt',
        'ggggggggtttttttggggtttttggggggggggggggtttt',
        'gtggggggttttttttgggtttttggggggggggtttttttt',
        'ggggggggttttttttggggttttgggggggggttttttttt',
        'ggggggggggggtttggggggttttgggggggggtttttttt',
        'gggggggggggggtggggggtttttgggggggggggggggtt',
        'gggggggggggggtgggggttttttggggggggggggggggt',
        'gggggggggggggggggggttttttggggrrggggggggggt',
        'grgggggggggggggggggttttgtggggggggggggggggt',
        'grgggggggggggggggttttttgtggggggggggggggggt',
        'grggggggggggggggttttttttggrggggggggggggggt',
        'gggggggggggggggggtttttttgrrgggttgggggggggt',
        'ggggggggggggggggggggtttttgggggttgggggggggt',
        'gtgggggggttgggggggggttttggggggttgggggggggg',
        'gtggggggtttgggggggggtttggggggggtgggggggggg',
        'gtggggggtttggggggggttttggggggggtgggggggggr',
        'gggggggggggggggggggttttggggggggtgggggggggg',
        'ggggtttggggtttttgggttttggggggggggggggggggg',
        'gggtttttgggtttttttttttttgggwwwgggggggggggg',
        'ggggttttgggttttttggttttttgwwwwwwwwgggggggg',
        'ggggtttttttttttggggttttttgwwwwwwwwgggggggg',
        'ggggttttttttgggggggttttttgwwwwwwwggggggggg',
        'ggggttttttttgggggggttttttggggggggggggtttgg',
        'ggggtttttttggggggggttttttgggggggggggttttgg',
        'ggggttttgggggggggggttttttgggggggggggttttgg',
        'ggtttttggggggggggggtttttttrggggggggggttggg',
        'grtttttggggggggggggtttttttrtgggggggggggggg',
        'grtttttggggggggggggttttttrrtgggggggggggggg',
        'gggggtgggggggggggggttttttrrtgggggggggggggg',
        'gggggggggggggggggttttttgggrgggggwwwwwwwggg',
        'ggggggggggggggggtrrttttggggggggwwwwwwwwggg',
        'ggggggggggggggggtrtttttgggggrrrrwwwrgggggg',
        'ggggggggggggggggggtttttggggggrrrgggggggggg',
        'gggggggggggggggggggttttgggggggrggggggggggg',
        'gggggggggggggggggggttttggggggggggtttttrrgg',
        'gggggggggggggggggggttttggggggggggtttttrrgg',
        'gggggggggggggggggggttttggggggggggtttttrrgg',
        'gggggggggggggggggggttttttgtggggggtttgggggg',
        'gggggggggggggggggggtttttttwwgggggggggggggt',
        'gggggggggggggggggggtttttttwwwggggggggggggt',
        'ggggggggggggggggwwgtgtttttwwwggggggggggggt',
        'gttggggggggggggwwwtttttgtgwwgggggggggggggg',
        'gttggggggggggggwwwtttttttggggggggggggggggg',
        'gttgggggggggggggwwtttttttggggggggggggggggg',
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(42, 63, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.DWARF, Race.HUMAN], scripted=True)
    world.spawn_unit(world.neutral, UnitType.GOLEM, (27.338477631085027, 53.33847763108503))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (32.11752972105457, 57.11752972105459))
    origin = footman.pos
    world.attack_move([footman.id], (7.0, 60.0))
    for _ in range(400):
        world.step()
    assert dist(origin, footman.pos) > 8.0, "the known guard must not disappear at each fog edge and reverse the route"
    assert footman.hp == footman.max_hp
