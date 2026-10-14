"""A stronger brain transfers soldiers between duties without overlapping owners."""

import random
from dataclasses import replace

import pytest

from tests.warband.test_creeping_strategy import forest_expedition
from warband.brains.pro_ai import PRO, ProBrain
from warband.brains.pro_assignments import Duty
from warband.sim.model import Move, World, dist
from warband.sim.rules import BuildingType, Terrain, UnitType


def assert_exclusive(brain, world):
    """After a decision, every live soldier has one owner and dead ones have none."""
    assigned = [uid for duty in Duty for uid in brain.army.assignments.members(duty)]
    living = {unit.id for unit in world.player_units(brain.player) if not unit.is_worker and unit.hp > 0}
    assert len(assigned) == len(set(assigned))
    assert set(assigned) == living


def test_a_raider_becomes_a_patient_then_rejoins_and_is_released_on_death():
    """Recorded retreat replaces the raid immediately, before the next economic decision."""
    world = World(48, 40, [[Terrain.GRASS] * 48 for _ in range(40)], 2, scripted=True)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (40, 32))
    rider = world.spawn_unit(0, UnitType.KNIGHT, (10.5, 10.5))
    world.spawn_unit(1, UnitType.ARCHER, (12.5, 10.5))
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, raid=True, raiders=1, scout=False, creep=False))
    rng = random.Random(11)
    brain.think(world, rng)
    assert brain.army.assignments.duty(rider.id) is Duty.RAID
    assert_exclusive(brain, world)

    rider.hp = 1  # The same raider has just survived a blow in visible weapon range.
    world.time += brain.profile.combat_every
    brain.think(world, rng)
    assert brain.army.assignments.duty(rider.id) is Duty.HEAL
    assert not brain.army.assignments.members(Duty.RAID)
    assert isinstance(rider.order, Move)
    assert_exclusive(brain, world)

    rider.hp = rider.max_hp
    world.time += brain.profile.think_every
    brain.think(world, rng)
    assert brain.army.assignments.duty(rider.id) is Duty.RAID
    assert_exclusive(brain, world)

    rider.hp = 0
    world.step()
    brain.think(world, rng)
    assert brain.army.assignments.duty(rider.id) is None
    assert_exclusive(brain, world)


def test_a_vacant_raid_cannot_steal_a_knight_from_a_committed_expedition():
    """Forest1003: losing the detached rider cannot give a camp soldier two competing jobs."""
    world, camp, _army = forest_expedition()
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, raid=True, raiders=1, scout=False))
    rng = random.Random(11)
    brain.think(world, rng)
    assert brain.army.creeping == camp.lair
    party = set(brain.army.assignments.members(Duty.CREEP))
    assert party and any(world.units[uid].type is UnitType.KNIGHT for uid in party)
    [raider] = brain.army.assignments.members(Duty.RAID)
    assert raider not in party
    world.units[raider].hp = 0
    world.step()
    world.time += brain.profile.think_every
    brain.think(world, rng)
    assert not brain.army.assignments.members(Duty.RAID)
    assert set(brain.army.assignments.members(Duty.CREEP)) == party
    assert_exclusive(brain, world)


def test_a_blind_push_yielding_to_a_camp_ends_the_push_commitment():
    """Forest1003's prepared force can replace its guessed expedition with a concrete camp objective."""
    world, camp, troops = forest_expedition()
    world.update_vision()  # The camp is visible; the guessed rival base remains unexplored.
    brain = ProBrain(0, replace(PRO, scout=False))
    brain.army.attacking = True
    brain.army.target = (65.5, 43.5)
    brain.army.commit_strength = 100.0
    world.attack_move([unit.id for unit in troops], brain.army.target)
    brain.think(world, random.Random(11))
    assert brain.army.creeping == camp.lair
    assert brain.army.assignments.members(Duty.CREEP)
    assert not brain.army.attacking
    assert brain.army.target is None
    party = set(brain.army.assignments.members(Duty.CREEP))
    world.place_building(1, BuildingType.BARRACKS, (54, 30))
    world.reveal_all(0)  # A real sighting must not resurrect the superseded guessed push.
    world.time += brain.profile.think_every
    brain.think(world, random.Random(11))
    assert brain.army.creeping == camp.lair
    assert set(brain.army.assignments.members(Duty.CREEP)) == party
    assert not brain.army.attacking
    assert_exclusive(brain, world)


def test_tower_defense_interrupts_the_camp_and_keeps_its_departing_soldiers_safe():
    """Forest1003: a new home tower transfers the expedition to escape while a fresh defender strikes it."""
    from warband.sim import camps
    from warband.sim.model import Attack
    from warband.sim.rules import CAMP_WATCH, SIM_DT

    world, camp, troops = forest_expedition()
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False))
    rng = random.Random(11)
    brain.think(world, rng)
    party = set(brain.army.assignments.members(Duty.CREEP))
    assert party
    world.attack([unit.id for unit in troops[:6]], camp.guards[0])
    centre = camps.centre(world, camp)
    for _ in range(round(6 / SIM_DT)):
        world.step()
        if camp.roused and any(dist(unit.pos, centre) <= CAMP_WATCH + 1.0 for unit in troops[:6]):
            break
    assert camp.roused
    tower = world.place_building(1, BuildingType.TOWER, (10, 5))
    defender = world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 9.5))
    world.reveal_all(0)
    world.time += brain.profile.think_every
    brain.think(world, rng)
    assert brain.army.creeping is None
    assert not brain.army.assignments.members(Duty.CREEP)
    assert party == set(brain.army.assignments.members(Duty.ESCAPE))
    assert all(isinstance(world.units[uid].order, Move) for uid in party)
    assert isinstance(defender.order, Attack) and defender.order.target == tower.id
    assert_exclusive(brain, world)


@pytest.mark.parametrize("defender_count, feasible", [(1, False), (2, True)])
def test_a_young_tower_strike_counts_only_the_defenders_who_can_participate(defender_count, feasible):
    """Forest1003's camp cannot fund a premature strike while its own soldiers must escape first."""
    from warband.sim.model import Attack

    world, camp, _troops = forest_expedition()
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False))
    rng = random.Random(11)
    brain.think(world, rng)
    party = set(brain.army.assignments.members(Duty.CREEP))
    assert party
    tower = world.place_building(1, BuildingType.TOWER, (10, 5), done=False)
    defenders = [world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 9.5 + i)) for i in range(defender_count)]
    world.reveal_all(0)
    world.time += brain.profile.think_every
    brain.think(world, rng)
    if feasible:
        assert brain.army.creeping is None
        assert party == set(brain.army.assignments.members(Duty.ESCAPE))
        assert all(isinstance(unit.order, Attack) and unit.order.target == tower.id for unit in defenders)
    else:
        assert brain.army.creeping == camp.lair
        assert party == set(brain.army.assignments.members(Duty.CREEP))
        assert not brain.army.assignments.members(Duty.ESCAPE)
        assert all(not isinstance(unit.order, Attack) or unit.order.target != tower.id for unit in defenders)
    assert_exclusive(brain, world)


@pytest.mark.parametrize("reason", ["policy", "timeout"])
def test_ending_a_live_camp_replaces_its_orders_with_safe_escape(reason):
    """A stance change or abort cannot leave an untracked expedition on its old camp orders."""
    from warband.brains.ai import CAMP_REACH
    from warband.sim import camps

    world, camp, _troops = forest_expedition()
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, scout=False))
    rng = random.Random(11)
    brain.think(world, rng)
    party = set(brain.army.assignments.members(Duty.CREEP))
    assert brain.army.creeping == camp.lair and party
    if reason == "policy":
        brain.set_profile(replace(brain.profile, creep=False))
    else:
        brain.army.creep_until = world.time
    world.time += brain.profile.think_every
    brain.think(world, rng)
    assert brain.army.creeping is None
    assert not brain.army.assignments.members(Duty.CREEP)
    assert party == set(brain.army.assignments.members(Duty.ESCAPE))
    assert all(isinstance(world.units[uid].order, Move) for uid in party)
    assert all(dist(world.units[uid].order.target, point) > CAMP_REACH
               for uid in party for _lair, point in camps.defended(world, brain.player))
    assert_exclusive(brain, world)
