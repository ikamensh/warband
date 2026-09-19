"""Marksmanship (lumber mill): a shooter left to itself picks the mark in reach it fells soonest, through the armour it
wears and counting what is already on its way to it, and wastes no arrow on the dying.  An order names its own mark."""

import random

from warband.sim.model import Attack, World
from warband.sim.rules import BuildingType, Terrain, UnitType, Upgrade


def field(drilled: bool) -> World:
    world = World(30, 16, [[Terrain.GRASS] * 30 for _ in range(16)], 2, human=None, rng=random.Random(4))
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 12))
    if drilled:
        world.players[0].upgrades.add(Upgrade.MARKSMANSHIP)
    return world


def marks(world: World, shooters, seconds: float = 1.5) -> list[int]:
    """Whom each arrow of *shooters* flew at, in the order they were loosed."""
    seen: dict[int, int] = {}
    own = {u.id for u in shooters}
    for _ in range(int(seconds * 20)):
        world.step()
        for p in world.projectiles.values():
            if p.source in own:
                seen.setdefault(p.id, p.target)
    return [seen[k] for k in sorted(seen)]


def test_the_upgrade_is_researched_at_the_lumber_mill_by_every_race() -> None:
    world = field(drilled=False)
    mill = world.place_building(0, BuildingType.LUMBER_MILL, (5, 5))
    world.players[0].gold = world.players[0].lumber = 5000
    assert world.can_research(mill, Upgrade.MARKSMANSHIP) is None


def test_drilled_shooters_waste_no_arrow_on_a_mark_the_first_arrow_fells() -> None:
    """Two archers and two peasants in reach, the nearer one a blow from death: undrilled both loose at it, drilled
    the second archer takes the other, because the first one's shot is already counted against it."""
    targets = {}
    for drilled in (False, True):
        world = field(drilled)
        archers = [world.spawn_unit(0, UnitType.ARCHER, (10.5, 7.5 + k)) for k in range(2)]
        dying = world.spawn_unit(1, UnitType.PEASANT, (13.5, 8.0))
        hale = world.spawn_unit(1, UnitType.PEASANT, (14.2, 8.0))
        dying.hp = 1
        world.hold([dying.id, hale.id])  # they stand and take it: the archers' marks are what is being read
        world.update_vision()
        loosed = marks(world, archers)
        targets[drilled] = (loosed[:2], dying.id, hale.id)
    undrilled, dying, hale = targets[False]
    assert undrilled == [dying, dying]
    drilled_marks, dying, hale = targets[True]
    assert sorted(drilled_marks) == sorted([dying, hale])


def test_a_drilled_shooter_prefers_the_mark_its_arrows_hurt() -> None:
    """A footman in plate stands nearer than an unarmoured archer, both in reach: the undrilled archer looses at the
    nearer, the drilled one at the one it fells in a fraction of the arrows."""
    first = {}
    for drilled in (False, True):
        world = field(drilled)
        archer = world.spawn_unit(0, UnitType.ARCHER, (10.5, 8.0))
        plate = world.spawn_unit(1, UnitType.FOOTMAN, (13.0, 8.0))
        soft = world.spawn_unit(1, UnitType.ARCHER, (14.0, 8.4))
        world.hold([plate.id, soft.id])
        world.update_vision()
        first[drilled] = (marks(world, [archer])[0], plate.id, soft.id)
    assert first[False][0] == first[False][1]
    assert first[True][0] == first[True][2]


def test_an_order_to_attack_names_its_own_mark() -> None:
    world = field(drilled=True)
    archer = world.spawn_unit(0, UnitType.ARCHER, (10.5, 8.0))
    plate = world.spawn_unit(1, UnitType.FOOTMAN, (13.0, 8.0))
    soft = world.spawn_unit(1, UnitType.ARCHER, (14.0, 8.4))
    world.hold([plate.id, soft.id])
    world.update_vision()
    world.attack([archer.id], plate.id)
    assert set(marks(world, [archer], seconds=4.0)) == {plate.id}
    assert isinstance(archer.order, Attack) and archer.order.target == plate.id
