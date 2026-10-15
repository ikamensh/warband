"""Story answers remain readable and selectable at the compact supported window."""

import pytest

from saga2d import Game, Scene
from saga2d.testing import assert_no_text_overlap, assert_text_fits
from warband.art.visual_lint import use_real_text_metrics
from warband.story.campaign import Choice, Line
from warband.story.catalog import UNDERTOW
from warband.story.dialog import DialogScene
from warband.story import undertow_dialogue
from warband.ui.style import build_theme


def test_conversation_has_its_own_screen_and_returns_to_the_frozen_scene(tmp_path):
    """A conversation owns the screen and input; the underlying mission resumes at exactly the same instant."""
    class Battlefield(Scene):
        elapsed = 0.0

        def update(self, dt):
            self.elapsed += dt

        def draw(self):
            self.draw_text("BATTLEFIELD HUD", 10, 20)

    game = Game("Story view", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        battlefield = Battlefield()
        game.push(battlefield)
        game.tick(.1)
        before = battlefield.elapsed
        game.push(DialogScene((Line("Issa", "Keep the village safe first."),), UNDERTOW.speakers, {}))
        game.tick(.1)
        assert battlefield.elapsed == before
        assert "BATTLEFIELD HUD" not in [item["text"] for item in game.backend.texts]
        game.backend.inject_key("return")
        game.tick(.1)
        assert game.scene is battlefield
        assert battlefield.elapsed > before
    finally:
        game.close()


@pytest.mark.parametrize("choice", [item for dialog in (undertow_dialogue.GROVE_PLAN, undertow_dialogue.WEIGHT_CONFESSION)
                                    for item in dialog if isinstance(item, Choice)], ids=lambda choice: choice.key)
def test_long_choice_answers_fit_and_number_keys_keep_their_meaning(tmp_path, choice):
    """The actual grove and seam answers must fit and retain their number-key bindings."""
    game = Game("Story choices", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    variables = {}
    try:
        game.push(Scene())
        dialog = DialogScene((choice,), UNDERTOW.speakers, variables)
        game.push(dialog)
        game.tick(.1)
        assert_text_fits(game)
        assert_no_text_overlap(game, top_scene_only=True)
        portrait = game.assets.image(f"story.portrait.{UNDERTOW.speakers[choice.speaker].portrait}")
        assert any(item["image"] == portrait for item in game.backend.images)
        game.backend.inject_key(str(len(choice.options)))
        game.tick(.1)
        assert variables[choice.key] == choice.options[-1].value
        assert game.scene is not dialog
    finally:
        game.close()


@pytest.mark.slow
@pytest.mark.parametrize("size", [(1200, 680), (1280, 800)])
def test_every_authored_undertow_line_fits_the_dialogue_panel(tmp_path, size):
    """Slow: walk all authored conversations and conditional endings at both supported window sizes."""
    dialogs = [dialog for name, dialog in vars(undertow_dialogue).items()
               if name.isupper() and isinstance(dialog, tuple)]
    dialogs += [dialog for mission in UNDERTOW.missions for dialog in (mission.briefing, mission.debrief)]
    items = list(dict.fromkeys(item for dialog in dialogs for item in dialog))
    game = Game("Campaign dialogue", backend="mock", resolution=size,
                theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    try:
        game.push(Scene())
        for item in items:
            variables = {item.when: True} if isinstance(item, Line) and item.when else {}
            if isinstance(item, Line) and item.unless:
                variables[item.unless] = False
            scene = DialogScene((item,), UNDERTOW.speakers, variables)
            game.push(scene)
            game.tick(.1)
            assert scene.current is item
            assert_text_fits(game)
            assert_no_text_overlap(game, top_scene_only=True)
            game.pop()
    finally:
        game.close()
