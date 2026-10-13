"""Automatic workers must retain observed creature danger when their sight recedes."""

import json
from pathlib import Path

from tools.fuzz import check_progress
from warband.sim import worker_ai
from warband.sim.model import World, dist
from warband.sim.rules import CAMP_POST, CAMP_WATCH, SIM_DT, Race, Terrain


def test_a_worker_escapes_a_remembered_guard_without_bouncing_as_sight_changes():
    """Fuzz seed 81: losing sight of the guardian must not reverse the worker's safe escape.

    The fixture retains the two actors, their orders and camp membership from
    3e20bc1 at 548.05 seconds, on the exact x=124..152, y=70..90 terrain and
    remembered-terrain crop. Coordinates are translated and player 4 is seat 0.
    Its tree-lined geometry is retained because the real worker stalled here.
    """
    captured = json.loads((Path(__file__).with_name("fixtures") / "fuzz81_guard_warning.json").read_text())
    terrain = {kind.value[0]: kind for kind in Terrain}
    rows = [[terrain[cell] for cell in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2,
                  races=[Race(captured["race"]), Race.HUMAN], scripted=True).to_dict()
    for field in ("units", "buildings", "camps", "time", "tick", "next_id"):
        saved[field] = captured[field]
    remembered = [None if cell == "?" else terrain[cell].value
                  for row in captured["known_terrain"] for cell in row]
    saved["worker_knowledge"][0] = dict(captured["knowledge"], terrain=remembered)
    saved["explored"][0] = bytes(cell is not None for cell in remembered).hex()
    saved["players"][0]["upgrades"] = captured["upgrades"]
    world = World.from_dict(saved)
    [worker] = world.player_units(0)
    knowledge = world.worker_knowledge[0]
    assert not knowledge.encounters
    [warning] = knowledge.guard_warnings.values()
    stalled = {}
    for tick in range(round(25 / SIM_DT)):
        world.step()
        world.take_events()
        if tick % 20 == 0:
            check_progress(world, stalled)
    assert worker.id in world.units
    assert dist(worker.pos, warning) > CAMP_WATCH + CAMP_POST + 1.0
    assert not worker_ai.safe_navigation(world, 0)[worker.tile[1] * world.width + worker.tile[0]]
