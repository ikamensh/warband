"""The neutral gate measures real replacement losses and obtainable army clears."""

import random

import pytest

from tools.creep_report import Measurements, encounter
from warband.sim import camps
from warband.sim.model import World
from warband.sim.rules import CAMP_ENCOUNTERS, SIM_DT, Race, Terrain, UnitType


def test_a_neutral_kill_is_counted_at_the_victims_replacement_price():
    """The report must price the actual casualty, including its lumber, rather than count all units equally."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (14, 10), "wolf_den")
    guard = world.units[camp.guards[0]]
    victim = world.spawn_unit(0, UnitType.ARCHER, (guard.x + .8, guard.y))
    victim.hp = 1
    price = victim.info.cost
    measure = Measurements(world, ("human", "idle"))
    world.hold([victim.id])
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if victim.id not in world.units:
            break
    row = measure.finish(world)[0]
    assert row.lost == 1
    assert (row.loss_gold, row.loss_lumber) == (price.gold, price.lumber)
    assert row.gold == row.lumber == 0


def test_a_bystander_loss_is_not_a_clear_when_another_seat_claims_the_camp():
    """An incidental victim earns neither the other expedition's clear nor its bounty."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (14, 10), "wolf_den")
    guard = world.units[camp.guards[0]]
    victim = world.spawn_unit(0, UnitType.PEASANT, (guard.x + .8, guard.y))
    victim.hp = 1
    measure = Measurements(world, ("bystander", "expedition"))
    world.hold([victim.id])
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if victim.id not in world.units:
            break
    army = [world.spawn_unit(1, UnitType.KNIGHT, (8.5 + i % 4, 9.5 + i // 4)) for i in range(16)]
    world.reveal_all(1)
    world.attack_move([unit.id for unit in army], camp.posts[0])
    for _ in range(int(30 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if camp.cleared:
            break
    rows = {row.agent: row for row in measure.finish(world)}
    assert camp.cleared
    assert rows["expedition"].cleared
    assert not rows["bystander"].cleared
    assert rows["bystander"].lost == rows["bystander"].lost_workers == 1


@pytest.mark.slow
@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("identity", list(CAMP_ENCOUNTERS))
def test_every_race_can_clear_each_encounter_profitably_with_common_units(race, identity):
    """Slow: a complete multi-unit combat encounter through real orders and fixed simulation steps."""
    row = encounter(1000, race.value, identity)
    info = CAMP_ENCOUNTERS[identity]
    assert row.cleared, row
    assert (row.gold, row.lumber) == (info.gold, info.lumber)
    assert row.gold + row.lumber >= row.loss_gold + row.loss_lumber, row
    assert row.seconds > 0
