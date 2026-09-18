"""A sight disc must be the same shape wherever it lands on the map.

``World._reveal`` paints a disc that lies wholly on the map as one big integer and
clips one row at a time near an edge; the two paths have to agree with the spans
:func:`sight_spans` describes, or a unit standing near a border would see differently
from the same unit two tiles inland.
"""

import random

from warband.model import World, sight_spans
from warband.rules import Terrain

WIDTH, HEIGHT = 24, 21


def flat_world() -> World:
    terrain = [[Terrain.GRASS] * WIDTH for _ in range(HEIGHT)]
    return World(WIDTH, HEIGHT, terrain, 2, rng=random.Random(1))


def spanned(at: tuple[int, int], radius: int) -> set[tuple[int, int]]:
    """The disc as the spans describe it, clipped to the map."""
    x0, y0 = at
    return {(x0 + dx, y0 + dy)
            for dy, half, _run in sight_spans(radius)
            for dx in range(-half, half + 1)
            if 0 <= x0 + dx < WIDTH and 0 <= y0 + dy < HEIGHT}


def test_reveal_paints_the_spans_from_every_tile() -> None:
    world = flat_world()
    for radius in (0, 1, 4, 7):
        for y in range(HEIGHT):
            for x in range(WIDTH):
                visible = bytearray(WIDTH * HEIGHT)
                world._reveal(visible, (x, y), radius)
                painted = {(index % WIDTH, index // WIDTH) for index, flag in enumerate(visible) if flag}
                assert painted == spanned((x, y), radius), f"radius {radius} at {(x, y)}"


def test_reveal_only_adds_to_what_is_already_seen() -> None:
    """Discs are OR-ed together: revealing never clears a tile another disc lit."""
    world = flat_world()
    visible = bytearray(WIDTH * HEIGHT)
    world._reveal(visible, (4, 4), 4)
    world._reveal(visible, (18, 15), 7)  # far away, and wholly on the map
    painted = {(index % WIDTH, index // WIDTH) for index, flag in enumerate(visible) if flag}
    assert painted == spanned((4, 4), 4) | spanned((18, 15), 7)
