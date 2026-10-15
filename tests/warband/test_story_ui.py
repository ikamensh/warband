"""Campaign controls describe the actual story, and its script owns announcements about progress."""

import pytest

from saga2d import Button, Game
from warband.sim.rules import Difficulty
from warband.story.campaign_scene import CampaignScene
from warband.story.mission_scene import MissionScene, build_world
from warband.story.new_campaign import CAMPAIGN
from warband.ui.style import build_theme


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
