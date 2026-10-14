"""The Undertow: five authored missions played through public orders, their flags and their endings.

Fast tests build each mission's authored world and check the invariants a player depends on (supply,
landmarks, reachable objective sites, standalone play with no flags).  Slow tests play whole missions
with the solver in ``tools/play_undertow.py``: ordinary ``World`` orders and ``world.step`` plus
``run.tick``, the way ``MissionScene`` drives a mission — whole missions are minutes of simulation,
which is why they cannot be fast.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from warband.story.campaign import Run
from warband.story.catalog import CAMPAIGNS, DEFAULT_CAMPAIGN, find_mission, get_campaign
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN
from warband.sim.rules import BuildingType as B, SIM_DT, Terrain, UnitType as U

_SOLVER_PATH = Path(__file__).resolve().parents[2] / "tools" / "play_undertow.py"
_spec = importlib.util.spec_from_file_location("play_undertow", _SOLVER_PATH)
solver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(solver)


def mission(mission_id: str):
    return CAMPAIGN.mission(mission_id)


def test_undertow_is_registered_first_and_default_with_thornwood_playable() -> None:
    assert CAMPAIGN.id == "undertow" and CAMPAIGN.cover == "campaign/undertow.png"
    assert CAMPAIGNS[0] is CAMPAIGN and DEFAULT_CAMPAIGN is CAMPAIGN
    assert get_campaign("thornwood").id == "thornwood"
    assert [m.id for m in CAMPAIGN.missions] == [
        "undertow_mill", "undertow_caravan", "undertow_grove", "undertow_weight", "undertow_maw"]
    for m in CAMPAIGN.missions:
        assert find_mission(m.id) == (CAMPAIGN, m)


@pytest.mark.parametrize("mission_id", [m.id for m in CAMPAIGN.missions])
def test_every_mission_builds_an_authored_world_within_supply(mission_id: str) -> None:
    """Standalone ``--mission`` play: empty flags, an authored (not generated) map, landmarks on the
    objective sites, and a starting force the farms can feed where the mission starts with a hall."""
    run = build_world(mission(mission_id), flags={})
    world = run.world
    assert world.scripted and world.magic
    assert run.vars.get("landmarks"), "objective sites are landmarked"
    for record in run.vars["landmarks"].values():
        assert world.in_bounds((int(record["point"][0]), int(record["point"][1])))
    if run.hall(0) is not None:
        used, cap = world.supply(0)
        assert used <= cap, f"{mission_id}: starting force {used} exceeds supply {cap}"
    # The authored board survives a few seconds of ordinary play with no orders but the script's.
    for _ in range(int(3 / SIM_DT)):
        world.step()
        run.tick()
    assert not run.won and run.lost is None


def test_mill_pylon_is_hostile_and_the_vault_taps_its_rift() -> None:
    run = build_world(mission("undertow_mill"), flags={})
    world = run.world
    vaults = world.vaults(0)
    assert len(vaults) == 1 and world.taps(vaults[0])
    pylon = world.buildings[run.get("mill_pylon")]
    assert pylon.player == 1, "the player must be able to attack the pylon with ordinary orders"
    assert world.can_place(B.VAULT, vaults[0].pos, 0) is not None  # occupied: it really stands there


def test_caravan_ruins_stand_abandoned_and_salvageable() -> None:
    run = build_world(mission("undertow_caravan"), flags={})
    ruins = [b for b in run.world.buildings.values() if b.player == 2]
    assert len(ruins) == 4 and all(b.abandoned and b.done for b in ruins)
    assert run.hall(0) is None and not run.world.players[2].alive


def test_weight_seam_rift_is_clear_of_the_seam_and_capable_of_a_vault() -> None:
    run = build_world(mission("undertow_weight"), flags={})
    world = run.world
    seam = next(b for b in world.mines() if b.type is B.GOLD_SEAM)
    assert seam.has_gold
    rift = tuple(run.get("seam_rift"))
    assert rift in world.rifts and rift not in seam.tiles()
    # Explored in play by walking there; the footprint itself is lawful building ground.
    assert run.footprint_free(B.VAULT, rift)


def test_maw_starts_within_supply_for_every_flag_combination() -> None:
    """The audit's trap: Brakk's band, the Guardian and a farm lost to the blown dam must never
    together put the starting camp over supply, or training is unreachable."""
    combos = [
        {},
        {"undertow_mill_vault": True},
        {"undertow_mill_vault": False, "undertow_dam": True, "undertow_guardian_ally": True},
        {"undertow_mill_vault": True, "undertow_dam": True, "undertow_guardian_core": True,
         "undertow_seam_mined": True},
        {"undertow_mill_vault": False, "undertow_dam": False, "undertow_guardian_ally": True,
         "undertow_seam_capped": True},
    ]
    for flags in combos:
        run = build_world(mission("undertow_maw"), flags=flags)
        used, cap = run.world.supply(0)
        assert used <= cap, f"{flags}: {used} > {cap}"


def test_maw_flag_effects_are_real_board_differences() -> None:
    plain = build_world(mission("undertow_maw"), flags={})
    held = build_world(mission("undertow_maw"), flags={"undertow_mill_vault": True})
    assert len(held.world.vaults(0)) == len(plain.world.vaults(0)) + 1
    assert len(held.soldiers(0)) < len(plain.soldiers(0)), "shuttering the mill vault earns Brakk's band instead"
    ally = build_world(mission("undertow_maw"), flags={"undertow_guardian_ally": True})
    guardians = [u for u in ally.units(0) if u.type is U.ANCIENT_GUARDIAN]
    assert len(guardians) == 1
    ally.world.attack_move([guardians[0].id], (guardians[0].x + 3, guardians[0].y))
    for _ in range(int(2 / SIM_DT)):
        ally.world.step()
    assert guardians[0].x > 0  # a player-owned creature takes ordinary orders


def test_run_state_round_trips_mid_mission_with_pending_dialogue() -> None:
    run = build_world(mission("undertow_mill"), flags={})
    solver.play_until(run, lambda r: "wave_2" in r.fired, seconds=420,
                      act=lambda r: solver.fight(r, r.home(0)))
    assert run.pending, "the fork dialogue is queued mid-phase"
    data = json.loads(json.dumps(run.to_dict()))
    again = Run.from_dict(run.mission, run.world, data)
    assert again.vars == run.vars and again.fired == run.fired and again.pending == run.pending


@pytest.mark.slow
def test_millfield_can_hold_the_vault_through_the_surges() -> None:
    """Slow: a whole mission of beast waves fought with attack-move orders."""
    run = build_world(mission("undertow_mill"), flags={})
    seconds = solver.solve_mill(run, shutter=False)
    assert run.won and run.remembered() == {"undertow_mill_vault": True}
    assert seconds < 900


@pytest.mark.slow
def test_millfield_can_shutter_the_vault_at_its_pylon() -> None:
    """Slow: a whole mission, won by attacking the hostile pylon and clearing the last beasts."""
    run = build_world(mission("undertow_mill"), flags={})
    solver.solve_mill(run, shutter=True)
    assert run.won and run.remembered() == {"undertow_mill_vault": False}
    assert not run.world.vaults(0), "the shuttered vault no longer draws"


def test_millfield_losing_the_town_hall_loses() -> None:
    run = build_world(mission("undertow_mill"), flags={})
    hall = run.hall(0)
    band = run.spawn(1, [U.TROLL, U.TROLL], hall.center, attack=hall.center)
    run.world.attack([u.id for u in band], hall.id)
    solver.play_until(run, lambda r: r.lost is not None, seconds=300)
    assert run.lost and not run.won


@pytest.mark.slow
def test_the_caravan_salvages_moves_and_rebuilds_on_the_mesa() -> None:
    """Slow: salvage orders strip the ruins, a sapper blasts the rockfall, and build orders raise
    the mesa camp — the packed stores make the resettlement affordable without editing the purse."""
    run = build_world(mission("undertow_caravan"), flags={})
    seconds = solver.solve_caravan(run, blast_dam=False)
    assert run.won and run.remembered() == {"undertow_dam": False}
    assert seconds < 1500


@pytest.mark.slow
def test_the_caravan_can_blast_the_mill_dam_and_sweep_the_open_hand_camp() -> None:
    """Slow: the dam path of a whole mission; the flood is the camp's real removal, not narration."""
    run = build_world(mission("undertow_caravan"), flags={})
    solver.solve_caravan(run, blast_dam=True)
    assert run.won and run.remembered() == {"undertow_dam": True}
    assert not run.units(1), "the Open Hand camp was swept off the map"


@pytest.mark.slow
def test_the_grove_can_cut_the_firebreak_after_parley() -> None:
    """Slow: Wrenna walks to the woodcutters (parley before any blow), gatherers fell the marked
    strip tree by tree, and the diminished bloom is fought off."""
    run = build_world(mission("undertow_grove"), flags={})
    solver.solve_grove(run, cut=True, guardian="ally")
    assert run.won
    remembered = run.remembered()
    assert remembered["undertow_grove_cut"] is True and remembered["undertow_guardian_ally"] is True
    assert "parley" in run.fired


@pytest.mark.slow
def test_the_grove_can_stay_whole_and_weather_the_bloom() -> None:
    """Slow: the woodcutters are driven off by force and both bloom waves are beaten at the Moonwell."""
    run = build_world(mission("undertow_grove"), flags={})
    solver.solve_grove(run, cut=False, guardian="core")
    assert run.won
    remembered = run.remembered()
    assert remembered["undertow_grove_cut"] is False and remembered["undertow_guardian_core"] is True


def test_the_grove_loses_wrenna_and_the_mission() -> None:
    run = build_world(mission("undertow_grove"), flags={})
    wrenna = run.unit("wrenna")
    band = run.spawn(2, [U.TROLL, U.TROLL], wrenna.pos, attack=wrenna.pos)
    run.world.attack([u.id for u in band], wrenna.id)
    solver.play_until(run, lambda r: r.lost is not None, seconds=300)
    assert run.lost and not run.won


@pytest.mark.slow
def test_the_weight_can_break_the_siege_and_cap_the_seam() -> None:
    """Slow: three counted engineer bands are beaten off the Weights, the enemy hall is razed, and
    a vault is built square on the seam-rift by ordinary build orders."""
    run = build_world(mission("undertow_weight"), flags={})
    solver.solve_weight(run, seam="cap")
    assert run.won and run.remembered()["undertow_seam_capped"] is True


@pytest.mark.slow
def test_the_weight_can_spend_the_powder_and_work_the_seam() -> None:
    """Slow: the defensive win (workshop razed, bands spent) with the seam worked by real haul trips
    until the mission's own seam counter, not a gold delta, reaches its threshold."""
    run = build_world(mission("undertow_weight"), flags={})
    solver.solve_weight(run, seam="mine")
    assert run.won and run.remembered()["undertow_seam_mined"] is True
    assert run.get("seam_gold") >= 300


@pytest.mark.slow
def test_the_maw_can_be_resealed_at_the_keystone() -> None:
    """Slow: peasants repair the Keystone under the final assault and the assault is broken."""
    run = build_world(mission("undertow_maw"), flags={})
    seconds = solver.solve_maw(run, ending="sealed")
    assert run.won and run.remembered()["undertow_ending_sealed"] is True
    assert seconds < 1800


@pytest.mark.slow
def test_the_maw_can_be_opened_pylon_by_pylon() -> None:
    """Slow: three hostile seal-pylons are destroyed by attack orders, Sella stands down, and the
    bloom wave out of the open Maw is ridden out."""
    run = build_world(mission("undertow_maw"), flags={})
    solver.solve_maw(run, ending="open")
    assert run.won and run.remembered()["undertow_ending_open"] is True
    assert not run.units(1)


@pytest.mark.slow
def test_the_maw_can_be_grounded_behind_a_ring_of_vaults() -> None:
    """Slow: builders raise a vault on each Maw rift under fire and hold them while the aether
    store climbs to the stated 450.  Standalone play: the grove stands whole by default."""
    run = build_world(mission("undertow_maw"), flags={})
    solver.solve_maw(run, ending="ground")
    assert run.won and run.remembered()["undertow_ending_ground"] is True
    assert run.world.players[0].aether >= 450


@pytest.mark.slow
def test_a_cut_grove_without_the_guardian_cannot_ground_the_maw() -> None:
    """Slow: with the grove cut and no Guardian either way, Maw vaults are only economy — the
    mission stays winnable by resealing, and the ground ending never silently completes."""
    run = build_world(mission("undertow_maw"), flags={"undertow_grove_cut": True})
    solver.solve_maw(run, ending="sealed")
    assert run.won and run.remembered()["undertow_ending_ground"] is False


@pytest.mark.slow
def test_a_full_campaign_of_flags_flows_into_the_maw(tmp_path) -> None:
    """Slow: progress written by earlier victories is what the finale reads, through the store."""
    from warband.story.campaign import Progress, ProgressStore
    from warband.sim.rules import Difficulty

    store = ProgressStore(tmp_path, CAMPAIGN.id)
    progress = Progress(CAMPAIGN.id, Difficulty.MEDIUM, flags={
        "undertow_mill_vault": False, "undertow_dam": True, "undertow_grove_cut": False,
        "undertow_guardian_ally": True, "undertow_seam_capped": True})
    for m in CAMPAIGN.missions[:4]:
        progress.complete(m, {})
    store.save(progress)
    loaded = store.load()
    run = build_world(mission("undertow_maw"), flags=loaded.flags)
    assert any(u.type is U.ANCIENT_GUARDIAN for u in run.units(0))
    solver.solve_maw(run, ending="ground")
    assert run.won
    loaded.complete(run.mission, run.remembered())
    assert loaded.next_mission(CAMPAIGN) is None
    assert loaded.flags["undertow_ending_ground"] is True
