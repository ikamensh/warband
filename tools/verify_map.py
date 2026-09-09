"""Inspect the native map rim, fog and seeded terrain regions.

    uv run python tools/verify_warband_map.py /tmp/warband-map

Captures an ordinary fogged game at opposite corners, then fully revealed
survey views using the same MapView assets. Surveys freeze simulation and
reveal terrain for inspection only; they do not change gameplay visibility.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["SAGA2D_SILENT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Camera, Game, Scene, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband import mapgen  # noqa: E402
from warband.rules import MapTheme  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402
from warband.textures import TILE  # noqa: E402
from warband.view import MapView, Overlay  # noqa: E402


class Survey(Scene):
    background_color = (10, 12, 20, 255)

    def __init__(self, seed: int, theme: MapTheme) -> None:
        self.seed, self.theme = seed, theme

    def on_enter(self) -> None:
        self.world = mapgen.generate(self.seed, theme=self.theme)
        self.world.visible[0][:] = bytes([1]) * (self.world.width * self.world.height)
        self.world.explored[0][:] = self.world.visible[0]
        self.camera = Camera(self.game.resolution, zoom=0.54)
        self.camera.center_on(self.world.width * TILE / 2, self.world.height * TILE / 2 - 24)
        self.view = MapView(self, self.world, 0)

    def update(self, dt: float) -> None:
        self.view.sync(dt)

    def draw(self) -> None:
        self.view.draw(Overlay())
        self.draw_text(f"WARBAND  /  {self.theme.value.upper()}  /  SEED {self.seed}", 24, 30,
                       font=fonts.EXTRABOLD, font_size=18, color=(232, 214, 172, 255))
        self.draw_text("Native terrain survey • fog revealed for inspection • simulation frozen", 24, 775,
                       font_size=12, color=(164, 177, 170, 255))


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-map-") as scratch:
        game = Game("Warband map verification", backend="pyglet", visible=False,
                    resolution=(1280, 800), save_dir=Path(scratch), theme=build_theme())
        try:
            fonts.load(game)
            for theme in MapTheme:
                scene = GameScene(mapgen.generate(3, theme=theme), 3)
                scene.paused = True
                game.clear_and_push(scene)
                for _ in range(20):
                    tick(game, 0.2)
                game.backend.capture_frame().save(output / f"{theme.value}-fog-northwest.png")
                scene.camera.center_on(scene.world.width * TILE, scene.world.height * TILE)
                tick(game)
                game.backend.capture_frame().save(output / f"{theme.value}-fog-southeast.png")
                game.clear_and_push(Survey(3, theme))
                for _ in range(4):
                    tick(game)
                game.backend.capture_frame().save(output / f"{theme.value}-regions.png")
            game.clear_and_push(Survey(19, MapTheme.SUMMER))
            for _ in range(4):
                tick(game)
            game.backend.capture_frame().save(output / "summer-seed19-regions.png")
        finally:
            game.close()
    print(f"Native map verification passed: {output.resolve()}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband-map"))
