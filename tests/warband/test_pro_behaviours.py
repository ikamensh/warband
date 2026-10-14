"""The search's newer behaviours: softest-target attacks, punishing an absent army, the siege answer.

Each is off unless a posture asks, so every test runs its scene twice, once
with the behaviour and once without, and only the decision may differ.
"""

import random
from dataclasses import replace

from warband.brains.pro_ai import PRO, ProBrain
from warband.brains.pro_force import strength
from warband.sim.model import World, dist
from warband.sim.rules import BuildingType, Terrain, UnitType


def _world() -> World:
    world = World(64, 48, [[Terrain.GRASS] * 64 for _ in range(48)], 2, rng=random.Random(5))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.BARRACKS, (7, 2))
    for player in world.players[:2]:
        player.gold, player.lumber = 5000, 2000
    for i in range(6):
        world.spawn_unit(0, UnitType.PEASANT, (4.5, 6.5 + i))
    return world


def _soldiers(world: World, player: int, n: int, at: tuple[float, float]) -> list:
    return [world.spawn_unit(player, UnitType.FOOTMAN, (at[0], at[1] + i)) for i in range(n)]


def _brain(**changes) -> ProBrain:
    profile = replace(PRO, name="trial", scout=False, creep=False, min_army=5, **changes)
    return ProBrain(0, profile)


def _soft_scene(soft: bool) -> ProBrain:
    """A near barracks under a tower and four footmen; a far hall alone.  Who gets walked at?"""
    world = _world()
    world.place_building(1, BuildingType.BARRACKS, (20, 8))
    world.place_building(1, BuildingType.TOWER, (24, 8))
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    _soldiers(world, 1, 4, (22.5, 12.5))
    _soldiers(world, 0, 10, (5.5, 10.5))
    world.reveal_all(0)
    brain = _brain(soft_target=soft, attack_ratio=0.5)
    brain.think(world, random.Random(1))
    return brain


def test_soft_target_walks_at_the_undefended_hall_not_the_nearest_barracks():
    soft = _soft_scene(True)
    plain = _soft_scene(False)
    assert soft.attacking and plain.attacking
    assert dist(soft.target, (53.5, 37.5)) < 6.0, f"soft target chose {soft.target}"
    assert dist(plain.target, (21.5, 9.5)) < 6.0, f"nearest target chose {plain.target}"


def _punish_scene(punish: bool) -> ProBrain:
    """Their eight footmen are visible in the far corner; their hall stands empty.  Six of ours wait."""
    world = _world()
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    _soldiers(world, 1, 8, (58.5, 4.5))
    _soldiers(world, 0, 6, (5.5, 10.5))
    world.reveal_all(0)
    brain = _brain(punish=punish, punish_ratio=0.5, attack_ratio=1.2)
    brain.think(world, random.Random(1))
    return brain


def test_punish_attacks_the_empty_base_it_would_otherwise_leave():
    assert _punish_scene(True).attacking, "their army is seen away: go now"
    assert not _punish_scene(False).attacking, "six against eight on paper: the unmodified brain waits"


def test_a_push_turned_back_by_towers_calls_for_catapults_without_holding_the_army():
    world = _world()
    world.place_building(0, BuildingType.BLACKSMITH, (7, 6))
    workshop = world.place_building(0, BuildingType.WORKSHOP, (11, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    world.place_building(1, BuildingType.TOWER, (49, 36))
    world.place_building(1, BuildingType.TOWER, (56, 36))
    _soldiers(world, 1, 4, (52.5, 32.5))
    ours = _soldiers(world, 0, 4, (50.5, 30.5))
    world.reveal_all(0)
    brain = _brain(siege_answer=2, abort_ratio=1.5, attack_ratio=0.5)
    brain.attacking = True
    brain.target = (53.5, 37.5)
    brain.commit_strength = strength(world, ours)
    brain.think(world, random.Random(1))
    assert not brain.attacking, "the push reads the towers and turns back"
    assert brain._siege_wanted(world), "and calls for catapults"
    assert not brain._push_waits(world), "but the army is not held hostage to the workshop"
    counts = {t: 0 for t in (UnitType.FOOTMAN, UnitType.CATAPULT, UnitType.FLYING_MACHINE)}
    wish = brain._choose_unit(workshop, counts, {UnitType.CATAPULT: 0.1, UnitType.FOOTMAN: 0.9})
    assert wish is not None and wish[1] is UnitType.CATAPULT
    world.spawn_unit(0, UnitType.CATAPULT, (6.5, 20.5))
    world.spawn_unit(0, UnitType.CATAPULT, (7.5, 20.5))
    assert not brain._siege_wanted(world)


def _trade_scene(trade: bool) -> ProBrain:
    """Three raiders at a hall two towers cover; eight of ours could answer them or walk at their hall."""
    world = _world()
    world.place_building(0, BuildingType.TOWER, (6, 6))
    world.place_building(0, BuildingType.TOWER, (2, 7))
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    _soldiers(world, 1, 3, (6.5, 5.5))
    _soldiers(world, 0, 8, (10.5, 10.5))
    world.reveal_all(0)
    brain = _brain(base_trade=trade, attack_ratio=0.5)
    brain.think(world, random.Random(1))
    return brain


def test_base_trade_lets_the_towers_hold_and_walks_at_their_base():
    assert _trade_scene(True).attacking, "home holds on its towers: start the race"
    assert not _trade_scene(False).attacking, "the unmodified brain comes home to defend"


def _intercept_scene(intercept: bool) -> ProBrain:
    """Four of theirs in the open middle; their hall behind three towers; eight of ours at home."""
    world = _world()
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    for at in ((49, 36), (56, 36), (52, 41)):
        world.place_building(1, BuildingType.TOWER, at)
    _soldiers(world, 1, 4, (32.5, 24.5))
    _soldiers(world, 0, 8, (5.5, 10.5))
    world.reveal_all(0)
    brain = _brain(intercept=intercept, attack_ratio=1.0)
    brain.think(world, random.Random(1))
    return brain


def test_intercept_fights_the_army_in_the_open_instead_of_its_towers():
    on = _intercept_scene(True)
    off = _intercept_scene(False)
    assert on.attacking and dist(on.target, (32.5, 26.0)) < 6.0, f"intercept chose {on.target}"
    assert off.target is None or dist(off.target, (32.5, 26.0)) >= 6.0


def _repair_orders(world: World) -> int:
    from warband.sim.model import Repair

    return sum(1 for p in world.player_units(0) if isinstance(p.order, Repair))


def test_a_repair_crew_mends_several_walls_at_once_and_under_fire_when_asked():
    world = _world()
    tower = world.place_building(0, BuildingType.TOWER, (14, 14))
    barracks = next(b for b in world.player_buildings(0) if b.type is BuildingType.BARRACKS)
    tower.hp = tower.max_hp // 3
    barracks.hp = barracks.max_hp // 3
    _soldiers(world, 1, 2, (15.5, 17.5))  # at the tower's wall, far from the barracks
    solo = _brain()
    solo._repairs(world)
    assert _repair_orders(world) == 1, "the unmodified brain sends one hammer, to whichever wall is quiet"

    world2 = _world()
    tower2 = world2.place_building(0, BuildingType.TOWER, (14, 14))
    barracks2 = next(b for b in world2.player_buildings(0) if b.type is BuildingType.BARRACKS)
    tower2.hp = tower2.max_hp // 3
    barracks2.hp = barracks2.max_hp // 3
    _soldiers(world2, 1, 2, (15.5, 17.5))
    crew = _brain(repair_crew=3, repair_under_fire=True)
    crew._repairs(world2)
    assert _repair_orders(world2) == 2, "both walls get a hammer, the tower's under fire included"


def test_queue_depth_lets_a_barracks_run_ahead_of_itself():
    def queued(depth: int) -> int:
        world = _world()
        for i in range(4):
            world.place_building(0, BuildingType.FARM, (12 + 3 * i, 6))
        brain = _brain(queue_depth=depth)
        for _ in range(3):
            brain._training(world)
        barracks = next(b for b in world.player_buildings(0) if b.type is BuildingType.BARRACKS)
        return len(barracks.queue)

    assert queued(2) == 2
    assert queued(4) == 3, "one more soldier is already paid for and coming"


def test_without_siege_answer_the_same_withdrawal_asks_for_nothing():
    world = _world()
    world.place_building(1, BuildingType.TOWN_HALL, (52, 36))
    world.place_building(1, BuildingType.TOWER, (49, 36))
    world.place_building(1, BuildingType.TOWER, (56, 36))
    _soldiers(world, 1, 10, (52.5, 32.5))
    ours = _soldiers(world, 0, 4, (50.5, 30.5))
    world.reveal_all(0)
    brain = _brain(abort_ratio=1.5, attack_ratio=0.5)
    brain.attacking = True
    brain.target = (53.5, 37.5)
    brain.commit_strength = strength(world, ours)
    brain.think(world, random.Random(1))
    assert not brain.attacking and not brain._siege_wanted(world)
