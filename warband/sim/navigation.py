"""The static walking grids, their connectivity, and edits that keep them consistent.

Callers may read a grid for path searches; terrain and building footprints change
through this module so the ordinary and forest grids cannot drift apart. Movement
orders and avoidance of remembered enemies remain rules of the World.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

from warband.sim import path
from warband.sim.rules import Terrain

Pos = tuple[int, int]
Point = tuple[float, float]
BLOCKING: Final = frozenset({Terrain.WATER, Terrain.TREES, Terrain.ROCK})
_TRUTH: Final = bytes([0] + [1] * 255)


@dataclass
class NavigationState:
    """A reversible map-generation edit, including a forest grid if already requested."""

    terrain: list[list[Terrain]]
    ground: bytearray
    forest: bytearray | None


class Navigation:
    def __init__(self, width: int, height: int, terrain: list[list[Terrain]], changed: Callable[[], None]) -> None:
        self.width = width
        self.height = height
        self._terrain = terrain
        self._changed = changed
        self.ground = bytearray(tile in BLOCKING for row in terrain for tile in row)
        self._forest: bytearray | None = None
        self._regions: path.Regions | None = None
        self._forest_regions: path.Regions | None = None

    def grid(self, *, forest: bool = False) -> bytearray:
        """The ordinary or forest walking grid, borrowed for reading by path searches."""
        if not forest:
            return self.ground
        if self._forest is None:
            self._forest = bytearray(self.ground)
            for y, row in enumerate(self._terrain):
                for x in range(self.width):
                    if row[x] is Terrain.TREES:
                        self._forest[y * self.width + x] = 0
        return self._forest

    def regions(self, *, forest: bool = False) -> path.Regions:
        """Connectivity for this walking kind, rebuilt after its grid changes."""
        grid = self.grid(forest=forest)
        cached = self._forest_regions if forest else self._regions
        if cached is None or cached.grid != grid:
            cached = path.Regions(grid, self.width, self.height)
            if forest:
                self._forest_regions = cached
            else:
                self._regions = cached
        return cached

    def set_terrain(self, tile: Pos, kind: Terrain) -> None:
        """Paint an unoccupied terrain tile, keeping both walking kinds in step."""
        x, y = tile
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"terrain tile outside map: {tile}")
        self._terrain[y][x] = kind
        self.ground[y * self.width + x] = int(kind in BLOCKING)
        if self._forest is not None:
            self._forest[y * self.width + x] = int(kind is Terrain.WATER or kind is Terrain.ROCK)
        self._changed()

    def set_footprint(self, rect: tuple[int, int, int, int], blocked: bool) -> None:
        """Place or remove a building's solid footprint for both walking kinds."""
        left, top, width, height = rect
        for y in range(top, top + height):
            for x in range(left, left + width):
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.ground[y * self.width + x] = int(blocked)
                    if self._forest is not None:
                        self._forest[y * self.width + x] = int(blocked)
        self._changed()

    def checkpoint(self) -> NavigationState:
        """Remember terrain and derived grids before trying a map-generation candidate."""
        return NavigationState([row[:] for row in self._terrain], bytearray(self.ground),
                               bytearray(self._forest) if self._forest is not None else None)

    def restore(self, state: NavigationState) -> None:
        """Undo a candidate without invalidating references to the map's terrain or ordinary grid."""
        for row, saved in zip(self._terrain, state.terrain):
            row[:] = saved
        self.ground[:] = state.ground
        self._forest = bytearray(state.forest) if state.forest is not None else None
        self._changed()

    def check(self, building_tiles: Iterable[Pos]) -> None:
        """Assert that both grids describe the terrain and building footprints (the fuzz invariant)."""
        expected = bytearray(tile in BLOCKING for row in self._terrain for tile in row)
        for x, y in building_tiles:
            expected[y * self.width + x] = 1
        # mypyc's zip lowering supports bytes, but rejects bytearray sequences.
        expected_bytes = bytes(expected)
        blocked = bytes(self.ground.translate(_TRUTH))
        if blocked != expected_bytes:
            i = next(i for i, (have, want) in enumerate(zip(blocked, expected_bytes)) if have != want)
            raise AssertionError(("blocked grid mismatch", (i % self.width, i // self.width)))
        if self._forest is not None:
            trees = bytes(tile is Terrain.TREES for row in self._terrain for tile in row)
            want = bytes(e & (1 - t) for e, t in zip(expected_bytes, trees))
            have = bytes(self._forest.translate(_TRUTH))
            if have != want:
                i = next(i for i, (a, b) in enumerate(zip(have, want)) if a != b)
                raise AssertionError(("forest grid mismatch", (i % self.width, i // self.width)))

    def line_clear(self, a: Point, b: Point, *, navigation: bytearray | None = None) -> bool:
        """No blocked tile on the straight line from *a* to *b*.

        Every tile the segment crosses is visited (a grid walk, not sampling: a
        sample every quarter tile can skip the corner tile a unit standing at a
        building's corner would step into).  Passing exactly through a corner
        needs both tiles beside it free, as a diagonal step in the pathfinder does.
        """
        # Check continuous coordinates before int() can turn -0.1 into tile zero.
        width, height = self.width, self.height
        if not (0 <= a[0] < width and 0 <= a[1] < height
                and 0 <= b[0] < width and 0 <= b[1] < height):
            return False
        grid = self.ground if navigation is None else navigation
        x, y = int(a[0]), int(a[1])
        end_x, end_y = int(b[0]), int(b[1])
        dx, dy = b[0] - a[0], b[1] - a[1]
        step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        # Fraction of the segment at which the next vertical / horizontal grid line is crossed.
        next_x = ((x + (step_x > 0)) - a[0]) / dx if dx else math.inf
        next_y = ((y + (step_y > 0)) - a[1]) / dy if dy else math.inf
        per_x, per_y = (abs(1 / dx) if dx else math.inf), (abs(1 / dy) if dy else math.inf)
        # The walk never leaves the box spanned by the two endpoints' tiles: once it stands in the end tile's
        # column (or row), the only way on is along it.  A segment ending exactly on a tile's corner otherwise stepped
        # across the corner at its very end, out of the box and off the map (a crowd skipping ahead along its path,
        # race report seed 27).  So only the two tiles beside an inner corner need their own bounds test.
        row = y * width
        for _ in range(abs(end_x - x) + abs(end_y - y) + 1):
            if grid[row + x]:
                return False
            if x == end_x and y == end_y:
                return True
            if abs(next_x - next_y) < 1e-9 and x != end_x and y != end_y:
                beside_x, beside_y = x + step_x, y + step_y
                if not 0 <= beside_x < width or grid[row + beside_x]:
                    return False
                if not 0 <= beside_y < height or grid[beside_y * width + x]:
                    return False
                x, y, row = beside_x, beside_y, beside_y * width
                next_x, next_y = next_x + per_x, next_y + per_y
            elif y == end_y or (x != end_x and next_x < next_y):
                x, next_x = x + step_x, next_x + per_x
            else:
                y, next_y, row = y + step_y, next_y + per_y, row + step_y * width
        return not grid[row + x]


    def clamp(self, point: Point) -> Point:
        """Keep a continuous point inside the playable map."""
        return (min(max(point[0], 0.05), self.width - 0.05), min(max(point[1], 0.05), self.height - 0.05))
