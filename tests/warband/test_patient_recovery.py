"""Seed230: waiting for healing that does not exist must not permanently retire a living army."""

import json
import random
from pathlib import Path

import pytest

from warband.brains.ai import make_brain, prepared_cohort
from warband.sim.model import Move, World
from warband.sim.rules import BuildingType, Difficulty, SIM_DT, Terrain, UnitType


def deadlocked_match():
    """Restore the exact world and the brain's actual bookkeeping, which a World save does not contain."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "seed230_patient_deadlock.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id", "rng", "regrowth", "theme", "layout", "magic", "wilds", "gates", "rifts", "gate_links"):
        saved[key] = captured[key]
    for seat, known in enumerate(captured["known_terrain"]):
        remembered = [None if letter == "?" else letters[letter].value for row in known for letter in row]
        saved["worker_knowledge"][seat] = dict(captured["knowledge"][seat], terrain=remembered)
        saved["explored"][seat] = bytes(cell is not None for cell in remembered).hex()
    world = World.from_dict(saved)
    brains = [make_brain(seat, Difficulty.MASTER, 230) for seat in range(2)]
    for brain, state in zip(brains, captured["brain_state"]):
        # These private fields restore real decision state omitted by World saves;
        # assertions below exercise public think, recorded orders and actual training.
        brain._hurt = set(state["hurt"])
        brain._seen = {int(seat): {UnitType(kind): count for kind, count in values.items()}
                       for seat, values in state["seen"].items()}
        brain._seen_at = {int(seat): when for seat, when in state["seen_at"].items()}
        for key in ("next_think", "next_combat", "attacking", "commit_strength", "regroup_until", "rush_over", "rush_drafted"):
            setattr(brain, key, state[key])
        brain.target = tuple(state["target"])
    rng = random.Random()
    state = captured["brain_rng"]
    rng.setstate((state[0], tuple(state[1]), state[2]))
    return world, brains, rng


def think_until_due(world, brains, rng):
    for _ in range(8):
        for brain in brains:
            brain.think(world, rng)
        world.step()


def test_unhealable_idle_patients_restore_the_real_army_and_worker_recovery():
    """The eventless Human–Orc position must regain ordinary combat and its affordable worker order."""
    world, brains, rng = deadlocked_match()
    patients = {uid for brain in brains for uid in brain._hurt}
    assert len(patients) == 34
    assert all(not world.units[uid].orders and not world.units[uid].info.regen for uid in patients)
    assert not any(unit.info.heal for unit in world.units.values())
    think_until_due(world, brains, rng)
    assert all(not brain._hurt for brain in brains)
    assert any(UnitType.PEASANT in hall.queue for hall in world.player_buildings(0, BuildingType.TOWN_HALL))
    assert any(world.units[uid].orders for uid in patients)
    # Release is for ordinary combat: low health still cannot fund a planned camp assault.
    assert not patients.intersection(unit.id for unit in prepared_cohort(world, world.player_units(0)))


@pytest.mark.parametrize("support", ["alive", "queued"])
def test_real_patients_wait_when_a_healer_is_alive_or_in_training(support):
    """A healing prospect retains the captured patients instead of spending their remaining health."""
    world, brains, rng = deadlocked_match()
    expected = set(brains[0]._hurt)
    if support == "alive":
        world.spawn_unit(0, UnitType.CLERIC, (15.5, 15.5))
    else:
        world.players[0].gold = world.players[0].lumber = 10000
        church = world.place_building(0, BuildingType.CHURCH, (15, 15))
        world.train(church.id, UnitType.CLERIC)
    think_until_due(world, brains, rng)
    assert expected <= brains[0]._hurt


def test_a_patient_finishes_its_retreat_before_rejoining_without_healing():
    """Lack of a healer cannot reclaim a soldier whose recorded walk to safety is still running."""
    world, brains, rng = deadlocked_match()
    uid = next(iter(brains[0]._hurt))
    world.move([uid], (15.5, 15.5))
    think_until_due(world, brains, rng)
    assert uid in brains[0]._hurt
    assert isinstance(world.units[uid].order, Move)


def test_natural_regeneration_keeps_a_patient_waiting_to_recover():
    """An actual regenerating treant remains a patient even without another healer."""
    world, brains, rng = deadlocked_match()
    tree = world.spawn_unit(0, UnitType.TREANT, (15.5, 15.5))
    brains[0]._hurt.add(tree.id)  # captured patient state with the regenerating-unit control
    tree.hp = 10
    think_until_due(world, brains, rng)
    assert tree.id in brains[0]._hurt
