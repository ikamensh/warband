"""The campaign: missions that play through the scene, choices that carry over, and progress that outlives a version."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from saga2d import Game, SaveError
from warband.campaign import Progress, ProgressStore
from warband.campaign_scene import CampaignScene
from warband.dialog import DialogScene
from warband.mission_scene import CAMPAIGN_SLOT, MissionResultScene, MissionScene, build_world
from warband.missions import CAMPAIGN
from warband.model import tile_center
from warband.rules import SIM_DT, BuildingType, Difficulty, Race, UnitType
from warband.style import build_theme
from warband.title import TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Campaign", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


def run_for(run, seconds: float) -> None:
    """Advance a mission the way the scene does: the world steps, then the script looks."""
    for _ in range(int(round(seconds / SIM_DT))):
        run.world.step()
        run.tick()


def slay(world, side: int) -> None:
    """Every unit of *side* falls on the next step."""
    for unit in world.player_units(side):
        unit.hp = 0


def mission(mission_id: str):
    return CAMPAIGN.mission(mission_id)


# -- Progress: the file that outlives versions ----------------------------------------------


def test_progress_round_trips_and_carries_what_this_version_does_not_know(tmp_path) -> None:
    store = ProgressStore(tmp_path)
    assert store.load() is None
    progress = Progress(CAMPAIGN.id, Difficulty.HARD, completed=["hollowmere", "a_mission_from_the_future"], flags={"truce": True, "new_flag": [1, 2]},
                        extra={"chapter_art": "v2"})
    store.save(progress)
    again = store.load()
    assert again == progress
    assert again.next_mission(CAMPAIGN).id == "greywater"  # the unknown mission is kept but never blocks the order
    again.complete(mission("greywater"), {"truce": False})
    store.save(again)
    written = json.loads((tmp_path / "campaign" / "save_1.json").read_text())["state"]
    assert written["chapter_art"] == "v2" and written["completed"] == ["hollowmere", "a_mission_from_the_future", "greywater"]
    assert written["flags"] == {"truce": False, "new_flag": [1, 2]} and written["format"] == 1


def test_a_progress_file_from_a_newer_warband_is_refused_with_a_reason(tmp_path) -> None:
    store = ProgressStore(tmp_path)
    store.saves.save(1, {"format": 99, "campaign": CAMPAIGN.id, "completed": []}, "WarbandCampaign")
    with pytest.raises(SaveError, match="newer"):
        store.load()


# -- Mission 1 through the run ---------------------------------------------------------------


def test_hollowmere_raids_come_once_the_village_stands_and_the_third_wave_broken_wins(game) -> None:
    run = build_world(mission("hollowmere"), flags={})
    world = run.world
    hall = run.hall(0)
    run_for(run, 5)
    assert run.state["hold"] == "hidden" and not run.fired and not world.player_units(1)
    world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
    for i in range(4):
        world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
    run_for(run, SIM_DT)
    assert run.state["farm"] == run.state["barracks"] == run.state["soldiers"] == "done"
    run_for(run, SIM_DT)
    assert "raid_1" in run.fired and run.state["hold"] == "open" and len(world.player_units(1)) == 4
    assert run.pending and run.pending[0][0].speaker == "Aldric"
    raiders = world.player_units(1)
    assert all(u.orders for u in raiders)  # sent at the village, not standing in their camp
    slay(world, 1)
    run_for(run, 81)
    assert "raid_2" in run.fired and len(world.player_units(1)) == 6 and not run.won
    slay(world, 1)
    run_for(run, 96)
    assert "raid_3" in run.fired and len(world.player_units(1)) == 8
    slay(world, 1)
    run_for(run, 1)
    assert run.state["hold"] == "done" and run.won and run.lost is None


def test_losing_the_hall_loses_hollowmere(game) -> None:
    run = build_world(mission("hollowmere"), flags={})
    run_for(run, 301)  # the raid comes at five minutes whether the village is ready or not
    assert "raid_1" in run.fired
    run.hall(0).hp = 0
    run_for(run, 1)
    assert run.lost == "Hold Hollowmere against the raids" and not run.won


# -- The campaign flow through the scenes ----------------------------------------------------------


def begin_campaign(game: Game) -> MissionScene:
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "a")
    assert isinstance(game.scene, CampaignScene)
    press(game, "return")
    assert isinstance(game.scene, DialogScene)
    press(game, "escape")  # skip the briefing
    scene = game.scene
    assert isinstance(scene, MissionScene) and scene.mission.id == "hollowmere"
    return scene


def test_the_first_mission_plays_to_a_result_that_records_progress_and_leads_on(game) -> None:
    scene = begin_campaign(game)
    past_the_banner(game)
    assert "1. Hollowmere" in texts(game) and "Build a farm" in texts(game) and "Getting started" not in texts(game)
    world = scene.world
    hall = scene.run.hall(0)
    world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
    for i in range(4):
        world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
    for _ in range(12):
        game.tick(1 / 60)
    assert isinstance(game.scene, DialogScene)  # Aldric sees the dust on the road; the match waits
    clock = world.time
    game.tick(1 / 60)
    assert world.time == clock
    press(game, "space")
    assert game.scene is scene
    for building in world.player_buildings(1):
        building.hp = 0  # the village razes the camp instead of waiting for the third wave
    for _ in range(12):
        game.tick(1 / 60)
    assert isinstance(game.scene, MissionResultScene) and game.scene.won
    assert "Mission complete" in texts(game) and "Or raze the raiders' camp in the east" in texts(game)
    progress = ProgressStore(game.data_dir).load()
    assert progress.completed == ["hollowmere"] and game.save_manager.load(CAMPAIGN_SLOT) is None
    press(game, "return")
    assert isinstance(game.scene, DialogScene) and any("children's things" in t for t in texts(game))
    press(game, "escape")
    assert isinstance(game.scene, CampaignScene) and game.scene.next_mission.id == "greywater"
    assert "2. Greywater Ford" in texts(game)


# -- Choices that carry across missions --------------------------------------------------------------


def start(game: Game, mission_id: str, flags: dict | None = None, difficulty: Difficulty = Difficulty.MEDIUM) -> MissionScene:
    run = build_world(mission(mission_id), flags=flags or {})
    scene = MissionScene(CAMPAIGN, run, difficulty=difficulty)
    game.push(scene)
    game.tick(1 / 60)
    return scene


@pytest.mark.slow
def test_granting_the_truce_at_the_ford_ends_the_mission_and_is_remembered(game) -> None:
    """The ford's waves and its emissary come on the mission's clock, ten minutes of it: the slow tier."""
    scene = start(game, "greywater")
    run, world = scene.run, scene.world
    assert [type(b).__name__ for b in scene.brains] == ["Brain"] and scene.brains[0].difficulty is Difficulty.EASY
    run_for(run, 160)
    assert "probe_1" in run.fired and len(world.player_units(1)) == 6  # three peons at home, three grunts at the ford
    slay(world, 1)  # the levy holds the ford
    run_for(run, 240)
    assert "probe_2" in run.fired
    slay(world, 1)
    run_for(run, 200)
    assert "emissary" in run.fired and run.state["answer"] == "open" and run.state["hold"] == "done"
    game.tick(1 / 60)
    assert isinstance(game.scene, DialogScene) and "Gorrash Ironjaw" in texts(game)
    for _ in range(4):
        press(game, "space")
    assert "Grant the truce" in texts(game) and "No quarter" in texts(game)
    press(game, "space")  # a question is not answered by nodding
    assert "Grant the truce" in texts(game)
    press(game, "1")
    assert any("The wastes are yours" in t for t in texts(game))
    press(game, "space")
    press(game, "space")
    assert game.scene is scene and run.vars["truce"] is True
    for _ in range(6):
        game.tick(1 / 60)
    assert not world.players[1].alive and not world.player_buildings(1)
    assert isinstance(game.scene, MissionResultScene) and game.scene.won
    assert ProgressStore(game.data_dir).load().completed == ["greywater"]
    press(game, "return")
    press(game, "escape")
    assert ProgressStore(game.data_dir).load().flags == {"truce": True}


@pytest.mark.slow
def test_refusing_the_truce_means_the_camp_must_burn(game) -> None:
    """Ten minutes of the mission's clock: the slow tier."""
    run = build_world(mission("greywater"), flags={})
    for seconds in (160, 240, 200):
        run_for(run, seconds)
        slay(run.world, 1)
    run.pending.clear()
    run.set("truce", False)
    run_for(run, 1)
    assert run.state["raze"] == "open" and run.state["answer"] == "done" and not run.won
    run.world.players[1].alive = False
    run_for(run, SIM_DT)
    assert run.won


def test_the_truce_and_the_powder_shape_the_later_missions() -> None:
    peace = build_world(mission("retaken"), flags={"truce": True})
    war = build_world(mission("retaken"), flags={})
    assert peace.ai[1] is Difficulty.EASY and war.ai[1] is Difficulty.MEDIUM
    assert peace.world.players[0].gold == war.world.players[0].gold + 1000
    court = build_world(mission("court_of_thorns"), flags={"truce": True, "powder": True})
    assert not court.world.players[2].alive and not court.world.player_units(2)
    assert court.state["orcs"] == "hidden" and court.units(0, UnitType.CATAPULT) and court.buildings(0, BuildingType.WORKSHOP)
    court_at_war = build_world(mission("court_of_thorns"), flags={"truce": False, "powder": False})
    court_at_war.tick()
    assert court_at_war.world.players[2].alive and court_at_war.state["orcs"] == "open"
    assert not court_at_war.units(0, UnitType.CATAPULT) and court_at_war.world.players[0].gold == court.world.players[0].gold + 2000
    court.world.players[1].alive = False
    court.tick()
    assert court.won  # with the truce the orcs are no part of the win


def test_a_replayed_mission_asks_its_own_question_again() -> None:
    run = build_world(mission("greywater"), flags={"truce": True})
    assert "truce" not in run.vars
    run_for(run, 1)
    assert not run.won


# -- Saves in the middle of a mission ----------------------------------------------------------------------


@pytest.mark.slow
def test_a_mission_save_keeps_the_script_where_it_was_and_continue_resumes_it(game) -> None:
    """Five minutes of the mission's clock before the save: the slow tier."""
    scene = start(game, "hollowmere")
    run = scene.run
    run_for(run, 301)
    game.tick(1 / 60)
    press(game, "space")  # Aldric's warning
    assert "raid_1" in run.fired and run.state["hold"] == "open"
    press(game, "f5")
    saved = game.save_manager.load("quick")
    assert saved["scene_class"] == "MissionScene" and saved["summary"]["mission"] == "1. Hollowmere"
    game.save(CAMPAIGN_SLOT, scene=scene)
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    assert any("Continue resumes the campaign mission" in t for t in texts(game))
    press(game, "c")
    loaded = game.scene
    assert isinstance(loaded, MissionScene) and loaded is not scene
    assert loaded.run.fired.keys() == {"raid_1"} and loaded.run.state == run.state and loaded.run.get("camp") == run.get("camp")
    assert [p.name for p in loaded.world.players] == ["Hollowmere", "Bloodfang Raiders"] and loaded.world.scripted
    past_the_banner(game)
    assert "1. Hollowmere" in texts(game) and "Hold Hollowmere against the raids" in texts(game)
    assert loaded.AUTOSAVE_SLOT == CAMPAIGN_SLOT and not loaded.ranked


def test_a_mission_save_from_another_version_costs_the_mission_not_the_campaign(game) -> None:
    store = ProgressStore(game.data_dir)
    store.save(Progress(CAMPAIGN.id, Difficulty.EASY, completed=["hollowmere"], flags={"truce": True}))
    game.save_manager.save(CAMPAIGN_SLOT, {"version": 0, "seed": 1, "difficulty": "easy", "world": {}, "mission": {"id": "greywater"}}, "MissionScene",
                           summary={"mission": "2. Greywater Ford"})
    game.push(CampaignScene())
    game.tick(1 / 60)
    scene = game.scene
    assert isinstance(scene, CampaignScene) and scene.next_mission.id == "greywater" and scene.difficulty is Difficulty.EASY
    assert "Continue opens its briefing" in texts(game) and "another version" in " ".join(texts(game))
    press(game, "return")
    assert isinstance(game.scene, DialogScene)  # the briefing of Greywater Ford, from the top
    press(game, "escape")
    assert isinstance(game.scene, MissionScene) and game.scene.mission.id == "greywater"
    assert store.load().completed == ["hollowmere"] and store.load().flags == {"truce": True}


def test_start_over_asks_twice_and_then_erases(game) -> None:
    ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.MEDIUM, completed=["hollowmere"]))
    game.push(CampaignScene())
    game.tick(1 / 60)
    scene = game.scene
    scene.start_over()
    game.tick(1 / 60)
    assert ProgressStore(game.data_dir).load() is not None and "Really start over?" in texts(game)
    scene.start_over()
    game.tick(1 / 60)
    assert ProgressStore(game.data_dir).load() is None and "Begin the campaign" in texts(game)


# -- The escort -----------------------------------------------------------------------------------------------


def test_the_silent_hold_is_won_by_maren_at_the_pass_and_lost_with_her(game) -> None:
    run = build_world(mission("silent_hold"), flags={"truce": True})
    world = run.world
    assert not world.player_buildings(0) and len(world.player_units(0)) == 10
    maren = run.unit("maren")
    assert maren.type is UnitType.CLERIC
    run_for(run, 2)
    assert "road" in run.fired and "ambush" not in run.fired
    goal = tile_center((int(run.get("goal")[0]), int(run.get("goal")[1])))
    for unit in world.player_units(0):
        unit.x, unit.y = goal[0] - 1.5, goal[1] - 1.5  # the company arrives
    run_for(run, SIM_DT)
    assert "ambush" in run.fired and any(item.speaker == "Warden" for item in run.pending[0])
    run_for(run, SIM_DT)
    assert run.won
    again = build_world(mission("silent_hold"), flags={})
    again.unit("maren").hp = 0
    run_for(again, 1)
    assert again.lost == "Sister Maren must survive" and not again.won


# -- The dialogue scene -----------------------------------------------------------------------------------------


def test_dialogue_lines_follow_the_answer_and_escape_skips_to_the_question(game) -> None:
    from warband.campaign import Choice, Line, Option

    vars: dict = {}
    done = []
    dialog = (Line("Aldric", "First."), Line("Maren", "Second."), Choice("truce", "Aldric", "Well?", (Option("Yes", True), Option("No", False))),
              Line("Aldric", "Agreed.", when="truce"), Line("Aldric", "Never.", unless="truce"), Line("", "The end."))
    game.push(DialogScene(dialog, CAMPAIGN.speakers, vars, on_done=lambda: done.append(True)))
    game.tick(1 / 60)
    assert "First." in texts(game) and "Captain Aldric Vane" in texts(game)
    press(game, "escape")
    assert "Well?" in texts(game) and "Second." not in texts(game)
    press(game, "2")
    assert vars == {"truce": False} and "Never." in texts(game)
    press(game, "space")
    assert "The end." in texts(game)
    press(game, "space")
    assert done == [True] and game.scene is None


# -- Every mission both ways ------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]

READ_PROGRESS = """
import json, sys
from pathlib import Path
from saga2d import Game
from warband.campaign_scene import CampaignScene
from warband.style import build_theme
data = Path(sys.argv[1])
game = Game("Warband Campaign", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=data / "saves")
game.push(CampaignScene())
game.tick(1 / 60)
scene = game.scene
print(json.dumps({"next": scene.next_mission.id, "flags": scene.progress.flags, "difficulty": scene.difficulty.value}))
game.close()
"""




def raze(world, side: int) -> None:
    """Everything *side* has falls on the next step, buildings and units alike."""
    slay(world, side)
    for building in world.player_buildings(side):
        building.hp = 0


def settle(game: Game, frames: int = 30) -> None:
    for _ in range(frames):
        game.tick(1 / 60)


def past_the_banner(game: Game) -> None:
    """The mission's title banner holds the screen for 2.7 seconds: three seconds in tenths are past it."""
    for _ in range(30):
        game.tick(0.1)


def read_in_a_new_process(data_dir) -> dict:
    """What the campaign screen of a fresh process offers from the progress file in *data_dir*."""
    env = {**os.environ, "SAGA2D_SILENT": "1"}
    done = subprocess.run([sys.executable, "-c", READ_PROGRESS, str(data_dir)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def talk_through(game: Game, until) -> list[str]:
    """Press Space through the dialogues until *until* holds; every text shown on the way."""
    seen: list[str] = []
    for _ in range(16):
        seen += texts(game)
        if until(game.scene):
            return seen
        press(game, "space")
    raise AssertionError(f"still in {type(game.scene).__name__} after sixteen lines")


def test_losing_the_hall_before_the_levies_come_loses_the_ford() -> None:
    run = build_world(mission("greywater"), flags={})
    run_for(run, 60)
    run.hall(0).hp = 0
    run_for(run, 1)
    assert run.lost == "Hold the ford until the levies arrive (10:00)" and not run.won


@pytest.mark.slow
def test_karst_hold_is_won_by_burning_the_camp_and_the_powder_goes_south_into_a_new_process(game) -> None:
    """A second process reads the progress file: the slow tier."""
    ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.HARD, completed=["hollowmere", "greywater", "silent_hold"], flags={"truce": True}))
    scene = start(game, "karst_hold", flags={"truce": True}, difficulty=Difficulty.HARD)
    run, world = scene.run, scene.world
    assert world.players[0].race is Race.DWARF and [type(b).__name__ for b in scene.brains] == ["ProBrain"]  # Medium, one step harder
    run_for(run, 5)
    assert "assault" in run.fired and run.state["break"] == "open"
    raze(world, 1)
    settle(game)
    assert isinstance(game.scene, MissionResultScene) and game.scene.won
    press(game, "return")  # the debrief
    assert isinstance(game.scene, DialogScene)
    press(game, "escape")  # to Brunna's question
    assert "Take the powder south" in texts(game)
    press(game, "1")
    talk_through(game, lambda scene: isinstance(scene, CampaignScene))
    assert game.scene.next_mission.id == "retaken"
    assert read_in_a_new_process(game.data_dir) == {"next": "retaken", "flags": {"truce": True, "powder": True}, "difficulty": "hard"}


def test_karst_hold_is_lost_with_its_deep_hold() -> None:
    run = build_world(mission("karst_hold"), flags={})
    run_for(run, 5)
    run.hall(0).hp = 0
    run_for(run, 1)
    assert run.lost == "Karst's Deep Hold must stand" and not run.won


def test_greywater_retaken_is_won_when_the_lodges_burn_and_lost_with_the_hall() -> None:
    run = build_world(mission("retaken"), flags={"truce": True})
    run_for(run, 2)
    assert "tribute" in run.fired and run.state["retake"] == "open"
    raze(run.world, 1)
    run_for(run, 1)
    assert run.state["retake"] == "done" and run.won and run.lost is None
    again = build_world(mission("retaken"), flags={})
    run_for(again, 2)
    assert "tribute" not in again.fired
    again.hall(0).hp = 0
    run_for(again, 1)
    assert again.lost == "Your town hall must stand" and not again.won


def test_the_court_falls_once_the_orcs_are_driven_off_and_the_epilogue_reads_the_three_choices(game) -> None:
    before = [m.id for m in CAMPAIGN.missions[:5]]
    ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.MEDIUM, completed=before, flags={"truce": False, "powder": True}))
    scene = start(game, "court_of_thorns", flags={"truce": False, "powder": True})
    run, world = scene.run, scene.world
    run_for(run, 2)
    raze(world, 1)
    settle(game)
    assert run.state["court"] == "done" and run.state["orcs"] == "open" and not run.won and game.scene is scene
    raze(world, 2)
    settle(game)
    assert isinstance(game.scene, MissionResultScene) and game.scene.won and "The war is over" in texts(game)
    press(game, "return")  # the debrief
    press(game, "escape")  # to Ysolde's question
    press(game, "1")  # burn it back
    shown = " ".join(talk_through(game, lambda scene: isinstance(scene, CampaignScene)))
    assert "The Thornwood War ended in the ash of the Court" in shown
    assert "Every spring since" in shown and "No orc has crossed the Greywater" in shown and "crater to boast of" in shown
    assert "oath held" not in shown and "grandchildren" not in shown and "kept its powder" not in shown
    progress = ProgressStore(game.data_dir).load()
    assert progress.completed == before + ["court_of_thorns"] and progress.flags == {"truce": False, "powder": True, "burn": True}
    assert progress.next_mission(CAMPAIGN) is None and "Read the epilogue" in texts(game)


def test_the_court_of_thorns_is_lost_with_the_hall() -> None:
    run = build_world(mission("court_of_thorns"), flags={"truce": True})
    run_for(run, 2)
    run.hall(0).hp = 0
    run_for(run, 1)
    assert run.lost == "Your town hall must stand" and not run.won


# -- The mission's HUD ---------------------------------------------------------------------------------------------------


def test_the_title_banner_has_the_screen_first_and_notices_hang_under_the_objectives(game) -> None:
    """At 680 tall the banner's band crosses where the objectives panel reaches, so the panel waits for it; and a
    notice slides in under the panel however tall the panel has grown, never over it."""
    scene = start(game, "hollowmere")
    assert "Mission 1: Hollowmere" in texts(game) and "Build a farm" not in texts(game)
    past_the_banner(game)
    assert "Build a farm" in texts(game) and "Mission 1: Hollowmere" not in texts(game)
    world, hall = scene.world, scene.run.hall(0)
    world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
    for i in range(4):
        world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
    settle(game, 12)
    press(game, "space")  # Aldric's warning; the raid's objectives join the panel
    settle(game, 40)
    notice = next(t for t in game.backend.texts if t["text"] == "Objectives complete")
    _x, top, _w, height = scene.objectives.bounds
    assert "Hold Hollowmere against the raids" in texts(game) and notice["y"] > top + height


def test_a_camera_cue_never_pans_into_unexplored_ground_but_the_minimap_and_space_still_point_there(game) -> None:
    scene = start(game, "silent_hold")
    home = scene.camera.center
    settle(game, 90)  # the road trigger at one second names the pass, deep in unexplored ground
    goal = tuple(scene.run.get("goal"))
    assert "road" in scene.run.fired and scene.last_alert == goal
    assert scene.camera.center == home
