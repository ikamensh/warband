"""Render the neutral creatures through the real backend and lay them out to look at.

    uv run python tools/verify_monsters.py docs/evidence/monsters

One contact sheet per creature: eight facings down, the nine frames across (stand, the
four-step walk, the four-phase blow), drawn by the game's own renderer on the game's own
grass.  Then the same creatures beside a footman, a knight and a catapult at the real game
zoom (``TILE`` = 32 px), which is the only picture that says whether a silhouette reads.
Finally the art lint over every frame.

A creature with a painted sheet under ``warband/assets/restyled`` (``tools/restyle.py
--monsters``) is drawn from it, so these are the painted pictures; ``compare-<creature>.png``
puts every facing's low-poly stand-in row directly above the painted one, which is how a
painting is judged against what it was painted from.  ``--procedural`` draws the stand-ins
instead and writes its files with a ``-standin`` suffix, so the two sets can be laid side by
side.

``--zoom`` sets the contact sheets' magnification (2 by default, 1 for gameplay size); the
parade is always drawn at 1.  The display must be awake (``caffeinate -u``).
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

from sagaforge import restyle  # noqa: E402

from saga2d import Game, Scene, fonts  # noqa: E402
from warband.art import monsters, textures, visual_lint  # noqa: E402
from warband.art.monsters import Monster  # noqa: E402
from warband.sim.rules import MapTheme, Race, Terrain, UnitType  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

RESOLUTION = (1280, 860)
CREAM = (240, 230, 209, 255)
MUTED = (159, 174, 167, 255)
ACCENT = (212, 177, 97, 255)
GRASS_KEY = "monster-verify.grass"


def grass(game: Game) -> None:
    """One painted grass chunk, the same texture the map draws, as the sheets' backdrop."""
    if not game.assets.has_image(GRASS_KEY):
        image = textures.ground_chunk(lambda tile: Terrain.GRASS, lambda tile: True, 0, 0,
                                      game.backend.scale_factor, MapTheme.SUMMER)
        game.assets.image_from_pil(GRASS_KEY, image)


class Paddock(Scene):
    """Sprites placed by their feet on painted grass, exactly as the map places a unit."""

    background_color = (24, 34, 30, 255)

    def __init__(self, title: str, subtitle: str, zoom: float) -> None:
        self.title, self.subtitle, self.zoom = title, subtitle, zoom
        self.sprites: list[tuple[str, float, float]] = []  # (key, feet x, feet y) in logical pixels
        self.labels: list[tuple[str, float, float, int]] = []

    def stand(self, key: str, x: float, y: float) -> None:
        self.sprites.append((key, x, y))

    def label(self, text: str, x: float, y: float, size: int = 12) -> None:
        self.labels.append((text, x, y, size))

    def draw(self) -> None:
        span = textures.CHUNK * textures.TILE
        for row in range(-1, RESOLUTION[1] // span + 2):
            for col in range(-1, RESOLUTION[0] // span + 2):
                self.draw_image(GRASS_KEY, col * span - textures.TILE, row * span - textures.TILE + 96,
                                textures.CHUNK_PX, textures.CHUNK_PX)
        self.draw_rect(0, 0, RESOLUTION[0], 92, (18, 26, 24, 235))
        self.draw_text("WARBAND  /  NEUTRAL CREATURES", 28, 26, font=fonts.EXTRABOLD, font_size=12, color=ACCENT)
        self.draw_text(self.title, 28, 50, font=fonts.EXTRABOLD, font_size=24, color=CREAM)
        self.draw_text(self.subtitle, 29, 74, font_size=13, color=MUTED)
        for key, x, y in self.sprites:
            placement = textures.placements[key]
            w, h = placement.size[0] * self.zoom, placement.size[1] * self.zoom
            self.draw_image(key, x - w / 2, y + placement.drop * self.zoom - h, w, h)
        for text, x, y, size in self.labels:
            self.draw_text(text, x, y, anchor_x="center", font_size=size, color=CREAM)


class Capture:
    def __init__(self, suffix: str = "") -> None:
        self.suffix = suffix
        self.temporary = tempfile.TemporaryDirectory(prefix="warband-monsters-")
        self.game = Game("Warband monsters", resolution=RESOLUTION, visible=False, theme=build_theme(),
                         save_dir=Path(self.temporary.name) / "saves")
        fonts.load(self.game)
        grass(self.game)

    def frame(self, scene: Scene) -> Image.Image:
        self.game.clear_and_push(scene)
        for _ in range(2):
            self.game.tick(1 / 60)
        return self.game.backend.capture_frame().convert("RGB").resize(RESOLUTION)

    def shoot(self, scene: Scene, output: Path, name: str) -> None:
        self.frame(scene).save(output / f"{name}.png")
        print(f"  {output / f'{name}.png'}", flush=True)

    def sheet(self, monster: Monster, output: Path, zoom: float) -> None:
        """Eight facings down and nine frames across, in two captures stacked into one sheet:
        one screen cannot hold eight rows of a creature without them treading on each other."""
        bands = []
        for half in range(2):
            facings = range(half * 4, half * 4 + 4)
            scene = Paddock(f"{monster.value.title()} — every frame of facings {facings.start}–{facings.stop - 1}",
                            f"columns: {', '.join(textures.FRAMES)}.  zoom {zoom:g}x on the game's own grass.  "
                            f"facing 0 is east, 2 faces the camera, 4 is west", zoom)
            left, top = 110, 260
            step_x = (RESOLUTION[0] - left - 30) / len(textures.FRAMES)
            step_y = (RESOLUTION[1] - top - 20) / 4
            for column, frame in enumerate(textures.FRAMES):
                scene.label(frame, left + column * step_x + step_x / 2, 126, 13)
            for row, facing in enumerate(facings):
                scene.label(f"facing {facing}", 54, top + row * step_y - 8, 12)
                for column, frame in enumerate(textures.FRAMES):
                    key = monsters.monster_image(self.game, monster, facing, frame)
                    scene.stand(key, left + column * step_x + step_x / 2, top + row * step_y)
            bands.append(self.frame(scene))
        sheet = Image.new("RGB", (RESOLUTION[0], 2 * RESOLUTION[1]), (24, 34, 30))
        for index, band in enumerate(bands):
            sheet.paste(band, (0, index * RESOLUTION[1]))
        sheet.save(output / f"{monster.value}-frames{self.suffix}.png")
        print(f"  {output / f'{monster.value}-frames{self.suffix}.png'}", flush=True)

    #: The units a neutral creature could be taken for.  The orc knight *is* an ogre, the orc
    #: scout rides a wolf and the dwarf knight rides a war bear, so these three stand in the
    #: parade beside the creatures: a player must tell a monster from a mounted enemy at a glance,
    #: and a neutral creature has no team colour to help.
    RIVALS = ((UnitType.KNIGHT, Race.ORC, "orc Ogre"), (UnitType.SCOUT, Race.ORC, "orc Wolf Rider"),
              (UnitType.KNIGHT, Race.DWARF, "dwarf Bear Rider"), (UnitType.FOOTMAN, Race.HUMAN, "footman"))

    def parade(self, output: Path) -> None:
        """The creatures beside the units they could be confused with, at the zoom the game is
        played at.  This is the picture that decides whether a silhouette reads."""
        scene = Paddock("At the real zoom — TILE = 32 px",
                        "neutral creatures beside the units they must not be taken for; top row faces the camera, "
                        "bottom row faces east.  No magnification.", 1.0)
        subjects: list[tuple[str, list[str]]] = [
            (monster.value, [monsters.monster_image(self.game, monster, facing, "stand") for facing in (2, 0)])
            for monster in Monster]
        subjects += [(name, [textures.unit_image(self.game, unit, 0, facing, "stand", race=race) for facing in (2, 0)])
                     for unit, race, name in self.RIVALS]
        step = (RESOLUTION[0] - 120) / len(subjects)
        for index, (name, keys) in enumerate(subjects):
            x = 60 + index * step + step / 2
            scene.label(name, x, 150, 13)
            scene.stand(keys[0], x, 230)
            scene.stand(keys[1], x, 330)
        for index, monster in enumerate(Monster):  # the walk and the blow, in a strip, unmagnified
            y = 470 + index * 92
            scene.label(monster.value, 60, y - 6, 12)
            for column, frame in enumerate(textures.FRAMES):
                scene.stand(monsters.monster_image(self.game, monster, 2, frame), 150 + column * 64, y)
                if index == 0:
                    scene.label(frame, 150 + column * 64, 420, 11)
        self.shoot(scene, output, f"parade-1x{self.suffix}")

    def close(self) -> None:
        self.game._teardown()
        self.game.backend.quit()
        self.temporary.cleanup()


def compare(monster: Monster, output: Path, suffix: str) -> None:
    """Every facing of every frame, the low-poly stand-in row above the painted row.

    This is the picture that says what the painter changed and what it moved: the pair of rows
    share a cell, an anchor and a scale, so a creature that grew a limb, left its ground or
    turned another way shows up as a mismatch between the two strips."""
    painted = monsters.restyled_monster(monster)
    if painted is None:
        print(f"  {monster.value}: no painted sheet, nothing to compare")
        return
    sheet, frames = painted
    from restyle import Monsters  # the tool that built the sheet renders the stand-ins the same way

    _, stand_ins = Monsters(monster).build_sheet()
    bands = []
    for facing in range(textures.FACINGS):
        keys = [monsters.monster_key(monster, facing, frame) for frame in textures.FRAMES]
        bands += [restyle.strip(stand_ins, keys, scale=0.5), restyle.strip(frames, keys, scale=0.5)]
    picture = Image.new("RGB", (max(b.width for b in bands), sum(b.height for b in bands)), (24, 34, 30))
    y = 0
    for band in bands:
        picture.paste(band, (0, y), band)
        y += band.height
    path = output / f"compare-{monster.value}{suffix}.png"
    picture.save(path)
    print(f"  {path}", flush=True)


def lint() -> list[visual_lint.Finding]:
    """Every creature frame through the art lint: empty, clipped, chroma, and the frames of one
    creature against each other (feet that hop, a figure that slides as it turns).  The lint keeps
    the PIL image behind each key, which only the mock backend hands it, so it runs on its own game."""
    with tempfile.TemporaryDirectory(prefix="warband-monster-lint-") as scratch:
        game = Game("Warband monster lint", backend="mock", resolution=RESOLUTION, theme=build_theme(),
                    save_dir=Path(scratch) / "saves")
        store = visual_lint.ImageStore(game)
        findings: list[visual_lint.Finding] = []
        for monster in Monster:
            keyed = {(facing, frame): (key, store.image(key))
                     for facing in range(textures.FACINGS) for frame in textures.FRAMES
                     for key in [monsters.monster_image(game, monster, facing, frame)]}
            for key, image in keyed.values():
                findings += visual_lint.lint_image(key, image)
            findings += visual_lint.lint_subject(monster.value, keyed, textures.placements[next(iter(keyed.values()))[0]])
        return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--zoom", type=float, default=2.0, help="magnification of the contact sheets (1 is gameplay)")
    parser.add_argument("--creatures", default=",".join(m.value for m in Monster), help="comma-separated creatures")
    parser.add_argument("--procedural", action="store_true",
                        help="draw the low-poly stand-ins instead of the painted sheets (files get a -standin suffix)")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.procedural:  # what _painted reads, so the creatures fall back to their renders
        textures.RESTYLED_ART = False
        monsters.restyled_monster.cache_clear()
        monsters.monster_heads.cache_clear()
    suffix = "-standin" if args.procedural else ""
    capture = Capture(suffix)
    try:
        for name in args.creatures.split(","):
            capture.sheet(Monster(name), args.output, args.zoom)
        capture.parade(args.output)
    finally:
        capture.close()
    if not args.procedural:
        for name in args.creatures.split(","):
            compare(Monster(name), args.output, suffix)
    findings = lint()
    print(f"lint: {len(findings)} findings")
    for finding in findings:
        print(f"  {finding}")


if __name__ == "__main__":
    main()
