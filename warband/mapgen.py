"""Procedural maps: a base in each corner, a gold mine and a wood beside it,
lakes and forests in between, and every base reachable from every other.
"""

from __future__ import annotations

import heapq
import random
from collections import deque

from warband.model import Pos, World, tile_center
from warband.rules import EXPANSION_GOLD, BuildingType, Terrain, UnitType

SIZES: dict[str, tuple[int, int]] = {"Small": (40, 32), "Medium": (48, 40), "Large": (64, 48)}
_BASE_MARGIN = 7  # tiles from the map edge to the hall's top-left
_BASE_CLEARING = 7  # radius of open ground around the hall centre
_CORNERS = ((0, 0), (1, 1), (1, 0), (0, 1))  # player order: opposite corners first
_EXPANSION_MINES = {2: 2, 3: 2, 4: 3}


def generate(seed: int, width: int = 48, height: int = 40, players: int = 2, human: int | None = 0) -> World:
    if not 2 <= players <= 4:
        raise ValueError("2 to 4 players")
    rng = random.Random(seed)
    terrain = _terrain(rng, width, height)
    bases = [_base(width, height, corner) for corner in _CORNERS[:players]]
    for hall, mine, wood in bases:
        _clear(terrain, (hall[0] + 1, hall[1] + 1), _BASE_CLEARING)
        _clump(terrain, wood, 2.6, rng)
        for pos in _rect_tiles(mine, 3):
            terrain[pos[1]][pos[0]] = Terrain.GRASS
        for pos in _ring(mine, 3, 1):
            terrain[pos[1]][pos[0]] = Terrain.GRASS
    world = World(width, height, terrain, players, human=human, rng=random.Random(seed))
    for player, (hall, mine, _wood) in enumerate(bases):
        world.place_building(player, BuildingType.TOWN_HALL, hall)
        world.place_building(None, BuildingType.GOLD_MINE, mine)
        below = hall[1] + 3 if hall[1] < height // 2 else hall[1] - 1
        for i in range(3):
            world.spawn_unit(player, UnitType.PEASANT, tile_center((hall[0] + i, below)))
    _connect(world, [hall for hall, _m, _w in bases])
    _expansion_mines(world, rng, [hall for hall, _m, _w in bases])
    world.update_vision()
    return world


# -- Layout ----------------------------------------------------------------------


def _base(width: int, height: int, corner: tuple[int, int]) -> tuple[Pos, Pos, Pos]:
    """``(hall, mine, wood)`` top-left tiles for the base in *corner* (0 = left/top, 1 = right/bottom)."""
    cx, cy = corner

    def place(dx: int, dy: int, size: int) -> Pos:
        x = _BASE_MARGIN + dx if cx == 0 else width - _BASE_MARGIN - size - dx
        y = _BASE_MARGIN + dy if cy == 0 else height - _BASE_MARGIN - size - dy
        return (x, y)

    return place(0, 0, 3), place(-5, -4, 3), place(9, 1, 1)


def _rect_tiles(pos: Pos, size: int) -> list[Pos]:
    return [(pos[0] + dx, pos[1] + dy) for dy in range(size) for dx in range(size)]


def _ring(pos: Pos, size: int, gap: int) -> list[Pos]:
    return [(pos[0] + dx, pos[1] + dy) for dx in range(-gap, size + gap) for dy in range(-gap, size + gap)
            if not (0 <= dx < size and 0 <= dy < size)]


# -- Terrain ---------------------------------------------------------------------


def _noise(rng: random.Random, width: int, height: int, cell: int) -> list[list[float]]:
    """Bilinear value noise with control points every *cell* tiles."""
    cols, rows = width // cell + 2, height // cell + 2
    grid = [[rng.random() for _ in range(cols)] for _ in range(rows)]
    out = [[0.0] * width for _ in range(height)]
    for y in range(height):
        gy, fy = divmod(y, cell)
        ty = fy / cell
        for x in range(width):
            gx, fx = divmod(x, cell)
            tx = fx / cell
            a, b = grid[gy][gx], grid[gy][gx + 1]
            c, d = grid[gy + 1][gx], grid[gy + 1][gx + 1]
            out[y][x] = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
    return out


def _terrain(rng: random.Random, width: int, height: int) -> list[list[Terrain]]:
    trees = _noise(rng, width, height, 5)
    fine = _noise(rng, width, height, 2)
    water = _noise(rng, width, height, 9)
    rocks = _noise(rng, width, height, 3)
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            edge = min(x, y, width - 1 - x, height - 1 - y)
            t = trees[y][x] * 0.7 + fine[y][x] * 0.3
            if edge == 0 or t > 0.62 - (0.25 if edge < 3 else 0.0):
                terrain[y][x] = Terrain.TREES
            elif water[y][x] > 0.74 and edge > 3:
                terrain[y][x] = Terrain.WATER
            elif rocks[y][x] > 0.86 and fine[y][x] > 0.5:
                terrain[y][x] = Terrain.ROCK
    return terrain


def _clear(terrain: list[list[Terrain]], center: Pos, radius: int) -> None:
    for y in range(max(0, center[1] - radius), min(len(terrain), center[1] + radius + 1)):
        for x in range(max(0, center[0] - radius), min(len(terrain[0]), center[0] + radius + 1)):
            if (x - center[0]) ** 2 + (y - center[1]) ** 2 <= radius * radius and min(x, y, len(terrain[0]) - 1 - x, len(terrain) - 1 - y) > 0:
                terrain[y][x] = Terrain.GRASS


def _clump(terrain: list[list[Terrain]], center: Pos, radius: float, rng: random.Random) -> None:
    r = int(radius) + 1
    for y in range(center[1] - r, center[1] + r + 1):
        for x in range(center[0] - r, center[0] + r + 1):
            if 0 < x < len(terrain[0]) - 1 and 0 < y < len(terrain) - 1:
                if (x - center[0]) ** 2 + (y - center[1]) ** 2 <= (radius + rng.uniform(-0.6, 0.6)) ** 2:
                    terrain[y][x] = Terrain.TREES


# -- Connectivity ----------------------------------------------------------------


_CARVE_COST = {Terrain.GRASS: 1.0, Terrain.TREES: 4.0, Terrain.ROCK: 6.0, Terrain.WATER: 12.0}


def _reachable(world: World, start: Pos) -> set[Pos]:
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in seen and world.passable(nx, ny):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


def _front_door(world: World, hall: Pos) -> Pos:
    spot = world.free_tile_near((hall[0], hall[1], 3, 3))
    assert spot is not None
    return spot


def _connect(world: World, halls: list[Pos]) -> None:
    """Carve grass corridors until every base can walk to the first one."""
    doors = [_front_door(world, hall) for hall in halls]
    for door in doors[1:]:
        if door not in _reachable(world, doors[0]):
            _carve(world, _cheapest_route(world, doors[0], door))


def _cheapest_route(world: World, start: Pos, goal: Pos) -> list[Pos]:
    """Dijkstra where trees, rock and water are merely expensive; buildings stay impassable."""
    best: dict[Pos, float] = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    frontier = [(0.0, start)]
    while frontier:
        cost, current = heapq.heappop(frontier)
        if current == goal:
            break
        if cost > best.get(current, float("inf")):
            continue
        x, y = current
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not world.in_bounds(nxt) or world.building_at(nxt) is not None:
                continue
            edge = min(nxt[0], nxt[1], world.width - 1 - nxt[0], world.height - 1 - nxt[1])
            if edge == 0:
                continue
            new_cost = cost + _CARVE_COST[world.terrain_at(nxt)]
            if new_cost < best.get(nxt, float("inf")):
                best[nxt] = new_cost
                parent[nxt] = current
                heapq.heappush(frontier, (new_cost, nxt))
    route = [goal]
    while route[-1] != start:
        route.append(parent[route[-1]])
    return route


def _expansion_mines(world: World, rng: random.Random, halls: list[Pos]) -> None:
    """Neutral mines away from every base, on the openest ground available; a corridor is carved if need be."""
    door = _front_door(world, halls[0])
    wanted = _EXPANSION_MINES[len(halls)]
    spacing = 13 if len(halls) == 2 else 11
    candidates = [(x, y) for y in range(3, world.height - 6) for x in range(3, world.width - 6)
                  if all(max(abs(x - hx), abs(y - hy)) >= spacing for hx, hy in halls)]
    rng.shuffle(candidates)

    def roughness(pos: Pos) -> int:
        return sum(world.terrain_at(t) is not Terrain.GRASS for t in _rect_tiles(pos, 3) + _ring(pos, 3, 2))

    placed: list[Pos] = []
    for pos in sorted(candidates[:300], key=roughness):
        if len(placed) >= wanted:
            break
        tiles = _rect_tiles(pos, 3) + _ring(pos, 3, 2)
        if any(world.building_at(t) is not None for t in tiles):
            continue
        if any(max(abs(pos[0] - px), abs(pos[1] - py)) < 10 for px, py in placed):
            continue
        for x, y in tiles:
            world.terrain[y][x] = Terrain.GRASS
            world._blocked[y * world.width + x] = 0
        mine = world.place_building(None, BuildingType.GOLD_MINE, pos)
        mine.gold = EXPANSION_GOLD
        placed.append(pos)
        mine_door = world.free_tile_near(mine.rect)
        assert mine_door is not None
        if mine_door not in _reachable(world, door):
            _carve(world, _cheapest_route(world, door, mine_door))


def _carve(world: World, route: list[Pos]) -> None:
    for x, y in route:
        for nx, ny in ((x, y), (x + 1, y), (x, y + 1)):
            if world.in_bounds((nx, ny)) and world.building_at((nx, ny)) is None and world.terrain_at((nx, ny)) is not Terrain.GRASS:
                world.terrain[ny][nx] = Terrain.GRASS
                world._blocked[ny * world.width + nx] = 0
