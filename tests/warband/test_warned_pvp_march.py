"""Plains1009: an ordinary push must react to armed guards it sees before their den is known."""

import json
import random
from pathlib import Path

from warband.brains.pro_ai import ProBrain
from warband.sim.model import Attack, AttackMove, Move, World, dist
from warband.sim.rules import SIM_DT, Terrain, UnitType


def warned_march():
    """Keep the real terrain, both warnings and all live movement state from the first sighting."""
    captured = json.loads((Path(__file__).with_name("fixtures") / "plains1009_warned_march.json").read_text())
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    rows = [[letters[letter] for letter in row] for row in captured["terrain"]]
    saved = World(len(rows[0]), len(rows), rows, 2, scripted=True).to_dict()
    for key in ("units", "players", "buildings", "camps", "time", "tick", "next_id", "rng", "theme", "layout", "magic", "wilds"):
        saved[key] = captured[key]
    remembered = [None if letter == "?" else letters[letter].value
                  for row in captured["known_terrain"] for letter in row]
    saved["worker_knowledge"][0] = dict(captured["knowledge"], terrain=remembered)
    saved["explored"][0] = bytes(cell is not None for cell in remembered).hex()
    world = World.from_dict(saved)
    for actor in captured["actors"]:
        unit = world.units[actor["id"]]
        # Routes/timers are exact runtime data omitted by World saves. Their old
        # approach is load-bearing: replanning on load hid the original failure.
        unit.path = [tuple(tile) for tile in actor["path"]]
        unit.path_goal = None if actor["goal"] is None else tuple(actor["goal"])
        unit.exact = None if actor["exact"] is None else tuple(actor["exact"])
        for key in ("replan_at", "progress", "last_distance"):
            setattr(unit, key, actor[key])
    brain = ProBrain(0)
    brain.attacking = True
    brain.target = (57.5, 34.5)
    brain.commit_strength = 85.0
    brain.next_think = world.time + 100  # guard reaction cannot wait for the next macro pass
    return world, brain


def test_a_new_guard_warning_breaks_off_the_unsafe_ordinary_push():
    """The two full-health archers stop the doomed march and leave without recruiting a neutral fight."""
    world, brain = warned_march()
    assert not world.worker_knowledge[0].encounters
    assert len(world.worker_knowledge[0].guard_warnings) == 2
    starts = {uid: world.units[uid].pos for uid in (67, 70)}
    brain.think(world, random.Random(11))
    assert not brain.attacking and brain.regroup_until > world.time
    assert all(isinstance(world.units[uid].order, Move) for uid in starts)
    brain.next_think = world.time  # real macro passes must honor regroup instead of restarting the old push
    rng = random.Random(11)
    for _ in range(round(10 / SIM_DT)):
        brain.think(world, rng)
        world.step()
        for event in world.take_events():
            assert not (event.kind == "hit" and event.entity in {16, 17} and event.other in starts)
    assert all(uid in world.units and world.units[uid].hp == world.units[uid].max_hp for uid in starts)
    assert all(dist(world.units[uid].pos, starts[uid]) > 1 for uid in starts)
    assert not world.camp_for(15).roused


def test_warning_response_keeps_a_deliberately_committed_camp_party():
    """The same sighting cannot cancel the neutral expedition that owns these two archers."""
    world, brain = warned_march()
    brain.creeping = 15
    brain.creep_party = {67, 70}
    world.attack_move([67, 70], world.camp_for(15).origin)
    brain.think(world, random.Random(11))
    assert all(isinstance(world.units[uid].order, AttackMove)
               and world.units[uid].order.target == world.camp_for(15).origin for uid in (67, 70))


def test_warning_response_preserves_visible_rival_combat():
    """Only ordinary marchers regroup; a recorded attack on a living visible rival keeps fighting."""
    world, brain = warned_march()
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (30.5, 17.5))
    world.update_vision()
    world.attack([70], enemy.id)
    brain.think(world, random.Random(11))
    assert isinstance(world.units[70].order, Attack) and world.units[70].order.target == enemy.id


def test_warning_response_preserves_patients_and_existing_escape_walks():
    """The newly seen guard does not overwrite an existing safe retreat with another assignment."""
    world, brain = warned_march()
    world.units[67].hp = 10
    brain._hurt.add(67)  # actual patient bookkeeping for the retained retreat control
    world.move([67, 70], (8.5, 8.5))
    brain.camp_escape[70] = world.time + 30
    brain.think(world, random.Random(11))
    assert all(isinstance(world.units[uid].order, Move)
               and world.units[uid].order.target == (8.5, 8.5) for uid in (67, 70))
