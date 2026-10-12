"""Forest1006: a seen guard makes its expansion unsafe before the den is discovered."""

import json
import random
from pathlib import Path

from warband.brains.ai import auto_site, camp_safe_point
from warband.sim import camps
from warband.sim.model import World, dist
from warband.sim.rules import BuildingType, Terrain
from warband.sim.worker_knowledge import KnownMine


def captured_expansion():
    """Keep the captured terrain, halls, mine and the seat's actual last guard sighting."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "forest1006_guarded_expansion.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    terrain = [[letters[letter] for letter in row] for row in captured["terrain"]]
    world = World(len(terrain[0]), len(terrain), terrain, 2, scripted=True)
    saved = world.to_dict()
    saved["buildings"] = captured["buildings"]
    saved["players"] = captured["players"]
    world = World.from_dict(saved)
    world.time = captured["time"]
    knowledge = world.worker_knowledge[1]
    knowledge.mines = {8: KnownMine(**captured["mine"])}
    knowledge.guard_warnings = {uid: tuple(point) for uid, point in captured["guard_warnings"]}
    return world, knowledge.mines[8].center


def test_seen_guard_blocks_automatic_expansion_before_its_den_is_known():
    """The public hall planner must wait; forgetting that sighting restores the real usable site."""
    world, mine = captured_expansion()
    assert not world.worker_knowledge[1].encounters
    assert auto_site(world, BuildingType.TOWN_HALL, 1, mine, random.Random(11)) is None
    # Another seat retaining the same sighting cannot block our expansion.
    world.worker_knowledge[0].guard_warnings.update(world.worker_knowledge[1].guard_warnings)
    world.worker_knowledge[1].guard_warnings.clear()
    assert auto_site(world, BuildingType.TOWN_HALL, 1, mine, random.Random(11)) is not None


def test_rally_avoids_the_same_guard_warning_before_its_den_is_known():
    """A rally at the captured mine must move clear using only its owner's sighting."""
    world, mine = captured_expansion()
    safe = camp_safe_point(world, 1, mine)
    assert all(dist(safe, point) > camps.GUARD_WARNING
               for point in world.worker_knowledge[1].guard_warnings.values())
