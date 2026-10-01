"""Army decisions under real camp rules, through the public brain entry point."""

import random
from dataclasses import replace

import pytest

from warband.brains.ai import Brain, Hunt, dodge_camp_slams
from warband.brains.pro_ai import PRO, ProBrain
from warband.sim import camps
from warband.sim.model import AttackMove, Move, World, dist
from warband.sim.rules import CAMP_WATCH, SIM_DT, BuildingType, Difficulty, Race, Terrain, UnitType


def match():
    world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2, rng=random.Random(11))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (62, 40))
    world.players[0].gold = world.players[0].lumber = 0
    army = [world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4)) for i in range(12)]
    world.time = 180.0
    return world, army


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
