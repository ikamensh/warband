"""Armour classes and attack types (WB-049): one table says how hard each kind of blow lands on each kind of armour.
Piercing blows (every race's archers) land half again as hard on the unarmoured (peasants, clerics, catapults), siege
stones half again as hard on buildings, and everything else as listed.  The end of the module is where the player is
told: the codex's tables, which a player reads beside the card of the unit they have selected."""

import random

import pytest

from saga2d import Game
from saga2d.ui import Label
from warband.sim.model import SIM_DT, World
from warband.sim.races import RACES
from warband.sim.rules import (
    DAMAGE_FACTORS, HIT_VARIANCE, PLAYABLE_UNITS, UNITS, ArmorClass, AttackType, BuildingType, Race, Terrain, UnitType, damage_factor,
)
from warband.ui.scene import PAGE_LEGENDS, CodexScene, armour_name
from warband.ui.style import build_theme


def field() -> World:
    """Open grass; each side keeps a hall in a far corner, so neither has surrendered."""
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], 2, rng=random.Random(7))
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 16))
    return world


def blows(world: World, striker: int, victim: int, seconds: float = 8.0) -> list[int]:
    """What *striker*'s blows did to *victim*, blow by blow, over *seconds* of striking at it."""
    world.update_vision()  # an order on what the striker's side has never seen is dropped
    world.attack([striker], victim)
    dealt: list[int] = []
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()
        dealt += [e.amount for e in world.take_events() if e.kind == "hit" and e.entity == striker and e.other == victim]
        if victim not in world.units and victim not in world.buildings:
            break
    assert dealt, "no blow landed"
    return dealt


def rolled(damage: float, armor: int) -> tuple[int, int]:
    """The least and the most a blow of *damage* can do through *armor*."""
    return max(1, round(damage * (1 - HIT_VARIANCE)) - armor), max(1, round(damage * (1 + HIT_VARIANCE)) - armor)


def within(dealt: list[int], damage: float, armor: int) -> bool:
    low, high = rolled(damage, armor)
    return all(low <= amount <= high for amount in dealt)


@pytest.mark.parametrize("victim", [UnitType.PEASANT, UnitType.CLERIC, UnitType.CATAPULT])
def test_an_archer_strikes_the_unarmoured_half_again_as_hard(victim: UnitType) -> None:
    world = field()
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 10.5))
    target = world.spawn_unit(1, victim, (8.5, 10.5))
    world.hold([target.id])
    dealt = blows(world, archer.id, target.id)
    assert within(dealt, 1.5 * archer.info.damage, target.info.armor), dealt
    assert max(dealt) > rolled(archer.info.damage, target.info.armor)[1], "no blow landed harder than an unscaled one could"


def test_an_archer_strikes_a_footman_and_a_footman_strikes_a_peasant_as_listed() -> None:
    world = field()
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 10.5))
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 10.5))
    world.hold([footman.id])
    assert within(blows(world, archer.id, footman.id), archer.info.damage, footman.info.armor)
    world = field()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 10.5))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (6.3, 10.5))
    world.hold([peasant.id])
    assert within(blows(world, footman.id, peasant.id), footman.info.damage, peasant.info.armor)


def test_a_tower_arrow_strikes_a_peasant_as_listed() -> None:
    """Towers shoot a normal blow: the rush answers of WB-037 and WB-044 were measured on it."""
    world = field()
    tower = world.place_building(0, BuildingType.TOWER, (4, 9))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (8.5, 10.5))
    world.hold([peasant.id])
    dealt: list[int] = []
    for _ in range(int(round(6.0 / SIM_DT))):
        world.step()
        dealt += [e.amount for e in world.take_events() if e.kind == "hit" and e.entity == tower.id]
    assert dealt and within(dealt, world.damage_of(tower), peasant.info.armor), dealt


def test_a_stone_strikes_a_building_half_again_as_hard() -> None:
    world = field()
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (3.5, 10.5))
    farm = world.place_building(1, BuildingType.FARM, (9, 10))
    dealt = blows(world, catapult.id, farm.id, seconds=10.0)
    assert within(dealt, 1.5 * catapult.info.damage, farm.info.armor), dealt


def test_the_table_covers_every_unit_of_every_race_and_most_pairings_are_even() -> None:
    for race in Race:
        for unit_type, info in RACES[race].units.items():
            assert isinstance(info.armor_class, ArmorClass) and isinstance(info.attack, AttackType), (race, unit_type)
            assert info.attack is UNITS[unit_type].attack and info.armor_class is UNITS[unit_type].armor_class
    assert UNITS[UnitType.ARCHER].attack is AttackType.PIERCING and UNITS[UnitType.CATAPULT].attack is AttackType.SIEGE
    assert {t for t in PLAYABLE_UNITS if UNITS[t].armor_class is ArmorClass.UNARMORED} == {
        UnitType.PEASANT, UnitType.CLERIC, UnitType.CATAPULT}
    uneven = {pair: factor for pair, factor in DAMAGE_FACTORS.items() if factor != 1.0}
    assert uneven == {(AttackType.PIERCING, ArmorClass.UNARMORED): 1.5, (AttackType.SIEGE, ArmorClass.FORTIFIED): 1.5}
    assert all(damage_factor(attack, armor) == DAMAGE_FACTORS.get((attack, armor), 1.0) for attack in AttackType for armor in ArmorClass)


def test_a_save_from_before_the_armour_classes_loads_with_its_stone_in_flight() -> None:
    """A checkpoint saved before WB-049 carried a projectile's building multiplier as ``siege``; it loads as the
    projectile's attack type, so a retained campaign or room resumes."""
    world = field()
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (3.5, 10.5))
    farm = world.place_building(1, BuildingType.FARM, (9, 10))
    world.update_vision()
    world.attack([catapult.id], farm.id)
    for _ in range(100):
        if world.projectiles:
            break
        world.step()
    assert world.projectiles, "no stone in flight"
    data = world.to_dict()
    for shot in data["projectiles"]:
        shot["siege"] = 1.5 if shot.pop("attack") == AttackType.SIEGE.value else 1.0
    copy = World.from_dict(data)
    assert [p.attack for p in copy.projectiles.values()] == [AttackType.SIEGE]
    assert World.from_dict(world.to_dict()).projectiles == world.projectiles


def codex(tmp_path, page: int, race: Race = Race.HUMAN) -> tuple[Game, list[str]]:
    """*race*'s codex open at *page* in the smallest window, and every label on it: a wrapped cell is drawn line by
    line, so the table is read off the UI tree rather than off the text the backend took."""
    game = Game("Warband codex", backend="mock", resolution=(1200, 680), theme=build_theme(), save_dir=tmp_path / "saves")
    world = World(1, 1, [[Terrain.GRASS]], 1, races=[race])
    game.push(CodexScene(world, 0, page, in_match=False))
    game.tick(1 / 60)
    return game, [str(c.text) for c in game.scene.ui.walk() if isinstance(c, Label)]


@pytest.mark.parametrize("race", list(Race), ids=lambda r: r.value)
def test_the_codex_names_every_unit_s_armour_class_and_its_blow_where_it_is_not_the_plain_one(tmp_path, race) -> None:
    """The unit page's Role column names what every unit wears; it has no room to name a normal blow as well.  At
    1200×680 the page already stands 672 px of 680, and ", normal" on every row wraps the human and orc tables
    28 px past the window.  The card of a selected unit names both halves, always."""
    game, labels = codex(tmp_path, 0, race)
    try:
        for unit_type, info in RACES[race].units.items():
            wanted = armour_name(info.armor_class) + (f", {info.attack.value}" if info.attack is not AttackType.NORMAL else "")
            assert any(text.endswith(wanted) for text in labels), (unit_type, wanted, labels)
    finally:
        game.close()


def test_the_codex_says_once_that_every_building_is_fortified(tmp_path) -> None:
    """The building page has no room for a class column and no need of one: every building wears the same armour,
    so the page says it in a line under the table."""
    game, labels = codex(tmp_path, 1)
    try:
        assert PAGE_LEGENDS[1] in labels
        assert "fortified" in PAGE_LEGENDS[1] and "×1.5" in PAGE_LEGENDS[1]
    finally:
        game.close()
