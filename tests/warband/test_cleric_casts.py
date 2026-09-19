"""A cleric heals in casts (WB-051): it faces its patient, winds up, restores its heal at once and waits its cooldown,
so each heal is a moment to see and hear.  Its own blow is weak and a last resort: left to itself it strikes only while
no one in sight needs healing, and an enemy still counts it after the soldiers when choosing whom to hit."""

import random

from warband.sim.model import SIM_DT, Attack, Heal, Hold, World
from warband.sim.rules import BuildingType, Terrain, UnitType


def field() -> World:
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], 2, rng=random.Random(3))
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 16))
    return world


def run(world: World, seconds: float) -> list:
    events = []
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()
        events += world.take_events()
    return events


def test_a_heal_is_one_cast_after_a_wind_up_then_a_cooldown() -> None:
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 5.5))
    cleric.facing = 0.0
    hurt = world.spawn_unit(0, UnitType.KNIGHT, (7.5, 5.5))
    world.hold([hurt.id])
    hurt.hp = 20
    casts: list[tuple[float, int]] = []
    windups = []
    for _ in range(int(round(8.0 / SIM_DT))):
        world.step()
        windups.append(cleric.windup)
        casts += [(world.time, e.amount) for e in world.take_events() if e.kind == "heal" and e.entity == cleric.id]
    assert [amount for _, amount in casts][:3] == [15, 15, 15], casts  # the whole heal at once, never a trickle
    gaps = [b - a for (a, _), (b, _) in zip(casts, casts[1:])]
    assert all(abs(gap - cleric.info.period) <= 2 * SIM_DT for gap in gaps), gaps
    assert casts[0][0] >= cleric.info.windup - SIM_DT and max(windups) > 0.0
    assert world.heal_rate(cleric) == 15 / cleric.info.period == 6.0


def test_the_last_cast_restores_only_what_is_missing() -> None:
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 5.5))
    hurt = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 5.5))
    world.hold([hurt.id])
    hurt.hp = hurt.max_hp - 4
    events = run(world, 2.0)
    assert [e.amount for e in events if e.kind == "heal"] == [4] and hurt.hp == hurt.max_hp


def test_a_cast_broken_off_by_an_order_heals_nothing() -> None:
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 5.5))
    hurt = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 5.5))
    world.hold([hurt.id])
    hurt.hp = 20
    while cleric.windup <= 0.0:
        world.step()
    world.move([cleric.id], (5.5, 12.5))
    events = run(world, 1.0)
    assert hurt.hp == 20 and not any(e.kind == "heal" for e in events) and cleric.windup == 0.0


def test_the_most_wounded_under_fire_is_healed_first() -> None:
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 8.5))
    scratched = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 7.5))
    bleeding = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 9.5))
    world.hold([scratched.id, bleeding.id])
    scratched.hp, bleeding.hp = scratched.max_hp - 5, 15
    run(world, 0.5)
    assert isinstance(cleric.order, Heal) and cleric.order.target == bleeding.id


def test_a_cleric_strikes_only_while_no_one_needs_healing() -> None:
    """Left alone with an enemy in sight it lands its weak blow; the moment a friend is hurt it turns to heal."""
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 8.5))
    friend = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 11.5))
    enemy = world.spawn_unit(1, UnitType.PEASANT, (8.5, 8.5))
    world.hold([friend.id, enemy.id])
    world.update_vision()
    events = run(world, 4.0)
    assert isinstance(cleric.order, Attack) and cleric.order.auto
    blows = [e.amount for e in events if e.kind == "hit" and e.entity == cleric.id]
    assert blows and max(blows) <= 4, blows  # a weak blow: three, give or take a quarter
    friend.hp = 30
    run(world, 0.5)
    assert isinstance(cleric.order, Heal) and cleric.order.target == friend.id


def test_an_enemy_takes_on_soldiers_before_a_cleric() -> None:
    world = field()
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 8.5))
    cleric = world.spawn_unit(0, UnitType.CLERIC, (7.3, 8.5))
    soldier = world.spawn_unit(0, UnitType.ARCHER, (10.5, 8.5))
    world.hold([cleric.id, soldier.id])
    world.update_vision()
    run(world, 0.5)
    assert isinstance(footman.order, Attack) and footman.order.target == soldier.id


def test_a_cleric_on_hold_heals_the_wounded_in_its_reach_before_it_strikes() -> None:
    """Held, a cleric still treats a hurt friend beside it rather than strike the enemy in its reach, and strikes only once
    no one in its reach needs it; it leaves its spot for neither, nor for a friend hurt beyond its reach.  It used to only
    strike, weakly, while its friend bled."""
    world = field()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 8.5))
    beside = world.spawn_unit(0, UnitType.FOOTMAN, (6.5, 8.5))
    beyond = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 4.0))  # in its sight, out of its reach
    enemy = world.spawn_unit(1, UnitType.PEASANT, (5.5, 10.5))
    world.hold([cleric.id, beside.id, beyond.id, enemy.id])
    beside.hp, beyond.hp = beside.max_hp - 10, 20
    world.update_vision()
    events = run(world, 1.5)
    assert [(e.other, e.amount) for e in events if e.kind == "heal"] == [(beside.id, 10)]
    assert not any(e.kind == "hit" and e.entity == cleric.id for e in events)
    events = run(world, 3.0)
    assert {e.other for e in events if e.kind == "hit" and e.entity == cleric.id} == {enemy.id}
    assert not any(e.kind == "heal" for e in events) and beyond.hp == 20
    assert isinstance(cleric.order, Hold) and cleric.pos == (5.5, 8.5)
