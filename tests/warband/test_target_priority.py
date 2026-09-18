"""Whom a unit fights on its own: fighters before bystanders, anything alive before buildings."""
import random

from warband.model import Attack, World
from warband.rules import BuildingType, Terrain, UnitType


def battlefield():
    return World(20, 16, [[Terrain.GRASS] * 20 for _ in range(16)], 2, rng=random.Random(5))


def test_an_idle_soldier_fights_the_enemy_fighter_rather_than_the_nearer_peasant():
    world = battlefield()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 7.5))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (8.5, 7.5))
    fighter = world.spawn_unit(1, UnitType.FOOTMAN, (5.5, 11.5))
    world.hold([peasant.id, fighter.id])
    world.update_vision()
    for _ in range(10):
        world.step()
    assert isinstance(ours.order, Attack) and ours.order.auto and ours.order.target == fighter.id


def test_a_soldier_busy_on_a_building_turns_on_a_fighter_that_comes_into_sight():
    world = battlefield()
    world.place_building(1, BuildingType.TOWN_HALL, (16, 0))  # keeps the enemy in the match, out of sight
    farm = world.place_building(1, BuildingType.FARM, (10, 10))
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 10.5))
    world.update_vision()
    for _ in range(40):
        world.step()
    assert isinstance(ours.order, Attack) and ours.order.auto and ours.order.target == farm.id
    archer = world.spawn_unit(1, UnitType.ARCHER, (9.5, 14.5))
    world.hold([archer.id])
    for _ in range(20):
        world.step()
    assert isinstance(ours.order, Attack) and ours.order.target == archer.id
    for _ in range(200):
        world.step()
    assert archer.id not in world.units


def test_a_soldier_busy_on_a_building_turns_on_a_shooter_beyond_its_own_sight():
    """The catapult outranges the knight's sight, so only the blow itself can give it away."""
    world = battlefield()
    world.place_building(1, BuildingType.TOWN_HALL, (16, 0))
    farm = world.place_building(1, BuildingType.FARM, (10, 10))
    ours = world.spawn_unit(0, UnitType.KNIGHT, (7.5, 10.5))
    world.reveal_all(0)
    for _ in range(40):
        world.step()
    assert isinstance(ours.order, Attack) and ours.order.auto and ours.order.target == farm.id
    catapult = world.spawn_unit(1, UnitType.CATAPULT, (16.0, 10.5))
    world.attack([catapult.id], ours.id)
    for _ in range(80):  # the crew wheels round, cranks the arm and the stone flies
        world.step()
        if ours.hp < ours.max_hp:
            break
    assert ours.hp < ours.max_hp
    assert isinstance(ours.order, Attack) and ours.order.target == catapult.id
