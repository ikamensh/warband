"""Audio feedback exercised through real simulation steps and the game scene."""

import random

import pytest

from saga2d import Game
from warband.model import Deposit, World
from warband.rules import BuildingType, Resource, Terrain, UnitType
from warband.scene import GameScene


@pytest.fixture
def battle(tmp_path):
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    game = Game("Battle audio", backend="mock", save_dir=tmp_path)
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    yield game, scene, world
    game.close()


def test_automatic_gold_deliveries_do_not_ring(battle):
    """Repeated harvesting should grow the treasury without notification jingles."""
    game, scene, world = battle
    worker = world.spawn_unit(0, UnitType.PEASANT, (7.5, 5.5))
    before = world.players[0].gold
    for _ in range(4):
        worker.carrying, worker.carry = Resource.GOLD, 100
        worker.orders.append(Deposit())
        game.tick(0.1)
    assert world.players[0].gold == before + 400
    assert not scene.recent_sounds
