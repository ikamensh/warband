"""Capture walking and woodcutting through the actual game renderer.

    caffeinate -d -u python3 ../tools/slot.py -- uv run python tools/verify_gait.py OUT

An archer, knight and bear rider walk along marked lanes at their real movement
speeds, followed by human workers chopping from three directions. Writes one
motion video, a contact sheet of every displayed pose, a native full frame and
capture metadata. Requires an awake display and ffmpeg. No player files are used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

os.environ.setdefault("SAGA2D_SILENT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from saga2d import Game, RenderLayer, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband.art import textures  # noqa: E402
from warband.sim.model import Harvest, Unit, World  # noqa: E402
from warband.sim.rules import BuildingType, Race, Terrain, UnitType  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

RESOLUTION = (1280, 960)
FPS = 30
CELL = (230, 180)
SETTINGS = {"tutorial": False, "music": 0.0, "sfx": 0.0, "edge_scroll": False}


class GaitScene(GameScene):
    """The real match scene, with ground marks and subject labels for inspection."""

    def __init__(self, world: World, subjects: list[tuple[str, Unit]], title: str, *, lanes: bool = False) -> None:
        super().__init__(world, 0, ranked=False, settings=SETTINGS)
        self.subjects, self.capture_title, self.lanes = subjects, title, lanes

    def draw(self) -> None:
        super().draw()
        if self.lanes:
            for _, unit in self.subjects:
                y = unit.y * textures.TILE
                self.draw_line(2 * textures.TILE, y, 38 * textures.TILE, y,
                               (223, 210, 163, 115), space="world", layer=RenderLayer.OBJECTS)
                for x in range(2, 39):
                    self.draw_line(x * textures.TILE, y - 5, x * textures.TILE, y + 5,
                                   (223, 210, 163, 180), space="world", layer=RenderLayer.OBJECTS)
        self.draw_rect(850, 20, 410, 70, (15, 23, 19, 225), radius=5)
        self.draw_text(self.capture_title, 864, 45, font=fonts.EXTRABOLD, font_size=18, color=(242, 231, 203, 255))
        self.draw_text("Real orders  /  zoom 2  /  marks = 1 tile", 864, 72,
                       font_size=12, color=(197, 204, 180, 255))
        for label, unit in self.subjects:
            sprite = self.view.unit_sprite(unit.id)
            if sprite is not None:
                x, y = self.camera.world_to_screen(sprite.x, sprite.y - textures.placements[sprite.image].drop)
                self.draw_text(label, x, y + 23, anchor_x="center", font_size=12, color=(248, 239, 213, 255))


def field(*, trees: tuple[tuple[int, int], ...] = ()) -> World:
    terrain = [[Terrain.GRASS] * 40 for _ in range(30)]
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(40, 30, terrain, 2, races=(Race.HUMAN, Race.DWARF), scripted=True, wilds=False)
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    return world


def install(game: Game, scene: GaitScene, center: tuple[float, float]) -> None:
    game.clear_and_push(scene)
    scene._warm = None  # The utility warms every required image before the measured journey.
    scene.view.set_reveal(True)
    scene.camera.zoom = 2.0
    scene.camera.center_on(center[0] * textures.TILE, center[1] * textures.TILE)
    scene.execution.paused = True
    for _ in range(8):  # Retire the opening banner without moving the subjects.
        game.tick(1.0)
    scene.execution.paused = False


def crop_subject(frame: Image.Image, scene: GaitScene, unit: Unit) -> Image.Image:
    sprite = scene.view.unit_sprite(unit.id)
    assert sprite is not None and sprite.visible, unit.id
    x, y = scene.camera.world_to_screen(sprite.x, sprite.y - textures.placements[sprite.image].drop)
    width, height = CELL
    return frame.crop((round(x - width / 2), round(y - height + 26), round(x + width / 2), round(y + 26)))


def contact_sheet(rows: list[tuple[str, tuple[str, ...], dict[str, Image.Image]]]) -> Image.Image:
    width, height = CELL
    columns = max(len(poses) for _, poses, _ in rows)
    row_height = height + 44
    sheet = Image.new("RGB", (width * columns, row_height * len(rows)), (20, 30, 26))
    draw = ImageDraw.Draw(sheet)
    for row, (label, poses, images) in enumerate(rows):
        missing = set(poses) - images.keys()
        assert not missing, (label, missing)
        top = row * row_height
        draw.text((10, top + 7), label, fill=(242, 231, 203))
        for column, pose in enumerate(poses):
            left = column * width
            sheet.paste(images[pose], (left, top + 24))
            draw.text((left + 10, top + height + 28), pose, fill=(197, 204, 180))
    return sheet


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, tuple[str, ...], dict[str, Image.Image]]] = []
    report: list[dict[str, object]] = []
    encoder = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{RESOLUTION[0]}x{RESOLUTION[1]}", "-framerate", str(FPS), "-i", "pipe:0", "-an",
        "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(output / "motion.mp4"),
    ], stdin=subprocess.PIPE)
    assert encoder.stdin is not None
    try:
        with tempfile.TemporaryDirectory(prefix="warband-gait-") as scratch:
            game = Game("Warband gait verification", resolution=RESOLUTION, backend="pyglet", visible=False,
                        theme=build_theme(), save_dir=Path(scratch) / "saves")
            try:
                fonts.load(game)
                world = field()
                subjects = [("Human archer", world.spawn_unit(0, UnitType.ARCHER, (8.5, 10.5))),
                            ("Human knight", world.spawn_unit(0, UnitType.KNIGHT, (8.5, 13.5))),
                            ("Dwarf bear rider", world.spawn_unit(1, UnitType.KNIGHT, (8.5, 16.5)))]
                scene = GaitScene(world, subjects, "Walking: planted feet", lanes=True)
                install(game, scene, (14.0, 12.25))
                for _, unit in subjects:
                    for pose in textures.WALK_FRAMES:
                        textures.unit_image(game, unit.type, unit.player, 0, pose, race=unit.race)
                    world.move([unit.id], (35.5, unit.y))
                images: dict[int, dict[str, Image.Image]] = {unit.id: {} for _, unit in subjects}
                starts = {unit.id: unit.pos for _, unit in subjects}
                for frame_number in range(4 * FPS):
                    tick(game, 1 / FPS)
                    native = game.backend.capture_frame().convert("RGB")
                    frame = native.resize(RESOLUTION)
                    encoder.stdin.write(frame.tobytes())
                    if frame_number == FPS:
                        native.save(output / "gameplay.png")
                    for _, unit in subjects:
                        sprite = scene.view.unit_sprite(unit.id)
                        assert sprite is not None and sprite.visible, unit.id
                        pose = sprite.image.rsplit(".", 1)[-1]
                        if frame_number >= FPS // 2 and pose in textures.WALK_FRAMES and pose not in images[unit.id]:
                            images[unit.id][pose] = crop_subject(frame, scene, unit)
                for label, unit in subjects:
                    rows.append((label, textures.WALK_FRAMES, images[unit.id]))
                    report.append({"subject": label, "start": starts[unit.id], "end": unit.pos,
                                   "seconds": 4, "poses": list(images[unit.id])})

                targets = ((12, 13), (17, 13), (22, 13))
                world = field(trees=targets)
                subjects = [(label, world.spawn_unit(0, UnitType.PEASANT, position)) for label, position in (
                    ("Worker: facing east", (11.65, 13.5)), ("Worker: facing north", (17.5, 14.35)),
                    ("Worker: facing west", (23.35, 13.5)))]
                scene = GaitScene(world, subjects, "Woodcutting: axe swing")
                install(game, scene, (17.5, 12.5))
                for (_, unit), target in zip(subjects, targets):
                    world.harvest([unit.id], target)
                images = {unit.id: {} for _, unit in subjects}
                for frame_number in range(3 * FPS):
                    tick(game, 1 / FPS)
                    frame = game.backend.capture_frame().convert("RGB").resize(RESOLUTION)
                    encoder.stdin.write(frame.tobytes())
                    for _, unit in subjects:
                        assert isinstance(unit.order, Harvest), (unit.id, unit.order)
                        sprite = scene.view.unit_sprite(unit.id)
                        assert sprite is not None and sprite.visible, unit.id
                        pose = sprite.image.rsplit(".", 1)[-1]
                        if frame_number >= FPS // 2 and pose in textures.CHOP_FRAMES and pose not in images[unit.id]:
                            images[unit.id][pose] = crop_subject(frame, scene, unit)
                for label, unit in subjects:
                    rows.append((label, textures.CHOP_FRAMES, images[unit.id]))
                    report.append({"subject": label, "state": unit.state, "facing": unit.facing,
                                   "poses": list(images[unit.id])})
            finally:
                game.close()
    finally:
        encoder.stdin.close()
        result = encoder.wait()
    if result:
        raise RuntimeError(f"Gait video encoding failed: ffmpeg exited {result}")
    contact_sheet(rows).save(output / "contact-sheet.png")
    metadata = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
                "command": sys.argv, "art": os.environ.get("WARBAND_ART", "painted"), "subjects": report}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("output", type=Path, help="explicit directory for the capture")
    main(parser.parse_args().output)
