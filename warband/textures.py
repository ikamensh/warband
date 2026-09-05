"""Warband's art, all procedural.

The ground is painted with Pillow in chunks of ``CHUNK``×``CHUNK`` tiles
(grass dapples, forest floor, water with ripples, sand along the shore).
Everything that stands on it — trees, rocks, gold mines, buildings, units —
is a low-poly mesh rendered with :mod:`saga2d.render3d` through a 3/4 camera
whose tile footprints stay square (:meth:`Projection.front`), so a 3×3
building covers exactly 3×3 tiles on screen and still shows lit walls.

Units face eight ways and have four frames (stand, two walking, attack);
peasants add carrying variants.  Those images are rendered on demand
(:func:`unit_image`) because a match uses only a fraction of the
combinations.  Sprites are anchored at the bottom centre; :data:`placements`
records each image's logical size and *drop* — how far its bottom edge lies
below the point it is placed at — like Tribes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from saga2d import Game
from saga2d import render3d as r3
from saga2d.render3d import Mesh
from warband.rules import BUILDINGS, PLAYERS, BuildingType, Resource, Terrain, UnitType

TILE = 32
ELEVATION = 50.0
PROJECTION = r3.Projection.front(TILE, ELEVATION)
VIEW = PROJECTION.view
CHUNK = 8  # ground tiles per chunk image (plus one tile of margin all round to hide the seams)
CHUNK_PX = (CHUNK + 2) * TILE
PAD = 2
FACINGS = 8
FRAMES = ("stand", "walk1", "walk2", "attack")
TREE_VARIANTS = 3
ROCK_VARIANTS = 2

GRASS = (108, 162, 78)
FOREST_FLOOR = ((76, 118, 58), (80, 122, 60), (72, 112, 54))
WATER = (52, 110, 170)
WATER_RIPPLE = (120, 170, 220)
SAND = (198, 182, 134)
ROCK_GROUND = (118, 140, 90)
TRUNK = (98, 70, 46)
LEAF = ((44, 110, 58), (56, 126, 66), (38, 98, 52))
LEAF_LIGHT = ((70, 140, 76), (84, 156, 84), (62, 128, 70))
ROCK = (132, 130, 126)
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

Color = tuple[int, int, int]


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


def ground_chunk(terrain_at, in_bounds, cx: int, cy: int, scale: float) -> Image.Image:
    """Paint the chunk at chunk coordinates ``(cx, cy)`` with a tile of margin
    around it; *terrain_at(pos)* and *in_bounds(pos)* read the map."""
    px = TILE * scale
    n = CHUNK + 2
    image = Image.new("RGBA", (round(n * px), round(n * px)), (*GRASS, 255))
    draw = ImageDraw.Draw(image)
    x0, y0 = cx * CHUNK - 1, cy * CHUNK - 1

    def kind(tx: int, ty: int) -> Terrain:
        return terrain_at((tx, ty)) if in_bounds((tx, ty)) else Terrain.TREES

    for j in range(n):
        for i in range(n):
            tx, ty = x0 + i, y0 + j
            terrain = kind(tx, ty)
            left, top = i * px, j * px
            if terrain is Terrain.WATER:
                draw.rectangle((left, top, left + px, top + px), fill=WATER)
            elif terrain is Terrain.TREES:
                draw.rectangle((left, top, left + px, top + px), fill=FOREST_FLOOR[scatter(tx, ty) % len(FOREST_FLOOR)])
                s = scatter(tx, ty, 5)
                dx, dy, r = (s & 0xFF) / 255 * px, ((s >> 8) & 0xFF) / 255 * px, px * 0.08
                draw.ellipse((left + dx - r, top + dy - r, left + dx + r, top + dy + r), fill=darker(FOREST_FLOOR[0], 0.9))
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
    # Shores: sand on the land side of every grass/water edge, a pale rim on the water side.
    band = px * 0.22
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
                    draw.rectangle((left + px - band * 0.4, top, left + px, top + px), fill=WATER_RIPPLE)
                elif dx == -1:
                    draw.rectangle((left - band, top, left, top + px), fill=SAND)
                    draw.rectangle((left, top, left + band * 0.4, top + px), fill=WATER_RIPPLE)
                elif dy == 1:
                    draw.rectangle((left, top + px, left + px, top + px + band), fill=SAND)
                    draw.rectangle((left, top + px - band * 0.4, left + px, top + px), fill=WATER_RIPPLE)
                else:
                    draw.rectangle((left, top - band, left + px, top), fill=SAND)
                    draw.rectangle((left, top, left + px, top + band * 0.4), fill=WATER_RIPPLE)
    for j in range(n):
        for i in range(n):
            tx, ty = x0 + i, y0 + j
            if kind(tx, ty) is Terrain.WATER:
                left, top = i * px, j * px
                s = scatter(tx, ty, 7)
                for k in range(2):
                    rx = left + px * (0.15 + 0.5 * ((s >> (k * 4)) & 0xF) / 15)
                    ry = top + px * (0.2 + 0.6 * ((s >> (k * 4 + 8)) & 0xF) / 15)
                    draw.line([(rx, ry), (rx + px * 0.12, ry - px * 0.03), (rx + px * 0.24, ry)], fill=WATER_RIPPLE, width=max(1, round(1.2 * scale)))
    return image


# -- Props --------------------------------------------------------------------------


def _prop(key: str, mesh: Mesh, drop: float, scale: float) -> Image.Image:
    """Render *mesh* into a canvas symmetric about the model origin whose bottom is
    *drop* below it, and record the placement."""
    min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
    half_w = math.ceil(max(-min_x, max_x) + PAD)
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


def _tree(variant: int) -> Mesh:
    leaf, light = LEAF[variant], LEAF_LIGHT[variant]
    tilt = (0.04, -0.03) if variant == 0 else (-0.03, 0.02) if variant == 1 else (0.0, 0.04)
    return (
        _shadow(0.34)
        + r3.cylinder((0, 0, 0), 0.07, 0.26, TRUNK, sides=6)
        + r3.cone((0, 0, 0.18), 0.42, 0.55, leaf, sides=8, rotation=0.2 * variant)
        + r3.cone((tilt[0], tilt[1], 0.5), 0.3, 0.5, light, sides=8, rotation=0.6 + 0.2 * variant)
    )


def _rock(variant: int) -> Mesh:
    if variant == 0:
        return _shadow(0.3) + r3.pyramid((0.05, 0.02, 0), (0.5, 0.42), 0.34, ROCK, apex_shift=(-0.08, 0.04)) + r3.pyramid((-0.22, -0.1, 0), (0.28, 0.24), 0.18, darker(ROCK, 0.85))
    return _shadow(0.3) + r3.box((0, 0, 0.12), (0.5, 0.36, 0.24), ROCK) + r3.pyramid((0.05, 0, 0.24), (0.42, 0.3), 0.2, darker(ROCK, 0.9), apex_shift=(0.08, 0.02))


def _mine() -> Mesh:
    mound = r3.pyramid((0, -0.1, 0), (2.6, 2.4), 1.0, EARTH, apex_shift=(0.0, -0.35))
    entrance = r3.facing(_facing_quad((0, 1.02, 0.24), 0.36, 0.24), INK, VIEW)
    beams = r3.box((-0.42, 1.06, 0.26), (0.1, 0.1, 0.52), WOOD_DARK) + r3.box((0.42, 1.06, 0.26), (0.1, 0.1, 0.52), WOOD_DARK)
    beams += r3.box((0, 1.06, 0.52), (0.98, 0.1, 0.1), WOOD_DARK)
    nuggets: Mesh = []
    for x, y, r in ((-0.72, 0.92, 0.1), (0.66, 0.98, 0.12), (0.2, 1.18, 0.08), (-0.35, 1.2, 0.07)):
        nuggets += r3.sphere((x, y, r), r, GOLD, rings=3, sides=6)
    return mound + entrance + beams + nuggets


def _door(x: float, y: float, z: float, w: float, h: float) -> Mesh:
    return r3.facing(_facing_quad((x, y, z), w / 2, h / 2), INK, VIEW)


def _pennant(x: float, y: float, z: float, height: float, color: Color) -> Mesh:
    pole = r3.box((x, y, z + height / 2), (0.04, 0.04, height), INK)
    flag = r3.facing([(x, y, z + height), (x + 0.3, y, z + height - 0.08), (x, y, z + height - 0.18)], color, VIEW)
    return pole + flag


def _building(building_type: BuildingType, player: int) -> Mesh:
    team = team_color(player)
    trim = darker(team, 0.75)
    if building_type is BuildingType.TOWN_HALL:
        roof_color = darker(team, 0.82)
        plinth = r3.box((0.15, 0.15, 0.08), (2.6, 2.3, 0.16), STONE_DARK)
        base = r3.box((0.15, 0.15, 0.7), (2.2, 2.0, 1.1), STONE)
        # The ridge runs towards the camera: a plaster gable in front, two slopes lit differently.
        roof = r3.rotate_z(r3.gable_roof((0.15, 0.15, 1.25), (2.25, 2.4), 0.62, roof_color), 90, about=(0.15, 0.15))
        gable = r3.facing([(-0.95, 1.36, 1.25), (1.25, 1.36, 1.25), (0.15, 1.36, 1.87)], PLASTER, VIEW)
        windows = r3.facing(_facing_quad((-0.4, 1.17, 0.8), 0.1, 0.14), INK, VIEW) + r3.facing(_facing_quad((0.75, 1.17, 0.8), 0.1, 0.14), INK, VIEW)
        tower = r3.box((-0.85, -0.6, 1.0), (0.7, 0.7, 2.0), STONE_DARK)
        cap = r3.pyramid((-0.85, -0.6, 2.0), (0.88, 0.88), 0.5, trim)
        return plinth + base + roof + gable + windows + tower + cap + _door(0.15, 1.17, 0.32, 0.5, 0.64) + _pennant(-0.85, -0.6, 2.5, 0.55, team)
    if building_type is BuildingType.BARRACKS:
        base = r3.box((0, 0.05, 0.5), (2.5, 1.9, 1.0), WOOD)
        roof = r3.rotate_z(r3.gable_roof((0, 0.05, 1.0), (2.1, 2.7), 0.5, SLATE), 90)
        roof += r3.facing([(-1.05, 1.41, 1.0), (1.05, 1.41, 1.0), (0, 1.41, 1.5)], WOOD_DARK, VIEW)
        wall = r3.box((0, 1.15, 0.18), (2.5, 0.28, 0.36), STONE_DARK)
        banners = r3.facing(_facing_quad((-0.8, 1.02, 0.75), 0.16, 0.34), team, VIEW) + r3.facing(_facing_quad((0.8, 1.02, 0.75), 0.16, 0.34), team, VIEW)
        return base + roof + wall + banners + _door(0, 1.01, 0.32, 0.5, 0.6)
    if building_type is BuildingType.FARM:
        house = r3.box((-0.42, -0.35, 0.28), (1.0, 0.85, 0.56), PLASTER)
        roof = r3.gable_roof((-0.42, -0.35, 0.56), (1.15, 1.0), 0.45, THATCH)
        rows: Mesh = []
        for k in range(4):
            rows += r3.box((0.45, -0.62 + k * 0.4, 0.03), (0.85, 0.16, 0.06), darker(EARTH, 0.9))
            rows += r3.box((0.45, -0.62 + k * 0.4, 0.09), (0.8, 0.1, 0.06), (150, 170, 70))
        fence: Mesh = []
        for x in (-0.9, -0.5, -0.1, 0.3, 0.7):
            fence += r3.box((x, 0.92, 0.1), (0.06, 0.06, 0.2), WOOD)
        fence += r3.box((-0.1, 0.92, 0.16), (1.7, 0.03, 0.04), WOOD)
        return house + roof + rows + fence + _door(-0.42, 0.08, 0.2, 0.3, 0.4) + r3.facing(_facing_quad((-0.42, 0.09, 0.62), 0.14, 0.1), team, VIEW)
    if building_type is BuildingType.TOWER:
        body = r3.cylinder((0, 0, 0), 0.6, 1.7, STONE, sides=10)
        crown: Mesh = []
        for i in range(6):
            a = 2 * math.pi * i / 6
            crown += r3.box((0.52 * math.cos(a), 0.52 * math.sin(a), 1.8), (0.2, 0.2, 0.22), STONE_DARK)
        return body + crown + r3.facing(_facing_quad((0, 0.61, 1.35), 0.12, 0.16), INK, VIEW) + _pennant(0, 0, 1.7, 0.6, team)
    raise ValueError(building_type)


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


def _legs(frame: str, color: Color, spread: float = 0.09) -> Mesh:
    swing = {"walk1": 0.09, "walk2": -0.09}.get(frame, 0.0)
    return (
        r3.cylinder((-spread, swing, 0), 0.07, 0.2, color, sides=6)
        + r3.cylinder((spread, -swing, 0), 0.07, 0.2, color, sides=6)
    )


def _body(tunic: Color, frame: str, head: Color = SKIN, body_r: float = 0.21, body_h: float = 0.42) -> Mesh:
    bob = 0.02 if frame == "walk1" else 0.0
    return (
        _legs(frame, (72, 62, 58))
        + r3.cylinder((0, 0, 0.18 + bob), body_r, body_h, tunic, sides=8)
        + r3.sphere((0, 0, 0.18 + bob + body_h + 0.15), 0.17, head, rings=5, sides=8)
    )


def _sword(frame: str) -> Mesh:
    if frame == "attack":
        return r3.box((0.3, 0.42, 0.62), (0.06, 0.66, 0.06), IRON) + r3.box((0.3, 0.1, 0.62), (0.2, 0.06, 0.06), WOOD_DARK)
    return r3.box((0.3, 0.06, 0.66), (0.06, 0.06, 0.62), IRON) + r3.box((0.3, 0.06, 0.4), (0.2, 0.06, 0.06), WOOD_DARK)


UNIT_SCALE = 1.4  # figures are modelled at chibi size and blown up so they read from the usual zoom


def _unit(unit_type: UnitType, player: int, frame: str, carrying: Resource | None) -> Mesh:
    return r3.scale(_unit_mesh(unit_type, player, frame, carrying), UNIT_SCALE)


def _unit_mesh(unit_type: UnitType, player: int, frame: str, carrying: Resource | None) -> Mesh:
    team = team_color(player)
    trim = darker(team, 0.7)
    if unit_type is UnitType.PEASANT:
        mesh = _shadow(0.3) + _body(team, frame)
        if carrying is Resource.GOLD:
            mesh += r3.sphere((-0.28, 0.02, 0.62), 0.17, GOLD, rings=4, sides=8)
        elif carrying is Resource.LUMBER:
            mesh += r3.box((0, 0.02, 0.98), (0.2, 0.9, 0.18), TRUNK)
        else:
            lift = 0.3 if frame == "attack" else 0.0
            mesh += r3.box((0.3, 0.04, 0.5 + lift), (0.05, 0.05, 0.55), WOOD) + r3.box((0.3, 0.04, 0.78 + lift), (0.26, 0.06, 0.07), IRON)
        return mesh
    if unit_type is UnitType.FOOTMAN:
        helmet = r3.cone((0, 0, 0.86), 0.19, 0.16, IRON, sides=8)
        shield = r3.box((-0.32, 0.04, 0.5), (0.07, 0.36, 0.42), trim) + r3.box((-0.36, 0.04, 0.5), (0.02, 0.12, 0.14), IRON)
        return _shadow(0.32) + _body(team, frame) + helmet + shield + _sword(frame)
    if unit_type is UnitType.ARCHER:
        hood = r3.sphere((0, 0, 0.78), 0.19, (60, 74, 62), rings=4, sides=8)
        quiver = r3.box((-0.2, -0.22, 0.6), (0.1, 0.1, 0.4), WOOD_DARK)
        bow: Mesh = []
        for a0, a1 in zip(range(-60, 60, 15), range(-45, 75, 15)):
            p0 = (0.3, 0.28 * math.sin(math.radians(a0)), 0.62 + 0.3 * math.cos(math.radians(a0)))
            p1 = (0.3, 0.28 * math.sin(math.radians(a1)), 0.62 + 0.3 * math.cos(math.radians(a1)))
            bow += r3.box(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2), (0.04, abs(p1[1] - p0[1]) + 0.03, abs(p1[2] - p0[2]) + 0.03), WOOD)
        arrow = r3.box((0.3, 0.42, 0.62), (0.03, 0.5, 0.03), IRON) if frame == "attack" else []
        return _shadow(0.3) + _body(team, frame) + hood + quiver + bow + arrow
    if unit_type is UnitType.KNIGHT:
        horse = (72, 52, 40)
        swing = {"walk1": 0.08, "walk2": -0.08}.get(frame, 0.0)
        mesh = _shadow(0.42, 0.06, 0.02)
        for x, y in ((-0.16, -0.26), (0.16, -0.26), (-0.16, 0.26), (0.16, 0.26)):
            mesh += r3.box((x, y + (swing if (x < 0) == (y < 0) else -swing), 0.15), (0.1, 0.1, 0.3), horse)
        mesh += r3.box((0, 0, 0.44), (0.4, 0.9, 0.3), horse)
        mesh += r3.box((0, 0.55, 0.66), (0.2, 0.3, 0.24), horse) + r3.box((0, 0.42, 0.6), (0.16, 0.16, 0.3), horse)
        mesh += r3.box((0, 0, 0.62), (0.44, 0.7, 0.08), team)  # caparison
        mesh += r3.cylinder((0, -0.05, 0.66), 0.17, 0.34, team, sides=8) + r3.sphere((0, -0.05, 1.13), 0.15, SKIN, rings=4, sides=8)
        mesh += r3.cone((0, -0.05, 1.2), 0.17, 0.16, IRON, sides=8) + r3.box((-0.28, 0, 0.9), (0.06, 0.3, 0.36), trim)
        lance_y = 0.55 if frame == "attack" else 0.1
        mesh += r3.box((0.28, lance_y, 1.0), (0.05, 1.2, 0.05), IRON) + r3.facing([(0.28, lance_y + 0.55, 1.03), (0.28, lance_y + 0.35, 1.13), (0.28, lance_y + 0.35, 1.0)], team, VIEW)
        return mesh
    raise ValueError(unit_type)


def facing_index(angle: float) -> int:
    """0..7 from a radian heading (0 = +x, quarter turns clockwise on screen)."""
    return int(round(angle / (math.pi / 4))) % FACINGS


def unit_key(unit_type: UnitType, player: int, facing: int, frame: str, carrying: Resource | None = None) -> str:
    carry = f".{carrying.value}" if carrying is not None else ""
    return f"unit.{unit_type.value}{carry}.{player}.{facing}.{frame}"


def unit_image(game: Game, unit_type: UnitType, player: int, facing: int, frame: str, carrying: Resource | None = None) -> str:
    """Register (once) and return the key of one unit image."""
    key = unit_key(unit_type, player, facing, frame, carrying)
    if not game.assets.has_image(key):
        mesh = r3.rotate_z(_unit(unit_type, player, frame, carrying), facing * 45 - 90)
        game.assets.image_from_pil(key, _prop(key, mesh, DROP_UNIT, game.backend.scale_factor))
    return key


def portrait_image(game: Game, subject: UnitType | BuildingType, player: int | None) -> str:
    """A tightly framed picture of a unit or building, for the selection panel."""
    key = f"portrait.{subject.value}.{player}"
    if not game.assets.has_image(key):
        if isinstance(subject, UnitType):
            mesh = r3.rotate_z(_unit(subject, player or 0, "stand", None), 0)
        elif subject is BuildingType.GOLD_MINE:
            mesh = _mine()
        else:
            mesh = _building(subject, player or 0)
        min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
        w, h = max_x - min_x + 2 * PAD, max_y - min_y + 2 * PAD
        px = 128 * game.backend.scale_factor / max(w, h)
        game.assets.image_from_pil(key, r3.render(mesh, PROJECTION, scale=px, canvas=(w, h), origin=(-min_x + PAD, -min_y + PAD)))
    return key


def building_key(building_type: BuildingType, player: int) -> str:
    return f"building.{building_type.value}.{player}"


def building_image(game: Game, building_type: BuildingType, player: int) -> str:
    key = building_key(building_type, player)
    if not game.assets.has_image(key):
        size = BUILDINGS[building_type].size
        game.assets.image_from_pil(key, _prop(key, _building(building_type, player), size / 2 * TILE + PAD, game.backend.scale_factor))
    return key


DROP_TREE = TILE / 2 + PAD  # a tree is placed at its tile's centre; its image reaches the tile's front edge
DROP_UNIT = TILE * 1.25 + PAD  # a lance pointed at the camera reaches well below the feet


# -- 2-D effect images ----------------------------------------------------------------


def _glow(size: int, radius_frac: float, color: tuple[int, int, int, int], blur_frac: float = 0.18) -> Image.Image:
    from PIL import ImageFilter

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


def register_static(game: Game) -> None:
    """Trees, rocks, the mine, construction sites and effect images (once per game)."""
    if game.assets.has_image("mine"):
        return
    scale = game.backend.scale_factor
    assets = game.assets
    for i in range(TREE_VARIANTS):
        assets.image_from_pil(f"tree.{i}", _prop(f"tree.{i}", _tree(i), DROP_TREE, scale))
    for i in range(ROCK_VARIANTS):
        assets.image_from_pil(f"rock.{i}", _prop(f"rock.{i}", _rock(i), DROP_TREE, scale))
    assets.image_from_pil("mine", _prop("mine", _mine(), 1.5 * TILE + PAD, scale))
    for size in {info.size for info in BUILDINGS.values()}:
        assets.image_from_pil(f"site.{size}", _prop(f"site.{size}", _site(size), size / 2 * TILE + PAD, scale))
    px = int(TILE * scale)
    assets.image_from_pil("glow", _glow(px * 2, 0.24, (*WHITE, 255)))
    assets.image_from_pil("ring", _ring(px * 2, scale))
    assets.image_from_pil("spark", _glow(int(px * 0.5), 0.3, (*WHITE, 255), 0.15))
    assets.image_from_pil("smoke", _glow(px, 0.3, (40, 40, 44, 200), 0.2))
    assets.image_from_pil("blank", Image.new("RGBA", (px, px), (*WHITE, 255)))
    assets.image_from_pil("arrow", _arrow(scale))
