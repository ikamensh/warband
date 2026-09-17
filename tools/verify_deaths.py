"""Capture deaths natively and lay the frames out to look at.

    uv run python tools/verify_deaths.py docs/evidence/deaths/before
    WARBAND_ART=procedural uv run python tools/verify_deaths.py docs/evidence/deaths/before-procedural

One victim per category (infantry, archer, mounted, siege) takes a killing blow from the west and
then from the east; frames every three display frames from the blow for 0.9 s, then lying and fading,
tiled into one PNG per victim. A mass-casualty scene at normal zoom is captured at several seconds.
The display must be awake (``caffeinate -u``). No real player data is read or written.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("SAGA2D_SILENT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from warband import textures  # noqa: E402
from warband.model import World  # noqa: E402
from warband.rules import BuildingType, Terrain, UnitType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402

VICTIMS = {"infantry": UnitType.FOOTMAN, "archer": UnitType.ARCHER, "mounted": UnitType.KNIGHT, "siege": UnitType.CATAPULT}
CELL = (200, 150)  # logical pixels around the victim in every tile of the montage


def field() -> World:
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    return world


class Capture:
    def __init__(self, output: Path):
        self.output = output
        self.temporary = tempfile.TemporaryDirectory(prefix="warband-deaths-")
        self.game = Game("Warband deaths", resolution=(1280, 800), visible=False, theme=build_theme(),
                         save_dir=Path(self.temporary.name) / "saves")
        fonts.load(self.game)
        self.settings = {"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False}

    def scene(self, world: World, center: tuple[float, float]) -> GameScene:
        scene = GameScene(world, 0, ranked=False, settings=self.settings)
        self.game.push(scene)
        scene._warm = None
        scene.view.set_reveal(True)
        scene.camera.center_on(center[0] * textures.TILE, center[1] * textures.TILE)
        scene.paused = True
        for _ in range(8):  # retire the intro banner without advancing the field
            self.game.tick(1.0)
        scene.paused = False
        return scene

    def frame(self) -> Image.Image:
        return self.game.backend.capture_frame().convert("RGB").resize(self.game.resolution)

    def around(self, scene: GameScene, point: tuple[float, float]) -> Image.Image:
        sx, sy = scene.camera.world_to_screen(point[0] * textures.TILE, point[1] * textures.TILE)
        w, h = CELL
        return self.frame().crop((round(sx - w / 2), round(sy - h * 0.62), round(sx + w / 2), round(sy + h * 0.38)))

    def single(self, name: str, kind: UnitType, side: str) -> Image.Image:
        world = field()
        victim = world.spawn_unit(1, kind, (20.5, 12.5))
        victim.hp = 1
        ax = 19.2 if side == "west" else 21.8
        attacker = world.spawn_unit(0, UnitType.KNIGHT, (ax, 12.5))
        scene = self.scene(world, (20.5, 12.5))
        world.attack([attacker.id], victim.id)
        for _ in range(60 * 4):
            self.game.tick(1 / 60)
            if victim.id not in world.units:
                break
        else:
            raise RuntimeError(f"{name}: the {kind.value} did not die")
        cells = []
        for step in range(18):  # 0.9 s from the killing blow
            cells.append(self.around(scene, (20.5, 12.5)))
            for _ in range(3):
                self.game.tick(1 / 60)
        for seconds in (1.5, 4.0, 1.5):  # lying, still lying, fading
            for _ in range(round(seconds * 60)):
                self.game.tick(1 / 60)
            cells.append(self.around(scene, (20.5, 12.5)))
        self.game.pop()
        self.game.tick(1 / 60)
        return montage(cells, 7)

    def mass(self) -> Image.Image:
        world = field()
        victims = [world.spawn_unit(1, UnitType.FOOTMAN, (18.5 + col, 10.5 + row)) for row in range(4) for col in range(4)]
        for victim in victims:
            victim.hp = 1
        attackers = [world.spawn_unit(0, UnitType.KNIGHT, (16.0 + (row % 2) * 0.7, 10.5 + row * 0.8)) for row in range(4)]
        scene = self.scene(world, (19.5, 12.0))
        for attacker in attackers:
            world.attack_move([attacker.id], (20.0, 12.0))
        cells, elapsed = [], 0.0
        for seconds in (1.0, 2.0, 3.0, 4.0, 6.0, 9.0, 12.0, 14.0):
            while elapsed < seconds:
                self.game.tick(1 / 60)
                elapsed += 1 / 60
            frame = self.frame()
            sx, sy = scene.camera.world_to_screen(19.5 * textures.TILE, 12.0 * textures.TILE)
            cells.append(frame.crop((round(sx - 260), round(sy - 200), round(sx + 260), round(sy + 190))))
        self.game.pop()
        self.game.tick(1 / 60)
        return montage(cells, 4)

    def close(self) -> None:
        self.game._teardown()
        self.game.backend.quit()
        self.temporary.cleanup()


def montage(cells: list[Image.Image], columns: int) -> Image.Image:
    w, h = cells[0].size
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (w + 4) + 4, rows * (h + 4) + 4), (24, 24, 28))
    for index, cell in enumerate(cells):
        sheet.paste(cell, (4 + (index % columns) * (w + 4), 4 + (index // columns) * (h + 4)))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--victims", default=",".join(VICTIMS), help="comma-separated categories (default: all)")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    capture = Capture(args.output)
    try:
        for name in args.victims.split(","):
            for side in ("west", "east"):
                capture.single(name, VICTIMS[name], side).save(args.output / f"{name}-from-{side}.png")
                print(f"{name} from the {side}: {args.output / f'{name}-from-{side}.png'}")
        capture.mass().save(args.output / "mass.png")
        print(f"mass casualties: {args.output / 'mass.png'}")
    finally:
        capture.close()


if __name__ == "__main__":
    main()
