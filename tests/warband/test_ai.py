"""The computer players: what a difficulty does with what it has."""

import random

from warband import mapgen
from warband.ai import DEFEND_RADIUS, Brain
from warband.model import AttackMove, Repair, dist
from warband.rules import SIM_DT, BuildingType, Difficulty, UnitType


def test_normal_and_hard_send_a_peasant_to_mend_a_damaged_building_but_easy_does_not() -> None:
    for difficulty, expected in ((Difficulty.NORMAL, True), (Difficulty.HARD, True), (Difficulty.EASY, False)):
        world = mapgen.generate(seed=5, players=2, human=None)
        brain = Brain(0, difficulty)
        hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
        hall.hp = hall.max_hp // 3
        rng = random.Random(1)
        for _ in range(int(8 / SIM_DT)):
            brain.think(world, rng)
            world.step()
        repairing = any(isinstance(u.order, Repair) for u in world.player_units(0)) or hall.hp > hall.max_hp // 3
        assert repairing == expected, difficulty
        if expected:
            assert any("repair town_hall" in what for _, what in brain.log)


def _siege_setup(enemy_type, enemy_count):
    """Eight own footmen marching on the enemy hall, with an enemy raid at an own farm."""
    world = mapgen.generate(seed=5, players=2, human=None)
    brain = Brain(0, Difficulty.NORMAL)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    farm = None
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            pos = (hall.x + dx, hall.y + dy)
            if world.can_place(BuildingType.FARM, pos, 0) is None:
                farm = world.place_building(0, BuildingType.FARM, pos)
                break
        if farm is not None:
            break
    assert farm is not None
    target = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    footmen = [world.spawn_unit(0, UnitType.FOOTMAN, (hall.center[0] + i, hall.center[1] + 1)) for i in range(8)]
    world.attack_move([u.id for u in footmen], target)
    brain.attacking = True
    fx, fy = farm.center
    enemies = [world.spawn_unit(1, enemy_type, (fx + 2, fy + i * 0.7)) for i in range(enemy_count)]
    world.update_vision()
    return world, brain, footmen, target, enemies


def _defend_lines(brain):
    return [what for _, what in brain.log if "defend with" in what]


def test_a_lone_scout_draws_only_a_couple_of_defenders_and_the_attack_goes_on() -> None:
    world, brain, footmen, target, enemies = _siege_setup(UnitType.SCOUT, 1)
    scout = enemies[0].pos
    brain.think(world, random.Random(1))
    defending = [u for u in footmen if Brain._aimed_at(world, u, scout)]
    holding = [u for u in footmen
               if isinstance(u.order, AttackMove) and dist(u.order.target, target) < 1.0]
    assert len(defending) <= 3
    assert len(holding) >= 5
    assert brain.attacking is True
    assert len(_defend_lines(brain)) == 1
    world.time += brain.profile.think_every + 0.1
    brain.think(world, random.Random(2))
    assert len(_defend_lines(brain)) == 1


def test_a_serious_raid_recalls_the_whole_army_and_cancels_the_attack() -> None:
    world, brain, footmen, _target, _enemies = _siege_setup(UnitType.FOOTMAN, 6)
    brain.think(world, random.Random(1))
    threat = brain._threat(world)
    assert threat is not None
    assert all(Brain._aimed_at(world, u, threat) for u in footmen)
    assert brain.attacking is False
