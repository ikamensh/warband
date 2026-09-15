"""A* over a tile grid: eight-way moves, no corner cutting, bounded search.

The grid is any callable ``passable(x, y) -> bool``.  A goal that cannot
be reached (a building, a tree, an island) yields the path to the
reachable tile nearest it, which is exactly what a unit walking up to a
building or a tree wants.
"""

from __future__ import annotations

import heapq
import itertools
import math
from typing import Callable, Iterable, Iterator

Pos = tuple[int, int]
Passable = Callable[[int, int], bool]

SQRT2 = math.sqrt(2)
DIAGONAL = SQRT2 - 2  # what a diagonal step saves against two orthogonal ones, for the octile heuristic
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
    """:func:`find_path` over a row-major ``blocked`` byte grid: the model's hot path, written for speed.

    Tiles are flat indices, scores and parents flat lists, and the frontier holds
    ``(f, g, index)``, so equal f goes to the smaller g and then the lower index.
    A goal in another region floods everything reachable; :class:`Regions` lets a
    caller substitute a reachable goal first.
    """
    if start == goal:
        return []
    size = width * height
    origin = start[1] * width + start[0]
    gx, gy = goal
    g_score = [math.inf] * size
    g_score[origin] = 0.0
    parent = [-1] * size
    done = bytearray(size)
    dx, dy = abs(start[0] - gx), abs(start[1] - gy)
    best, best_h = origin, (dx + dy + DIAGONAL * dy) if dx > dy else (dx + dy + DIAGONAL * dx)
    frontier = [(best_h, 0.0, origin)]
    expansions = 0
    push, pop = heapq.heappush, heapq.heappop
    while frontier and expansions < max_expansions:
        _f, g, current = pop(frontier)
        if done[current]:
            continue
        done[current] = 1
        expansions += 1
        y, x = divmod(current, width)
        if x == gx and y == gy:
            best = current
            break
        east = x + 1 < width and not blocked[current + 1]
        west = x > 0 and not blocked[current - 1]
        south = y + 1 < height and not blocked[current + width]
        north = y > 0 and not blocked[current - width]
        for offset, nx, ny, cost, open_ in (
            (1, x + 1, y, 1.0, east), (-1, x - 1, y, 1.0, west), (width, x, y + 1, 1.0, south), (-width, x, y - 1, 1.0, north),
            (width + 1, x + 1, y + 1, SQRT2, east and south), (1 - width, x + 1, y - 1, SQRT2, east and north),
            (width - 1, x - 1, y + 1, SQRT2, west and south), (-width - 1, x - 1, y - 1, SQRT2, west and north),
        ):
            if not open_:
                continue
            nxt = current + offset
            if blocked[nxt]:
                continue  # the diagonal tile itself; an orthogonal one was checked above
            ng = g + cost
            if ng < g_score[nxt]:
                g_score[nxt] = ng
                parent[nxt] = current
                dx, dy = abs(nx - gx), abs(ny - gy)
                h = (dx + dy + DIAGONAL * dy) if dx > dy else (dx + dy + DIAGONAL * dx)
                if h < best_h or (h == best_h and ng < g_score[best]):
                    best, best_h = nxt, h
                push(frontier, (ng + h, ng, nxt))
    path: list[Pos] = []
    node = best
    while node != origin:
        path.append(divmod(node, width)[::-1])
        node = parent[node]
    path.reverse()
    return path


class Regions:
    """The connected regions of a blocked grid: two tiles share a region exactly when a
    unit can walk between them.  A diagonal step needs both orthogonal tiles free, so
    orthogonal adjacency is what joins tiles.  Blocked tiles have region 0.

    ``grid`` keeps the bytes the labels were computed from, so an owner can tell when
    the grid has changed underneath (``regions.grid != blocked``).
    """

    def __init__(self, blocked: bytes | bytearray, width: int, height: int) -> None:
        self.grid = bytes(blocked)
        self.width, self.height = width, height
        size = width * height
        labels = [0] * size
        region = 0
        for seed in range(size):
            if blocked[seed] or labels[seed]:
                continue
            region += 1
            labels[seed] = region
            stack = [seed]
            while stack:
                index = stack.pop()
                x = index % width
                for nxt in (index - width, index + width, index - 1 if x else -1, index + 1 if x + 1 < width else -1):
                    if 0 <= nxt < size and not blocked[nxt] and not labels[nxt]:
                        labels[nxt] = region
                        stack.append(nxt)
        self.labels = labels
        self._nearest: dict[tuple[Pos, int], Pos] = {}

    def label(self, pos: Pos) -> int:
        return self.labels[pos[1] * self.width + pos[0]]

    def reachable_goal(self, start: Pos, goal: Pos) -> Pos:
        """*goal* when a walk from *start* can reach it, else the tile of *start*'s region nearest
        it (octile distance, ties by row-major order): where a search for *goal* would end up anyway,
        found without the search.  A blocked *start* is returned *goal* unchanged."""
        region = self.label(start)
        if region == 0 or self.label(goal) == region:
            return goal
        key = (goal, region)
        nearest = self._nearest.get(key)
        if nearest is None:
            gx, gy = goal
            width = self.width
            best, best_h = goal, math.inf
            for index in itertools.compress(range(len(self.labels)), (label == region for label in self.labels)):
                dx, dy = abs(index % width - gx), abs(index // width - gy)
                h = (dx + dy + DIAGONAL * dy) if dx > dy else (dx + dy + DIAGONAL * dx)
                if h < best_h:
                    best, best_h = (index % width, index // width), h
            nearest = self._nearest[key] = best
        return nearest


def grid_steps(index: int, blocked: bytes | bytearray, width: int, height: int) -> list[tuple[int, float]]:
    """The passable neighbours of flat tile *index* with their step costs; a diagonal step needs
    both orthogonal tiles free.  :func:`find_path_grid` inlines this for speed."""
    y, x = divmod(index, width)
    east = x + 1 < width and not blocked[index + 1]
    west = x > 0 and not blocked[index - 1]
    south = y + 1 < height and not blocked[index + width]
    north = y > 0 and not blocked[index - width]
    steps = []
    if east:
        steps.append((index + 1, 1.0))
    if west:
        steps.append((index - 1, 1.0))
    if south:
        steps.append((index + width, 1.0))
    if north:
        steps.append((index - width, 1.0))
    if east and south and not blocked[index + width + 1]:
        steps.append((index + width + 1, SQRT2))
    if east and north and not blocked[index - width + 1]:
        steps.append((index - width + 1, SQRT2))
    if west and south and not blocked[index + width - 1]:
        steps.append((index + width - 1, SQRT2))
    if west and north and not blocked[index - width - 1]:
        steps.append((index - width - 1, SQRT2))
    return steps


def distance_field(starts: Iterable[int], blocked: bytes | bytearray, width: int, height: int) -> list[float]:
    """Walking distance from the nearest of the *starts* (flat indices) to every tile; infinity where
    no walk leads."""
    distances = [math.inf] * (width * height)
    frontier = []
    for index in sorted(starts):
        distances[index] = 0.0
        frontier.append((0.0, index))
    heapq.heapify(frontier)
    push, pop = heapq.heappush, heapq.heappop
    while frontier:
        cost, current = pop(frontier)
        if cost > distances[current]:
            continue
        for nxt, step in grid_steps(current, blocked, width, height):
            total = cost + step
            if total < distances[nxt]:
                distances[nxt] = total
                push(frontier, (total, nxt))
    return distances


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
    origin = start[1] * width + start[0]
    penalties = {y * width + x: penalty for (x, y), penalty in goals.items()}
    costs = [math.inf] * (width * height)
    costs[origin] = 0.0
    parents = [-1] * (width * height)
    frontier = [(0.0, origin)]
    best, best_cost = -1, math.inf
    push, pop = heapq.heappush, heapq.heappop
    while frontier:
        cost, current = pop(frontier)
        if cost >= best_cost:
            break
        if cost != costs[current]:
            continue
        penalty = penalties.get(current)
        if penalty is not None and cost + penalty < best_cost:
            best, best_cost = current, cost + penalty
        for nxt, step in grid_steps(current, blocked, width, height):
            total = cost + step
            if total < costs[nxt]:
                costs[nxt] = total
                parents[nxt] = current
                push(frontier, (total, nxt))
    if best < 0:
        return None
    route = []
    while best != origin:
        route.append(divmod(best, width)[::-1])
        best = parents[best]
    route.reverse()
    return route
