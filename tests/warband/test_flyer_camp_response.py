"""Forest1001: answering an enemy flyer must not volunteer an idle shooter for a known Stone Cairn."""

import json
from pathlib import Path

from warband.brains.ai import CAMP_REACH, answer_flyers
from warband.sim import camps
from warband.sim.model import AttackMove, World, dist
from warband.sim.rules import SIM_DT, Terrain


def test_answering_a_flyer_does_not_start_an_unprepared_neutral_fight():
    """The real idle archer answers a flyer over our farm, survives, and never shoots the calm guards."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "forest1001_flyer_response.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2, scripted=True).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id", "rng", "regrowth"):
        saved[key] = captured[key]
    remembered = [None if letter == "?" else letters[letter].value
                  for row in captured["known_terrain"] for letter in row]
    saved["worker_knowledge"][1] = dict(captured["knowledge"], terrain=remembered,
                                      buildings=captured["known_buildings"], mines=[])
    saved["explored"][1] = bytes(letter is not None for letter in remembered).hex()
    world = World.from_dict(saved)
    archer, flyer, camp = world.units[385], world.units[357], world.camps[0]
    assert not archer.orders and not camp.roused
    assert world.is_visible(1, flyer.tile)
    answer_flyers(world, 1, [archer], 9.0)
    assert isinstance(archer.order, AttackMove), "the real flyer response must still be dispatched"
    assert dist(archer.order.target, camps.centre(world, camp)) > CAMP_REACH
    hits_on_flyer = 0
    for _ in range(round(24 / SIM_DT)):
        world.step()
        for event in world.take_events():
            if event.kind == "hit" and event.entity == archer.id:
                assert event.other not in {camp.lair, *camp.guards}, "the ordinary air response attacked guards"
                hits_on_flyer += event.other == flyer.id
    assert hits_on_flyer, "avoiding the camp must still allow the shooter to answer the actual flyer"
    assert archer.id in world.units and archer.hp == archer.max_hp
    assert not camp.roused
