"""An expedition spends a healthy force that can fight together, not scattered reinforcements."""

import json
import random
from pathlib import Path

import pytest

from warband.brains.ai import Brain
from warband.brains.pro_ai import ProBrain
from warband.sim import camps
from warband.sim.model import AttackMove, World, dist
from warband.sim.rules import Difficulty, SIM_DT, Terrain


def scattered_army():
    """Crossings1001 just before the real launch: most of the army is at the razed rival base."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "crossings1001_scattered_army.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2, scripted=True).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id"):
        saved[key] = captured[key]
    remembered = [None if letter == "?" else letters[letter].value
                  for row in captured["known_terrain"] for letter in row]
    saved["worker_knowledge"][1] = dict(captured["knowledge"], terrain=remembered,
                                      buildings=captured["known_buildings"], mines=[])
    saved["explored"][1] = bytes(letter is not None for letter in remembered).hex()
    world = World.from_dict(saved)
    return world, world.camps[0]


@pytest.mark.parametrize("kind", ["medium", "pro"])
def test_scattered_distant_strength_does_not_send_a_lone_archer_ahead(kind):
    """The real 20-body quote must not launch archer 1039 with its screen 50 tiles away."""
    world, camp = scattered_army()
    brain = Brain(1, Difficulty.MEDIUM) if kind == "medium" else ProBrain(1)
    brain.think(world, random.Random(11))
    archer = world.units[1039]
    assert not (isinstance(archer.order, AttackMove)
                and dist(archer.order.target, camps.centre(world, camp)) < 6)
    assert archer.id not in brain.creep_party
    assert 130 not in brain.creep_party, "the real8HP footman is not prepared for another fight"
    # The force already together may still march: distant isolated arrivals
    # must not make a sufficient healthy cluster idle indefinitely.
    assert brain.creeping == camp.lair
    assert len(brain.creep_party) >= 6
    for _ in range(round(12 / SIM_DT)):
        world.step()
        world.take_events()
    assert archer.id in world.units, "the isolated arrival fed the camp before its real cohort arrived"
    assert archer.hp == archer.max_hp
