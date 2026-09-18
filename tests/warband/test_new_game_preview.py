"""The new-game screen shows a map preview with the opponents' races."""

import time

import pytest

from saga2d import Game
from warband import mapgen
from warband.races import RACES
from warband.rules import Layout
from warband.style import build_theme
from warband.title import PREVIEW_BOX, PREVIEW_KEY, NewGameScene, TitleScene, preview_image


def open_new_game(tmp_path, resolution=(1280, 800)):
    game = Game("t", backend="mock", resolution=resolution, theme=build_theme(), save_dir=tmp_path / "saves")
    game.push(TitleScene())
    game.tick(1 / 60)
    game.push(NewGameScene(game.scenes[0]))
    game.tick(1 / 60)
    return game


def press(game, key):
    game.backend.inject_key(key)
    game.tick(1 / 60)


def texts(game):
    return [t["text"] for t in game.backend.texts]


def test_preview_is_drawn_with_opponents(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        scene = game.scene
        assert isinstance(scene, NewGameScene)
        assert scene._preview_world is not None and scene._preview_pil is not None
        handle = game.assets.image(PREVIEW_KEY)
        drawn = [i["image"] for i in game.backend.images]
        sprites = [s["image"] for s in game.backend.sprites.values()]
        assert handle in drawn or handle in sprites
        assert any("Opponents:" in t for t in texts(game))
    finally:
        game.close()


def test_reroll_changes_seed_and_image(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        scene = game.scene
        old_seed = scene.seed
        old_bytes = scene._preview_pil.tobytes()
        press(game, "r")
        assert scene.seed != old_seed
        assert scene._preview_pil.tobytes() != old_bytes
    finally:
        game.close()


@pytest.mark.parametrize("key, size, pixels", [("s", "Small", (288, 240)), ("m", "Medium", (320, 240)), ("l", "Large", (240, 192))])
def test_the_preview_fits_its_box_at_whole_pixels_per_tile(tmp_path, key: str, size: str, pixels: tuple[int, int]) -> None:
    game = open_new_game(tmp_path)
    try:
        press(game, key)
        scene = game.scene
        assert scene.size == size
        assert scene._preview_pil.size == pixels
        assert game.backend.get_image_size(game.assets.image(PREVIEW_KEY)) == PREVIEW_BOX  # one slot, the picture centred in it
    finally:
        game.close()


def test_the_map_row_picks_a_layout_and_the_caption_says_what_any_drew(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        scene = game.scene
        assert scene.layout is None
        assert any(t.startswith("Any drew ") for t in texts(game))
        press(game, "f")
        assert scene.layout is Layout.FOREST and scene._preview_world.layout is Layout.FOREST
        assert mapgen.PROMISES[Layout.FOREST] in texts(game)
        press(game, "k")
        assert scene._preview_world.layout is Layout.KLONDIKE
        press(game, "y")
        assert scene.layout is None
    finally:
        game.close()


def test_opponent_line_matches_mapgen(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        scene = game.scene
        width, height = mapgen.SIZES[scene.size]
        expected_world = mapgen.generate(
            scene.seed, width, height, scene.players,
            theme=scene.theme, races=[scene.race] + [None] * (scene.players - 1), layout=scene.layout,
        )
        expected = "Opponents: " + ", ".join(RACES[p.race].name for p in expected_world.players[1:])
        assert expected in texts(game)
    finally:
        game.close()


def test_large_preview_generation_is_fast() -> None:
    from warband.rules import MapTheme, Race

    t0 = time.perf_counter()
    world = mapgen.generate(12345, 64, 48, 4, theme=MapTheme.SUMMER, races=[Race.HUMAN, None, None, None])
    image = preview_image(world)
    elapsed = time.perf_counter() - t0
    assert image.size == (320, 240)
    assert elapsed < 1.0
