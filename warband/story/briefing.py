"""Mission-specific field charts: the actual ground, with an authored beat for each briefing line.

Only named briefing landmarks are disclosed. No live units, plans, resources or fog
are read after construction. Advancing the dialogue inks more of the chart; the
animation is presentation time and never advances the mission.
"""

from __future__ import annotations

import math
import random
from hashlib import sha256
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
from saga2d import Scene, fonts
from warband.sim.model import Point
from warband.sim.rules import Terrain
from warband.story.campaign import Run

INK = (86, 65, 42, 255)
LIT = (255, 220, 142, 255)


@dataclass(frozen=True)
class Beat:
    caption: str
    places: tuple[str, ...]
    route: tuple[str, ...] = ()


# Physical line indices are deliberate: conditional lines keep their own cartographic beat.
PLANS: dict[str, tuple[Beat, ...]] = {
    "undertow_mill": (
        Beat("The fieldhands are still outside", ("home", "mill_fields")),
        Beat("Hold the south field; protect the vault", ("mill_fields", "mill_vault"), ("home", "mill_fields")),
        Beat("Take command of the company", ("home", "mill_fields", "mill_vault")),
    ),
    "undertow_caravan": (
        Beat("Uphill, to the Broken Tooth", ("old_camp", "mesa"), ("old_camp", "middle_ford", "mesa")),
        Beat("Salvage the Old Camp; rebuild on the mesa", ("old_camp", "mesa"), ("old_camp", "middle_ford", "mesa")),
        Beat("Bring at least five drovers home", ("old_camp", "mesa")),
        Beat("The guarded north ford and its dam", ("north_ford", "dam_pylon")),
        Beat("Choose a crossing; count the cost to Millfield", ("middle_ford", "south_ford", "dam_pylon"), ("old_camp", "middle_ford", "mesa")),
        Beat("The new Great Hall keeps the caravan alive", ("mesa",)),
    ),
    "undertow_grove": (
        Beat("The living filter is at its limit", ("moon_hall", "firebreak")),
        Beat("The grove grows back overnight", ("moon_hall", "firebreak")),
        Beat("Hear the woodcutters before drawing steel", ("cutter_camp",), ("moon_hall", "cutter_camp")),
        Beat("Courtesy before steel at the stone ring", ("guardian_ring",), ("moon_hall", "guardian_ring")),
    ),
    "undertow_weight": (
        Beat("A siege train below the three Weights", ("enemy", "weight_1", "weight_2", "weight_3")),
        Beat("Keep at least two Weights standing", ("weight_1", "weight_2", "weight_3")),
        Beat("Break the siege; cover the repair crews", ("home", "enemy"), ("home", "weight_1", "enemy")),
        Beat("The endless seam has its own account", ("seam",)),
        Beat("Clear the siege, then settle the seam", ("enemy", "seam", "seam_rift")),
    ),
    "undertow_maw": (
        Beat("The Keepers arrive at the broken ring", ("keepers_camp", "keystone", "enemy"), ("keepers_camp", "keystone")),
        Beat("Sella's refuge holds the wounded crews", ("enemy",)),
        Beat("The survey's missing nine minutes", ("enemy",)),
        Beat("The people behind the promise", ("enemy",)),
        Beat("Ask the crews waiting in the refuge", ("refuge_tower",)),
        Beat("Three vaults to drink the Maw's aether", ("maw_rift_1", "maw_rift_2", "maw_rift_3")),
        Beat("GROUND needs the Guardian or its heart", ("maw_rift_1", "maw_rift_2", "maw_rift_3")),
        Beat("First work commits the ending", ("keystone", "seal_pylon_1", "maw_rift_1")),
        Beat("Set the Relief Sluice before OPEN", ("relief_sluice", "keystone"), ("keepers_camp", "relief_sluice")),
    ),
    "hollowmere": (
        Beat("The Greywater raids reach Hollowmere", ("home", "camp")),
        Beat("Raiders in the eastern hills", ("camp", "home"), ("camp", "home")),
        Beat("Shelter and bread before spears", ("home",)),
        Beat("A farm, a barracks, four soldiers", ("home",)),
        Beat("The mine and southern timber", ("mine", "home")),
    ),
    "greywater": (
        Beat("The border at Greywater Ford", ("home", "orc_home"), ("home", "orc_home")),
        Beat("Hold until the Marcher levies arrive", ("home",)),
        Beat("A chance to speak across the river", ("orc_home",)),
        Beat("The far bank is held by the warbands", ("orc_home",)),
    ),
    "silent_hold": (
        Beat("North through the Frostcomb pass", ("home", "goal"), ("home", "goal")),
        Beat("A company on foot", ("home",)),
        Beat("Reach the hold beyond the wardens", ("goal",), ("home", "goal")),
        Beat("Sister Maren must survive", ("home", "goal")),
    ),
    "karst_hold": (
        Beat("Karst's walls and siege engines", ("home", "siege")),
        Beat("Wardens at the valley mouth", ("enemy",)),
        Beat("Destroy the enemy Moon Hall", ("enemy",), ("home", "enemy")),
    ),
    "retaken": (
        Beat("The Thornwood has crossed the Greywater", ("home", "enemy")),
        Beat("Retake the ford", ("enemy",), ("home", "enemy")),
        Beat("Ironjaw's promise on the northern flank", ("enemy",)),
        Beat("No help will come from the north", ("home",)),
        Beat("Raise the levy and reclaim the bank", ("home", "enemy"), ("home", "enemy")),
    ),
    "court_of_thorns": (
        Beat("The old Moon Hall and its eyries", ("enemy",)),
        Beat("A message brought through half the wood", ("home", "enemy"), ("home", "enemy")),
        Beat("The Marches demand their border", ("home", "enemy")),
        Beat("The Court will not retreat", ("enemy",)),
        Beat("The engineers stand ready", ("home",)),
        Beat("Karst's siege train", ("home",)),
        Beat("Ironjaw's survivors enter the wood", ("enemy",)),
        Beat("The northern flank is held", ("enemy",)),
        Beat("Bring down the Court", ("enemy",), ("home", "enemy")),
    ),
}


@dataclass
class BriefingChart:
    """A snapshot of this level's geography and its narrated annotations."""

    mission_id: str
    size: tuple[int, int]
    ground: Image.Image
    places: dict[str, tuple[str, Point]]
    beats: tuple[Beat, ...]
    image_key: str = field(init=False)

    def __post_init__(self) -> None:
        self.image_key = f"story.chart.{self.mission_id}.{sha256(self.ground.tobytes()).hexdigest()[:12]}"

    def draw(self, scene: Scene, index: int, age: float, clock: float, bounds: tuple[float, float, float, float], *,
             revealed: set[int]) -> None:
        x, y, w, h = bounds
        key = self.image_key
        if not scene.game.assets.has_image(key):
            scene.game.assets.image_from_pil(key, self.ground)
        with scene.screen_layer(4):
            scene.draw_rect(x - 9, y - 9, w + 18, h + 18, (12, 21, 25, 246), border_color=(167, 139, 81, 255), border_width=1, radius=4)
        with scene.screen_layer(5):
            scene.draw_image(key, x, y, w, h)
        with scene.screen_layer(6):
            beat = self.beats[index]
            visible = dict.fromkeys(place for n in sorted(revealed) for place in self.beats[n].places)
            active = set(beat.places)

            def project(place: str) -> Point:
                point = self.places[place][1]
                return x + point[0] / self.size[0] * w, y + point[1] / self.size[1] * h

            # A route is inked over 1.2 seconds, then a travelling bead keeps its direction readable.
            for start, end in zip(beat.route, beat.route[1:]):
                ax, ay = project(start)
                bx, by = project(end)
                count = max(1, round(math.hypot(bx - ax, by - ay) / 10))
                progress = min(1.0, age / 1.2)
                for n in range(round(count * progress)):
                    f, g = n / count, min((n + .55) / count, progress)
                    scene.draw_line(ax + (bx - ax) * f, ay + (by - ay) * f, ax + (bx - ax) * g, ay + (by - ay) * g, INK, 2)
                f = (clock * .22) % max(.001, progress)
                scene.draw_circle(ax + (bx - ax) * f, ay + (by - ay) * f, 3, (248, 234, 184, 255))
            labels: list[tuple[float, float, float, float]] = []
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
                    lx = max(x + 6, min(x + w - tw - 8, px + 10))
                    ly = max(y + 8, min(y + h - th - 8, py - 21))
                    for previous in labels:
                        if lx < previous[0] + previous[2] and lx + tw + 8 > previous[0] and ly < previous[1] + previous[3] and ly + th + 6 > previous[1]:
                            ly = previous[1] + previous[3] + 3
                    labels.append((lx, ly, tw + 8, th + 6))
                    scene.draw_rect(lx - 3, ly - 2, tw + 6, th + 4, (218, 200, 157, 240), radius=2)
                    scene.draw_text(label, lx, ly, font_size=11, font=fonts.SEMIBOLD, color=INK, anchor_y="top")
            # A modest compass needle stays out of the authored annotations.
            scene.draw_text("N", x + w - 14, y + 18, font_size=12, color=INK, font=fonts.SEMIBOLD, anchor_x="center")
            scene.draw_line(x + w - 14, y + 25, x + w - 14, y + 42, INK)


def _ground(run: Run) -> Image.Image:
    """A parchment survey drawn from terrain masks; glyphs soften the grid without inventing ground."""
    world = run.world
    cell = 14
    size = (world.width * cell, world.height * cell)
    rng = random.Random(run.mission.seed)
    grain = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    picture = ImageOps.colorize(grain, (192, 170, 122), (215, 195, 150))
    wash = Image.frombytes("L", (32, 32), rng.randbytes(1024)).resize(size, Image.Resampling.BICUBIC)
    picture = Image.blend(picture, ImageOps.colorize(wash, (175, 147, 98), (229, 208, 163)), .30)
    colors = {Terrain.WATER: (93, 137, 141), Terrain.TREES: (127, 145, 100), Terrain.ROCK: (167, 157, 135)}
    for terrain, color in colors.items():
        mask = Image.new("L", (world.width, world.height))
        mask.putdata([255 if tile is terrain else 0 for row in world.terrain for tile in row])
        mask = mask.resize(size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(3))
        edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(9)), mask)
        picture.paste((113, 103, 76), mask=edge)
        fill = Image.blend(Image.new("RGB", size, color), picture, .12)
        picture.paste(fill, mask=mask)
    draw = ImageDraw.Draw(picture)
    for ty, row in enumerate(world.terrain):
        for tx, terrain in enumerate(row):
            x, y = tx * cell, ty * cell
            if terrain is Terrain.TREES and (tx + ty) % 3 == 0:
                x, y = x + rng.randrange(5), y + rng.randrange(4)
                draw.line((x + 6, y + 1, x + 1, y + 10, x + 11, y + 10, x + 6, y + 1), fill=(71, 95, 66), width=1)
                draw.line((x + 6, y + 6, x + 6, y + 13), fill=(87, 91, 58))
                draw.line((x + 4, y + 7, x + 8, y + 7), fill=(93, 115, 73))
            elif terrain is Terrain.ROCK and (tx + ty) % 4 == 0:
                draw.line((x - 2, y + 12, x + 6, y + 1, x + 15, y + 12), fill=(106, 101, 86), width=1)
                draw.line((x + 6, y + 2, x + 4, y + 8, x + 8, y + 6, x + 11, y + 11), fill=(133, 124, 103))
            elif terrain is Terrain.WATER and rng.random() < .20:
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
    beats = PLANS[run.mission.id]
    if len(beats) != len(run.mission.briefing):
        raise ValueError(f"{run.mission.id}: each briefing line needs its own chart beat")
    for beat in beats:
        for key in (*beat.places, *beat.route):
            if key not in places:
                raise KeyError(f"{run.mission.id}: briefing chart has no landmark {key!r}")
    return BriefingChart(run.mission.id, (world.width, world.height), _ground(run), places, beats)
