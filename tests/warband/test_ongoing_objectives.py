"""Conditions that must still hold at victory keep their HUD state truthful."""

from dataclasses import replace

from warband.story.campaign import Objective, Run
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN


def test_an_ongoing_objective_reopens_and_only_reports_real_changes() -> None:
    """A present-tense condition differs from an action already performed, including after load."""
    base = build_world(CAMPAIGN.missions[0], flags={})
    mission = replace(base.mission, objectives=(
        Objective("present", "The crew must be here", lambda run: bool(run.get("here")), ongoing=True),
        Objective("arrived", "Bring the crew here once", lambda run: bool(run.get("here"))),
    ), triggers=(), win=lambda run: False)
    run = Run(mission, base.world, flags={"here": True})
    run.tick()
    assert run.state == {"present": "done", "arrived": "done"}
    run.completed.clear()
    run.tick()
    assert run.completed == [], "an unchanged checkmark does not repeat its notification"
    run = Run.from_dict(mission, base.world, run.to_dict())
    run.set("here", False)
    run.tick()
    assert run.state == {"present": "open", "arrived": "done"}
    run.set("here", True)
    run.tick()
    assert run.completed == ["present"]
