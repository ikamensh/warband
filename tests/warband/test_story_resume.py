"""Story queues must survive a mission save, so a fired trigger cannot lose its question."""

import json

from warband.sim.model import World
from warband.story.campaign import Choice, Line, Option, Run
from warband.story.mission_scene import build_world
from warband.story.missions import CAMPAIGN


def test_a_saved_trigger_keeps_its_queued_dialogue_and_question() -> None:
    """A save between queued conversations preserves their order and conditional lines."""
    mission = CAMPAIGN.missions[0]
    run = build_world(mission, flags={})
    first = (Line("Maren", "The road is open.", when="road_open"),)
    second = (Choice("trust", "Aldric", "Carry the news?", (Option("Carry it", True), Option("Stay", False))),
              Line("Maren", "Then we go.", when="trust", unless="road_closed"))
    run.say(*first)
    run.say(*second)
    run.set("road_open", True)
    saved = json.loads(json.dumps({"world": run.world.to_dict(), "mission": run.to_dict()}))
    resumed = Run.from_dict(mission, World.from_dict(saved["world"]), saved["mission"])
    assert resumed.pending == [first, second]
    assert resumed.pending[0][0].spoken(resumed.vars)
