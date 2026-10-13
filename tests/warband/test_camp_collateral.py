"""A rival's expedition must not enlist unrelated workers beyond the camp's alarm."""

import json
from pathlib import Path

from warband.sim.model import World, dist
from warband.sim.rules import CAMP_WATCH, SIM_DT


def test_a_roused_camp_keeps_its_real_opponent_without_acquiring_outside_workers():
    """Klondike1010 at 510 s: all guards fought Elf392, then enrolled uninvolved Orc35/124 outside Watch5.

    Preserve the actual terrain and local actors/orders; unrelated economy
    and brains are removed. The guard's legitimate fight must still happen,
    while workers seven/eight tiles off the den remain unharmed.
    """
    captured = json.loads((Path(__file__).with_name("fixtures") / "klondike1010_collateral.json").read_text())
    world = World.from_dict(captured["world"])
    # Normal checkpoints discard routes; this exact replay retains the
    # captured march that puts the real opponent under the guards' blows.
    for actor in captured["actors"]:
        unit = world.units[actor["id"]]
        unit.path = [tuple(point) for point in actor["path"]]
        unit.path_goal = tuple(actor["goal"]) if actor["goal"] is not None else None
        unit.exact = tuple(actor["exact"]) if actor["exact"] is not None else None
        unit.replan_at = actor["replan_at"]
        unit.progress = actor["progress"]
        unit.last_distance = actor["last_distance"]
    camp = world.camps[0]
    assert camp.roused
    workers = {uid: world.units[uid].hp for uid in (35, 124)}
    assert all(dist(world.units[uid].pos, camp.origin) > CAMP_WATCH for uid in workers)
    legitimate = False
    for _ in range(round(10 / SIM_DT)):
        world.step()
        events = world.take_events()
        legitimate |= any(event.kind == "hit" and event.entity in camp.guards and event.other == 392
                          for event in events)
        assert not any(event.kind == "hit" and event.entity in camp.guards and event.other in workers
                       for event in events)
    assert legitimate, "the camp must keep fighting its actual opponent"
    assert all(uid in world.units and world.units[uid].hp == hp for uid, hp in workers.items())
