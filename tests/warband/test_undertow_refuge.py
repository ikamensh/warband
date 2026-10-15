"""The finale warns an approaching army about the occupied refuge before it can fire."""

import json

import pytest

from tools import play_undertow as solver
from warband.sim.model import World
from warband.sim.rules import UnitType as U
from warband.story.campaign import Run
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN


@pytest.mark.slow
def test_an_approaching_army_learns_who_is_in_the_refuge_before_firing_and_only_once():
    """Slow: a real scout reaches the warning perimeter; saving there must not replay the interruption."""
    run = build_world(CAMPAIGN.mission("undertow_maw"), flags={})
    world = run.world
    world.hold([unit.id for unit in run.units(0)])
    refuge = run.vars["landmarks"]["refuge_tower"]
    tower = world.buildings[run.get("sella_tower")]
    health = tower.hp
    scout = run.units(0, U.ARCHER)[0]
    # The east flank avoids the ring and the guarded south road. This is an ordinary move order.
    world.move([scout.id], (58.5, 40.5))
    world.move([scout.id], (52.5, 47.5), queue=True)
    solver.play_until(run, lambda r: "refuge_warning" in r.fired, seconds=100, what="occupied refuge warning")
    assert tower.hp == health and not run.won
    assert refuge["kind"] == "refuge"
    assert run.pending, "the names must be presented to the player, not only stored as a variable"
    run.pending.clear()  # The player dismisses the warning before saving.
    loaded = Run.from_dict(run.mission, World.from_dict(world.to_dict()), json.loads(json.dumps(run.to_dict())))
    solver.play_until(loaded, lambda r: r.time >= run.time + 1, seconds=2, what="resumed warning perimeter")
    assert not loaded.pending, "a witnessed warning must not interrupt again after resume"
    assert not loaded.get("ending_path"), "learning about the crew must not choose an ending"
