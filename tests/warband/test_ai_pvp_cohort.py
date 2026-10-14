"""Klondike1007: a healthy cohesive army already fighting rivals is not a free camp opportunity."""

import json
import random
from warband.brains.pro_assignments import Duty
from pathlib import Path

from warband.brains.ai import prepared_cohort
from warband.brains.pro_ai import ProBrain
from warband.sim import camps
from warband.sim.model import Attack, AttackMove, Hold, World, dist
from warband.sim.rules import BuildingType, SIM_DT, Terrain, UnitType


def captured_skirmish(*, rivals=True):
    """Keep actual own orders and visible actors; rival commands carry no information."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "klondike1007_active_pvp.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2, scripted=True).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id"):
        saved[key] = captured[key]
    if not rivals:
        saved["units"] = [unit for unit in saved["units"] if unit["player"] != 0]
    remembered = [None if letter == "?" else letters[letter].value
                  for row in captured["known_terrain"] for letter in row]
    saved["worker_knowledge"][1] = dict(captured["knowledge"], terrain=remembered,
                                      buildings=captured["known_buildings"], mines=[])
    saved["explored"][1] = bytes(letter is not None for letter in remembered).hex()
    return World.from_dict(saved)


def test_an_active_visible_rival_fight_is_not_replaced_by_an_outpost_march():
    """The real six-body Dwarf group keeps its ongoing fight despite no strategic attack flag."""
    world = captured_skirmish()
    assert all(not unit.orders for unit in world.player_units(0))
    own = world.player_units(1)
    assert any(isinstance(unit.order, Attack) for unit in own)
    brain = ProBrain(1)
    brain.think(world, random.Random(11))
    assert brain.army.creeping is None
    site = camps.centre(world, world.camps[0])
    assert not any(isinstance(unit.order, AttackMove) and dist(unit.order.target, site) < 6
                   for unit in own)


def test_expired_rival_attack_orders_do_not_hold_a_prepared_cohort_back():
    """Once those rival targets are gone, the same healthy force can volunteer without waiting on stale orders."""
    world = captured_skirmish(rivals=False)
    brain = ProBrain(1)
    brain.think(world, random.Random(11))
    assert brain.army.creeping == world.camps[0].lair
    assert len(brain.army.assignments.members(Duty.CREEP)) == 6


def test_a_target_just_killed_or_a_neutral_target_does_not_mark_a_rival_fight():
    """Current dead targets and deliberate camp commands remain eligible for neutral preparation."""
    world = captured_skirmish()
    soldier = world.units[76]
    target = world.entity(soldier.order.target)
    target.hp = 0  # the visible target dies before this frame's removal pass
    assert prepared_cohort(world, [soldier]) == [soldier]
    world.reveal_all(1)
    world.attack([soldier.id], world.camps[0].guards[0])
    assert prepared_cohort(world, [soldier]) == [soldier]


def test_held_troops_fighting_the_same_visible_rivals_are_busy():
    """A held weapon's automatic target is the same ongoing rival fight as an attack order."""
    world = captured_skirmish()
    own = world.player_units(1)
    world.hold([unit.id for unit in own])
    for _ in range(5):
        world.step()  # held weapons acquire actual targets on the fifth-tick combat pass
    assert any(isinstance(unit.order, Hold) and unit.order.target is not None for unit in own)
    brain = ProBrain(1)
    brain.think(world, random.Random(11))
    assert brain.army.creeping is None


def test_a_target_inside_a_mine_is_not_a_visible_rival_fight():
    """A real miner can enter after the striker's step, leaving one legal attack order queued."""
    world = World(40, 36, [[Terrain.GRASS] * 40 for _ in range(36)], 2, scripted=True)
    soldier = world.spawn_unit(1, UnitType.FOOTMAN, (23.5, 17.5))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (22, 22))
    worker = world.spawn_unit(0, UnitType.PEASANT, (23.5, 21.6))
    world.update_vision()
    world.attack([soldier.id], worker.id)
    world.harvest([worker.id], mine.id)
    world.step()
    assert worker.hidden and world.is_visible(1, worker.tile)
    assert isinstance(soldier.order, Attack)
    assert prepared_cohort(world, [soldier]) == [soldier]


def test_an_unseen_target_does_not_change_readiness_with_its_hidden_health():
    """A worker outruns a real chasing footman into fog while the attack is still queued."""
    world = World(48, 36, [[Terrain.GRASS] * 48 for _ in range(36)], 2, scripted=True)
    soldier = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 10.5))
    worker = world.spawn_unit(0, UnitType.PEASANT, (15.5, 10.5))
    world.update_vision()
    world.attack([soldier.id], worker.id)
    world.move([worker.id], (40.5, 10.5))
    for _ in range(round(6 / SIM_DT)):
        world.step()
        if not world.is_visible(1, worker.tile):
            break
    assert not world.is_visible(1, worker.tile)
    assert isinstance(soldier.order, Attack)
    ready = prepared_cohort(world, [soldier])
    worker.hp = 0  # unseen health is a counterfactual; it cannot alter this seat's decision
    assert prepared_cohort(world, [soldier]) == ready == [soldier]
