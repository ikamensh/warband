"""Bastion1005: a defense withdrawal cannot choose another known camp as its rally ground."""

import json
import random
from pathlib import Path

import pytest
from tests.warband.brain_helpers import members, military
from warband.brains.pro_assignments import Duty

from warband.brains.ai import CAMP_REACH, Brain
from warband.brains.pro_ai import ProBrain
from warband.sim import camps
from warband.sim.model import Move, World, dist
from warband.sim.rules import CAMP_WATCH, Difficulty, SIM_DT, Terrain


def interrupted_expedition(kind):
    """Keep the real expedition, visible worker threat, scout and two camps from the captured decision."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "bastion1005_escape_destination.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2, scripted=True).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id", "rng", "regrowth", "theme", "layout", "magic", "wilds"):
        saved[key] = captured[key]
    remembered = [None if letter == "?" else letters[letter].value
                  for row in captured["known_terrain"] for letter in row]
    saved["worker_knowledge"][1] = dict(captured["knowledge"], terrain=remembered,
                                      buildings=captured["known_buildings"], mines=[])
    saved["explored"][1] = bytes(cell is not None for cell in remembered).hex()
    world = World.from_dict(saved)
    brain = ProBrain(1) if kind == "pro" else Brain(1, Difficulty.MEDIUM)
    state = captured["brain_state"]
    military(brain).creeping = state["creeping"]
    if kind == "pro":
        brain.army.assignments.assign(state["party"], Duty.CREEP)
    else:
        brain.creep_party = set(state["party"])
    military(brain).creep_strength = state["strength"]
    military(brain).creep_until = state["until"]
    military(brain).camp_at_launch = {int(lair): value for lair, value in state["launch"].items()}
    if kind == "medium":
        brain.creep_size = len(members(brain, Duty.CREEP))
    party = [world.units[uid] for uid in sorted(members(brain, Duty.CREEP))]
    return world, brain, party


@pytest.mark.parametrize("kind", ["pro", "medium"])
def test_projected_defense_retreat_stays_outside_every_other_known_camp(kind):
    """The actual seven-body withdrawal moves to safety without rousing or being struck by Cairn27."""
    world, brain, party = interrupted_expedition(kind)
    other = world.camp_for(27)
    assert world.is_visible(1, world.units[44].tile) and not other.roused
    brain.think(world, random.Random(11))
    assert military(brain).creeping is None and not members(brain, Duty.CREEP)
    assert all(isinstance(unit.order, Move) for unit in party)
    assert all(dist(unit.order.target, point) > CAMP_REACH
               for unit in party for _lair, point in camps.defended(world, 1))
    starts = {unit.id: unit.pos for unit in party}
    for _ in range(round(10 / SIM_DT)):
        world.step()
        for event in world.take_events():
            assert not (event.kind == "hit" and event.entity in other.guards
                        and event.other in starts), "the defense walk fed the unrelated camp"
        assert all(dist(unit.pos, camps.centre(world, other)) > CAMP_WATCH
                   for unit in party if unit.id in world.units)
    assert any(unit.id in world.units and dist(unit.pos, starts[unit.id]) > 3 for unit in party)
    assert not other.roused
