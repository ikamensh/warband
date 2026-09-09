"""Native results/leaderboard playback, isolated from the player's saves.

Run: uv run python tools/verify_warband_scores.py /tmp/warband-score-shots
Uses completed battle fixtures and real pyglet keyboard/mouse events. The
model integration tests cover combat attribution and recovery decisions.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyglet.window import key, mouse
from saga2d import Game, fonts
from warband.model import World
from warband.rules import Difficulty
from warband.scene import GameOverScene, load_game, new_game
from warband.score_scene import HighScoreScene
from warband.scores import HighScores
from warband.style import build_theme
from warband.title import TitleScene


def verify(out: Path, resolution: tuple[int, int]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-scores-") as temp:
        game = Game("Warband", resolution=resolution, backend="pyglet", visible=False,
                    theme=build_theme(), save_dir=Path(temp) / "saves")
        backend, window = game.backend, game.backend.window
        fonts.load(game)
        settings = {"music": 0, "sfx": 0, "tutorial": False}

        def frames(count=3):
            for _ in range(count):
                started = time.monotonic()
                game.tick(1 / 60)
                time.sleep(max(0, 1 / 30 - (time.monotonic() - started)))

        def press(symbol):
            window.dispatch_event("on_key_press", symbol, 0)
            window.dispatch_event("on_key_release", symbol, 0)
            frames()

        def shot(name):
            frames()
            path = out / f"{resolution[0]}x{resolution[1]}-{name}.png"
            backend.capture_frame().save(path)
            print(path, flush=True)

        try:
            scene = new_game(3, width=40, height=32, settings=settings)
            world = scene.world
            world.time = 645
            for unit in world.player_units(1):
                unit.hp = 0
            world.players[1].gold = world.players[1].lumber = 0
            world.step()
            assert world.players[1].surrendered and world.winner == scene.human
            game.push(scene)
            frames()
            assert isinstance(game.scene, GameOverScene)
            frozen_time = world.time
            entries = HighScores(game.data_dir).load()
            assert len(entries) == 1 and entries[0].victory
            shot("victory")
            state = scene.get_save_state()
            restored = load_game(state, settings=settings)
            game.clear_and_push(restored)
            frames()
            assert isinstance(game.scene, GameOverScene) and restored.world.time == frozen_time
            assert HighScores(game.data_dir).load() == entries
            # Populate ten distinct, completed fixture matches for the dense layout.
            for i in range(1, 11):
                older = World.from_dict(world.to_dict())
                older.time += i * 37
                HighScores(game.data_dir).record(older, player=scene.human, seed=3 + i,
                                                 difficulty=Difficulty.NORMAL, run_id=f"fixture-{i}")
            press(key.B)
            assert isinstance(game.scene, HighScoreScene)
            assert len(HighScores(game.data_dir).load()) == 10
            for count in (3, 4, 2):
                press(key.P)
                assert game.scene.players == count
            shot("leaderboard")
            press(key.D)
            assert game.scene.difficulty is Difficulty.HARD
            shot("empty")
            press(key.ESCAPE)
            assert isinstance(game.scene, GameOverScene)
            press(key.T)
            assert isinstance(game.scene, TitleScene)
            shot("title")
            press(key.B)
            assert isinstance(game.scene, HighScoreScene)
            # Back through a physical mouse click, not a direct scene callback.
            button = game.scene.ui.children[0].children[-1]
            x, y, width, height = button.bounds
            px = int((x + width / 2) * backend.scale_factor + backend.offset_x)
            py = int((resolution[1] - y - height / 2) * backend.scale_factor + backend.offset_y)
            window.dispatch_event("on_mouse_press", px, py, mouse.LEFT, 0)
            window.dispatch_event("on_mouse_release", px, py, mouse.LEFT, 0)
            frames()
            assert isinstance(game.scene, TitleScene)
            # The human can lose while two AI rivals are still fighting.
            defeat = new_game(9, width=40, height=32, players=3, settings=settings)
            defeat.world.time = 720
            for entity in [*defeat.world.player_units(0), *defeat.world.player_buildings(0)]:
                entity.hp = 0
            defeat.world.step()
            assert not defeat.player.alive and defeat.world.winner is None
            game.clear_and_push(defeat)
            frames()
            assert isinstance(game.scene, GameOverScene)
            shot("defeat")
            # Errors must be readable and the damaged file must not be replaced.
            store = HighScores(game.data_dir)
            store.path.write_text("{broken", encoding="utf-8")
            game.clear_and_push(load_game(state, settings=settings))
            frames()
            assert game.scene.score_error
            press(key.B)
            assert isinstance(game.scene, HighScoreScene) and game.scene.error
            shot("storage-error")
            assert store.path.read_text() == "{broken"
            print(f"PASS {resolution}: native keys/mouse, frozen outcomes, reload deduplication, filters, defeat and corruption", flush=True)
        finally:
            game._teardown()
            backend.quit()


if __name__ == "__main__":
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband-score-shots")
    for size in ((1280, 800), (1280, 720)):
        verify(directory, size)
