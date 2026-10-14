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
    # The interruption must hit a genuinely roused camp, not a quiet one: step
    # until the guards answer inside their own watch.
    centre = camps.centre(world, camp)
    for _ in range(round(6 / SIM_DT)):
        world.step()
        if camp.roused and any(dist(unit.pos, centre) <= CAMP_WATCH + 1.0
                               for unit in army[:6] if unit.id in world.units):
            break
    assert camp.roused, "the staged attack never roused the camp"
    assert any(dist(unit.pos, centre) <= CAMP_WATCH + 1.0
               for unit in army[:6] if unit.id in world.units), "the party never reached the watch"
    party_ids = {unit.id for unit in army}
    # The threat stands between the camp and our base, as a raid on it does:
    # the walk-out past it then leads away from the camp, and a withdrawing
    # party gets out. Staged beyond the camp instead, the same walk marches
    # along its hold inside chaser range the whole way, and no withdrawal
    # assignment survives it, whatever the brain does.
    rival = world.spawn_unit(1, UnitType.FOOTMAN, (14.0, 16.0))
    world.reveal_all(0)
    world.time += 1
    brain.think(world, random.Random(11))
    assert brain.creeping is None
    assert not brain.creep_party
    # The whole expedition walks out blind past the threat: stopping or
    # attack-moving inside the roused camp would reacquire its guards, and
    # stopping at the threat leaves the vanguard fighting chasers alone.
    from warband.brains.ai import rally_past
    rally = rally_past(centre, rival.pos)
    assert all(isinstance(unit.order, Move) and dist(unit.order.target, rally) < 1.0 for unit in army)
    assert camp.lair in brain.camp_retry
    assert brain.camp_failed[camp.lair] > 0
    # Escape under pressure: think on the way out, as a live match does, and
    # no interrupted member may die to the camp or still stand in its watch.
    for step in range(round(12 / SIM_DT)):
        if step % 10 == 0:
            brain.think(world, random.Random(11))
            # Still walking out means still on the escape march: no raid,
            # hunt, commander or defense errand may retask a sheltered
            # soldier back into the camp it is leaving. A sheltered march
            # stays within the rally ground: the escape itself, or the
            # model's way home beside it after the kill. A sheltered member
            # the model set onto a rival is resuming the defense. Anything
            # else (a brain errand, a march back at the guards) is the
            # retasking this test hunts; every brain destination lies
            # farther from the rally than the model's home ground.
            for uid in party_ids:
                if uid not in world.units or uid not in brain.camp_escape:
                    continue
                order = world.units[uid].order
                if isinstance(order, Move) and dist(order.target, rally) < 2.0:
                    continue
                foe = world.entity(order.target) if isinstance(order, Attack) and order.auto else None
                assert foe is not None and foe.player is not None and foe.player < world.seats, (uid, order)
        world.step()
    assert all(uid in world.units for uid in party_ids), "interrupted members fed the camp untracked"
    assert all(dist(world.units[uid].pos, centre) > CAMP_WATCH for uid in party_ids)
    # Out of the camp, the walk-out is over: every survivor is back in the
    # normal assignment pool, answering whatever the match needs next.
    brain.think(world, random.Random(11))
    assert not brain.camp_escape


def test_a_medium_base_defense_cancels_the_committed_expedition():
    """Forest1003 in the classic brain: answering a rival clears the camp assignment instead of resuming it."""
    world, camp, army = forest_expedition()
    world.place_building(0, BuildingType.TOWER, (16, 8))
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (10.5, 12.5))
    for i in range(3):
        army.append(world.spawn_unit(0, UnitType.ARCHER, (8.5 + i, 13.5)))
    world.reveal_all(0)
    brain = Brain(0, Difficulty.MEDIUM)
    brain.think(world, random.Random(11))
    assert brain.creeping == camp.lair
    assert gryphon.id in brain.creep_party
    world.attack([unit.id for unit in army[:6]], camp.guards[0])
    assert all(isinstance(unit.order, Attack) for unit in army[:6])
    # The interruption must hit a genuinely roused camp, not a quiet one: step
    # until the guards answer inside their own watch.
    centre = camps.centre(world, camp)
    for _ in range(round(6 / SIM_DT)):
        world.step()
        if camp.roused and any(dist(unit.pos, centre) <= CAMP_WATCH + 1.0
                               for unit in army[:6] if unit.id in world.units):
            break
    assert camp.roused, "the staged attack never roused the camp"
    assert any(dist(unit.pos, centre) <= CAMP_WATCH + 1.0
               for unit in army[:6] if unit.id in world.units), "the party never reached the watch"
    party_ids = set(brain.creep_party)
    assert len(party_ids) > 2
    # A rival scout overhead gives the gryphon an own-unit errand on the
    # defense pass, when the raid, the hunt and the commander have already
    # filtered the army the cancellation reads.
    prey = world.spawn_unit(1, UnitType.FLYING_MACHINE, (24.5, 12.5))
    world.hold([prey.id])
    # Between the camp and our base, as in the pro interruption above: the
    # walk-out past it leads away from the camp rather than along its hold.
    rival = world.spawn_unit(1, UnitType.FOOTMAN, (14.0, 16.0))
    world.reveal_all(0)
    world.time += 1
    brain.think(world, random.Random(11))
    assert brain.creeping is None
    assert not brain.creep_party
    assert camp.lair in brain.camp_retry
    assert brain.camp_failed[camp.lair] > 0
    # Every interrupted member walks out blind past the threat: an
    # attack-move would reacquire the guards, stopping at the threat leaves
    # the vanguard fighting chasers alone, and a member left standing to
    # fight is never redirected. Stopped stragglers would feed the camp.
    from warband.brains.ai import rally_past
    rally = rally_past(centre, rival.pos)
    for uid in party_ids:
        order = world.units[uid].order
        assert isinstance(order, Move) and dist(order.target, rally) < 1.0
    # Escape under pressure: think on the way out, as a live match does, and
    # no interrupted member may die to the camp or still stand in its watch.
    for step in range(round(12 / SIM_DT)):
        if step % 10 == 0:
            brain.think(world, random.Random(11))
            # Still walking out means still on the escape march: no raid,
            # hunt, commander or defense errand may retask a sheltered
            # soldier back into the camp it is leaving. A sheltered march
            # stays within the rally ground: the escape itself, or the
            # model's way home beside it after the kill. A sheltered member
            # the model set onto a rival is resuming the defense. Anything
            # else (a brain errand, a march back at the guards) is the
            # retasking this test hunts; every brain destination lies
            # farther from the rally than the model's home ground.
            for uid in party_ids:
                if uid not in world.units or uid not in brain.camp_escape:
                    continue
                order = world.units[uid].order
                if isinstance(order, Move) and dist(order.target, rally) < 2.0:
                    continue
                foe = world.entity(order.target) if isinstance(order, Attack) and order.auto else None
                assert foe is not None and foe.player is not None and foe.player < world.seats, (uid, order)
        world.step()
    centre = camps.centre(world, camp)
    assert all(uid in world.units for uid in party_ids), "interrupted members fed the camp untracked"
    assert all(dist(world.units[uid].pos, centre) > CAMP_WATCH for uid in party_ids)
    # Out of the camp, the walk-out is over: every survivor is back in the
    # normal assignment pool, answering whatever the match needs next.
    brain.think(world, random.Random(11))
    assert not brain.camp_escape


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


def stranded_endgame(knights: int, *, lair_down: bool, time: float, revealed: bool = True):
    """A lost endgame on open ground: seat 1 is razed but for one hidden peasant, seat 0 has learned the whole
    map including the wolf den at (30, 25).  With *lair_down* the lair entity is gone while its encounter stands
    uncleared, as an online planning copy sees every remembered camp it cannot see now.  Unrevealed, nothing is
    known yet, so the first think marches at the guessed corner."""
    world = World(48, 40, [[Terrain.GRASS] * 48 for _ in range(40)], 2,
                  races=[Race.DWARF, Race.ORC], rng=random.Random(5))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (40, 32)).hp = 0
    camp = camps.place_encounter(world, (30, 25), "wolf_den")
    army = [world.spawn_unit(0, UnitType.KNIGHT, (8.5 + i % 4, 10.5 + i // 4)) for i in range(knights)]
    world.spawn_unit(1, UnitType.PEASANT, (45.5, 3.5))
    for _ in range(5):
        world.step()  # the razed hall falls before seat 0 learns the map, so nothing of the rival is remembered
    if revealed:
        world.reveal_all(0)
    if lair_down:
        world.buildings[camp.lair].hp = 0
    for _ in range(5):
        world.step()
    world.update_vision()
    world.time = time
    return world, camp, army


def learn_the_map(world):
    """Seat 0 honestly learns the whole map after marching out blind: reveal, then recompute sight so the distant
    peasant and camp guards stay hidden."""
    world.reveal_all(0)
    world.update_vision()


def creep_bound_for(army, centre):
    """The soldiers whose public orders march at the camp: the prepared expedition, not passing searchers, whose
    camp-safe destinations stay outside the watch."""
    return [unit for unit in army if unit.orders and isinstance(unit.orders[0], AttackMove)
            and dist(unit.orders[0].target, centre) <= 6.0]


def test_a_prepared_army_clears_a_remembered_camp_it_cannot_see():
    """An online planning copy omits the unseen lair entity, though the encounter is remembered and uncleared:
    the prepared force must still march at it, through the public orders it is given."""
    world, camp, army = stranded_endgame(10, lair_down=True, time=200.0)
    assert camp.lair not in world.buildings
    ProBrain(0, PRO).think(world, random.Random(5))
    centre = camps.centre(world, camp)
    assert len(creep_bound_for(army, centre)) >= 6, "no prepared force was given the remembered camp"


def test_a_blind_pro_push_yields_to_a_remembered_camp():
    """The army first marches at its guessed corner with nothing known; once the den is learned, the blind push
    yields and the prepared force is ordered at the camp instead."""
    world, camp, army = stranded_endgame(10, lair_down=False, time=200.0, revealed=False)
    brain = ProBrain(0, PRO)
    brain.think(world, random.Random(5))
    assert brain.attacking and brain.creeping is None
    learn_the_map(world)
    world.time += 1
    brain.think(world, random.Random(5))
    centre = camps.centre(world, camp)
    assert len(creep_bound_for(army, centre)) >= 6, "the blind push never yielded to the remembered camp"


def test_a_blind_medium_push_yields_to_a_remembered_camp():
    """The classic brain stalls the same way: Medium creeps by design, so its wave at a guessed corner must yield
    to clearing the remembered den just as the stronger brain's does."""
    world, camp, army = stranded_endgame(16, lair_down=False, time=500.0, revealed=False)
    brain = Brain(0, Difficulty.MEDIUM)
    brain.think(world, random.Random(5))
    assert brain.attacking and brain.creeping is None
    learn_the_map(world)
    world.time += 1
    brain.think(world, random.Random(5))
    centre = camps.centre(world, camp)
    assert len(creep_bound_for(army, centre)) >= 6, "the blind push never yielded to the remembered camp"


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_a_weakened_camp_is_retried_without_rebuilding_the_failed_force(kind):
    """Guards that fall during the failed assault count: a den quartered before the abort needs a quarter retry."""
    world, army = match()
    for i in range(4):
        world.spawn_unit(0, UnitType.ARCHER, (8.5 + (12 + i) % 4, 10.5 + (12 + i) // 4))
    army = [unit for unit in world.player_units(0) if not unit.is_worker]
    camp = camps.place_encounter(world, (20, 18), "wolf_den")
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    assert sum("clear the camp" in text for _, text in brain.log) == 1
    # The committed army stands off while a witnessed thrust quarters the den during the assault.
    world.stop([unit.id for unit in army])
    world.move([unit.id for unit in army], (8.5, 10.5))
    slayers = [world.spawn_unit(0, UnitType.KNIGHT, (24.5 + i % 5, 21.5 + i // 5)) for i in range(10)]
    target = None
    for _ in range(round(180 / SIM_DT)):
        if sum(world.worker_knowledge[0].fallen_guards.get(camp.lair, {}).values()) >= 3:
            break
        live = [uid for uid in camp.guards if uid in world.units]
        if target not in live:
            target = live[0]
            world.attack([slayer.id for slayer in slayers if slayer.id in world.units], target)
        world.step()
    assert world.worker_knowledge[0].fallen_guards == {camp.lair: {"wolf": 3}}
    for slayer in slayers:
        if slayer.id in world.units:
            world.units[slayer.id].hp = 0
    # A costly assault then breaks off against the weakened den.
    for unit in army[:10]:
        if unit.id in world.units:
            world.units[unit.id].hp = 0
    world.step()
    world.time += 1
    brain.think(world, random.Random(11))
    assert any("break off the camp" in text for _, text in brain.log)
    world.time += 180
    for i in range(8):
        world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4))
    world.reveal_all(0)
    brain.think(world, random.Random(11))
    assert sum("clear the camp" in text for _, text in brain.log) == 2

def split_world():
    """Open ground cut by an unwalkable river: seat 0 holds the west bank alone, with no rival to march at."""
    rows = [[Terrain.GRASS] * 40 for _ in range(30)]
    for y in range(30):
        rows[y][8] = rows[y][9] = Terrain.WATER
    world = World(40, 30, rows, 2, rng=random.Random(11))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (3, 3))
    world.time = 180.0
    return world


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_only_the_reachable_cohort_commits_to_a_camp(kind):
    """A stranded recruit neither blocks nor joins the expedition: the reachable cohort clears the reachable den."""
    world = split_world()
    near = camps.place_encounter(world, (11, 5), "wolf_den")
    far = camps.place_encounter(world, (4, 24), "wolf_den")
    army = [world.spawn_unit(0, UnitType.ARCHER, (4.5 + i % 4, 10.5 + i // 4)) for i in range(20)]
    stranded = world.spawn_unit(0, UnitType.KNIGHT, (35.5, 25.5))
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    brain.think(world, random.Random(11))
    assert brain.creeping == far.lair
    assert stranded.id not in brain.creep_party
    assert len(brain.creep_party) >= 8
    assert all(world.units[uid].pos[0] < 8 for uid in brain.creep_party)
    for _ in range(round(150 / SIM_DT)):
        world.step()
        if round(world.time * 20) % 10 == 0:
            brain.think(world, random.Random(11))
        if far.cleared:
            break
    assert far.cleared, "the reachable cohort must clear the reachable camp"
    assert stranded.id in world.units


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_stranded_troops_do_not_fund_an_expedition(kind):
    """Unreachable strength is not spent: a cohort too weak on its own stays home, whatever waits across the water."""
    world = split_world()
    camp = camps.place_encounter(world, (4, 24), "wolf_den")
    weak = [world.spawn_unit(0, UnitType.ARCHER, (4.5 + i % 4, 10.5 + i // 4)) for i in range(11)]
    for i in range(6):
        world.spawn_unit(0, UnitType.KNIGHT, (33.5 + i % 3, 24.5 + i // 3))
    world.reveal_all(0)
    brain = (Brain(0, Difficulty.MEDIUM) if kind == "medium"
             else ProBrain(0, replace(PRO, scout=False)))
    for _ in range(3):
        world.time += 1
        brain.think(world, random.Random(11))
    assert brain.creeping is None
    assert not brain.creep_party


def test_a_pro_soldier_bleeding_against_guards_withdraws_to_heal():
    """Wound retreat answers camp guards too: a nearly-dead soldier with guards on it leaves, whatever the foe."""
    world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2, rng=random.Random(11))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    camp = camps.place_encounter(world, (12, 10), "wolf_den")
    hurt = world.spawn_unit(0, UnitType.FOOTMAN, (15.5, 12.5))
    hurt.hp = int(hurt.max_hp * 0.2)
    sound = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 10.5))
    sound.hp = int(sound.max_hp * 0.2)
    world.time = 180.0
    world.update_vision()
    brain = ProBrain(0, replace(PRO, scout=False))
    brain.think(world, random.Random(11))
    assert hurt.id in brain._hurt
    assert isinstance(world.units[hurt.id].order, Move)
    assert sound.id not in brain._hurt


def test_a_wounded_flyer_ignores_ground_guards_but_answers_air_threats():
    """Wound retreat asks whether the guard's blow can land: wolves cannot touch a gryphon, spiders can."""
    def retreats_from(identity):
        world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2, rng=random.Random(11))
        world.scripted = True
        world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
        camps.place_encounter(world, (12, 10), identity)
        gryphon = world.spawn_unit(0, UnitType.GRYPHON, (15.5, 12.5))
        gryphon.hp = int(gryphon.max_hp * 0.2)
        world.time = 180.0
        world.update_vision()
        brain = ProBrain(0, replace(PRO, scout=False))
        brain.think(world, random.Random(11))
        return gryphon.id in brain._hurt

    assert not retreats_from("wolf_den")
    assert retreats_from("spider_nest")


def test_a_guarded_expansion_counts_beyond_its_bounty():
    """A camp on our next mine is worth extra walk: an endless seam most, any working mine more than bounty."""
    from warband.brains.ai import CAMP_WALK, camp_worth, known_camps

    def worth_with(deposit, gold=None, rival=None):
        world, _army = match()
        camp = camps.place_encounter(world, (20, 18), "wolf_den")
        mine = world.place_building(None, deposit, (26, 13))
        if gold is not None:
            mine.gold = gold
        if rival is not None:
            world.place_building(1, BuildingType.TOWN_HALL, rival)
        world.reveal_all(0)
        record = next(r for r in known_camps(world, 0) if r.id == camp.lair)
        return camp_worth(world, 0, record)

    bounty = (1200 + 150) / 1200.0
    assert worth_with(BuildingType.GOLD_SEAM) == CAMP_WALK
    small = worth_with(BuildingType.GOLD_MINE, gold=1500)
    assert bounty < small < CAMP_WALK
    assert worth_with(BuildingType.GOLD_MINE, gold=0) == bounty
    assert worth_with(BuildingType.GOLD_MINE, gold=1500, rival=(28, 20)) == bounty


def test_a_camp_estimate_falls_with_its_watched_casualties():
    """Halving a discovered den's guards while watching lowers the priced force, not just the visible one."""
    from warband.brains.pro_force import camp_strength

    world, _army = match()
    camp = camps.place_encounter(world, (20, 18), "wolf_den")
    slayers = [world.spawn_unit(0, UnitType.KNIGHT, (24.5 + i % 5, 21.5 + i // 5)) for i in range(10)]
    world.reveal_all(0)
    centre = camps.centre(world, camp)
    full = camp_strength(world, 0, centre, [], camp.lair)
    assert full > 0
    target = None
    for _ in range(round(180 / SIM_DT)):
        if sum(world.worker_knowledge[0].fallen_guards.get(camp.lair, {}).values()) >= 2:
            break
        live = [uid for uid in camp.guards if uid in world.units]
        if target not in live:
            target = live[0]
            world.attack([slayer.id for slayer in slayers if slayer.id in world.units], target)
        world.step()
    assert world.worker_knowledge[0].fallen_guards == {camp.lair: {"wolf": 2}}
    assert camp_strength(world, 0, centre, [], camp.lair) < full
    assert camp_strength(world, 0, centre, [], camp.lair, seen=full) < full


def expansion_world():
    """Seed-1003 Plains at an expansion decision: prepared army, drying mine and a scouted guard."""
    from warband.sim import mapgen
    from warband.sim.rules import Layout, MapTheme

    world = mapgen.generate(seed=1003, width=64, height=48, players=2, races=[Race.HUMAN, Race.ORC],
                            layout=Layout.PLAINS, theme=MapTheme.SUMMER, wilds=False)
    world.scripted = True
    world.players[0].gold = 6000
    mains = [b for b in world.buildings.values()
             if b.type is BuildingType.GOLD_MINE and abs(b.center[0] - 3.5) < 3]
    assert mains, "the probe's main mine moved; restage the chain"
    mains[0].gold = 1200
    natural = next(b for b in world.buildings.values()
                   if b.type is BuildingType.GOLD_MINE and abs(b.center[0] - 24.5) < 3)
    for kind, position in (
        (BuildingType.FARM, (3, 8)), (BuildingType.FARM, (7, 3)),
        (BuildingType.FARM, (11, 8)), (BuildingType.FARM, (11, 5)),
        (BuildingType.BARRACKS, (5, 12)), (BuildingType.LUMBER_MILL, (11, 12)),
    ):
        world.place_building(0, kind, position)
    camp = camps.place_encounter(world, (19, 12), "wolf_outpost", watch=natural.center)
    # A prepared early economy: this test starts at the expansion decision,
    # rather than requiring a starved opening to fund its own expedition.
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for i, kind in enumerate([UnitType.FOOTMAN] * 4 + [UnitType.ARCHER] * 6 + [UnitType.CLERIC] * 2):
        tile = world.free_tile_near((hall.x, hall.y, hall.size, hall.size), prefer=(13.5 + i % 4, 10.5 + i // 4))
        assert tile is not None
        world.spawn_unit(0, kind, (tile[0] + .5, tile[1] + .5))
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (20.5, 9.5))
    world.time = 180
    world.update_vision()
    return world, camp, mains[0], natural


def drive_expansion(world, camp, main, natural, brain, *, destroy_lair=False, budget=400.0):
    """Think the live brain every fourth step to the budget, recording the chain's milestones.

    With *destroy_lair* the lair falls by fixture the moment its encounter is discovered, while its
    guards stand: lair-only destruction, which must never read as permission to build.
    """
    from warband.brains.ai import CAMP_REACH, guarded

    milestones = {"guards": len(camp.guards)}
    destroyed = False
    for step in range(int(budget / SIM_DT)):
        if step % 4 == 0:
            brain.think(world, random.Random(3))
        world.step()
        t = world.time
        knowledge = world.worker_knowledge[0]
        if camp.lair in knowledge.encounters and "seen" not in milestones:
            milestones["seen"] = round(t, 1)
        if destroy_lair and "seen" in milestones and not destroyed and camp.lair in world.buildings:
            world.buildings[camp.lair].hp = 0  # staged, as other tests raze with hp = 0
            destroyed = True
        if destroyed and camp.lair not in world.buildings and "fell" not in milestones:
            milestones["fell"] = round(t, 1)
            milestones["guards_stood"] = sum(1 for uid in camp.guards if uid in world.units)
            milestones["guarded_at_fell"] = guarded(world, 0, natural.center)
        if camp.cleared and "cleared" not in milestones:
            milestones["cleared"] = round(t, 1)
            milestones["fallen"] = {lair: dict(kills) for lair, kills in knowledge.fallen_guards.items()}
        # A hall counts for this chain only on the ground the camp holds: the same
        # reach the planner avoids, so a hall beyond the watch is no violation.
        anchor = camps.centre(world, camp)
        halls = [b for b in world.player_buildings(0, BuildingType.TOWN_HALL)
                 if dist(b.center, anchor) < CAMP_REACH]
        if halls and "frame" not in milestones:
            milestones["frame"] = round(t, 1)
            milestones["main_gold"] = main.gold
        done = [b for b in halls if b.done]
        if done and "hall" not in milestones:
            milestones["hall"] = round(t, 1)
            milestones["gold_at_hall"] = natural.gold
        if ("hall" in milestones and natural.gold <= milestones["gold_at_hall"] - 500
                and "worked" not in milestones):
            milestones["worked"] = round(t, 1)
            break
    return milestones


@pytest.mark.slow
def test_a_cleared_camp_unlocks_its_guarded_expansion():
    """Slow: seed-1003 Plains through the live Pro brain: the den is scouted, cleared by recorded combat with
    witnessed casualties, then the natural is framed, finished and worked; the casualty memory rides the
    owner's own snapshot and leaks to no other seat."""
    from warband.brains.ai import guarded
    from warband.online.authority import WarbandMatch

    world, camp, main, natural = expansion_world()
    assert guarded(world, 0, natural.center)  # the scout has seen its expansion guard
    brain = ProBrain(0, PRO)
    milestones = drive_expansion(world, camp, main, natural, brain)
    assert milestones["seen"] < milestones["cleared"] < milestones["frame"] < milestones["hall"] < milestones["worked"], milestones
    assert camp.cleared
    assert camp.lair in world.worker_knowledge[0].cleared_encounters
    fallen = world.worker_knowledge[0].fallen_guards.get(camp.lair, {})
    assert sum(fallen.values()) == milestones["guards"], milestones
    assert not guarded(world, 0, natural.center)
    assert milestones["main_gold"] < 1200, "the old mine was still full when the natural was claimed"

    match = WarbandMatch(seed=81)
    match.world = world
    match.begun = world.to_dict()["terrain"]
    expected = {lair: dict(kills) for lair, kills in world.worker_knowledge[0].fallen_guards.items()}
    for seat in range(world.seats):
        client = World.from_dict(match.snapshot(seat)["world"])
        assert client.worker_knowledge[0].fallen_guards == (expected if seat == 0 else {}), seat
        assert client.worker_knowledge[1].fallen_guards == {}, seat


@pytest.mark.slow
def test_a_fallen_lair_alone_keeps_its_expansion_guarded():
    """Slow: the same staging, but the lair falls on discovery with its guards standing: the natural stays
    avoided until the guards themselves are cleared, and any hall still waits for that completion."""
    from warband.brains.ai import guarded

    world, camp, main, natural = expansion_world()
    brain = ProBrain(0, PRO)
    milestones = drive_expansion(world, camp, main, natural, brain, destroy_lair=True)
    assert milestones["fell"] >= milestones["seen"], milestones
    assert milestones["guards_stood"] > 0, "the lair must fall with its guards standing"
    assert milestones["guarded_at_fell"], milestones
    assert camp.lair not in world.buildings
    if "cleared" not in milestones:
        assert not camp.cleared
        assert guarded(world, 0, natural.center)
        assert "frame" not in milestones, milestones
    else:
        assert camp.lair in world.worker_knowledge[0].cleared_encounters
        if "frame" in milestones:
            assert milestones["frame"] > milestones["cleared"], milestones


def test_ordinary_destinations_avoid_both_a_den_and_its_guarded_mine():
    """A discovered off-site expansion watch is unsafe even well away from its den."""
    from warband.brains.ai import CAMP_REACH, camp_safe_point

    world, _army = match()
    camp = camps.place_encounter(world, (30, 20), "wolf_outpost", watch=(23.5, 21.5))
    world.reveal_all(0)
    for anchor in (camps.centre(world, camp), camp.watch):
        destination = camp_safe_point(world, 0, anchor)
        assert world.passable(int(destination[0]), int(destination[1]))
        assert dist(destination, camps.centre(world, camp)) > CAMP_REACH
        assert dist(destination, camp.watch) > CAMP_REACH


def test_a_wounded_flyer_withdraws_from_a_guardians_longer_air_attack():
    """A guardian's ranged air shot threatens a flyer beyond its ground melee reach."""
    world, army = match()
    guardian = world.spawn_unit(world.neutral, UnitType.ANCIENT_GUARDIAN, (26.5, 20.5))
    flyer = world.spawn_unit(0, UnitType.GRYPHON, (30.5, 20.5))
    flyer.hp = max(1, int(flyer.max_hp * .2))
    world.hold([flyer.id])
    world.reveal_all(0)
    assert world.is_visible(0, guardian.tile)
    assert world.range_of(guardian) + 2 < dist(guardian.pos, flyer.pos) < world.strike_range(guardian, flyer)
    brain = ProBrain(0, replace(PRO, scout=False))
    brain.think(world, random.Random(11))
    assert isinstance(flyer.order, Move)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    assert dist(flyer.order.target, hall.center) < 10
    # Losing sight of the attacker must not reclaim the patient's retreat.
    guardian.hp = 0
    world.step()
    world.time += 1
    brain.think(world, random.Random(11))
    assert isinstance(flyer.order, Move)
    assert dist(flyer.order.target, hall.center) < 10
    healer = world.spawn_unit(0, UnitType.CLERIC, (3.5, 8.5))
    world.hold([healer.id])
    for _ in range(round(35 / SIM_DT)):
        world.step()
        brain.think(world, random.Random(11))
        if flyer.hp >= PRO.rejoin_hp * flyer.max_hp:
            break
    assert flyer.hp >= PRO.rejoin_hp * flyer.max_hp
    world.time += 1
    brain.think(world, random.Random(11))
    assert isinstance(flyer.order, AttackMove)


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_two_soldiers_collect_a_camp_whose_guards_they_saw_fall(kind):
    """A witnessed empty den needs cleanup, not a new full-sized combat wave."""
    world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2, rng=random.Random(11), scripted=True)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (62, 40))
    world.players[0].gold = world.players[0].lumber = 0
    camp = camps.place_encounter(world, (24, 19), "wolf_outpost")
    world.reveal_all(0)
    for uid in camp.guards:
        world.units[uid].hp = 0
    world.step()
    party = [world.spawn_unit(0, UnitType.FOOTMAN, (10.5 + i, 12.5)) for i in range(2)]
    world.time = 180
    brain = Brain(0, Difficulty.MEDIUM) if kind == "medium" else ProBrain(0, replace(PRO, scout=False))
    brain.think(world, random.Random(11))
    assert all(isinstance(unit.order, AttackMove) and dist(unit.order.target, camps.centre(world, camp)) < 6
               for unit in party)
    for _ in range(round(60 / SIM_DT)):
        world.step()
        brain.think(world, random.Random(11))
        if camp.cleared:
            break
    assert camp.cleared
    assert all(unit.id in world.units for unit in party)
    assert world.players[0].stats["bounty_gold"] == camp.gold
