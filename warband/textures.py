"""Warband's art, all procedural.

The ground is painted with Pillow in chunks of ``CHUNK``×``CHUNK`` tiles
(continuous grass, water with ripples, sand along the shore).
Everything that stands on it — trees, rocks, gold mines, buildings, units —
is a low-poly mesh rendered with :mod:`saga2d.render3d` through a 3/4 camera
whose tile footprints stay square (:meth:`Projection.front`), so a 3×3
building covers exactly 3×3 tiles on screen and still shows lit walls.

Trees grow twenty seeded branching skeletons per theme; crystal colonies and
gold outcrops each have twenty forms. Tile coordinates choose stable variants.
Units face eight ways and have four frames (stand, two walking, attack);
peasants add carrying variants and four articulated chopping poses. Images are rendered on demand
(:func:`unit_image`) because a match uses only a fraction of the
combinations.  Sprites are anchored at the bottom centre; :data:`placements`
records each image's logical size and *drop* — how far its bottom edge lies
below the point it is placed at — like Tribes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from saga2d import Game
from saga2d import render3d as r3
from saga2d.render3d import Mesh
from warband.rules import BUILDINGS, PLAYERS, BuildingType, MapTheme, Race, Resource, Terrain, UnitType

TILE = 32
ELEVATION = 50.0
PROJECTION = r3.Projection.front(TILE, ELEVATION)
VIEW = PROJECTION.view
CHUNK = 8  # ground tiles per chunk image (plus one tile of margin all round to hide the seams)
WATER_PHASES = 3  # a chunk with water is painted this many times, ripples and shoreline lapping shifted per phase
CHUNK_PX = (CHUNK + 2) * TILE
PAD = 2
FACINGS = 8
FRAMES = ("stand", "walk1", "walk2", "attack")
CHOP_FRAMES = ("chop1", "chop2", "chop3", "chop4")
TREE_VARIANTS = 20
ROCK_VARIANTS = 20
MINE_VARIANTS = 20

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    """The colours of one map theme."""

    grass: Color
    water: Color
    ripple: Color
    sand: Color
    rock_ground: Color
    trunk: Color
    leaf: tuple[Color, ...]
    leaf_light: tuple[Color, ...]
    rock: Color
    snow: bool = False  # snow caps on the trees
    bare: bool = False  # dead trees: trunk and branches, no canopy
    minimap: dict[Terrain, Color] = None  # type: ignore[assignment]


PALETTES: dict[MapTheme, Palette] = {
    MapTheme.SUMMER: Palette(
        grass=(108, 162, 78), water=(52, 110, 170), ripple=(120, 170, 220),
        sand=(198, 182, 134), rock_ground=(118, 140, 90), trunk=(98, 70, 46),
        leaf=((44, 110, 58), (56, 126, 66), (38, 98, 52)), leaf_light=((70, 140, 76), (84, 156, 84), (62, 128, 70)), rock=(132, 130, 126),
        minimap={Terrain.GRASS: (96, 142, 70), Terrain.WATER: (46, 96, 156), Terrain.TREES: (44, 86, 46), Terrain.ROCK: (108, 118, 92)},
    ),
    MapTheme.WINTER: Palette(
        grass=(222, 228, 236), water=(150, 188, 222), ripple=(226, 240, 250),
        sand=(206, 218, 230), rock_ground=(184, 188, 196), trunk=(78, 58, 44),
        leaf=((34, 76, 58), (40, 84, 64), (30, 68, 52)), leaf_light=((52, 98, 74), (60, 108, 80), (46, 90, 68)), rock=(140, 146, 156), snow=True,
        minimap={Terrain.GRASS: (200, 208, 218), Terrain.WATER: (140, 176, 210), Terrain.TREES: (52, 90, 70), Terrain.ROCK: (130, 136, 146)},
    ),
    MapTheme.WASTELAND: Palette(
        grass=(178, 150, 96), water=(88, 112, 98), ripple=(124, 150, 132),
        sand=(154, 124, 74), rock_ground=(150, 118, 84), trunk=(96, 76, 56),
        leaf=((92, 78, 52), (84, 70, 48), (98, 84, 58)), leaf_light=((110, 94, 64), (104, 88, 60), (116, 100, 70)), rock=(150, 118, 100), bare=True,
        minimap={Terrain.GRASS: (160, 134, 84), Terrain.WATER: (78, 100, 88), Terrain.TREES: (98, 78, 52), Terrain.ROCK: (134, 106, 90)},
    ),
}
STONE = (172, 164, 154)
STONE_DARK = (128, 122, 114)
WOOD = (152, 110, 66)
WOOD_DARK = (110, 80, 50)
PLASTER = (234, 224, 202)
THATCH = (200, 168, 96)
SLATE = (74, 76, 90)
SKIN = (232, 196, 160)
IRON = (178, 182, 192)
INK = (40, 36, 44)
GOLD = (240, 198, 64)
EARTH = (146, 116, 84)
SHADOW = (0, 0, 0, 90)
WHITE = (255, 255, 255)
SNOW = (240, 244, 250)
BOULDER = (132, 130, 126)  # the stone a catapult throws
TRUNK = PALETTES[MapTheme.SUMMER].trunk


@dataclass(frozen=True)
class Placement:
    size: tuple[float, float]
    drop: float


placements: dict[str, Placement] = {}


def darker(color: Color, factor: float = 0.7) -> Color:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def team_color(player: int) -> Color:
    return PLAYERS[player].color


def scatter(x: int, y: int, salt: int = 0) -> int:
    """A small deterministic integer for a tile: picks shades and dapple spots."""
    h = (x * 0x27D4EB2D ^ (y + 0x165667B1 + salt * 0x9E3779B1) * 0x85EBCA77) & 0xFFFFFFFF
    return (h ^ (h >> 15)) & 0xFFFF


# -- Ground ------------------------------------------------------------------------


def grass_tint(x: int, y: int, cell: int = 5) -> float:
    """Smooth brightness across the meadow: value noise on a lattice every *cell* tiles."""
    gx, fx = divmod(x, cell)
    gy, fy = divmod(y, cell)
    tx, ty = fx / cell, fy / cell

    def lattice(i: int, j: int) -> float:
        return (scatter(i, j, 9) & 0xFF) / 255

    a, b, c, d = lattice(gx, gy), lattice(gx + 1, gy), lattice(gx, gy + 1), lattice(gx + 1, gy + 1)
    v = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
    return 0.9 + 0.2 * v


def ground_chunk(terrain_at, in_bounds, cx: int, cy: int, scale: float, theme: MapTheme = MapTheme.SUMMER, phase: int = 0) -> Image.Image:
    """Paint the chunk at chunk coordinates ``(cx, cy)`` with a tile of margin
    around it; *terrain_at(pos)* and *in_bounds(pos)* read the map.  *phase*
    (0 to ``WATER_PHASES - 1``) shifts the ripples and the shoreline so a
    view can cycle the images and the water moves."""
    pal = PALETTES[theme]
    GRASS, WATER, WATER_RIPPLE, SAND, ROCK_GROUND = pal.grass, pal.water, pal.ripple, pal.sand, pal.rock_ground
    px = TILE * scale
    # Paint an extra tile of context, then trim it. Shores and grass details
    # from neighbours must agree throughout the visible overlap of two chunks.
    n = CHUNK + 4
    image = Image.new("RGBA", (round(n * px), round(n * px)), (*GRASS, 255))
    draw = ImageDraw.Draw(image)
    x0, y0 = cx * CHUNK - 2, cy * CHUNK - 2

    def kind(tx: int, ty: int) -> Terrain:
        return terrain_at((tx, ty)) if in_bounds((tx, ty)) else Terrain.TREES

    for j in range(n):
        for i in range(n):
            tx, ty = x0 + i, y0 + j
            terrain = kind(tx, ty)
            left, top = i * px, j * px
            if terrain is Terrain.WATER:
                draw.rectangle((left, top, left + px, top + px), fill=WATER)
            elif terrain is Terrain.ROCK:
                draw.rectangle((left, top, left + px, top + px), fill=ROCK_GROUND)
            else:
                tint = grass_tint(tx, ty)
                base = tuple(min(255, int(c * tint)) for c in GRASS)
                draw.rectangle((left, top, left + px, top + px), fill=base)
                for k in range(4):
                    s = scatter(tx, ty, k + 1)
                    dx, dy, r = (s & 0xFF) / 255 * px, ((s >> 8) & 0xFF) / 255 * px, px * (0.05 + 0.04 * (k % 3))
                    shade = darker(base, 0.9) if k == 0 else tuple(min(255, int(c * 1.07)) for c in base) if k == 1 else darker(base, 0.95)
                    draw.ellipse((left + dx - r, top + dy - r, left + dx + r, top + dy + r), fill=shade)
    # Shores: sand on the land side of every grass/water edge, a pale rim on the water side
    # that laps a little further up the beach with each phase.
    band = px * 0.22
    rim = band * (0.4 + 0.14 * phase)
    for j in range(n):
        for i in range(n):
            tx, ty = x0 + i, y0 + j
            if kind(tx, ty) is not Terrain.WATER:
                continue
            left, top = i * px, j * px
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if kind(tx + dx, ty + dy) is Terrain.WATER:
                    continue
                if dx == 1:
                    draw.rectangle((left + px, top, left + px + band, top + px), fill=SAND)
                    draw.rectangle((left + px - rim, top, left + px, top + px), fill=WATER_RIPPLE)
                elif dx == -1:
                    draw.rectangle((left - band, top, left, top + px), fill=SAND)
                    draw.rectangle((left, top, left + rim, top + px), fill=WATER_RIPPLE)
                elif dy == 1:
                    draw.rectangle((left, top + px, left + px, top + px + band), fill=SAND)
                    draw.rectangle((left, top + px - rim, left + px, top + px), fill=WATER_RIPPLE)
                else:
                    draw.rectangle((left, top - band, left + px, top), fill=SAND)
                    draw.rectangle((left, top, left + px, top + rim), fill=WATER_RIPPLE)
    for j in range(n):
        for i in range(n):
            tx, ty = x0 + i, y0 + j
            if kind(tx, ty) is Terrain.WATER:
                left, top = i * px, j * px
                s = scatter(tx, ty, 7)
                for k in range(2):
                    rx = left + px * (0.15 + 0.5 * ((s >> (k * 4)) & 0xF) / 15 + 0.07 * phase)  # drifts with the phase
                    ry = top + px * (0.2 + 0.6 * ((s >> (k * 4 + 8)) & 0xF) / 15)
                    points = [(rx, ry), (rx + px * 0.12, ry - px * 0.03), (rx + px * 0.24, ry)]
                    draw.line([(round(x), round(y)) for x, y in points], fill=WATER_RIPPLE, width=max(1, round(1.2 * scale)))
    # Margins overlap neighbouring chunks, but must never invent land outside
    # the playable rectangle. Clear after shores so they cannot bleed past it.
    for j in range(n):
        for i in range(n):
            if not in_bounds((x0 + i, y0 + j)):
                draw.rectangle((round(i * px), round(j * px), round((i + 1) * px) - 1, round((j + 1) * px) - 1), fill=(0, 0, 0, 0))
    start, size = round(px), round(CHUNK_PX * scale)
    return image.crop((start, start, start + size, start + size))


def map_edge(length: int, scale: float, theme: MapTheme) -> Image.Image:
    """A narrow exposed stone rim; the playable map meets its bottom edge.

    Layered slate, chipped seams and a worn earth cap make the board boundary
    readable even beside unexplored fog. The view rotates it for each side.
    """
    pal = PALETTES[theme]
    width, height = round(length * TILE * scale), round(TILE * scale)
    image = Image.new("RGBA", (width, height), (10, 12, 20, 255))
    draw = ImageDraw.Draw(image)
    rock = tuple(round(c * 0.48) for c in pal.rock)
    cap = tuple(round(c * 0.53) for c in pal.sand)
    for row, (top, bottom, factor) in enumerate(((0.13, 0.48, 0.68), (0.48, 0.79, 0.88), (0.79, 1.0, 1.16))):
        step = TILE * scale * (1.15 if row == 1 else 0.85)
        for index in range(-1, math.ceil(width / step) + 1):
            seed = scatter(index, row, 27)
            left = (index + row * 0.31) * step
            right = left + step
            y = height * top
            chip = height * (0.035 + (seed & 15) / 400)
            shade = tuple(round(c * factor * (0.88 + ((seed >> 4) & 15) / 75)) for c in rock)
            draw.polygon([(left + scale, y + chip), (right - 3 * scale, y),
                          (right - scale, height * bottom - scale), (left + 2 * scale, height * bottom)], fill=shade)
            draw.line([(left + 3 * scale, y + chip), (right - 4 * scale, y + scale)],
                      fill=tuple(round(c * 1.2) for c in shade), width=max(1, round(scale)))
            if seed & 1:
                mid = left + step * (0.3 + ((seed >> 8) & 15) / 40)
                draw.line([(mid, y + chip), (mid - 3 * scale, height * (top + bottom) / 2),
                           (mid + scale, height * bottom)], fill=darker(shade, 0.55), width=max(1, round(scale)))
    draw.rectangle((0, height - 3 * scale, width, height), fill=cap)
    draw.line([(0, height - scale), (width, height - scale)], fill=darker(cap, 1.3), width=max(1, round(scale)))
    return image


# -- Props --------------------------------------------------------------------------


def _prop(key: str, mesh: Mesh, drop: float, scale: float, *, min_width: float = 0) -> Image.Image:
    """Render *mesh* into a canvas symmetric about the model origin whose bottom is
    *drop* below it, and record the placement."""
    min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
    half_w = math.ceil(max(-min_x, max_x, min_width / 2) + PAD)
    top = math.ceil(-min_y + PAD)
    if max_y + PAD > drop:
        raise ValueError(f"{key}: mesh extends {max_y:.1f} below its anchor, more than its drop of {drop}")
    canvas = (2 * half_w, top + drop)
    placements[key] = Placement(canvas, drop)
    return r3.render(mesh, PROJECTION, scale=scale, canvas=canvas, origin=(half_w, top))


def _ellipse(cx: float, cy: float, rx: float, ry: float, sides: int = 16) -> list[tuple[float, float]]:
    return [(cx + rx * math.cos(2 * math.pi * i / sides), cy + ry * math.sin(2 * math.pi * i / sides)) for i in range(sides)]


def _shadow(radius: float, cx: float = 0.06, cy: float = 0.04) -> Mesh:
    return r3.flat(_ellipse(cx, cy, radius, radius * 0.8), 0.0, SHADOW)


def _facing_quad(center: r3.Vec3, half_w: float, half_h: float) -> list[r3.Vec3]:
    """A vertical square facing the camera (the +y side)."""
    cx, cy, cz = center
    return [(cx - half_w, cy, cz - half_h), (cx + half_w, cy, cz - half_h), (cx + half_w, cy, cz + half_h), (cx - half_w, cy, cz + half_h)]


def _branch(start: r3.Vec3, end: r3.Vec3, radius: float, tip_radius: float, color: Color) -> Mesh:
    """A tapered six-sided growth segment, including leaning trunks and roots."""
    dx, dy, dz = (end[i] - start[i] for i in range(3))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    axis = (dx / length, dy / length, dz / length)
    # A perpendicular frame gives each fork a round cross section.
    side = (-axis[1], axis[0], 0.0) if abs(axis[2]) < 0.99 else (1.0, 0.0, 0.0)
    norm = math.sqrt(sum(v * v for v in side))
    side = tuple(v / norm for v in side)
    up = (axis[1] * side[2] - axis[2] * side[1], axis[2] * side[0] - axis[0] * side[2], axis[0] * side[1] - axis[1] * side[0])
    rings = []
    for center, r in ((start, radius), (end, tip_radius)):
        rings.append([tuple(center[j] + r * (side[j] * math.cos(i * math.tau / 6) + up[j] * math.sin(i * math.tau / 6)) for j in range(3)) for i in range(6)])
    bottom, top = rings
    return [r3.Face(tuple(reversed(bottom)), color), r3.Face(tuple(top), color)] + [
        r3.Face((bottom[i], bottom[(i + 1) % 6], top[(i + 1) % 6], top[i]), color) for i in range(6)
    ]


def _tree(variant: int, theme: MapTheme = MapTheme.SUMMER) -> Mesh:
    """Twenty seeded trees: whorled fir/spruce and recursively forked oak/birch.

    Forks shrink at each generation; their terminal buds grow irregular crowns.
    Winter keeps the same skeleton under snow; wasteland exposes its branching.
    """
    rng = random.Random(8309 + variant * 7919)
    pal = PALETTES[theme]
    species = variant % 4
    height = rng.uniform(1.5, 2.1) * (1.12 if species == 1 else 1)
    leaf = pal.leaf[variant % len(pal.leaf)]
    light = pal.leaf_light[variant % len(pal.leaf_light)]
    bark = (204, 204, 182) if species == 3 and not pal.bare else pal.trunk
    lean = (rng.uniform(-0.12, 0.12), rng.uniform(-0.09, 0.09))
    mesh: Mesh = []  # The feathered ground contact is composited into the sprite below.
    for i in range(5):
        angle = i * math.tau / 5 + rng.random() * 0.3
        mesh += _branch((math.cos(angle) * 0.26, math.sin(angle) * 0.26, 0.01), (0, 0, 0.24), 0.025, 0.065, darker(bark, 0.78))
    mesh += _branch((0, 0, 0.02), (lean[0], lean[1], height), 0.085, 0.012, bark)
    if species < 2 and not pal.bare:
        # Apical growth: staggered branch whorls get shorter towards the leader.
        for level in range(6):
            fraction = level / 6
            z = height * (0.24 + 0.66 * fraction)
            reach = (0.42 if species == 0 else 0.35) * (1 - fraction * 0.74)
            angle = rng.uniform(0, math.tau)
            for i in range(5):
                a = angle + i * math.tau / 5
                end = (lean[0] * fraction + math.cos(a) * reach, lean[1] * fraction + math.sin(a) * reach, z - 0.09)
                mesh += _branch((lean[0] * fraction, lean[1] * fraction, z + 0.09), end, 0.023, 0.006, bark)
                # Overlapping needle fans break the outline into branch tips.
                mesh += r3.cone(end, reach * rng.uniform(0.43, 0.58), height * 0.19, leaf if i % 2 else light, sides=5, rotation=a)
                if pal.snow:
                    mesh += r3.cone((end[0], end[1], end[2] + height * 0.08), reach * 0.36, height * 0.115, SNOW, sides=5, rotation=a)
            mesh += r3.cone((lean[0] * fraction, lean[1] * fraction, z), reach * 0.7, height * 0.25, light if level % 2 else leaf, sides=7, rotation=angle)
        mesh += r3.cone((lean[0], lean[1], height * 0.85), 0.12, height * 0.21, SNOW if pal.snow else light, sides=6)
    else:
        def grow(start: r3.Vec3, angle: float, reach: float, rise: float, depth: int) -> None:
            nonlocal mesh
            end = (start[0] + math.cos(angle) * reach, start[1] + math.sin(angle) * reach, start[2] + rise)
            mesh += _branch(start, end, 0.022 * (depth + 1), 0.012 * (depth + 1), bark)
            if depth:
                for turn in (-0.65, 0.65):
                    grow(end, angle + turn + rng.uniform(-0.2, 0.2), reach * 0.56, rise * 0.65, depth - 1)
            elif not pal.bare:
                radius = rng.uniform(0.20, 0.29) if species == 2 else rng.uniform(0.16, 0.23)
                mesh += r3.sphere(end, radius, light if rng.random() < 0.4 else leaf, rings=3, sides=7)
                mesh += r3.sphere((end[0] - 0.04, end[1] - 0.02, end[2] + radius * 0.4), radius * 0.75, SNOW if pal.snow else light, rings=3, sides=6)
        for i in range(6):
            z = height * (0.38 + i * 0.07)
            grow((lean[0] * z / height, lean[1] * z / height, z), i * 2.39996 + rng.random() * 0.3, rng.uniform(0.15, 0.24), height * rng.uniform(0.12, 0.20), 2)
        if species == 3:
            for i in range(5):
                z = 0.2 + i * height * 0.12
                mesh += r3.box((lean[0] * z / height, lean[1] * z / height + 0.065, z), (0.095, 0.018, 0.025), darker(pal.trunk, 0.7))
    return mesh


def _crystal(base: r3.Vec3, radius: float, height: float, lean: tuple[float, float], color: Color, rotation: float) -> Mesh:
    """A six-sided mineral prism with split bright/dark terminal facets."""
    x, y, z = base
    bottom = [(x + radius * math.cos(rotation + i * math.tau / 6), y + radius * math.sin(rotation + i * math.tau / 6), z) for i in range(6)]
    shoulder = [(px + lean[0] * 0.7, py + lean[1] * 0.7, z + height * 0.72) for px, py, _ in bottom]
    tip = (x + lean[0], y + lean[1], z + height)
    mesh: Mesh = []
    for i in range(6):
        nxt = (i + 1) % 6
        tint = tuple(min(255, round(c * (0.78, 1.12, 0.94, 0.72, 0.88, 1.2)[i])) for c in color)
        mesh.append(r3.Face((bottom[i], bottom[nxt], shoulder[nxt], shoulder[i]), tint))
        mesh.append(r3.Face((shoulder[i], shoulder[nxt], tip), tuple(min(255, round(c * 1.17)) for c in tint)))
    return mesh


def _rock(variant: int, theme: MapTheme = MapTheme.SUMMER) -> Mesh:
    """Seeded crystal colonies: a dominant growth axis with smaller satellite buds."""
    rng = random.Random(1907 + variant * 3571)
    pal = PALETTES[theme]
    crystal = ((78, 177, 190), (126, 148, 212), (115, 188, 173), (158, 137, 201))[variant % 4]
    mesh = _shadow(0.4)
    mesh += r3.sphere((0, 0, 0.1), 0.33, pal.rock, rings=3, sides=7)
    for i in range(rng.randint(4, 7)):
        angle = i * 2.39996 + rng.uniform(-0.3, 0.3)
        reach = 0.0 if i == 0 else rng.uniform(0.15, 0.31)
        x, y = math.cos(angle) * reach, math.sin(angle) * reach
        height = rng.uniform(0.62, 0.92) if i == 0 else rng.uniform(0.27, 0.63)
        mesh += _crystal((x, y, 0.1), rng.uniform(0.08, 0.14), height, (x * 0.4, y * 0.4), crystal, angle)
    if pal.snow:
        mesh += r3.sphere((-0.15, 0.13, 0.13), 0.19, SNOW, rings=3, sides=6)
    return mesh


def _mine(variant: int = 0) -> Mesh:
    """Gold-bearing crystal outcrop with a readable timbered mine entrance."""
    rng = random.Random(6173 + variant * 1049)
    mesh = _shadow(1.22)
    for i in range(9):
        angle = i * math.tau / 9
        x, y = math.cos(angle) * rng.uniform(0.45, 0.87), math.sin(angle) * rng.uniform(0.4, 0.75) - 0.22
        mesh += r3.sphere((x, y, rng.uniform(0.12, 0.23)), rng.uniform(0.36, 0.55), (112, 113, 124), rings=3, sides=6)
    for i in range(8):
        x, y = rng.uniform(-0.95, 0.95), rng.uniform(-0.9, 0.0)
        height = rng.uniform(0.75, 1.65)
        mesh += _crystal((x, y, 0.25), rng.uniform(0.16, 0.27), height, (x * 0.24, y * 0.18), (234, 176 + i * 5, 66), rng.random() * math.tau)
    # Recessed opening, strong beams and a short cart track are visible from above.
    mesh += r3.box((0, 0.53, 0.2), (0.84, 0.95, 0.4), INK)
    for x in (-0.49, 0.49):
        mesh += r3.box((x, 0.65, 0.31), (0.15, 0.7, 0.62), WOOD_DARK)
        mesh += r3.box((x, 0.97, 0.3), (0.18, 0.13, 0.6), WOOD)
    mesh += r3.box((0, 0.85, 0.67), (1.16, 0.45, 0.17), WOOD)
    for y in (1.06, 1.22, 1.38):
        mesh += r3.box((0, y, 0.025), (0.68, 0.075, 0.05), WOOD_DARK)
    for x in (-0.22, 0.22):
        mesh += r3.box((x, 1.18, 0.06), (0.035, 0.58, 0.035), IRON)
    mesh += _crystal((-0.87, 0.8, 0.04), 0.15, 0.48, (-0.07, 0), GOLD, 0.4)
    mesh += _crystal((0.84, 0.94, 0.04), 0.12, 0.35, (0.05, 0), GOLD, 0.1)
    return mesh


def _tree_ground(image: Image.Image, variant: int, theme: MapTheme, scale: float) -> Image.Image:
    """Local shade and litter leave with the tree, revealing unchanged grass."""
    pal = PALETTES[theme]
    rng = random.Random(4127 + variant * 977)
    cx, cy = image.width / 2, image.height - DROP_TREE * scale
    ground = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(ground)
    rx, ry = (9 + variant % 4 * 0.5) * scale, 6.5 * scale
    draw.ellipse((cx + scale - rx, cy + scale - ry, cx + scale + rx, cy + scale + ry), fill=(0, 0, 0, 46))
    ground = ground.filter(ImageFilter.GaussianBlur(2.0 * scale))
    draw = ImageDraw.Draw(ground)
    count = 3 if pal.snow or pal.bare else 9
    # Tiny ochre/olive fragments, with mostly buried litter in winter.
    color = tuple(round(a * 0.65 + b * 0.35) for a, b in zip(pal.grass, pal.trunk))
    alpha = 46 if pal.snow else 110
    for _ in range(count):
        angle, radius = rng.uniform(0, math.tau), rng.uniform(0.16, 0.37) * TILE * scale
        x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius * 0.65
        length = rng.uniform(0.7, 1.3) * scale
        draw.line((x, y, x + math.cos(angle + 0.8) * length, y + math.sin(angle + 0.8) * length),
                  fill=(*color, alpha), width=max(1, round(scale)))
    ground.alpha_composite(image)
    return ground


@lru_cache(maxsize=240)
def _resource_image(kind: str, variant: int, theme: MapTheme, scale: float) -> Image.Image:
    """Reuse immutable pre-renders across matches; gameplay never grows geometry."""
    if kind == "mine":
        return _prop(f"mine.{variant}", _mine(variant), 1.5 * TILE + PAD, scale)
    mesh = {"tree": _tree, "rock": _rock}[kind](variant, theme)
    image = _prop(f"{kind}.{theme.value}.{variant}", mesh, DROP_TREE, scale, min_width=40 if kind == "tree" else 0)
    return _tree_ground(image, variant, theme, scale) if kind == "tree" else image


def mine_image(game: Game, variant: int) -> str:
    key = f"mine.{variant}"
    if not game.assets.has_image(key):
        game.assets.image_from_pil(key, _resource_image("mine", variant, MapTheme.SUMMER, game.backend.scale_factor))
    return key


def _octagon(center: r3.Vec3, radius: float) -> list[r3.Vec3]:
    """A regular octagon in a vertical plane facing the camera."""
    cx, cy, cz = center
    return [(cx + radius * math.cos(a), cy, cz + radius * math.sin(a)) for a in (math.radians(22.5 + 45 * i) for i in range(8))]


def _door(x: float, y: float, z: float, w: float, h: float) -> Mesh:
    return r3.facing(_facing_quad((x, y, z), w / 2, h / 2), INK, VIEW)


def _pennant(x: float, y: float, z: float, height: float, color: Color) -> Mesh:
    pole = r3.box((x, y, z + height / 2), (0.04, 0.04, height), WOOD_DARK)
    flag = r3.facing([(x, y, z + height), (x + 0.42, y, z + height - 0.06), (x + 0.32, y, z + height - 0.2), (x, y, z + height - 0.24)], color, VIEW)
    return pole + flag


def _timber(start: r3.Vec3, end: r3.Vec3, radius: float, color: Color = WOOD_DARK, sides: int = 6) -> Mesh:
    """A beam or log with a true axis and outward-facing end caps."""
    dx, dy, dz = (b - a for a, b in zip(start, end))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    axis = (dx / length, dy / length, dz / length)
    horizontal = math.hypot(dx, dy)
    u = (-dy / horizontal, dx / horizontal, 0.0) if horizontal else (1.0, 0.0, 0.0)
    v = (axis[1] * u[2] - axis[2] * u[1], axis[2] * u[0] - axis[0] * u[2], axis[0] * u[1] - axis[1] * u[0])
    rings = [tuple(tuple(p[j] + radius * (u[j] * math.cos(i * math.tau / sides) + v[j] * math.sin(i * math.tau / sides)) for j in range(3)) for i in range(sides)) for p in (start, end)]
    # u × v points along the axis, so the two caps face outwards.
    mesh = [r3.Face(rings[0][::-1], color), r3.Face(rings[1], color)]
    mesh += [r3.Face((rings[0][i], rings[0][(i + 1) % sides], rings[1][(i + 1) % sides], rings[1][i]), color) for i in range(sides)]
    return mesh


def _yard(size: float, color: Color) -> Mesh:
    h, cut = size / 2 - 0.1, 0.18
    outline = [(-h + cut, -h), (h - cut, -h), (h, -h + cut), (h, h - cut), (h - cut, h), (-h + cut, h), (-h, h - cut), (-h, -h + cut)]
    return r3.flat(outline, 0.025, darker(color, 0.78)) + r3.flat([(x * 0.95, y * 0.95) for x, y in outline], 0.035, color)


def _banner(x: float, y: float, z: float, w: float, h: float, team: Color) -> Mesh:
    points = [(x - w / 2, y, z + h / 2), (x + w / 2, y, z + h / 2), (x + w / 2, y, z - h / 3), (x, y, z - h / 2), (x - w / 2, y, z - h / 3)]
    return r3.facing(points, team, VIEW) + r3.facing(_facing_quad((x, y + 0.012, z + h * 0.1), w * 0.11, h * 0.18), GOLD, VIEW)


def _arch(x: float, y: float, base: float, width: float, height: float, color: Color = INK) -> Mesh:
    points = [(x - width / 2, y, base), (x + width / 2, y, base), (x + width / 2, y, base + height * 0.66), (x + width * 0.34, y, base + height * 0.88), (x, y, base + height), (x - width * 0.34, y, base + height * 0.88), (x - width / 2, y, base + height * 0.66)]
    return r3.facing(points, color, VIEW)


def _inset_arch(x: float, y: float, base: float, width: float, height: float, border: Color, inside: Color, thickness: float = 0.09) -> Mesh:
    """Stone surround with a real opening, so painter sorting cannot cover its inset."""
    outer = _arch(x, y, base, width, height, border)[0].points
    inner = _arch(x, y, base, width - 2 * thickness, height - thickness, inside)[0].points
    mesh = [r3.Face(inner, inside)]
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        if outer[i][2] == inner[i][2] == outer[j][2] == inner[j][2]:
            continue
        mesh += r3.facing([outer[i], outer[j], inner[j], inner[i]], border, VIEW)
    return mesh


def _battlement(x: float, y: float, z: float, radius: float, height: float) -> Mesh:
    mesh = r3.cylinder((x, y, z), radius, height, STONE, sides=8, rotation=math.pi / 8)
    mesh += r3.cylinder((x, y, z + height - 0.16), radius + 0.08, 0.14, STONE_DARK, sides=8, rotation=math.pi / 8)
    mesh += r3.cylinder((x, y, z + height - 0.015), radius + 0.1, 0.12, STONE, sides=8, rotation=math.pi / 8)
    mesh += r3.cylinder((x, y, z + height + 0.11), radius * 0.76, 0.015, INK, sides=8)
    for i in range(8):
        a = math.tau * i / 8
        mesh += r3.rotate_z(r3.box((x + radius * math.cos(a), y + radius * math.sin(a), z + height + 0.22), (radius * 0.56, radius * 0.34, 0.26), STONE), math.degrees(a), about=(x + radius * math.cos(a), y + radius * math.sin(a)))
    return mesh


def _fence(start: tuple[float, float], end: tuple[float, float], count: int = 5) -> Mesh:
    mesh: Mesh = []
    for i in range(count):
        x, y = (a + (b - a) * i / (count - 1) for a, b in zip(start, end))
        mesh += r3.box((x, y, 0.27), (0.075, 0.075, 0.48), WOOD)
        mesh += r3.pyramid((x, y, 0.51), (0.08, 0.08), 0.06, WOOD_DARK)
    for z in (0.19, 0.4):
        mesh += _timber((*start, z), (*end, z), 0.034, WOOD)
    return mesh


def _roofed_walls(center: r3.Vec3, size: r3.Vec3, color: Color) -> Mesh:
    """Walls closed by their pitched roof, without a hidden overlapping flat top."""
    top = center[2] + size[2] / 2
    return [face for face in r3.box(center, size, color) if not all(p[2] == top for p in face.points)]


def _roof_tiles(mesh: Mesh) -> Mesh:
    """Small independently shaded roof faces give slate/thatch visible courses.

    Splitting the slopes also lets the software painter sort a dormer or
    chimney against its actual patch of roof instead of one enormous face.
    """
    tiled: Mesh = []
    for face in mesh:
        pts = face.points
        if max(p[2] for p in pts) == min(p[2] for p in pts):
            continue  # the underside is hidden by the building
        if len(pts) == 3:
            # Pyramid hips split into courses running up to their apex;
            # gable ends are kept as a clean triangular fascia.
            a, b, c = pts
            if a[0] == b[0] == c[0] or a[1] == b[1] == c[1]:
                tiled.append(face)
                continue
            rows = 6
            for row in range(rows):
                low, high = row / rows, (row + 1) / rows
                left = tuple(a[k] + (c[k] - a[k]) * low for k in range(3))
                right = tuple(b[k] + (c[k] - b[k]) * low for k in range(3))
                upper_left = tuple(a[k] + (c[k] - a[k]) * high for k in range(3))
                upper_right = tuple(b[k] + (c[k] - b[k]) * high for k in range(3))
                points = (left, right, upper_right) if row == rows - 1 else (left, right, upper_right, upper_left)
                tiled.append(r3.Face(points, darker(face.color, 0.92 + 0.08 * (row % 2))))
            continue
        cols, rows = 10, 4
        def point(u: float, v: float) -> r3.Vec3:
            return tuple((pts[0][k] * (1 - u) + pts[1][k] * u) * (1 - v) + (pts[3][k] * (1 - u) + pts[2][k] * u) * v for k in range(3))
        for row in range(rows):
            for col in range(cols):
                factor = 0.89 + 0.11 * (scatter(col, row, 71) % 7) / 6
                tiled.append(r3.Face((point(col / cols, row / rows), point((col + 1) / cols, row / rows), point((col + 1) / cols, (row + 1) / rows), point(col / cols, (row + 1) / rows)), darker(face.color, factor)))
    return tiled


@dataclass(frozen=True)
class Materials:
    """What a race builds with; roof colours pass through :meth:`roof`."""

    stone: Color
    stone_dark: Color
    wood: Color
    wood_dark: Color
    plaster: Color
    thatch: Color
    roof_tint: Color | None  # blended into every roof; None keeps the building's own colour
    roof_blend: float = 0.5

    def roof(self, color: Color) -> Color:
        if self.roof_tint is None:
            return color
        return tuple(round(c * (1 - self.roof_blend) + t * self.roof_blend) for c, t in zip(color, self.roof_tint))  # type: ignore[return-value]


MATERIALS: dict[Race, Materials] = {
    Race.HUMAN: Materials(STONE, STONE_DARK, WOOD, WOOD_DARK, PLASTER, THATCH, None),
    Race.ORC: Materials((122, 108, 94), (84, 74, 66), (112, 78, 48), (72, 50, 34), (152, 118, 84), (124, 92, 56), (96, 40, 30), 0.55),
    Race.ELF: Materials((200, 204, 194), (152, 158, 148), (212, 194, 152), (162, 144, 106), (238, 234, 220), (136, 178, 108), (70, 150, 110), 0.55),
    Race.DWARF: Materials((150, 148, 146), (104, 102, 100), (128, 96, 62), (90, 64, 40), (172, 168, 162), (118, 108, 100), (88, 92, 106), 0.6),
}
COPPER = (190, 120, 70)


def _building(building_type: BuildingType, player: int, race: Race = Race.HUMAN) -> Mesh:
    """Purpose-led silhouettes: a yard's machinery matters as much as its walls.  A race changes the
    materials and roof colours throughout, redraws the hall, farm and tower it is known by, and dresses
    every yard with its own ornaments (see :func:`_dressing`)."""
    m = MATERIALS[race]
    roof = m.roof
    mesh = _building_body(building_type, player, race, m, roof)
    return mesh + _dressing(building_type, race, team_color(player))


def _building_body(building_type: BuildingType, player: int, race: Race, m: Materials, roof) -> Mesh:
    team = team_color(player)
    trim = darker(team, 0.68)
    if building_type is BuildingType.TOWN_HALL:
        mesh = _yard(3, (168, 157, 136))
        mesh += _roofed_walls((0, -0.32, 0.8), (2.05, 1.62, 1.5), m.stone)
        for x in (-1.045, 1.045):
            mesh += r3.box((x, -0.32, 1.51), (0.09, 1.76, 0.16), m.plaster)
        for y in (-1.155, 0.515):
            mesh += r3.box((0, y, 1.51), (2.18, 0.09, 0.16), m.plaster)
        if race is Race.ORC:
            # A hide dome stretched over the hall, ribbed with bone and crowned with a skull.
            mesh += r3.sphere((0, -0.32, 1.45), 1.12, m.roof((150, 118, 84)), rings=5, sides=10)
            for i in range(6):
                a = i * math.tau / 6
                mesh += r3.cone((math.cos(a) * 0.95, -0.32 + math.sin(a) * 0.8, 2.0), 0.07, 0.34, BONE, sides=4)
            mesh += r3.sphere((0, -0.32, 2.62), 0.16, BONE, rings=3, sides=6)
            mesh += _pennant(0.5, -0.9, 2.3, 0.7, team)
        elif race is Race.ELF:
            # A tall pointed roof with a living crown of leaves growing through it.
            mesh += _roof_tiles(r3.pyramid((0, -0.32, 1.6), (2.25, 1.85), 1.35, trim))
            for x, y, radius in ((-0.6, -0.7, 0.42), (0.55, -0.55, 0.38), (0.0, 0.05, 0.36), (-0.2, -1.0, 0.3)):
                mesh += r3.sphere((x, y, 2.35 + radius * 0.6), radius, (86, 150, 96), rings=3, sides=7)
                mesh += r3.sphere((x - 0.08, y - 0.04, 2.35 + radius * 1.1), radius * 0.6, (118, 178, 112), rings=3, sides=6)
            mesh += _pennant(0, -0.32, 2.97, 0.5, team)
        elif race is Race.DWARF:
            # A flat stone top with battlements and a copper dome.
            mesh += r3.box((0, -0.32, 1.66), (2.2, 1.8, 0.12), m.stone_dark)
            for x in (-1.0, 1.0):
                for y in (-1.15, 0.5):
                    mesh += r3.box((x, y, 1.84), (0.22, 0.22, 0.26), m.stone)
            mesh += r3.cylinder((0, -0.32, 1.72), 0.62, 0.3, m.stone, sides=8, rotation=math.pi / 8)
            mesh += r3.sphere((0, -0.32, 2.02), 0.6, COPPER, rings=4, sides=10)
            mesh += r3.cylinder((0, -0.32, 2.58), 0.08, 0.3, GOLD, sides=6)
            mesh += _pennant(0.9, -1.15, 2.1, 0.5, team)
        else:
            mesh += _roof_tiles(r3.pyramid((0, -0.32, 1.6), (2.25, 1.85), 0.83, trim))
            mesh += _roofed_walls((0, -0.36, 2.05), (0.76, 0.66, 0.82), m.stone)
            mesh += _roof_tiles(r3.pyramid((0, -0.36, 2.46), (0.92, 0.82), 0.42, team))
            mesh += _arch(0, -0.018, 2.12, 0.27, 0.29, GOLD)
            mesh += _pennant(0, -0.36, 2.88, 0.56, team)
        # Twin gate towers and their connecting wall form a civic fortress.
        mesh += r3.box((0, 0.71, 0.53), (1.8, 0.32, 0.94), m.stone_dark)
        for x in (-0.92, 0.92):
            mesh += _battlement(x, 0.62, 0.08, 0.36, 1.45)
            mesh += _arch(x, 0.962, 0.83, 0.105, 0.38)
            mesh += _banner(x, 1.005, 0.54, 0.28, 0.38, team)
        mesh += _inset_arch(0, 0.895, 0.08, 0.8, 1.1, m.plaster, INK, 0.11)
        for x in (-0.19, 0, 0.19):
            mesh += r3.box((x, 0.91, 0.44), (0.035, 0.025, 0.69), m.wood)
        mesh += r3.box((0, 1.06, 0.09), (0.87, 0.37, 0.16), m.stone)
        mesh += r3.box((0, 1.28, 0.045), (1.05, 0.19, 0.09), m.stone_dark)
        return mesh
    if building_type is BuildingType.BARRACKS:
        mesh = _yard(3, (154, 131, 98))
        mesh += _roofed_walls((0, -0.65, 0.55), (2.5, 1.05, 1.03), m.stone_dark)
        mesh += _roof_tiles(r3.gable_roof((0, -0.65, 1.07), (2.73, 1.35), 0.54, roof((98, 104, 119))))
        mesh += r3.box((0, -0.65, 1.61), (2.82, 0.1, 0.1), m.wood_dark)
        for x in (-1.12, -0.56, 0.56, 1.12):
            mesh += r3.box((x, -0.11, 0.57), (0.1, 0.1, 1.05), m.wood_dark)
        mesh += _arch(0, -0.102, 0.05, 0.69, 0.9)
        for x in (-0.86, 0.86):
            mesh += _banner(x, -0.035, 0.72, 0.34, 0.64, team)
        # Open parade ground, palisade wings and obvious military equipment.
        for x in (-1.24, 1.24):
            for y in (0.12, 0.4, 0.68, 0.96, 1.22):
                mesh += r3.box((x, y, 0.34), (0.13, 0.2, 0.57), m.wood)
                mesh += r3.pyramid((x, y, 0.625), (0.13, 0.2), 0.13, m.wood)
        for x in (-0.79, 0.73):
            mesh += _timber((x, 0.5, 0.06), (x, 0.5, 0.96), 0.053)
            mesh += _timber((x - 0.27, 0.5, 0.71), (x + 0.27, 0.5, 0.71), 0.046)
            mesh += r3.facing(_octagon((x, 0.59, 0.7), 0.21), team, VIEW)
            mesh += r3.facing(_octagon((x, 0.603, 0.7), 0.08), GOLD, VIEW)
        for x in (-0.98, -0.72, -0.46):
            mesh += _timber((x, 1.03, 0.12), (x + 0.04, 1.02, 1.0), 0.025, m.wood)
            mesh += r3.cone((x + 0.04, 1.02, 1.0), 0.075, 0.18, IRON, sides=4)
        mesh += _timber((-1.1, 1.06, 0.48), (-0.34, 1.06, 0.48), 0.05)
        mesh += _pennant(1.1, -1.0, 1.2, 0.96, team)
        return mesh
    if building_type is BuildingType.FARM:
        mesh = _yard(2, (150, 115, 70))
        mesh += _roofed_walls((-0.47, -0.51, 0.31), (0.75, 0.67, 0.56), m.plaster)
        mesh += _roof_tiles(r3.gable_roof((-0.47, -0.51, 0.59), (0.93, 0.87), 0.43, m.thatch))
        mesh += r3.box((-0.47, -0.51, 1.025), (1.0, 0.07, 0.07), m.wood_dark)
        mesh += _door(-0.46, -0.168, 0.25, 0.26, 0.42)
        mesh += _banner(-0.75, -0.161, 0.37, 0.14, 0.26, team)
        if race is Race.ORC:
            # A muddy pen with three pigs.
            mesh += r3.flat([(-0.02, -0.82), (0.84, -0.82), (0.84, 0.08), (-0.02, 0.08)], 0.045, (118, 88, 58))
            mesh += _fence((-0.02, -0.82), (0.84, -0.82), 4) + _fence((0.84, -0.82), (0.84, 0.08), 3)
            for x, y, a in ((0.22, -0.58, 0.3), (0.6, -0.22, 2.1), (0.4, -0.5, 4.0)):
                pig = r3.box((x, y, 0.17), (0.4, 0.26, 0.24), (226, 166, 156)) + r3.box((x + 0.25, y, 0.2), (0.16, 0.18, 0.17), (214, 150, 144))
                pig += r3.box((x + 0.34, y, 0.18), (0.04, 0.09, 0.07), (160, 96, 100))
                for side in (-1, 1):
                    pig += r3.cone((x + 0.27, y + side * 0.07, 0.28), 0.03, 0.08, (214, 150, 144), sides=4)
                mesh += r3.rotate_z(pig, math.degrees(a), about=(x, y))
        elif race is Race.ELF:
            # An orchard of small fruit trees.
            for x, y in ((0.15, -0.6), (0.6, -0.55), (0.35, -0.15), (0.75, -0.1), (0.15, 0.3)):
                mesh += _timber((x, y, 0.05), (x, y, 0.36), 0.035, m.wood_dark, sides=5)
                mesh += r3.sphere((x, y, 0.5), 0.2, (92, 156, 98), rings=3, sides=6)
                mesh += r3.sphere((x + 0.08, y - 0.1, 0.55), 0.06, (230, 90, 80), rings=2, sides=5)
        elif race is Race.DWARF:
            # A brewhouse: kegs by the door and a stout stone chimney.
            for x, y in ((0.2, -0.65), (0.5, -0.65), (0.35, -0.42), (0.7, -0.3)):
                mesh += r3.cylinder((x, y, 0.05), 0.13, 0.28, m.wood, sides=8)
                for z in (0.1, 0.26):
                    mesh += r3.cylinder((x, y, z), 0.135, 0.03, m.wood_dark, sides=8)
            mesh += r3.box((-0.7, -0.75, 0.9), (0.2, 0.2, 0.7), m.stone_dark)
            mesh += r3.box((-0.7, -0.75, 1.27), (0.26, 0.26, 0.06), m.stone)
        else:
            for row in range(5):
                y = -0.71 + row * 0.31
                mesh += r3.box((0.4, y, 0.055), (0.87, 0.22, 0.07), (101, 77, 44))
                for k in range(6):
                    x = 0.04 + k * 0.145
                    h = 0.21 + 0.07 * ((row * 5 + k * 3) % 4) / 3
                    mesh += _timber((x, y, 0.09), (x + 0.025, y, h + 0.09), 0.017, (189, 161, 63), sides=4)
                    mesh += r3.sphere((x + 0.025, y, h + 0.08), 0.047, (238, 201 - row * 5, 93), rings=3, sides=5)
        mesh += _fence((-0.86, 0.87), (0.86, 0.87), 5)
        mesh += r3.cylinder((-0.55, 0.34, 0.04), 0.22, 0.31, m.thatch, sides=8)
        mesh += r3.cylinder((-0.55, 0.34, 0.16), 0.225, 0.045, m.wood_dark, sides=8)
        return mesh
    if building_type is BuildingType.TOWER and race is Race.ORC:
        # A timber watchtower: four leaning posts, a platform, a hide roof and spikes.
        mesh = _yard(2, (128, 112, 92))
        for x, y in ((-0.55, -0.55), (0.55, -0.55), (-0.55, 0.55), (0.55, 0.55)):
            mesh += _timber((x, y, 0.05), (x * 0.7, y * 0.7, 1.7), 0.09, m.wood_dark)
        for z in (0.6, 1.2):
            for (x0, y0), (x1, y1) in (((-0.55, -0.55), (0.55, -0.55)), ((-0.55, 0.55), (0.55, 0.55)), ((-0.55, -0.55), (-0.55, 0.55)), ((0.55, -0.55), (0.55, 0.55))):
                f = 1 - 0.3 * z / 1.7
                mesh += _timber((x0 * f, y0 * f, z), (x1 * f, y1 * f, z), 0.04, m.wood)
        mesh += r3.box((0, 0, 1.72), (1.0, 1.0, 0.1), m.wood)
        mesh += r3.box((0, 0, 1.92), (0.7, 0.7, 0.32), m.wood_dark)
        mesh += r3.pyramid((0, 0, 2.08), (1.1, 1.1), 0.5, m.roof((150, 118, 84)))
        for x, y in ((-0.45, -0.45), (0.45, -0.45), (-0.45, 0.45), (0.45, 0.45)):
            mesh += r3.cone((x, y, 2.05), 0.05, 0.3, BONE, sides=4)
        mesh += r3.sphere((0, 0, 2.66), 0.13, BONE, rings=3, sides=6)
        mesh += _banner(0, 0.36, 1.95, 0.4, 0.4, team)
        return mesh
    if building_type is BuildingType.TOWER and race is Race.ELF:
        # A watch tree: a great trunk with a railed platform in its crown.
        mesh = _yard(2, (150, 170, 130))
        mesh += _branch((0, 0, 0.03), (0.05, -0.05, 2.1), 0.32, 0.18, (150, 122, 88))
        for i in range(5):
            a = i * math.tau / 5 + 0.4
            mesh += _branch((math.cos(a) * 0.4, math.sin(a) * 0.4, 0.02), (0, 0, 0.5), 0.05, 0.12, (128, 102, 72))
        mesh += r3.cylinder((0.05, -0.05, 2.05), 0.62, 0.1, m.wood, sides=8)
        for i in range(8):
            a = i * math.tau / 8
            mesh += r3.box((0.05 + math.cos(a) * 0.58, -0.05 + math.sin(a) * 0.58, 2.3), (0.06, 0.06, 0.4), m.wood_dark)
        mesh += r3.cylinder((0.05, -0.05, 2.48), 0.62, 0.04, m.wood_dark, sides=8)
        for x, y, radius in ((0.5, 0.2, 0.42), (-0.45, -0.3, 0.4), (0.1, -0.55, 0.36), (0.0, 0.1, 0.5)):
            mesh += r3.sphere((x, y, 2.75 + radius * 0.4), radius, (86, 150, 96), rings=3, sides=7)
        mesh += _banner(0.05, 0.6, 2.28, 0.34, 0.4, team)
        return mesh
    if building_type is BuildingType.TOWER and race is Race.DWARF:
        # A squat granite bolt tower with a crossbow engine on its roof.
        mesh = _yard(2, (140, 138, 134))
        mesh += r3.cylinder((0, 0, 0.05), 0.8, 0.3, m.stone_dark, sides=8, rotation=math.pi / 8)
        mesh += r3.cylinder((0, 0, 0.35), 0.66, 1.2, m.stone, sides=8, rotation=math.pi / 8)
        mesh += r3.cylinder((0, 0, 1.5), 0.74, 0.16, m.stone_dark, sides=8, rotation=math.pi / 8)
        for i in range(8):
            a = math.tau * i / 8
            mesh += r3.box((0.7 * math.cos(a), 0.7 * math.sin(a), 1.76), (0.22, 0.22, 0.24), m.stone)
        mesh += r3.box((0, 0, 1.82), (0.32, 0.5, 0.28), m.wood_dark)
        mesh += _timber((-0.55, 0.25, 2.0), (0.55, 0.25, 2.0), 0.045, COPPER)
        mesh += _timber((0, -0.35, 2.02), (0, 0.55, 2.02), 0.04, m.wood)
        mesh += _timber((-0.55, 0.25, 2.0), (0, -0.2, 2.0), 0.012, PLASTER) + _timber((0.55, 0.25, 2.0), (0, -0.2, 2.0), 0.012, PLASTER)
        mesh += _arch(0, 0.665, 0.25, 0.24, 0.5)
        mesh += _banner(0, 0.7, 1.05, 0.36, 0.5, team)
        return mesh
    if building_type is BuildingType.TOWER:
        mesh = _yard(2, (155, 151, 139))
        mesh += r3.cylinder((0, 0, 0.05), 0.77, 0.27, m.stone_dark, sides=8, rotation=math.pi / 8)
        mesh += _battlement(0, 0, 0.32, 0.53, 2.05)
        for z in (0.65, 1.26, 1.87):
            mesh += r3.cylinder((0, 0, z), 0.554, 0.085, m.stone_dark, sides=8, rotation=math.pi / 8)
        for x in (-0.29, 0.29):
            mesh += _arch(x, 0.495, 1.43, 0.1, 0.38)
        mesh += _arch(0, 0.525, 0.25, 0.24, 0.56)
        mesh += _banner(0, 0.565, 1.06, 0.36, 0.56, team)
        for x in (-0.62, 0.62):
            mesh += r3.box((x, 0.12, 0.45), (0.2, 0.6, 0.65), m.stone_dark)
            mesh += r3.pyramid((x, 0.12, 0.775), (0.2, 0.6), 0.25, m.stone)
        mesh += _pennant(0, -0.1, 2.48, 0.7, team)
        return mesh
    if building_type is BuildingType.LUMBER_MILL:
        mesh = _yard(3, (157, 121, 78))
        # Open saw shed: its machinery and log deck remain visible from above.
        for x in (-1.08, 0.14):
            for y in (-1.06, 0.27):
                mesh += r3.box((x, y, 0.63), (0.15, 0.15, 1.19), m.wood_dark)
        mesh += _roof_tiles(r3.gable_roof((-0.47, -0.46, 1.24), (1.57, 1.59), 0.45, roof((178, 117, 61))))
        for y in (-0.96, -0.69, -0.42, -0.15, 0.12):
            z = 1.24 + 0.45 * (1 - abs(y + 0.46) / 0.795)
            mesh += r3.box((-0.47, y, z + 0.025), (1.58, 0.028, 0.04), m.wood_dark)
        mesh += r3.box((-0.47, 0.32, 1.15), (1.42, 0.13, 0.18), m.wood_dark)
        mesh += _banner(-0.48, 0.392, 1.08, 0.31, 0.35, team)
        # Stockpile rounds and pale end grain give logs a readable identity.
        for x, z in ((0.65, 0.2), (1.05, 0.2), (0.85, 0.52)):
            mesh += _timber((x, -1.03, z), (x, 0.02, z), 0.2, (101, 65, 38), sides=9)
            mesh += r3.facing(_octagon((x, 0.031, z), 0.164), (211, 167, 101), VIEW)
            mesh += r3.facing(_octagon((x, 0.045, z), 0.076), (169, 120, 67), VIEW)
        mesh += r3.box((0, 0.9, 0.26), (2.28, 0.48, 0.13), m.wood_dark)
        mesh += _timber((-1.04, 0.88, 0.45), (0.92, 0.88, 0.45), 0.18, (125, 84, 45), sides=9)
        # Large steel saw, with a serrated edge and a bolted hub.
        points = [(0.42 + (0.49 if i % 2 == 0 else 0.40) * math.cos(i * math.tau / 32), 0.79, 0.79 + (0.49 if i % 2 == 0 else 0.40) * math.sin(i * math.tau / 32)) for i in range(32)]
        mesh += r3.facing(points, IRON, VIEW)
        mesh += r3.facing(_octagon((0.42, 0.803, 0.79), 0.14), m.wood_dark, VIEW)
        mesh += r3.facing(_octagon((0.42, 0.815, 0.79), 0.055), GOLD, VIEW)
        for x in (-0.94, 0.96):
            mesh += r3.box((x, 0.91, 0.15), (0.12, 0.43, 0.3), m.wood)
        return mesh
    if building_type is BuildingType.BLACKSMITH:
        mesh = _yard(3, (118, 113, 106))
        brick = (134, 82, 58)
        mesh += r3.box((-0.8, -0.64, 0.66), (0.82, 1.19, 1.23), brick)
        for x in (-1.14, -0.46):
            mesh += r3.box((x, 0.095, 0.66), (0.14, 0.28, 1.23), brick)
        mesh += r3.box((-0.8, 0.095, 1.17), (0.82, 0.28, 0.21), brick)
        mesh += r3.box((-0.78, -0.57, 1.75), (0.56, 0.63, 1.26), brick)
        for z in (1.3, 1.65, 2.0, 2.33):
            mesh += r3.box((-0.78, -0.57, z), (0.64, 0.72, 0.1), m.stone_dark)
        mesh += r3.box((-0.78, -0.57, 2.39), (0.41, 0.49, 0.015), INK)
        mesh += r3.box((0.34, -0.87, 0.57), (1.46, 0.29, 1.03), m.stone_dark)
        for x in (-0.25, 1.04):
            mesh += r3.box((x, 0.14, 0.58), (0.12, 0.12, 1.09), m.wood_dark)
        mesh += _roof_tiles(r3.gable_roof((0.35, -0.53, 1.14), (1.6, 1.49), 0.34, roof((68, 80, 91))))
        # Furnace mouth is a dark arch containing nested hot coals.
        mesh += _inset_arch(-0.8, 0.245, 0.17, 0.67, 0.92, m.stone_dark, (56, 35, 29), 0.065)
        for x, z, h in ((-0.98, 0.44, 0.47), (-0.8, 0.47, 0.7), (-0.63, 0.44, 0.42)):
            mesh += r3.facing([(x - 0.09, 0.43, z), (x + 0.1, 0.43, z), (x + 0.015, 0.43, z + h)], (255, 115, 27), VIEW)
            mesh += r3.facing([(x - 0.04, 0.45, z + 0.15), (x + 0.06, 0.45, z + 0.15), (x, 0.45, z + h * 0.82)], (255, 219, 91), VIEW)
        mesh += r3.box((-0.8, 0.43, 0.14), (0.71, 0.41, 0.19), m.stone_dark)
        for x in (-0.96, -0.8, -0.64):
            mesh += r3.box((x, 0.31, 0.25), (0.035, 0.12, 0.22), INK)
        # An oversized horned anvil occupies the uncovered working apron.
        mesh += r3.cylinder((0.49, 0.85, 0.055), 0.3, 0.26, m.wood_dark, sides=8)
        mesh += r3.box((0.49, 0.85, 0.36), (0.39, 0.28, 0.16), (54, 63, 70))
        mesh += r3.box((0.49, 0.85, 0.51), (0.64, 0.36, 0.13), IRON)
        mesh += r3.facing([(0.8, 1.035, 0.58), (1.11, 1.035, 0.5), (0.8, 1.035, 0.45)], IRON, VIEW)
        mesh += _timber((0.16, 0.9, 0.63), (0.48, 0.9, 0.68), 0.035, m.wood)
        mesh += r3.box((0.16, 0.9, 0.66), (0.11, 0.12, 0.16), INK)
        mesh += _banner(0.46, 0.234, 1.13, 0.36, 0.39, team)
        mesh += r3.cylinder((-0.59, 1.03, 0.045), 0.23, 0.31, m.wood, sides=8)
        mesh += r3.cylinder((-0.59, 1.03, 0.353), 0.19, 0.01, (64, 108, 127), sides=8)
        return mesh
    if building_type is BuildingType.STABLES:
        mesh = _yard(3, (167, 140, 94))
        mesh += _roofed_walls((0, -0.73, 0.47), (2.48, 0.83, 0.86), m.wood)
        mesh += _roof_tiles(r3.gable_roof((0, -0.73, 0.93), (2.74, 1.08), 0.54, roof((180, 139, 72))))
        mesh += r3.box((0, -0.73, 1.48), (2.83, 0.09, 0.07), m.wood_dark)
        for x in (-0.83, 0, 0.83):
            mesh += _arch(x, -0.304, 0.09, 0.54, 0.7)
            mesh += r3.box((x, -0.27, 0.26), (0.55, 0.07, 0.32), m.wood_dark)
            mesh += r3.box((x, -0.222, 0.34), (0.59, 0.035, 0.045), m.thatch)
        for x in (-1.15, -0.42, 0.42, 1.15):
            mesh += r3.box((x, -0.29, 0.53), (0.1, 0.1, 0.88), m.wood_dark)
        mesh += _fence((-1.2, -0.1), (-1.2, 1.19), 4) + _fence((1.2, -0.1), (1.2, 1.19), 4)
        mesh += _fence((-1.2, 1.19), (0.08, 1.19), 4)
        mesh += _fence((0.72, 1.19), (1.2, 1.19), 2)
        if race is not Race.HUMAN:
            # The race's own beast, saddled and side-on in the yard.
            beast = [face for face in _mount("stand", race is Race.DWARF, team, race) if face.color != SHADOW]
            mesh += _shift(r3.scale(r3.rotate_z(beast, 90), 0.62), (0.1, 0.55, 0.05))
            mesh += _banner(0, -0.168, 1.22, 0.32, 0.42, team)
            mesh += r3.box((-0.77, 0.45, 0.2), (0.35, 0.64, 0.26), m.wood_dark)
            mesh += r3.box((-0.77, 0.45, 0.34), (0.28, 0.55, 0.035), (205, 177, 98))
            return mesh
        # A side-on horse keeps the long neck, muzzle and four legs legible.
        horse = (110, 69, 43)
        mesh += r3.box((0.1, 0.55, 0.58), (0.87, 0.3, 0.33), horse)
        for x in (-0.23, 0.43):
            for y in (0.44, 0.65):
                mesh += _timber((x, y, 0.1), (x + 0.035, y, 0.48), 0.045, horse)
                mesh += r3.box((x + 0.02, y, 0.09), (0.12, 0.085, 0.095), INK)
        mesh += _timber((0.43, 0.56, 0.62), (0.61, 0.56, 1.04), 0.125, horse)
        mesh += r3.box((0.74, 0.56, 1.01), (0.36, 0.2, 0.21), horse)
        mesh += r3.box((0.85, 0.56, 0.985), (0.15, 0.205, 0.15), (169, 126, 88))
        for y in (0.5, 0.63):
            mesh += r3.cone((0.62, y, 1.105), 0.045, 0.16, horse, sides=4)
        mesh += _timber((-0.35, 0.55, 0.66), (-0.54, 0.55, 0.28), 0.06, INK)
        mesh += _timber((0.43, 0.55, 0.76), (0.53, 0.55, 1.13), 0.045, INK)
        mesh += r3.box((0.03, 0.55, 0.765), (0.34, 0.37, 0.055), team)
        mesh += _banner(0, -0.168, 1.22, 0.32, 0.42, team)
        mesh += r3.box((-0.77, 0.45, 0.2), (0.35, 0.64, 0.26), m.wood_dark)
        mesh += r3.box((-0.77, 0.45, 0.34), (0.28, 0.55, 0.035), (205, 177, 98))
        return mesh
    if building_type is BuildingType.WORKSHOP:
        mesh = _yard(3, (130, 116, 94))
        # A roofless engineering yard and tall timber crane replace a house.
        mesh += r3.box((-0.65, -0.84, 0.42), (1.3, 0.65, 0.74), m.wood_dark)
        mesh += r3.box((-0.65, -0.84, 0.82), (1.43, 0.74, 0.12), m.wood)
        for x in (-1.0, -0.74, -0.48, -0.22):
            mesh += r3.box((x, -0.84, 0.9), (0.2, 0.63, 0.07), (175, 131, 77))
        for x in (0.54, 1.03):
            mesh += _timber((x, -0.85, 0.07), (0.8, -0.64, 2.11), 0.085, m.wood)
        mesh += _timber((0.8, -0.64, 2.05), (-0.8, 0.69, 2.05), 0.095, m.wood)
        mesh += _timber((0.8, -0.64, 1.27), (-0.4, 0.36, 2.05), 0.06, m.wood_dark)
        mesh += _timber((0.8, -0.64, 2.06), (1.23, -1.03, 2.06), 0.08, m.wood_dark)
        mesh += r3.box((1.19, -0.99, 1.82), (0.3, 0.28, 0.39), m.stone_dark)
        mesh += _timber((-0.69, 0.6, 2.05), (-0.69, 0.6, 0.93), 0.023, INK)
        mesh += r3.box((-0.69, 0.6, 0.77), (0.43, 0.42, 0.35), m.wood)
        for x in (-0.83, -0.55):
            mesh += r3.box((x, 0.819, 0.77), (0.04, 0.025, 0.35), m.wood_dark)
        # Siege chassis under assembly: iron-rim wheels and raised throwing arm.
        mesh += r3.box((0.38, 0.76, 0.37), (0.74, 0.76, 0.18), m.wood_dark)
        for x in (-0.08, 0.84):
            for y in (0.43, 1.09):
                wheel = _timber((x - 0.065, y, 0.27), (x + 0.065, y, 0.27), 0.24, INK, sides=10)
                wheel += _timber((x - 0.072, y, 0.27), (x + 0.072, y, 0.27), 0.18, m.wood, sides=8)
                mesh += wheel
        mesh += _timber((0.12, 0.67, 0.4), (0.37, 0.67, 1.13), 0.06, m.wood)
        mesh += _timber((0.64, 0.67, 0.4), (0.37, 0.67, 1.13), 0.06, m.wood)
        mesh += _timber((0.37, 0.38, 0.78), (0.37, 1.02, 1.44), 0.052, m.wood)
        mesh += r3.box((0.37, 1.02, 1.43), (0.29, 0.24, 0.11), m.wood_dark)
        mesh += _banner(-0.64, -0.491, 0.54, 0.39, 0.39, team)
        mesh += _pennant(0.8, -0.64, 2.16, 0.52, team)
        return mesh
    if building_type is BuildingType.CHURCH:
        mesh = _yard(3, (183, 179, 160))
        shingle = roof((68, 111, 123))
        mesh += _roofed_walls((0.1, -0.2, 0.73), (1.22, 2.03, 1.38), m.plaster)
        mesh += _roofed_walls((0.1, -0.38, 0.51), (2.35, 0.72, 0.94), m.stone)
        mesh += r3.rotate_z(r3.gable_roof((0.1, -0.2, 1.43), (2.21, 1.4), 0.85, shingle), 90, about=(0.1, -0.2))
        mesh += r3.gable_roof((0.1, -0.38, 1.02), (2.57, 0.89), 0.52, shingle)
        mesh += r3.box((0.1, -0.2, 2.29), (0.055, 2.23, 0.055), darker(shingle, 0.8))
        # An attached octagonal bell tower rises above the cross-shaped nave.
        mesh += r3.cylinder((-0.9, -0.68, 0.05), 0.34, 2.22, m.stone, sides=8, rotation=math.pi / 8)
        mesh += r3.cylinder((-0.9, -0.68, 1.79), 0.39, 0.12, m.plaster, sides=8, rotation=math.pi / 8)
        mesh += _arch(-0.9, -0.361, 1.89, 0.24, 0.35)
        mesh += r3.cone((-0.9, -0.68, 2.28), 0.49, 1.0, shingle, sides=8, rotation=math.pi / 8)
        if race is Race.ORC:
            mesh += _timber((-0.9, -0.68, 3.2), (-0.9, -0.68, 3.55), 0.04, m.wood_dark)
            mesh += r3.sphere((-0.9, -0.68, 3.62), 0.15, BONE, rings=3, sides=6)
            for x in (-1.08, -0.72):
                mesh += r3.cone((x, -0.68, 3.28), 0.04, 0.3, BONE, sides=4)
        elif race is Race.ELF:
            mesh += r3.box((-0.9, -0.68, 3.42), (0.045, 0.045, 0.4), GOLD)
            crescent = [(-0.9 + 0.2 * math.cos(a), -0.68, 3.75 + 0.2 * math.sin(a)) for a in (i * math.pi / 5 - math.pi / 2 for i in range(11))]
            mesh += _unit_panel(crescent + [(-0.9 + 0.1 * math.cos(a), -0.68, 3.75 + 0.1 * math.sin(a)) for a in (i * math.pi / 5 - math.pi / 2 for i in reversed(range(11)))], GOLD)
        elif race is Race.DWARF:
            mesh += r3.box((-0.9, -0.68, 3.4), (0.055, 0.055, 0.34), COPPER)
            mesh += r3.box((-0.9, -0.68, 3.62), (0.3, 0.18, 0.16), COPPER)
        else:
            mesh += r3.box((-0.9, -0.68, 3.42), (0.055, 0.055, 0.42), GOLD)
            mesh += r3.box((-0.9, -0.68, 3.48), (0.27, 0.055, 0.055), GOLD)
        mesh += r3.facing([(-0.6, 0.911, 1.43), (0.8, 0.911, 1.43), (0.1, 0.911, 2.28)], m.plaster, VIEW)
        for x in (-0.66, 0.86):
            mesh += r3.box((x, 0.78, 0.58), (0.23, 0.52, 1.07), m.stone)
            mesh += r3.pyramid((x, 0.78, 1.115), (0.25, 0.54), 0.25, m.plaster)
        mesh += _inset_arch(0.1, 0.945, 0.12, 0.67, 1.07, m.stone_dark, (81, 61, 51), 0.1)
        mesh += _inset_arch(0.1, 0.947, 1.3, 0.44, 0.61, m.stone_dark, (100, 184, 209) if race is not Race.ORC else (200, 90, 40), 0.07)
        if race is Race.HUMAN:
            mesh += r3.box((0.1, 0.963, 0.43), (0.029, 0.02, 0.59), GOLD)
            mesh += r3.box((0.1, 0.96, 1.56), (0.035, 0.025, 0.38), GOLD)
            mesh += r3.box((0.1, 0.96, 1.53), (0.28, 0.025, 0.035), GOLD)
        elif race is Race.DWARF:
            mesh += r3.box((0.1, 0.96, 1.55), (0.3, 0.025, 0.06), GOLD)
        for x in (-0.91, 1.1):
            mesh += _banner(x, 0.017, 0.78, 0.26, 0.44, team)
        mesh += r3.box((0.1, 1.13, 0.1), (0.88, 0.31, 0.18), m.stone)
        mesh += r3.box((0.1, 1.31, 0.055), (1.03, 0.19, 0.09), m.stone_dark)
        return mesh
    raise ValueError(building_type)




def _dressing(building_type: BuildingType, race: Race, team: Color) -> Mesh:
    """Race ornaments around every yard: orc bone spikes and a skull pole, elf saplings and a moon
    standard, dwarf rune pillars with copper caps.  Humans keep their plain yards."""
    size = BUILDINGS[building_type].size
    h = size / 2 - 0.22
    mesh: Mesh = []
    if race is Race.ORC:
        for x, y in ((-h, -h), (h, -h), (-h, h), (h, h)):
            mesh += r3.cone((x, y, 0.03), 0.06, 0.55, BONE, sides=4)
        mesh += _timber((h - 0.1, h - 0.05, 0.05), (h - 0.1, h - 0.05, 1.3), 0.05, WOOD_DARK)
        mesh += r3.sphere((h - 0.1, h - 0.05, 1.38), 0.13, BONE, rings=3, sides=6)
        mesh += _unit_panel([(h - 0.1, h - 0.05, 1.25), (h - 0.1, h - 0.4, 1.15), (h - 0.1, h - 0.05, 0.95)], team)
    elif race is Race.ELF:
        for x, y in ((-h, h - 0.1), (h, -h + 0.1)):
            mesh += _timber((x, y, 0.03), (x, y, 0.55), 0.035, (150, 122, 88), sides=5)
            mesh += r3.sphere((x, y, 0.72), 0.24, (92, 156, 98), rings=3, sides=6)
            mesh += r3.sphere((x - 0.06, y - 0.04, 0.9), 0.14, (118, 178, 112), rings=3, sides=5)
        mesh += _timber((h - 0.05, h - 0.05, 0.05), (h - 0.05, h - 0.05, 1.4), 0.03, (222, 206, 168))
        crescent = [(h - 0.05 + 0.16 * math.cos(a), h - 0.05, 1.5 + 0.16 * math.sin(a)) for a in (i * math.pi / 5 - math.pi / 2 for i in range(11))]
        mesh += _unit_panel(crescent + [(h - 0.05 + 0.08 * math.cos(a), h - 0.05, 1.5 + 0.08 * math.sin(a)) for a in (i * math.pi / 5 - math.pi / 2 for i in reversed(range(11)))], GOLD)
    elif race is Race.DWARF:
        for x, y in ((-h, h), (h, h)):
            mesh += r3.box((x, y, 0.32), (0.26, 0.26, 0.64), (104, 102, 100))
            mesh += r3.pyramid((x, y, 0.64), (0.3, 0.3), 0.16, COPPER)
            mesh += r3.box((x, y + 0.135, 0.36), (0.1, 0.01, 0.16), GOLD)
    return mesh

def _site(size: int) -> Mesh:
    """A building under construction: corner posts, beams and a pile of planks."""
    h = size / 2 - 0.2
    mesh: Mesh = []
    for x in (-h, h):
        for y in (-h, h):
            mesh += r3.box((x, y, 0.35), (0.12, 0.12, 0.7), WOOD)
    mesh += r3.box((0, -h, 0.7), (2 * h, 0.08, 0.08), WOOD) + r3.box((0, h, 0.7), (2 * h, 0.08, 0.08), WOOD)
    mesh += r3.box((-h, 0, 0.7), (0.08, 2 * h, 0.08), WOOD) + r3.box((h, 0, 0.7), (0.08, 2 * h, 0.08), WOOD)
    mesh += r3.box((0.1, 0.2, 0.1), (0.9, 0.5, 0.2), WOOD_DARK) + r3.box((-0.2, -0.3, 0.08), (0.7, 0.35, 0.16), WOOD)
    return mesh


# -- Units ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Look:
    """The colours and proportions that make one race's figures its own.  Every role keeps
    the same pose and articulation; the look supplies skin, hair, metal, cloth, and the
    stretch that makes a dwarf squat and an orc broad."""

    skin: Color
    hair: Color
    metal: Color
    metal_dark: Color
    cloth: Color  # robes, hoods and cloth that is not the team colour
    leather: Color
    stretch: tuple[float, float]  # (across, tall) applied to the whole figure


LOOKS: dict[Race, Look] = {
    Race.HUMAN: Look(SKIN, (120, 84, 50), IRON, (120, 124, 134), PLASTER, (114, 72, 41), (1.0, 1.0)),
    Race.ORC: Look((98, 142, 76), (36, 32, 34), (112, 104, 96), (66, 60, 58), (150, 58, 48), (96, 62, 40), (1.16, 1.06)),
    Race.ELF: Look((242, 224, 204), (228, 210, 138), (216, 222, 210), (150, 162, 152), (58, 122, 82), (112, 132, 92), (0.92, 1.08)),
    Race.DWARF: Look((226, 182, 146), (176, 74, 40), (198, 148, 86), (128, 94, 56), (148, 148, 156), (102, 72, 46), (1.16, 0.82)),
}
TUSK = (236, 228, 208)
BONE = (222, 214, 190)
FUR_WOLF = (112, 108, 104)
FUR_STAG = (168, 128, 82)
FUR_RAM = (214, 206, 190)
FUR_BEAR = (98, 68, 44)


def _stretch(mesh: Mesh, across: float, tall: float) -> Mesh:
    """Scale a figure horizontally and vertically about the origin (its feet stay on the ground)."""
    return [r3.Face(tuple((x * across, y * across, z * tall) for x, y, z in face.points), face.color) for face in mesh]


def _legs(frame: str, color: Color, spread: float = 0.09) -> Mesh:
    swing = {"walk1": 0.11, "walk2": -0.11}.get(frame, 0.0)
    mesh: Mesh = []
    for x, step in ((-spread, swing), (spread, -swing)):
        mesh += _unit_rod((x, 0, 0.28), (x, step, 0.08), 0.065, color)
        mesh += r3.box((x, step + 0.035, 0.065), (0.13, 0.2, 0.13), INK)
    return mesh


def _unit_rod(start: r3.Vec3, end: r3.Vec3, radius: float, color: Color, sides: int = 6) -> Mesh:
    """A solid limb, handle or strut between two joints."""
    delta = tuple(b - a for a, b in zip(start, end))
    length = math.sqrt(sum(d * d for d in delta))
    dx, dy, dz = (d / length for d in delta)
    across_length = math.hypot(dx, dz)
    u = (dz / across_length, 0.0, -dx / across_length) if across_length else (1.0, 0.0, 0.0)
    v = (dy * u[2], dz * u[0] - dx * u[2], -dy * u[0])
    return [r3.Face(tuple((start[0] + x * u[0] + y * v[0] + z * dx,
                          start[1] + x * u[1] + y * v[1] + z * dy,
                          start[2] + x * u[2] + y * v[2] + z * dz)
                         for x, y, z in face.points), face.color)
            for face in r3.cylinder((0, 0, 0), radius, length, color, sides=sides)]


def _unit_pitch(mesh: Mesh, angle: float, pivot: r3.Vec3) -> Mesh:
    """Rotate a tool around its grip, through the local forward/up plane."""
    sine, cosine = math.sin(math.radians(angle)), math.cos(math.radians(angle))
    _, py, pz = pivot
    return [r3.Face(tuple((x, py + (y - py) * cosine - (z - pz) * sine,
                          pz + (y - py) * sine + (z - pz) * cosine)
                         for x, y, z in face.points), face.color) for face in mesh]


def _unit_panel(points: list[r3.Vec3], color: Color) -> Mesh:
    """Two-sided cloth or sheet metal, visible from every unit heading."""
    return [r3.Face(tuple(points), color), r3.Face(tuple(reversed(points)), color)]


def _unit_head(center: r3.Vec3, radius: float = 0.16, race: Race = Race.HUMAN) -> Mesh:
    """A head with the race's features: orc tusks and topknot, elf ears, dwarf beard and nose."""
    look = LOOKS[race]
    x, y, z = center
    mesh = (r3.sphere(center, radius, look.skin, rings=4, sides=8)
            + r3.box((x, y + radius * 0.91, z), (0.065, 0.055, 0.07), look.skin)
            + r3.box((x, y + radius * 0.9, z + 0.045), (0.15, 0.022, 0.026), INK))
    if race is Race.ORC:
        for side in (-1, 1):
            mesh += r3.cone((x + side * radius * 0.42, y + radius * 0.82, z - radius * 0.42), 0.032, 0.13, TUSK, sides=4)
        mesh += r3.cone((x, y - 0.02, z + radius * 0.85), 0.07, 0.2, look.hair, sides=5)
    elif race is Race.ELF:
        for side in (-1, 1):
            mesh += _unit_rod((x + side * radius * 0.7, y - 0.01, z + 0.01), (x + side * radius * 1.75, y - 0.06, z + 0.12), 0.03, look.skin, sides=4)
    elif race is Race.DWARF:
        mesh += r3.box((x, y + radius * 0.98, z - 0.02), (0.085, 0.07, 0.085), look.skin)  # a big nose
        mesh += r3.sphere((x, y + radius * 0.55, z - radius * 0.7), radius * 0.62, look.hair, rings=3, sides=7)
        mesh += r3.cone((x, y + radius * 0.6, z - radius * 0.9), radius * 0.5, -radius * 1.5, look.hair, sides=6)
        mesh += r3.box((x, y + radius * 0.95, z - radius * 0.32), (0.2, 0.05, 0.05), look.hair)  # moustache
    return mesh


def _body(tunic: Color, frame: str, body_r: float = 0.21, body_h: float = 0.42, *, include_legs: bool = True, race: Race = Race.HUMAN) -> Mesh:
    bob = 0.02 if frame == "walk1" else 0.0
    return (
        (_legs(frame, (72, 62, 58)) if include_legs else [])
        + r3.cylinder((0, 0, 0.23 + bob), body_r, body_h, tunic, sides=8)
        + r3.cylinder((0, 0, 0.33 + bob), body_r + 0.01, 0.055, WOOD_DARK, sides=8)
        + _unit_head((0, 0, 0.23 + bob + body_h + 0.14), race=race)
    )


def _helm(z: float, race: Race, team: Color, radius: float = 0.19) -> Mesh:
    """Headgear at a head's top: a conical helm, a spiked cap, a winged leaf helm or a nasal helm with horns."""
    look = LOOKS[race]
    if race is Race.HUMAN:
        return (r3.cylinder((0, 0, z), radius, 0.17, look.metal, sides=8) + r3.cone((0, 0, z + 0.17), radius, 0.1, look.metal, sides=8)
                + r3.box((0, 0.181, z + 0.075), (0.28, 0.04, 0.048), INK) + r3.box((0, 0.211, z + 0.035), (0.045, 0.035, 0.17), look.metal)
                + r3.box((0, 0, z + 0.265), (0.07, 0.29, 0.09), team))
    if race is Race.ORC:
        mesh = r3.cylinder((0, 0, z - 0.03), radius * 1.04, 0.13, look.metal_dark, sides=7)
        mesh += r3.sphere((0, 0, z + 0.1), radius * 1.02, look.metal_dark, rings=3, sides=7)
        for x in (-0.16, 0.16):
            mesh += r3.cone((x, 0.02, z + 0.1), 0.045, 0.19, BONE, sides=4)
        return mesh + r3.cone((0, 0, z + 0.27), 0.04, 0.12, look.metal, sides=4)
    if race is Race.ELF:
        mesh = r3.cylinder((0, 0, z), radius * 0.95, 0.12, look.metal, sides=8)
        mesh += r3.cone((0, 0.02, z + 0.12), radius * 0.95, 0.24, look.metal, sides=8)
        for side in (-1, 1):
            mesh += _unit_panel([(side * 0.17, 0.0, z + 0.1), (side * 0.36, -0.12, z + 0.3), (side * 0.18, -0.02, z + 0.22)], look.metal)
        return mesh + r3.box((0, 0.17, z + 0.06), (0.05, 0.03, 0.14), team)
    mesh = r3.sphere((0, 0, z + 0.05), radius * 1.05, look.metal, rings=3, sides=8)
    mesh += r3.cylinder((0, 0, z - 0.02), radius * 1.08, 0.07, look.metal_dark, sides=8)
    mesh += r3.box((0, 0.2, z + 0.02), (0.045, 0.03, 0.17), look.metal_dark)  # nasal
    for side in (-1, 1):
        mesh += _unit_rod((side * 0.17, 0.02, z + 0.12), (side * 0.3, -0.05, z + 0.22), 0.035, BONE, sides=4)
    return mesh + r3.box((0, 0, z + 0.2), (0.05, 0.22, 0.07), team)


def _sword(frame: str, race: Race = Race.HUMAN) -> Mesh:
    """The race's hand weapon in the right hand: sword, cleaver, curved blade or axe."""
    look = LOOKS[race]
    grip = (0.32, 0.13, 0.5)
    handle = _unit_rod((0.32, 0.13, 0.4), (0.32, 0.13, 0.55), 0.043, WOOD_DARK)
    if race is Race.ORC:
        blade = (_unit_rod((0.32, 0.13, 0.55), (0.32, 0.13, 1.12), 0.04, WOOD_DARK)
                 + _unit_panel([(0.32, 0.16, 0.78), (0.32, 0.5, 0.86), (0.32, 0.46, 1.2), (0.32, 0.16, 1.14)], look.metal)
                 + r3.cone((0.32, 0.1, 1.12), 0.045, 0.12, look.metal, sides=4))
    elif race is Race.ELF:
        blade = (r3.box((0.32, 0.13, 0.57), (0.22, 0.07, 0.05), look.hair)
                 + _unit_panel([(0.32, 0.1, 0.6), (0.32, 0.17, 0.6), (0.32, 0.3, 1.0), (0.32, 0.2, 1.24), (0.32, 0.08, 1.0)], look.metal))
    elif race is Race.DWARF:
        blade = (_unit_rod((0.32, 0.13, 0.55), (0.32, 0.13, 1.05), 0.04, WOOD)
                 + r3.box((0.32, 0.13, 0.98), (0.09, 0.14, 0.13), look.metal_dark)
                 + _unit_panel([(0.26, 0.2, 0.9), (0.26, 0.42, 0.84), (0.26, 0.42, 1.14), (0.26, 0.2, 1.08)], look.metal)
                 + _unit_panel([(0.38, 0.2, 0.9), (0.38, 0.42, 0.84), (0.38, 0.42, 1.14), (0.38, 0.2, 1.08)], look.metal))
    else:
        blade = (r3.box((0.32, 0.13, 0.85), (0.08, 0.055, 0.59), look.metal) + r3.pyramid((0.32, 0.13, 1.145), (0.08, 0.055), 0.14, look.metal)
                 + r3.box((0.32, 0.13, 0.57), (0.27, 0.09, 0.06), GOLD))
    return _unit_pitch(blade + handle, -85 if frame == "attack" else -12, grip)


_WORKER_SWING = {"chop1": 35, "chop2": -28, "chop3": -96, "chop4": -48, "attack": -96}
_WORKER_LEAN = {"chop1": 12, "chop2": -5, "chop3": -18, "chop4": -6}
_WORKER_HIP = (0.0, 0.0, 0.26)
_WORKER_GRIP = (0.29, 0.16, 0.55)
_WORKER_AXE_EDGE = ((0.29, 0.42, 0.99), (0.29, 0.4, 1.21))


def _worker_axe_angle(frame: str) -> float:
    # Counter the torso bend so the blade keeps its intended cutting direction.
    return _WORKER_SWING.get(frame, -12) - _WORKER_LEAN.get(frame, 0)


def _worker_axe(frame: str, race: Race = Race.HUMAN) -> Mesh:
    # The grip follows the torso; the head sweeps from behind the shoulder into the tree.
    # chop1 = raised, chop2 = fast downswing, chop3 = contact, chop4 = recovery.
    metal = LOOKS[race].metal
    axe = _unit_rod((0.29, 0.16, 0.35), (0.29, 0.16, 1.17), 0.035, WOOD)
    # Broad wedge and bright cutting edge are readable even at normal zoom.
    axe += r3.box((0.29, 0.17, 1.1), (0.105, 0.16, 0.14), WOOD_DARK)
    for x in (0.235, 0.345):
        axe += _unit_panel([(x, 0.19, 1.16), (x, 0.41, 1.22),
                            (x, 0.43, 0.98), (x, 0.19, 1.03)], metal)
    axe += _unit_rod(*_WORKER_AXE_EDGE, 0.045, (228, 234, 242))
    return _unit_pitch(axe, _worker_axe_angle(frame), _WORKER_GRIP)


def _shield(x: float, y: float, z: float, team: Color, size: float = 1.0, race: Race = Race.HUMAN) -> Mesh:
    """A heater shield; orcs carry a hide-bound round shield, dwarves a bossed round shield, elves a leaf-shaped buckler."""
    look = LOOKS[race]
    mesh: Mesh = []
    if race in (Race.ORC, Race.DWARF):
        radius = 0.3 * size if race is Race.ORC else 0.27 * size
        for offset, factor, color in ((0, 1.0, look.metal_dark if race is Race.ORC else look.metal), (0.025, 0.78, team)):
            ring = [(x + radius * factor * math.cos(a), y + offset, z + radius * factor * math.sin(a)) for a in (i * math.tau / 8 for i in range(8))]
            mesh += _unit_panel(ring, color)
        mesh += r3.sphere((x, y + 0.04, z), 0.07 * size, look.metal, rings=3, sides=6)
        if race is Race.ORC:
            for a in (0.4, 2.5, 4.4):
                mesh += r3.cone((x + radius * 0.75 * math.cos(a), y + 0.03, z + radius * 0.75 * math.sin(a)), 0.03, 0.09, BONE, sides=4)
        return mesh
    if race is Race.ELF:
        outline = [(-0.16, 0.3), (0.16, 0.3), (0.2, 0.0), (0, -0.36), (-0.2, 0.0)]
        for offset, factor, color in ((0, 1.0, look.metal), (0.025, 0.7, team)):
            mesh += _unit_panel([(x + dx * size * factor, y + offset, z + dz * size * factor) for dx, dz in outline], color)
        return mesh + r3.box((x, y + 0.035, z + 0.02), (0.045 * size, 0.06, 0.3 * size), look.hair)
    outline = [(-0.23, 0.26), (0.23, 0.26), (0.24, -0.05), (0, -0.34), (-0.24, -0.05)]
    for offset, factor, color in ((0, 1.0, look.metal), (0.025, 0.8, team)):
        mesh += _unit_panel([(x + dx * size * factor, y + offset, z + dz * size * factor)
                             for dx, dz in outline], color)
    mesh += r3.box((x, y + 0.035, z - 0.015), (0.055 * size, 0.06, 0.34 * size), GOLD)
    mesh += r3.box((x, y + 0.04, z + 0.075), (0.23 * size, 0.06, 0.055 * size), GOLD)
    return mesh


def _mount(frame: str, heavy: bool, team: Color, race: Race = Race.HUMAN) -> Mesh:
    """The race's steed on the same four-legged rig: horse, wolf, deer or stag, ram or bear."""
    swing = {"walk1": 0.12, "walk2": -0.12}.get(frame, 0.0)
    if race is Race.HUMAN:
        coat = (78, 65, 65) if heavy else (174, 123, 68)
    elif race is Race.ORC:
        coat = (74, 70, 68) if heavy else FUR_WOLF
    elif race is Race.ELF:
        coat = FUR_STAG if heavy else (188, 150, 100)
    else:
        coat = FUR_BEAR if heavy else FUR_RAM
    size = 1.08 if heavy else 0.92
    body_h, head_z = (0.48, 0.83), (0.48, 0.83)
    if race is Race.ORC:
        body_h, head_z = (0.42, 0.62), (0.42, 0.62)  # a wolf runs low
    elif race is Race.DWARF and heavy:
        body_h, head_z = (0.5, 0.74), (0.5, 0.74)
    bz, hz = body_h[0], head_z[1]
    mesh = _shadow(0.44)
    for x, y in ((-0.17, -0.28), (0.17, -0.28), (-0.17, 0.29), (0.17, 0.29)):
        stride = swing if (x < 0) == (y < 0) else -swing
        mesh += _unit_rod((x, y, bz), (x, y + stride, 0.1), 0.065 if race is not Race.DWARF else 0.085, coat)
        mesh += r3.box((x, y + stride + 0.025, 0.065), (0.125, 0.16, 0.13), INK)
    if race is Race.DWARF and heavy:
        mesh += r3.sphere((0, -0.025, bz + 0.05), 0.42, coat, rings=4, sides=8)  # a bear's bulk
        mesh += r3.box((0, -0.025, bz), (0.46, 0.8, 0.34), coat)
    else:
        mesh += r3.box((0, -0.025, bz), (0.43, 0.78, 0.32), coat)
    if race is Race.ORC:
        mesh += _unit_rod((0, 0.25, bz), (0, 0.42, bz + 0.22), 0.13, coat)
        mesh += r3.box((0, 0.5, hz), (0.2, 0.34, 0.2), coat)
        mesh += r3.box((0, 0.7, hz - 0.05), (0.15, 0.22, 0.11), darker(coat, 0.7))  # long snout
        for side in (-1, 1):
            mesh += r3.cone((side * 0.07, 0.37, hz + 0.1), 0.04, 0.14, coat, sides=4)  # pricked ears
            mesh += r3.cone((side * 0.045, 0.79, hz - 0.13), 0.018, -0.06, TUSK, sides=4)  # fangs
        mesh += _unit_rod((0, -0.38, bz + 0.1), (0, -0.66, bz + 0.05), 0.07, coat)  # a straight tail
    elif race is Race.ELF:
        mesh += _unit_rod((0, 0.25, bz), (0, 0.42, hz + 0.05), 0.1, coat)
        mesh += r3.box((0, 0.5, hz + 0.02), (0.18, 0.34, 0.19), coat)
        mesh += r3.box((0, 0.66, hz - 0.03), (0.14, 0.12, 0.11), darker(coat, 0.65))
        for side in (-1, 1):
            mesh += r3.cone((side * 0.085, 0.38, hz + 0.1), 0.04, 0.15, coat, sides=4)
            if heavy:  # antlers
                base = (side * 0.07, 0.4, hz + 0.12)
                for tip in ((side * 0.28, 0.32, hz + 0.5), (side * 0.16, 0.24, hz + 0.44), (side * 0.36, 0.42, hz + 0.34)):
                    mesh += _unit_rod(base, tip, 0.022, BONE, sides=4)
        mesh += _unit_rod((0, -0.36, bz + 0.06), (0, -0.48, bz - 0.02), 0.04, PLASTER)
    elif race is Race.DWARF:
        if heavy:
            mesh += _unit_rod((0, 0.25, bz + 0.05), (0, 0.4, hz), 0.17, coat)
            mesh += r3.box((0, 0.52, hz), (0.28, 0.34, 0.26), coat)
            mesh += r3.box((0, 0.7, hz - 0.04), (0.16, 0.14, 0.13), darker(coat, 0.7))
            for side in (-1, 1):
                mesh += r3.sphere((side * 0.12, 0.4, hz + 0.15), 0.05, coat, rings=3, sides=5)  # round ears
        else:
            mesh += _unit_rod((0, 0.25, bz), (0, 0.4, hz - 0.02), 0.13, coat)
            mesh += r3.box((0, 0.5, hz - 0.02), (0.22, 0.32, 0.22), coat)
            mesh += r3.box((0, 0.68, hz - 0.08), (0.16, 0.12, 0.12), darker(coat, 0.75))
            for side in (-1, 1):  # curled horns
                for i, angle in enumerate((0.0, 1.0, 2.0, 3.0)):
                    x, z = side * (0.13 + 0.06 * math.cos(angle)), hz + 0.08 + 0.09 * math.sin(angle) - 0.03 * i
                    mesh += r3.sphere((x, 0.42 - 0.03 * i, z), 0.045 - 0.006 * i, BONE, rings=3, sides=5)
        mesh += _unit_rod((0, -0.36, bz + 0.02), (0, -0.46, bz - 0.06), 0.05, coat)
    else:
        mesh += _unit_rod((0, 0.25, bz), (0, 0.4, 0.87), 0.135, coat)
        mesh += r3.box((0, 0.49, 0.83), (0.22, 0.36, 0.21), coat)
        mesh += r3.box((0, 0.66, 0.79), (0.2, 0.12, 0.13), darker(coat, 0.65))
        for x in (-0.08, 0.08):
            mesh += r3.cone((x, 0.39, 0.92), 0.05, 0.16, coat, sides=4)
        mesh += _unit_rod((0, -0.36, 0.54), (0, -0.57, 0.22), 0.065, INK)
        mesh += _unit_rod((0, 0.28, 0.59), (0, 0.31, 0.94), 0.065, INK)
    mesh += r3.box((0, -0.07, bz + 0.18), (0.47, 0.42, 0.07), WOOD_DARK)  # saddle
    # Reins and bridle break up the head and point out its facing.
    mesh += r3.box((0, 0.56, hz + 0.01), (0.24, 0.035, 0.23), WOOD_DARK)
    for x in (-0.13, 0.13):
        mesh += _unit_rod((x, 0.57, hz + 0.03), (x, -0.02, hz + 0.03), 0.014, WOOD_DARK)
    look = LOOKS[race]
    if heavy:
        for x in (-0.235, 0.235):
            mesh += _unit_panel([(x, -0.37, bz + 0.14), (x, 0.27, bz + 0.14),
                                 (x, 0.26, bz - 0.22), (x, 0.02, bz - 0.16), (x, -0.37, bz - 0.22)], team)
        mesh += r3.box((0, 0.53, hz + 0.12), (0.22, 0.29, 0.055), look.metal)
        mesh += r3.box((0, 0.29, bz + 0.2), (0.46, 0.2, 0.11), look.metal)
    else:
        mesh += r3.box((0, -0.07, bz + 0.135), (0.46, 0.44, 0.085), team)
    return r3.scale(mesh, size)


UNIT_SCALE = 1.4  # figures are modelled at chibi size and blown up so they read from the usual zoom


def _unit(unit_type: UnitType, player: int, frame: str, carrying: Resource | None, race: Race = Race.HUMAN) -> Mesh:
    mesh = _unit_mesh(unit_type, player, frame, carrying, race)
    if unit_type is not UnitType.CATAPULT:
        mesh = _stretch(mesh, *LOOKS[race].stretch)
    return r3.scale(mesh, UNIT_SCALE)


def _worker(player: int, frame: str, carrying: Resource | None, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    planted = _shadow(0.3) + _legs(frame, (72, 62, 58))
    shirt = look.skin if race is Race.ORC else (186, 159, 106) if race is Race.HUMAN else look.cloth if race is Race.ELF else (158, 132, 96)
    mesh = _body(shirt, frame, body_r=0.185, body_h=0.36, include_legs=False, race=race)
    head_z = 0.23 + 0.36 + 0.14
    if race is Race.HUMAN:
        # Broad straw hat, team shirt sleeves and a leather carpenter's apron.
        mesh += r3.cylinder((0, 0, 0.88), 0.28, 0.045, THATCH, sides=10)
        mesh += r3.cone((0, 0, 0.92), 0.17, 0.16, THATCH, sides=8)
        mesh += r3.cylinder((0, 0, 0.92), 0.174, 0.035, team, sides=8)
    elif race is Race.ORC:
        mesh += r3.box((0, 0.183, 0.42), (0.28, 0.045, 0.2), team)  # a team loincloth over bare green
        mesh += r3.box((0, 0, 0.62), (0.2, 0.4, 0.05), look.leather)  # a rope belt
    elif race is Race.ELF:
        mesh += r3.cone((0, -0.02, head_z - 0.05), 0.2, 0.26, team, sides=8)  # a hood
        mesh += r3.cylinder((0, -0.02, head_z - 0.06), 0.205, 0.04, darker(team, 0.75), sides=8)
    else:
        mesh += r3.sphere((0, 0, head_z + 0.06), 0.185, look.metal_dark, rings=3, sides=8)  # a miner's helmet with a lamp
        mesh += r3.cylinder((0, 0.17, head_z + 0.1), 0.05, 0.05, GOLD, sides=6)
        mesh += r3.box((0, 0, head_z + 0.08), (0.05, 0.2, 0.07), team)
    if race is not Race.ORC:
        mesh += r3.box((0, 0.183, 0.42), (0.25, 0.045, 0.34), look.leather)
        mesh += r3.box((0, 0.212, 0.36), (0.15, 0.025, 0.09), (159, 105, 57))
        mesh += r3.box((0, 0.215, 0.55), (0.065, 0.025, 0.045), GOLD)
    for x in (-0.21, 0.21):
        mesh += _unit_rod((x, 0, 0.55), (x * 1.15, 0.08, 0.45), 0.075, look.skin if race is Race.ORC else team)
    mesh += _unit_rod((0.24, 0.08, 0.45), (0.29, 0.16, 0.55), 0.05, look.skin)
    if carrying is Resource.GOLD:
        mesh += r3.sphere((-0.28, 0.13, 0.48), 0.2, (113, 80, 48), rings=4, sides=8)
        mesh += r3.cone((-0.28, 0.13, 0.62), 0.15, 0.11, GOLD, sides=5)
        mesh += r3.cylinder((-0.28, 0.13, 0.65), 0.07, 0.045, WOOD_DARK, sides=6)
    elif carrying is Resource.LUMBER:
        for y, z in ((-0.05, 0.98), (0.12, 0.98), (0.035, 1.12)):
            mesh += _unit_rod((-0.48, y, z), (0.48, y, z), 0.095, TRUNK)
            mesh += _unit_rod((0.478, y, z), (0.495, y, z), 0.072, THATCH)
        mesh += r3.box((0.12, 0.035, 1.06), (0.05, 0.37, 0.32), WOOD_DARK)
    else:
        mesh += _worker_axe(frame, race)
        angle = math.radians(_worker_axe_angle(frame))
        gx, gy, gz = _WORKER_GRIP
        lower_grip = (gx, gy + 0.12 * math.sin(angle), gz - 0.12 * math.cos(angle))
        mesh += _unit_rod((-0.24, 0.08, 0.45), lower_grip, 0.045, look.skin)
    if carrying is None and frame in _WORKER_LEAN:
        mesh = _unit_pitch(mesh, _WORKER_LEAN[frame], _WORKER_HIP)
    return planted + mesh


def _footman(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    mesh = _shadow(0.34) + _body(team, frame, body_r=0.23, race=race)
    mesh += r3.box((0, 0.18, 0.59), (0.34, 0.12, 0.28), look.metal)
    for x in (-0.255, 0.255):
        if race is Race.ORC:
            mesh += r3.box((x, 0, 0.66), (0.16, 0.18, 0.1), look.metal_dark)
            mesh += r3.cone((x * 1.15, 0, 0.71), 0.045, 0.16, BONE, sides=4)  # a spiked pauldron
        else:
            mesh += r3.sphere((x, 0, 0.66), 0.115, look.metal, rings=3, sides=6)
        mesh += _unit_rod((x, 0, 0.6), (x * 1.2, 0.13, 0.45), 0.065, look.metal if race is not Race.ORC else look.skin)
    mesh += _helm(0.79, race, team)
    return mesh + _shield(-0.32, 0.21, 0.48, team, race=race) + _sword(frame, race)


def _archer(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    green = look.cloth if race is not Race.HUMAN else (52, 88, 67)
    mesh = _shadow(0.3) + _body(team, frame, body_r=0.17, body_h=0.36, race=race)
    mesh += _unit_panel([(-0.18, -0.1, 0.7), (0.18, -0.1, 0.7),
                         (0.27, -0.28, 0.2), (-0.25, -0.28, 0.2)], green)
    if race is Race.ORC:
        mesh += r3.box((0, -0.12, 0.62), (0.28, 0.12, 0.34), look.leather)  # a quiver of throwing axes on the back
        for x in (-0.09, 0.0, 0.09):
            mesh += _unit_rod((x, -0.14, 0.75), (x, -0.16, 1.0), 0.02, WOOD)
            mesh += r3.box((x, -0.14, 0.99), (0.06, 0.05, 0.08), look.metal)
        mesh += _helm(0.79, race, team)
        raised = frame == "attack"
        hand = (0.34, 0.36 if raised else 0.14, 1.05 if raised else 0.6)
        mesh += _unit_rod((0.17, 0, 0.58), hand, 0.05, look.skin)
        axe = _unit_rod(hand, (hand[0], hand[1] + 0.04, hand[2] + 0.36), 0.025, WOOD)
        axe += _unit_panel([(hand[0], hand[1] + 0.02, hand[2] + 0.3), (hand[0], hand[1] + 0.22, hand[2] + 0.26),
                            (hand[0], hand[1] + 0.2, hand[2] + 0.44), (hand[0], hand[1] + 0.02, hand[2] + 0.4)], look.metal)
        mesh += axe
        mesh += _unit_rod((-0.17, 0, 0.57), (-0.3, 0.14, 0.44), 0.048, look.skin)
        return mesh
    mesh += r3.sphere((0, -0.055, 0.81), 0.2, green, rings=4, sides=8)
    mesh += r3.cone((0, -0.04, 0.93), 0.14, 0.18 if race is not Race.ELF else 0.3, green, sides=6)
    mesh += _unit_head((0, 0.075, 0.76), 0.13, race=race)
    mesh += _unit_rod((-0.19, -0.23, 0.35), (-0.27, -0.23, 0.79), 0.085, WOOD_DARK)
    for x in (-0.32, -0.26, -0.2):
        mesh += _unit_rod((x, -0.23, 0.67), (x - 0.03, -0.23, 1.03), 0.014, THATCH)
        mesh += r3.box((x - 0.03, -0.23, 0.97), (0.05, 0.05, 0.09), PLASTER)
    bow_y = 0.36 if frame == "attack" else 0.18
    if race is Race.DWARF:
        # A crossbow held level: a stock, a short steel bow and a bolt on top.
        stock = (0.3, bow_y + 0.05, 0.62)
        mesh += _unit_rod((stock[0], stock[1] - 0.25, stock[2]), (stock[0], stock[1] + 0.35, stock[2]), 0.035, WOOD_DARK)
        mesh += _unit_rod((stock[0] - 0.28, stock[1] + 0.3, stock[2]), (stock[0] + 0.28, stock[1] + 0.34, stock[2]), 0.025, look.metal)
        mesh += _unit_rod((stock[0] - 0.28, stock[1] + 0.3, stock[2]), (stock[0], stock[1] - 0.05, stock[2]), 0.01, PLASTER)
        mesh += _unit_rod((stock[0] + 0.28, stock[1] + 0.34, stock[2]), (stock[0], stock[1] - 0.05, stock[2]), 0.01, PLASTER)
        mesh += _unit_rod((0.17, 0, 0.58), (stock[0], stock[1] - 0.1, stock[2]), 0.048, look.skin)
        mesh += _unit_rod((-0.17, 0, 0.57), (stock[0] - 0.02, stock[1] + 0.15, stock[2] - 0.02), 0.048, look.skin)
        if frame == "attack":
            mesh += _unit_rod((stock[0], stock[1] - 0.05, stock[2] + 0.03), (stock[0], stock[1] + 0.5, stock[2] + 0.03), 0.015, THATCH)
        return mesh
    tall = 1.28 if race is Race.ELF else 1.12
    path = [(0.32, bow_y, 0.12), (0.32, bow_y + 0.17, 0.35),
            (0.32, bow_y + 0.23, 0.64), (0.32, bow_y + 0.17, 0.94), (0.32, bow_y, tall)]
    for start, end in zip(path, path[1:]):
        mesh += _unit_rod(start, end, 0.035, (201, 145, 76) if race is Race.HUMAN else (222, 206, 168))
    draw_y = bow_y - 0.27 if frame == "attack" else bow_y
    mesh += _unit_rod(path[0], (0.32, draw_y, 0.64), 0.01, PLASTER)
    mesh += _unit_rod((0.32, draw_y, 0.64), path[-1], 0.01, PLASTER)
    mesh += _unit_rod((0.17, 0, 0.58), (0.32, bow_y + 0.2, 0.64), 0.048, look.skin)
    mesh += _unit_rod((-0.17, 0, 0.57), (0.32, draw_y, 0.64), 0.048, look.skin)
    if frame == "attack":
        mesh += _unit_rod((0.32, draw_y, 0.64), (0.32, bow_y + 0.66, 0.64), 0.018, THATCH)
        mesh += r3.box((0.32, bow_y + 0.64, 0.64), (0.055, 0.13, 0.045), look.metal)
    return mesh


def _knight(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    trim = darker(team, 0.7)
    if race is Race.ORC:
        # An ogre: two heads, a club, no mount and no manners.
        mesh = _shadow(0.42) + _legs(frame, look.skin, spread=0.16)
        mesh += r3.cylinder((0, 0, 0.26), 0.34, 0.62, look.skin, sides=8)
        mesh += r3.box((0, 0.2, 0.46), (0.5, 0.2, 0.3), team)  # a team-dyed loincloth and belt
        mesh += r3.cylinder((0, 0, 0.45), 0.35, 0.07, look.leather, sides=8)
        for x in (-0.36, 0.36):
            mesh += r3.sphere((x, 0, 0.82), 0.14, look.skin, rings=3, sides=6)
        mesh += _unit_head((-0.17, 0.02, 1.02), 0.15, race=Race.ORC)
        mesh += _unit_head((0.17, 0.02, 1.0), 0.14, race=Race.ORC)
        mesh += r3.box((-0.17, 0.02, 1.16), (0.18, 0.18, 0.06), look.metal_dark)
        mesh += _unit_rod((-0.34, 0, 0.78), (-0.5, 0.2, 0.6), 0.09, look.skin)
        grip = (0.44, 0.16, 0.66)
        mesh += _unit_rod((0.34, 0, 0.78), grip, 0.09, look.skin)
        club = _unit_rod((0.44, 0.16, 0.5), (0.44, 0.16, 1.2), 0.05, WOOD_DARK)
        club += r3.sphere((0.44, 0.16, 1.24), 0.17, WOOD_DARK, rings=3, sides=7)
        for a in (0.3, 1.6, 2.9, 4.2, 5.5):
            club += r3.cone((0.44 + 0.15 * math.cos(a), 0.16 + 0.15 * math.sin(a), 1.24), 0.03, 0.1, look.metal, sides=4)
        mesh += _unit_pitch(club, -95 if frame == "attack" else -20, grip)
        return mesh
    mesh = _mount(frame, True, team, race)
    rider_z = 0.73 if race is not Race.DWARF else 0.68
    mesh += r3.cylinder((0, -0.11, rider_z), 0.21, 0.34, look.metal, sides=8)
    mesh += _unit_panel([(-0.21, -0.19, rider_z + 0.34), (0.21, -0.19, rider_z + 0.34),
                         (0.28, -0.45, rider_z - 0.19), (-0.28, -0.45, rider_z - 0.19)], trim)
    for x in (-0.24, 0.24):
        mesh += _unit_rod((x, -0.1, rider_z + 0.03), (x * 1.12, 0.03, rider_z - 0.26), 0.075, look.metal)
        mesh += r3.sphere((x, -0.09, rider_z + 0.29), 0.13, look.metal, rings=3, sides=6)
    head = (0, -0.11, rider_z + 0.4)
    if race is Race.DWARF:
        mesh += _unit_head((head[0], head[1], head[2] + 0.12), 0.16, race=race)
        mesh += _shift(_helm(0.0, race, team), (0, -0.11, rider_z + 0.6))
    else:
        mesh += r3.cylinder(head, 0.18, 0.24, look.metal, sides=8)
        mesh += r3.cone((head[0], head[1], head[2] + 0.24), 0.18, 0.11 if race is Race.HUMAN else 0.2, look.metal, sides=8)
        mesh += r3.box((0, 0.065, rider_z + 0.54), (0.29, 0.05, 0.045), INK)
        mesh += r3.box((0, 0.075, rider_z + 0.45), (0.045, 0.05, 0.22), GOLD if race is Race.HUMAN else look.hair)
        if race is Race.ELF:
            for side in (-1, 1):
                mesh += _unit_panel([(side * 0.17, -0.11, rider_z + 0.5), (side * 0.38, -0.25, rider_z + 0.72), (side * 0.18, -0.13, rider_z + 0.63)], look.metal)
        else:
            mesh += _unit_rod((0, -0.1, rider_z + 0.72), (0, -0.31, rider_z + 0.89), 0.1, team)
            mesh += r3.cone((0, -0.32, rider_z + 0.83), 0.13, 0.14, team, sides=6)
    mesh += _shield(-0.33, 0.11, rider_z + 0.21, team, 0.92, race=race)
    grip = (0.34, 0.05, rider_z + 0.27)
    if race is Race.DWARF:
        lance = _unit_rod((0.34, 0.05, rider_z), (0.34, 0.05, rider_z + 0.95), 0.036, WOOD)
        lance += r3.box((0.34, 0.05, rider_z + 0.9), (0.12, 0.22, 0.16), look.metal)  # a war hammer's head
        lance += r3.cone((0.34, 0.17, rider_z + 0.9), 0.05, 0.14, look.metal_dark, sides=4)
    else:
        lance = _unit_rod((0.34, 0.05, rider_z - 0.06), (0.34, 0.05, rider_z + 1.19), 0.036, THATCH if race is Race.HUMAN else (222, 206, 168))
        lance += r3.cone((0.34, 0.05, rider_z + 1.17), 0.085, 0.2, look.metal, sides=4)
        lance += _unit_panel([(0.34, 0.05, rider_z + 1.1), (0.34, -0.29, rider_z + 0.97), (0.34, 0.05, rider_z + 0.86)], team)
    mesh += _unit_pitch(lance, -82 if frame == "attack" else -38, grip)
    return mesh


def _shift(mesh: Mesh, offset: r3.Vec3) -> Mesh:
    ox, oy, oz = offset
    return [r3.Face(tuple((x + ox, y + oy, z + oz) for x, y, z in face.points), face.color) for face in mesh]


def _scout(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    mesh = _mount(frame, False, team, race)
    rider_z = 0.63 if race is not Race.ORC else 0.5
    mesh += r3.cylinder((0, -0.1, rider_z), 0.15, 0.29, look.leather, sides=6)
    mesh += _unit_panel([(-0.18, -0.16, rider_z + 0.29), (0.18, -0.16, rider_z + 0.29),
                         (0.2, -0.57, rider_z - 0.09), (0, -0.48, rider_z - 0.04), (-0.2, -0.57, rider_z - 0.09)], team)
    mesh += _unit_head((0, -0.085, rider_z + 0.43), 0.14, race=race)
    if race is Race.HUMAN:
        mesh += r3.cone((0, -0.095, rider_z + 0.52), 0.2, 0.13, (73, 93, 64), sides=6)
        mesh += _unit_rod((-0.1, -0.11, rider_z + 0.58), (-0.16, -0.23, rider_z + 0.8), 0.032, PLASTER)
    elif race is Race.ORC:
        mesh += r3.sphere((0, -0.09, rider_z + 0.52), 0.15, look.metal_dark, rings=3, sides=6)
        mesh += r3.cone((0, -0.09, rider_z + 0.62), 0.04, 0.14, BONE, sides=4)
    elif race is Race.ELF:
        mesh += r3.cone((0, -0.1, rider_z + 0.5), 0.17, 0.25, look.cloth, sides=7)
    else:
        mesh += r3.sphere((0, -0.09, rider_z + 0.5), 0.16, look.metal, rings=3, sides=7)
    for x in (-0.19, 0.19):
        mesh += _unit_rod((x, -0.06, rider_z + 0.11), (x * 1.15, 0.06, rider_z - 0.2), 0.058, WOOD_DARK)
        mesh += _unit_rod((x, -0.08, rider_z + 0.23), (x, 0.12, rider_z + 0.19), 0.045, look.skin)
    grip = (0.27, 0.07, rider_z + 0.27)
    spear = _unit_rod((0.27, 0.07, rider_z - 0.08), (0.27, 0.07, rider_z + 1.02), 0.024, WOOD)
    spear += r3.cone((0.27, 0.07, rider_z + 1.0), 0.06, 0.18, look.metal, sides=4)
    if race is Race.ORC:
        spear += r3.cone((0.27, 0.07, rider_z + 0.85), 0.05, -0.1, BONE, sides=4)
    mesh += _unit_pitch(spear, -84 if frame == "attack" else -8, grip)
    return mesh


def _siege(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    wood, wood_dark = (WOOD, WOOD_DARK) if race is not Race.ELF else ((196, 186, 150), (150, 140, 104))
    mesh = _shadow(0.51, 0.05, 0.03)
    for x in (-0.27, 0.27):
        mesh += r3.box((x, 0, 0.27), (0.11, 0.96, 0.13), wood_dark)
        mesh += _unit_rod((x, -0.38, 0.3), (x, -0.04, 0.83), 0.055, wood)
        mesh += _unit_rod((x, 0.37, 0.3), (x, -0.04, 0.83), 0.055, wood)
    for y in (-0.32, 0.32):
        mesh += _unit_rod((-0.5, y, 0.23), (0.5, y, 0.23), 0.055, look.metal)
    wheel_turn = {"walk1": 20, "walk2": -20}.get(frame, 0)
    for x in (-0.44, 0.44):
        for y in (-0.32, 0.32):
            mesh += _unit_rod((x - 0.05, y, 0.23), (x + 0.05, y, 0.23), 0.225, INK, sides=10)
            outer = x + (0.055 if x > 0 else -0.055)
            mesh += _unit_rod((x, y, 0.23), (outer, y, 0.23), 0.18, wood_dark, sides=10)
            for degrees in range(wheel_turn, wheel_turn + 360, 60):
                angle = math.radians(degrees)
                mesh += _unit_rod((outer, y, 0.23),
                                  (outer, y + 0.18 * math.cos(angle), 0.23 + 0.18 * math.sin(angle)), 0.019, THATCH)
            mesh += _unit_rod((x, y, 0.23), (outer * 1.045, y, 0.23), 0.055, look.metal)
    mesh += _unit_rod((-0.34, -0.04, 0.8), (0.34, -0.04, 0.8), 0.08, look.metal)
    if race is Race.DWARF:
        # A mortar: a short iron barrel on the chassis, tipped back to lob.
        pivot = (0, -0.04, 0.6)
        barrel = _unit_rod((0, -0.04, 0.45), (0, -0.04, 1.05), 0.17, look.metal_dark, sides=8)
        barrel += _unit_rod((0, -0.04, 1.0), (0, -0.04, 1.08), 0.19, look.metal, sides=8)
        barrel += _unit_rod((0, -0.04, 0.5), (0, -0.04, 0.58), 0.19, look.metal, sides=8)
        barrel += r3.cylinder((0, -0.04, 1.06), 0.11, 0.03, INK, sides=8)
        mesh += _unit_pitch(barrel, -20 if frame == "attack" else 42, pivot)
        for x in (-0.2, 0.2):
            mesh += r3.sphere((x, 0.36, 0.45), 0.09, BOULDER, rings=3, sides=6)  # shot
        mesh += r3.box((0, 0.29, 0.35), (0.58, 0.13, 0.15), wood)
    elif race is Race.ELF:
        # A ballista: a great horizontal bow on the front and a bolt in the groove.
        pivot = (0, -0.04, 0.65)
        arm = _unit_rod((0, -0.5, 0.72), (0, 0.42, 0.72), 0.05, wood)
        for side in (-1, 1):
            arm += _unit_rod((0, 0.42, 0.72), (side * 0.62, 0.3, 0.72), 0.03, wood_dark)
            arm += _unit_rod((side * 0.62, 0.3, 0.72), (0, 0.02 if frame == "attack" else -0.16, 0.72), 0.012, PLASTER)
        arm += _unit_rod((0, -0.16, 0.75), (0, 0.6, 0.75), 0.02, wood_dark)
        arm += _unit_rod((0, 0.58, 0.75), (0, 0.74, 0.75), 0.045, look.metal, sides=4)  # the bolt's head
        mesh += _unit_pitch(arm, -30 if frame == "attack" else -12, pivot)
        mesh += r3.sphere((0, -0.34, 0.92), 0.16, (86, 150, 96), rings=3, sides=6)  # living wood leafs at the tail
    else:
        pivot = (0, -0.04, 0.65)
        arm = _unit_rod((0, -0.04, 0.44), (0, -0.04, 1.43), 0.055, wood)
        arm += r3.cylinder((0, -0.04, 1.33), 0.16, 0.13, wood_dark, sides=8)
        arm += r3.cylinder((0, -0.04, 1.45), 0.175, 0.035, look.metal, sides=8)
        if frame != "attack":
            arm += r3.sphere((0, -0.04, 1.5), 0.125, BOULDER, rings=3, sides=6)
        mesh += _unit_pitch(arm, -52 if frame == "attack" else 66, pivot)
        if race is Race.ORC:
            for x in (-0.3, 0.3):
                mesh += r3.cone((x, -0.4, 0.83), 0.05, 0.2, BONE, sides=4)
            mesh += r3.sphere((0, 0.5, 0.42), 0.09, BONE, rings=3, sides=6)  # a skull on the frame
        mesh += r3.box((0, 0.29, 0.35), (0.58, 0.13, 0.15), wood)
    mesh += _unit_panel([(-0.2, 0.365, 0.4), (0.2, 0.365, 0.4),
                         (0.2, 0.365, 0.22), (0, 0.365, 0.17), (-0.2, 0.365, 0.22)], team)
    return mesh


def _healer(player: int, frame: str, race: Race) -> Mesh:
    team = team_color(player)
    look = LOOKS[race]
    robe = PLASTER if race is Race.HUMAN else look.cloth if race is not Race.ORC else (78, 52, 40)
    bob = 0.025 if frame == "walk1" else 0
    mesh = _shadow(0.3) + _legs(frame, robe)
    mesh += r3.cone((0, 0, 0.08), 0.29, 0.84, robe, sides=8)
    mesh += r3.cylinder((0, 0, 0.38 + bob), 0.185, 0.32, robe, sides=8)
    for x in (-0.095, 0.095):
        mesh += _unit_panel([(x - 0.04, 0.178, 0.68), (x + 0.04, 0.178, 0.68),
                             (x + 0.055, 0.254, 0.13), (x - 0.055, 0.254, 0.13)], team)
        mesh += r3.box((x, 0.262, 0.2), (0.09, 0.025, 0.035), GOLD if race is not Race.ORC else BONE)
    mesh += _unit_head((0, 0.01, 0.83 + bob), 0.155, race=race)
    if race is Race.HUMAN:
        mesh += r3.pyramid((0, 0, 0.96 + bob), (0.29, 0.22), 0.31, PLASTER)
        mesh += r3.box((0, 0, 0.99 + bob), (0.3, 0.235, 0.06), GOLD)
        mesh += r3.box((0, 0.074, 1.095 + bob), (0.055, 0.075, 0.18), team)
    elif race is Race.ORC:
        # A wooden mask with feathers.
        mesh += _unit_panel([(-0.15, 0.16, 0.72 + bob), (0.15, 0.16, 0.72 + bob), (0.12, 0.16, 1.0 + bob), (-0.12, 0.16, 1.0 + bob)], WOOD)
        for x in (-0.06, 0.06):
            mesh += r3.box((x, 0.17, 0.88 + bob), (0.04, 0.02, 0.04), INK)
        for x, tilt in ((-0.1, -0.25), (0.0, 0.0), (0.1, 0.25)):
            mesh += _unit_rod((x, 0.1, 0.98 + bob), (x + tilt, 0.05, 1.28 + bob), 0.025, team)
    elif race is Race.ELF:
        mesh += r3.cone((0, -0.02, 0.9 + bob), 0.2, 0.3, look.cloth, sides=8)  # a hood
        mesh += r3.cylinder((0, 0, 1.0 + bob), 0.06, 0.02, look.hair, sides=6)
    else:
        mesh += r3.sphere((0, 0, 0.95 + bob), 0.17, look.metal_dark, rings=3, sides=7)  # a runed skullcap
        mesh += r3.box((0, 0.16, 0.98 + bob), (0.07, 0.03, 0.07), GOLD)
    mesh += _unit_rod((-0.2, 0, 0.64), (-0.34, 0.12, 0.57), 0.08, robe)
    mesh += _unit_rod((0.2, 0, 0.64), (0.3, 0.18, 0.7 if frame == "attack" else 0.49), 0.075, robe)
    lift = 0.15 if frame == "attack" else 0
    staff = _unit_rod((-0.36, 0.12, 0.12 + lift), (-0.36, 0.12, 1.3 + lift), 0.032, WOOD)
    if race is Race.HUMAN:
        # Tall gilded sun staff gives the healer an unmistakable asymmetric silhouette.
        staff += r3.sphere((-0.36, 0.12, 1.34 + lift), 0.125, GOLD, rings=3, sides=8)
        staff += r3.box((-0.36, 0.13, 1.36 + lift), (0.34, 0.055, 0.055), GOLD)
        staff += r3.box((-0.36, 0.12, 1.39 + lift), (0.055, 0.055, 0.36), GOLD)
        staff += r3.sphere((-0.36, 0.19, 1.35 + lift), 0.064, (143, 221, 246), rings=3, sides=6)
    elif race is Race.ORC:
        staff += r3.sphere((-0.36, 0.12, 1.36 + lift), 0.11, BONE, rings=3, sides=6)  # a skull totem
        for x, tilt in ((-0.44, -0.2), (-0.28, 0.2)):
            staff += _unit_rod((x, 0.12, 1.4 + lift), (x + tilt, 0.05, 1.62 + lift), 0.02, team)
    elif race is Race.ELF:
        for tip in ((-0.52, 0.06, 1.58 + lift), (-0.2, 0.06, 1.6 + lift), (-0.42, 0.2, 1.5 + lift), (-0.3, 0.2, 1.52 + lift)):
            staff += _unit_rod((-0.36, 0.12, 1.3 + lift), tip, 0.022, BONE)  # antlers
        staff += r3.sphere((-0.36, 0.12, 1.42 + lift), 0.07, (150, 240, 190), rings=3, sides=6)
    else:
        staff += r3.box((-0.36, 0.12, 1.36 + lift), (0.16, 0.24, 0.16), look.metal)  # a rune hammer
        staff += r3.box((-0.36, 0.245, 1.36 + lift), (0.07, 0.01, 0.07), GOLD)
    return mesh + staff


def _unit_mesh(unit_type: UnitType, player: int, frame: str, carrying: Resource | None, race: Race = Race.HUMAN) -> Mesh:
    if unit_type is UnitType.PEASANT:
        return _worker(player, frame, carrying, race)
    if unit_type is UnitType.FOOTMAN:
        return _footman(player, frame, race)
    if unit_type is UnitType.ARCHER:
        return _archer(player, frame, race)
    if unit_type is UnitType.KNIGHT:
        return _knight(player, frame, race)
    if unit_type is UnitType.SCOUT:
        return _scout(player, frame, race)
    if unit_type is UnitType.CATAPULT:
        return _siege(player, frame, race)
    if unit_type is UnitType.CLERIC:
        return _healer(player, frame, race)
    raise ValueError(unit_type)


def facing_index(angle: float) -> int:
    """0..7 from a radian heading (0 = +x, quarter turns clockwise on screen)."""
    return int(round(angle / (math.pi / 4))) % FACINGS


def chop_contact_offset(facing: int, race: Race = Race.HUMAN) -> tuple[float, float]:
    """Projected cutting edge of the worker's contact pose, relative to its feet."""
    across, tall = LOOKS[race].stretch
    lean = math.radians(_WORKER_LEAN["chop3"])
    swing = math.radians(_WORKER_SWING["chop3"])
    _, gy, gz = _WORKER_GRIP
    _, hy, hz = _WORKER_HIP
    # Tool articulation counters the body bend: pitch the grip with the torso,
    # then pitch the blade relative to that grip by its absolute swing angle.
    bent_y = hy + (gy - hy) * math.cos(lean) - (gz - hz) * math.sin(lean)
    bent_z = hz + (gy - hy) * math.sin(lean) + (gz - hz) * math.cos(lean)
    edge_x, edge_y, edge_z = _WORKER_AXE_EDGE[1]
    x = edge_x * across * UNIT_SCALE
    y = (bent_y + (edge_y - gy) * math.cos(swing) - (edge_z - gz) * math.sin(swing)) * across * UNIT_SCALE
    z = (bent_z + (edge_y - gy) * math.sin(swing) + (edge_z - gz) * math.cos(swing)) * tall * UNIT_SCALE
    angle = math.radians(facing * 45 - 90)
    c, s = math.cos(angle), math.sin(angle)
    return PROJECTION.project((x * c - y * s, x * s + y * c, z))


def unit_key(unit_type: UnitType, player: int, facing: int, frame: str, carrying: Resource | None = None, race: Race = Race.HUMAN) -> str:
    carry = f".{carrying.value}" if carrying is not None else ""
    return f"unit.{race.value}.{unit_type.value}{carry}.{player}.{facing}.{frame}"


def unit_image(game: Game, unit_type: UnitType, player: int, facing: int, frame: str, carrying: Resource | None = None, *,
               race: Race = Race.HUMAN) -> str:
    """Register (once) and return the key of one unit image."""
    key = unit_key(unit_type, player, facing, frame, carrying, race)
    if not game.assets.has_image(key):
        mesh = r3.rotate_z(_unit(unit_type, player, frame, carrying, race), facing * 45 - 90)
        game.assets.image_from_pil(key, _prop(key, mesh, DROP_UNIT, game.backend.scale_factor))
    return key


def portrait_image(game: Game, subject: UnitType | BuildingType, player: int | None, race: Race = Race.HUMAN) -> str:
    """A tightly framed picture of a unit or building, for the selection panel."""
    key = f"portrait.{race.value}.{subject.value}.{player}"
    if not game.assets.has_image(key):
        if isinstance(subject, UnitType):
            mesh = r3.rotate_z(_unit(subject, player or 0, "stand", None, race), 0)
        elif subject is BuildingType.GOLD_MINE:
            mesh = _mine()
        else:
            mesh = _building(subject, player or 0, race)
        min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
        w, h = max_x - min_x + 2 * PAD, max_y - min_y + 2 * PAD
        px = 128 * game.backend.scale_factor / max(w, h)
        game.assets.image_from_pil(key, r3.render(mesh, PROJECTION, scale=px, canvas=(w, h), origin=(-min_x + PAD, -min_y + PAD)))
    return key


def warm_units(game: Game, players: list[int], races: list[Race] | None = None):
    """A generator that renders every unit image the match may need, one per step, so the
    scene can spread the cost over its first frames instead of hitching in the first battle."""
    for index, player in enumerate(players):
        race = races[index] if races is not None else Race.HUMAN
        for unit_type in UnitType:
            carries: tuple[Resource | None, ...] = (None, Resource.GOLD, Resource.LUMBER) if unit_type is UnitType.PEASANT else (None,)
            for carrying in carries:
                frames = FRAMES + CHOP_FRAMES if unit_type is UnitType.PEASANT and carrying is None else FRAMES
                for facing in range(FACINGS):
                    for frame in frames:
                        yield unit_image(game, unit_type, player, facing, frame, carrying, race=race)


def building_key(building_type: BuildingType, player: int, race: Race = Race.HUMAN) -> str:
    return f"building.{race.value}.{building_type.value}.{player}"


def building_image(game: Game, building_type: BuildingType, player: int, race: Race = Race.HUMAN) -> str:
    key = building_key(building_type, player, race)
    if not game.assets.has_image(key):
        size = BUILDINGS[building_type].size
        game.assets.image_from_pil(key, _prop(key, _building(building_type, player, race), size / 2 * TILE + PAD, game.backend.scale_factor))
    return key


DROP_TREE = TILE / 2 + PAD  # a tree is placed at its tile's centre; its image reaches the tile's front edge
DROP_UNIT = TILE * 1.5 + PAD  # a lance pointed at the camera, or a broad dwarf's axe at the foot of its swing, reaches well below the feet


# -- 2-D effect images ----------------------------------------------------------------


def _glow(size: int, radius_frac: float, color: tuple[int, int, int, int], blur_frac: float = 0.18) -> Image.Image:

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = size * radius_frac
    c = size / 2
    draw.ellipse([c - r, c - r, c + r, c + r], fill=color)
    return img.filter(ImageFilter.GaussianBlur(size * blur_frac))


def _ring(px: int, scale: float) -> Image.Image:
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    c, r = px / 2, px * 0.42
    draw.ellipse([c - r, c - r, c + r, c + r], outline=(*WHITE, 255), width=max(2, round(3 * scale)))
    return img


def _arrow(scale: float) -> Image.Image:
    """A fletched arrow pointing right, 24 logical units long."""
    w, h = round(24 * scale), round(6 * scale)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(0, h / 2), (w - 3 * scale, h / 2)], fill=(214, 190, 150, 255), width=max(1, round(1.5 * scale)))
    draw.polygon([(w, h / 2), (w - 5 * scale, 0), (w - 5 * scale, h)], fill=(220, 224, 230, 255))
    draw.polygon([(0, 0), (4 * scale, h / 2), (0, h)], fill=(220, 80, 70, 255))
    return img


# -- Registration -----------------------------------------------------------------------


def register_theme(game: Game, theme: MapTheme) -> None:
    """The trees and rocks of one theme (once per game)."""
    scale = game.backend.scale_factor
    assets = game.assets
    if assets.has_image(f"tree.{theme.value}.0"):
        return
    for i in range(TREE_VARIANTS):
        key = f"tree.{theme.value}.{i}"
        assets.image_from_pil(key, _resource_image("tree", i, theme, scale))
    for i in range(ROCK_VARIANTS):
        key = f"rock.{theme.value}.{i}"
        assets.image_from_pil(key, _resource_image("rock", i, theme, scale))


def register_static(game: Game) -> None:
    """Construction sites and effect images (once per game); mines load on demand."""
    if game.assets.has_image("glow"):
        return
    scale = game.backend.scale_factor
    assets = game.assets
    for size in {info.size for info in BUILDINGS.values()}:
        assets.image_from_pil(f"site.{size}", _prop(f"site.{size}", _site(size), size / 2 * TILE + PAD, scale))
    px = int(TILE * scale)
    assets.image_from_pil("glow", _glow(px * 2, 0.24, (*WHITE, 255)))
    assets.image_from_pil("ring", _ring(px * 2, scale))
    assets.image_from_pil("spark", _glow(int(px * 0.5), 0.3, (*WHITE, 255), 0.15))
    assets.image_from_pil("smoke", _glow(px, 0.3, (40, 40, 44, 200), 0.2))
    assets.image_from_pil("blank", Image.new("RGBA", (px, px), (*WHITE, 255)))
    assets.image_from_pil("arrow", _arrow(scale))
    assets.image_from_pil("stone", _glow(int(px * 0.4), 0.36, (150, 140, 128, 255), 0.06))
