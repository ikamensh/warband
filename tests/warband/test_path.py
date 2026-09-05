"""A* over a tile grid: straight lines, detours, no corner cutting, unreachable goals."""

from warband.path import find_path, nearest_passable, octile


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
