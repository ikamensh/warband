"""Campaign identity keeps each story's progress and in-play saves separate."""

import pytest
from dataclasses import replace
import sys

from saga2d import Button, Game, SaveError
from warband.story.campaign import Choice, Line, Objective, Option
from warband.ui.style import build_theme

from warband.story.campaign import Progress, ProgressStore
from warband.story.missions import CAMPAIGN
from warband.sim.rules import Difficulty


def test_each_campaign_has_its_own_progress_without_moving_the_legacy_file(tmp_path) -> None:
    """A second story cannot overwrite the player's Thornwood completion or choices."""
    legacy = ProgressStore(tmp_path)
    thornwood = Progress(CAMPAIGN.id, Difficulty.HARD, completed=[CAMPAIGN.missions[0].id], flags={"truce": True})
    legacy.save(thornwood)
    before = legacy.path.read_bytes()
    second = ProgressStore(tmp_path, "second_story")
    progress = Progress("second_story", Difficulty.EASY, flags={"rescue": True})
    second.save(progress)
    assert second.load() == progress
    assert legacy.load() == thornwood and legacy.path.read_bytes() == before
    assert legacy.path == tmp_path / "campaign" / "save_1.json"
    second.clear()
    assert legacy.path.read_bytes() == before and second.load() is None


def test_progress_with_another_campaign_identity_is_refused_without_overwriting(tmp_path) -> None:
    """An incorrectly placed file stays intact rather than becoming another story's progress."""
    store = ProgressStore(tmp_path, "second_story")
    foreign = Progress(CAMPAIGN.id, Difficulty.MEDIUM)
    store.saves.save(1, foreign.to_dict(), "WarbandCampaign")
    before = store.path.read_bytes()
    with pytest.raises(SaveError, match="campaign"):
        store.load()
    with pytest.raises(SaveError, match="campaign"):
        store.save(foreign)
    assert store.path.read_bytes() == before


def test_catalog_routes_mission_ids_to_their_campaign(monkeypatch) -> None:
    """Direct mission launches and save loading resolve the owning campaign from stable ids."""
    from warband.story import catalog

    intro = replace(CAMPAIGN.missions[0], id="second_intro")
    second = replace(CAMPAIGN, id="second_story", title="Second Story", missions=(intro,))
    monkeypatch.setattr(catalog, "CAMPAIGNS", (CAMPAIGN, second))
    assert catalog.get_campaign(second.id) is second
    assert catalog.find_mission(intro.id) == (second, intro)
    assert catalog.find_mission(CAMPAIGN.missions[0].id) == (CAMPAIGN, CAMPAIGN.missions[0])
    with pytest.raises(KeyError, match="campaign"):
        catalog.get_campaign("missing")
    with pytest.raises(KeyError, match="mission"):
        catalog.find_mission("missing")


@pytest.fixture
def second_campaign(monkeypatch):
    """An authored second story exercises the catalogue without coupling tests to shipped content."""
    from warband.story import catalog

    intro = replace(CAMPAIGN.missions[0], id="second_intro", title="Second Opening", act="Act I", triggers=(),
                    objectives=(Objective("goal", "Finish the opening", lambda run: bool(run.get("finished")),
                                          failed=lambda run: run.hall(0) is None),),
                    briefing=(Line("", "Another story begins."),),
                    debrief=(Choice("rescue", "Aldric", "Save the witness?", (Option("Save", True), Option("Leave", False))),),
                    win=None, remember=("rescue",))
    ending = replace(intro, id="second_ending", title="Second Ending", act="Act II", debrief=(), remember=())
    second = replace(CAMPAIGN, id="second_story", title="Second Story", missions=(intro, ending), epilogue=(Line("", "The end."),))
    monkeypatch.setattr(catalog, "CAMPAIGNS", (CAMPAIGN, second))
    return second


@pytest.fixture
def story_game(tmp_path):
    game = Game("Campaign catalogue", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


def press(game, key) -> None:
    game.backend.inject_key(key)
    game.tick(0.1)


def click(game, label) -> None:
    button = next(item for item in game.scene.ui.walk() if isinstance(item, Button) and item.text == label)
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.tick(0.1)


@pytest.mark.slow
def test_selecting_a_story_saves_resumes_and_restarts_only_that_story(story_game, second_campaign) -> None:
    """Slow: several full mission scenes and their map views exercise selection, saves and retry through the UI."""
    from warband.story.campaign_scene import CampaignScene
    from warband.story.dialog import DialogScene
    from warband.story.mission_scene import CAMPAIGN_SLOT, MissionScene, campaign_save_slot

    game = story_game
    legacy = ProgressStore(game.data_dir)
    legacy.save(Progress(CAMPAIGN.id, Difficulty.HARD, completed=[CAMPAIGN.missions[0].id], flags={"truce": True}))
    legacy_before = legacy.path.read_bytes()
    game.save_manager.save(CAMPAIGN_SLOT, {"legacy": "kept"}, "LegacyMission")
    legacy_save_before = game.save_manager.load(CAMPAIGN_SLOT)
    game.push(CampaignScene())
    game.tick(0.1)
    click(game, second_campaign.title)
    assert game.scene.campaign is second_campaign and game.scene.progress is None
    assert any("2 missions in 2 acts" in item["text"] for item in game.backend.texts)
    click(game, "Begin the campaign")
    assert isinstance(game.scene, DialogScene)
    press(game, "escape")
    scene = game.scene
    assert isinstance(scene, MissionScene) and scene.campaign is second_campaign
    scene.run.set("checkpoint", "kept")
    press(game, "escape")
    click(game, "Campaign")
    assert game.scene.campaign is second_campaign and game.scene.resume.run.get("checkpoint") == "kept"
    click(game, "Continue")
    assert isinstance(game.scene, MissionScene) and game.scene.run.get("checkpoint") == "kept"
    press(game, "escape")
    click(game, "Restart mission")
    assert isinstance(game.scene, MissionScene) and game.scene.campaign is second_campaign
    assert game.scene.run.get("checkpoint") is None
    press(game, "escape")
    click(game, "Campaign")
    click(game, "Start over")
    click(game, "Really start over?")
    assert game.scene.campaign is second_campaign and game.scene.progress is None
    assert game.save_manager.load(campaign_save_slot(second_campaign)) is None
    click(game, "Begin the campaign")
    press(game, "escape")
    assert isinstance(game.scene, MissionScene) and game.scene.run.get("checkpoint") is None
    assert legacy.path.read_bytes() == legacy_before
    assert game.save_manager.load(CAMPAIGN_SLOT) == legacy_save_before


@pytest.mark.slow
def test_results_and_debrief_choices_continue_the_selected_story(story_game, second_campaign) -> None:
    """Slow: a complete mission/debrief/next-mission/retry path builds several full scene views."""
    from warband.story.campaign_scene import CampaignScene
    from warband.story.dialog import DialogScene
    from warband.story.mission_scene import MissionResultScene, MissionScene

    game = story_game
    legacy = ProgressStore(game.data_dir)
    legacy.save(Progress(CAMPAIGN.id, Difficulty.HARD, flags={"truce": True}))
    before = legacy.path.read_bytes()
    second = ProgressStore(game.data_dir, second_campaign.id)
    second.save(Progress(second_campaign.id, Difficulty.EASY, flags={"past": "kept"}))
    game.push(CampaignScene(campaign=second_campaign))
    game.tick(0.1)
    click(game, "Continue")
    press(game, "escape")
    assert isinstance(game.scene, MissionScene) and game.scene.run.get("past") == "kept"
    game.scene.run.set("finished", True)
    for _ in range(5):
        game.tick(0.1)
    assert isinstance(game.scene, MissionResultScene) and game.scene.won
    assert second.load().completed == [second_campaign.missions[0].id]
    click(game, "Continue")
    assert isinstance(game.scene, DialogScene)
    press(game, "1")
    assert isinstance(game.scene, CampaignScene) and game.scene.campaign is second_campaign
    assert second.load().flags == {"past": "kept", "rescue": True}
    click(game, "Continue")
    press(game, "escape")
    assert game.scene.mission is second_campaign.missions[1] and game.scene.run.get("rescue") is True
    game.scene.run.hall(0).hp = 0
    for _ in range(5):
        game.tick(0.1)
    assert isinstance(game.scene, MissionResultScene) and not game.scene.won
    click(game, "Retry mission")
    assert isinstance(game.scene, MissionScene) and game.scene.campaign is second_campaign
    assert game.scene.mission is second_campaign.missions[1] and game.scene.run.get("rescue") is True
    assert legacy.path.read_bytes() == before


@pytest.mark.slow
def test_mission_saves_validate_campaign_and_mission_identity(story_game, second_campaign) -> None:
    """Slow: full scene save restoration must return the owning story and refuse foreign ids."""
    from warband.story.mission_scene import MissionScene, build_world
    from warband.ui.scene import load_game

    run = build_world(second_campaign.missions[0], flags={"past": "kept"})
    scene = MissionScene(second_campaign, run, difficulty=Difficulty.EASY)
    story_game.push(scene)
    story_game.tick(0.1)
    state = scene.get_save_state()
    loaded = load_game(state)
    assert loaded.campaign is second_campaign and loaded.mission is second_campaign.missions[0]
    assert loaded.record.run_id == scene.record.run_id
    assert loaded.run.get("past") == "kept" and loaded.AUTOSAVE_SLOT == scene.AUTOSAVE_SLOT
    for identity in (CAMPAIGN.id, "unknown_story", None):
        with pytest.raises(SaveError, match="campaign"):
            load_game({**state, "campaign": identity})


def test_mission_setup_can_supply_an_authored_world() -> None:
    """Cleanup, naming and vision apply to the authored map rather than the discarded generated map."""
    from warband.story.mission_scene import build_world
    from warband.sim.model import World
    from warband.sim.rules import BuildingType, Terrain

    authored = World(20, 20, [[Terrain.GRASS] * 20 for _ in range(20)], 2, magic=True)
    authored.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    authored.place_building(1, BuildingType.TOWN_HALL, (14, 14))
    authored.lay_rifts(((3, 3), (8, 8)))

    def setup(run):
        run.world = authored

    mission = replace(CAMPAIGN.missions[0], setup=setup)
    run = build_world(mission, flags={})
    assert run.world is authored and authored.scripted and authored.magic
    assert [player.name for player in authored.players[:authored.seats]] == [side.name for side in mission.sides]
    assert authored.rifts == ((8, 8),)
    assert authored.is_visible(0, (3, 3))


def test_cli_lists_every_campaign_and_starts_the_missions_own_story(tmp_path, monkeypatch, capsys, second_campaign) -> None:
    """The public entry point lists both stories and hands the right scene and flags to Game.run."""
    from warband.__main__ import main
    from warband.story import catalog
    from warband.story.campaign_scene import CampaignScene
    from warband.story.mission_scene import MissionScene

    monkeypatch.setenv("WARBAND_INTERPRETED", "1")
    monkeypatch.setattr(sys, "argv", ["warband", "--mission", "list"])
    main()
    output = capsys.readouterr().out
    assert CAMPAIGN.title in output and second_campaign.title in output
    assert second_campaign.missions[0].id in output and CAMPAIGN.missions[0].id in output

    monkeypatch.setattr(catalog, "DEFAULT_CAMPAIGN", second_campaign)
    ProgressStore(tmp_path).save(Progress(CAMPAIGN.id, Difficulty.HARD, flags={"truce": True}))
    ProgressStore(tmp_path, second_campaign.id).save(Progress(second_campaign.id, Difficulty.EASY, flags={"rescue": True}))
    ran, made = [], []
    real_game = Game

    def factory(*args, **kwargs):
        game = real_game(*args, backend="mock", save_dir=tmp_path / "saves", **kwargs)
        made.append(game)
        return game

    monkeypatch.setattr("saga2d.Game", factory)
    monkeypatch.setattr("warband.audio.sound.install", lambda game: None)  # audio is outside CLI scene routing
    monkeypatch.setattr(Game, "run", lambda self, scene, **kwargs: ran.append(scene))
    for args in (["--campaign"], ["--mission", second_campaign.missions[1].id], ["--mission", CAMPAIGN.missions[0].id]):
        monkeypatch.setattr(sys, "argv", ["warband", *args])
        try:
            main()
        finally:
            for game in made:
                game.close()
            made.clear()
    assert isinstance(ran[0], CampaignScene) and ran[0].campaign is second_campaign
    assert isinstance(ran[1], MissionScene) and ran[1].campaign is second_campaign
    assert ran[1].run.get("rescue") is True and ran[1].record.difficulty is Difficulty.EASY
    assert ran[2].campaign is CAMPAIGN and ran[2].run.get("truce") is True and ran[2].record.difficulty is Difficulty.HARD


def test_campaign_cover_draws_and_switching_back_to_thornwood_still_runs(story_game, second_campaign) -> None:
    """A cover supplied by the campaign renders through real scene drawing, including a compact window."""
    from warband.story.campaign_scene import CampaignScene

    covered = replace(second_campaign, cover="icon.png")  # existing source asset, sufficient for draw executability
    game = story_game
    game.set_window_size((1200, 680))
    game.push(CampaignScene(campaign=covered))
    game.tick(0.1)
    assert any(item["text"] == second_campaign.title for item in game.backend.texts)
    click(game, CAMPAIGN.title)
    assert game.scene.campaign is CAMPAIGN and game.scene.cover_key is None
