"""Capture each race's own unit (WB-068) in play and on its card, natively, and lay the frames out to look at.

    caffeinate -d -u uv run python tools/verify_own_units.py OUT

One montage per unit, at the near zoom: the gryphon rider after a flying machine and a footman (its storm hammer in
the air), the goblin sapper running at a tower alone and going up with it (the blast, frame by frame, under the fog
its owner plays under: its eyes go up with it), the treant walking through a wood a footman walks round, and the rune
golem slamming a knot of footmen.  Then each race's building card with its own unit on it, the Keep researched, and
a Stables training knights endlessly while its three gryphon riders are out.  The display must be awake.  No real
player data is read or written.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("SAGA2D_SILENT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from warband.art import textures  # noqa: E402
from warband.sim.model import World  # noqa: E402
from warband.sim.rules import OWN_UNITS, BuildingType, Race, Terrain, UnitType, Upgrade  # noqa: E402
from warband.sim.races import RACES  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

CELL = (360, 260)  # logical pixels round the middle of the action in every tile of a montage


def field(races: tuple[Race, Race], trees=()) -> World:
    terrain = [[Terrain.GRASS] * 40 for _ in range(30)]
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(40, 30, terrain, 2, races=list(races))
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    return world


class Capture:
    def __init__(self, zoom: float) -> None:
        self.zoom = zoom
        self.temporary = tempfile.TemporaryDirectory(prefix="warband-own-units-")
        self.game = Game("Warband own units", resolution=(1280, 800), visible=False, theme=build_theme(),
                         save_dir=Path(self.temporary.name) / "saves")
        fonts.load(self.game)
        self.settings = {"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False}

    def scene(self, world: World, center: tuple[float, float], *, reveal: bool = True) -> GameScene:
        scene = GameScene(world, 0, ranked=False, settings=self.settings)
        self.game.push(scene)
        scene._warm = None  # the tool's own frames: no warming spread over them
        scene.view.set_reveal(reveal)
        scene.camera.zoom = self.zoom
        scene.camera.center_on(center[0] * textures.TILE, center[1] * textures.TILE)
        scene.paused = True
        for _ in range(8):  # retire the intro banner without advancing the field
            self.game.tick(1.0)
        scene.paused = False
        return scene

    def frame(self) -> Image.Image:
        return self.game.backend.capture_frame().convert("RGB").resize(self.game.resolution)

    def around(self, scene: GameScene, point: tuple[float, float], cell: tuple[int, int] = CELL) -> Image.Image:
        sx, sy = scene.camera.world_to_screen(point[0] * textures.TILE, point[1] * textures.TILE)
        w, h = cell
        return self.frame().crop((round(sx - w / 2), round(sy - h / 2), round(sx + w / 2), round(sy + h / 2)))

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds * 60)):
            self.game.tick(1 / 60)

    def done(self) -> None:
        self.game.pop()
        self.game.tick(1 / 60)

    def gryphon(self) -> Image.Image:
        world = field((Race.HUMAN, Race.ORC))
        gryphon = world.spawn_unit(0, UnitType.GRYPHON, (15.5, 14.5))
        catapult = world.spawn_unit(1, UnitType.CATAPULT, (19.5, 14.5))
        machine = world.spawn_unit(1, UnitType.FLYING_MACHINE, (19.0, 11.5))
        world.hold([catapult.id, machine.id])
        scene = self.scene(world, (18.0, 10.5))  # the camera above the action: the zeppelin is drawn in the air over it
        world.attack([gryphon.id], catapult.id)
        cells = []
        for _ in range(8):  # the hammer thrown at the catapult on the ground…
            self.run(0.25)
            cells.append(self.around(scene, (18.0, 11.9), (500, 380)))
        world.attack([gryphon.id], machine.id)
        for _ in range(8):  # …and at the zeppelin in the air
            self.run(0.25)
            cells.append(self.around(scene, (18.0, 11.9), (500, 380)))
        self.done()
        return montage(cells, 4)

    def sapper(self) -> Image.Image:
        world = field((Race.ORC, Race.HUMAN))
        tower = world.place_building(1, BuildingType.TOWER, (20, 12))
        world.spawn_unit(1, UnitType.FOOTMAN, (19.0, 15.0))
        sapper = world.spawn_unit(0, UnitType.SAPPER, (14.5, 13.0))
        scene = self.scene(world, (19.0, 13.0), reveal=False)  # alone: nothing else of its side sees the tower
        world.attack([sapper.id], tower.id)
        cells = [self.around(scene, (19.0, 13.0))]
        for _ in range(60 * 6):
            self.game.tick(1 / 60)
            if sapper.id not in world.units:
                break
            if self.game.backend is not None and len(cells) < 4 and scene.clock % 0.5 < 1 / 60:
                cells.append(self.around(scene, (19.0, 13.0)))
        for _ in range(8):  # the blast, frame by frame
            cells.append(self.around(scene, (19.0, 13.0)))
            self.run(3 / 60)
        self.run(1.0)
        cells.append(self.around(scene, (19.0, 13.0)))
        self.done()
        return montage(cells, 4)

    def treant(self) -> Image.Image:
        wood = [(x, y) for x in range(17, 22) for y in range(6, 22)]
        world = field((Race.ELF, Race.HUMAN), trees=wood)
        treant = world.spawn_unit(0, UnitType.TREANT, (13.5, 13.5))
        footman = world.spawn_unit(0, UnitType.FOOTMAN, (13.5, 15.5))
        scene = self.scene(world, (19.5, 14.0))
        world.move([treant.id], (26.5, 13.5))
        world.move([footman.id], (26.5, 15.5))
        cells = []
        for _ in range(8):
            cells.append(self.around(scene, (19.5, 14.0), (560, 360)))
            self.run(0.8)
        treant.hp = treant.max_hp // 2
        self.done()
        return montage(cells, 4)

    def golem(self) -> Image.Image:
        world = field((Race.DWARF, Race.HUMAN))
        golem = world.spawn_unit(0, UnitType.RUNE_GOLEM, (16.5, 13.5))
        world.spawn_unit(0, UnitType.FOOTMAN, (17.0, 15.0))
        knot = [world.spawn_unit(1, UnitType.FOOTMAN, (18.3 + 0.75 * (i % 2), 12.9 + 0.75 * (i // 2))) for i in range(4)]
        world.hold([u.id for u in knot])
        scene = self.scene(world, (18.0, 13.5))
        world.attack([golem.id], knot[0].id)
        cells = []
        for _ in range(12):
            cells.append(self.around(scene, (18.0, 13.5)))
            self.run(0.25)
        self.done()
        return montage(cells, 4)

    def cards(self) -> Image.Image:
        cells = []
        for race in Race:
            world = field((race, Race.HUMAN if race is not Race.HUMAN else Race.ORC))
            unit = OWN_UNITS[race]
            building = world.place_building(0, RACES[race].units[unit].trained_at, (8, 8))
            world.players[0].upgrades.add(Upgrade.KEEP)
            world.players[0].gold = world.players[0].lumber = 9000
            scene = self.scene(world, (9.5, 9.5))
            scene.select([building.id])
            self.run(0.3)
            frame = self.frame()
            x, y, w, h = scene.card_panel.bounds
            px, py, pw, ph = scene.selection_panel.bounds
            left, top = min(x, px), min(y, py)
            cells.append(frame.crop((round(left) - 4, round(top) - 4, round(max(x + w, px + pw)) + 4, round(max(y + h, py + ph)) + 4)))
            self.done()
        width = max(c.width for c in cells)
        return montage([c.resize((width, round(c.height * width / c.width))) for c in cells], 1)

    def endless(self) -> Image.Image:
        """A Stables with knights and gryphon riders endless, three riders out and no gold: the panel names the knight
        as the next, why it waits, and the riders at their limit."""
        world = field((Race.HUMAN, Race.ORC))
        stables = world.place_building(0, BuildingType.STABLES, (8, 8))
        world.players[0].upgrades.add(Upgrade.KEEP)
        world.players[0].gold = 0
        scene = self.scene(world, (9.5, 9.5))
        world.set_auto_train(stables.id, UnitType.KNIGHT, True)
        world.set_auto_train(stables.id, UnitType.GRYPHON, True)
        for i in range(3):
            world.spawn_unit(0, UnitType.GRYPHON, (8.5 + i, 11.5))
        scene.select([stables.id])
        self.run(1.2)
        frame = self.frame()
        x, y, w, h = scene.card_panel.bounds
        px, py, pw, ph = scene.selection_panel.bounds
        crop = frame.crop((round(min(x, px)) - 4, round(min(y, py)) - 4, round(max(x + w, px + pw)) + 4, round(max(y + h, py + ph)) + 4))
        self.done()
        return crop

    def close(self) -> None:
        self.game._teardown()
        self.game.backend.quit()
        self.temporary.cleanup()


def montage(cells: list[Image.Image], columns: int) -> Image.Image:
    w, h = max(c.width for c in cells), max(c.height for c in cells)
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (w + 4) + 4, rows * (h + 4) + 4), (24, 24, 28))
    for index, cell in enumerate(cells):
        sheet.paste(cell, (4 + (index % columns) * (w + 4), 4 + (index // columns) * (h + 4)))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--zoom", type=float, default=2.0, help="camera zoom: 1 is gameplay, 2 is near")
    parser.add_argument("--only", default="gryphon,sapper,treant,golem,cards,endless", help="comma-separated scenes")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    capture = Capture(args.zoom)
    try:
        for name in args.only.split(","):
            getattr(capture, name)().save(args.output / f"{name}.png")
            print(f"{name}: {args.output / f'{name}.png'}")
    finally:
        capture.close()


if __name__ == "__main__":
    main()
