"""Campaign controls describe the actual story, and its script owns announcements about progress."""

import pytest

from saga2d import Button, Game, Label
from saga2d.settings import Settings
from warband.sim.rules import SIM_DT, Difficulty
from warband.story.campaign import Progress, ProgressStore
from warband.story.campaign_scene import CampaignScene
from warband.story.mission_scene import MissionScene, build_world
from warband.story.new_campaign import CAMPAIGN
from warband.ui.style import build_theme
from warband.ui.scene import DEFAULT_SETTINGS, GameScene, SettingsScene


@pytest.fixture
def game(tmp_path):
    game = Game("Story UI", backend="mock", resolution=(1200, 680), theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


def test_an_authored_story_does_not_offer_a_difficulty_that_changes_nothing(game) -> None:
    """Finite authored encounters have no computer opponent to shift: offer the campaign's real choice instead."""
    game.push(CampaignScene(campaign=CAMPAIGN))
    game.tick(1 / 60)
    buttons = [component.text for component in game.scene.ui.walk() if isinstance(component, Button)]
    assert not set(buttons) & {"Easy", "Medium", "Hard"}
    assert "Begin the campaign" in buttons and "The Thornwood War" in buttons


@pytest.mark.slow
def test_campaign_entry_speed_carries_into_the_briefing_and_mission(game) -> None:
    """Slow: traverse the real campaign entrance and briefing, then measure the live mission's pace."""
    from warband.story.dialog import DialogScene

    settings = game.settings(DEFAULT_SETTINGS)
    game.push(CampaignScene(settings, campaign=CAMPAIGN))
    game.tick(0.1)
    button = game.scene.ui.find(lambda c: isinstance(c, Button) and c.text == "Speed: ×1")
    assert button is not None
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.backend.inject_release(x + width / 2, y + height / 2)
    game.tick(0.1)
    assert Settings(settings.path, DEFAULT_SETTINGS)["campaign_speed"] == 1.2
    game.backend.inject_key("return")
    game.tick(0.1)
    assert isinstance(game.scene, DialogScene)
    scene = game.scenes[-2]
    before = scene.world.time
    game.tick(0.1)
    assert scene.world.time == before
    game.scene.skip()
    for _ in range(5):
        game.tick(0.1)
    assert scene.world.time - before == pytest.approx(0.6, abs=SIM_DT + 1e-9)


@pytest.mark.slow
def test_campaign_speed_changes_through_the_pause_settings_and_is_saved(game) -> None:
    """Slow: play a real mission through pause/settings, measure its clock and reload its saved preference."""
    settings = game.settings(DEFAULT_SETTINGS)
    run = build_world(CAMPAIGN.missions[0], flags={})
    ProgressStore(game.data_dir, CAMPAIGN.id).save(Progress(CAMPAIGN.id, Difficulty.MEDIUM))
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM, settings=settings)
    game.push(scene)
    game.tick(0.1)
    assert scene.execution.speed == 1.0
    for key in ("f10", "s"):
        game.backend.inject_key(key)
        game.tick(0.1)
    assert isinstance(game.scene, SettingsScene)
    label = game.scene.ui.find(lambda c: isinstance(c, Label) and c.text == "Campaign speed")
    assert label is not None
    plus = label.parent.find(lambda c: isinstance(c, Button) and c.text == "+")
    x, y, width, height = plus.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.backend.inject_release(x + width / 2, y + height / 2)
    game.tick(0.1)
    for _ in range(2):
        game.backend.inject_key("right")
        game.tick(0.1)
    assert settings["campaign_speed"] == 2.0
    for _ in range(2):
        game.backend.inject_key("escape")
        game.tick(0.1)
    assert game.scene is scene
    before = scene.world.time
    for _ in range(5):
        game.tick(0.1)
    assert scene.world.time - before == pytest.approx(1.0)
    assert "×2" in [item["text"] for item in game.backend.texts]
    assert Settings(settings.path, DEFAULT_SETTINGS)["campaign_speed"] == 2.0
    for key in ("f10", "c"):
        game.backend.inject_key(key)
        game.tick(0.1)
    assert isinstance(game.scene, CampaignScene)
    for _ in range(2):
        game.scene.cycle_speed()  # 2× → 3× → 0.5× before resuming the saved mission
    game.backend.inject_key("return")
    game.tick(0.1)
    resumed = game.scene
    assert isinstance(resumed, MissionScene) and resumed is not scene
    before = resumed.world.time
    for _ in range(4):
        game.tick(0.1)
    assert resumed.world.time - before == pytest.approx(0.2)


def test_campaign_speed_does_not_accelerate_skirmishes(game) -> None:
    """A shared campaign preference changes only campaign play, including when returning to a skirmish."""
    from tests.warband.battlefield import field

    scene = GameScene(field(), 0, settings={"campaign_speed": 3.0, "music": 0.0, "sfx": 0.0})
    game.push(scene)
    before = scene.world.time
    for _ in range(5):
        game.tick(0.1)
    assert scene.world.time - before == pytest.approx(0.5)


@pytest.mark.slow
def test_a_future_bloom_is_not_announced_as_defeated_when_the_mission_opens(game) -> None:
    """Slow: builds the full elven map view and advances past the title banner to inspect actual HUD text."""
    run = build_world(CAMPAIGN.mission("undertow_grove"), flags={})
    game.push(MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM))
    seen = []
    for _ in range(30):
        game.tick(0.1)
        seen.extend(text["text"] for text in game.backend.texts)
    assert "A rival falls" not in seen
    assert not any("last holdings are revealed" in text for text in seen)
    assert any("Woodcutters: parley" in text for text in seen)


@pytest.mark.slow
def test_the_maw_can_show_all_arrivals_without_the_notice_falling_below_the_window(game) -> None:
    """Slow: render the full finale and its live multi-line consequence notice at the smallest window."""
    from warband.art import visual_lint

    visual_lint.use_real_text_metrics(game)
    flags = {"undertow_mill_vault": True, "undertow_dam": True,
             "undertow_guardian_ally": True, "undertow_seam_mined": True}
    run = build_world(CAMPAIGN.mission("undertow_maw"), flags=flags)
    game.push(MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM))
    for _ in range(40):
        game.tick(.1)
    assert "The muster of consequences" in [item["text"] for item in game.backend.texts]
    findings = [finding for finding in visual_lint.lint_texts(game) if finding.check == "text-off-screen"]
    assert not findings, "\n".join(str(finding) for finding in findings)
