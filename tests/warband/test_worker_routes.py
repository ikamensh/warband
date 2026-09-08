"""Headless harvesting routes must reach a useful resource or depot, even in groups."""
import random
import pytest
from warband.model import World
from warband.rules import BuildingType, SIM_DT, Terrain, UnitType


@pytest.mark.parametrize('count', [1, 8])
def test_workers_deliver_to_a_reachable_hall_instead_of_a_nearer_isolated_one(count):
    """The closest hall lies across a sealed wall; workers must use the farther accessible hall."""
    terrain = [[Terrain.GRASS] * 32 for _ in range(20)]
    for y in range(20):
        terrain[y][10] = Terrain.ROCK
    world = World(32, 20, terrain, 2, rng=random.Random(17))
    world.place_building(0, BuildingType.TOWN_HALL, (6, 8))
    world.place_building(0, BuildingType.TOWN_HALL, (22, 8))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (12, 8))
    workers = [world.spawn_unit(0, UnitType.PEASANT, (15.5 + i % 4 * .75, 12.5 + i // 4)) for i in range(count)]
    world.harvest([u.id for u in workers], mine.id)
    initial = world.players[0].gold
    for _ in range(600):
        world.step()
    assert world.players[0].gold - initial >= count * 100


def test_a_woodcutting_convoy_keeps_working_around_a_wall_and_buildings():
    """All workers should contribute instead of losing their orders at a crowded tree."""
    terrain = [[Terrain.GRASS] * 36 for _ in range(24)]
    for y in range(18):
        terrain[y][16] = Terrain.ROCK
    for y in range(6, 16):
        for x in range(24, 29):
            terrain[y][x] = Terrain.TREES
    world = World(36, 24, terrain, 2, rng=random.Random(7))
    world.place_building(0, BuildingType.TOWN_HALL, (3, 8))
    world.place_building(1, BuildingType.TOWN_HALL, (31, 19))
    workers = [world.spawn_unit(0, UnitType.PEASANT, (8 + i % 4 * .8, 8 + i // 4 * .8)) for i in range(12)]
    world.reveal_all(0)  # the route was scouted; current vision still recedes normally
    world.harvest([u.id for u in workers], (24, 10))
    contributors = set()
    initial = world.players[0].lumber
    for _ in range(round(60 / SIM_DT)):
        world.step()
        for unit in workers:
            assert unit.hidden or world.passable(*unit.tile)
        contributors.update(event.entity for event in world.take_events() if event.kind == "deposit")
    assert len(contributors) == len(workers)
    assert world.players[0].lumber - initial >= 1200


def test_a_worker_closes_the_last_small_gap_to_a_tree_before_stopping():
    """A valid corner waypoint must reach chopping range, even inside movement's arrival tolerance."""
    terrain = [[Terrain.GRASS] * 24 for _ in range(20)]
    terrain[10][12] = Terrain.TREES
    world = World(24, 20, terrain, 2)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 14))
    world.place_building(1, BuildingType.TOWN_HALL, (19, 15))
    worker = world.spawn_unit(0, UnitType.PEASANT, (13.5065, 11.5579))
    world.update_vision()
    world.harvest([worker.id], (12, 10))
    initial = world.players[0].lumber
    for _ in range(round(15 / SIM_DT)):
        world.step()
    assert world.players[0].lumber - initial >= 100
