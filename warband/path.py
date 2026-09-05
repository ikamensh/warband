"""A* over a tile grid: eight-way moves, no corner cutting, bounded search.

The grid is any callable ``passable(x, y) -> bool``.  A goal that cannot
be reached (a building, a tree, an island) yields the path to the
reachable tile nearest it, which is exactly what a unit walking up to a
building or a tree wants.
"""

from __future__ import annotations

import heapq
import math
from typing import Callable, Iterator

Pos = tuple[int, int]
Passable = Callable[[int, int], bool]

SQRT2 = math.sqrt(2)
_STEPS: tuple[tuple[int, int, float], ...] = (
    (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
    (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2),
)
MAX_EXPANSIONS = 6000


def octile(a: Pos, b: Pos) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (SQRT2 - 1) * min(dx, dy)


def neighbours(pos: Pos, passable: Passable) -> Iterator[tuple[Pos, float]]:
    """Passable neighbours; a diagonal step needs both orthogonal tiles free."""
    x, y = pos
    for dx, dy, cost in _STEPS:
        nx, ny = x + dx, y + dy
        if not passable(nx, ny):
            continue
        if dx and dy and not (passable(x + dx, y) and passable(x, y + dy)):
            continue
        yield (nx, ny), cost


def find_path(start: Pos, goal: Pos, passable: Passable, *, max_expansions: int = MAX_EXPANSIONS) -> list[Pos]:
    """Tiles from *start* (exclusive) to *goal*, or to the reachable tile
    nearest *goal* when it cannot be reached.  Empty when already there."""
    if start == goal:
        return []
    g_score: dict[Pos, float] = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    best, best_h = start, octile(start, goal)
    frontier: list[tuple[float, float, Pos]] = [(best_h, 0.0, start)]
    closed: set[Pos] = set()
    expansions = 0
    while frontier and expansions < max_expansions:
        _f, g, current = heapq.heappop(frontier)
        if current in closed:
            continue
        closed.add(current)
        expansions += 1
        if current == goal:
            best = current
            break
        for nxt, cost in neighbours(current, passable):
            ng = g + cost
            if ng < g_score.get(nxt, math.inf):
                g_score[nxt] = ng
                parent[nxt] = current
                h = octile(nxt, goal)
                if h < best_h or (h == best_h and ng < g_score[best]):
                    best, best_h = nxt, h
                heapq.heappush(frontier, (ng + h, ng, nxt))
    path: list[Pos] = []
    node = best
    while node != start:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def nearest_passable(origin: Pos, passable: Passable, *, max_radius: int = 12, prefer: Pos | None = None) -> Pos | None:
    """The passable tile nearest *origin* (Chebyshev rings), ties broken towards *prefer*."""
    for r in range(max_radius + 1):
        ring = [(origin[0] + dx, origin[1] + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
        candidates = [p for p in ring if passable(*p)]
        if candidates:
            if prefer is None:
                return min(candidates, key=lambda p: (p[0] - origin[0]) ** 2 + (p[1] - origin[1]) ** 2)
            return min(candidates, key=lambda p: (p[0] - prefer[0]) ** 2 + (p[1] - prefer[1]) ** 2)
    return None
