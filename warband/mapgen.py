"""Procedural maps in five layouts, fair by symmetry.

A map is drawn once for the first seat and copied to the others: two players
get the point reflection through the centre, three and four the mirror in
both axes (with three, the fourth corner stays empty and its natural mine
neutral).  Every layout shares one skeleton: a hall with its main mine and
grove in a clearing, a natural expansion far enough out to need a hall of its
own, contested third mines in the middle, forest along the edges, and every
door and mine walkable within the pathfinder's budget.  The layouts add their
own walls and gold:

  Plains     open ground with groves and ponds
  Forest     woods everywhere; clearings joined by winding two-tile roads
  Crossings  a river with a wide centre ford and narrow edge fords
  Klondike   a small start mine; the rest of the gold in a rock-ringed pit
  Bastion    a tree ring with one gate around every base

``generate`` retries a seed a few times when the audit finds a fault and
raises when the layout cannot make a fair map at that size.  The design and
its reasons are in docs/warband-maps.md.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from warband import path as pathing
from warband.model import Pos, World, tile_center
from warband.rules import EXPANSION_GOLD, MINE_GOLD, BuildingType, Layout, MapTheme, Race, Terrain, UnitType

SIZES: Final[dict[str, tuple[int, int]]] = {"Small": (48, 40), "Medium": (64, 48), "Large": (80, 64)}
PROMISES: Final[dict[Layout, str]] = {
    Layout.PLAINS: "Open ground: raids come early, expansions lie exposed",
    Layout.FOREST: "Deep woods: narrow roads, hidden clearings, chop your own way through",
    Layout.CROSSINGS: "A river splits the land: hold the fords or find the long way round",
    Layout.KLONDIKE: "Little gold at home; the rest lies in a walled pit in the middle",
    Layout.BASTION: "Walled in: boom in safety, then break out and fight for the middle",
}
RETRIES: Final = 8
KLONDIKE_START_GOLD: Final = 20_000
POOR_GOLD: Final = 10_000  # the coward's gold: a far corner mine on Klondike
_MARGIN: Final = 7  # tiles from the map edge to the hall's top-left
_CLEARING: Final = 7  # radius of open ground around the hall's middle tile
_SITE_SPACING: Final = {True: 8, False: 7}  # Chebyshev tiles between mine sites, by point symmetry (mirror quadrants are tighter)
_SITE_ROOM: Final = 60  # open tiles within six of a natural or third, so a hall and farms fit

Point = tuple[float, float]


def fresh_seed() -> int:
    """Choose a new map seed within the online protocol's signed 32-bit range."""
    return random.randrange(1, 2**31)


class NoFairMap(ValueError):
    """The layout cannot make a fair map at that size for that many players."""


def generate(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0, theme: MapTheme = MapTheme.SUMMER,
             races: Sequence[Race | None] | None = None, layout: Layout | None = None) -> World:
    """*races* names each player's race; ``None`` entries are drawn from the seed, so a seed reproduces
    the whole match.  Without a list the *human* leads Humans and the computer players are drawn.
    *layout* ``None`` draws one from the seed."""
    return build(seed, width, height, players, human, theme, races, layout)[0]


def build(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0, theme: MapTheme = MapTheme.SUMMER,
          races: Sequence[Race | None] | None = None, layout: Layout | None = None) -> tuple[World, dict]:
    """:func:`generate` plus the audit report of the map it settled on (``attempt`` counts the retries)."""
    if not 2 <= players <= 4:
        raise ValueError("2 to 4 players")
    if races is not None and len(races) != players:
        raise ValueError(f"{players} players need {players} races, not {len(races)}")
    if min(width, height) < 40:
        raise ValueError(f"maps are at least 40 tiles on their shorter side, not {width}x{height}: four symmetric seats need the room")
    if layout is None:
        layout = random.Random(seed ^ 0x1A70).choice(list(Layout))
    wanted: list[Race | None] = list(races) if races is not None else [Race.HUMAN if i == human else None for i in range(players)]
    chosen = draw_races(wanted, random.Random(seed ^ 0x5ACE))
    problems: list[str] = []
    for attempt in range(RETRIES):
        world, report = _attempt(random.Random(seed * 16 + attempt), seed, width, height, players, human, theme, chosen, layout)
        if not report["problems"]:
            report["attempt"] = attempt
            return world, report
        problems = report["problems"]
    raise NoFairMap(f"No fair {layout.value} map at {width}x{height} for {players} players from seed {seed} in {RETRIES} tries: {problems}.")


def draw_races(races: list[Race | None], rng: random.Random) -> list[Race]:
    """Fill the ``None`` entries: each draw avoids races already on the map until all four are taken."""
    chosen = list(races)
    for i, race in enumerate(chosen):
        if race is None:
            taken = {r for r in chosen if r is not None}
            pool = [r for r in Race if r not in taken] or list(Race)
            chosen[i] = rng.choice(pool)
    return chosen  # type: ignore[return-value]


# -- Canvas ------------------------------------------------------------------------


class _Canvas:
    """The terrain under construction and the symmetry that copies the first seat to the others.

    Everything is drawn for the first seat in the *canonical* part of the map (the top half
    under point symmetry, the top-left quadrant under the mirror); :meth:`symmetrize` copies it
    onto the images.  Self-symmetric features (a pit on the centre, a river through it) are
    drawn whole and survive the copy unchanged."""

    def __init__(self, width: int, height: int, seats: int) -> None:
        self.w, self.h = width, height
        self.point = seats == 2
        self.grid = [[Terrain.GRASS] * width for _ in range(height)]
        self.protected: set[Pos] = set()  # walls no corridor may be carved through
        self.centre: Point = ((width - 1) / 2, (height - 1) / 2)

    def images(self, pos: Pos) -> tuple[Pos, ...]:
        """*pos* and its copies, in seat order: self, opposite corner, then across and down."""
        x, y = pos
        far = (self.w - 1 - x, self.h - 1 - y)
        if self.point:
            return ((x, y), far)
        return ((x, y), far, (far[0], y), (x, far[1]))

    def rect_images(self, pos: Pos, size: int) -> tuple[Pos, ...]:
        """Top-left tiles of the copies of a *size* square at *pos*, in seat order."""
        x, y = pos
        fx, fy = self.w - size - x, self.h - size - y
        if self.point:
            return ((x, y), (fx, fy))
        return ((x, y), (fx, fy), (fx, y), (x, fy))

    def orbit(self, tiles: Iterable[Pos]) -> set[Pos]:
        return {image for tile in tiles for image in self.images(tile)}

    def canonical(self, x: int, y: int) -> bool:
        return y < self.h // 2 and (self.point or x < self.w // 2)

    def symmetrize(self) -> None:
        grid = self.grid
        for y in range(self.h // 2):
            for x in range(self.w if self.point else self.w // 2):
                kind = grid[y][x]
                for ix, iy in self.images((x, y))[1:]:
                    grid[iy][ix] = kind
        self.protected = self.orbit(self.protected)

    def symmetric(self, terrain: list[list[Terrain]]) -> bool:
        return all(terrain[iy][ix] is terrain[y][x] for y in range(self.h) for x in range(self.w) for ix, iy in self.images((x, y)))

    def inside(self, x: int, y: int) -> bool:
        """Within the map and off its edge row, which stays forest."""
        return 0 < x < self.w - 1 and 0 < y < self.h - 1

    def within(self, centre: Point, radius: float) -> list[Pos]:
        cx, cy = centre
        r = int(radius) + 1
        return [(x, y) for y in range(int(cy) - r, int(cy) + r + 2) for x in range(int(cx) - r, int(cx) + r + 2)
                if self.inside(x, y) and (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius]

    def band(self, centre: Point, inner: float, outer: float) -> list[Pos]:
        cx, cy = centre
        return [(x, y) for x, y in self.within(centre, outer) if (x - cx) ** 2 + (y - cy) ** 2 >= inner * inner]

    def paint(self, tiles: Iterable[Pos], kind: Terrain, *, over: tuple[Terrain, ...] | None = None) -> None:
        for x, y in tiles:
            if over is None or self.grid[y][x] in over:
                self.grid[y][x] = kind

    def along_ray(self, tiles: Iterable[Pos], origin: Point, angle: float, half_width: float) -> list[Pos]:
        """The *tiles* within *half_width* of the ray from *origin* at *angle*."""
        dx, dy = math.cos(angle), math.sin(angle)
        out = []
        for x, y in tiles:
            vx, vy = x - origin[0], y - origin[1]
            if vx * dx + vy * dy > 0 and abs(vx * dy - vy * dx) <= half_width:
                out.append((x, y))
        return out


def _block(pos: Pos, gap: int = 1) -> list[Pos]:
    """A 3x3 mine at *pos* and *gap* tiles around it."""
    return [(pos[0] + dx, pos[1] + dy) for dy in range(-gap, 3 + gap) for dx in range(-gap, 3 + gap)]


def _mine_centre(pos: Pos) -> Point:
    return (pos[0] + 1.5, pos[1] + 1.5)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# -- Terrain -----------------------------------------------------------------------


def _noise(rng: random.Random, width: int, height: int, cell: int) -> list[list[float]]:
    """Smooth value noise with control points every *cell* tiles."""
    cols, rows = width // cell + 2, height // cell + 2
    grid = [[rng.random() for _ in range(cols)] for _ in range(rows)]
    out = [[0.0] * width for _ in range(height)]
    for y in range(height):
        gy, fy = divmod(y, cell)
        ty = fy / cell
        ty = ty * ty * (3 - 2 * ty)
        for x in range(width):
            gx, fx = divmod(x, cell)
            tx = fx / cell
            tx = tx * tx * (3 - 2 * tx)
            a, b = grid[gy][gx], grid[gy][gx + 1]
            c, d = grid[gy + 1][gx], grid[gy + 1][gx + 1]
            out[y][x] = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
    return out


def _speckle(cv: _Canvas, rng: random.Random, *, trees: float = 0.70, water: float = 0.84, rock: float = 0.87) -> None:
    """Open ground with groves, ponds and outcrops from three noise fields; the edge row is forest
    with a ragged fringe.  Lower thresholds mean more of that kind."""
    grove = _noise(rng, cv.w, cv.h, 4)
    pond = _noise(rng, cv.w, cv.h, 5)
    stone = _noise(rng, cv.w, cv.h, 4)
    fringe = _noise(rng, cv.w, cv.h, 3)
    for y in range(cv.h):
        for x in range(cv.w):
            edge = min(x, y, cv.w - 1 - x, cv.h - 1 - y)
            if edge == 0 or (edge < 3 and fringe[y][x] > 0.4):
                cv.grid[y][x] = Terrain.TREES
            elif pond[y][x] > water and edge > 3:
                cv.grid[y][x] = Terrain.WATER
            elif stone[y][x] > rock:
                cv.grid[y][x] = Terrain.ROCK
            elif grove[y][x] > trees:
                cv.grid[y][x] = Terrain.TREES


def _clump(cv: _Canvas, centre: Pos, radius: float, rng: random.Random) -> None:
    r = int(radius) + 1
    for y in range(centre[1] - r, centre[1] + r + 1):
        for x in range(centre[0] - r, centre[0] + r + 1):
            if cv.inside(x, y) and (x - centre[0]) ** 2 + (y - centre[1]) ** 2 <= (radius + rng.uniform(-0.6, 0.6)) ** 2:
                cv.grid[y][x] = Terrain.TREES


# -- Layouts -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Spec:
    layout: Layout
    clearing: int = _CLEARING
    natural: bool = True
    natural_range: tuple[int, int] = (10, 18)  # tiles from the hall's middle
    natural_clearing: int = 0  # trees cut around the natural (Forest)
    third_clearing: int = 0
    thirds: bool = True  # contested mines in the middle (Klondike keeps its gold in the pit instead)
    contested: int | None = None  # how many tiles nearer one hall than the next a third may be; None: the symmetry's default
    start_gold: int = MINE_GOLD


_SPECS: Final[dict[Layout, _Spec]] = {
    Layout.PLAINS: _Spec(Layout.PLAINS),
    Layout.FOREST: _Spec(Layout.FOREST, clearing=9, natural_range=(13, 18), natural_clearing=5, third_clearing=4),  # a full base needs the room; four seats get less, see _clearing
    Layout.CROSSINGS: _Spec(Layout.CROSSINGS, contested=14),  # the river runs down the bisector; thirds sit on its banks
    Layout.KLONDIKE: _Spec(Layout.KLONDIKE, clearing=6, natural=False, thirds=False, start_gold=KLONDIKE_START_GOLD),
    Layout.BASTION: _Spec(Layout.BASTION, natural_range=(12, 18)),
}


@dataclass
class _Walls:
    """What a layout's wall pass leaves for the site search and the audit, in first-seat coordinates."""

    gates: set[Pos]
    fords: set[Pos]
    rects: list[tuple[Pos, int]]  # footprints the site search must avoid, all seats
    mines: list[tuple[Pos, int]]  # (top-left, gold) of the layout's own mines, all seats
    prefer_natural: Callable[[Pos], float] | None = None
    prefer_third: Callable[[Pos], float] | None = None


def _clearing(spec: _Spec, width: int, height: int, seats: int) -> int:
    """The base clearing's radius: Forest's generous nine shrinks to eight, then seven, where four
    seats share a small map, or the woods between them would be too thin to matter."""
    if spec.layout is not Layout.FOREST or seats == 2:
        return spec.clearing
    return 8 if width * height >= 3000 else 7


def _third_orbits(spec: _Spec, width: int, height: int, seats: int) -> int:
    """How many contested mine sites (each copied to every seat) a map gets: four seats need
    a Large map before the middle has room for any."""
    area = width * height
    if not spec.thirds:
        return 0
    if seats == 2:
        return 1 if area < 2500 else 2
    return 0 if area < 2500 else 1 if area < 5000 else 2


def _river(cv: _Canvas, rng: random.Random, walls: _Walls) -> None:
    """Two players: one river from the centre to the far edge, wandering, and its reflection.
    Four: a straight cross of two rivers of varying width.  A wide ford on the centre, a narrow
    one near each end, rock outcrops on the banks beside the centre ford."""
    cx, cy = cv.centre
    radius = 1.5 if min(cv.w, cv.h) < (48 if cv.point else 64) else 2.0 if min(cv.w, cv.h) < 64 else 2.5
    headings = [-math.pi / 4] if cv.point else [math.pi, -math.pi / 2]
    fords: set[Pos] = set()
    for base in headings:
        points: list[Point] = []
        x, y, heading, travelled = cx, cy, base, 0.0
        while cv.inside(round(x), round(y)):
            points.append((x, y))
            if cv.point and travelled > 5:
                heading = min(base + 0.7, max(base - 0.7, heading + rng.uniform(-0.4, 0.4)))
            x, y, travelled = x + 3 * math.cos(heading), y + 3 * math.sin(heading), travelled + 3
        widths = [radius if cv.point else radius + rng.uniform(0, 0.8) for _ in points]
        widths = [sum(widths[max(0, i - 2):i + 3]) / len(widths[max(0, i - 2):i + 3]) for i in range(len(widths))]  # smoothed: the cross swells and narrows
        tiles: set[Pos] = set()
        for point, width in zip(points, widths):
            tiles.update(cv.within(point, width))
        cv.paint(tiles, Terrain.WATER)
        centre_ford = _cut(tiles, (cx, cy), base, 3.0)
        end = max(1, len(points) - 3)
        edge_ford = _cut(tiles, points[end], math.atan2(points[end][1] - points[end - 1][1], points[end][0] - points[end - 1][0]), 1.5)
        cv.paint(centre_ford | edge_ford, Terrain.GRASS)
        fords |= centre_ford | edge_ford
        cv.protected |= tiles - fords
        dx, dy = math.cos(base), math.sin(base)
        for along in (-6, 6):
            for across in (-(radius + 2.5), radius + 2.5):
                spot = (cx + along * dx - across * dy, cy + along * dy + across * dx)
                cv.paint(cv.within(spot, 1.5), Terrain.ROCK, over=(Terrain.GRASS, Terrain.TREES))
    walls.fords = fords
    walls.prefer_third = lambda pos: -min(_dist(_mine_centre(pos), f) for f in cv.orbit(fords))


def _cut(river: set[Pos], at: Point, heading: float, half_length: float) -> set[Pos]:
    """The river tiles within *half_length* along *heading* of *at*: a ford right across the water."""
    dx, dy = math.cos(heading), math.sin(heading)
    return {(x, y) for x, y in river if abs((x - at[0]) * dx + (y - at[1]) * dy) <= half_length}


def _pit(cv: _Canvas, rng: random.Random, hc: Pos, walls: _Walls) -> None:
    """A rock ring on the centre with a gate towards every seat; the gold inside, and a poor mine
    in each empty corner when two play."""
    cx, cy = cv.centre
    inner = max(6, min(9, round(min(cv.w, cv.h) * 0.18)))
    ring = cv.band((cx, cy), inner, inner + 3)
    cv.paint(ring, Terrain.ROCK)
    cv.paint(cv.within((cx, cy), inner - 0.5), Terrain.GRASS)
    angle = math.atan2(hc[1] - cy, hc[0] - cx) + rng.uniform(-0.5, 0.5)
    gate = cv.along_ray(ring, (cx, cy), angle, 2.0)
    cv.paint(gate, Terrain.GRASS)
    walls.gates = set(gate)
    cv.protected |= set(ring) - set(gate)
    offsets = [(-3.5, -1.5)] + ([(3.5, -3.5)] if inner >= 8 else []) if cv.point else [(-3.5, -2.5)]
    for ox, oy in offsets:
        pos = (round(cx + ox) - 1, round(cy + oy) - 1)
        for image in cv.rect_images(pos, 3):
            walls.mines.append((image, EXPANSION_GOLD))
            walls.rects.append((image, 3))
    if cv.point:
        poor = (cv.w - _MARGIN - 3, _MARGIN)
        cv.paint(_block(poor), Terrain.GRASS)
        for image in cv.rect_images(poor, 3):
            walls.mines.append((image, POOR_GOLD))
            walls.rects.append((image, 3))


def _ring(cv: _Canvas, rng: random.Random, hc: Pos, walls: _Walls) -> None:
    """A tree ring round the base clearing with a three-tile gate facing along the home edge.
    Mirror maps get a thinner ring and gates along the map's long axis, so the quadrant beside
    keeps room for the natural and the two facing gates share the middle column."""
    band = cv.band(hc, _CLEARING + 1, _CLEARING + 4.5) if cv.point else cv.band(hc, _CLEARING + 1, _CLEARING + 3.5)  # the main mine's far corner is 7.8 out
    cv.paint(band, Terrain.TREES)
    angle = rng.choice((0.0, math.pi / 2)) if cv.point else 0.0
    gate = cv.along_ray(band, hc, angle, 1.5)
    cv.paint(gate, Terrain.GRASS)
    walls.gates = set(gate)
    cv.protected |= set(band) - set(gate)
    outside = (hc[0] + 15 * math.cos(angle), hc[1] + 15 * math.sin(angle))
    walls.prefer_natural = lambda pos: -_dist(_mine_centre(pos), outside)


def _road(cv: _Canvas, rng: random.Random, a: Pos, b: Pos) -> None:
    """A two-tile road cut through the trees from *a* to *b*, bending round waypoints."""
    d = _dist(a, b) or 1.0
    n = max(1, int(d // 10))
    nx, ny = -(b[1] - a[1]) / d, (b[0] - a[0]) / d
    points: list[Pos] = [a]
    side = rng.choice((-1, 1))
    for i in range(1, n + 1):
        t = i / (n + 1)
        off = side * rng.uniform(6, 10)
        side = -side
        points.append((min(cv.w - 3, max(2, round(a[0] + (b[0] - a[0]) * t + nx * off))),
                       min(cv.h - 3, max(2, round(a[1] + (b[1] - a[1]) * t + ny * off)))))
    points.append(b)
    for p, q in zip(points, points[1:]):
        x, y = p
        while (x, y) != q:
            if abs(q[0] - x) >= abs(q[1] - y):
                x += 1 if q[0] > x else -1
            else:
                y += 1 if q[1] > y else -1
            cv.paint([t for t in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)) if cv.inside(*t)], Terrain.GRASS, over=(Terrain.TREES,))


def _forest_roads(cv: _Canvas, rng: random.Random, hc: Pos, natural: Pos | None, thirds: list[Pos]) -> None:
    """The middle clearing, and roads: hall to natural, natural to middle, hall to middle, thirds to middle."""
    middle = (round(cv.centre[0]), round(cv.centre[1]))
    cv.paint(cv.within(cv.centre, 5.5), Terrain.GRASS, over=(Terrain.TREES,))
    legs = [(hc, middle)]
    if natural is not None:
        door = (natural[0] + 1, natural[1] + 1)
        legs = [(hc, door), (door, middle), (hc, middle)]
    for third in thirds:
        legs.append(((third[0] + 1, third[1] + 1), middle))
    for a, b in legs:
        _road(cv, rng, a, b)


# -- Sites -------------------------------------------------------------------------


def _fits(cv: _Canvas, pos: Pos, rects: list[tuple[Pos, int]]) -> bool:
    """Every copy of a mine at *pos* lies off the edge, on ground without water, rock or a layout's
    wall, clear of other footprints and *_SITE_SPACING* from other mine sites."""
    spacing = _SITE_SPACING[cv.point]
    for image in cv.rect_images(pos, 3):
        for x, y in _block(image):
            if not cv.inside(x, y) or cv.grid[y][x] in (Terrain.WATER, Terrain.ROCK) or (x, y) in cv.protected:
                return False
        for (rx, ry), size in rects:
            if size == 3 and max(abs(rx - image[0]), abs(ry - image[1])) < spacing:
                return False
            if rx - 2 <= image[0] <= rx + size + 1 and ry - 2 <= image[1] <= ry + size + 1:
                return False
    return True


def _room(cv: _Canvas, pos: Pos, clearable: bool) -> int:
    kinds = (Terrain.GRASS, Terrain.TREES) if clearable else (Terrain.GRASS,)
    return sum(1 for x, y in cv.within(_mine_centre(pos), 6) if cv.grid[y][x] in kinds)


def _canonical_sites(cv: _Canvas) -> Iterable[Pos]:
    right = cv.w - 6 if cv.point else cv.w // 2 - 5
    for y in range(2, cv.h // 2 - 5):
        for x in range(2, right + 1):
            yield (x, y)


def _pick(cv: _Canvas, scored: list[tuple[float, Pos]], rects: list[tuple[Pos, int]], clearable: bool) -> Pos | None:
    for _score, pos in sorted(scored, reverse=True):
        if _fits(cv, pos, rects) and _room(cv, pos, clearable) >= _SITE_ROOM:
            return pos
    return None


def _natural_site(cv: _Canvas, rng: random.Random, spec: _Spec, hc: Pos, halls: list[Point], rects: list[tuple[Pos, int]],
                  prefer: Callable[[Pos], float] | None) -> Pos | None:
    """As far out as the range allows, half again nearer its own hall than any other."""
    low, high = spec.natural_range
    if not cv.point:
        low = min(low, 9 if spec.layout is not Layout.FOREST else 10)
    scored = []
    for pos in _canonical_sites(cv):
        c = _mine_centre(pos)
        own = _dist(c, halls[0])
        if not low <= own <= high or any(_dist(c, hall) < 1.4 * own for hall in halls[1:]):
            continue
        scored.append((own + rng.uniform(0, 4) + (prefer(pos) if prefer else 0.0), pos))
    return _pick(cv, scored, rects, spec.natural_clearing > 0)


def _third_site(cv: _Canvas, rng: random.Random, spec: _Spec, halls: list[Point], rects: list[tuple[Pos, int]],
                prefer: Callable[[Pos], float] | None) -> Pos | None:
    """Contested ground: at least twelve tiles from every hall, no nearer one hall than the next by more than six."""
    scored = []
    for pos in _canonical_sites(cv):
        c = _mine_centre(pos)
        near = sorted(_dist(c, hall) for hall in halls)
        if near[0] < 12 or near[1] - near[0] > (spec.contested or (6 if cv.point else 12)):
            continue
        scored.append((-(near[1] - near[0]) + rng.uniform(0, 6) + (prefer(pos) if prefer else 0.0), pos))
    return _pick(cv, scored, rects, spec.third_clearing > 0)


# -- Assembly ----------------------------------------------------------------------


def _attempt(rng: random.Random, seed: int, width: int, height: int, players: int, human: int | None, theme: MapTheme,
             races: list[Race], layout: Layout) -> tuple[World, dict]:
    spec = _SPECS[layout]
    cv = _Canvas(width, height, 2 if players == 2 else 4)
    seats = len(cv.images((0, 0)))
    clearing = _clearing(spec, width, height, seats)
    hall, hc = (_MARGIN, _MARGIN), (_MARGIN + 1, _MARGIN + 1)
    main = (_MARGIN - 5, _MARGIN - 4)
    if layout is Layout.FOREST:
        cv.paint(((x, y) for y in range(height) for x in range(width)), Terrain.TREES)
    else:
        _speckle(cv, rng)
    cv.symmetrize()
    cv.paint(cv.within(hc, clearing), Terrain.GRASS)
    cv.paint(_block(main), Terrain.GRASS)
    _clump(cv, (_MARGIN + 9, _MARGIN + 1), 2.6, rng)
    walls = _Walls(set(), set(), [], [])
    if layout is Layout.CROSSINGS:
        _river(cv, rng, walls)
    elif layout is Layout.KLONDIKE:
        _pit(cv, rng, hc, walls)
    elif layout is Layout.BASTION:
        _ring(cv, rng, hc, walls)
    cv.symmetrize()
    halls = [_mine_centre(pos) for pos in cv.rect_images(hall, 3)][:players]
    rects = [(pos, 3) for pos in cv.rect_images(hall, 3)] + [(pos, 3) for pos in cv.rect_images(main, 3)] + walls.rects
    problems: list[str] = []
    natural: Pos | None = None
    if spec.natural:
        natural = _natural_site(cv, rng, spec, hc, halls, rects, walls.prefer_natural)
        if natural is None:
            problems.append("no room for a natural")
        else:
            rects += [(pos, 3) for pos in cv.rect_images(natural, 3)]
            cv.paint(_block(natural), Terrain.GRASS)
            if spec.natural_clearing:
                cv.paint(cv.within(_mine_centre(natural), spec.natural_clearing), Terrain.GRASS, over=(Terrain.TREES,))
    thirds: list[Pos] = []
    for _ in range(_third_orbits(spec, width, height, seats)):
        third = _third_site(cv, rng, spec, halls, rects, walls.prefer_third)
        if third is None:
            problems.append("no room for a third mine")
            break
        thirds.append(third)
        rects += [(pos, 3) for pos in cv.rect_images(third, 3)]
        cv.paint(_block(third), Terrain.GRASS)
        if spec.third_clearing:
            cv.paint(cv.within(_mine_centre(third), spec.third_clearing), Terrain.GRASS, over=(Terrain.TREES,))
    cv.symmetrize()
    if layout is Layout.FOREST:
        _forest_roads(cv, rng, hc, natural, thirds)
        cv.symmetrize()

    world = World(width, height, cv.grid, players, human=human, rng=random.Random(seed), theme=theme, races=races, layout=layout)
    for seat, pos in enumerate(cv.rect_images(hall, 3)[:players]):
        world.place_building(seat, BuildingType.TOWN_HALL, pos)
    mines: list[tuple[Pos, int]] = [(pos, spec.start_gold) for pos in cv.rect_images(main, 3)[:players]]
    if players == 3 and layout is Layout.KLONDIKE:
        mines.append((cv.rect_images(main, 3)[3], POOR_GOLD))  # the empty seat's corner
    if natural is not None:
        mines += [(pos, EXPANSION_GOLD) for pos in cv.rect_images(natural, 3)]  # the empty seat's stays, neutral
    for third in thirds:
        mines += [(pos, EXPANSION_GOLD) for pos in cv.rect_images(third, 3)]
    mines += walls.mines
    for pos, gold in mines:
        world.place_building(None, BuildingType.GOLD_MINE, pos).gold = gold
    for seat in range(players):
        for i in range(3):
            world.spawn_unit(seat, UnitType.PEASANT, tile_center(cv.images((_MARGIN + i, _MARGIN + 3))[seat]))
    _connect(world, cv)
    world.update_vision()
    report = _audit(world, cv, spec, walls, natural)
    report["problems"] = problems + report["problems"]
    return world, report


# -- Connectivity ------------------------------------------------------------------


_CARVE_COST: Final = {Terrain.GRASS: 1.0, Terrain.TREES: 4.0, Terrain.ROCK: 6.0, Terrain.WATER: 12.0}


def reachable(world: World, start: Pos, *, shut: frozenset[Pos] = frozenset()) -> set[Pos]:
    """Every tile a unit standing on *start* can walk to (four-way, the map's own passability),
    treating the *shut* tiles as blocked."""
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in seen and n not in shut and world.passable(*n):
                seen.add(n)
                queue.append(n)
    return seen


def _doors(world: World) -> tuple[list[Pos], list[Pos]]:
    """A passable tile beside every hall, in seat order, and beside every mine."""
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    doors = [world.free_tile_near(h.rect) for h in halls]
    mine_doors = [world.free_tile_near(m.rect) for m in world.mines()]
    assert all(d is not None for d in doors + mine_doors)
    return doors, mine_doors  # type: ignore[return-value]


def _connect(world: World, cv: _Canvas) -> None:
    """Carve two-tile corridors (and their images) until every door reaches the first hall's,
    never through a layout's walls; what stays cut off, the audit reports."""
    doors, mine_doors = _doors(world)
    for goal in doors[1:] + mine_doors:
        if goal in reachable(world, doors[0]):
            continue
        route = _cheapest_route(world, doors[0], goal, cv.protected)
        if route is not None:
            _carve(world, cv, route)


def _cheapest_route(world: World, start: Pos, goal: Pos, protected: set[Pos]) -> list[Pos] | None:
    """Dijkstra where trees, rock and water are merely expensive; buildings, the edge row and
    protected walls stay impassable."""
    best: dict[Pos, float] = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    frontier = [(0.0, start)]
    while frontier:
        cost, current = heapq.heappop(frontier)
        if current == goal:
            route = [goal]
            while route[-1] != start:
                route.append(parent[route[-1]])
            return route
        if cost > best.get(current, float("inf")):
            continue
        x, y = current
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not world.in_bounds(nxt) or world.building_at(nxt) is not None or nxt in protected:
                continue
            if min(nxt[0], nxt[1], world.width - 1 - nxt[0], world.height - 1 - nxt[1]) == 0:
                continue
            new_cost = cost + _CARVE_COST[world.terrain_at(nxt)]
            if new_cost < best.get(nxt, float("inf")):
                best[nxt] = new_cost
                parent[nxt] = current
                heapq.heappush(frontier, (new_cost, nxt))
    return None


def _carve(world: World, cv: _Canvas, route: list[Pos]) -> None:
    for x, y in route:
        for brush in ((x, y), (x + 1, y), (x, y + 1)):
            for nx, ny in cv.images(brush):
                if cv.inside(nx, ny) and (nx, ny) not in cv.protected and world.building_at((nx, ny)) is None \
                        and world.terrain_at((nx, ny)) is not Terrain.GRASS:
                    world.terrain[ny][nx] = Terrain.GRASS
                    world._blocked[ny * world.width + nx] = 0


# -- Audit -------------------------------------------------------------------------


def audit(world: World) -> dict:
    """The numbers a fair start needs, per base: open ground within six tiles of the hall, the
    distance to the nearest mine and to wood, whether every door and mine share one region,
    how many mines there are beyond the main ones, and the terrain mix."""
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    doors, mine_doors = _doors(world)
    region = reachable(world, doors[0])
    report: dict = {"players": len(halls), "layout": world.layout.value, "open": [], "mine": [], "wood": []}
    for hall in halls:
        cx, cy = int(hall.center[0]), int(hall.center[1])
        report["open"].append(sum(1 for dx in range(-6, 7) for dy in range(-6, 7) if world.passable(cx + dx, cy + dy)))
        report["mine"].append(min(max(abs(m.center[0] - hall.center[0]), abs(m.center[1] - hall.center[1])) for m in world.mines()))
        tree = world.nearest_tree(hall.center, 12)
        report["wood"].append(None if tree is None else max(abs(tree[0] - cx), abs(tree[1] - cy)))
    report["connected"] = all(d in region for d in doors + mine_doors)
    report["expansions"] = len(world.mines()) - len(halls)
    total = world.width * world.height
    report["trees"] = sum(1 for row in world.terrain for t in row if t is Terrain.TREES) / total
    report["water"] = sum(1 for row in world.terrain for t in row if t is Terrain.WATER) / total
    return report


def _route(world: World, start: Pos, goal: Pos) -> list[Pos] | None:
    """The production pathfinder's route, or None when its budget runs out first."""
    if start == goal:
        return []
    route = pathing.find_path_grid(start, goal, world._blocked, world.width, world.height)
    return route if route and route[-1] == goal else None


def _audit(world: World, cv: _Canvas, spec: _Spec, walls: _Walls, natural: Pos | None) -> dict:
    report = audit(world)
    problems: list[str] = []
    if not report["connected"]:
        problems.append("a door or mine is cut off")
    if not cv.symmetric(world.terrain):
        problems.append("terrain is not symmetric")
    if any(o < 90 for o in report["open"]):
        problems.append(f"cramped base {report['open']}")
    if any(w is None or w > 12 for w in report["wood"]):
        problems.append(f"no wood in reach {report['wood']}")
    if any(world.terrain_at(tile) is not Terrain.GRASS for b in world.buildings.values() for tile in b.tiles()):
        problems.append("a building stands on trees, water or rock")
    doors, mine_doors = _doors(world)
    routes = {goal: _route(world, doors[0], goal) for goal in doors[1:] + mine_doors}
    if any(route is None for route in routes.values()):
        problems.append("a route exceeds the pathfinder's budget")
    report["detour"] = None
    route = routes.get(doors[1])
    if route is not None:
        walk = sum(pathing.octile(a, b) for a, b in zip([doors[0]] + route, route))
        report["detour"] = walk / _dist(doors[0], doors[1])
    layout = spec.layout
    if layout is Layout.FOREST:
        if report["trees"] < 0.35:
            problems.append(f"woods too thin {report['trees']:.2f}")
        if report["detour"] is not None and report["detour"] < 1.1:
            problems.append(f"roads too straight {report['detour']:.2f}")
    elif layout is Layout.CROSSINGS:
        fords = frozenset(cv.orbit(walls.fords))
        if doors[1] in reachable(world, doors[0], shut=fords):
            problems.append("the banks join off the fords")
    elif layout is Layout.KLONDIKE:
        gates = frozenset(cv.orbit(walls.gates))
        pit = [world.free_tile_near((x, y, 3, 3)) for (x, y), gold in walls.mines if gold == EXPANSION_GOLD]
        if any(door in reachable(world, doors[0], shut=gates) for door in pit):
            problems.append("the pit is open beside its gates")
    elif layout is Layout.BASTION and natural is not None:
        gates = frozenset(cv.orbit(walls.gates))
        for seat, pos in enumerate(cv.rect_images(natural, 3)[:len(doors)]):
            door = world.free_tile_near((pos[0], pos[1], 3, 3))
            if door in reachable(world, doors[seat], shut=gates):
                problems.append(f"seat {seat}'s ring is open beside its gate")
    report["fords"] = sorted(cv.orbit(walls.fords))
    report["gates"] = sorted(cv.orbit(walls.gates))
    report["problems"] = problems
    return report
