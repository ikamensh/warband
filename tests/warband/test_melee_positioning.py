"""Melee approach behavior through real orders and fixed simulation steps."""

import pytest

from warband.model import Attack, World
from warband.rules import BuildingType, Terrain, UnitType


def stationary_worker(world, player, point):
    worker = world.spawn_unit(player, UnitType.PEASANT, point)
    world.hold([worker.id])
    return worker


@pytest.mark.parametrize("unit_type", [UnitType.PEASANT, UnitType.FOOTMAN, UnitType.SCOUT, UnitType.KNIGHT])
def test_melee_recovers_contact_when_an_ally_pushes_it_away_from_a_wall(unit_type):
    """A tiny friendly shove must not strand an attacker just outside weapon reach."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    world.rng.seed(1)
    target = world.place_building(1, BuildingType.TOWN_HALL, (14, 10))
    stationary_worker(world, 0, (13.6, 10.5))
    soldier = world.spawn_unit(0, unit_type, (10, 10.5))
    world.attack([soldier.id], target.id)
    hits = 0
    for _ in range(160):
        world.step()
        hits += sum(event.kind == "hit" and event.entity == soldier.id and event.other == target.id
                    for event in world.take_events())
        assert world.passable(*soldier.tile)
    assert hits >= 5, f"The soldier landed only {hits} hits in eight seconds"
    assert isinstance(soldier.order, Attack) and soldier.order.target == target.id


def test_melee_keeps_the_explicit_target_when_an_enemy_worker_is_closer():
    """Better positioning must not replace the player's focus-fire order with an easier victim."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    world.rng.seed(1)
    target = world.place_building(1, BuildingType.TOWN_HALL, (14, 10))
    worker = stationary_worker(world, 1, (11.5, 10.5))
    stationary_worker(world, 0, (13.6, 10.5))
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (10, 10.5))
    world.attack([soldier.id], target.id)
    victims = []
    for _ in range(160):
        world.step()
        victims.extend(event.other for event in world.take_events()
                       if event.kind == "hit" and event.entity == soldier.id)
    assert len(victims) >= 5 and set(victims) == {target.id}
    assert worker.hp == worker.max_hp


def test_melee_reaches_the_wall_contact_point_by_going_around_blocked_terrain():
    """A closer contact destination still follows the only legal path around an obstacle."""
    terrain = [[Terrain.GRASS] * 24 for _ in range(20)]
    for y in range(13):
        terrain[y][12] = Terrain.WATER
    world = World(24, 20, terrain, 2)
    world.rng.seed(1)
    target = world.place_building(1, BuildingType.TOWN_HALL, (14, 10))
    stationary_worker(world, 0, (13.6, 10.5))
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (10, 10.5))
    world.attack([soldier.id], target.id)
    hits = 0
    previous = soldier.pos
    for _ in range(200):
        world.step()
        assert world.passable(*soldier.tile)
        if previous[0] < 12 <= soldier.x:
            assert soldier.y >= 13
        previous = soldier.pos
        hits += sum(event.kind == "hit" and event.entity == soldier.id and event.other == target.id
                    for event in world.take_events())
    assert hits >= 3


def test_attack_move_fights_an_adjacent_defender_instead_of_chasing_past_it():
    """An automatically acquired opponent must not make a ready soldier ignore contact."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    world.rng.seed(3)
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5))
    distant = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 8.5))
    world.hold([distant.id])
    world.attack_move([soldier.id], (18, 8.5))
    world.update_vision()
    for _ in range(5):
        world.step()
    assert isinstance(soldier.order, Attack) and soldier.order.target == distant.id
    defender = world.spawn_unit(1, UnitType.FOOTMAN, (soldier.x + 1, soldier.y))
    world.hold([defender.id])
    world.update_vision()
    world.take_events()
    world.step()
    hits = [event for event in world.take_events() if event.kind == "hit" and event.entity == soldier.id]
    assert len(hits) == 1 and hits[0].other == defender.id


def test_an_acquired_opponent_is_not_abandoned_during_attack_recovery():
    """A nearby substitute is considered when ready to strike, preserving focus during recovery."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5))
    target = world.spawn_unit(1, UnitType.FOOTMAN, (6.5, 8.5))
    world.hold([target.id])
    world.attack_move([soldier.id], (15, 8.5))
    world.update_vision()
    for _ in range(6):
        world.step()
    assert soldier.cooldown > 0
    substitute = world.spawn_unit(1, UnitType.FOOTMAN, (soldier.x, soldier.y + .7))
    world.hold([substitute.id])
    world.move([target.id], (15, 8.5))
    for _ in range(8):
        world.step()
    assert soldier.cooldown > 0
    assert isinstance(soldier.order, Attack) and soldier.order.target == target.id


def test_attack_move_finishes_a_wounded_visible_opponent_in_reach():
    """A ready soldier finishes a reachable wounded defender instead of spreading its damage."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5))
    healthy = world.spawn_unit(1, UnitType.FOOTMAN, (6.3, 8.5))
    wounded = world.spawn_unit(1, UnitType.FOOTMAN, (5.5, 9.6))
    wounded.hp = 1
    world.hold([healthy.id, wounded.id])
    world.attack_move([soldier.id], (15, 8.5))
    world.update_vision()
    assert world.is_visible(soldier.player, wounded.tile)
    hits = []
    for _ in range(6):
        world.step()
        hits.extend(event for event in world.take_events() if event.kind == "hit" and event.entity == soldier.id)
    assert len(hits) == 1 and hits[0].other == wounded.id
    assert wounded.id not in world.units and healthy.hp == healthy.max_hp


def test_auto_acquisition_does_not_find_a_unit_on_an_unseen_boundary_tile():
    """A unit's body entering acquisition radius does not reveal its fog-covered tile."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, (5.95, 5.95))
    hidden = stationary_worker(world, 1, (11.05, 5.95))
    world.update_vision()
    assert not world.is_visible(0, hidden.tile)
    for _ in range(5):
        world.step()
    assert soldier.order is None


def test_an_attack_on_a_mining_unit_ends_even_when_the_attacker_shares_its_position():
    """Entering a mine removes a worker as a combat target before contact geometry is used."""
    world = World(24, 20, [[Terrain.GRASS] * 24 for _ in range(20)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (9, 8))
    worker = world.spawn_unit(1, UnitType.PEASANT, (8.5, 8.5))
    world.harvest([worker.id], mine.id)
    world.step()
    assert worker.hidden
    soldier = world.spawn_unit(0, UnitType.FOOTMAN, worker.pos)
    world.attack([soldier.id], worker.id)
    world.step()
    assert soldier.order is None
    assert worker.hp == worker.max_hp
