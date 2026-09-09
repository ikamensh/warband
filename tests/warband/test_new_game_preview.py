"""The new-game screen shows a map preview with the opponents' races."""

import time

from saga2d import Game
from warband import mapgen
from warband.races import RACES
from warband.style import build_theme
from warband.title import NewGameScene, TitleScene, preview_image


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
        handle = game.assets.image(scene._preview_key)
        drawn = [i["image"] for i in game.backend.images]
        sprites = [s["image"] for s in game.backend.sprites.values()]
        assert handle in drawn or handle in sprites
        assert any("Opponents:" in t for t in texts(game))
    finally:
        game._teardown()


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
        game._teardown()


def test_large_preview_is_256x192(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        press(game, "l")
        scene = game.scene
        assert scene.size == "Large"
        handle = game.assets.image(scene._preview_key)
        assert game.backend.get_image_size(handle) == (256, 192)
    finally:
        game._teardown()


def test_opponent_line_matches_mapgen(tmp_path) -> None:
    game = open_new_game(tmp_path)
    try:
        scene = game.scene
        width, height = mapgen.SIZES[scene.size]
        expected_world = mapgen.generate(
            scene.seed, width, height, scene.players,
            theme=scene.theme, races=[scene.race] + [None] * (scene.players - 1),
        )
        expected = "Opponents: " + ", ".join(RACES[p.race].name for p in expected_world.players[1:])
        assert expected in texts(game)
    finally:
        game._teardown()


def test_large_preview_generation_is_fast() -> None:
    from warband.rules import MapTheme, Race

    t0 = time.perf_counter()
    world = mapgen.generate(12345, 64, 48, 4, theme=MapTheme.SUMMER, races=[Race.HUMAN, None, None, None])
    image = preview_image(world)
    elapsed = time.perf_counter() - t0
    assert image.size == (256, 192)
    assert elapsed < 1.0
