"""Mission-specific field charts: the actual ground, with an authored beat for each briefing line.

Only named briefing landmarks are disclosed. No live units, plans, resources or fog
are read after construction. Advancing the dialogue inks more of the chart; the
animation is presentation time and never advances the mission.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from hashlib import sha256

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
from saga2d import Scene, fonts
from warband.sim.model import Point
from warband.sim.rules import Terrain
from warband.story.campaign import ChartBeat, Line, Run

INK = (86, 65, 42, 255)
LIT = (255, 220, 142, 255)


@dataclass
class BriefingChart:
    """A snapshot of this level's geography and its narrated annotations."""

    mission_id: str
    size: tuple[int, int]
    terrain: tuple[tuple[Terrain, ...], ...]
    seed: int
    places: dict[str, tuple[str, Point]]
    beats: tuple[ChartBeat | None, ...]
    image_key: str

    def draw(self, scene: Scene, index: int, age: float, clock: float, bounds: tuple[float, float, float, float], *,
             revealed: set[int]) -> None:
        x, y, w, h = bounds
        key = self.image_key
        if not scene.game.assets.has_image(key):
            scene.game.assets.image_from_pil(key, _ground(self.terrain, self.seed))
        with scene.screen_layer(4):
            scene.draw_rect(x - 9, y - 9, w + 18, h + 18, (12, 21, 25, 246), border_color=(167, 139, 81, 255), border_width=1, radius=4)
        with scene.screen_layer(5):
            scene.draw_image(key, x, y, w, h)
        with scene.screen_layer(6):
            beat = self.beats[index]
            visible = dict.fromkeys(place for n in sorted(revealed) if (earlier := self.beats[n]) is not None
                                    for place in (*earlier.places, *earlier.route))
            active = set(beat.places) if beat else set()

            def project(place: str) -> Point:
                point = self.places[place][1]
                return x + point[0] / self.size[0] * w, y + point[1] / self.size[1] * h

            # A route is inked over 1.2 seconds, then a travelling bead keeps its direction readable.
            route = beat.route if beat else ()
            for start, end in zip(route, route[1:]):
                ax, ay = project(start)
                bx, by = project(end)
                count = max(1, round(math.hypot(bx - ax, by - ay) / 10))
                progress = min(1.0, age / 1.2)
                for n in range(round(count * progress)):
                    f, g = n / count, min((n + .55) / count, progress)
                    scene.draw_line(ax + (bx - ax) * f, ay + (by - ay) * f, ax + (bx - ax) * g, ay + (by - ay) * g, INK, 2)
                f = (clock * .22) % max(.001, progress)
                scene.draw_circle(ax + (bx - ax) * f, ay + (by - ay) * f, 3, (248, 234, 184, 255))
            labels: list[tuple[float, float, float, float]] = [(x + w - 30, y, 30, 48)]
            for place in visible:
                px, py = project(place)
                lit = place in active
                if lit:
                    radius = 10 + 5 * ((clock * .6) % 1)
                    for n in range(32):
                        a, b = n * math.tau / 32, (n + 1) * math.tau / 32
                        scene.draw_line(px + math.cos(a) * radius, py + math.sin(a) * radius,
                                        px + math.cos(b) * radius, py + math.sin(b) * radius,
                                        (100, 60, 23, round(150 * (1 - (radius - 10) / 5))), 1)
                scene.draw_polygon([(px, py - 6), (px + 5, py), (px, py + 6), (px - 5, py)], INK)
                scene.draw_circle(px, py, 2, LIT if lit else (190, 161, 104, 255))
                if lit:
                    label = self.places[place][0]
                    tw, th = scene.game.backend.measure_text(label, 11, fonts.SEMIBOLD)
                    lx, ly = _label_position(px, py, tw, th, bounds, labels)
                    labels.append((lx - 3, ly - 2, tw + 6, th + 4))
                    scene.draw_rect(lx - 3, ly - 2, tw + 6, th + 4, (218, 200, 157, 240), radius=2)
                    scene.draw_text(label, lx, ly, font_size=11, font=fonts.SEMIBOLD, color=INK, anchor_y="top")
            # A modest compass needle stays out of the authored annotations.
            scene.draw_text("N", x + w - 14, y + 18, font_size=12, color=INK, font=fonts.SEMIBOLD, anchor_x="center")
            scene.draw_line(x + w - 14, y + 25, x + w - 14, y + 42, INK)


def _label_position(px: float, py: float, tw: float, th: float, bounds: tuple[float, float, float, float],
                    occupied: list[tuple[float, float, float, float]]) -> Point:
    """Place a whole label inside the paper, outside the compass and every earlier label."""
    x, y, w, h = bounds
    if tw + 16 > w or th + 16 > h:
        raise ValueError("a briefing chart label is larger than its paper")
    for top in (py - 21, py + 12, py - 47, py + 38, y + 8, y + h - th - 8):
        for left in (px + 10, px - tw - 10, x + 8, x + w - tw - 8):
            lx = max(x + 8, min(x + w - tw - 8, left))
            ly = max(y + 8, min(y + h - th - 8, top))
            if all(lx + tw + 6 <= ox or lx - 6 >= ox + ow or ly + th + 6 <= oy or ly - 6 >= oy + oh
                   for ox, oy, ow, oh in occupied):
                return lx, ly
    raise ValueError("briefing chart labels cannot fit without overlapping")


def _ground(terrain: tuple[tuple[Terrain, ...], ...], seed: int) -> Image.Image:
    """A parchment survey drawn from terrain masks; glyphs soften the grid without inventing ground."""
    width, height = len(terrain[0]), len(terrain)
    cell = 14
    size = (width * cell, height * cell)
    rng = random.Random(seed)
    grain = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    picture = ImageOps.colorize(grain, (192, 170, 122), (215, 195, 150))
    wash = Image.frombytes("L", (32, 32), rng.randbytes(1024)).resize(size, Image.Resampling.BICUBIC)
    picture = Image.blend(picture, ImageOps.colorize(wash, (175, 147, 98), (229, 208, 163)), .30)
    colors = {Terrain.WATER: (93, 137, 141), Terrain.TREES: (127, 145, 100), Terrain.ROCK: (167, 157, 135)}
    for kind, color in colors.items():
        mask = Image.new("L", (width, height))
        mask.putdata([255 if tile is kind else 0 for row in terrain for tile in row])
        mask = mask.resize(size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(3))
        edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(9)), mask)
        picture.paste((113, 103, 76), mask=edge)
        fill = Image.blend(Image.new("RGB", size, color), picture, .12)
        picture.paste(fill, mask=mask)
    draw = ImageDraw.Draw(picture)
    for ty, row in enumerate(terrain):
        for tx, kind in enumerate(row):
            x, y = tx * cell, ty * cell
            if kind is Terrain.TREES and (tx + ty) % 3 == 0:
                x, y = x + rng.randrange(5), y + rng.randrange(4)
                draw.line((x + 6, y + 1, x + 1, y + 10, x + 11, y + 10, x + 6, y + 1), fill=(71, 95, 66), width=1)
                draw.line((x + 6, y + 6, x + 6, y + 13), fill=(87, 91, 58))
                draw.line((x + 4, y + 7, x + 8, y + 7), fill=(93, 115, 73))
            elif kind is Terrain.ROCK and (tx + ty) % 4 == 0:
                draw.line((x - 2, y + 12, x + 6, y + 1, x + 15, y + 12), fill=(106, 101, 86), width=1)
                draw.line((x + 6, y + 2, x + 4, y + 8, x + 8, y + 6, x + 11, y + 11), fill=(133, 124, 103))
            elif kind is Terrain.WATER and rng.random() < .20:
                draw.arc((x, y + 3, x + 10, y + 7), 0, 150, fill=(143, 175, 168))
    # Fold creases and a double ink border belong to the paper, rather than a square cell overlay.
    for fraction in range(1, 4):
        x, y = size[0] * fraction // 4, size[1] * fraction // 4
        draw.line((x, 9, x, size[1] - 9), fill=(173, 158, 120))
        draw.line((9, y, size[0] - 9, y), fill=(173, 158, 120))
    for inset in (5, 9):
        draw.rectangle((inset, inset, size[0] - inset - 1, size[1] - inset - 1), outline=(135, 112, 72), width=1)
    return picture


def briefing_chart(run: Run) -> BriefingChart:
    """Make the field chart from this run, failing visibly when authored narration names missing ground."""
    world = run.world
    units = world.player_units(run.human)
    hall = run.hall(run.human)
    origin = hall.center if hall else units[0].pos
    places = {"home": ("Your company", origin)}
    enemy_hall = run.hall(1)
    enemies = world.player_units(1)
    if enemy_hall or enemies:
        places["enemy"] = ("Opposing stronghold", enemy_hall.center if enemy_hall else enemies[0].pos)
    mines = [b for b in world.buildings.values() if b.has_gold]
    if mines:
        mine = min(mines, key=lambda b: math.dist(b.center, origin))
        places["mine"] = ("Gold mine", mine.center)
    for key in ("camp", "orc_home", "goal", "siege", "north_ford", "south_ford"):
        if key in run.vars:
            labels = {"camp": "Raider camp", "orc_home": "Orc camp", "goal": "The pass to Karst", "siege": "Karst siege engines",
                      "north_ford": "North ford", "south_ford": "South ford"}
            places[key] = (labels[key], tuple(run.vars[key]))
    for key, landmark in run.vars.get("landmarks", {}).items():
        places[key] = (landmark["name"].split(" (")[0], tuple(landmark["point"]))
    if run.mission.id == "undertow_maw":
        places["enemy"] = ("Sella's refuge", world.buildings[run.vars["sella_tower"]].center)
    beats = tuple(item.chart if isinstance(item, Line) else None for item in run.mission.briefing)
    for beat in beats:
        if beat is None:
            continue
        for key in (*beat.places, *beat.route):
            if key not in places:
                raise KeyError(f"{run.mission.id}: briefing chart has no landmark {key!r}")
    terrain = tuple(tuple(row) for row in world.terrain)
    codes = {kind: index for index, kind in enumerate(Terrain)}
    fingerprint = sha256(f"{world.width}x{world.height}:{run.mission.seed}".encode()
                         + bytes(codes[tile] for row in terrain for tile in row)).hexdigest()[:12]
    return BriefingChart(run.mission.id, (world.width, world.height), terrain, run.mission.seed, places, beats,
                         f"story.chart.{run.mission.id}.{fingerprint}")
