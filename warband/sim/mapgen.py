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

The ground between the bases is composed, not speckled: one nameable place
at the centre (a lake, a mesa, a great wood, marsh ponds, an open field —
or the layout's own river, pit or middle clearing), a ridge with a pass
across the way to it, a tree belt on one flank, naturals backed into
pockets and contested mines beside a landmark grove, so a screenshot of a
map supports a plan in plain words.  :func:`describe` reads the finished
ground back into those words for the New game screen.

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
from warband.sim.model import MINE_CLEARANCE, RIFT, Building, Pos, World, int_sum, plain_sum, rects_gap, tile_center
from warband.sim.rules import (BUILDINGS, EXPANSION_GOLD, LODE_GOLD, MAX_PLAYERS, MINE_GOLD, BuildingType, Layout, MapTheme, Race,
                               CAMP_WATCH, Terrain, UnitType)

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
#: The shared ground's prize is one of two five-tile deposits (:class:`~warband.sim.rules.MineInfo`), dealt by
#: the map's seed: a gold seam, twenty gold a trip and it never runs out, or a Mother Lode, a mine's hundred a
#: trip at the seam's twelve places and LODE_GOLD to give (WB-071).  So the middle of a big map is either a long
#: siege for a trickle or a short war for a fortune.  Both are worth what holding them is worth, so a prize goes
#: on the maps whose matches are long and whose middle is far from home, and nowhere else: the three shipped
#: sizes keep the economy their difficulty ratings and their balance league were measured on.
_PRIZES: Final = (BuildingType.GOLD_SEAM, BuildingType.MOTHER_LODE)
_PRIZE_SALT: Final = 0x10DE  # the deal's own stream, seeded apart from the map's: which prize never moves a tile
_PRIZE_MAP: Final = 5200  # tiles of map a prize wants more of; a Large (80x64) is 5120
_PRIZE_CELL: Final = 1000  # tiles of a seat's own cell: a smaller share has no middle to put a five-tile dig in
_PRIZE_AWAY: Final = 18  # tiles from every hall: past the natural, out where a seat has to go and stay
_PRIZE_ROOM: Final = 110  # open tiles within eight of the prize, against _SITE_ROOM within six of a natural
_MARGIN: Final = 7  # tiles from a cell's corner to a corner hall's top-left
_CLEARING: Final = 7  # radius of open ground around the hall's middle tile
_SITE_SPACING: Final = {True: 8, False: 7}  # Chebyshev tiles between mine sites, by whether the cell spans the map (mirrored cells are tighter)
_SITE_ROOM: Final = 60  # open tiles within six of a natural or third, so a hall and farms fit
_MIN_CELL: Final = (24, 20)  # the smallest share of a map that has ever made a fair base: Small with four seats
_MAX_CELL: Final = 5000  # the largest share a seat can hold: beyond it the walk to the next base is the whole match
_GLADE_ROOM: Final = 1300  # tiles of a Forest cell per extra clearing cut in it, beyond the two the layout always cuts
#: Encounters are side expeditions, one symmetric opportunity per seat and tier at most.
#: Their stream is separate from the terrain/deposit deal, so wilds=False is the same map.
_CAMP_SALT: Final = 0xCA47
_CAMP_SPACING: Final = 9
_CAMP_SEPARATION: Final = max(16, 2 * CAMP_WATCH + 2)  # room for independent fights, beyond the scoutable watch
_CAMP_ROOM: Final = 48
_CAMP_HOME: Final = 14.0
_CAMP_SAFE_MINE: Final = 10.5

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
             races: Sequence[Race | None] | None = None, layout: Layout | None = None, wilds: bool = True,
             prize: BuildingType | None = None, *, magic: bool = False) -> World:
    """*races* names each player's race; ``None`` entries are drawn from the seed, so a seed reproduces
    the whole match.  Without a list the *human* leads Humans and the computer players are drawn.
    *layout* ``None`` draws one from the seed.  *wilds* ``False`` removes optional encounters while preserving terrain and deposits,
    which is how a map is measured against one with camps on it.  *prize* ``None`` has the seed deal the
    shared ground's prize (:func:`deal_prize`); naming one plays the same map with that prize on it, which is
    how a lode is measured against a seam. *magic* opts in to ley rifts and magical technology;
    ordinary matches have neither."""
    return build(seed, width, height, players, human, theme, races, layout, wilds, prize, magic=magic)[0]


def build(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0, theme: MapTheme = MapTheme.SUMMER,
          races: Sequence[Race | None] | None = None, layout: Layout | None = None, wilds: bool = True,
          prize: BuildingType | None = None, *, magic: bool = False) -> tuple[World, dict]:
    """:func:`generate` plus the audit report of the map it settled on (``attempt`` counts the retries)."""
    if prize is not None and prize not in _PRIZES:
        raise ValueError(f"the shared ground's prize is one of {', '.join(p.value for p in _PRIZES)}, not {prize.value}")
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
    dealt = deal_prize(seed) if prize is None else prize
    problems: list[str] = []
    without: tuple[World, dict] | None = None  # the best map so far that is fair but is missing something wished for
    for attempt in range(RETRIES):
        world, report = _attempt(random.Random(seed * 16 + attempt), seed, width, height, players, human, theme, chosen, layout, wilds,
                                 random.Random((seed * 16 + attempt) ^ _RIFT_SALT), dealt, magic)
        report["attempt"] = attempt
        if not report["problems"]:
            if not report["wishes"]:
                return world, report
            if without is None:
                without = (world, report)
        problems = report["problems"] or report["wishes"]
    # A fault makes a map unfair and there is nothing to do but raise; a wish is a feature the layout's
    # own walls left no room for on this seed.  The prize (a seam or a lode) is the one wish there is: eight
    # seeds are given the chance to fit one in, and a map that has everything else is a map, not a refusal.
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


#: The one place at a map's centre you can name from the preview, drawn per seed: ``lake`` (pass it
#: on either side), ``mesa`` (rock armies go around), ``greatwood`` (chop through or go around),
#: ``marsh`` (ponds breaking the approach) or ``field`` (open ground between two groves).  The three
#: layouts whose centre is already a place keep theirs: Crossings' river, Klondike's pit, Forest's
#: middle clearing.  :func:`describe` reads the finished ground back into these words.
_MOTIFS: Final[dict[Layout, tuple[str, ...]]] = {
    Layout.PLAINS: ("lake", "mesa", "greatwood", "marsh", "field"),
    Layout.FOREST: ("deepwood",),
    Layout.CROSSINGS: ("river",),
    Layout.KLONDIKE: ("pit",),
    Layout.BASTION: ("mesa", "marsh", "field", "greatwood"),
}


def _blob(cv: _Canvas, centre: Point, radius: float, kind: Terrain, rng: random.Random, *,
          over: tuple[Terrain, ...] = (Terrain.GRASS,)) -> None:
    """One coherent body of *kind* — a lake, a mesa, a grove — with a ragged shore: solid inside
    *radius* − 0.8, thinning to nothing at *radius* + 0.8.  Noise decides only the edge of a
    feature, never where the feature is, so a screenshot shows places rather than camouflage."""
    for tile in cv.disc(centre, radius + 0.8):
        x, y = tile
        if not (0 <= x < cv.w and 0 <= y < cv.h) or cv.grid[y][x] not in over:
            continue
        d = _dist(tile, centre)
        if d <= radius - 0.8 or rng.random() < (radius + 0.8 - d) / 1.6:
            cv.grid[y][x] = kind


def _ridge(cv: _Canvas, rng: random.Random, a: Point, b: Point, *, rock: bool, gap_at: float, width: float = 1.9) -> None:
    """A wall of trees (with a rock spine when *rock*) along the line *a*→*b*, broken by one pass:
    a gap of open ground a few tiles wide at *gap_at* of the way along.  A ridge across the line
    between two halls turns an approach into a sentence — *through the pass or round the end* —
    and its trees are lumber a determined player can cut a second pass through."""
    length = _dist(a, b)
    if length < 5:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    gap = 2.2  # half the pass's width in tiles along the ridge
    steps = int(length / 1.25)
    for i in range(steps + 1):
        along = i * 1.25
        if abs(along - gap_at * length) <= gap:
            continue
        t = along / length
        spot = (a[0] + (b[0] - a[0]) * t + rng.uniform(-0.35, 0.35) * uy,
                a[1] + (b[1] - a[1]) * t - rng.uniform(-0.35, 0.35) * ux)
        cv.paint(cv.within(spot, width), Terrain.TREES, over=(Terrain.GRASS,))
        if rock:
            cv.paint(cv.within(spot, width - 0.8), Terrain.ROCK, over=(Terrain.GRASS, Terrain.TREES))


def _clamped(cv: _Canvas, point: Point) -> Point:
    """*point* pulled inside the canonical cell, two tiles off its edges, so a composed feature
    belongs to the cell the symmetry copies rather than straddling the next one by accident."""
    return (min(max(point[0], 2.0), float(cv.cw - 3)), min(max(point[1], 2.0), float(cv.ch - 3)))


def _landscape(cv: _Canvas, rng: random.Random, layout: Layout, hc: Pos) -> str:
    """The ground a player can read, drawn for the first seat before any walls or mines: a forest
    fringe, one named place at the centre (the motif, returned), a ridge with a pass across the
    way to it, a tree belt along one flank, and a few small groves and ponds as local colour.

    What this replaced (three noise fields thresholded into amoeba blobs) made every seed the
    same camouflage: no lanes, no landmarks, mines floating on anonymous grass.  Here every
    large shape is placed in relation to the hall and the centre, so the preview supports a
    plan: which side of the lake, through which pass, behind which belt."""
    fringe = _noise(rng, cv.w, cv.h, 3)
    for y in range(cv.h):
        for x in range(cv.w):
            edge = min(x, y, cv.w - 1 - x, cv.h - 1 - y)
            if edge == 0 or (edge < 3 and fringe[y][x] > 0.45):
                cv.grid[y][x] = Terrain.TREES
    motif = rng.choice(_MOTIFS[layout])
    home: Point = (float(hc[0]), float(hc[1]))
    junction = cv.junction
    span = _dist(home, junction) or 1.0
    ux, uy = (junction[0] - home[0]) / span, (junction[1] - home[1]) / span
    px, py = -uy, ux

    def toward(t: float, side: float) -> Point:
        return _clamped(cv, (home[0] + ux * span * t + px * side, home[1] + uy * span * t + py * side))

    # The centre: one place, drawn on the junction so the copies assemble it whole (as the pit
    # and the river are).  The river and the pit are drawn by their own passes later.
    reach = max(4.0, min(8.5, min(cv.cw, cv.ch) * 0.24, span * 0.22))
    if layout not in (Layout.CROSSINGS, Layout.KLONDIKE):
        # Overlapping bodies stretched across the approach, never one stamped disc: a centre
        # drawn as a perfect circle reads as a diagram, not a place.
        if motif == "lake":
            _blob(cv, junction, reach * 0.85, Terrain.WATER, rng)
            _blob(cv, (junction[0] + px * reach * 0.55, junction[1] + py * reach * 0.55), reach * 0.6, Terrain.WATER, rng)
            bay = (junction[0] - ux * reach * 0.95, junction[1] - uy * reach * 0.95)
            _blob(cv, bay, reach * 0.45, Terrain.WATER, rng)
        elif motif == "mesa":
            _blob(cv, junction, reach * 0.72, Terrain.ROCK, rng)
            _blob(cv, (junction[0] + px * reach * 0.5, junction[1] + py * reach * 0.5), reach * 0.52, Terrain.ROCK, rng)
            for tile in cv.band(junction, reach * 0.65, reach * 0.95):
                if cv.grid[tile[1]][tile[0]] is Terrain.GRASS and rng.random() < 0.55:
                    cv.grid[tile[1]][tile[0]] = Terrain.TREES
        elif motif == "greatwood":
            for off in (-0.55, 0.0, 0.55):
                _blob(cv, (junction[0] + px * off * reach, junction[1] + py * off * reach), reach * 0.78, Terrain.TREES, rng)
        elif motif == "marsh":
            for off in (-1.0, 0.0, 1.0):
                pond = (junction[0] - ux * reach * 0.65 + px * off * reach * 1.1,
                        junction[1] - uy * reach * 0.65 + py * off * reach * 1.1)
                _blob(cv, pond, rng.uniform(1.9, 2.7), Terrain.WATER, rng)
        else:  # field: open ground to meet on, two groves to fight from the edge of
            for side in (-1.0, 1.0):
                grove = (junction[0] - ux * reach * 0.4 + px * side * reach * 0.95,
                         junction[1] - uy * reach * 0.4 + py * side * reach * 0.95)
                _blob(cv, grove, reach * 0.5, Terrain.TREES, rng)

    # A ridge across the way home→centre, with its pass: the choke every early army files
    # through, and the line a defender towers.  The river does this job on Crossings.
    if layout is not Layout.CROSSINGS:
        ridges = 1 if cv.cw * cv.ch < 2200 else rng.choice((1, 2))
        for _ in range(ridges):
            t = rng.uniform(0.30, 0.40) if layout is Layout.KLONDIKE else rng.uniform(0.38, 0.54)
            centre = toward(t, rng.choice((-1.0, 1.0)) * rng.uniform(0.06, 0.18) * span)
            heading = math.atan2(py, px) + rng.uniform(-0.3, 0.3)
            half = span * rng.uniform(0.28, 0.38)
            a = _clamped(cv, (centre[0] - half * math.cos(heading), centre[1] - half * math.sin(heading)))
            b = _clamped(cv, (centre[0] + half * math.cos(heading), centre[1] + half * math.sin(heading)))
            stony = 0.65 if layout is Layout.BASTION else 0.45
            _ridge(cv, rng, a, b, rock=rng.random() < stony, gap_at=rng.uniform(0.35, 0.65), width=1.5)

    # One belt of trees lengthwise on a flank: lumber, cover, and a hidden lane behind it.
    # A roomy cell earns the other flank one too — on a Giant cell the fringe is a shrinking
    # share of the ground, and without a second belt the woods thin below what a long
    # match's lumber economy (and the fairness audit's floor) needs.
    side = rng.choice((-1.0, 1.0)) * span * rng.uniform(0.30, 0.42)
    _ridge(cv, rng, toward(0.22, side), toward(0.78, side * 0.8), rock=False,
           gap_at=rng.uniform(0.35, 0.65), width=1.6)
    if cv.cw * cv.ch >= 2200:
        other = -side * rng.uniform(0.75, 1.0)
        _ridge(cv, rng, toward(0.30, other), toward(0.82, other * 0.85), rock=False,
               gap_at=rng.uniform(0.35, 0.65), width=1.6)

    # Local colour, kept small and few so the composed shapes stay the story.
    for _ in range(max(2, cv.cw * cv.ch // 500)):
        spot = (rng.uniform(3, cv.cw - 4), rng.uniform(3, cv.ch - 4))
        if _dist(spot, home) >= 9:
            _blob(cv, spot, rng.uniform(1.2, 2.6), Terrain.TREES, rng)
    # Ponds belong on the flanks, where they name the side lanes, not sprinkled at random.
    ponds = 0 if layout is Layout.CROSSINGS or motif in ("lake", "marsh") else 2 if motif == "field" else 1
    for _ in range(ponds):
        flank = rng.choice((-1.0, 1.0)) * span * rng.uniform(0.32, 0.45)
        spot = toward(rng.uniform(0.25, 0.7), flank)
        if _dist(spot, home) >= 10 and cv.grid[int(spot[1])][int(spot[0])] is Terrain.GRASS:
            _blob(cv, spot, rng.uniform(1.7, 2.7), Terrain.WATER, rng)
    return motif


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
    prize: bool = False  # a seam or a lode out in the shared ground, where the map is big enough for one
    contested: int | None = None  # how many tiles nearer one hall than the next a third may be; None: the symmetry's default
    start_gold: int = MINE_GOLD


#: Three of the five layouts hold a prize, and each for its own reason.  Plains is open ground where
#: expansions lie exposed, so a deposit worth more than any other is exactly the thing to fight over.
#: Crossings already asks who holds the fords, and a prize on the far bank gives the answer a price.
#: Bastion promises a boom in safety and then a fight for the middle, and the prize is what the middle
#: is finally worth.  Forest has none: its clearings and roads are cut by hand and a five-tile dig
#: with its open ground around it would take a base's worth of woods out of a layout whose whole
#: promise is that the woods are thick.  Klondike has none either: little gold at home and the rest
#: in a walled pit is a deliberate shape of economy, and a fortune or a trickle outside the pit unmakes it.
#: Plains and Crossings also have short home mines: their free naturals should be fought over
#: during an ordinary match, before a player has already won from one safe deposit.
_SPECS: Final[dict[Layout, _Spec]] = {
    Layout.PLAINS: _Spec(Layout.PLAINS, prize=True, start_gold=15_000),
    Layout.FOREST: _Spec(Layout.FOREST, clearing=9, natural_range=(13, 18), natural_clearing=5, third_clearing=4),  # a full base needs the room; four seats get less, see _clearing
    Layout.CROSSINGS: _Spec(Layout.CROSSINGS, contested=14, prize=True, start_gold=20_000),  # the river runs down the bisector; thirds sit on its banks
    Layout.KLONDIKE: _Spec(Layout.KLONDIKE, clearing=6, natural=False, thirds=False, start_gold=KLONDIKE_START_GOLD),
    Layout.BASTION: _Spec(Layout.BASTION, natural_range=(12, 18), prize=True),
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


def _wants_a_prize(spec: _Spec, width: int, height: int, cw: int, ch: int) -> bool:
    """Whether this map gets a prize in the shared ground (one, copied to every seat, so one seat one prize):
    on a layout that holds them, on a map bigger than the shipped three, where a seat's own cell has the
    middle ground to put it in.  A match on a map that size is a long one, which is what a deposit
    whose worth is how long you keep it is for."""
    return spec.prize and width * height >= _PRIZE_MAP and cw * ch >= _PRIZE_CELL


def deal_prize(seed: int) -> BuildingType:
    """Which prize *seed* deals the shared ground, where its map holds one: a seam or a Mother Lode, even odds.

    Drawn from a stream of its own, as the layout and the races are, so the deal is the seed's and not an
    attempt's (every retry of a seed deals the same), and the map's own stream never learns of it: the two
    prizes are the same five tiles on the same site, so a seed draws the same ground either way.  Neighbouring
    seeds seed unrelated streams, so a ladder's run of seeds deals as a run of fair coins would."""
    return random.Random(seed ^ _PRIZE_SALT).choice(_PRIZES)


def _pit_inner(width: int, height: int) -> int:
    """The open radius inside Klondike's rock ring."""
    return max(6, min(9, round(min(width, height) * 0.18)))


def _river(cv: _Canvas, rng: random.Random, walls: _Walls) -> None:
    """Two players: one river from the crossing of the cells to the far edge, wandering, and its
    reflection.  Any other grid: a straight cross of two rivers of varying width, which the copies
    repeat at every crossing of cells, so each cell is moated on two sides.  A wide ford on the
    crossing, a narrow one near each end, rock outcrops on the banks beside the wide ford."""
    cx, cy = cv.junction
    # A ribbon one can follow with a finger, three to four tiles wide: the wide discs this used
    # swelled where they overlapped into a chain of lakes, and the fords drowned in it.
    radius = 1.3 if min(cv.w, cv.h) < (48 if cv.wide else 64) else 1.5 if min(cv.w, cv.h) < 64 else 1.8
    headings = [-math.pi / 4] if cv.wide else [math.pi, -math.pi / 2]
    fords: set[Pos] = set()
    for base in headings:
        points: list[Point] = []
        x, y, heading, travelled = cx, cy, base, 0.0
        while cv.inside(round(x), round(y)):
            points.append((x, y))
            if cv.wide and travelled > 5:
                heading = min(base + 0.7, max(base - 0.7, heading + rng.uniform(-0.22, 0.22)))
            x, y, travelled = x + 1.5 * math.cos(heading), y + 1.5 * math.sin(heading), travelled + 1.5
        widths = [radius if cv.wide else radius + rng.uniform(0, 0.8) for _ in points]
        widths = [plain_sum(widths[max(0, i - 2):i + 3]) / len(widths[max(0, i - 2):i + 3]) for i in range(len(widths))]  # smoothed: the cross swells and narrows
        tiles: set[Pos] = set()
        for point, width in zip(points, widths):
            tiles.update(cv.within(point, width))
        cv.paint(tiles, Terrain.WATER)
        centre_ford = _cut(tiles, (cx, cy), base, 3.0)
        end = max(1, len(points) - 6)
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
    before the five-tile deposits existed is drawn exactly as it was."""
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
    return int_sum(1 for x, y in cv.within(_mine_centre(pos, size), 6 + (size - 3)) if cv.grid[y][x] in kinds)


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
    (``_natural_site``, ``_third_site`` and ``_prize_site`` are the three there are, all scoring
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


def _beside_a_site(tile: Pos, rects: list[tuple[Pos, int]]) -> bool:
    """Whether *tile* falls in a claimed footprint's block, ring included: ground a pocket or a
    landmark grove must never grow over."""
    return any(rx - 1 <= tile[0] <= rx + size and ry - 1 <= tile[1] <= ry + size for (rx, ry), size in rects)


def _paint_orbit(cv: _Canvas, tile: Pos, kind: Terrain, *, over: tuple[Terrain, ...]) -> None:
    """Paint *tile* and every copy of it: a pocket arc commonly reaches across a cell border
    toward the centre, where painting one tile alone would be undone by the next symmetrize."""
    for x, y in cv.images(tile):
        if cv.grid[y][x] in over:
            cv.grid[y][x] = kind


def _pocket(cv: _Canvas, rng: random.Random, pos: Pos, hall: Point, rects: list[tuple[Pos, int]], avoid: set[Pos]) -> None:
    """Back the natural at *pos* with an arc of trees (a little rock among them) on the side away
    from its *hall*, and clear the trees from the mouth toward home: the second base reads at a
    glance as a place one entrance defends, and a raider must come round the mouth or through
    the trees.  Never over a claimed site, a gate, a ford or a protected wall, so the pocket
    closes no way the layout promised and seals no mine the audit must reach."""
    middle = _mine_centre(pos)
    away = math.atan2(middle[1] - hall[1], middle[0] - hall[0])
    for tile in cv.band(middle, 4.0, 7.0):
        if any(image in cv.protected or image in avoid or _beside_a_site(image, rects) for image in cv.images(tile)):
            continue
        turn = abs((math.atan2(tile[1] - middle[1], tile[0] - middle[0]) - away + math.pi) % (2 * math.pi) - math.pi)
        if turn < 1.75 and _dist(tile, middle) >= 5.0 and rng.random() < 0.9:  # the far half, and a little round the sides
            _paint_orbit(cv, tile, Terrain.ROCK if rng.random() < 0.12 else Terrain.TREES, over=(Terrain.GRASS,))
        elif turn > math.pi - 1.0:  # the mouth: fell whatever the landscape left across the way home
            _paint_orbit(cv, tile, Terrain.GRASS, over=(Terrain.TREES,))


def _grove_beside(cv: _Canvas, rng: random.Random, pos: Pos, rects: list[tuple[Pos, int]], avoid: set[Pos]) -> None:
    """A small grove on one flank of a contested mine: no shelter a pocket gives, but a landmark —
    *the mine by the grove* is a place an order can name, and cover one side fights from."""
    middle = _mine_centre(pos)
    angle = rng.uniform(0, 2 * math.pi)
    spot = (middle[0] + 5.5 * math.cos(angle), middle[1] + 5.5 * math.sin(angle))
    for tile in cv.within(spot, 1.8):
        if not any(image in cv.protected or image in avoid or _beside_a_site(image, rects) for image in cv.images(tile)):
            _paint_orbit(cv, tile, Terrain.TREES, over=(Terrain.GRASS,))


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
        # Out means out on either axis too: a diagonal mine can pass the circle at nine tiles
        # while standing seven from the hall's wall, a second main mine rather than an expansion.
        if not low <= own <= high or max(abs(c[0] - halls[0][0]), abs(c[1] - halls[0][1])) < 9 \
                or any(_dist(c, hall) < 1.4 * own for hall in halls[1:]):
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


def _prize_site(cv: _Canvas, rng: random.Random, spec: _Spec, halls: list[Point], rects: list[tuple[Pos, int]], size: int) -> Pos | None:
    """Ground worth leaving home for: :data:`_PRIZE_AWAY` tiles from every hall, as evenly shared
    between two of them as a third is, and with :data:`_PRIZE_ROOM` open tiles around it for the hall
    and the towers whoever means to keep it will want."""
    scored = []
    for pos in _canonical_sites(cv, size):
        c = _mine_centre(pos, size)
        near = sorted(_dist(c, hall) for hall in halls)
        if near[0] < _PRIZE_AWAY or near[1] - near[0] > (spec.contested or (6 if cv.wide else 12)):
            continue
        scored.append((-(near[1] - near[0]) + rng.uniform(0, 6), pos))
    return _pick(cv, scored, rects, spec.third_clearing > 0, size, _PRIZE_ROOM)


def _encounter_sites(world: World, cv: _Canvas, halls: list[Point], safe_mines: list[Pos],
                     rects: list[tuple[Pos, int]], protected_routes: set[Pos], camp_sites: list[Point],
                     rng: random.Random) -> list[Pos]:
    """Open, reachable side sites, with the opening and its connecting roads outside aggro.

    Reserving the actual route certificates before any camp is placed is stronger than distance
    from the map's middle: a forest road or a Klondike gate can be off-centre and still mandatory.
    The whole orbit of those roads is reserved, keeping the opportunities congruent even for
    three seats, where a fourth cell has no hall.
    """
    doors, _mine_doors = _doors(world)
    region = reachable(world, doors[0])
    safe_centres = [_mine_centre(pos) for pos in safe_mines]
    scored: list[tuple[float, Pos]] = []
    for pos in _canonical_sites(cv):
        middle = _mine_centre(pos)
        if min(_dist(middle, hall) for hall in halls) < _CAMP_HOME:
            continue
        if any(_dist(middle, mine) < _CAMP_SAFE_MINE for mine in safe_centres):
            continue
        if any(_dist(middle, camp) < _CAMP_SEPARATION for camp in camp_sites):
            continue
        # Every guard's watch stays off the certified opening and inter-base routes.
        if (pos[0] + 1, pos[1] + 1) in protected_routes:
            continue
        if not _fits(cv, pos, rects, spacing=_CAMP_SPACING) or _room(cv, pos, True) < _CAMP_ROOM:
            continue
        images = cv.rect_images(pos, 3)
        if any(_dist(_mine_centre(a), _mine_centre(b)) < _CAMP_SEPARATION
               for i, a in enumerate(images) for b in images[i + 1:]):
            continue
        if not any(tile in region for tile in cv.within(middle, 10)):
            continue
        if any(rects_gap((*image, 3, 3), (*rift, RIFT, RIFT)) < 3 for image in images for rift in world.rifts):
            continue
        # Prefer nearby side expeditions; seed jitter chooses between equivalent flanks.
        scored.append((-_dist(middle, halls[0]) + rng.uniform(0.0, 9.0), pos))
    return [pos for _score, pos in sorted(scored, reverse=True)]


def _prepare_shared_ancient(world: World, cv: _Canvas, safe_mines: list[Pos]) -> Pos | None:
    """One contested Ancient for three/four seats, with certified routes around its watch.

    A shared centre avoids filling a crowded four-seat map with four 6,000-gold bosses. The
    odd three-tile lair has at most a tile and a half of approach-distance bias on an even map.
    Klondike's central pit is its required economy, so its encounters remain side expeditions.
    """
    if world.seats not in (3, 4) or world.width * world.height < 5000 or world.layout is Layout.KLONDIKE:
        return None
    pos = (world.width // 2 - 1, world.height // 2 - 1)
    centre = _mine_centre(pos)
    rect = (*pos, 3, 3)
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    if any(_dist(centre, b.center) < _CAMP_HOME for b in halls):
        return None
    if any(_dist(centre, _mine_centre(mine)) < _CAMP_SAFE_MINE for mine in safe_mines):
        return None
    if any(rects_gap(rect, b.rect) < 1 for b in world.buildings.values()):
        return None
    if any(rects_gap(rect, (*rift, RIFT, RIFT)) < 3 for rift in world.rifts):
        return None
    if any(world.terrain_at(tile) in (Terrain.WATER, Terrain.ROCK) or tile in cv.protected for tile in _block(pos, gap=0)):
        return None
    hard = {(x, y) for y in range(world.height) for x in range(world.width)
            if world.terrain[y][x] in (Terrain.WATER, Terrain.ROCK)}
    doors, _mine_doors = _doors(world)
    approach = _cheapest_route(world, doors[0], (pos[0] + 1, pos[1] + 3),
                              cv.protected | hard | set(_block(pos, gap=0)))
    if approach is None or not _prepare_bypasses(world, cv, safe_mines, [centre]):
        return None
    _carve(world, cv, approach, trees_only=True)
    _clear_arena(world, cv, centre)
    return pos


def _prepare_bypasses(world: World, cv: _Canvas, safe_mines: list[Pos], centres: list[Point]) -> bool:
    """Certify an opening network outside every encounter's watch; carve tree-only detours."""
    watch = cv.orbit(tile for centre in centres for tile in cv.within(centre, CAMP_WATCH + 1))
    hard = {(x, y) for y in range(world.height) for x in range(world.width)
            if world.terrain[y][x] in (Terrain.WATER, Terrain.ROCK)}
    shut = cv.protected | watch | hard
    doors, _mine_doors = _doors(world)
    goals = doors[1:] + [world.free_tile_near((*mine, 3, 3)) for mine in safe_mines]
    routes: list[list[Pos]] = []
    for goal in goals:
        if goal is None:
            return False
        route = _cheapest_route(world, doors[0], goal, shut)
        if route is None:
            return False
        routes.append(route)
    for route in routes:
        _carve(world, cv, route, trees_only=True)
    return True


def _clear_arena(world: World, cv: _Canvas, centre: Point) -> None:
    """Clear only trees, preserving protected walls and both walkers' static grids."""
    for tx, ty in cv.orbit(cv.within(centre, 4)):
        if (tx, ty) not in cv.protected and world.terrain[ty][tx] is Terrain.TREES:
            world.terrain[ty][tx] = Terrain.GRASS
            world._blocked[ty * world.width + tx] = 0
            if world._forest is not None:
                world._forest[ty * world.width + tx] = 0


def _lay_encounters(world: World, cv: _Canvas, seed: int, main: Pos, natural: Pos | None, wilds: bool) -> None:
    """At most one Raid, Stronghold and Ancient orbit, where the finished map has safe side room.

    Small maps offer Raids; Medium adds Strongholds; Large adds an optional Ancient. Crowded
    boards may omit an expedition instead of forcing a PvE toll. Side clearings are prepared
    with or without occupants, so a camps-off comparison preserves the strategic map.
    """
    rng = random.Random(seed ^ _CAMP_SALT)
    halls = [b.center for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    safe_mines = list(cv.rect_images(main, 3))
    if natural is not None:
        safe_mines += list(cv.rect_images(natural, 3))
    doors, _mine_doors = _doors(world)
    goals = doors[1:] + [world.free_tile_near((*pos, 3, 3)) for pos in safe_mines]
    roads: set[Pos] = set()
    for goal in goals:
        if goal is not None:
            route = _route(world, doors[0], goal)
            if route is not None:
                roads.update(route)
    protected_routes = {tile for road in cv.orbit(roads) for tile in cv.within(tile_center(road), CAMP_WATCH + 0.8)}
    shared = _prepare_shared_ancient(world, cv, safe_mines)
    rects = [(b.pos, b.info.size) for b in world.buildings.values()]
    families: list[tuple[str, ...]] = [("wolf_den", "spider_nest")]
    if world.width * world.height >= 3000:
        families.append(("troll_mound", "stone_cairn"))
    if world.width * world.height >= 5000 and shared is None:
        families.append(("ancient_sanctum",))
    camp_sites: list[Point] = [] if shared is None else [_mine_centre(shared)]
    planned: list[tuple[Pos, str]] = [] if shared is None else [(shared, "ancient_sanctum")]
    if shared is not None:
        rects.append((shared, 3))
    # A cramped map keeps its approachable raid before offering harder expeditions.
    for index, family in enumerate(families):
        key = rng.choice(family)
        sites = _encounter_sites(world, cv, halls, safe_mines, rects, protected_routes, camp_sites, rng)
        if not sites:
            continue
        pos = sites[0]
        if index + 1 < len(families):
            # Keep another arena available rather than choosing the centre of a cramped flank.
            for candidate in sites:
                copies = cv.rect_images(candidate, 3)
                occupied = rects + [(image, 3) for image in copies]
                if any(_fits(cv, other, occupied, spacing=_CAMP_SPACING)
                       and all(_dist(_mine_centre(image), _mine_centre(rival)) >= _CAMP_SEPARATION
                               for image in copies for rival in cv.rect_images(other, 3)) for other in sites):
                    pos = candidate
                    break
        images = cv.rect_images(pos, 3)
        centre = _mine_centre(pos)
        region = reachable(world, doors[0])
        approach = min(region, key=lambda tile: (_dist(tile_center(tile), centre), tile))
        hard = {(x, y) for y in range(world.height) for x in range(world.width)
                if world.terrain[y][x] in (Terrain.WATER, Terrain.ROCK)}
        route = _cheapest_route(world, approach, (int(centre[0]), int(centre[1])), cv.protected | hard)
        if route is None:
            continue
        _carve(world, cv, route, trees_only=True)
        _clear_arena(world, cv, centre)
        planned += [(image, key) for image in images[:world.seats]]
        rects += [(image, 3) for image in images]
        camp_sites += [_mine_centre(image) for image in images]
    if shared is not None and not _prepare_bypasses(world, cv, safe_mines, [_mine_centre(pos) for pos, _key in planned]):
        planned = [(pos, key) for pos, key in planned if pos != shared]
    if wilds:
        for image, key in planned:
            camping.place_encounter(world, image, key)


# -- Assembly ----------------------------------------------------------------------


def _attempt(rng: random.Random, seed: int, width: int, height: int, players: int, human: int | None, theme: MapTheme,
             races: list[Race], layout: Layout, wilds: bool, rift_rng: random.Random, prize: BuildingType, magic: bool) -> tuple[World, dict]:
    spec = _SPECS[layout]
    cv = _Canvas(width, height, players)
    clearing = _clearing(spec, cv.cw, cv.ch, cv.wide)
    hall = _hall_corner(cv.cols, cv.rows, cv.cw, cv.ch)
    hc = (hall[0] + 1, hall[1] + 1)
    main = (hall[0] - 5, hall[1] - 4)
    if layout is Layout.FOREST:
        cv.paint(((x, y) for y in range(height) for x in range(width)), Terrain.TREES)
        motif = "deepwood"
    else:
        motif = _landscape(cv, rng, layout, hc)
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
            if layout is not Layout.FOREST:  # in the woods the clearing's edge already pockets it
                _pocket(cv, rng, natural, halls[0], rects, walls.gates | walls.fords)
    thirds: list[Pos] = []
    for _ in range(_third_orbits(spec, cv.cw, cv.ch)):
        third = _third_site(cv, rng, spec, halls, rects, walls.prefer_third)
        if third is None:
            problems.append("no room for a third mine")
            break
        thirds.append(third)
        _claim(cv, third, EXPANSION_GOLD, rects, mines, clearing=spec.third_clearing)
        if layout is not Layout.FOREST:
            _grove_beside(cv, rng, third, rects, walls.gates | walls.fords)
    if _wants_a_prize(spec, width, height, cv.cw, cv.ch):
        size = BUILDINGS[prize].size
        site = _prize_site(cv, rng, spec, halls, rects, size)
        if site is None:
            wishes.append(f"no room for a {BUILDINGS[prize].name}")
        else:  # an endless seam holds no stock: what it gives is a trip at a time, as long as it is held
            _claim(cv, site, 0 if prize is BuildingType.GOLD_SEAM else LODE_GOLD, rects, mines, clearing=spec.third_clearing, kind=prize)
    mines += walls.mines
    cv.symmetrize()
    if layout is Layout.FOREST:
        _forest_roads(cv, rng, hc, natural, thirds)
        cv.symmetrize()

    cv.frame()
    world = World(width, height, cv.grid, players, human=human, rng=random.Random(seed), theme=theme, races=races, layout=layout, magic=magic)
    for seat, pos in enumerate(cv.rect_images(hall, 3)[:players]):
        world.place_building(seat, BuildingType.TOWN_HALL, pos)
    for pos, kind, gold in mines:
        world.place_building(None, kind, pos).gold = gold
    for seat in range(players):
        for i in range(3):
            world.spawn_unit(seat, UnitType.PEASANT, tile_center(cv.images((hall[0] + i, hall[1] + 3))[seat]))
    _connect(world, cv)
    if magic and not _lay_rifts(world, cv, walls, hall, main, rift_rng):
        problems.append("no room for a ley rift")
    _lay_encounters(world, cv, seed, main, natural, wilds)
    world.update_vision()
    report = _audit(world, cv, spec, walls, natural)
    if layout is Layout.BASTION:
        world.gates = frozenset(cv.orbit(walls.gates))
        if natural is not None:
            world.gate_links = tuple(zip(cv.rect_images(hall, 3)[:players], cv.rect_images(natural, 3)[:players]))
    report["problems"] = problems + report["problems"]
    report["wishes"] = wishes  # nothing the audit looks at is a wish: an unfair map is a fault, every time
    report["motif"] = motif  # the centre the seed drew; describe() reads the same place off the ground
    report["story"] = describe(world)
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
    return room == 0 or int_sum(1 for tx, ty in cv.within(middle, 4.0) if world.passable(tx, ty)) >= room


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


def _carve(world: World, cv: _Canvas, route: list[Pos], *, trees_only: bool = False) -> None:
    for x, y in route:
        for brush in ((x, y), (x + 1, y), (x, y + 1)):
            for nx, ny in cv.images(brush):
                # A tile whose copies include one on the rim is carved everywhere but there: the rim
                # is a frame outside play, and leaving it would wall two cells off from each other.
                if cv.inside(nx, ny) and (nx, ny) not in cv.protected and world.building_at((nx, ny)) is None \
                        and world.terrain_at((nx, ny)) is not Terrain.GRASS \
                        and (not trees_only or world.terrain_at((nx, ny)) is Terrain.TREES):
                    world.terrain[ny][nx] = Terrain.GRASS
                    world._blocked[ny * world.width + nx] = 0
                    if world._forest is not None:
                        world._forest[ny * world.width + nx] = 0


# -- The story a map tells --------------------------------------------------------

#: Kept short on purpose: a description captions the preview beside its picture on a 680-pixel
#: screen, where the whole story has some 155 characters of height to live in.
_CENTRE_PHRASES: Final = {
    "lake": "a lake fills the centre — pass either side",
    "mesa": "a rock mesa blocks the centre",
    "greatwood": "a great wood fills the centre — chop or go round",
    "marsh": "marsh ponds break the centre",
    "field": "an open field fills the centre",
}


def _centre_place(world: World) -> str:
    """Which of :data:`_MOTIFS`' places the finished ground has at its middle, read off the tiles
    within six of the centre rather than trusted from the draw: what a player sees is what the
    description may claim."""
    centre = (world.width / 2, world.height / 2)
    tiles = [(x, y) for y in range(int(centre[1]) - 6, int(centre[1]) + 7)
             for x in range(int(centre[0]) - 6, int(centre[0]) + 7)
             if 0 <= x < world.width and 0 <= y < world.height and _dist((x, y), centre) <= 6]
    share = {kind: int_sum(1 for x, y in tiles if world.terrain[y][x] is kind) / len(tiles)
             for kind in (Terrain.WATER, Terrain.ROCK, Terrain.TREES)}
    inner = [tile for tile in tiles if _dist(tile, centre) <= 2.5]
    flooded = int_sum(1 for x, y in inner if world.terrain[y][x] is Terrain.WATER) / max(1, len(inner))
    if share[Terrain.ROCK] >= 0.3:
        return "mesa"
    if flooded >= 0.6:  # a lake covers the middle itself; a marsh rings it with ponds
        return "lake"
    if share[Terrain.WATER] >= 0.12:
        return "marsh"
    if share[Terrain.TREES] >= 0.45:
        return "greatwood"
    return "field"


def _own_naturals(world: World, halls: list[Building]) -> dict[int, Building]:
    """Each hall's own expansion mine: the nearest 30 000 mine nearer it than any other hall."""
    own: dict[int, Building] = {}
    for hall in halls:
        candidates = [m for m in world.mines() if m.type is BuildingType.GOLD_MINE and m.gold == EXPANSION_GOLD
                      and all(_dist(m.center, other.center) > _dist(m.center, hall.center) for other in halls if other is not hall)]
        if candidates:
            own[hall.id] = min(candidates, key=lambda m: _dist(m.center, hall.center))
    return own


def describe(world: World) -> str:
    """This map in two plain sentences, read off the finished ground: the place at its centre,
    where the second base lies and what shelters it, and what the middle game is fought over.

    Phrased by relation (toward the centre, along the home edge) rather than compass points, so
    it is true from every seat of a symmetric map at once.  The New game screen shows it under
    the layout's promise, and a seed whose ground supports no such sentences is a map with
    nothing to plan around — which is what the generator exists to avoid."""
    halls = sorted((b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL),
                   key=lambda b: b.player if b.player is not None else -1)
    if not halls:
        return ""
    hall = halls[0]
    centre = (world.width / 2, world.height / 2)
    own = _own_naturals(world, halls)
    natural = own.get(hall.id)
    mine_word = lambda n: "mine" if n == 1 else "mines"
    if world.layout is Layout.KLONDIKE:
        pit = int_sum(1 for m in world.mines() if m.gold == EXPANSION_GOLD)
        return (f"Home gold is short: the match is the {pit} {mine_word(pit)} in the central rock pit — "
                f"take a gate and hold it, or fall back on the poor corner mine.")
    contested = [m for m in world.mines() if m.type is BuildingType.GOLD_MINE and m.gold == EXPANSION_GOLD
                 and m not in own.values()]
    if world.layout is Layout.CROSSINGS:
        waters = [(x, y) for y in range(world.height) for x in range(world.width) if world.terrain[y][x] is Terrain.WATER]
        banks = bool(contested) and bool(waters) and min(_dist(m.center, tile) for m in contested for tile in waters) <= 6
        by_fords = "on the banks by the fords" if banks else "inland, behind the river"
        return (f"One river, three fords: the wide centre ford is the short road. "
                f"Naturals face it; the {len(contested)} contested {mine_word(len(contested))} sit {by_fords}.")
    # Where the second base lies, and what stands behind it.
    lies, shelter = "toward the centre", "on open ground"
    if natural is not None:
        to_centre = (centre[0] - hall.center[0], centre[1] - hall.center[1])
        out = (natural.center[0] - hall.center[0], natural.center[1] - hall.center[1])
        facing = (out[0] * to_centre[0] + out[1] * to_centre[1]) / ((_dist(out, (0.0, 0.0)) or 1.0) * (_dist(to_centre, (0.0, 0.0)) or 1.0))
        lies = "toward the centre" if facing > 0.55 else "along the home edge" if facing > -0.2 else "behind the base"
        far = [(x, y) for y in range(int(natural.center[1]) - 7, int(natural.center[1]) + 8)
               for x in range(int(natural.center[0]) - 7, int(natural.center[0]) + 8)
               if 0 <= x < world.width and 0 <= y < world.height and 4.5 <= _dist((x, y), natural.center) <= 7.0
               and (x - natural.center[0]) * out[0] + (y - natural.center[1]) * out[1] > 0]
        walled = [world.terrain[y][x] for x, y in far if world.terrain[y][x] is not Terrain.GRASS]
        kinds = {kind: walled.count(kind) for kind in (Terrain.TREES, Terrain.ROCK, Terrain.WATER)}
        backing = max(kinds, key=lambda k: kinds[k]) if walled else Terrain.GRASS
        shelter = {Terrain.TREES: "tree-backed, mouths home", Terrain.ROCK: "rock-backed, mouths home",
                   Terrain.WATER: "water-backed, mouths home"}.get(backing, "on open ground")
        if len(walled) < 0.35 * max(1, len(far)):
            shelter = "on open ground"
    second = f"Naturals lie {lies}, {shelter}" if natural is not None else "There is no safe second base"
    middle = (f"the {len(contested)} contested {mine_word(len(contested))} are the prize" if contested
              else "the middle game goes to who expands furthest")
    if world.layout is Layout.FOREST:
        hidden = f"Naturals hide in clearings {lies}" if natural is not None else second
        return f"Roads wind between clearings; fights start at their mouths. {hidden}, and {middle}."
    centre_phrase = _CENTRE_PHRASES[_centre_place(world)]
    if world.layout is Layout.BASTION:
        return f"One gate in each tree ring, naturals outside; beyond, {centre_phrase}, and {middle}."
    return f"{centre_phrase[0].upper() + centre_phrase[1:]}. {second}, and {middle}."


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
        report["open"].append(int_sum(1 for dx in range(-6, 7) for dy in range(-6, 7) if world.passable(cx + dx, cy + dy)))
        report["mine"].append(min(max(abs(m.center[0] - hall.center[0]), abs(m.center[1] - hall.center[1])) for m in world.mines()))
        tree = world.nearest_tree(hall.center, 12)
        report["wood"].append(None if tree is None else max(abs(tree[0] - cx), abs(tree[1] - cy)))
        report["rift"].append(min((max(abs(x + RIFT / 2 - hall.center[0]), abs(y + RIFT / 2 - hall.center[1])) for x, y in world.rifts),
                                  default=None))
    report["connected"] = all(d in region for d in doors + mine_doors + list(world.rifts))
    report["rifts"] = len(world.rifts)
    report["expansions"] = len(world.mines()) - len(halls)
    report["seams"] = int_sum(1 for m in world.mines() if m.type is BuildingType.GOLD_SEAM)
    report["lodes"] = int_sum(1 for m in world.mines() if m.type is BuildingType.MOTHER_LODE)
    report["camps"] = len(world.camps)
    total = world.width * world.height
    report["trees"] = int_sum(1 for row in world.terrain for t in row if t is Terrain.TREES) / total
    report["water"] = int_sum(1 for row in world.terrain for t in row if t is Terrain.WATER) / total
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


def _route(world: World, start: Pos, goal: Pos, *, ignore_camps: bool = False) -> list[Pos] | None:
    """The production pathfinder's route, or None when its budget runs out first."""
    if start == goal:
        return []
    grid = world._blocked
    if ignore_camps and world.camps:
        grid = bytearray(grid)
        for camp in world.camps:
            lair = world.buildings.get(camp.lair)
            if lair is not None:
                for x, y in lair.tiles():
                    grid[y * world.width + x] = 0
    route = pathing.find_path_grid(start, goal, grid, world.width, world.height, max_expansions=world.path_budget)
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
    if world.magic:
        problems += _rift_problems(world, cv)
    report["detour"] = None
    # Layout detours describe permanent terrain, so optional lair footprints cannot change a seed
    # from accepted to retried when wilds is toggled. Actual routes above still check the budget.
    route = _route(world, doors[0], doors[1], ignore_camps=True)
    if route is not None:
        walk = plain_sum(pathing.octile(a, b) for a, b in zip([doors[0]] + route, route))
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
