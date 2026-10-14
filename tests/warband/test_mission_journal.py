"""Dismissed story lines and decisions can be recalled after a mission save."""

import json

import pytest

from saga2d import Game, Scene
from saga2d.testing import assert_text_fits
from warband.art.visual_lint import use_real_text_metrics
from warband.sim.model import World
from warband.story.campaign import Choice, Line, Option, Run
from warband.story.catalog import UNDERTOW
from warband.story.dialog import DialogScene
from warband.story.mission_scene import build_world
from warband.ui.style import build_theme


def press(game, key):
    game.backend.inject_key(key)
    game.tick(.1)


def test_a_saved_journal_recalls_seen_lines_and_answers_without_unseen_story(tmp_path):
    """Reading history never offers future choices or a conditional line from the other answer."""
    game = Game("Journal", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    run = build_world(UNDERTOW.missions[0], flags={})
    dialogue = (
        Line("Issa", "The vault is straining."),
        Line("Dagna", "A line the player skipped."),
        Choice("hold", "Issa", "The vault, Captain?", (Option("Hold it", True), Option("Shutter it", False))),
        Line("Issa", "Then hold it.", when="hold"),
        Line("Issa", "Then shutter it.", unless="hold"),
    )
    try:
        game.push(Scene())
        game.push(DialogScene(dialogue, UNDERTOW.speakers, run.vars, record=True))
        game.tick(.1)
        press(game, "escape")
        press(game, "2")
        press(game, "space")
        saved = json.loads(json.dumps(run.to_dict()))
        resumed = Run.from_dict(run.mission, World.from_dict(run.world.to_dict()), saved)
        from warband.story.journal import JournalScene

        game.push(JournalScene(resumed, UNDERTOW.speakers))
        game.tick(.1)
        seen = [item["text"] for item in game.backend.texts]
        assert "Then shutter it." in seen
        press(game, "home")
        assert "The vault is straining." in [item["text"] for item in game.backend.texts]
        press(game, "right")
        seen = [item["text"] for item in game.backend.texts]
        assert any("Shutter it" in text for text in seen)
        assert not any("Then hold it" in text or "player skipped" in text for text in seen)
        press(game, "escape")
        assert not isinstance(game.scene, JournalScene)
    finally:
        game.close()


@pytest.mark.slow
def test_the_match_and_pause_menu_open_a_read_only_journal(game):
    """Slow: the real mission map, pause menu and journal exercise both reachable player entry points."""
    from warband.sim.rules import Difficulty
    from warband.story.journal import JournalScene
    from warband.story.mission_scene import MissionScene
    from warband.ui.scene import HelpScene

    mission = MissionScene(UNDERTOW, build_world(UNDERTOW.missions[0], flags={}), difficulty=Difficulty.MEDIUM)
    mission.paused = True
    game.push(mission)
    game.tick(.1)
    saved = json.dumps(mission.get_save_state(), sort_keys=True)
    press(game, "j")
    assert isinstance(game.scene, JournalScene)
    press(game, "b")
    first_line = next(line for line in mission.mission.briefing if isinstance(line, Line) and line.spoken(mission.run.vars))
    assert " ".join(first_line.text.split()) in " ".join(item["text"] for item in game.backend.texts)
    press(game, "escape")
    press(game, "escape")
    press(game, "j")
    assert isinstance(game.scene, JournalScene)
    press(game, "escape")
    press(game, "escape")
    assert game.scene is mission
    assert json.dumps(mission.get_save_state(), sort_keys=True) == saved
    press(game, "f1")
    assert isinstance(game.scene, HelpScene)
    assert any("journal" in item["text"].lower() for item in game.backend.texts)


@pytest.mark.slow
@pytest.mark.parametrize("size", [(1200, 680), (1280, 800)])
def test_keeper_focus_keeps_every_current_maw_objective_visible(tmp_path, size):
    """Slow: the real finale HUD and keeper command card must fit after banner and notices finish."""
    from warband.sim.rules import Difficulty
    from warband.story.mission_scene import MissionScene

    game = Game("Maw objectives", backend="mock", resolution=size,
                theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    run = build_world(UNDERTOW.mission("undertow_maw"), flags={})
    scene = MissionScene(UNDERTOW, run, difficulty=Difficulty.MEDIUM)
    try:
        game.push(scene)
        for _ in range(12):
            game.tick(.1)
        scene.paused = True
        for _ in range(120):
            game.tick(.1)
        press(game, "f3")
        assert scene.selection == [run.unit("issa").id]
        assert scene.objectives_body.visible
        rendered = " ".join(item["text"] for item in game.backend.texts)
        for objective in scene.mission.objectives:
            if run.state[objective.id] != "hidden":
                assert " ".join(objective.text.split()) in rendered
        assert_text_fits(game)
        _, objective_y, _, objective_height = scene.objectives.bounds
        _, card_y, _, _ = scene.card_panel.bounds
        assert objective_y + objective_height <= card_y
    finally:
        game.close()
