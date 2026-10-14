"""Finale regressions: the corrected release is played, and each ending faces its consequences."""

import pytest

from tools import play_undertow as solver
from warband.sim.rules import BuildingType as B, UnitType as U
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN


@pytest.mark.slow
def test_open_cannot_finish_until_issa_operates_the_corrected_relief_sluice() -> None:
    """Slow: destroy all three pylons with real orders, then operate the surveyed bypass.

    Demolition alone used to win while the story claimed a corrected procedure the player
    never performed. Issa stays at camp until the release actually needs her.
    """
    run = build_world(CAMPAIGN.mission("undertow_maw"), flags={})
    world = run.world
    world.hold([u.id for u in run.units(0, U.PEASANT)])

    def demolish(r):
        solver.train(r, B.BARRACKS, U.FOOTMAN, 16)
        for pos in (tuple(p) for p in r.get("pylon_pos")):
            pylon = solver.building_at(r, 1, B.FARM, pos)
            if pylon is not None:
                solver.attack_building(r, pylon.id)
                army = [u.id for u in r.soldiers(0) if u.id != r.get("issa")]
                r.world.attack_move(army, pylon.center)
                return
        solver.fight(r, tuple(r.get("camp_center")), sides=(1, 2), exclude=(r.get("issa"),))

    solver.play_until(run, lambda r: all(solver.building_at(r, 1, B.FARM, tuple(p)) is None
                                        for p in r.get("pylon_pos")) and not r.units(2),
                      seconds=600, act=demolish, what="demolition and any uncontrolled bloom")
    assert not run.won, "destroying pylons cannot substitute for the corrected release"
    assert not run.get("maw_relief_open")

    issa = run.unit("issa")
    world.move([issa.id], tuple(run.get("relief_sluice")))
    solver.solve_maw(run, ending="open")
    assert run.won and run.get("maw_relief_open")
    assert run.remembered()["undertow_ending_open"]
