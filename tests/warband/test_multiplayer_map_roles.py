"""Neutral objectives remain playable on the smaller cells multiplayer maps use."""

import pytest

from warband.sim import camps, mapgen, path
from warband.sim.model import dist
from warband.sim.rules import CAMP_ENCOUNTERS, PLAYABLE_UNITS, UNITS, BuildingType, Layout, Terrain


def test_three_seat_medium_forest_has_an_expansion_to_clear() -> None:
    """Seed 1 previously placed its contested mines where no mirrored guard den could fit."""
    world = mapgen.generate(1, *mapgen.dimensions("Medium", 3), 3, layout=Layout.FOREST)
    guards = [camp for camp in world.camps if CAMP_ENCOUNTERS[camp.encounter].role == "expansion"]
    assert len(guards) == world.seats


def test_forest_road_offers_a_local_shortcut_to_clear() -> None:
    """Seed 1 has an optional road crossing, diluted by its full hall-to-hall march in the old proof."""
    world = mapgen.generate(1, *mapgen.dimensions("Medium", 2), 2, layout=Layout.FOREST)
    chokes = [camp for camp in world.camps if CAMP_ENCOUNTERS[camp.encounter].role == "choke"]
    assert len(chokes) == world.seats
    bare = mapgen.generate(1, *mapgen.dimensions("Medium", 2), 2, layout=Layout.FOREST, wilds=False)
    grid = bytearray(0 if bare.passable(x, y) else 1
                     for y in range(bare.height) for x in range(bare.width))
    halls = [building for building in bare.buildings.values() if building.type is BuildingType.TOWN_HALL]
    doors = [bare.free_tile_near(hall.rect) for hall in halls]
    assert all(door is not None for door in doors)
    budget = bare.width * bare.height * 4
    road = path.find_path_grid(doors[0], doors[1], grid, bare.width, bare.height, max_expansions=budget)
    # These are the real road's entry/exit around seed 1's first sentry, outside its padded watch.
    entry, exit_ = (21, 9), (29, 21)
    assert entry in road and exit_ in road and road.index(entry) < road.index(exit_)
    # The crossing is a physical neck between tree banks, not an open-field danger-circle detour.
    for tile, left, right in (((22, 12), (20, 12), (24, 12)), ((22, 13), (20, 14), (24, 12))):
        assert tile in road
        assert all(bare.terrain_at(bank) in (Terrain.TREES, Terrain.WATER, Terrain.ROCK) for bank in (left, right))
    chosen = min(chokes, key=lambda camp: dist(camps.centre(world, camp), (23.5, 16.5)))
    centres = [point for camp in world.camps for point in (camps.centre(world, camp), camps.watch_of(world, camp))]
    margin = max([1.0] + [UNITS[kind].radius + .5 for kind in PLAYABLE_UNITS if not UNITS[kind].flying])
    closed = camps.navigation(world, 0, grid, set(), margin, lairs=centres)
    rest = [point for camp in world.camps if camp is not chosen
            for point in (camps.centre(world, camp), camps.watch_of(world, camp))]
    opened = camps.navigation(world, 0, grid, set(), margin, lairs=rest)
    assert all(not closed[y * bare.width + x] for x, y in (entry, exit_))
    around = path.find_path_grid(entry, exit_, closed, bare.width, bare.height, max_expansions=budget)
    through = path.find_path_grid(entry, exit_, opened, bare.width, bare.height, max_expansions=budget)
    assert around and through, "the guarded crossing needs a real bypass and a real cleared route"
    around_cost = sum(path.octile(a, b) for a, b in zip([entry] + around, around))
    through_cost = sum(path.octile(a, b) for a, b in zip([entry] + through, through))
    assert around_cost >= 1.15 * through_cost


@pytest.mark.slow
def test_sixteen_seat_giant_forest_has_an_expansion_to_clear() -> None:
    """Slow: seed 1 needs a complete sixteen-seat map; its cramped thirds previously had no guards."""
    world = mapgen.generate(1, *mapgen.dimensions("Giant", 16), 16, layout=Layout.FOREST)
    guards = [camp for camp in world.camps if CAMP_ENCOUNTERS[camp.encounter].role == "expansion"]
    assert len(guards) == world.seats
