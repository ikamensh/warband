"""Campaign autosaves are discoverable from the ordinary title and load controls."""

import pytest

from saga2d import Button, Game, Scene
from saga2d.testing import assert_no_text_overlap, assert_text_fits
from warband.art.visual_lint import use_real_text_metrics
from warband.sim.rules import Difficulty
from warband.story.catalog import THORNWOOD, UNDERTOW
from warband.story.mission_scene import MissionScene, build_world
from warband.ui.style import build_theme
from warband.ui.scene import SaveBrowserScene
from warband.ui.title import TitleScene


@pytest.fixture
def game(tmp_path):
    game = Game("Campaign saves", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


def press(game, key):
    game.backend.inject_key(key)
    game.tick(.1)


@pytest.mark.slow
def test_title_continue_resumes_the_undertow_autosave(game):
    """Slow: render the mission, title and resumed map through the normal Continue control."""
    run = build_world(UNDERTOW.missions[0], flags={"earlier_choice": True})
    mission = MissionScene(UNDERTOW, run, difficulty=Difficulty.MEDIUM)
    game.push(mission)
    game.tick(.1)
    game.save(mission.AUTOSAVE_SLOT, scene=mission)
    game.clear_and_push(TitleScene())
    game.tick(.1)
    assert not any("No saved game yet" in text["text"] for text in game.backend.texts)
    press(game, "c")
    assert isinstance(game.scene, MissionScene)
    assert game.scene.campaign is UNDERTOW
    assert game.scene.run.get("earlier_choice") is True


def test_load_browser_can_choose_each_campaign_autosave_without_moving_its_files(game):
    """Both stories are named in Load, and their number keys select the correct independent slot."""
    states = {"campaign_undertow": {"campaign": UNDERTOW.id}, "campaign": {"campaign": THORNWOOD.id}}
    for slot, state in states.items():
        game.save_manager.save(slot, state, "MissionScene", summary={"mission": state["campaign"]})
    game.push(Scene())
    chosen = []
    for key, campaign in (("4", UNDERTOW), ("5", THORNWOOD)):
        game.push(SaveBrowserScene(game, "load", on_pick=chosen.append))
        game.tick(.1)
        assert {UNDERTOW.title, THORNWOOD.title} <= {c.text for c in game.scene.ui.walk() if isinstance(c, Button)}
        press(game, key)
        assert game.save_manager.load(chosen[-1])["state"]["campaign"] == campaign.id
    assert chosen == ["campaign_undertow", "campaign"]
    assert {slot: game.save_manager.load(slot)["state"] for slot in states} == states


def test_save_browser_never_overwrites_a_campaign_automatic_slot(game):
    """A campaign save remains readable but cannot be replaced with a manual browser save."""
    state = {"campaign": UNDERTOW.id}
    game.save_manager.save("campaign_undertow", state, "MissionScene")
    game.push(Scene())
    chosen = []
    game.push(SaveBrowserScene(game, "save", on_pick=chosen.append))
    game.tick(.1)
    campaign_button = next(c for c in game.scene.ui.walk() if isinstance(c, Button) and c.text == UNDERTOW.title)
    assert not campaign_button.enabled
    press(game, "4")
    assert isinstance(game.scene, SaveBrowserScene) and chosen == []
    assert game.save_manager.load("campaign_undertow")["state"] == state


def test_a_full_load_browser_fits_the_compact_window(game):
    """Every ordinary slot and both campaign saves fit together with their wrapped summaries."""
    use_real_text_metrics(game)
    for slot in (1, 2, 3, "quick", "autosave", "campaign_undertow", "campaign"):
        game.save_manager.save(slot, {}, "MissionScene", summary={
            "mission": "4. The Weight", "map": "64×48", "players": 2, "difficulty": "Medium", "clock": "08:31",
        })
    game.push(Scene())
    game.push(SaveBrowserScene(game, "load", on_pick=lambda slot: None))
    game.tick(.1)
    assert_text_fits(game)
    assert_no_text_overlap(game, top_scene_only=True)
