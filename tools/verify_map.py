"""Inspect the native map rim, fog, seeded terrain regions and the shared ground's prize.

    uv run python tools/verify_map.py /tmp/warband-map

Captures an ordinary fogged game at opposite corners, then fully revealed
survey views using the same MapView assets, and last a big map's prize with
a crew inside it, three times on the same ground: the poor gold seam, the
rich Mother Lode and the lode worked out below its line. Five tiles of
workings against the three of a mine, close enough to see whether the
picture stands on its ground. Surveys freeze
simulation and reveal terrain for inspection only; they do not change
gameplay visibility.
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
from warband.sim import mapgen  # noqa: E402
from warband.sim.model import dist, tile_center  # noqa: E402
from warband.sim.rules import BUILDINGS, LODE_GOLD, BuildingType, MapTheme, SIM_DT, UnitType  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from warband.art.textures import TILE  # noqa: E402
from warband.ui.view import MapView, Overlay  # noqa: E402


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


class Prize(Scene):
    """The shared ground's prize with peasants at its face, beside the mine and hall it is not: a gold seam, or a
    Mother Lode holding *gold* (rich above its line, worked out below).

    A prize only ever stands on a map bigger than the shipped three (:func:`mapgen._wants_a_prize`), and on that map
    it lies in the shared ground far from home, so this builds one on the same ground either way, hires a crew beside
    it rather than walking one out for a minute, and runs the world until they are inside; the crew is what makes the
    workings wear their ``active`` look."""

    background_color = (10, 12, 20, 255)

    def __init__(self, prize: BuildingType, gold: int | None = None) -> None:
        super().__init__()
        self.prize, self.gold = prize, gold

    def on_enter(self) -> None:
        width, height = mapgen.dimensions("Huge", 2)
        self.world = mapgen.generate(11, width=width, height=height, players=2, human=0, prize=self.prize)
        hall = next(b for b in self.world.player_buildings(0, BuildingType.TOWN_HALL))
        self.seam = min((b for b in self.world.mines() if b.type is self.prize), key=lambda b: dist(b.center, hall.center))
        if self.gold is not None:
            self.seam.gold = self.gold
        x, y, size, _ = self.seam.rect
        ring = [(x + dx, y - 1) for dx in range(size)] + [(x + dx, y + size) for dx in range(size)]
        for tile in [t for t in ring if self.world.passable(*t)][:9]:  # a crew for a face that seats twelve
            self.world.spawn_unit(0, UnitType.PEASANT, tile_center(tile))
        self.world.reveal_all(0)
        self.world.update_vision()
        self.world.harvest([u.id for u in self.world.player_units(0)
                            if dist(u.pos, self.seam.center) < 12], self.seam.id)
        self.camera = Camera(self.game.resolution, zoom=1.0)
        self.camera.center_on(self.seam.center[0] * TILE, self.seam.center[1] * TILE)
        self.view = MapView(self, self.world, 0)

    def update(self, dt: float) -> None:
        for _ in range(round(dt / SIM_DT)):
            self.world.step()
        self.world.take_events()
        self.view.sync(dt)

    def draw(self) -> None:
        self.view.draw(Overlay())
        inside = sum(1 for u in self.world.units.values() if u.inside == self.seam.id)
        name = BUILDINGS[self.prize].name.upper()
        self.draw_text(f"WARBAND  /  {name}  /  HUGE PLAINS  /  SEED 11", 24, 30,
                       font=fonts.EXTRABOLD, font_size=18, color=(232, 214, 172, 255))
        held = "never spent" if self.seam.info.mine.endless else f"{self.seam.gold:,} gold left"
        self.draw_text(f"Five tiles of workings, {self.seam.info.mine.trip} gold a trip, {held} • {inside} peasants at the face", 24, 775,
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
            for name, prize, gold in (("gold-seam", BuildingType.GOLD_SEAM, None), ("mother-lode", BuildingType.MOTHER_LODE, None),
                                      ("worked-lode", BuildingType.MOTHER_LODE, LODE_GOLD // 3)):
                seam = Prize(prize, gold)
                game.clear_and_push(seam)
                for _ in range(600):  # until the face is busy: a peasant is only inside for a few seconds at a time
                    tick(game, 0.2)
                    if sum(1 for u in seam.world.units.values() if u.inside == seam.seam.id) >= 5:
                        break
                tick(game)
                game.backend.capture_frame().save(output / f"{name}.png")
                assert any(u.inside == seam.seam.id for u in seam.world.units.values()), f"nobody reached the {name}'s face"
        finally:
            game.close()
    print(f"Native map verification passed: {output.resolve()}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband-map"))
