"""A* over a tile grid: straight lines, detours, no corner cutting, unreachable goals."""

import random

import pytest

from warband.path import SQRT2, Regions, find_path, find_path_grid, nearest_passable, octile


def grid(rows: list[str]):
    def passable(x: int, y: int) -> bool:
        return 0 <= y < len(rows) and 0 <= x < len(rows[0]) and rows[y][x] == "."

    return passable


def test_straight_line_is_a_diagonal_walk() -> None:
    passable = grid(["....", "....", "....", "...."])
    assert find_path((0, 0), (3, 3), passable) == [(1, 1), (2, 2), (3, 3)]
    assert find_path((2, 2), (2, 2), passable) == []


def test_walls_force_a_detour_and_diagonals_never_cut_corners() -> None:
    rows = [
        ".....",
        ".###.",
        ".#...",
        ".#.#.",
        ".....",
    ]
    passable = grid(rows)
    path = find_path((0, 0), (2, 2), passable)
    assert path[-1] == (2, 2)
    for (ax, ay), (bx, by) in zip([(0, 0)] + path, path):
        assert passable(bx, by)
        if ax != bx and ay != by:
            assert passable(bx, ay) and passable(ax, by), "cut a corner"


def test_unreachable_goal_yields_the_path_to_the_nearest_tile() -> None:
    rows = [
        "......",
        "..###.",
        "..#.#.",
        "..###.",
        "......",
    ]
    passable = grid(rows)
    path = find_path((0, 2), (3, 2), passable)
    assert path and all(passable(*p) for p in path)
    assert octile(path[-1], (3, 2)) == min(octile(p, (3, 2)) for p in path)
    assert octile(path[-1], (3, 2)) == 2  # the ring of walls keeps everything two steps away


def test_path_to_a_blocked_goal_ends_next_to_it() -> None:
    rows = [
        ".....",
        "..#..",
        ".....",
    ]
    passable = grid(rows)
    path = find_path((0, 1), (2, 1), passable)
    assert path[-1] in ((1, 1), (1, 0), (1, 2))


def test_nearest_passable_prefers_the_side_asked_for() -> None:
    rows = [
        ".....",
        ".###.",
        ".....",
    ]
    passable = grid(rows)
    assert nearest_passable((2, 1), passable, prefer=(2, 0)) == (2, 0)
    assert nearest_passable((2, 1), passable, prefer=(2, 5)) == (2, 2)
    assert nearest_passable((2, 1), grid(["###", "###", "###"]), max_radius=1) is None


# -- The grid search against the reference, and regions ---------------------------------


def random_grid(rng: random.Random) -> tuple[bytearray, int, int]:
    width, height = rng.randint(3, 14), rng.randint(3, 14)
    return bytearray(int(rng.random() < 0.3) for _ in range(width * height)), width, height


def walk_cost(start, path, passable) -> float:
    """The cost of walking *path* from *start*; fails when a step is not a legal move."""
    total = 0.0
    for (ax, ay), (bx, by) in zip([start] + path, path):
        assert passable(bx, by) and max(abs(ax - bx), abs(ay - by)) == 1
        if ax != bx and ay != by:
            assert passable(bx, ay) and passable(ax, by), "cut a corner"
            total += SQRT2
        else:
            total += 1
    return total


def test_the_grid_search_walks_legally_and_as_short_as_the_reference() -> None:
    """find_path_grid is find_path rewritten for speed: on random grids both must reach the goal
    (or the same distance from it) at the same cost, by legal steps only."""
    rng = random.Random(1)
    for _ in range(80):
        blocked, width, height = random_grid(rng)
        open_tiles = [(i % width, i // width) for i in range(width * height) if not blocked[i]]
        if len(open_tiles) < 2:
            continue
        start, goal = rng.sample(open_tiles, 2)

        def passable(x: int, y: int) -> bool:
            return 0 <= x < width and 0 <= y < height and not blocked[y * width + x]

        reference = find_path(start, goal, passable)
        path = find_path_grid(start, goal, blocked, width, height)
        assert walk_cost(start, path, passable) == pytest.approx(walk_cost(start, reference, passable))
        assert octile(path[-1] if path else start, goal) == pytest.approx(octile(reference[-1] if reference else start, goal))


def test_regions_join_exactly_the_tiles_a_unit_can_walk_between() -> None:
    rows = [
        "..#..",
        "..#..",
        "##...",
        ".....",
    ]
    width, height = 5, 4
    blocked = bytearray(int(cell == "#") for row in rows for cell in row)
    regions = Regions(blocked, width, height)
    assert regions.label((0, 0)) == regions.label((1, 1)) != 0
    assert regions.label((1, 1)) != regions.label((2, 2)), "touching at a corner only is no passage"
    assert regions.label((0, 3)) == regions.label((4, 0)), "the bottom row leads round to the right side"
    assert regions.label((2, 0)) == 0


def test_a_goal_in_another_region_becomes_the_nearest_tile_of_the_units_own() -> None:
    rows = [
        "..#..",
        "..#..",
        "##...",
        ".....",
    ]
    blocked = bytearray(int(cell == "#") for row in rows for cell in row)
    regions = Regions(blocked, 5, 4)
    assert regions.reachable_goal((0, 3), (4, 0)) == (4, 0), "reachable goals stay"
    assert regions.reachable_goal((0, 0), (4, 0)) == (1, 0)
    assert regions.reachable_goal((4, 0), (0, 0)) == (2, 2), "the corner-only neighbour, 2.83 away, beats the bottom row's 3"
    # The substitute is where the full search would have ended: the same octile distance from the goal.
    reference = find_path((0, 0), (4, 0), lambda x, y: 0 <= x < 5 and 0 <= y < 4 and not blocked[y * 5 + x])
    assert octile(reference[-1], (4, 0)) == octile(regions.reachable_goal((0, 0), (4, 0)), (4, 0))
