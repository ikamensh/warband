"""Inspect forest ground and the real chopping cycle, including the cleared ground.

    uv run python tools/verify_warband_forest.py /tmp/warband-forest
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["SAGA2D_SILENT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from tools.native_frames import tick  # noqa: E402
from tools.verify_warband_art import settlement  # noqa: E402
from warband import textures  # noqa: E402
from warband.rules import MapTheme, Resource, Terrain  # noqa: E402
from warband.style import build_theme  # noqa: E402


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-forest-") as scratch:
        game = Game("Forest ground verification", resolution=(1280, 800), backend="pyglet",
                    visible=False, save_dir=Path(scratch), theme=build_theme())
        try:
            fonts.load(game)
            for theme in MapTheme:
                scene, workers, targets = settlement()
                scene.world.theme = theme
                scene.selection = []
                scene.paused = True
                game.clear_and_push(scene)
                scene.camera.zoom = 2.0
                scene.camera.center_on(32 * textures.TILE, 11.5 * textures.TILE)
                for _ in range(20):
                    tick(game, 0.2)  # Clear the opening banner without advancing the world.
                game.backend.capture_frame().save(output / f"{theme.value}-forest.png")
                if theme is not MapTheme.SUMMER:
                    continue
                for worker, target in zip(workers, targets):
                    scene.world.harvest([worker.id], target)
                scene.paused = False
                for _ in range(3):
                    tick(game, 1 / 30)
                poses: dict[str, Image.Image] = {}
                frames: list[Image.Image] = []
                for _ in range(32):
                    tick(game, 1 / 30)
                    sprite = scene.view.unit_sprite(workers[0].id)
                    assert sprite is not None
                    pose = sprite.image.rsplit(".", 1)[-1]
                    assert pose in textures.CHOP_FRAMES
                    capture = game.backend.capture_frame()
                    scale = game.backend.scale_factor
                    a = scene.camera.world_to_screen(27.5 * textures.TILE, 7.5 * textures.TILE)
                    b = scene.camera.world_to_screen(37.5 * textures.TILE, 15 * textures.TILE)
                    crop = capture.crop(tuple(round(v * scale) for v in (*a, *b)))
                    poses.setdefault(pose, crop)
                    frames.append(crop.convert("RGB"))
                assert set(poses) == set(textures.CHOP_FRAMES)
                for pose, image in poses.items():
                    image.save(output / f"{pose}.png")
                frames[0].save(output / "workers-chopping.gif", save_all=True, append_images=frames[1:], duration=33, loop=0)
                # The same live scene must reveal ordinary grass after the tree disappears.
                for _ in range(150):
                    tick(game, 1 / 30)
                    if workers[0].carrying is Resource.LUMBER:
                        break
                assert workers[0].carrying is Resource.LUMBER
                assert scene.world.terrain_at(targets[0]) is Terrain.GRASS
                game.backend.capture_frame().save(output / "summer-cleared.png")
        finally:
            game.close()
    print(f"Native forest/harvesting verification passed: {output.resolve()}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband-forest"))
