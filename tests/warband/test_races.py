"""The four races: shared skeleton, different names and numbers, race arts and one mechanic each."""

import json
import random

import pytest

from warband import mapgen
from warband.ai import Brain
from warband.model import RuleError, World, dist
from warband.races import RACES
from warband.rules import (
    BUILDINGS, DEEP_MINING_TRIP, GOLD_PER_TRIP, REGROWTH_SECONDS, SIM_DT, UNITS, UPGRADES, BuildingType, Difficulty, Race, Resource, Terrain,
    UnitType, Upgrade,
)


def flat_world(races: tuple[Race, ...], width: int = 30, height: int = 24) -> World:
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], len(races), rng=random.Random(2), races=races)
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


# -- The skeleton is shared -----------------------------------------------------------


def test_every_race_fields_every_role_from_the_same_buildings_with_the_same_hotkeys_and_costs() -> None:
    for race, info in RACES.items():
        assert set(info.units) == set(UnitType) and set(info.buildings) == set(BuildingType)
        names = [u.name for u in info.units.values()] + [b.name for b in info.buildings.values() if b.name != "Gold Mine"]
        assert len(set(names)) == len(names), (race, "duplicate name")
        for unit_type, unit in info.units.items():
            base = UNITS[unit_type]
            assert (unit.cost, unit.trained_at, unit.hotkey, unit.heal > 0, unit.melee) == (base.cost, base.trained_at, base.hotkey, base.heal > 0, base.melee)
        for building_type, building in info.buildings.items():
            base = BUILDINGS[building_type]
            assert (building.cost, building.size, building.hotkey, building.trains, building.requires) == (base.cost, base.size, base.hotkey, base.trains, base.requires)
        assert len(info.arts) == 2 and all(UPGRADES[art].race is race for art in info.arts)
        for building_type, card in info.cards.items():
            assert len(card) <= 8, (race, building_type, card)
    assert {UPGRADES[u].race for u in Upgrade} == {None, *Race}


def test_names_and_numbers_differ_by_race_and_a_unit_reports_its_race() -> None:
    world = flat_world((Race.HUMAN, Race.ORC, Race.ELF, Race.DWARF))
    footmen = [world.spawn_unit(p, UnitType.FOOTMAN, (2.5 + p, 2.5)) for p in range(4)]
    assert [u.info.name for u in footmen] == ["Footman", "Grunt", "Sentinel", "Ironguard"]
    assert [u.race for u in footmen] == list(Race)
    assert footmen[1].max_hp > footmen[0].max_hp > footmen[2].max_hp and footmen[3].max_hp > footmen[0].max_hp
    assert world.speed_of(footmen[2]) > world.speed_of(footmen[0]) > world.speed_of(footmen[3])
    assert world.armor_of(footmen[3]) > world.armor_of(footmen[0]) > world.armor_of(footmen[1])
    halls = [world.place_building(p, BuildingType.TOWN_HALL, (2 + 4 * p, 8)) for p in range(4)]
    assert [b.info.name for b in halls] == ["Town Hall", "Great Hall", "Moon Hall", "Deep Hold"]
    assert halls[3].max_hp == int(BUILDINGS[BuildingType.TOWN_HALL].hp * 1.25) and world.armor_of(halls[3]) == BUILDINGS[BuildingType.TOWN_HALL].armor + 2
    assert world.mines() == [] and world.place_building(None, BuildingType.GOLD_MINE, (20, 20)).info.name == "Gold Mine"


def test_race_arts_are_refused_to_other_races_and_the_ai_researches_only_its_own() -> None:
    world = flat_world((Race.ORC, Race.HUMAN))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.BARRACKS, (6, 2))
    stables = world.place_building(0, BuildingType.STABLES, (10, 2))
    assert world.can_research(stables, Upgrade.HORSES) == "Horse Breeding is a Human art"
    with pytest.raises(RuleError, match="Human art"):
        world.order_upgrade(0, Upgrade.HORSES)
    assert world.can_research(stables, Upgrade.PLUNDER) is None
    world.order_upgrade(0, Upgrade.PLUNDER)
    run(world, 1.5)
    assert stables.research is Upgrade.PLUNDER
    world = mapgen.generate(seed=11, players=2, human=None, races=(Race.ELF, Race.DWARF))
    for player in world.players:
        player.gold, player.lumber = 50_000, 50_000
    for player in world.players:
        hall = world.player_buildings(player.id, BuildingType.TOWN_HALL)[0]
        dx, dy = (4 if hall.x < world.width / 2 else -4), (4 if hall.y < world.height / 2 else -4)  # towards the middle
        world.place_building(player.id, BuildingType.BARRACKS, (hall.x + dx, hall.y + dy))
        world.place_building(player.id, BuildingType.LUMBER_MILL, (hall.x + 2 * dx, hall.y + dy))
        world.place_building(player.id, BuildingType.BLACKSMITH, (hall.x + dx, hall.y + 2 * dy))
        world.place_building(player.id, BuildingType.STABLES, (hall.x + 2 * dx, hall.y + 2 * dy))
    brains = [Brain(p.id, Difficulty.HARD) for p in world.players]
    rng = random.Random(1)
    for _ in range(int(400 / SIM_DT)):
        for brain in brains:
            brain.think(world, rng)
        world.step()
    researched = [set(p.upgrades) for p in world.players]
    assert Upgrade.LONGBOWS in researched[0] and Upgrade.DEEP_MINING in researched[1]
    for upgrades, race in zip(researched, (Race.ELF, Race.DWARF)):
        assert all(UPGRADES[u].race in (None, race) for u in upgrades), (race, upgrades)


# -- Humans: drill ----------------------------------------------------------------------


def test_humans_train_faster_than_the_other_races() -> None:
    world = flat_world((Race.HUMAN, Race.ORC))
    halls = [world.place_building(p, BuildingType.TOWN_HALL, (2 + 6 * p, 2)) for p in range(2)]
    for hall in halls:
        world.train(hall.id, UnitType.PEASANT)
    run_until(world, lambda: not halls[0].queue, 20)
    assert halls[1].queue == [UnitType.PEASANT]
    assert UNITS[UnitType.PEASANT].build_time * 0.8 < world.time < UNITS[UnitType.PEASANT].build_time
    run_until(world, lambda: not halls[1].queue, 20)
    assert [u.info.name for u in world.player_units(1)] == ["Peon"]


# -- Orcs: frenzy, bloodlust and plunder ----------------------------------------------------


def test_orcs_hit_harder_below_half_health_and_bloodlust_doubles_the_frenzy() -> None:
    world = flat_world((Race.ORC, Race.HUMAN))
    grunt = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    peon = world.spawn_unit(0, UnitType.PEASANT, (3.5, 2.5))
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (4.5, 2.5))
    calm = world.damage_of(grunt)
    assert calm == UNITS[UnitType.FOOTMAN].damage + 1 and not world.frenzied(grunt)
    grunt.hp = grunt.max_hp // 2 - 1
    assert world.frenzied(grunt) and world.damage_of(grunt) == int(round(calm * 1.25))
    peon.hp, footman.hp = 1, 1
    assert not world.frenzied(peon) and not world.frenzied(footman)
    world.players[0].upgrades.add(Upgrade.BLOODLUST)
    assert world.damage_of(grunt) == int(round(calm * 1.5))
    grunt.hp = grunt.max_hp
    assert world.damage_of(grunt) == calm


def test_plunder_loots_gold_from_razed_buildings() -> None:
    world = flat_world((Race.ORC, Race.HUMAN))
    ogre = world.spawn_unit(0, UnitType.KNIGHT, (3.5, 8.5))
    farm = world.place_building(1, BuildingType.FARM, (6, 8))
    farm.hp = 5
    world.attack([ogre.id], farm.id)
    gold = world.players[0].gold
    run_until(world, lambda: farm.id not in world.buildings, 10)
    assert world.players[0].gold == gold  # plunder is an art
    world.players[0].upgrades.add(Upgrade.PLUNDER)
    barracks = world.place_building(1, BuildingType.BARRACKS, (10, 8))
    barracks.hp = 5
    world.attack([ogre.id], barracks.id)
    run_until(world, lambda: barracks.id not in world.buildings, 15)
    loot = int(BUILDINGS[BuildingType.BARRACKS].cost.gold * 0.2)
    assert world.players[0].gold == gold + loot
    assert any(e.kind == "plunder" and e.amount == loot and e.player == 0 for e in world.events)


# -- Elves: keen eyes, longbows and regrowth ------------------------------------------------------


def test_elves_see_farther_rangers_shoot_farther_and_longbows_reach_towers_too() -> None:
    world = flat_world((Race.ELF, Race.HUMAN))
    ranger = world.spawn_unit(0, UnitType.ARCHER, (2.5, 2.5))
    archer = world.spawn_unit(1, UnitType.ARCHER, (2.5, 5.5))
    eyrie = world.place_building(0, BuildingType.TOWER, (10, 10))
    tower = world.place_building(1, BuildingType.TOWER, (14, 10))
    assert ranger.info.sight == archer.info.sight + 2
    assert world.range_of(ranger) == world.range_of(archer) + 1 and world.building_range(eyrie) == world.building_range(tower)
    world.players[0].upgrades.add(Upgrade.LONGBOWS)
    assert world.range_of(ranger) == world.range_of(archer) + 2 and world.building_range(eyrie) == world.building_range(tower) + 1
    assert world.range_of(world.spawn_unit(0, UnitType.CATAPULT, (2.5, 8.5))) == UNITS[UnitType.CATAPULT].range  # bows, not ballistae
    victim = world.spawn_unit(1, UnitType.PEASANT, (11.5, 18.0))  # 6.5 tiles below the eyrie's wall, beyond a plain tower
    world.hold([victim.id])
    run(world, 3.0)
    assert victim.hp < victim.max_hp


def test_regrowth_brings_felled_trees_back_unless_something_stands_there() -> None:
    world = flat_world((Race.ELF, Race.HUMAN), 40, 20)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    for x in range(12, 14):
        for y in range(7, 10):
            world.terrain[y][x] = Terrain.TREES
            world._blocked[y * world.width + x] = 1
    gatherer = world.spawn_unit(0, UnitType.PEASANT, (10.5, 8.5))
    world.harvest([gatherer.id], (12, 8))
    run_until(world, lambda: world.terrain_at((12, 8)) is Terrain.GRASS, 12)
    assert world.regrowth == []  # not researched yet
    world.players[0].upgrades.add(Upgrade.REGROWTH)
    world.stop([gatherer.id])
    world.harvest([gatherer.id], (12, 9))
    run_until(world, lambda: world.terrain_at((12, 9)) is Terrain.GRASS, 30)
    (tile, when), = world.regrowth
    assert tile == (12, 9) and when == pytest.approx(world.time + REGROWTH_SECONDS, abs=SIM_DT)
    world.stop([gatherer.id])
    squatter = world.spawn_unit(1, UnitType.FOOTMAN, (12.5, 9.5))
    world.hold([squatter.id])
    run(world, REGROWTH_SECONDS + 2)
    assert world.terrain_at((12, 9)) is Terrain.GRASS and world.regrowth  # occupied: it waits
    del world.units[squatter.id]
    run(world, 6)
    assert world.terrain_at((12, 9)) is Terrain.TREES and world.passable(12, 9) is False and world.regrowth == []
    assert any(e.kind == "tree_grown" and e.pos == (12.5, 9.5) for e in world.events)
    copy = World.from_dict(json.loads(json.dumps(world.to_dict())))
    assert copy.terrain_at((12, 9)) is Terrain.TREES and copy.players[0].race is Race.ELF


# -- Dwarves: stonework, deep mining and blasting powder ------------------------------------------


def test_deep_mining_brings_more_gold_per_trip() -> None:
    world = flat_world((Race.DWARF, Race.HUMAN), 30, 20)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (10, 8))
    miner = world.spawn_unit(0, UnitType.PEASANT, (8.5, 9.5))
    world.harvest([miner.id], mine.id)
    run_until(world, lambda: miner.carrying is Resource.GOLD, 15)
    assert miner.carry == GOLD_PER_TRIP
    world.players[0].upgrades.add(Upgrade.DEEP_MINING)
    run_until(world, lambda: miner.carrying is None, 15)
    run_until(world, lambda: miner.carrying is Resource.GOLD, 20)
    assert miner.carry == DEEP_MINING_TRIP and mine.gold == 50_000 - GOLD_PER_TRIP - DEEP_MINING_TRIP


def test_blasting_powder_widens_the_mortar_splash() -> None:
    world = flat_world((Race.DWARF, Race.HUMAN))
    mortar = world.spawn_unit(0, UnitType.CATAPULT, (3.5, 8.5))
    farm = world.place_building(1, BuildingType.FARM, (12, 8))
    near = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 9.5))
    far = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 10.4))  # 1.96 tiles from the struck wall: inside a 1.8-tile splash, outside 1.2
    world.hold([near.id, far.id])
    world.attack([mortar.id], farm.id)
    run_until(world, lambda: near.hp < near.max_hp, 10)
    assert far.hp == far.max_hp
    world.players[0].upgrades.add(Upgrade.BLASTING_POWDER)
    assert world.splash_of(mortar) == pytest.approx(UNITS[UnitType.CATAPULT].splash * 1.5)
    run_until(world, lambda: far.hp < far.max_hp, 10)


# -- Maps, saves and matches ---------------------------------------------------------------------


def test_maps_draw_distinct_races_from_the_seed_and_honour_explicit_choices() -> None:
    drawn = [tuple(p.race for p in mapgen.generate(seed=seed, players=4).players) for seed in range(1, 6)]
    assert all(len(set(races)) == 4 and races[0] is Race.HUMAN for races in drawn) and len(set(drawn)) > 1  # the human leads Humans
    assert drawn[0] == tuple(p.race for p in mapgen.generate(seed=1, players=4).players)
    assert {tuple(p.race for p in mapgen.generate(seed=seed, players=2, human=None).players)[0] for seed in range(1, 12)} > {Race.HUMAN}
    world = mapgen.generate(seed=1, players=3, races=(Race.ORC, None, Race.ORC))
    assert world.players[0].race is Race.ORC and world.players[2].race is Race.ORC and world.players[1].race is not Race.ORC
    assert all(u.race is world.players[u.player].race for u in world.units.values())
    assert all(b.race is world.players[b.player].race for b in world.buildings.values() if b.player is not None)
    with pytest.raises(ValueError, match="need 3 races"):
        mapgen.generate(seed=1, players=3, races=(Race.ORC, Race.ELF))


def test_races_survive_a_save_and_an_old_save_means_humans() -> None:
    world = mapgen.generate(seed=4, players=2, races=(Race.DWARF, Race.ELF))
    data = json.loads(json.dumps(world.to_dict()))
    copy = World.from_dict(data)
    assert [p.race for p in copy.players] == [Race.DWARF, Race.ELF]
    hall = copy.player_buildings(0, BuildingType.TOWN_HALL)[0]
    assert hall.race is Race.DWARF and hall.info.name == "Deep Hold" and hall.hp == hall.max_hp
    assert all(u.info.name == "Gatherer" for u in copy.player_units(1))
    for saved in data["players"]:
        del saved["race"]
    del data["regrowth"]
    old = World.from_dict(data)
    assert all(p.race is Race.HUMAN for p in old.players) and old.regrowth == []


def test_a_match_between_two_races_plays_out_under_the_ai() -> None:
    world = mapgen.generate(seed=9, players=2, human=None, races=(Race.ORC, Race.DWARF))
    brains = [Brain(p.id, Difficulty.HARD) for p in world.players]
    rng = random.Random(9)
    for _ in range(int(240 / SIM_DT)):
        for brain in brains:
            brain.think(world, rng)
        world.step()
    for player in world.players:
        army = [u for u in world.player_units(player.id) if not u.is_worker]
        assert army and all(u.race is player.race for u in army), player.race
        assert any(b.type is BuildingType.BARRACKS for b in world.player_buildings(player.id))
    assert all(dist(u.pos, u.pos) == 0 for u in world.units.values())
