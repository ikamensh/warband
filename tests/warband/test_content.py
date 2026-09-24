"""The content layer: the tech chain, research and upgrades, healers, siege engines, lumber mills."""

import random
import re
from collections.abc import Iterable

import pytest

from warband.sim.model import Attack, Deposit, Heal, Move, RuleError, World, dist, tile_center
from warband.sim.rules import (BUILDINGS, BUILT, HORSES_BONUS, PLAYABLE_UNITS, SIM_DT, UNITS, UPGRADES, BuildingType, Race, Resource, Terrain,
                               UnitType, Upgrade)


def flat_world(width: int = 30, height: int = 24, trees: Iterable[tuple[int, int]] = ()) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 2, rng=random.Random(2))
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


# -- What a refusal reads like -------------------------------------------------------


def refusals(race: Race) -> set[str]:
    """Every reason the rules can give a player of *race* for refusing an order of the catalogue."""
    world = World(24, 24, [[Terrain.GRASS] * 24 for _ in range(24)], 2, human=0, races=[race, race])
    for player in world.players:
        world.reveal_all(player.id)
    placed = []
    for index, kind in enumerate(BUILDINGS):
        if kind is BuildingType.GOLD_MINE:
            world.place_building(None, kind, (20, 20))
            continue
        placed.append(world.place_building(0, kind, (1 + index % 4 * 4, 1 + index // 4 * 4)))
    site = world.place_building(0, BuildingType.FARM, (1, 16), done=False)
    said = {world.can_train(b, u) for b in [*placed, site] for u in PLAYABLE_UNITS}
    said |= {world.can_research(b, up) for b in placed for up in Upgrade}
    said |= {world.can_place(kind, pos, 0) for kind in BUILDINGS for pos in ((1, 1), (23, 23), (-1, 5), (20, 20))}
    said |= {world.can_plan_building(kind, (2, 2), 0) for kind in BUILDINGS}
    said |= {world.auto_train_blocker(b) for b in placed}
    return {reason for reason in said if reason}


@pytest.mark.parametrize("race", list(Race))
def test_a_refusal_names_things_the_way_english_does(race: Race) -> None:
    """The races name an Altar, an Orchard and an Engine Works, and one Footman makes Footmen: a message that
    glues "a" or "s" onto a name from the tables gets one of them wrong for some race."""
    for reason in refusals(race):
        assert not re.search(r"\ba [aeiouAEIOU]", reason), reason
        assert not re.search(r"\b(man|Man)s\b", reason), reason


# -- Tech chain ----------------------------------------------------------------------


def test_every_unit_and_building_is_reachable_through_the_chain() -> None:
    trained = {u for info in BUILDINGS.values() for u in info.trains}
    assert trained == set(PLAYABLE_UNITS)
    researched = {u for info in BUILDINGS.values() for u in info.researches}
    assert researched == set(Upgrade)
    for building_type, info in BUILDINGS.items():
        chain, seen = info.requires, set()
        while chain is not None:
            assert chain not in seen, f"{building_type} requires itself"
            seen.add(chain)
            chain = BUILDINGS[chain].requires
    for upgrade in Upgrade:  # an upgrade that waits for itself, however far round, is a button nobody can ever press
        seen, edge = set(), [upgrade]
        while edge:
            needed = edge.pop()
            assert needed is not upgrade or not seen, f"{upgrade} requires itself"
            if needed not in seen:
                seen.add(needed)
                edge.extend(UPGRADES[needed].requires)
    assert len(PLAYABLE_UNITS) >= 7 and len(BUILT) >= 8 and len(Upgrade) >= 6


def test_the_keep_gates_the_upper_tiers_and_the_master_weapons() -> None:
    """The hall researches a Keep, and behind it stand the second tier of every stat and the third of the two weapon
    lines: each is refused by name until both its lower tier and the Keep are in."""
    world = flat_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.BARRACKS, (6, 2))
    smith = world.place_building(0, BuildingType.BLACKSMITH, (10, 2))
    mill = world.place_building(0, BuildingType.LUMBER_MILL, (14, 2))
    for building, upgrade in ((smith, Upgrade.BLADES_2), (smith, Upgrade.ARMOR_2), (mill, Upgrade.ARROWS_2), (mill, Upgrade.ARROWS_3)):
        assert "Keep" in world.can_research(building, upgrade), upgrade
    assert world.can_research(smith, Upgrade.BLADES_3) == "Requires Tempered Blades and Keep"
    assert world.can_research(smith, Upgrade.KEEP) == "Keep is not researched here"

    world.research(hall.id, Upgrade.KEEP)
    run(world, UPGRADES[Upgrade.KEEP].time + 0.1)
    assert Upgrade.KEEP in world.players[0].upgrades
    assert world.can_research(smith, Upgrade.BLADES_2) == "Requires Sharpened Blades"  # the gate is open; the tier is not
    for upgrade in (Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3):
        assert world.can_research(smith, upgrade) is None
        world.research(smith.id, upgrade)
        run(world, UPGRADES[upgrade].time + 0.1)
    assert world.can_research(hall, Upgrade.KEEP) == "Already researched"


def test_the_master_weapons_are_worth_two_tiers_and_leave_armour_alone() -> None:
    """The third tier of each weapon line is the only one to add four: a very expensive, long research for a step
    twice what the tiers below it gave.  Armour has no third tier to give."""
    world = flat_world()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5))
    archer = world.spawn_unit(0, UnitType.ARCHER, (6.5, 8.5))
    tower = world.place_building(0, BuildingType.TOWER, (10, 10))
    base = (world.damage_of(footman), world.damage_of(archer), world.damage_of(tower))
    world.players[0].upgrades.update({Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARROWS_1, Upgrade.ARROWS_2})
    assert (world.damage_of(footman), world.damage_of(archer)) == (base[0] + 4, base[1] + 4)
    world.players[0].upgrades.update({Upgrade.BLADES_3, Upgrade.ARROWS_3})
    assert world.damage_of(footman) == base[0] + 8
    assert world.damage_of(archer) == base[1] + 8 and world.damage_of(tower) == base[2] + 8
    assert {u for u in Upgrade if u.value.startswith("armor_")} == {Upgrade.ARMOR_1, Upgrade.ARMOR_2}
    assert UPGRADES[Upgrade.BLADES_3].cost.gold >= 2 * UPGRADES[Upgrade.BLADES_2].cost.gold
    assert UPGRADES[Upgrade.BLADES_3].time >= 2 * UPGRADES[Upgrade.BLADES_2].time


def test_buildings_and_units_need_their_prerequisites() -> None:
    world = flat_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    assert world.can_place(BuildingType.STABLES, (10, 10), 0) == "Requires a Barracks"
    barracks = world.place_building(0, BuildingType.BARRACKS, (6, 2))
    assert world.can_place(BuildingType.STABLES, (10, 10), 0) is None
    assert world.can_place(BuildingType.WORKSHOP, (10, 10), 0) == "Requires a Blacksmith"
    assert world.can_train(barracks, UnitType.KNIGHT) == "The Knight is trained at the Stables"
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
    assert world.can_research(smith, Upgrade.BLADES_2) == "Requires Sharpened Blades and Keep"
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
    assert world.heal_amount(cleric) == round(UNITS[UnitType.CLERIC].heal * 1.5)  # a blessed cast restores half again
    assert world.heal_rate(cleric) == pytest.approx(world.heal_amount(cleric) / cleric.info.period) and world.heal_rate(cleric) > base[5]
    assert world.armor_of(knight) == UNITS[UnitType.KNIGHT].armor + 1 and world.armor_of(cleric) == 1


# -- Clerics ------------------------------------------------------------------------------


def test_clerics_heal_the_wounded_on_their_own_and_strike_only_on_order_or_when_no_one_needs_them() -> None:
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
    world.update_vision()
    world.attack([cleric.id], enemy.id)
    assert isinstance(cleric.order, Attack)  # WB-051: its weak blow is the player's to use


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
    assert next(e.amount for e in hits if e.other == farm.id) >= 20  # ×1.5 against buildings, minus armour
    assert a.hp < a.max_hp and b.hp < b.max_hp  # both stood where the stone came down
    assert max(e.amount for e in hits if e.other == b.id) < max(e.amount for e in hits if e.other == a.id)  # a tile off: a share of the blow


def test_a_flying_machine_outpaces_and_outsees_a_knight_and_horses_are_for_knights() -> None:
    world = flat_world(60, 10)
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (2.5, 5.5))
    knight = world.spawn_unit(0, UnitType.KNIGHT, (2.5, 3.5))
    world.move([flyer.id], (58.5, 4.5))
    world.move([knight.id], (58.5, 4.5))
    run(world, 5.0)
    assert flyer.x > knight.x + 3
    assert UNITS[UnitType.FLYING_MACHINE].sight > UNITS[UnitType.KNIGHT].sight
    world.players[0].upgrades.add(Upgrade.HORSES)
    assert world.speed_of(knight) == UNITS[UnitType.KNIGHT].speed + HORSES_BONUS
    assert world.speed_of(flyer) == UNITS[UnitType.FLYING_MACHINE].speed, "Horse Breeding is for knights"


# -- Lumber mills --------------------------------------------------------------------------


def test_lumber_goes_to_the_nearest_mill_and_gold_only_to_a_hall() -> None:
    world = flat_world(40, 20, trees=[(x, y) for x in range(32, 35) for y in range(7, 12)])
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    mill = world.place_building(0, BuildingType.LUMBER_MILL, (26, 8))
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


def test_a_shot_does_more_than_a_scratch_against_the_heaviest_armour() -> None:
    """Armour is flat with a floor of one, so a shooter's damage has to clear the heaviest plate by a margin.

    At five damage an archer did one point to a knight's four armour: ninety
    shots to fell it, and the counter the rules table promises did not exist.
    The balance league measured archers taking nothing at all against a
    knights army; this pins the margin that fixed it.
    """
    heaviest = max(info.armor for info in UNITS.values())
    for shooter in (UnitType.ARCHER, UnitType.CATAPULT):
        assert UNITS[shooter].damage - heaviest >= 2, f"{shooter.value} barely scratches the heaviest armour"
