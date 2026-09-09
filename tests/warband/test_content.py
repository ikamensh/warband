"""The content layer: the tech chain, research and upgrades, healers, siege engines, lumber mills."""

import random

import pytest

from warband.model import Attack, Deposit, Heal, Move, RuleError, World, dist, tile_center
from warband.rules import BUILDINGS, SIM_DT, UNITS, UPGRADES, BuildingType, Resource, Terrain, UnitType, Upgrade


def flat_world(width: int = 30, height: int = 24) -> World:
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 2, rng=random.Random(2))
    for player in world.players:
        player.gold, player.lumber = 20_000, 20_000
        world.reveal_all(player.id)
    return world


def run(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def run_until(world: World, condition, max_seconds: float) -> None:
    for _ in range(int(round(max_seconds / SIM_DT))):
        if condition():
            return
        world.step()
    raise AssertionError(f"not reached within {max_seconds}s")


# -- Tech chain ----------------------------------------------------------------------


def test_every_unit_and_building_is_reachable_through_the_chain() -> None:
    trained = {u for info in BUILDINGS.values() for u in info.trains}
    assert trained == set(UnitType)
    researched = {u for info in BUILDINGS.values() for u in info.researches}
    assert researched == set(Upgrade)
    for building_type, info in BUILDINGS.items():
        chain, seen = info.requires, set()
        while chain is not None:
            assert chain not in seen, f"{building_type} requires itself"
            seen.add(chain)
            chain = BUILDINGS[chain].requires
    assert len(UnitType) >= 7 and len([b for b in BuildingType if b is not BuildingType.GOLD_MINE]) >= 8 and len(Upgrade) >= 6


def test_buildings_and_units_need_their_prerequisites() -> None:
    world = flat_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    assert world.can_place(BuildingType.STABLES, (10, 10), 0) == "Requires a Barracks"
    barracks = world.place_building(0, BuildingType.BARRACKS, (6, 2))
    assert world.can_place(BuildingType.STABLES, (10, 10), 0) is None
    assert world.can_place(BuildingType.WORKSHOP, (10, 10), 0) == "Requires a Blacksmith"
    assert world.can_train(barracks, UnitType.KNIGHT) == "Knights are trained at the Stables"
    stables = world.place_building(0, BuildingType.STABLES, (10, 2))
    assert world.can_train(stables, UnitType.KNIGHT) is None and world.can_train(hall, UnitType.PEASANT) is None


# -- Research and upgrades ---------------------------------------------------------------


def test_research_costs_time_and_money_and_upgrades_apply_to_the_right_units() -> None:
    world = flat_world()
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.BARRACKS, (6, 2))
    smith = world.place_building(0, BuildingType.BLACKSMITH, (10, 2))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5))
    archer = world.spawn_unit(0, UnitType.ARCHER, (6.5, 8.5))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (7.5, 8.5))
    assert world.can_research(smith, Upgrade.BLADES_2) == "Requires Sharpened Blades"
    assert world.can_research(smith, Upgrade.ARROWS_1) == "Bodkin Arrows is not researched here"
    gold = world.players[0].gold
    world.research(smith.id, Upgrade.BLADES_1)
    assert world.players[0].gold == gold - UPGRADES[Upgrade.BLADES_1].cost.gold and smith.research is Upgrade.BLADES_1
    assert world.can_research(smith, Upgrade.ARMOR_1) == "Researching Sharpened Blades"
    assert world.can_train(smith, UnitType.FOOTMAN) is not None
    run(world, UPGRADES[Upgrade.BLADES_1].time + 0.1)
    assert Upgrade.BLADES_1 in world.players[0].upgrades and smith.research is None
    assert any(e.kind == "researched" and e.text == "Sharpened Blades" for e in world.events)
    assert world.damage_of(footman) == UNITS[UnitType.FOOTMAN].damage + 2
    assert world.damage_of(archer) == UNITS[UnitType.ARCHER].damage  # blades are for melee
    assert world.damage_of(peasant) == UNITS[UnitType.PEASANT].damage  # peasants stay peasants
    assert world.can_research(smith, Upgrade.BLADES_1) == "Already researched"
    world.research(smith.id, Upgrade.ARMOR_1)
    with pytest.raises(RuleError, match="Already being researched"):
        world.research(world.place_building(0, BuildingType.BLACKSMITH, (14, 2)).id, Upgrade.ARMOR_1)
    world.cancel_research(smith.id)
    assert smith.research is None and world.players[0].gold == gold - UPGRADES[Upgrade.BLADES_1].cost.gold


def test_arrows_horses_siege_and_blessing_change_the_matching_stats() -> None:
    world = flat_world()
    archer = world.spawn_unit(0, UnitType.ARCHER, (5.5, 8.5))
    tower = world.place_building(0, BuildingType.TOWER, (10, 10))
    knight = world.spawn_unit(0, UnitType.KNIGHT, (6.5, 8.5))
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (7.5, 8.5))
    cleric = world.spawn_unit(0, UnitType.CLERIC, (8.5, 8.5))
    base = (world.damage_of(archer), world.damage_of(tower), world.speed_of(knight), world.range_of(catapult), world.damage_of(catapult), world.heal_rate(cleric))
    world.players[0].upgrades.update({Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.HORSES, Upgrade.SIEGE, Upgrade.BLESSING, Upgrade.ARMOR_1})
    assert world.damage_of(archer) == base[0] + 4 and world.damage_of(tower) == base[1] + 4
    assert world.speed_of(knight) == pytest.approx(base[2] + 0.8)
    assert world.range_of(catapult) == base[3] + 1 and world.damage_of(catapult) > base[4]
    assert world.heal_rate(cleric) == pytest.approx(base[5] * 1.5)
    assert world.armor_of(knight) == UNITS[UnitType.KNIGHT].armor + 1 and world.armor_of(cleric) == 1


# -- Clerics ------------------------------------------------------------------------------


def test_clerics_heal_the_wounded_on_their_own_and_never_attack() -> None:
    world = flat_world()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 5.5))
    hurt = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 5.5))
    hurt.hp = 20
    run(world, 0.5)
    assert isinstance(cleric.order, Heal) and cleric.order.target == hurt.id
    run_until(world, lambda: hurt.hp >= hurt.max_hp, 12.0)
    assert any(e.kind == "heal" for e in world.events)
    run(world, 2.0)
    assert not cleric.orders and dist(cleric.pos, (5.5, 5.5)) < 1.5
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (12.5, 5.5))
    world.attack([cleric.id], enemy.id)
    assert isinstance(cleric.order, Move)  # a healer follows, it does not fight
    world.stop([cleric.id])
    run(world, 3.0)
    assert not any(isinstance(o, Attack) for o in cleric.orders)


def test_clerics_on_attack_move_tend_the_wounded_along_the_way() -> None:
    world = flat_world()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (2.5, 5.5))
    hurt = world.spawn_unit(0, UnitType.KNIGHT, (10.5, 5.5))
    hurt.hp = 30
    world.attack_move([cleric.id], (20.5, 5.5))
    run_until(world, lambda: isinstance(cleric.order, Heal), 6.0)
    run_until(world, lambda: hurt.hp >= hurt.max_hp, 20.0)
    run_until(world, lambda: dist(cleric.pos, (20.5, 5.5)) < 0.5, 15.0)


# -- Catapults ------------------------------------------------------------------------------


def test_catapults_splash_and_batter_buildings_from_afar() -> None:
    world = flat_world()
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (3.5, 8.5))
    farm = world.place_building(1, BuildingType.FARM, (12, 8))
    a = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 8.5))  # standing at the wall the stones hit
    b = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 9.5))
    world.hold([a.id, b.id])
    world.attack([catapult.id], farm.id)
    run_until(world, lambda: farm.hp < farm.max_hp, 8.0)
    assert dist(catapult.pos, farm.center) >= 6.5  # it never closes in
    hits = [e for e in world.events if e.kind == "hit" and e.entity == catapult.id]
    assert hits[0].other == farm.id and hits[0].amount >= 20  # ×1.5 against buildings, minus armour
    assert a.hp < a.max_hp and b.hp < b.max_hp  # both stood inside the splash
    assert max(e.amount for e in hits if e.other == a.id) < hits[0].amount  # a share of the blow, not the whole


def test_scouts_are_fast_and_knights_faster_with_horses() -> None:
    world = flat_world(60, 10)
    scout = world.spawn_unit(0, UnitType.SCOUT, (2.5, 5.5))
    knight = world.spawn_unit(0, UnitType.KNIGHT, (2.5, 3.5))
    world.move([scout.id], (58.5, 4.5))
    world.move([knight.id], (58.5, 4.5))
    run(world, 5.0)
    assert scout.x > knight.x + 3
    assert UNITS[UnitType.SCOUT].sight > UNITS[UnitType.KNIGHT].sight


# -- Lumber mills --------------------------------------------------------------------------


def test_lumber_goes_to_the_nearest_mill_and_gold_only_to_a_hall() -> None:
    world = flat_world(40, 20)
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    mill = world.place_building(0, BuildingType.LUMBER_MILL, (26, 8))
    for x in range(32, 35):
        for y in range(7, 12):
            world.terrain[y][x] = Terrain.TREES
            world._blocked[y * world.width + x] = 1
    peasant = world.spawn_unit(0, UnitType.PEASANT, (30.5, 9.5))
    world.harvest([peasant.id], (32, 9))
    run_until(world, lambda: peasant.carrying is Resource.LUMBER, 10.0)
    run_until(world, lambda: peasant.carrying is None, 6.0)  # far too soon to have reached the hall 28 tiles away
    assert world.players[0].lumber == 20_100
    assert any(e.kind == "deposit" and dist(e.pos, mill.center) < 4 for e in world.events)
    world.stop([peasant.id])
    courier = world.spawn_unit(0, UnitType.PEASANT, (30.5, 9.5))
    courier.carrying, courier.carry = Resource.GOLD, 100
    courier.orders.append(Deposit())
    gold = world.players[0].gold
    run(world, 6.0)
    assert courier.carrying is Resource.GOLD  # the nearby mill cannot take crystals
    run_until(world, lambda: courier.carrying is None, 25.0)
    assert world.players[0].gold == gold + 100
    assert any(e.kind == "deposit" and e.text == "gold" and dist(e.pos, hall.center) < 4 for e in world.events)


def test_research_and_upgrades_survive_a_save(tmp_path) -> None:
    import json

    world = flat_world()
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.BARRACKS, (6, 2))
    smith = world.place_building(0, BuildingType.BLACKSMITH, (10, 2))
    world.players[0].upgrades.add(Upgrade.ARMOR_1)
    world.research(smith.id, Upgrade.BLADES_1)
    cleric = world.spawn_unit(0, UnitType.CLERIC, (5.5, 8.5))
    cleric.charge = 0.4
    run(world, 2.0)
    copy = World.from_dict(json.loads(json.dumps(world.to_dict())))
    assert copy.players[0].upgrades == {Upgrade.ARMOR_1}
    assert copy.buildings[smith.id].research is Upgrade.BLADES_1 and copy.buildings[smith.id].research_progress == pytest.approx(2.0)
    assert copy.units[cleric.id].charge == pytest.approx(cleric.charge)
    run(world, 45.0)
    run(copy, 45.0)
    assert world.to_dict() == copy.to_dict() and Upgrade.BLADES_1 in copy.players[0].upgrades
