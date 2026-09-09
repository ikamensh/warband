"""The computer players: what a difficulty does with what it has."""

import random

from warband import mapgen
from warband.ai import DEFEND_RADIUS, PROFILES, Brain
from warband.model import AttackMove, Harvest, Repair, dist
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


def _farm_headroom(world, count=3) -> None:
    """Completed farms near player 0's first hall so the supply cap does not mask the workforce target."""
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    placed = 0
    for radius in range(4, 13):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius or placed >= count:
                    continue
                pos = (hall.x + dx, hall.y + dy)
                if world.can_place(BuildingType.FARM, pos, 0) is None:
                    world.place_building(0, BuildingType.FARM, pos)
                    placed += 1
        if placed >= count:
            break
    assert placed == count
    world.update_vision()


def _expansion_world():
    """Player 0 with a completed hall beside a far neutral mine, plus farm headroom and gold to spare."""
    world = mapgen.generate(seed=5, players=2, human=None)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    home = [b.center for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    candidates = [m for m in world.mines() if all(dist(m.center, h) > 10 for h in home)]
    far = max(candidates or world.mines(), key=lambda m: dist(m.center, hall.center))
    pos = None
    for dx, dy in ((-5, 0), (4, 0), (0, -5), (0, 4)):
        candidate = (far.x + dx, far.y + dy)
        if 0 <= candidate[0] <= world.width - 3 and 0 <= candidate[1] <= world.height - 3:
            pos = candidate
            break
    assert pos is not None
    world.place_building(0, BuildingType.TOWN_HALL, pos)
    _farm_headroom(world)
    world.update_vision()
    world.players[0].gold = 20000
    world.players[0].lumber = 5000
    return world, far


def _run_brain(world, seconds=90):
    brain = Brain(0, Difficulty.NORMAL)
    rng = random.Random(1)
    for _ in range(int(seconds / SIM_DT)):
        brain.think(world, rng)
        world.step()
    return brain


def _harvests_far(unit, far) -> bool:
    if unit.inside == far.id:
        return True
    return any(isinstance(order, Harvest) and order.target == far.id for order in unit.orders)


def test_a_second_hall_grows_the_workforce_onto_its_own_mine() -> None:
    world, far = _expansion_world()
    brain = _run_brain(world)
    peasants = [u for u in world.player_units(0) if u.is_worker]
    assert len(peasants) > PROFILES[Difficulty.NORMAL].peasants
    assert any(_harvests_far(unit, far) for unit in peasants)
    assert any("workforce target" in what for _, what in brain.log)


def test_one_hall_holds_the_workforce_at_the_profile_value() -> None:
    world = mapgen.generate(seed=5, players=2, human=None)
    _farm_headroom(world)
    world.players[0].gold = 20000
    world.players[0].lumber = 5000
    _run_brain(world)
    peasants = [u for u in world.player_units(0) if u.is_worker]
    assert len(peasants) == PROFILES[Difficulty.NORMAL].peasants
