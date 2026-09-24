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

import functools
import heapq
import math
import random
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from warband.sim import camps as camping
from warband.sim import path as pathing
from warband.sim.model import MINE_CLEARANCE, RIFT, Pos, World, rects_gap, tile_center
from warband.sim.rules import (BUILDINGS, EXPANSION_GOLD, MAX_PLAYERS, MINE_GOLD, BuildingType, Layout, MapTheme, Race, Terrain,
                               UnitType)

SIZES: Final[dict[str, tuple[int, int]]] = {
    # Nominal tiles; :func:`dimensions` rounds a size up to whole cells of the seat count's grid.
    # The first three are what shipped and are left where they are: the measured difficulty ratings
    # (brains.DIFFICULTY_ELO) and the balance league were played on them, and league.arena keeps its
    # own copy of them so a new entry here never moves the ladder.
    "Small": (48, 40),      # 1 920 tiles
    "Medium": (64, 48),     # 3 072
    "Large": (80, 64),      # 5 120
    "Huge": (108, 84),      # 9 072
    "Giant": (144, 108),    # 15 552
    "Epic": (180, 132),     # 23 760 — sixteen seats at the per-seat room a Large four-player map gives
}
#: The seat counts New game offers: every one of them tiles a map exactly (three fills three of four cells).
SEAT_COUNTS: Final[tuple[int, ...]] = (2, 3, 4, 6, 8, 12, 16)
#: Seats to the ``cols x rows`` grid of congruent cells they are dealt.  Two and four are the point
#: reflection and the two mirrors that shipped; three fills three cells of the four.  A count that
#: leaves a cell empty leaves its natural behind as a neutral mine, as three players always have.
#:
#: Every axis has an even number of cells or exactly one, and no other count will do.  Neighbouring
#: cells mirror each other, so the canonical column a map edge shows alternates along the axis: with
#: an even number the two edges show the same one and the map's rim is a single orbit, and with one
#: cell the two edges *are* the two ends of the cell.  With an odd number they differ, and then one
#: seat's rim is the forest fringe while another's is open ground, or one seat's share of a feature
#: on a crossing of cells is cut off by the map's edge.
_GRIDS: Final[dict[int, tuple[int, int]]] = {
    2: (1, 2), 3: (2, 2), 4: (2, 2), 5: (6, 1), 6: (6, 1), 7: (4, 2), 8: (4, 2),
    9: (6, 2), 10: (6, 2), 11: (6, 2), 12: (6, 2), 13: (4, 4), 14: (4, 4), 15: (4, 4), 16: (4, 4),
}
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
#: A gold seam is the endless deposit (:class:`~warband.sim.rules.MineInfo`): five tiles across instead of
#: three, twenty gold a trip instead of a hundred, and it never runs out.  It is worth what holding it is
#: worth, so it goes on the maps whose matches are long and whose middle is far from home, and nowhere else:
#: the three shipped sizes keep the economy their difficulty ratings and their balance league were measured on.
_SEAM_MAP: Final = 5200  # tiles of map a seam wants more of; a Large (80x64) is 5120
_SEAM_CELL: Final = 1000  # tiles of a seat's own cell: a smaller share has no middle to put a five-tile dig in
_SEAM_AWAY: Final = 18  # tiles from every hall: past the natural, out where a seat has to go and stay
_SEAM_ROOM: Final = 110  # open tiles within eight of a seam, against _SITE_ROOM within six of a natural
_MARGIN: Final = 7  # tiles from a cell's corner to a corner hall's top-left
_CLEARING: Final = 7  # radius of open ground around the hall's middle tile
_SITE_SPACING: Final = {True: 8, False: 7}  # Chebyshev tiles between mine sites, by whether the cell spans the map (mirrored cells are tighter)
_SITE_ROOM: Final = 60  # open tiles within six of a natural or third, so a hall and farms fit
_MIN_CELL: Final = (24, 20)  # the smallest share of a map that has ever made a fair base: Small with four seats
_MAX_CELL: Final = 5000  # the largest share a seat can hold: beyond it the walk to the next base is the whole match
_GLADE_ROOM: Final = 1300  # tiles of a Forest cell per extra clearing cut in it, beyond the two the layout always cuts
#: A creature camp squats beside a *contested* deposit -- a third mine or a gold seam -- and never beside a
#: seat's own mine or its natural.  That is the whole placement rule, and it is what the camps are for: the
#: opening is untouched, the expansion every build order needs is free, and the ground a player has to leave
#: home for is held by something.  A seat that wants the middle now has to take it from somebody at minute
#: four, which is a job for an army that is otherwise pure cost until the timing push (docs/balance.md).
# Tiles between the deposit's middle and its lair's: near enough to guard it, not on top of it.  Two numbers
# rather than a pair, because a Final tuple is a value the compiled simulation does not always set
# (mypyc inlines a Final scalar and leaves a Final tuple's slot empty; docs/fast-simulation.md).
_CAMP_NEAREST: Final = 4.5
_CAMP_FURTHEST: Final = 9.0
_CAMP_SPACING: Final = 5  # Chebyshev tiles between a lair's corner and any other footprint's: two tiles of daylight
_CAMP_ROOM: Final = 40  # open tiles within six of a lair, so an army has somewhere to fight
#: What each kind of camp is made of and what its den is sitting on.  A third mine draws one of the two
#: small camps; the endless seam, worth the most and standing furthest out, is always the big one.
_ROSTERS: Final[dict[str, tuple[tuple[UnitType, ...], int]]] = {
    "den": ((UnitType.WOLF,) * 4, 500),
    "nest": ((UnitType.SPIDER, UnitType.SPIDER, UnitType.WOLF, UnitType.WOLF), 600),
    "lair": ((UnitType.TROLL, UnitType.GOLEM, UnitType.SPIDER, UnitType.SPIDER), 1500),
}

#: Ley rifts (WB-063).  Every seat gets one near its hall, in its own cell, and a cell with room for a middle gets a
#: contested one out in the shared ground: each a canonical site copied a cell at a time, like a mine.  They are laid
#: last, on the finished ground, from a stream of their own (seeded apart from the map's), and they never paint a tile:
#: a rift goes only on open grass the first hall can already walk to.  So every map that was drawn before them is
#: drawn exactly as it was, with its rifts on top, and a seed that made a fair map still makes the same one.
_RIFT_SALT: Final = 0x21F7
_RIFT_HOME: Final = (4.5, 8.0)  # tiles from the hall's middle to its rift's: in the clearing, off the hall's doorstep
_RIFT_HALL_GAP: Final = 2  # tiles of daylight between a rift and a hall or any other building of a seat's
_RIFT_DEPOSIT_GAP: Final = 3  # ...and between a rift and a deposit: a vault never stands in a mine's mouth
_RIFT_WALL_GAP: Final = 2  # tiles between a rift and a gate or a ford, which a vault must never plug
_RIFT_SPACING: Final = 6  # Chebyshev tiles between two rifts' squares
_RIFT_CELL: Final = 750  # tiles of a seat's cell that earn it a contested rift: Small with two seats has one, with four none
_RIFT_AWAY: Final = 12  # tiles from every hall to a contested rift's middle: a third mine's distance
_RIFT_ROOM: Final = 36  # open tiles within four of a contested rift's middle, so its vault never plugs a road
_RIFT_RING: Final = 8  # of the twelve tiles round a rift, how many must be open ground the first hall reaches
_RIFT_LAIR: Final = 6.0  # tiles from a lair's middle to a rift's: outside its guards' ring, not outside its watch

Point = tuple[float, float]


def fresh_seed() -> int:
    """Choose a new map seed within the online protocol's signed 32-bit range."""
    return random.randrange(1, 2**31)


class NoFairMap(ValueError):
    """The layout cannot make a fair map at that size for that many players."""


def grid(seats: int) -> tuple[int, int]:
    """The ``cols x rows`` grid of congruent cells *seats* are dealt, one seat a cell.

    Two seats get one column of two cells (the point reflection that shipped), three and four a
    two-by-two (the two mirrors that shipped, with three leaving one cell empty).  Above that the
    grid is the one that wastes fewest cells while keeping them as square as a base wants."""
    if not 1 <= seats <= MAX_PLAYERS:
        raise ValueError(f"1 to {MAX_PLAYERS} players, not {seats}")
    return (1, 1) if seats == 1 else _GRIDS[seats]



def dimensions(size: str, seats: int) -> tuple[int, int]:
    """The nominal *size* rounded up until the seat count's grid divides it exactly.

    Cells must be congruent to the tile, so a map is only ever as wide as a whole number of cells.
    Every shipped size already divides by the grids of two, three and four seats, so those maps are
    the maps they always were."""
    width, height = SIZES[size]
    cols, rows = grid(seats)
    return (-(-width // cols) * cols, -(-height // rows) * rows)


def refusal(width: int, height: int, seats: int, layout: Layout | None) -> str | None:
    """Why this map cannot be fair for this many seats, or ``None`` when it can.

    A seat's share of the map has to hold a base; some layouts want more of it than others, and an
    unfair map is worse than a refused one.  Under Any (``layout=None``) the seed draws from the
    layouts this map can hold, so Any is refused only when none of them can."""
    cols, rows = grid(seats)
    if width % cols or height % rows:
        return f"{seats} seats need {cols}x{rows} whole cells, which {width}x{height} tiles do not make"
    cw, ch = width // cols, height // rows
    if cw < _MIN_CELL[0] or ch < _MIN_CELL[1]:
        return f"{seats} seats leave {cw}x{ch} tiles each; a base needs {_MIN_CELL[0]}x{_MIN_CELL[1]}"
    if cw * ch > _MAX_CELL:
        return f"{seats} seats on {width}x{height} tiles give each {cw * ch} tiles to hold, more than {_MAX_CELL}"
    if layout is not None:
        return _layout_refusal(_SPECS[layout], cols, rows, cw, ch)
    reasons = [_layout_refusal(_SPECS[candidate], cols, rows, cw, ch) for candidate in Layout]
    return None if any(why is None for why in reasons) else reasons[0]


def layouts_for(width: int, height: int, seats: int) -> tuple[Layout, ...]:
    """The layouts this map can hold fairly for this many seats: what Any draws from."""
    return tuple(one for one in Layout if _layout_refusal(_SPECS[one], *grid(seats), width // grid(seats)[0], height // grid(seats)[1]) is None)


def offered(size: str, layout: Layout | None = None) -> tuple[int, ...]:
    """The seat counts a size can seat fairly, biggest map to most seats."""
    return tuple(n for n in SEAT_COUNTS if refusal(*dimensions(size, n), n, layout) is None)


def start_guesses(width: int, height: int, seats: int, inset: float = 2.5) -> list[Point]:
    """Where a brain that has found nobody yet should go looking for them.

    Up to four seats sit in the map's corners, and the corners are the guess they have always been.
    Beyond that the seats are dealt one to a cell of a grid, so the guess is the middle of each
    cell; a map whose shape is nobody's (a mission, a test) falls back to the corners."""
    cols, rows = grid(seats) if 2 <= seats <= MAX_PLAYERS else (2, 2)
    if seats <= 4 or width % cols or height % rows:
        return [(inset, inset), (width - inset, inset), (inset, height - inset), (width - inset, height - inset)]
    cw, ch = width // cols, height // rows
    return [(col * cw + cw / 2, row * ch + ch / 2) for row in range(rows) for col in range(cols)]


def size_name(width: int, height: int, seats: int) -> str:
    """What this map would be called on the New game screen, or its tiles when it is nobody's size."""
    for name in SIZES:
        if dimensions(name, seats) == (width, height):
            return name
    return f"{width}×{height}"


def sizes_for(seats: int, layout: Layout | None = None) -> tuple[str, ...]:
    """The sizes that seat this many fairly, in the order :data:`SIZES` lists them."""
    return tuple(name for name in SIZES if refusal(*dimensions(name, seats), seats, layout) is None)


def _layout_refusal(spec: _Spec, cols: int, rows: int, cw: int, ch: int) -> str | None:
    """What a layout's own walls need of a cell that the cell does not have."""
    hall = _hall_corner(cols, rows, cw, ch)
    if spec.layout is Layout.BASTION:
        # The ring is drawn round the hall and must close inside the cell: where the hall sits in a
        # cell's middle there is no map edge to lean the ring against, as there is with two cells.
        reach = 2 * (_CLEARING + 4.0 + 1)
        if (cols > 2 and cw < reach) or (rows > 2 and ch < reach):
            return f"Bastion's tree ring needs {int(reach)} tiles across a cell, not {cw}x{ch}"
    if spec.layout is Layout.KLONDIKE:
        # The pit sits where cells meet; a base that stands inside its rock ring is no base.
        junction = _junction(cols, rows, cw, ch)
        keep = _clearing(spec, cw, ch, cols == 1) + _pit_inner(cw * cols, ch * rows) + 4
        if _dist(_mine_centre(hall), junction) < keep:
            return f"Klondike's pit would swallow a base {cw}x{ch} tiles from it"
    return None


def generate(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0, theme: MapTheme = MapTheme.SUMMER,
             races: Sequence[Race | None] | None = None, layout: Layout | None = None, wilds: bool = True) -> World:
    """*races* names each player's race; ``None`` entries are drawn from the seed, so a seed reproduces
    the whole match.  Without a list the *human* leads Humans and the computer players are drawn.
    *layout* ``None`` draws one from the seed.  *wilds* ``False`` leaves the contested deposits unguarded,
    which is how a map is measured against one with camps on it."""
    return build(seed, width, height, players, human, theme, races, layout, wilds)[0]


def build(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0, theme: MapTheme = MapTheme.SUMMER,
          races: Sequence[Race | None] | None = None, layout: Layout | None = None, wilds: bool = True) -> tuple[World, dict]:
    """:func:`generate` plus the audit report of the map it settled on (``attempt`` counts the retries)."""
    if not 2 <= players <= MAX_PLAYERS:
        raise ValueError(f"2 to {MAX_PLAYERS} players, not {players}")
    if races is not None and len(races) != players:
        raise ValueError(f"{players} players need {players} races, not {len(races)}")
    if min(width, height) < 40:
        raise ValueError(f"maps are at least 40 tiles on their shorter side, not {width}x{height}: symmetric seats need the room")
    why = refusal(width, height, players, layout)
    if why is not None:
        raise NoFairMap(f"No fair map at {width}x{height} for {players} players: {why}.")
    if layout is None:
        choices = layouts_for(width, height, players) if width % grid(players)[0] == 0 and height % grid(players)[1] == 0 else ()
        layout = random.Random(seed ^ 0x1A70).choice(choices or list(Layout))
    wanted: list[Race | None] = list(races) if races is not None else [Race.HUMAN if i == human else None for i in range(players)]
    chosen = draw_races(wanted, random.Random(seed ^ 0x5ACE))
    problems: list[str] = []
    without: tuple[World, dict] | None = None  # the best map so far that is fair but is missing something wished for
    for attempt in range(RETRIES):
        world, report = _attempt(random.Random(seed * 16 + attempt), seed, width, height, players, human, theme, chosen, layout, wilds,
                                 random.Random((seed * 16 + attempt) ^ _RIFT_SALT))
        report["attempt"] = attempt
        if not report["problems"]:
            if not report["wishes"]:
                return world, report
            if without is None:
                without = (world, report)
        problems = report["problems"] or report["wishes"]
    # A fault makes a map unfair and there is nothing to do but raise; a wish is a feature the layout's
    # own walls left no room for on this seed.  A gold seam is the one wish there is: eight seeds are
    # given the chance to fit one in, and a map that has everything else is a map, not a refusal.
    if without is not None:
        return without
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


@functools.lru_cache(maxsize=None)
def _cells(cols: int, rows: int) -> tuple[tuple[int, int, bool, bool], ...]:
    """Every cell as ``(col, row, flip_x, flip_y)``, in seat order.

    Neighbouring cells are mirror images of each other, so the cell they share a border with shows
    the same tiles from both sides and every cell is an exact congruent copy of the canonical one.
    A grid one cell wide (or one tall) has no border to mirror across on that axis, so its cells
    alternate in *both* axes instead: that is the point reflection two seats have always had.
    Seats take the cells in checkerboard order, so the first two are diagonally opposite and a
    count that does not fill the grid (three seats of four) leaves a corner cell empty, as before."""
    out = []
    for parity in (0, 1):
        for row in range(rows):
            for col in range(cols):
                if (col + row) % 2 != parity:
                    continue
                flip_x = row % 2 if cols == 1 else col % 2
                flip_y = col % 2 if rows == 1 else row % 2
                out.append((col, row, bool(flip_x), bool(flip_y)))
    return tuple(out)


def _fold(cols: int, rows: int, cw: int, ch: int, pos: Pos, size: int = 1) -> Pos:
    """Which square of the canonical cell the *size* square at *pos* is a copy of.

    Layout passes draw features that straddle a junction of cells and corridors are carved wherever
    they are needed, so a square handed back is not always one of the canonical cell's own."""
    col, lx = divmod(pos[0], cw)
    row, ly = divmod(pos[1], ch)
    flip_x = row % 2 if cols == 1 else col % 2
    flip_y = col % 2 if rows == 1 else row % 2
    return (cw - size - lx if flip_x else lx, ch - size - ly if flip_y else ly)


def _images(cols: int, rows: int, cw: int, ch: int, pos: Pos, size: int = 1) -> tuple[Pos, ...]:
    """The copies of the *size* square whose top-left is the canonical *pos*, one a cell, seat order."""
    x, y = pos
    return tuple((col * cw + (cw - size - x if fx else x), row * ch + (ch - size - y if fy else y))
                 for col, row, fx, fy in _cells(cols, rows))


def cell_images(width: int, height: int, seats: int, pos: Pos, size: int = 1) -> tuple[Pos, ...]:
    """Where a map of this shape sends the *size* square at *pos*: one copy per cell, in seat order.

    Whatever the generator draws for the first seat, every other seat has exactly; this is the
    symmetry the audit and the tests read.  *pos* may be in any cell — it is folded into the
    canonical one first, so the orbit of a square is the same wherever it is named from."""
    cols, rows = grid(seats)
    cw, ch = width // cols, height // rows
    return _images(cols, rows, cw, ch, _fold(cols, rows, cw, ch, pos, size), size)


def _hall_corner(cols: int, rows: int, cw: int, ch: int) -> Pos:
    """The hall's top-left tile inside the canonical cell.

    With one or two cells on an axis the mirror throws a hall near the cell's edge out to the map's
    own edge, which is where halls have always stood.  With three or more it would throw two halls
    together against their shared border instead, so the hall sits in the middle of the cell and
    every seat is the same distance from the next."""
    x = _MARGIN if cols <= 2 else (cw - 3) // 2
    y = _MARGIN if rows <= 2 else (ch - 3) // 2
    return (x, y)


def _junction(cols: int, rows: int, cw: int, ch: int) -> Point:
    """Where cells meet at the canonical cell's far corner: the map's centre when the grid is one
    or two cells each way, and one of several crossings on a bigger grid.  A feature drawn around
    it in the canonical cell is assembled whole by the copies, which is how the pit and the river
    have always been built."""
    return (cw - 0.5 if cols > 1 else (cw - 1) / 2, ch - 0.5 if rows > 1 else (ch - 1) / 2)


class _Canvas:
    """The terrain under construction and the symmetry that copies the first seat to the others.

    The map is a ``cols x rows`` grid of congruent cells, one to a seat.  Everything is drawn for
    the first seat in the *canonical* cell (the top-left one, ``cw`` by ``ch`` tiles);
    :meth:`symmetrize` copies it onto the images.  A feature that straddles a junction of cells (a
    pit on it, a river through it) is drawn whole and the copies reassemble it."""

    def __init__(self, width: int, height: int, seats: int) -> None:
        self.w, self.h = width, height
        self.cols, self.rows = grid(seats)
        if width % self.cols or height % self.rows:
            raise ValueError(f"{seats} seats need {self.cols}x{self.rows} whole cells, not {width}x{height}")
        self.cw, self.ch = width // self.cols, height // self.rows
        #: The canonical cell spans the map's full width: the roomy half-map two seats share.
        self.wide = self.cols == 1
        self.grid = [[Terrain.GRASS] * width for _ in range(height)]
        self.protected: set[Pos] = set()  # walls no corridor may be carved through
        #: Where the canonical cell meets its neighbours; the centre of the map on a small grid.
        self.junction: Point = _junction(self.cols, self.rows, self.cw, self.ch)

    def images(self, pos: Pos) -> tuple[Pos, ...]:
        """*pos* and its copies, one per cell, in seat order.  A tile outside the canonical cell is
        folded into it first, so the orbit of any tile of the map is the orbit of its canonical one."""
        here = pos if 0 <= pos[0] < self.cw and 0 <= pos[1] < self.ch else _fold(self.cols, self.rows, self.cw, self.ch, pos)
        return _images(self.cols, self.rows, self.cw, self.ch, here)

    def rect_images(self, pos: Pos, size: int) -> tuple[Pos, ...]:
        """Top-left tiles of the copies of a *size* square at *pos*, in seat order.  *pos* is a
        canonical tile: a footprint is only ever placed inside one cell."""
        return _images(self.cols, self.rows, self.cw, self.ch, pos, size)

    def orbit(self, tiles: Iterable[Pos]) -> set[Pos]:
        return {image for tile in tiles for image in self.images(tile)}

    def symmetrize(self) -> None:
        grid = self.grid
        for y in range(self.ch):
            for x in range(self.cw):
                kind = grid[y][x]
                for ix, iy in self.images((x, y))[1:]:
                    grid[iy][ix] = kind
        self.protected = self.orbit(self.protected)

    def frame(self) -> None:
        """Forest round the whole map, once the copying is done.

        The rim is the map's frame, not a cell's ground: the canonical column it shows in one cell
        is an inner column of the next, which a road may need open.  So the rim is painted like any
        other tile while the map is drawn and put back to forest here, at the end."""
        for x in range(self.w):
            self.grid[0][x] = self.grid[self.h - 1][x] = Terrain.TREES
        for y in range(self.h):
            self.grid[y][0] = self.grid[y][self.w - 1] = Terrain.TREES

    def symmetric(self, terrain: list[list[Terrain]]) -> bool:
        """Every cell is the canonical one, tile for tile, on every tile of it that is in play.

        Reading the canonical cell alone covers the map: the cells partition it.  A tile whose
        copies include one on the map's rim is left out — with more than two cells on an axis the
        rim is a cell's own column in one place and an inner one in another, and the rim is a frame
        nobody walks on, so what stands there decides no match."""
        for y in range(self.ch):
            for x in range(self.cw):
                images = self.images((x, y))
                if any(not self.inside(ix, iy) for ix, iy in images):
                    continue
                kind = terrain[y][x]
                if any(terrain[iy][ix] is not kind for ix, iy in images):
                    return False
        return True

    def inside(self, x: int, y: int) -> bool:
        """Within the map and off its edge row, which stays forest."""
        return 0 < x < self.w - 1 and 0 < y < self.h - 1

    def disc(self, centre: Point, radius: float) -> list[Pos]:
        """:meth:`within`, but the map's rim counts: see :meth:`frame`."""
        cx, cy = centre
        r = int(radius) + 1
        return [(x, y) for y in range(int(cy) - r, int(cy) + r + 2) for x in range(int(cx) - r, int(cx) + r + 2)
                if 0 <= x < self.w and 0 <= y < self.h and (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius]

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


def _block(pos: Pos, gap: int = 1, size: int = 3) -> list[Pos]:
    """A *size* mine at *pos* and *gap* tiles around it."""
    return [(pos[0] + dx, pos[1] + dy) for dy in range(-gap, size + gap) for dx in range(-gap, size + gap)]


def _mine_centre(pos: Pos, size: int = 3) -> Point:
    return (pos[0] + size / 2, pos[1] + size / 2)


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
    seam: bool = False  # an endless gold seam out in the shared ground, where the map is big enough for one
    contested: int | None = None  # how many tiles nearer one hall than the next a third may be; None: the symmetry's default
    start_gold: int = MINE_GOLD


#: Three of the five layouts hold a seam, and each for its own reason.  Plains is open ground where
#: expansions lie exposed, so a deposit nobody can exhaust is exactly the thing to fight over.
#: Crossings already asks who holds the fords, and a seam on the far bank gives the answer a price.
#: Bastion promises a boom in safety and then a fight for the middle, and the seam is what the middle
#: is finally worth.  Forest has none: its clearings and roads are cut by hand and a five-tile dig
#: with its open ground around it would take a base's worth of woods out of a layout whose whole
#: promise is that the woods are thick.  Klondike has none either: little gold at home and the rest
#: in a walled pit is a deliberate shape of economy, and an endless trickle outside the pit unmakes it.
#: Plains and Crossings also have short home mines: their free naturals should be fought over
#: during an ordinary match, before a player has already won from one safe deposit.
_SPECS: Final[dict[Layout, _Spec]] = {
    Layout.PLAINS: _Spec(Layout.PLAINS, seam=True, start_gold=15_000),
    Layout.FOREST: _Spec(Layout.FOREST, clearing=9, natural_range=(13, 18), natural_clearing=5, third_clearing=4),  # a full base needs the room; four seats get less, see _clearing
    Layout.CROSSINGS: _Spec(Layout.CROSSINGS, contested=14, seam=True, start_gold=20_000),  # the river runs down the bisector; thirds sit on its banks
    Layout.KLONDIKE: _Spec(Layout.KLONDIKE, clearing=6, natural=False, thirds=False, start_gold=KLONDIKE_START_GOLD),
    Layout.BASTION: _Spec(Layout.BASTION, natural_range=(12, 18), seam=True),
}


@dataclass
class _Walls:
    """What a layout's wall pass leaves for the site search and the audit, in first-seat coordinates."""

    gates: set[Pos]
    fords: set[Pos]
    rects: list[tuple[Pos, int]]  # footprints the site search must avoid, all seats
    mines: list[tuple[Pos, BuildingType, int]]  # (top-left, kind, gold) of the layout's own mines, all seats
    prefer_natural: Callable[[Pos], float] | None = None
    prefer_third: Callable[[Pos], float] | None = None


def _clearing(spec: _Spec, cw: int, ch: int, wide: bool) -> int:
    """The base clearing's radius: Forest's generous nine shrinks to eight, then seven, where a
    seat's cell is small, or the woods between the seats would be too thin to matter."""
    if spec.layout is not Layout.FOREST or wide:
        return spec.clearing
    return 8 if cw * ch >= 750 else 7


def _third_orbits(spec: _Spec, cw: int, ch: int) -> int:
    """How many contested mine sites (each copied to every seat) a map gets, by the room a seat
    has: a cell under 625 tiles has no middle to put one in."""
    if not spec.thirds:
        return 0
    room = cw * ch
    orbits = 0 if room < 625 else 1 if room < 1250 else 2
    # Plains is open ground where expansions lie exposed: fewer mines there
    # contest the second base, so waiting at home costs what Klondike charges
    # for the pit. The other layouts keep their mines; Forest's woods and
    # Bastion's ring already make a second base safe.
    if spec.layout is Layout.PLAINS:
        orbits = min(orbits, 1)
    return orbits


def _wants_a_seam(spec: _Spec, width: int, height: int, cw: int, ch: int) -> bool:
    """Whether this map gets an endless seam (one, copied to every seat, so one seat one seam): on a
    layout that holds them, on a map bigger than the shipped three, where a seat's own cell has the
    middle ground to put it in.  A match on a map that size is a long one, which is what a deposit
    whose worth is how long you keep it is for."""
    return spec.seam and width * height >= _SEAM_MAP and cw * ch >= _SEAM_CELL


def _pit_inner(width: int, height: int) -> int:
    """The open radius inside Klondike's rock ring."""
    return max(6, min(9, round(min(width, height) * 0.18)))


def _river(cv: _Canvas, rng: random.Random, walls: _Walls) -> None:
    """Two players: one river from the crossing of the cells to the far edge, wandering, and its
    reflection.  Any other grid: a straight cross of two rivers of varying width, which the copies
    repeat at every crossing of cells, so each cell is moated on two sides.  A wide ford on the
    crossing, a narrow one near each end, rock outcrops on the banks beside the wide ford."""
    cx, cy = cv.junction
    radius = 1.5 if min(cv.w, cv.h) < (48 if cv.wide else 64) else 2.0 if min(cv.w, cv.h) < 64 else 2.5
    headings = [-math.pi / 4] if cv.wide else [math.pi, -math.pi / 2]
    fords: set[Pos] = set()
    for base in headings:
        points: list[Point] = []
        x, y, heading, travelled = cx, cy, base, 0.0
        while cv.inside(round(x), round(y)):
            points.append((x, y))
            if cv.wide and travelled > 5:
                heading = min(base + 0.7, max(base - 0.7, heading + rng.uniform(-0.4, 0.4)))
            x, y, travelled = x + 3 * math.cos(heading), y + 3 * math.sin(heading), travelled + 3
        widths = [radius if cv.wide else radius + rng.uniform(0, 0.8) for _ in points]
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
    # Bias the first expansion toward the central passage, where the opponent can contest it.
    walls.prefer_natural = lambda pos: -_dist(_mine_centre(pos), cv.junction)
    walls.prefer_third = lambda pos: -min(_dist(_mine_centre(pos), f) for f in cv.orbit(fords))


def _cut(river: set[Pos], at: Point, heading: float, half_length: float) -> set[Pos]:
    """The river tiles within *half_length* along *heading* of *at*: a ford right across the water."""
    dx, dy = math.cos(heading), math.sin(heading)
    return {(x, y) for x, y in river if abs((x - at[0]) * dx + (y - at[1]) * dy) <= half_length}


def _pit(cv: _Canvas, rng: random.Random, hc: Pos, walls: _Walls) -> None:
    """A rock ring on the crossing of the cells with a gate towards every seat; the gold inside,
    and a poor mine in the far half of the cell when the cell spans the map.  On a grid of more
    than two cells an axis the copies build one pit at every crossing, one for each group of four
    cells that meet there."""
    cx, cy = cv.junction
    inner = _pit_inner(cv.w, cv.h)
    ring = cv.band((cx, cy), inner, inner + 3)
    cv.paint(ring, Terrain.ROCK)
    cv.paint(cv.within((cx, cy), inner - 0.5), Terrain.GRASS)
    angle = math.atan2(hc[1] - cy, hc[0] - cx) + rng.uniform(-0.5, 0.5)
    gate = cv.along_ray(ring, (cx, cy), angle, 2.0)
    cv.paint(gate, Terrain.GRASS)
    walls.gates = set(gate)
    cv.protected |= set(ring) - set(gate)
    offsets = [(-3.5, -1.5)] + ([(3.5, -3.5)] if inner >= 8 else []) if cv.wide else [(-3.5, -2.5)]
    for ox, oy in offsets:
        pos = (round(cx + ox) - 1, round(cy + oy) - 1)
        for image in cv.rect_images(pos, 3):
            walls.mines.append((image, BuildingType.GOLD_MINE, EXPANSION_GOLD))
            walls.rects.append((image, 3))
    if cv.wide:
        poor = (cv.cw - _MARGIN - 3, _MARGIN)
        cv.paint(_block(poor), Terrain.GRASS)
        for image in cv.rect_images(poor, 3):
            walls.mines.append((image, BuildingType.GOLD_MINE, POOR_GOLD))
            walls.rects.append((image, 3))


def _ring(cv: _Canvas, rng: random.Random, hc: Pos, walls: _Walls) -> None:
    """A tree ring round the base clearing with a three-tile gate facing along the home edge.
    Mirror maps get a thinner ring and gates along the map's long axis, so the quadrant beside
    keeps room for the natural and the two facing gates share the middle column."""
    band = cv.band(hc, _CLEARING + 1, _CLEARING + 4.5) if cv.wide else cv.band(hc, _CLEARING + 1, _CLEARING + 3.5)  # the main mine's far corner is 7.8 out
    cv.paint(band, Terrain.TREES)
    angle = rng.choice((0.0, math.pi / 2)) if cv.wide else 0.0
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


def _glades(cv: _Canvas, rng: random.Random, hc: Pos) -> list[Pos]:
    """Extra clearings for a cell with room to spare, so a big Forest map is woods with glades in
    it rather than one solid block of trees: one per :data:`_GLADE_ROOM` tiles beyond the two the
    layout always cuts.  Every shipped cell is small enough to get none."""
    wanted = max(0, cv.cw * cv.ch // _GLADE_ROOM - 1)
    out: list[Pos] = []
    for _ in range(wanted):
        best: Pos | None = None
        best_score = 0.0
        for _try in range(40):
            spot = (rng.randrange(6, cv.cw - 6), rng.randrange(6, cv.ch - 6))
            near = min([_dist(spot, hc)] + [_dist(spot, other) for other in out])
            if near > best_score:
                best, best_score = spot, near
        if best is None or best_score < 12:
            break
        out.append(best)
    return out


def _meetings(cv: _Canvas) -> list[Pos]:
    """Where the canonical cell's roads must reach for the woods to be one road network.

    With at most two cells on each axis every cell meets every other at one point — the middle of
    the map — and one road to it is the whole network, which is what shipped.  On a bigger grid the
    cells meet along borders of two kinds (the mirror shows the cell's near column at one and its
    far column at the next), so a road must reach the middle of every border; leave one out and the
    connector tunnels a dead-straight corridor through the trees to join what the roads did not."""
    if cv.cols <= 2 and cv.rows <= 2:
        return [(round(cv.junction[0]), round(cv.junction[1]))]
    across = [(0, cv.ch // 2), (cv.cw - 1, cv.ch // 2)] if cv.cols > 1 else []
    down = [(cv.cw // 2, 0), (cv.cw // 2, cv.ch - 1)] if cv.rows > 1 else []
    return across + down


def _forest_roads(cv: _Canvas, rng: random.Random, hc: Pos, natural: Pos | None, thirds: list[Pos]) -> None:
    """The middle clearing, and roads: hall to natural, natural to the meeting, hall to every
    meeting, thirds to the nearest one, and a leg through every glade a roomy cell earns."""
    meetings = _meetings(cv)
    middle = meetings[0]
    if cv.cols <= 2 and cv.rows <= 2:
        cv.paint(cv.within(cv.junction, 5.5), Terrain.GRASS, over=(Terrain.TREES,))
    else:
        for meeting in meetings:
            # A clearing, not a road end: where the mirror is in the other axis (a grid one cell
            # tall) the copies of a single tile land diagonally apart, and nothing walks a diagonal.
            cv.paint(cv.disc(meeting, 2.5), Terrain.GRASS, over=(Terrain.TREES,))
    legs = [(hc, middle)]
    if natural is not None:
        door = (natural[0] + 1, natural[1] + 1)
        legs = [(hc, door), (door, middle), (hc, middle)]
    legs += [(hc, other) for other in meetings[1:]]
    nearest = lambda spot: min(meetings, key=lambda m: _dist(spot, m))
    for third in thirds:
        door = (third[0] + 1, third[1] + 1)
        legs.append((door, nearest(door)))
    for glade in _glades(cv, rng, hc):
        cv.paint(cv.within(glade, 5.0), Terrain.GRASS, over=(Terrain.TREES,))
        legs.append((glade, nearest(glade)))
    for a, b in legs:
        _road(cv, rng, a, b)


# -- Sites -------------------------------------------------------------------------


def _fits(cv: _Canvas, pos: Pos, rects: list[tuple[Pos, int]], size: int = 3, spacing: int | None = None) -> bool:
    """Every copy of a *size* mine at *pos* lies off the edge, on ground without water, rock or a
    layout's wall, clear of other footprints and *_SITE_SPACING* from other mine sites.

    A deposit wider than the three tiles every mine had wants that much more room on each side, and
    *slack* is that much and no more: it is zero for two 3x3 sites, so every map that was drawn
    before the seams existed is drawn exactly as it was."""
    if spacing is None:
        spacing = _SITE_SPACING[cv.wide]
    for image in cv.rect_images(pos, size):
        for x, y in _block(image, size=size):
            if not cv.inside(x, y) or cv.grid[y][x] in (Terrain.WATER, Terrain.ROCK) or (x, y) in cv.protected:
                return False
        for (rx, ry), other in rects:
            slack = (size - 3) + (other - 3)
            if max(abs(rx - image[0]), abs(ry - image[1])) < spacing + slack:
                return False
            if rx - 2 - slack <= image[0] <= rx + other + 1 + slack and ry - 2 - slack <= image[1] <= ry + other + 1 + slack:
                return False
    return True


def _room(cv: _Canvas, pos: Pos, clearable: bool, size: int = 3) -> int:
    """Open tiles around a *size* site: within six of a 3x3 one, and a tile further out for every tile it is wider."""
    kinds = (Terrain.GRASS, Terrain.TREES) if clearable else (Terrain.GRASS,)
    return sum(1 for x, y in cv.within(_mine_centre(pos, size), 6 + (size - 3)) if cv.grid[y][x] in kinds)


def _canonical_sites(cv: _Canvas, size: int = 3) -> Iterable[Pos]:
    """Every *size* mine site the canonical cell can hold, with room for the block and its ring.  A cell
    edge that is the map's edge wants a tile more margin than one a neighbouring cell mirrors."""
    right = cv.cw - 3 - size if cv.cols == 1 else cv.cw - 2 - size
    for y in range(2, cv.ch - 2 - size):
        for x in range(2, right + 1):
            yield (x, y)


def _pick(cv: _Canvas, scored: list[tuple[float, Pos]], rects: list[tuple[Pos, int]], clearable: bool,
          size: int = 3, room: int = _SITE_ROOM, spacing: int | None = None) -> Pos | None:
    for _score, pos in sorted(scored, reverse=True):
        if _fits(cv, pos, rects, size, spacing) and _room(cv, pos, clearable, size) >= room:
            return pos
    return None


def _claim(cv: _Canvas, pos: Pos, gold: int, rects: list[tuple[Pos, int]], mines: list[tuple[Pos, BuildingType, int]], *,
           clearing: int = 0, kind: BuildingType = BuildingType.GOLD_MINE) -> None:
    """Take a canonical deposit site: one deposit of *kind* holding *gold* in every cell, the ground
    under and around it cleared, and its footprints added to what later searches must keep away from.

    Its footprint is whatever the rules give that kind, so a wider deposit needs nothing said here.
    This is the whole of placing a kind of deposit: a new one is a site search of its own
    (``_natural_site``, ``_third_site`` and ``_seam_site`` are the three there are, all scoring
    :func:`_canonical_sites` and picking through :func:`_pick`) and a call here.  The order deposits
    are claimed in is the order they are built in, which the simulation's own order follows, so a new
    kind goes after the ones above it rather than among them.
    """
    size = BUILDINGS[kind].size
    rects += [(image, size) for image in cv.rect_images(pos, size)]
    cv.paint(_block(pos, size=size), Terrain.GRASS)
    if clearing:
        cv.paint(cv.within(_mine_centre(pos, size), clearing), Terrain.GRASS, over=(Terrain.TREES,))
    mines += [(image, kind, gold) for image in cv.rect_images(pos, size)]


def _natural_site(cv: _Canvas, rng: random.Random, spec: _Spec, hc: Pos, halls: list[Point], rects: list[tuple[Pos, int]],
                  prefer: Callable[[Pos], float] | None) -> Pos | None:
    """As far out as the range allows, half again nearer its own hall than any other."""
    low, high = spec.natural_range
    if not cv.wide:
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
        if near[0] < 12 or near[1] - near[0] > (spec.contested or (6 if cv.wide else 12)):
            continue
        scored.append((-(near[1] - near[0]) + rng.uniform(0, 6) + (prefer(pos) if prefer else 0.0), pos))
    return _pick(cv, scored, rects, spec.third_clearing > 0)


def _seam_site(cv: _Canvas, rng: random.Random, spec: _Spec, halls: list[Point], rects: list[tuple[Pos, int]]) -> Pos | None:
    """Ground worth leaving home for: :data:`_SEAM_AWAY` tiles from every hall, as evenly shared
    between two of them as a third is, and with :data:`_SEAM_ROOM` open tiles around it for the hall
    and the towers whoever means to keep it will want."""
    size = BUILDINGS[BuildingType.GOLD_SEAM].size
    scored = []
    for pos in _canonical_sites(cv, size):
        c = _mine_centre(pos, size)
        near = sorted(_dist(c, hall) for hall in halls)
        if near[0] < _SEAM_AWAY or near[1] - near[0] > (spec.contested or (6 if cv.wide else 12)):
            continue
        scored.append((-(near[1] - near[0]) + rng.uniform(0, 6), pos))
    return _pick(cv, scored, rects, spec.third_clearing > 0, size, _SEAM_ROOM)


def _camp_site(cv: _Canvas, rng: random.Random, anchor: Point, rects: list[tuple[Pos, int]]) -> Pos | None:
    """A lair site guarding the deposit whose middle is *anchor*, within reach of it, on
    ground with room to fight over, and clear of every footprint already claimed.

    A camp is placed the way a mine is -- one canonical site, one copy to a cell -- so every seat faces the
    same camp at the same remove from the same deposit and the audit's congruence still holds.  Its own
    spacing is tighter than a deposit's (:data:`_CAMP_SPACING`), because a den that had to keep a mine's
    distance from the dig it guards would not be guarding it.
    """
    scored = []
    for pos in _canonical_sites(cv):
        away = _dist(_mine_centre(pos), anchor)
        if not _CAMP_NEAREST <= away <= _CAMP_FURTHEST:
            continue
        scored.append((-away + rng.uniform(0.0, 2.0), pos))  # as close to the deposit as the ground allows
    return _pick(cv, scored, rects, True, 3, _CAMP_ROOM, _CAMP_SPACING)


def _guard(cv: _Canvas, rng: random.Random, deposit: Pos, size: int, kind: str, rects: list[tuple[Pos, int]],
           dens: list[tuple[Pos, str]]) -> None:
    """Put a camp of *kind* beside the deposit at *deposit*, if there is room for one.

    A camp is a wish, never a fault: an unguarded deposit is a poorer map, not an unfair one, and a
    layout whose walls leave no room beside a dig would otherwise refuse the whole seed.
    """
    spot = _camp_site(cv, rng, _mine_centre(deposit, size), rects)
    if spot is None:
        return
    rects += [(image, 3) for image in cv.rect_images(spot, 3)]
    cv.paint(_block(spot), Terrain.GRASS)
    cv.paint(cv.within(_mine_centre(spot), 4), Terrain.GRASS, over=(Terrain.TREES,))
    dens.append((spot, kind))


# -- Assembly ----------------------------------------------------------------------


def _attempt(rng: random.Random, seed: int, width: int, height: int, players: int, human: int | None, theme: MapTheme,
             races: list[Race], layout: Layout, wilds: bool, rift_rng: random.Random) -> tuple[World, dict]:
    spec = _SPECS[layout]
    cv = _Canvas(width, height, players)
    clearing = _clearing(spec, cv.cw, cv.ch, cv.wide)
    hall = _hall_corner(cv.cols, cv.rows, cv.cw, cv.ch)
    hc = (hall[0] + 1, hall[1] + 1)
    main = (hall[0] - 5, hall[1] - 4)
    if layout is Layout.FOREST:
        cv.paint(((x, y) for y in range(height) for x in range(width)), Terrain.TREES)
    else:
        _speckle(cv, rng)
    cv.symmetrize()
    cv.paint(cv.within(hc, clearing), Terrain.GRASS)
    cv.paint(_block(main), Terrain.GRASS)
    _clump(cv, (hall[0] + 9, hall[1] + 1), 2.6, rng)
    walls = _Walls(set(), set(), [], [])
    if layout is Layout.CROSSINGS:
        _river(cv, rng, walls)
    elif layout is Layout.KLONDIKE:
        _pit(cv, rng, hc, walls)
    elif layout is Layout.BASTION:
        _ring(cv, rng, hc, walls)
    elif layout is Layout.PLAINS:
        # The second base lies forward, between the players, rather than
        # behind: taking it means standing where the enemy walks, so an
        # early raid pays and waiting at home costs.
        junction = cv.junction
        walls.prefer_natural = lambda pos: -_dist(_mine_centre(pos), junction)
    cv.symmetrize()
    halls = [_mine_centre(pos) for pos in cv.rect_images(hall, 3)][:players]
    rects = [(pos, 3) for pos in cv.rect_images(hall, 3)] + [(pos, 3) for pos in cv.rect_images(main, 3)] + walls.rects
    problems: list[str] = []
    wishes: list[str] = []  # what this seed could not fit in but another might; see build()
    # The mines the map will hold, in the order they are placed: a seat's own, then whatever the
    # site searches find.  A new kind of mine is a search for its canonical site and one _claim.
    mines: list[tuple[Pos, BuildingType, int]] = [(pos, BuildingType.GOLD_MINE, spec.start_gold) for pos in cv.rect_images(main, 3)[:players]]
    if layout is Layout.KLONDIKE:
        mines += [(pos, BuildingType.GOLD_MINE, POOR_GOLD) for pos in cv.rect_images(main, 3)[players:]]  # an empty cell's corner
    natural: Pos | None = None
    if spec.natural:
        natural = _natural_site(cv, rng, spec, hc, halls, rects, walls.prefer_natural)
        if natural is None:
            problems.append("no room for a natural")
        else:  # the empty cell's stays, neutral
            _claim(cv, natural, EXPANSION_GOLD, rects, mines, clearing=spec.natural_clearing)
    thirds: list[Pos] = []
    # Every camp on the map, in the order they are raised: one canonical den to a contested deposit, copied
    # to every cell as the deposit itself is.  A seat's own mine and its natural are never guarded -- the
    # opening is untouched and the first expansion is free; what a seat has to leave home for is held.
    dens: list[tuple[Pos, str]] = []
    for _ in range(_third_orbits(spec, cv.cw, cv.ch)):
        third = _third_site(cv, rng, spec, halls, rects, walls.prefer_third)
        if third is None:
            problems.append("no room for a third mine")
            break
        thirds.append(third)
        _claim(cv, third, EXPANSION_GOLD, rects, mines, clearing=spec.third_clearing)
        if wilds:
            # Plains dens fall to a raid; elsewhere the small camps mix, so
            # creeping stays a skirmish everywhere a timing push can afford.
            # (Forest lairs were tried: trickle 7 units per lair, a sink the
            # gate in docs/balance.md refuses.) Single-element choices still
            # draw once, so other layouts' streams come out as before.
            if layout is Layout.PLAINS:
                camp_kind = rng.choice(("den",))
            else:
                camp_kind = rng.choice(("den", "nest"))
            _guard(cv, rng, third, 3, camp_kind, rects, dens)
    if _wants_a_seam(spec, width, height, cv.cw, cv.ch):
        seam = _seam_site(cv, rng, spec, halls, rects)
        if seam is None:
            wishes.append("no room for a gold seam")
        else:  # an endless deposit holds no stock: what it gives is a trip at a time, as long as it is held
            _claim(cv, seam, 0, rects, mines, clearing=spec.third_clearing, kind=BuildingType.GOLD_SEAM)
            if wilds:  # the richest prize and the furthest out: the big camp, every time
                _guard(cv, rng, seam, BUILDINGS[BuildingType.GOLD_SEAM].size, "lair", rects, dens)
    mines += walls.mines
    cv.symmetrize()
    if layout is Layout.FOREST:
        _forest_roads(cv, rng, hc, natural, thirds)
        cv.symmetrize()

    cv.frame()
    world = World(width, height, cv.grid, players, human=human, rng=random.Random(seed), theme=theme, races=races, layout=layout)
    for seat, pos in enumerate(cv.rect_images(hall, 3)[:players]):
        world.place_building(seat, BuildingType.TOWN_HALL, pos)
    for pos, kind, gold in mines:
        world.place_building(None, kind, pos).gold = gold
    for den, camp_kind in dens:
        roster, hoard = _ROSTERS[camp_kind]
        for image in cv.rect_images(den, 3):
            camping.place(world, image, list(roster), hoard)
    for seat in range(players):
        for i in range(3):
            world.spawn_unit(seat, UnitType.PEASANT, tile_center(cv.images((hall[0] + i, hall[1] + 3))[seat]))
    _connect(world, cv)
    if not _lay_rifts(world, cv, walls, hall, main, rift_rng):
        problems.append("no room for a ley rift")
    world.update_vision()
    report = _audit(world, cv, spec, walls, natural)
    if layout is Layout.BASTION:
        world.gates = frozenset(cv.orbit(walls.gates))
        if natural is not None:
            world.gate_links = tuple(zip(cv.rect_images(hall, 3)[:players], cv.rect_images(natural, 3)[:players]))
    report["problems"] = problems + report["problems"]
    report["wishes"] = wishes  # nothing the audit looks at is a wish: an unfair map is a fault, every time
    return world, report


# -- Ley rifts ---------------------------------------------------------------------


def _lay_rifts(world: World, cv: _Canvas, walls: _Walls, hall: Pos, main: Pos, rng: random.Random) -> bool:
    """Lay every seat's rift near its hall and, where the cell has room, a contested one in the shared ground; whether
    the seats' own could be laid (the contested one is a nicety: a cell without room for it simply has none).

    Each is a canonical site whose every copy is on open grass the first hall can walk to, clear of buildings,
    deposits, units, camps, gates and fords: the ground a vault is placed on by the rules, with room around it."""
    region = reachable(world, _doors(world)[0][0])
    walls_near = cv.orbit(walls.gates | walls.fords)
    halls = [_mine_centre(pos) for pos in cv.rect_images(hall, 3)]  # every cell's, a seatless one's too: the grid decides what is shared
    hall_middle = _mine_centre(hall)
    left, top = min(hall[0], main[0]), min(hall[1], main[1])
    right, bottom = max(hall[0], main[0]) + 3, max(hall[1], main[1]) + 3
    shelter = (left - 1, top - 1, right - left + 2, bottom - top + 2)  # hall, main mine and the walk between, a tile round
    mine_middle = _mine_centre(main)
    home = []
    for pos in _rift_sites(cv):
        middle = _mine_centre(pos, RIFT)
        away = _dist(middle, hall_middle)
        if not _RIFT_HOME[0] <= away <= _RIFT_HOME[1] or rects_gap((pos[0], pos[1], RIFT, RIFT), shelter) == 0:
            continue
        home.append((-abs(away - 6.0) + 0.15 * _dist(middle, mine_middle) + rng.uniform(0.0, 1.5), pos))
    laid: list[Pos] = []
    spot = _pick_rift(world, cv, home, region, walls_near, laid)
    if spot is None:
        return False
    laid += cv.rect_images(spot, RIFT)
    if cv.cw * cv.ch >= _RIFT_CELL:
        contested = []
        tolerance = _SPECS[world.layout].contested or (6 if cv.wide else 12)
        for pos in _rift_sites(cv):
            middle = _mine_centre(pos, RIFT)
            near = sorted(_dist(middle, other) for other in halls)
            if near[0] < _RIFT_AWAY or near[1] - near[0] > tolerance:
                continue
            contested.append((-(near[1] - near[0]) + rng.uniform(0.0, 3.0), pos))
        spot = _pick_rift(world, cv, contested, region, walls_near, laid, room=_RIFT_ROOM)
        if spot is not None:
            laid += cv.rect_images(spot, RIFT)
    world.lay_rifts(laid)
    return True


def _rift_sites(cv: _Canvas) -> Iterable[Pos]:
    """Every square a rift can take inside the canonical cell, a tile in from its edges."""
    for y in range(1, cv.ch - RIFT):
        for x in range(1, cv.cw - RIFT):
            yield (x, y)


def _pick_rift(world: World, cv: _Canvas, scored: list[tuple[float, Pos]], region: set[Pos], walls: set[Pos], laid: list[Pos], *,
               room: int = 0) -> Pos | None:
    """The best-scored canonical rift site whose every copy :func:`_rift_fits`, and whose copies keep
    :data:`_RIFT_SPACING` from one another: a site on a cell's border would otherwise stand beside its mirror image."""
    for _score, pos in sorted(scored, reverse=True):
        images = cv.rect_images(pos, RIFT)
        if any(rects_gap((a[0], a[1], RIFT, RIFT), (b[0], b[1], RIFT, RIFT)) < _RIFT_SPACING
               for i, a in enumerate(images) for b in images[i + 1:]):
            continue
        if all(_rift_fits(world, cv, image, region, walls, laid, room) for image in images):
            return pos
    return None


def _rift_fits(world: World, cv: _Canvas, pos: Pos, region: set[Pos], walls: set[Pos], laid: list[Pos], room: int) -> bool:
    """Whether a rift at *pos* is ground a vault can be set on and walked round: its square open grass the first
    hall reaches, inside the map with most of the ring round it open too; clear of every building, deposit and wall
    by the gaps above, of every unit, and of a camp's lair and its guards (not of its watch: a rift out in the shared
    ground may be held by a camp, as the deposits there are); *room* open tiles within four of its middle."""
    x, y = pos
    rect = (x, y, RIFT, RIFT)
    ring = 0
    for ty in range(y - 1, y + RIFT + 1):
        for tx in range(x - 1, x + RIFT + 1):
            if not cv.inside(tx, ty):
                return False
            if x <= tx < x + RIFT and y <= ty < y + RIFT:
                if world.terrain[ty][tx] is not Terrain.GRASS or (tx, ty) not in region:
                    return False
            elif world.passable(tx, ty) and (tx, ty) in region:
                ring += 1
    if ring < _RIFT_RING:
        return False
    if any(rects_gap(rect, (other[0], other[1], RIFT, RIFT)) < _RIFT_SPACING for other in laid):
        return False
    for b in world.buildings.values():
        gap = _RIFT_DEPOSIT_GAP if b.info.mine is not None or b.player == world.neutral else _RIFT_HALL_GAP
        if rects_gap(rect, b.rect) < gap:
            return False
    middle = _mine_centre(pos, RIFT)
    for camp in world.camps:
        lair = world.buildings.get(camp.lair)
        if lair is not None and _dist(middle, lair.center) < _RIFT_LAIR:
            return False
    if any(x - 1 <= u.x < x + RIFT + 1 and y - 1 <= u.y < y + RIFT + 1 for u in world.units.values()):
        return False
    if any(x - _RIFT_WALL_GAP <= tx < x + RIFT + _RIFT_WALL_GAP and y - _RIFT_WALL_GAP <= ty < y + RIFT + _RIFT_WALL_GAP for tx, ty in walls):
        return False
    return room == 0 or sum(1 for tx, ty in cv.within(middle, 4.0) if world.passable(tx, ty)) >= room


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
                # A tile whose copies include one on the rim is carved everywhere but there: the rim
                # is a frame outside play, and leaving it would wall two cells off from each other.
                if cv.inside(nx, ny) and (nx, ny) not in cv.protected and world.building_at((nx, ny)) is None \
                        and world.terrain_at((nx, ny)) is not Terrain.GRASS:
                    world.terrain[ny][nx] = Terrain.GRASS
                    world._blocked[ny * world.width + nx] = 0


# -- Audit -------------------------------------------------------------------------


def audit(world: World) -> dict:
    """The numbers a fair start needs, per base: open ground within six tiles of the hall, the
    distance to the nearest mine, to wood and to a ley rift, whether every door, mine and rift
    share one region, how many mines there are beyond the main ones, and the terrain mix."""
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    doors, mine_doors = _doors(world)
    region = reachable(world, doors[0])
    report: dict = {"players": len(halls), "layout": world.layout.value, "open": [], "mine": [], "wood": [], "rift": []}
    for hall in halls:
        cx, cy = int(hall.center[0]), int(hall.center[1])
        report["open"].append(sum(1 for dx in range(-6, 7) for dy in range(-6, 7) if world.passable(cx + dx, cy + dy)))
        report["mine"].append(min(max(abs(m.center[0] - hall.center[0]), abs(m.center[1] - hall.center[1])) for m in world.mines()))
        tree = world.nearest_tree(hall.center, 12)
        report["wood"].append(None if tree is None else max(abs(tree[0] - cx), abs(tree[1] - cy)))
        report["rift"].append(min((max(abs(x + RIFT / 2 - hall.center[0]), abs(y + RIFT / 2 - hall.center[1])) for x, y in world.rifts),
                                  default=None))
    report["connected"] = all(d in region for d in doors + mine_doors + list(world.rifts))
    report["rifts"] = len(world.rifts)
    report["expansions"] = len(world.mines()) - len(halls)
    report["seams"] = sum(1 for m in world.mines() if m.type is BuildingType.GOLD_SEAM)
    report["camps"] = len(world.camps)
    total = world.width * world.height
    report["trees"] = sum(1 for row in world.terrain for t in row if t is Terrain.TREES) / total
    report["water"] = sum(1 for row in world.terrain for t in row if t is Terrain.WATER) / total
    return report


def _rift_problems(world: World, cv: _Canvas) -> list[str]:
    """What is unfair about the ley rifts: a seat without one of its own near its hall, a rift whose copies are not
    all rifts, or one a vault could not be set on by the rules as the map begins."""
    problems: list[str] = []
    rifts = set(world.rifts)
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]  # placed in seat order
    for hall in halls:
        own = [r for r in rifts if max(abs(r[0] + RIFT / 2 - hall.center[0]), abs(r[1] + RIFT / 2 - hall.center[1])) <= _RIFT_HOME[1]]
        if not any(all(_dist(_mine_centre(r, RIFT), other.center) > _dist(_mine_centre(r, RIFT), hall.center) for other in halls
                       if other is not hall) for r in own):
            problems.append(f"seat {hall.player} has no ley rift of its own")
    if any(not set(cv.rect_images(_fold(cv.cols, cv.rows, cv.cw, cv.ch, rift, RIFT), RIFT)) <= rifts for rift in world.rifts):
        problems.append("the ley rifts are not symmetric")
    for x, y in world.rifts:
        if any(world.terrain[ty][tx] is not Terrain.GRASS or not world.passable(tx, ty) for ty in range(y, y + RIFT) for tx in range(x, x + RIFT)) \
                or any(m.info.mine is not None and rects_gap((x, y, RIFT, RIFT), m.rect) < MINE_CLEARANCE for m in world.buildings.values()):
            problems.append(f"no vault can stand on the ley rift at {(x, y)}")
    return problems


def _route(world: World, start: Pos, goal: Pos) -> list[Pos] | None:
    """The production pathfinder's route, or None when its budget runs out first."""
    if start == goal:
        return []
    route = pathing.find_path_grid(start, goal, world._blocked, world.width, world.height, max_expansions=world.path_budget)
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
    routes = {goal: _route(world, doors[0], goal) for goal in doors[1:] + mine_doors + list(world.rifts)}
    if any(route is None for route in routes.values()):
        problems.append("a route exceeds the pathfinder's budget")
    problems += _rift_problems(world, cv)
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
        pit = [world.free_tile_near((x, y, 3, 3)) for (x, y), _kind, gold in walls.mines if gold == EXPANSION_GOLD]
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
