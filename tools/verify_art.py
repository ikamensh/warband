"""Capture Warband's registered art and real lumber harvesting through pyglet.

    uv run python tools/verify_warband_art.py /tmp/warband_art

Produces labeled asset sheets, settlement views at normal and close zoom,
and four chopping stills plus a GIF from actual World.harvest orders. All
images pass through the game's native drawing path. Keep the display awake
and run this separately from other expensive verification jobs.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

os.environ["SAGA2D_SILENT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from saga2d import Game, Scene, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband import textures  # noqa: E402
from warband.model import Harvest, Unit, World  # noqa: E402
from warband.rules import BUILDINGS, UNITS, BuildingType, MapTheme, Resource, Terrain, UnitType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402

RESOLUTION = (1280, 800)
CREAM = (240, 230, 209, 255)
MUTED = (159, 174, 167, 255)
ACCENT = (212, 177, 97, 255)


@dataclass(frozen=True)
class Card:
    image: str
    label: str
    detail: str = ""


class AssetSheet(Scene):
    """Draw the same registered images used by MapView in a readable grid."""

    background_color = (20, 30, 29, 255)

    def __init__(self, title: str, subtitle: str, cards: list[Card], *, columns: int, zoom: float = 2.0) -> None:
        self.title, self.subtitle, self.cards = title, subtitle, cards
        self.columns, self.zoom = columns, zoom

    def draw(self) -> None:
        self.draw_text("WARBAND  /  PROCEDURAL ART", 28, 31, font=fonts.EXTRABOLD, font_size=12, color=ACCENT)
        self.draw_text(self.title, 28, 67, font=fonts.EXTRABOLD, font_size=28, color=CREAM)
        self.draw_text(self.subtitle, 29, 92, font_size=13, color=MUTED)
        rows = math.ceil(len(self.cards) / self.columns)
        gap, left, top = 12, 28, 115
        cell_w = (RESOLUTION[0] - 2 * left - gap * (self.columns - 1)) / self.columns
        cell_h = (RESOLUTION[1] - top - 38 - gap * (rows - 1)) / rows
        for index, card in enumerate(self.cards):
            x = left + (index % self.columns) * (cell_w + gap)
            y = top + (index // self.columns) * (cell_h + gap)
            self.draw_rect(x, y, cell_w, cell_h, (31, 45, 40, 255), border_color=(58, 72, 59, 255), border_width=1, radius=7)
            w, h = textures.placements[card.image].size
            scale = min(self.zoom, (cell_w - 24) / w, (cell_h - 58) / h)
            image_w, image_h = w * scale, h * scale
            self.draw_image(card.image, x + (cell_w - image_w) / 2, y + 8 + (cell_h - 58 - image_h) / 2, image_w, image_h)
            self.draw_text(card.label, x + cell_w / 2, y + cell_h - 28, anchor_x="center", font=fonts.EXTRABOLD,
                           font_size=14, color=CREAM)
            self.draw_text(card.detail, x + cell_w / 2, y + cell_h - 10, anchor_x="center", font_size=11, color=MUTED)
        self.draw_text("Native game renderer  •  registered in-game assets  •  deterministic procedural geometry", 28, 781,
                       font_size=11, color=MUTED)


def capture(game: Game, output: Path, name: str) -> Image.Image:
    for _ in range(2):
        tick(game)
    image = game.backend.capture_frame()
    image.save(output / f"{name}.png")
    print(f"  {name}.png", flush=True)
    return image


def capture_sheets(game: Game, output: Path) -> None:
    def sheet(name: str, title: str, subtitle: str, cards: list[Card], columns: int, zoom: float = 2.0) -> None:
        game.clear_and_push(AssetSheet(title, subtitle, cards, columns=columns, zoom=zoom))
        capture(game, output, name)

    roles = {
        BuildingType.TOWN_HALL: "Civic keep / economy",
        BuildingType.FARM: "Crop fields / supply",
        BuildingType.BARRACKS: "Garrison / infantry",
        BuildingType.TOWER: "Watchpost / defense",
        BuildingType.LUMBER_MILL: "Timber yard / lumber",
        BuildingType.BLACKSMITH: "Forge / armor and weapons",
        BuildingType.STABLES: "Horse yard / cavalry",
        BuildingType.WORKSHOP: "Siege yard / catapults",
        BuildingType.CHURCH: "Sanctuary / healers",
    }
    sheet("01_buildings", "A building for every purpose", "Nine distinct silhouettes, materials and visible tools of the trade.",
          [Card(textures.building_image(game, kind, 0), BUILDINGS[kind].name, role) for kind, role in roles.items()], 3)

    cards = [Card(textures.unit_image(game, kind, 0, 2, frame), UNITS[kind].name, label)
             for frame, label in (("stand", "At rest"), ("walk1", "On the move"), ("attack", "In action")) for kind in UnitType]
    sheet("02_units", "Read the army at a glance", "Seven roles in their actual stand, movement and action poses.", cards, 7, 2.6)

    cards = [Card(textures.unit_image(game, UnitType.PEASANT, 0, 0, frame), label, "Lumber harvesting")
             for frame, label in zip(textures.CHOP_FRAMES, ("Raise", "Wind up", "Strike", "Recover"))]
    cards += [Card(textures.unit_image(game, UnitType.PEASANT, 0, 2, "walk1", resource), label, "Return to depot")
              for resource, label in ((Resource.LUMBER, "Carry lumber"), (Resource.GOLD, "Carry gold"))]
    sheet("03_workers", "An axe swing with weight", "Four dedicated chopping poses, plus both resource-carrying appearances.", cards, 3, 4.0)

    for theme in MapTheme:
        textures.register_theme(game, theme)
        for kind, count, description in (("tree", textures.TREE_VARIANTS, "Branching growth and varied canopies"),
                                          ("rock", textures.ROCK_VARIANTS, "Faceted stone and mineral formations")):
            cards = [Card(f"{kind}.{theme.value}.{index}", f"{kind.title()} {index + 1:02}", theme.value.title()) for index in range(count)]
            sheet(f"04_{theme.value}_{kind}s", f"{theme.value.title()} / {count} {kind} variants",
                  f"{description}. Every variant is selected by the live map.", cards, 5)

    sheet("05_crystal_mines", "Twenty crystal deposits", "Distinct clusters and rock strata for the map's gold mines.",
          [Card(textures.mine_image(game, index), f"Deposit {index + 1:02}", "Gold mine") for index in range(textures.MINE_VARIANTS)], 5)


def settlement() -> tuple[GameScene, list[Unit], list[tuple[int, int]]]:
    """Build a compact working settlement through public World setup APIs."""
    width, height = 48, 36
    rng = random.Random(17)
    terrain = [[Terrain.GRASS for _ in range(width)] for _ in range(height)]
    for y in range(3, 10):
        for x in range(28, 40):
            if rng.random() < 0.62:
                terrain[y][x] = Terrain.TREES
    for x, y in ((2, 17), (3, 18), (4, 17), (3, 16), (37, 18), (38, 19), (39, 17)):
        terrain[y][x] = Terrain.ROCK
    for y in range(11, 16):
        for x in range(0, 4):
            terrain[y][x] = Terrain.WATER
    targets = [(29, 10), (32, 12), (35, 10)]
    for x, y in targets:
        terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 2, rng=rng)
    # Both sides retain a base, but this fixture has no autonomous opponent.
    world.players[1].human = True
    buildings = {
        BuildingType.FARM: (3, 7), BuildingType.TOWN_HALL: (7, 6), BuildingType.BARRACKS: (13, 6),
        BuildingType.TOWER: (19, 6), BuildingType.LUMBER_MILL: (23, 7), BuildingType.BLACKSMITH: (7, 17),
        BuildingType.STABLES: (13, 17), BuildingType.WORKSHOP: (20, 17), BuildingType.CHURCH: (27, 17),
    }
    for kind, pos in buildings.items():
        world.place_building(0, kind, pos)
    world.place_building(None, BuildingType.GOLD_MINE, (32, 17))
    world.place_building(1, BuildingType.TOWN_HALL, (43, 30))
    parade = [world.spawn_unit(0, kind, (5.5 + index * 3, 13.5)) for index, kind in enumerate(UnitType)]
    for unit in parade:
        unit.facing = math.pi / 2
    workers = [world.spawn_unit(0, UnitType.PEASANT, pos) for pos in ((28.65, 10.5), (32.5, 13.35), (36.35, 10.5))]
    world.update_vision()
    world.reveal_all(0)
    scene = GameScene(world, 17, settings={"tutorial": False, "music": 0.0, "sfx": 0.0, "edge_scroll": False})
    scene.selection = [unit.id for unit in parade]
    return scene, workers, targets


def capture_settlement(game: Game, output: Path) -> None:
    scene, workers, targets = settlement()
    game.clear_and_push(scene)
    # Let the match banner finish before issuing harvest orders.
    scene.paused = True
    for _ in range(20):
        tick(game, 0.2)
    scene.paused = False
    for worker, target in zip(workers, targets):
        scene.world.harvest([worker.id], target)
    scene.camera.zoom = 1.0
    scene.camera.center_on(20 * textures.TILE, 14 * textures.TILE)
    capture(game, output, "06_settlement_normal")
    scene.camera.zoom = 2.0
    scene.camera.center_on(14 * textures.TILE, 11.5 * textures.TILE)
    capture(game, output, "07_settlement_close")
    scene.selection = [worker.id for worker in workers]
    scene.camera.center_on(32 * textures.TILE, 11.5 * textures.TILE)
    capture(game, output, "08_lumber_camp")

    seen: set[str] = set()
    animation: list[Image.Image] = []
    for _ in range(30):
        tick(game, 1 / 30)
        for worker in workers:
            assert isinstance(worker.order, Harvest), worker.order
            assert worker.state == "chop", (worker.id, worker.state)
        sprite = scene.view.unit_sprite(workers[0].id)
        assert sprite is not None and sprite.visible
        pose = sprite.image.rsplit(".", 1)[-1]
        assert pose in textures.CHOP_FRAMES, sprite.image
        image = game.backend.capture_frame()
        if pose not in seen:
            image.save(output / f"09_{pose}.png")
            seen.add(pose)
        # Crop a real frame to the working forest, preserving its native pixels.
        left, top = scene.camera.world_to_screen(27.5 * textures.TILE, 7.5 * textures.TILE)
        right, bottom = scene.camera.world_to_screen(37.5 * textures.TILE, 15 * textures.TILE)
        scale = game.backend.scale_factor
        ox, oy = game.backend.offset_x, game.backend.offset_y
        box = (round(ox + left * scale), round(oy + top * scale), round(ox + right * scale), round(oy + bottom * scale))
        animation.append(image.crop(box).convert("RGB"))
    assert seen == set(textures.CHOP_FRAMES), seen
    animation[0].save(output / "09_workers_chopping.gif", save_all=True, append_images=animation[1:], duration=33, loop=0)
    print("  09_chop1..4.png and 09_workers_chopping.gif (all four real harvest poses verified)", flush=True)


def main(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-art-") as scratch:
        game = Game("Warband art verification", resolution=RESOLUTION, backend="pyglet", visible=False,
                    save_dir=Path(scratch), theme=build_theme())
        try:
            fonts.load(game)
            capture_sheets(game, output)
            capture_settlement(game, output)
        finally:
            game.close()
    print(f"Warband art verification passed. Open the PNGs and GIF in {output.resolve()}", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband_art"))
