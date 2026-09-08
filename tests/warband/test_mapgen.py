"""Generated maps: bases in corners, mines and woods beside them, everything reachable."""

from collections import deque

import pytest

from warband import mapgen
from warband.model import World
from warband.rules import BuildingType, MapTheme, Terrain, UnitType


def reachable(world: World, start) -> set:
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in seen and world.passable(*n):
                seen.add(n)
                queue.append(n)
    return seen


@pytest.mark.parametrize("seed", range(1, 9))
@pytest.mark.parametrize("players", (2, 4))
def test_every_base_has_a_hall_a_mine_a_wood_and_a_way_to_the_others(seed: int, players: int) -> None:
    world = mapgen.generate(seed=seed, players=players)
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    assert len(halls) == players and {h.player for h in halls} == set(range(players))
    doors = []
    for hall in halls:
        peasants = [u for u in world.units.values() if u.player == hall.player and u.type is UnitType.PEASANT]
        assert len(peasants) == 3 and all(world.passable(*p.tile) for p in peasants)
        assert any(abs(m.center[0] - hall.center[0]) < 9 and abs(m.center[1] - hall.center[1]) < 9 for m in world.mines())
        assert world.nearest_tree(hall.center, 12) is not None
        door = world.free_tile_near(hall.rect)
        assert door is not None
        doors.append(door)
        assert world.is_visible(hall.player, hall.pos)
    region = reachable(world, doors[0])
    assert all(door in region for door in doors)
    for mine in world.mines():
        assert world.free_tile_near(mine.rect) in region
    assert len(world.mines()) >= players + 1


def test_map_edges_are_forest_and_sizes_are_respected() -> None:
    world = mapgen.generate(seed=3, width=40, height=32)
    assert world.width == 40 and world.height == 32
    assert all(world.terrain_at((x, 0)) is Terrain.TREES and world.terrain_at((x, 31)) is Terrain.TREES for x in range(40))
    assert all(world.terrain_at((0, y)) is Terrain.TREES and world.terrain_at((39, y)) is Terrain.TREES for y in range(32))
    kinds = {t for row in world.terrain for t in row}
    assert Terrain.WATER in kinds and Terrain.TREES in kinds and Terrain.GRASS in kinds


def test_the_same_seed_makes_the_same_map() -> None:
    assert mapgen.generate(seed=11).to_dict() == mapgen.generate(seed=11).to_dict()


@pytest.mark.parametrize("seed", (3, 7, 11))
@pytest.mark.parametrize("theme", list(MapTheme))
def test_interior_has_meadow_forest_water_and_rock_regions(seed: int, theme: MapTheme) -> None:
    """Exploring beyond the bases finds open meadow and substantial connected terrain patches."""
    world = mapgen.generate(seed=seed, theme=theme)
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    interior = {(x, y) for y in range(3, world.height - 3) for x in range(3, world.width - 3)
                if all(max(abs(x - h.center[0]), abs(y - h.center[1])) >= 8 for h in halls)}

    for kind, minimum in ((Terrain.TREES, 20), (Terrain.WATER, 12), (Terrain.ROCK, 8)):
        remaining = {p for p in interior if world.terrain_at(p) is kind}
        largest = 0
        while remaining:
            start = min(remaining)
            remaining.remove(start)
            region, queue = {start}, deque([start])
            while queue:
                x, y = queue.popleft()
                for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if p in remaining:
                        remaining.remove(p)
                        region.add(p)
                        queue.append(p)
            largest = max(largest, len(region))
        assert largest >= minimum, (seed, kind, largest)

    assert any(all((x + dx, y + dy) in interior and world.passable(x + dx, y + dy)
                   for dy in range(6) for dx in range(6)) for x, y in interior), seed
