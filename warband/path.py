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
MAX_EXPANSIONS = 3000


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


def find_path_grid(start: Pos, goal: Pos, blocked: bytes | bytearray, width: int, height: int, *, max_expansions: int = MAX_EXPANSIONS) -> list[Pos]:
    """:func:`find_path` over a row-major ``blocked`` byte grid, inlined for speed (the model's hot path)."""
    if start == goal:
        return []
    sx, sy = start
    gx, gy = goal
    g_score: dict[Pos, float] = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    best, best_h = start, octile(start, goal)
    frontier: list[tuple[float, float, int, int]] = [(best_h, 0.0, sx, sy)]
    closed: set[Pos] = set()
    expansions = 0
    push, pop = heapq.heappush, heapq.heappop
    while frontier and expansions < max_expansions:
        _f, g, x, y = pop(frontier)
        current = (x, y)
        if current in closed:
            continue
        closed.add(current)
        expansions += 1
        if x == gx and y == gy:
            best = current
            break
        row = y * width
        east = x + 1 < width and not blocked[row + x + 1]
        west = x > 0 and not blocked[row + x - 1]
        south = y + 1 < height and not blocked[row + width + x]
        north = y > 0 and not blocked[row - width + x]
        for nx, ny, cost, ok in (
            (x + 1, y, 1.0, east), (x - 1, y, 1.0, west), (x, y + 1, 1.0, south), (x, y - 1, 1.0, north),
            (x + 1, y + 1, SQRT2, east and south and not blocked[row + width + x + 1]),
            (x + 1, y - 1, SQRT2, east and north and not blocked[row - width + x + 1]),
            (x - 1, y + 1, SQRT2, west and south and not blocked[row + width + x - 1]),
            (x - 1, y - 1, SQRT2, west and north and not blocked[row - width + x - 1]),
        ):
            if not ok:
                continue
            nxt = (nx, ny)
            ng = g + cost
            if ng < g_score.get(nxt, math.inf):
                g_score[nxt] = ng
                parent[nxt] = current
                dx, dy = abs(nx - gx), abs(ny - gy)
                h = (dx + dy + (SQRT2 - 2) * dy) if dx > dy else (dx + dy + (SQRT2 - 2) * dx)
                if h < best_h or (h == best_h and ng < g_score[best]):
                    best, best_h = nxt, h
                push(frontier, (ng + h, ng, nx, ny))
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


def find_work_path(start: Pos, goals: dict[Pos, float], blocked: bytes | bytearray,
                   width: int, height: int) -> list[Pos] | None:
    """Shortest route to an interaction tile, including its crowding penalty.

    Unlike movement A*, this must reach a real goal: a closest partial path
    cannot deliver cargo or harvest a resource. None means no reachable goal;
    an empty path means the worker already occupies the chosen goal.
    """
    if not goals:
        return None
    def passable(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height and not blocked[y * width + x]

    costs = {start: 0.0}
    parents: dict[Pos, Pos] = {}
    frontier = [(0.0, start)]
    best, best_cost = None, math.inf
    while frontier:
        cost, current = heapq.heappop(frontier)
        if cost >= best_cost:
            break
        if cost != costs[current]:
            continue
        if current in goals and cost + goals[current] < best_cost:
            best, best_cost = current, cost + goals[current]
        for nxt, step in neighbours(current, passable):
            total = cost + step
            if total < costs.get(nxt, math.inf):
                costs[nxt] = total
                parents[nxt] = current
                heapq.heappush(frontier, (total, nxt))
    if best is None:
        return None
    route = []
    while best != start:
        route.append(best)
        best = parents[best]
    route.reverse()
    return route
