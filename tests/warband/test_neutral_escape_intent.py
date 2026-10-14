"""Escaping one remembered danger retains the unit's deliberate encounter intent."""

import json
from pathlib import Path

import pytest

from tools.fuzz import check_progress
from warband.sim import camps
from warband.sim.model import Attack, AttackMove, World, dist
from warband.sim.rules import SIM_DT, BuildingType, Race, Terrain, UnitType


def captured_knight():
    """Fuzz81's sole walker and remembered danger; combat actors are unnecessary for this deadlock."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "fuzz81_knight_escape.json").read_text())
    kinds = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[kinds[cell] for cell in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2,
                  races=[Race.DWARF, Race.HUMAN], scripted=True).to_dict()
    for field in ("time", "tick", "next_id"):
        saved[field] = captured[field]
    saved["units"] = [captured["unit"]]
    remembered = [None if cell == "?" else kinds[cell].value
                  for row in captured["known_terrain"] for cell in row]
    saved["worker_knowledge"][0] = dict(captured["knowledge"], terrain=remembered)
    saved["explored"][0] = bytes(cell is not None for cell in remembered).hex()
    saved["players"][0]["upgrades"] = captured["upgrades"]
    world = World.from_dict(saved)
    [knight] = world.player_units(0)
    return world, knight


def test_a_guard_warning_does_not_deadlock_movement_at_a_deliberately_chosen_camp():
    """Fuzz 81 at 841.05 s: a warning's escape route must still admit the chosen encounter.

    The fixture keeps exact x=99..117/y=38..57 terrain, remembered terrain,
    knight 2511's position and queued orders, and its two remembered dangers.
    Player 2 becomes seat 0 and coordinates are translated; no path internals
    or combat modifications are necessary to reproduce the 20 second deadlock.
    """
    world, knight = captured_knight()
    origin = knight.pos
    destination = knight.orders[-1].target
    stalled = {}
    for tick in range(round(25 / SIM_DT)):
        world.step()
        world.take_events()
        if tick % 20 == 0:
            check_progress(world, stalled)
    assert dist(knight.pos, origin) > 1.0
    assert not knight.orders, "the retreat and queued expedition must both finish"
    assert dist(knight.pos, destination) < 1.0


@pytest.mark.parametrize("mine_aim", [True, False])
def test_only_a_deliberate_mine_aim_engages_its_visible_quiet_guards(mine_aim):
    """Explicit mine attack-move is an encounter intent; a passing march leaves quiet defenders alone."""
    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2, scripted=True)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (23, 19))
    camp = camps.place_encounter(world, (15, 8), "spider_hollow", watch=mine.center)
    archer = world.spawn_unit(0, UnitType.ARCHER, (30.0, 20.5))
    world.reveal_all(0)
    target = mine.center if mine_aim else (40.0, 20.5)
    world.attack_move([archer.id], target)
    for _ in range(camps.EVERY):
        world.step()
    assert not camp.roused, "the order must be checked before proximity wakes the camp"
    if mine_aim:
        assert isinstance(archer.order, Attack) and archer.order.target in camp.guards
    else:
        assert isinstance(archer.order, AttackMove) and archer.order.target == target
