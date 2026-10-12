"""Local brains obey the same neutral completion memory as an online seat.

These tests are slow because a rival army really clears an encounter in fog,
then the observing army walks over to discover the result.
"""

import random

import pytest

from warband.brains.ai import Brain
from warband.brains.pro_ai import ProBrain
from warband.sim import camps
from warband.sim.model import AttackMove, World, dist
from warband.sim.rules import BuildingType, Difficulty, SIM_DT, Terrain, UnitType


def hidden_completion():
    """Keep the observer's memory while a real rival expedition removes the camp."""
    world = World(70, 48, [[Terrain.GRASS] * 70 for _ in range(48)], 2,
                  rng=random.Random(42), scripted=True)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (62, 40))
    world.players[0].gold = world.players[0].lumber = 0
    camp = camps.place_encounter(world, (24, 19), "wolf_outpost")
    site = camps.centre(world, camp)
    world.reveal_all(0)
    world.update_vision()
    assert not world.is_visible(0, (int(site[0]), int(site[1])))
    rivals = [world.spawn_unit(1, UnitType.KNIGHT, (26.5 + i % 3, 25.5 + i // 3))
              for i in range(12)]
    world.attack_move([unit.id for unit in rivals], site)
    uncleared = World.from_dict(world.to_dict())
    for _ in range(round(40 / SIM_DT)):
        world.step()
        if camp.cleared:
            break
    assert camp.cleared, "the rival expedition must really finish the hidden camp"
    assert not uncleared.camp_for(camp.lair).cleared
    assert camp.lair in world.worker_knowledge[0].buildings
    assert camp.lair not in world.worker_knowledge[0].cleared_encounters
    assert world.worker_knowledge[0].to_dict() == uncleared.worker_knowledge[0].to_dict()
    return world, uncleared, camp.lair, site


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_hidden_completion_does_not_change_an_expedition_before_the_seat_visits(kind):
    """Real hidden completion leaves both brains' remembered objective until their own army sees it."""
    completed, uncleared, lair, site = hidden_completion()
    observed_brain = None
    for world in (completed, uncleared):
        world.time = 180.0  # the same obtainable expedition decision, after the opening
        army = [world.spawn_unit(0, UnitType.FOOTMAN if i < 6 else UnitType.ARCHER,
                                 (10.5 + i % 3 * 1.3, 12.5 + i // 3 * 1.3))
                for i in range(12)]
        world.update_vision()
        assert not world.is_visible(0, (int(site[0]), int(site[1])))
        brain = Brain(0, Difficulty.MEDIUM) if kind == "medium" else ProBrain(0)
        brain.think(world, random.Random(11))
        assert brain.creeping == lair, "a hidden rival clear is still an unknown camp to this seat"
        assert all(isinstance(unit.order, AttackMove)
                   and dist(unit.order.target, site) < camps.CAMP_WATCH for unit in army)
        if world is completed:
            observed_brain = brain

    assert observed_brain is not None
    rng = random.Random(11)
    for _ in range(round(30 / SIM_DT)):
        completed.step()
        observed_brain.think(completed, rng)
        if lair in completed.worker_knowledge[0].cleared_encounters:
            break
        assert observed_brain.creeping == lair, "marching must not reveal hidden completion either"
    assert lair in completed.worker_knowledge[0].cleared_encounters
    completed.time += 1.0
    observed_brain.think(completed, rng)
    assert observed_brain.creeping is None, "observed completion releases the expedition"
