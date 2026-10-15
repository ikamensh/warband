"""Authored story portraits play through the same dialogue controls as unit portraits."""

from saga2d import Game
from warband.sim.rules import Race, UnitType
from warband.story.campaign import Line, Speaker
from warband.story.dialog import DialogScene
from warband.ui.style import build_theme


def test_a_character_portrait_draws_and_the_dialogue_advances(tmp_path) -> None:
    """A campaign can show its own character art without changing how the player reads a line."""
    game = Game("Story portrait", backend="mock", resolution=(1200, 680), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        speaker = Speaker("Captain Issa Renn", Race.HUMAN, UnitType.KNIGHT, portrait="campaign/issa.png")
        scene = DialogScene((Line("Issa", "Then we walk down, one lock at a time."),), {"Issa": speaker}, {})
        game.push(scene)
        game.tick(1 / 60)
        assert any(image["width"] == 104 and image["height"] == 104 for image in game.backend.images)
        assert "Captain Issa Renn" in [text["text"] for text in game.backend.texts]
        game.backend.inject_key("space")
        game.tick(1 / 60)
        assert game.scene is None
    finally:
        game.close()
