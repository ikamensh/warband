"""Terrain edits keep both kinds of walker and their reachability in agreement."""

from warband.sim.model import World
from warband.sim.rules import Race, Terrain, UnitType


def test_carving_and_flooding_update_both_walkers_after_routes_have_been_queried() -> None:
    """Map generation and scripted terrain edits must invalidate connectivity for every walking kind."""
    terrain = [[Terrain.GRASS] * 18 for _ in range(12)]
    for row in terrain:
        row[9] = Terrain.TREES
    world = World(18, 12, terrain, 2, races=[Race.ELF, Race.HUMAN])
    walker = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 6.5))
    treant = world.spawn_unit(0, UnitType.TREANT, (7.5, 5.5))
    start, end = (7, 6), (11, 6)
    ordinary = world.navigation.regions()
    forest = world.navigation.regions(forest=True)
    assert ordinary.label(start) != ordinary.label(end)
    assert forest.label(start) == forest.label(end)

    world.navigation.set_terrain((9, 6), Terrain.GRASS)
    assert world.terrain_at((9, 6)) is Terrain.GRASS
    assert world.passable(9, 6)
    ordinary = world.navigation.regions()
    assert ordinary.label(start) == ordinary.label(end)

    for y in range(world.height):
        world.navigation.set_terrain((9, y), Terrain.WATER)
    for unit in (walker, treant):
        assert world.ground_of(unit)[6 * world.width + 9]
        regions = world.navigation.regions(forest=unit.forest)
        assert regions.label(start) != regions.label(end)


def test_a_rejected_map_edit_restores_terrain_and_both_kinds_of_connectivity() -> None:
    """Trying a camp location must not leave a shortcut behind when that candidate is rejected."""
    terrain = [[Terrain.GRASS] * 12 for _ in range(10)]
    for row in terrain:
        row[6] = Terrain.ROCK
    world = World(12, 10, terrain, 2)
    before = world.to_dict()
    checkpoint = world.navigation.checkpoint()
    world.navigation.set_terrain((6, 4), Terrain.GRASS)
    for forest in (False, True):
        regions = world.navigation.regions(forest=forest)
        assert regions.label((4, 4)) == regions.label((8, 4))

    world.navigation.restore(checkpoint)
    assert world.to_dict() == before
    for forest in (False, True):
        regions = world.navigation.regions(forest=forest)
        assert regions.label((4, 4)) != regions.label((8, 4))
