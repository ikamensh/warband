"""Story answers remain readable and selectable at the compact supported window."""

import pytest

from saga2d import Game, Scene
from saga2d.testing import assert_no_text_overlap, assert_text_fits
from warband.art.visual_lint import use_real_text_metrics
from warband.story.campaign import Choice, Line, Option
from warband.story.catalog import UNDERTOW
from warband.story.dialog import DialogScene
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


@pytest.mark.parametrize("options", [
    (Option("Hold it through the surges", True), Option("Shutter it at the pylon", False)),
    (Option("Cap it with a vault on its rift", "cap"), Option("Work it and pay for the siege", "mine"),
     Option("Post a guard and close the face", "guard")),
])
def test_long_choice_answers_fit_and_number_keys_keep_their_meaning(tmp_path, options):
    """The actual Millfield and seam answers must not collide with each other or their keycaps."""
    game = Game("Story choices", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    variables = {}
    try:
        game.push(Scene())
        dialog = DialogScene((Choice("choice", "Dagna", "The seam, Captain?", options),), UNDERTOW.speakers, variables)
        game.push(dialog)
        game.tick(.1)
        assert_text_fits(game)
        assert_no_text_overlap(game, top_scene_only=True)
        portrait = game.assets.image(f"story.portrait.{UNDERTOW.speakers['Dagna'].portrait}")
        assert any(item["image"] == portrait for item in game.backend.images)
        game.backend.inject_key(str(len(options)))
        game.tick(.1)
        assert variables["choice"] == options[-1].value
        assert game.scene is not dialog
    finally:
        game.close()
