"""Automatic archer spacing keeps firing useful and obeys player intent."""
import random

import pytest

from warband.model import Attack, Hold, World
from warband.rules import Terrain, UnitType


def battlefield():
    return World(20, 16, [[Terrain.GRASS] * 20 for _ in range(16)], 2, rng=random.Random(5))


@pytest.mark.parametrize("position, enemy_position", [
    ((.2, 7.5), (2.1, 7.5)), ((19.8, 7.5), (17.9, 7.5)),
    ((9.5, .2), (9.5, 2.1)), ((9.5, 15.8), (9.5, 13.9)),
])
def test_archer_retreat_stays_inside_every_map_edge(position, enemy_position):
    world = battlefield()
    archer = world.spawn_unit(0, UnitType.ARCHER, position)
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, enemy_position)
    world.hold([enemy.id])
    world.attack_move([archer.id], enemy.pos)
    world.update_vision()
    for _ in range(30):
        world.step()
        assert 0 <= archer.x < world.width and 0 <= archer.y < world.height
        assert world.passable(*archer.tile)
    assert enemy.hp < enemy.max_hp


def test_automatic_archer_fires_then_makes_space_during_recovery():
    """A ready archer shoots before retreating from visible melee pressure."""
    world = battlefield()
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 7.5))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (7.4, 7.5))
    world.hold([enemy.id])
    world.attack_move([archer.id], enemy.pos)
    world.update_vision()
    for _ in range(5):
        world.step()
    contact = archer.pos
    world.step()
    assert enemy.hp < enemy.max_hp
    assert archer.pos == contact
    for _ in range(12):
        world.step()
    assert archer.x < contact[0]
    assert isinstance(archer.order, Attack)
    assert archer.order.target == enemy.id


@pytest.mark.parametrize('command', ['attack', 'hold', 'move'])
def test_manual_archer_order_takes_priority_over_spacing(command):
    """Focus, Hold and movement commands keep the player's requested behavior."""
    from warband.model import Move

    world = battlefield()
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 7.5))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (7.4, 7.5))
    world.hold([enemy.id])
    if command == 'attack':
        world.attack([archer.id], enemy.id)
    elif command == 'hold':
        world.hold([archer.id])
    else:
        world.move([archer.id], (9., 5.5))
    world.update_vision()
    start = archer.pos
    for _ in range(10):
        world.step()
    if command == 'move':
        assert isinstance(archer.order, Move)
        assert archer.order.target == (9., 5.5)
        assert archer.x > start[0]
    else:
        assert archer.pos == start
        assert isinstance(archer.order, Attack if command == 'attack' else Hold)
        assert enemy.hp < enemy.max_hp


def test_archer_retreat_uses_a_clear_side_step_beside_a_wall():
    """Blocked ground behind an archer cannot be crossed to gain distance."""
    terrain = [[Terrain.GRASS] * 20 for _ in range(16)]
    terrain[7][4] = Terrain.WATER
    world = World(20, 16, terrain, 2, rng=random.Random(5))
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 7.5))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (7.4, 7.5))
    world.hold([enemy.id])
    world.attack_move([archer.id], enemy.pos)
    world.update_vision()
    for _ in range(35):
        world.step()
        assert world.passable(*archer.tile)
    assert archer.y != 7.5
    assert enemy.hp < enemy.max_hp


def test_unseen_melee_contact_does_not_change_archer_spacing():
    """A contact arriving between sight updates cannot influence retreat yet."""
    def battle(extra):
        world = battlefield()
        archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 7.5))
        target = world.spawn_unit(1, UnitType.ARCHER, (8., 7.5))
        world.hold([target.id])
        world.attack_move([archer.id], target.pos)
        world.update_vision()
        for _ in range(6):
            world.step()
        if extra:
            unseen = world.spawn_unit(1, UnitType.FOOTMAN, (5.5, 9.5))
            world.hold([unseen.id])
            world.visible[0][unseen.tile[1] * world.width + unseen.tile[0]] = 0
        world.step()
        return archer.pos, archer.cooldown, archer.order, target.hp

    assert battle(False) == battle(True)
