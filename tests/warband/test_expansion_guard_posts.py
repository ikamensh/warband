"""A watched mine announces its defenders before an automatic worker walks into it."""

import json
from pathlib import Path

import pytest

from warband.sim import camps
from warband.sim.model import TOUCH, World, dist, rect_gap
from warband.sim.rules import SIM_DT, BuildingType, Race, Terrain, UnitType


def approaching_worker():
    """Forest1006's exact approach, terrain and resource memory, without irrelevant armies."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "forest1006_expansion_worker.json").read_text())
    kinds = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[kinds[cell] for cell in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2,
                  races=[Race.DWARF, Race.HUMAN], scripted=True).to_dict()
    for field in ("time", "tick", "rng"):
        saved[field] = captured[field]
    saved["units"] = [captured["unit"]]
    saved["buildings"] = captured["buildings"]
    saved["players"][1] = captured["player"]
    remembered = [None if cell == "?" else kinds[cell].value
                  for row in captured["known_terrain"] for cell in row]
    saved["worker_knowledge"][1] = dict(captured["knowledge"], terrain=remembered)
    saved["explored"][1] = bytes(cell is not None for cell in remembered).hex()
    saved["next_id"] = 17  # reproduce the original canonical and mirrored camp identities
    world = World.from_dict(saved)
    camps.place_orbit(world, [(40, 15), (21, 30)], "spider_hollow",
                      [(False, False), (True, True)], watches=[(37.5, 15.5), (26.5, 32.5)])
    saved = world.to_dict()
    saved["next_id"] = captured["next_id"]
    world = World.from_dict(saved)
    camp = world.camp_for(20)
    assert camp is not None
    return world, camp, world.units[292]


def test_a_mirrored_expansion_posts_its_guards_where_an_approaching_worker_can_see_them():
    """Forest1006: the mine's defenders must be discovered before its hidden watch is entered.

    The real worker started at (45.4905,39.2008) with an automatic harvest
    order for mine 8 and no warning. Guards posted around the distant den
    let it enter the mine's watch before discovery and take needless damage.
    Construct the actual mirrored encounters through the public placement API.
    """
    world, camp, worker = approaching_worker()
    assert not world.worker_knowledge[1].guard_warnings
    assert camp.lair not in world.worker_knowledge[1].encounters
    discovered = False
    for _ in range(round(20 / SIM_DT)):
        world.step()
        events = world.take_events()
        assert worker.id in world.units
        knowledge = world.worker_knowledge[1]
        discovered |= (camp.lair in knowledge.encounters
                       or any(uid in knowledge.guard_warnings for uid in camp.guards))
        assert dist(worker.pos, camps.watch_of(world, camp)) >= camps.CAMP_WATCH
        assert not any(event.kind == "hit" and event.other == worker.id for event in events)
    assert discovered, "the approach must actually reveal the guards"
    assert worker.hp == worker.max_hp


@pytest.mark.parametrize("case", ["crossings1000", "bastion1003"])
def test_a_quiet_mine_alert_leaves_time_to_see_the_two_guards_from_their_angular_gap(case):
    """Real quiet camp approaches: distant den posts and a wide tripwire both caused blind worker deaths.

    Preserve each captured terrain, worker position/order, guard positions,
    buildings and resource memory. Irrelevant armies are removed; an ordinary
    automatic worker must discover the pair and turn away without provoking it.
    """
    captured = json.loads((Path(__file__).with_name("fixtures") / f"{case}_mine_alert.json").read_text())
    kinds = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[kinds[cell] for cell in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2,
                  races=[Race(player["race"]) for player in captured["players"] if not player["neutral"]],
                  scripted=True).to_dict()
    for field in ("units", "buildings", "camps", "players", "rng", "time", "tick", "next_id"):
        saved[field] = captured[field]
    owner = captured["owner"]
    remembered = [None if cell == "?" else kinds[cell].value
                  for row in captured["known_terrain"] for cell in row]
    saved["worker_knowledge"][owner] = dict(captured["knowledge"], terrain=remembered)
    saved["explored"][owner] = bytes(cell is not None for cell in remembered).hex()
    world = World.from_dict(saved)
    worker = world.units[captured["capture"]["actor"]]
    camp = world.camps[0]
    initial_hp = worker.hp
    assert not camp.roused
    assert camp.lair not in world.worker_knowledge[owner].encounters
    assert not any(uid in world.worker_knowledge[owner].guard_warnings for uid in camp.guards)
    discovered = False
    for _ in range(round(20 / SIM_DT)):
        world.step()
        events = world.take_events()
        assert worker.id in world.units
        knowledge = world.worker_knowledge[owner]
        discovered |= (camp.lair in knowledge.encounters
                       or any(uid in knowledge.guard_warnings for uid in camp.guards))
        assert not camp.roused, "the worker must turn away before provoking the quiet mine"
        assert not any(event.kind == "hit" and event.other == worker.id for event in events)
    assert discovered
    assert worker.hp == initial_hp


@pytest.mark.parametrize("point", [(x + 0.5, y + 0.5) for y in range(18, 23) for x in range(22, 27)
                                   if x in (22, 26) or y in (18, 22)])
def test_the_smaller_expansion_alarm_still_defends_every_legal_mining_mouth(point):
    """Every edge/corner mouth provokes the guards or is physically held by a posted guard's body."""
    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2, scripted=True)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (23, 19))
    camp = camps.place_encounter(world, (30, 19), "spider_hollow", watch=mine.center)
    worker = world.spawn_unit(0, UnitType.PEASANT, point)
    assert rect_gap(worker.pos, mine.rect) - worker.radius <= TOUCH
    world.hold([worker.id])
    for _ in range(camps.EVERY):
        world.step()
    assert camp.roused or rect_gap(worker.pos, mine.rect) - worker.radius > TOUCH
