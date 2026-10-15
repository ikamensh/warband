"""Authored mission checkpoints reached through public orders for UI verification.

The caravan's ruins are actually salvaged and Wrenna actually reaches the parley.
The caller still answers the queued grove choice through DialogScene; no objective
state, unit position or story answer is manufactured here.
"""

from warband.story.campaign import Run
from warband.story.catalog import UNDERTOW
from warband.story.mission_scene import build_world
from tools.play_undertow import play_until, workers


def reached_keeper_phase(mission_id: str) -> Run:
    """The real opening, post-salvage caravan, or grove at its offered plan choice."""
    run = build_world(UNDERTOW.mission(mission_id), flags={})
    if mission_id == "undertow_caravan":
        def strip(current: Run) -> None:
            ruins = [building for building in current.world.buildings.values() if building.player == 2]
            for worker in workers(current):
                if not worker.orders and ruins:
                    current.world.salvage([worker.id], ruins[0].id)

        play_until(run, lambda current: current.state.get("strip") == "done", seconds=600,
                   act=strip, what="Old Camp stripped for HUD verification")
    elif mission_id == "undertow_grove":
        run.world.move([run.unit("wrenna").id], (29.5, 27.5))
        play_until(run, lambda current: "grove_plan" in current.fired, seconds=420,
                   what="grove plan offered for HUD verification")
    return run
