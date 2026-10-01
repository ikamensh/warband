"""Army decisions under real camp rules, through the public brain entry point."""

import random
from dataclasses import replace

import pytest

from warband.brains.ai import Brain, Hunt, dodge_camp_slams
from warband.brains.pro_ai import PRO, ProBrain
from warband.sim import camps, worker_ai
from warband.sim.model import Attack, AttackMove, Harvest, Move, World, dist
from warband.sim.rules import CAMP_WATCH, SIM_DT, BuildingType, Difficulty, Race, Terrain, UnitType, Upgrade


def match():
    world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2, rng=random.Random(11))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (62, 40))
    world.players[0].gold = world.players[0].lumber = 0
    army = [world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4)) for i in range(12)]
    world.time = 180.0
    return world, army


def forest_expedition():
    """The Forest1003 camp, force and existing weapon/armour research at its decision point."""
    world, initial = match()
    for unit in initial:
        unit.hp = 0
    world.step()
    world.time = 506.95
    camp = camps.place_encounter(world, (21, 3), "spider_nest")
    world.players[0].upgrades.update((Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.BLADES_1))
    army = [world.spawn_unit(0, kind, point) for kind, point in (
        (UnitType.ARCHER, (16.56, 11.74)), (UnitType.ARCHER, (16.09, 12.25)),
        (UnitType.FOOTMAN, (16.91, 12.22)), (UnitType.FOOTMAN, (16.51, 13.34)),
        (UnitType.FOOTMAN, (16.96, 12.94)), (UnitType.FOOTMAN, (16.34, 12.78)),
        (UnitType.KNIGHT, (18.00, 12.00)), (UnitType.ARCHER, (15.44, 11.63)),
        (UnitType.KNIGHT, (15.80, 13.96)), (UnitType.ARCHER, (17.29, 10.10)),
        (UnitType.KNIGHT, (17.20, 11.48)), (UnitType.ARCHER, (16.28, 10.88)),
    )]
    return world, camp, army


def test_a_base_defense_interrupts_the_whole_committed_expedition():
    """Forest1003: answering a rival must not leave engaged soldiers on their abandoned camp assignment."""
    world, camp, army = forest_expedition()
    world.place_building(0, BuildingType.TOWER, (16, 8))
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False))
    brain.think(world, random.Random(11))
    assert brain.creeping == camp.lair
    # Recorded attacks reproduce the engaged front line that _defend used to
    # exclude, leaving only the unengaged part of its expedition to defend.
    world.attack([unit.id for unit in army[:6]], camp.guards[0])
    assert all(isinstance(unit.order, Attack) for unit in army[:6])
    rival = world.spawn_unit(1, UnitType.FOOTMAN, (23.68347207662885, 14.864653278699926))
    world.reveal_all(0)
    world.time += 1
    brain.think(world, random.Random(11))
    assert brain.creeping is None
    assert not brain.creep_party
    assert all(isinstance(unit.order, AttackMove) and unit.order.target == rival.pos for unit in army)
    assert camp.lair in brain.camp_retry
    assert brain.camp_failed[camp.lair] > 0


def test_wounded_soldiers_are_not_counted_as_a_prepared_expedition():
    """Forest1003: the healthy cohort must be sufficient before volunteering a worn-down PvP army for a camp."""
    world, camp, army = forest_expedition()
    for unit, hp in zip(army, (15, 40, 60, 3, 5, 50, 32, 40, 85, 40, 90, 40)):
        unit.hp = hp  # exact expedition-choice health from the captured match
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False, push_after=600))
    brain.think(world, random.Random(11))
    assert brain.creeping is None
    assert not any("clear the camp" in text for _, text in brain.log)
    # Once enough bodies have recovered, only the ready soldiers commit; the
    # still-wounded archer gets the existing healing muster instead.
    for unit in army[1:]:
        unit.hp = unit.max_hp
    world.time += 1
    brain.think(world, random.Random(11))
    assert brain.creeping == camp.lair
    assert army[0].id not in brain.creep_party
    assert isinstance(army[0].order, Move)
    assert all(isinstance(unit.order, AttackMove) for unit in army[1:])


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_a_searcher_revalidates_its_march_beneath_an_automatic_guard_attack(kind):
    """Crossings1002: automatic fighting must not hide the newly known danger in a searcher's old destination."""
    world = World(64, 48, [[Terrain.GRASS] * 64 for _ in range(48)], 2, rng=random.Random(1002))
    world.scripted = True
    camp = camps.place_encounter(world, (18, 28), "stone_cairn")
    rider = world.spawn_unit(0, UnitType.KNIGHT, (13.5, 30.1))
    world.attack_move([rider.id], (20.5, 28.5))
    world.reveal_all(0)
    for _ in range(8):
        world.step()
        if isinstance(rider.order, Attack):
            break
    assert isinstance(rider.order, Attack) and rider.order.auto
    assert not camp.roused
    if kind == "pro":
        brain = ProBrain(0, replace(PRO, scout=False))
        brain.next_combat = world.time + 100
    else:
        brain = Brain(0, Difficulty.MEDIUM)
    brain.next_think = world.time + 100
    brain.hunt.party[rider.id] = -1
    brain.think(world, random.Random(1002))
    assert isinstance(rider.order, AttackMove)
    assert dist(rider.order.target, camps.centre(world, camp)) > CAMP_WATCH
    for _ in range(20):
        brain.think(world, random.Random(1002))
        world.step()
        assert not camp.roused


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_an_impossible_nearby_camp_does_not_block_a_feasible_one(kind):
    """The entire army chooses the clearable camp, rather than waiting on a nearer overwhelming camp."""
    world, army = match()
    camps.place(world, (15, 8), [UnitType.TROLL] * 8, 6000)
    feasible = camps.place(world, (20, 24), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    orders = [u.order for u in army]
    assert all(isinstance(order, AttackMove) for order in orders)
    assert all(dist(order.target, world.buildings[feasible.lair].center) < 5 for order in orders)


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_a_failed_attempt_requires_a_stronger_force_before_trying_again(kind):
    """Healing/replacing the same failed force does not restart an indefinitely repeated camp assault."""
    world, army = match()
    camp = camps.place(world, (20, 18), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    assert any("clear the camp" in text for _, text in brain.log)
    # Fixture damage simulates the outcome of a costly assault, without a long match in the fast tier.
    for unit in army[:8]:
        unit.hp = 0
    world.step()
    world.time += 1
    brain.think(world, random.Random(11))
    assert any("break off the camp" in text for _, text in brain.log)
    world.time += 180
    for i in range(8):
        world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4))
    world.reveal_all(0)
    brain.think(world, random.Random(11))
    assert sum("clear the camp" in text for _, text in brain.log) == 1


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_the_army_finishes_surviving_guards_after_the_lair_falls(kind):
    """A demolished lair alone is not a completed encounter or a paid bounty."""
    world, army = match()
    camp = camps.place(world, (20, 18), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    world.buildings[camp.lair].hp = 0
    world.step()
    world.time += 1
    for unit in army:
        world.stop([unit.id])
    brain.think(world, random.Random(11))
    assert not any(text == "camp cleared" for _, text in brain.log)
    assert all(isinstance(unit.order, AttackMove) for unit in army)
    assert all(dist(unit.order.target, camps.centre(world, camp)) < 5 for unit in army)


def test_an_army_waiting_for_enemy_attack_tech_can_clear_a_camp():
    """Creeping supplies a useful job while a deliberate attack timing is still being prepared."""
    world, army = match()
    camp = camps.place(world, (20, 18), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False, push_after=600))
    brain.think(world, random.Random(11))
    assert any("clear the camp" in text for _, text in brain.log)
    assert all(isinstance(unit.order, AttackMove) for unit in army)


def test_a_visible_committed_slam_can_be_dodged_through_movement_orders():
    """A prepared cavalry unit escapes a real marked impact without taking its damage."""
    world, _ = match()
    camp = camps.place(world, (35, 22), [UnitType.GOLEM], 1200)
    guard = world.units[camp.guards[0]]
    knight = world.spawn_unit(0, UnitType.KNIGHT, (guard.x - .8, guard.y))
    world.hold([knight.id])
    world.reveal_all(0)
    marked = False
    for _ in range(int(6 / SIM_DT)):
        if guard.slam_point is not None:
            marked = True
            dodge_camp_slams(world, 0, [knight])
        world.step()
        if any(event.kind == "slam" for event in world.take_events()):
            break
    else:
        pytest.fail("the guard never released its slam")
    assert marked
    assert knight.hp == knight.max_hp


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_fresh_recruits_do_not_mask_losses_of_the_committed_camp_army(kind):
    """A failed expedition withdraws even if equally many fresh recruits are alive back at home."""
    world, army = match()
    camp = camps.place(world, (20, 18), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    for unit in army[:8]:
        unit.hp = 0
    world.step()
    recruits = [world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4)) for i in range(8)]
    world.time += 1
    world.reveal_all(0)
    brain.think(world, random.Random(11))
    assert any("break off the camp" in text for _, text in brain.log)
    assert not any(isinstance(unit.order, AttackMove) and dist(unit.order.target, camps.centre(world, camp)) < 5
                   for unit in recruits)


@pytest.mark.slow
def test_an_unrelated_army_march_routes_around_a_remembered_camp():
    """Slow: a whole open-field march verifies pathfinding, formation shortcuts and camp intrusion together."""
    world = World(46, 36, [[Terrain.GRASS] * 46 for _ in range(36)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (21, 16), "stone_cairn")
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 17.5))
    target = (39.5, 17.5)
    world.reveal_all(0)
    world.attack_move([soldier.id], target)
    nearest = float("inf")
    for _ in range(int(30 / SIM_DT)):
        world.step()
        nearest = min(nearest, dist(soldier.pos, camps.centre(world, camp)))
        assert not camp.roused
        if not soldier.orders:
            break
    assert nearest > CAMP_WATCH
    assert dist(soldier.pos, target) < 1
    assert soldier.hp == soldier.max_hp


def test_an_army_waiting_at_home_does_not_muster_inside_a_remembered_camp():
    """A safe march cannot help if the brain chooses an incidental camp as its rally destination."""
    world, _ = match()
    army = [world.spawn_unit(0, UnitType.ARCHER, (3.5 + i, 20.5)) for i in range(3)]
    camp = camps.place(world, (11, 6), [UnitType.TROLL] * 8, 6000)
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False, push_after=600))
    brain.think(world, random.Random(11))
    moving = [unit.order for unit in army if isinstance(unit.order, Move)]
    assert moving
    assert all(dist(order.target, camps.centre(world, camp)) > CAMP_WATCH + 1 for order in moving)


def test_an_archer_in_avoided_padding_does_not_kite_into_the_camp():
    """Only an actual intrusion grants escape movement; harmless safety padding must still constrain kiting."""
    world = World(34, 30, [[Terrain.GRASS] * 34 for _ in range(30)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (17, 15), "stone_cairn")
    cx, cy = camps.centre(world, camp)
    archer = world.spawn_unit(0, UnitType.ARCHER, (cx, cy - CAMP_WATCH - .1))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (archer.x, archer.y - 1.5))
    world.reveal_all(0)
    world.hold([enemy.id])
    world.attack_move([archer.id], (cx, 2.5))
    for _ in range(int(4 / SIM_DT)):
        world.step()
        assert not camp.roused
        assert dist(archer.pos, camps.centre(world, camp)) > CAMP_WATCH


def test_a_discovered_encounter_remains_known_after_its_lair_falls_and_reload():
    """Destroying the lair must not turn its surviving guards into unknown navigation hazards."""
    world = World(48, 32, [[Terrain.GRASS] * 48 for _ in range(32)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (28, 16), "ancient_sanctum")
    world.buildings[camp.lair].hp = 1  # a damaged benchmark lair; the final blow is a real recorded attack
    siege = world.spawn_unit(0, UnitType.CATAPULT, (18.5, 17.5))
    world.reveal_all(0)
    world.attack([siege.id], camp.lair)
    for _ in range(int(4 / SIM_DT)):
        world.step()
        if camp.lair not in world.buildings:
            break
    assert camp.lair not in world.buildings
    world.reveal_all(0)
    restored = World.from_dict(world.to_dict())
    assert camp.lair not in restored.worker_knowledge[0].buildings
    assert set(camp.guards) <= camps.known_guards(restored, 0)


def test_a_ground_searcher_does_not_choose_a_camp_as_its_scouting_destination():
    """A hunt searches for rival holdings without turning a nearby search square into an incidental raid."""
    world = World(34, 30, [[Terrain.GRASS] * 34 for _ in range(30)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (16, 16), "troll_mound")
    knight = world.spawn_unit(0, UnitType.KNIGHT, (22.5, 18.5))
    world.reveal_all(0)
    Hunt().step(world, 0, [knight], lost=True)
    assert isinstance(knight.order, AttackMove)
    assert dist(knight.order.target, camps.centre(world, camp)) > CAMP_WATCH


def test_an_automatic_worker_replans_when_its_old_route_becomes_camp_ground():
    """Seed1001 Plains: a newly discovered den must replace the old mining crossing with a real escape."""
    rows = (
        'gggggggggggggttttggggggggggggggggggggg',
        'gggggggggggggttttggggggggggggggggggggg',
        'gggggggggggggggggggggggggggggggggggggg',
        'gtggggggggggggggggggggggggggggggggtttt',
        'gtgggggggggggggggggggwwwgggggggggttttt',
        'gtggggggggggggggggtggggggggggggggttttt',
        'gtttgggggggggggggtttgggggggggggggggggg',
        'gtttgggggggggggggtttgggggtttgggggggggr',
        'tttgggggtttgggggggggggggtttggggggggggt',
        'ggggggggtttgggggggggggggtttgggggggggtt',
        'gggggggggtggggggggggggggggtgggggggggtt',
        'ggggwwwgggggggggggggggggggtggggggggggt',
        'ggggggggggggggggggggggggggtggggggggggt',
        'gggggggggggggggggggggggggggggggggggggg',
        'gggggggggggttttgggggggggggggttttgggggg',
        'gggggggggggttttgggggggggggggtttttrrggg',
        'gggtggggggwttttggggggggwwwggtttggrgggg',
        'ggggtggggggttttggggggggwwwgggggggggggg',
        'gggggtgggggggtggggggggggwwgggggggggggg',
        'gggggggggggggggggggggrggwwwggggggggggg',
        'gggggggggggggggggggggrggwwwggggggggggg',
        'ggggttggggggggggggggggggwwwggggggggggg',
        'gggggggggggggggggggggggggggtgggggggggg',
        'ggggggtgggggggggrrrggggggggtgggggggggg',
        'gggggggggggggggggggggggggggtgggggggggg',
        'gggggggggggggggggggggggggggggggggggggg',
        'ggggggggggggggggggggggggggggtggggggggg',
        'rrrrrrggggggggggggggggggggtttggggggggg',
        'rrrrrrgggggggggggggggggggtttgggggggggg',
        'ttttttttttttttttttttggggttttgggggggggg',
        'tttttttttttgggttttttttttttttgggggggggg',
        'ttttttttttttttttttttttttttttgggggggggg',
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(38, 32, [[tiles[c] for c in row] for row in rows], 2,
                  races=[Race.HUMAN, Race.ORC], rng=random.Random(1001), scripted=True)
    camp = camps.place_encounter(world, (21, 25), "wolf_den")
    mine = world.place_building(None, BuildingType.GOLD_MINE, (3, 2))
    worker = world.spawn_unit(1, UnitType.PEASANT, (28.81305126997453, 24.68374209639557))
    world.reveal_all(1)
    world.harvest([worker.id], mine.id)
    # Captured knowledge includes the crossing and distant mine, but not the
    # den. Load those public remembered facts and the actual automatic job.
    checkpoint = world.to_dict()
    knowledge = checkpoint["worker_knowledge"][1]
    knowledge["buildings"] = [b for b in knowledge["buildings"] if b["id"] != camp.lair]
    knowledge["encounters"] = [item for item in knowledge["encounters"] if item[0] != camp.lair]
    captured = next(u for u in checkpoint["units"] if u["id"] == worker.id)
    captured["worker_orders"] = [{"index": 0, "auto": True, "placed": True}]
    world = World.from_dict(checkpoint)
    worker = world.units[worker.id]
    camp = world.camp_for(camp.lair)
    assert camp is not None
    # Private fixture setup is necessary: normal checkpoints deliberately
    # discard routes, but this regression requires the path already chosen
    # before the lair enters sight. Positions/terrain/path are the exact crop.
    worker.path = [(28, 25), (27, 25), (26, 25), (25, 24), (24, 23)]
    worker.path_goal, worker.exact, worker.replan_at = (6, 5), (6.5, 5.5), 2.0
    for _ in range(int(2 / SIM_DT)):
        world.step()
        assert not camp.roused
    assert worker.hp == worker.max_hp


def test_a_scout_reconsiders_its_destination_when_it_discovers_a_camp():
    """Klondike1001: a ring chosen before discovery must not bring its scout inside the newly observed watch.

    The discovery checkpoint had only one reaction tick before intrusion. Keep its exact terrain and scout
    position; safety reactions must therefore run even while the brain's ordinary decisions are not due.
    """
    rows = (
        'ggggggggggggggggrrrggggggggg',
        'ggggggggggggggggrrrwgggggggg',
        'ggggggggggggggggrrrwwggggggg',
        'ggggggggggggggggrrrwwwwwwwwg',
        'gggggggggggggggrrrwwwwwwwwwg',
        'gggggggggggggggrrrwwwwwwwwwg',
        'ggggggggggggggggrrgggwwwwwrg',
        'rgggggggggggtggggggggtttgrrg',
        'rrrggggggggtgggggggggtttgrrg',
        'rrrrggggggrrrggggggggttttggg',
        'rrrrrrrrrrrrrrgggggggtgtgggg',
        'grrrrrrrrrrrrggggggggtgggggg',
        'ggrrrrrrrrgggggggggggtttgggg',
        'gggggggggggggggggggggtgggggg',
        'ggggggggggggggggggggttgggggg',
        'ggggggggggggtggggggttggggggg',
        'gttgggggggggttggggtttggggggg',
        'ggtggggggggggtttttttgggggggg',
        'ggwgggggggggggggtttggggggggg',
        'gggwwgggggggwwwggtgggggggggg',
        'ggggggtgggrrgwgggttggggggggg',
        'gggggggggggggggggggggggggggg',
        'gggggggggggggggggggggggggggg',
        'gggggggggtttttttgggggggggggg',
        'tttttttttttttttttggggggggggg',
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(28, 25, [[tiles[char] for char in row] for row in rows], 2,
                  rng=random.Random(1001), scripted=True)
    camp = camps.place_encounter(world, (15, 12), "wolf_den")
    scout = world.spawn_unit(0, UnitType.PEASANT, (11.44619669572824, 13.49999748185807))
    world.move([scout.id], (19.1612811503609, 11.530043208188054))
    assert camp.lair not in world.worker_knowledge[0].encounters
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=True))
    brain.scouts = [scout.id]
    brain.next_think = brain.next_combat = 10.0
    brain.think(world, random.Random(1001))
    assert isinstance(scout.order, Move)
    assert dist(scout.order.target, camps.centre(world, camp)) > CAMP_WATCH + 1
    for _ in range(20):
        brain.think(world, random.Random(1001))
        world.step()
        assert not camp.roused
    assert scout.hp == scout.max_hp


def test_a_worker_fleeing_rivals_keeps_other_camp_watches_closed():
    """Bastion1003: fleeing five peasants must not relax a different, remembered camp's watch.

    The terrain, worker, pursuers and first escape steps come from the 680.05s checkpoint.
    """
    rows = (
        'tggggggggggggggggggggg',
        'gggggggtttgggggggggggg',
        'ggggggggggggggtttggggg',
        'gggggggggggggggggggggg',
        'gggggggggggggggggggggg',
        'gggggggggggwgggggggggg',
        'gggggggggggggggggggggg',
        'gggggggggggggggggggggg',
        'gggggggggggggggggggggg',
        'gggggggggggggggggggggg',
        'gggggggggggggggtgggggg',
        'ttgggggggggggggggggggg',
        'tttttggrggttgggggggggg',
        'tttttgrrrgtttggggggggg',
        'tttttgrrrgtttggggggggg',
        'gggggggggggtgggggggggt',
        'ggggggggggrrgggggggggt',
        'ggggggggggrrrggggggrtt',
        'gggggggggggggggggggrgt',
        'gggggggggggwgggggggggg',
        'ggggggggggwwwggggggggw',
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(22, 21, [[tiles[char] for char in row] for row in rows], 2,
                  rng=random.Random(1003), scripted=True)
    camp = camps.place_encounter(world, (6, 6), "stone_cairn")
    worker = world.spawn_unit(0, UnitType.PEASANT, (13.358702152828624, 12.76171672278644))
    pursuers = [world.spawn_unit(1, UnitType.PEASANT, point) for point in [
        (15.038032700794368, 13.49509175273264), (13.650078218031297, 14.05822563544215),
        (14.254281705324363, 13.62074282796466), (14.459167322165467, 13.05368833294097),
        (14.341745817675474, 14.38528574557398),
        (14.950000000000003, 9.5), (14.494883730931722, 9.524071772514073),
    ]]
    world.hold([unit.id for unit in pursuers])
    world.reveal_all(0)
    # The captured automatic harvest remains active while the worker escapes the pursuers.
    worker.orders.append(Harvest((0, 0), auto=True, placed=True))
    # Saves omit route caches. Preserve this real escape prefix to exercise its continuation during the safety alarm.
    worker.path = [(12, 11), (11, 11), (10, 11), (9, 11), (9, 12), (9, 13), (9, 14), (9, 15)]
    worker.path_goal = (1, 1)
    worker.replan_at = .8
    # The saved route was already planned on this safety grid; restoration normally discards this association.
    world._camp_path_grids[worker.id] = worker_ai.safe_navigation(world, 0)
    for _ in range(60):
        world.step()
        assert not camp.roused, worker.pos
    assert dist(worker.pos, camps.centre(world, camp)) > CAMP_WATCH


def test_a_forest_walker_can_escape_camp_padding_from_a_tree_tile():
    """The danger map constrains travel, while the unit's own forest ground still permits its starting tree."""
    terrain = [[Terrain.GRASS] * 26 for _ in range(24)]
    terrain[12][8] = Terrain.TREES
    world = World(26, 24, terrain, 2, races=[Race.ELF, Race.HUMAN], rng=random.Random(11), scripted=True)
    camp = camps.place_encounter(world, (12, 11), "wolf_den")
    walker = world.spawn_unit(0, UnitType.TREANT, (8.0, 12.5))
    world.reveal_all(0)
    world.move([walker.id], (3.5, 12.5))
    for _ in range(30):
        world.step()
        assert not camp.roused
    assert walker.x < 7
    assert walker.hp == walker.max_hp


def test_a_medium_army_already_pushing_a_rival_does_not_divert_to_a_camp():
    """Klondike1000: the global army count includes a scattered ongoing PvP push, not a ready expedition."""
    world, army = match()
    camp = camps.place(world, (20, 18), [UnitType.WOLF] * 3, 1200)
    world.reveal_all(0)
    rival = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    world.attack_move([unit.id for unit in army], rival)
    brain = Brain(0, Difficulty.MEDIUM)
    brain.attacking = True
    brain.think(world, random.Random(11))
    assert not any("clear the camp" in text for _, text in brain.log)
    assert all(isinstance(unit.order, AttackMove) and unit.order.target == rival for unit in army)
    assert not camp.roused
