"""The invariants ``tools/fuzz.py`` holds a world to catch what they name, and say where.

Its whole-map checks are bitwise (a grid compared as bytes, fog as bitsets) so that they cost next to nothing beside
a compiled step; this holds them to the answers of the tile-by-tile loops they replaced."""
import random
import sys
from pathlib import Path

import pytest

from warband.sim.model import World
from warband.sim.rules import BuildingType, Terrain

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from fuzz import check_world  # noqa: E402  (imported as a library: the source simulation, as every test runs)


def sound_world() -> World:
    terrain = [[Terrain.GRASS] * 24 for _ in range(18)]
    for y in range(4, 9):
        terrain[y][15] = Terrain.TREES
    world = World(24, 18, terrain, 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (3, 3))
    world.place_building(1, BuildingType.TOWN_HALL, (18, 12))
    world.update_vision()
    return world


def test_a_sound_world_passes() -> None:
    check_world(sound_world())


@pytest.mark.parametrize("tile, flag", [((10, 10), 1), ((15, 6), 0), ((4, 4), 0)], ids=["grass", "trees", "a hall"])
def test_a_blocked_grid_out_of_step_with_the_map_is_named_at_its_tile(tile, flag) -> None:
    world = sound_world()
    x, y = tile
    world._blocked[y * world.width + x] = flag  # a private write: the corruption the check exists to find
    with pytest.raises(AssertionError) as caught:
        check_world(world)
    assert caught.value.args[0] in (("blocked grid mismatch", tile), ("building tile not blocked", world.building_at(tile)))


def test_a_tile_seen_but_never_explored_is_caught() -> None:
    world = sound_world()
    i = world.explored[1].index(0)
    world.visible[1][i] = 1  # a private write, as above
    with pytest.raises(AssertionError, match="visible but unexplored"):
        check_world(world)
