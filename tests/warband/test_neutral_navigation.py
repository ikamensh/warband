"""Exact fuzz geometries keep encounter avoidance from trapping ordinary marches."""

import random

import pytest

from warband.sim import camps
from warband.sim.model import World, dist
from warband.sim.rules import BuildingType, Race, Terrain, UnitType


@pytest.mark.parametrize("visible_guards", [False, True], ids=["no-warning-control", "observed-guard-warning"])
def test_a_march_can_leave_an_unremembered_guards_warning_and_continue(visible_guards: bool) -> None:
    """Seed82: the broad warning around partially observed guards prematurely ended a far march near its start.

    This retains the captured terrain/positions, with only the two buildings needed to see both guards.
    Removing the warning is the control: the same footman can cross this forest without a neutral fight.
    """
    rows = (
        "ttggggggggggggtttttttttttttttt",
        "tggggggggggggggttttttttttttttt",
        "tgggggggggggggggtttttttttttttt",
        "gggggggggggggggggttggggggggttt",
        "gggggggggggggggggttwwwwwwwwwww",
        "gggggggggggggggggtttwwwwwwwwww",
        "ggggggggggggggggttttwwwwgggwww",
        "gggggggggggggggggtttttggggggww",
        "gggggggggggggggggtttttgggggggw",
        "gggggggggggggggggtttttgggggggw",
        "gggggggggggggggttttttttggggggw",
        "gggggggggggggggtttttttttttgggw",
        "gggggggggggggggttttrrtttttgggg",
        "ggggggggggggggtttttrrgggtggggg",
        "ggggggggggggggttttgggggggggggg",
        "ggggggggggggttttttgggggggggggg",
        "tggggggggggttttttggggggggggggg",
        "tttttgggggttttttgggggggggggggg",
        "tttttgggggttttgggggggggggggggg",
        "tttgwttgggttgggggggrwggggggttt",
        "tttgwwwttggggggggggwwwgggggttt",
        "tgtgwwwttggggggggggwwwgggggttt",
        "tgtggwwtttgggggggggwwwggggggtt",
        "tttggggggggggttggggwwgggrggggg",
    )
    tiles = {tile.value[0]: tile for tile in Terrain}
    world = World(30, 24, [[tiles[char] for char in row] for row in rows], 2,
                  races=[Race.ELF, Race.HUMAN], rng=random.Random(82), scripted=True, magic=True)
    world.place_building(0, BuildingType.TOWER, (8, 15))
    world.place_building(0, BuildingType.MAGE_TOWER, (7, 18))
    if visible_guards:
        camp = camps.place(world, (20, 15), [UnitType.SPIDER, UnitType.WOLF], 1500)
        # Fixture placement retains the two surviving guards' exact captured positions and home posts.
        camp.posts = [(18.375860616707566, 16.6386064438633), (20.330627244803253, 14.61803681260735)]
        for uid, post in zip(camp.guards, camp.posts):
            world.units[uid].x, world.units[uid].y = post
    else:
        world.place_building(world.neutral, BuildingType.LAIR, (20, 15))
    origin = (16.64495384175752, 8.059738212962422)
    footman = world.spawn_unit(0, UnitType.FOOTMAN, origin)
    world.update_vision()
    if visible_guards:
        assert all(world.is_visible(0, world.units[uid].tile) for uid in camp.guards)
        assert camp.lair not in world.worker_knowledge[0].buildings
    world.attack_move([footman.id], (29.5, 23.5))
    for _ in range(300):
        world.step()
    assert dist(origin, footman.pos) > 5.0, (footman.pos, footman.order)


@pytest.mark.parametrize("march", ["move", "attack_move"])
def test_a_queued_expedition_keeps_the_current_march_outside_the_camp(march: str) -> None:
    """Queueing a later camp attack must not opt the current ordinary march into that fight."""
    world = World(30, 24, [[Terrain.GRASS] * 30 for _ in range(24)], 2,
                  rng=random.Random(11), scripted=True)
    camp = camps.place(world, (13, 10), [UnitType.WOLF], 1200)
    archer = world.spawn_unit(0, UnitType.ARCHER, (3.5, 11.5))
    destination = (25.5, 11.5)
    world.reveal_all(0)
    if march == "move":
        world.move([archer.id], destination)
    else:
        world.attack_move([archer.id], destination)
    first_march = archer.order
    world.attack([archer.id], camp.guards[0], queue=True)

    for _ in range(800):
        world.step()
        if first_march not in archer.orders:
            break
        assert not camp.roused, "a later expedition must not expose the current march"
        assert not world.to_dict()["camps"][0]["credit"], "a later expedition must not trigger early combat"
    else:
        pytest.fail("the first march never reached its destination")
    assert dist(archer.pos, destination) < 1.0

    for _ in range(300):
        world.step()
        if world.to_dict()["camps"][0]["credit"]:
            break
    assert world.to_dict()["camps"][0]["credit"], "the queued explicit expedition must still fight afterward"


def test_a_manual_mining_order_uses_the_bypass_around_a_remembered_camp() -> None:
    """Choosing a safe mine beyond a camp is a work order; its worker must route around the whole watch."""
    world = World(34, 24, [[Terrain.GRASS] * 34 for _ in range(24)], 2,
                  rng=random.Random(11), scripted=True)
    camp = camps.place(world, (13, 10), [UnitType.WOLF], 1200)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (27, 10))
    worker = world.spawn_unit(0, UnitType.PEASANT, (3.5, 11.5))
    world.reveal_all(0)
    world.harvest([worker.id], mine.id)

    for _ in range(800):
        world.step()
        assert not camp.roused, "choosing a safe mine must not order an incidental camp fight"
        assert worker.id in world.units
        if worker.inside == mine.id:
            break
    else:
        pytest.fail("the manual miner never reached the safe mine")
