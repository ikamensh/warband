"""Finale regressions: the corrected release is played, and each ending faces its consequences."""

import pytest

from tools import play_undertow as solver
from warband.sim.rules import BuildingType as B, UnitType as U
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN


@pytest.mark.parametrize("mill_held", [False, True])
def test_the_heart_stone_muster_reports_the_aether_that_fits_the_camp(mill_held) -> None:
    """The core's advertised grant agrees with the purse in either camp-capacity branch."""
    mission = CAMPAIGN.mission("undertow_maw")
    baseline = build_world(mission, flags={"undertow_mill_vault": mill_held})
    core = build_world(mission, flags={"undertow_mill_vault": mill_held, "undertow_guardian_core": True})
    grant = core.world.players[0].aether - baseline.world.players[0].aether
    assert core.get("maw_core_aether") == grant
    solver.play_until(core, lambda run: "muster" in run.fired, seconds=2, what="core muster")
    assert any(f"(+{grant} aether)" in line for _, lines in core.notes for line in lines)


def test_open_release_accepts_an_open_hand_already_eliminated() -> None:
    """A side already out before release cannot be asked to resign a second time."""
    run = build_world(CAMPAIGN.mission("undertow_maw"), flags={})
    run.world.resign(1)  # Public faction withdrawal models the same eliminated-side state as total defeat.
    run.world.move([run.get("issa")], tuple(run.get("relief_sluice")))
    solver.play_until(run, lambda r: "pylons_down" in r.fired, seconds=30, what="release after faction defeat")
    assert not run.units(1) and not run.world.players[1].alive
    assert run.units(2), "the bloom remains an actual concluding encounter"


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


@pytest.mark.slow
def test_ground_commitment_shows_only_its_work_and_faces_the_thinned_seam() -> None:
    """Slow: a completed real vault commits GROUND before enough aether can win.

    Previously all ending checks stayed available, and fast play escaped every mined-seam
    consequence. The committed works and crisis must also survive saving mid-mission.
    """
    from warband.sim.model import World
    from warband.story.campaign import Run

    run = build_world(CAMPAIGN.mission("undertow_maw"), flags={"undertow_seam_mined": True})
    world = run.world
    world.hold([u.id for u in run.units(0, U.PEASANT)])
    worker = run.units(0, U.PEASANT)[0]
    position = tuple(run.get("maw_rifts")[0])
    world.move([worker.id], (position[0] + 1.0, position[1] + 1.0))
    solver.play_until(run, lambda r: r.world.can_place(B.VAULT, position, 0, builder=worker.id) is None,
                      seconds=90, what="builder reaches first rift")
    world.build(worker.id, B.VAULT, position)
    solver.play_until(run, lambda r: bool(r.get("ending_path")), seconds=90, what="first vault completed")
    assert run.get("ending_path") == "ground"
    assert run.state["sealed"] == run.state["open"] == "hidden"
    assert run.units(2), "the thinned seam must react at commitment, before a fast victory"
    assert not run.won

    loaded = Run.from_dict(run.mission, World.from_dict(world.to_dict()), run.to_dict())
    assert loaded.state == run.state
    assert loaded.get("ending_path") == "ground"
    solver.solve_maw(loaded, ending="ground")
    assert loaded.won
    assert loaded.state["issa"] == loaded.state["hall"] == "done"
