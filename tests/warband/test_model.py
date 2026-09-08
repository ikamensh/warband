"""The rules, driven straight through World: orders, economy, combat, construction, fog, saves."""

import random

import pytest

from warband import mapgen
import math

from warband.model import Attack, Deposit, Harvest, Move, Repair, RuleError, World, dist, tile_center
from warband.rules import (
    BUILDINGS, CHOP_TIME, GOLD_PER_TRIP, LUMBER_PER_TRIP, MINE_GOLD, MINE_TIME, REPAIR_COST, SIM_DT, UNITS, BuildingType, Resource, Terrain,
    UnitType,
)


def flat_world(width: int = 24, height: int = 20, players: int = 2) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    return World(width, height, terrain, players, rng=random.Random(1))


def run(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def events(world: World, kind: str):
    return [e for e in world.events if e.kind == kind]


def run_until(world: World, condition, max_seconds: float) -> None:
    for _ in range(int(round(max_seconds / SIM_DT))):
        if condition():
            return
        world.step()
    raise AssertionError(f"not reached within {max_seconds}s")


# -- Movement ---------------------------------------------------------------------


def test_a_unit_walks_to_where_it_is_sent_and_stops() -> None:
    world = flat_world()
    unit = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    world.move([unit.id], (10.5, 2.5))
    run(world, 1.0)
    assert 3.5 < unit.x < 6 and unit.state == "move" and abs(unit.facing) < 0.01
    run(world, 4.0)
    assert dist(unit.pos, (10.5, 2.5)) < 0.15 and unit.state == "idle" and not unit.orders


def test_units_path_around_trees_and_never_stand_in_them() -> None:
    world = flat_world()
    for y in range(0, 20):
        if y != 15:
            world.terrain[y][10] = Terrain.TREES
            world._blocked[y * world.width + 10] = 1
    unit = world.spawn_unit(0, UnitType.KNIGHT, (2.5, 2.5))
    world.move([unit.id], (18.5, 2.5))
    for _ in range(int(20 / SIM_DT)):
        world.step()
        assert world.passable(*unit.tile), unit.pos
    assert dist(unit.pos, (18.5, 2.5)) < 0.2


def test_a_unit_at_a_building_corner_still_reaches_a_target_around_it() -> None:
    # Fuzz seed 203: the scout stood just below a lumber mill's corner with the peasant just left of
    # it; the straight line looked clear when sampled, but every step entered the mill's tile.
    world = flat_world()
    world.place_building(0, BuildingType.LUMBER_MILL, (4, 4))  # tiles 4..6 x 4..6
    peasant = world.spawn_unit(0, UnitType.PEASANT, (3.239, 5.354))
    scout = world.spawn_unit(1, UnitType.SCOUT, (4.105, 7.123))
    world.attack([scout.id], peasant.id)
    for _ in range(int(10 / SIM_DT)):
        world.step()
        assert world.passable(*scout.tile), scout.pos
        if peasant.hp < UNITS[UnitType.PEASANT].hp:
            break
    else:
        raise AssertionError(f"the scout never reached the peasant, standing at {scout.pos}")


def test_a_walk_ends_when_a_crowd_keeps_the_unit_from_the_exact_spot() -> None:
    # Fuzz seed 2016, the tiles and positions as found: two idle footmen pinned against the trees
    # above and to the right of the spot push the archer back exactly as far as it walks up each
    # tick, so it stood "walking" for the rest of the match.
    world = flat_world()
    rows = ("#######..", "##..####.", "#....###.", ".....##..", ".....##..")
    for j, row in enumerate(rows):
        for i, cell in enumerate(row):
            if cell == "#":
                world.terrain[10 + j][5 + i] = Terrain.TREES
                world._blocked[(10 + j) * world.width + 5 + i] = 1
    world.spawn_unit(0, UnitType.FOOTMAN, (9.999, 12.283))
    world.spawn_unit(0, UnitType.FOOTMAN, (9.999, 12.015))
    archer = world.spawn_unit(0, UnitType.ARCHER, (9.984, 12.67))
    world.attack_move([archer.id], (9.9846, 12.2515))
    run_until(world, lambda: not archer.orders, 8)
    assert archer.state == "idle" and dist(archer.pos, (9.9846, 12.2515)) < 1.0


def test_a_crowd_cannot_shove_a_unit_through_a_tree_wall() -> None:
    # Fuzz seed 2203: eight overlapping units summed a push of over a tile, and the nudge only checked
    # the destination tile, so units jumped across the forest into an isolated clearing.
    world = flat_world()
    for x in range(3, 10):
        for y in (2, 3, 4):
            if (x, y) != (6, 3):  # a one-tile clearing inside the wood
                world.terrain[y][x] = Terrain.TREES
                world._blocked[y * world.width + x] = 1
    units = [world.spawn_unit(0, UnitType.FOOTMAN, (6.0 + 0.01 * i, 5.05)) for i in range(10)]
    world.move([u.id for u in units], (6.5, 5.2))
    for _ in range(int(4 / SIM_DT)):
        world.step()
        for u in units:
            assert u.tile != (6, 3) and u.y >= 5.0, (u.id, u.pos)


def test_a_unit_pushed_into_a_corner_walks_back_to_its_tile_centre_before_the_exact_spot() -> None:
    # The same seed, the other half: a detour to the unit's own tile was inserted into the path, but
    # the waypoint rule still aimed at the exact point across the tree, so every step was refused.
    world = flat_world()
    world.terrain[5][4] = Terrain.TREES
    world._blocked[5 * world.width + 4] = 1
    unit = world.spawn_unit(0, UnitType.FOOTMAN, (5.02, 5.5))
    world.move([unit.id], (4.5, 6.9))
    unit.path, unit.exact, unit.path_goal = [(5, 5)], (4.5, 6.9), (4, 6)  # the state a crowd leaves behind
    run_until(world, lambda: not unit.orders, 6)
    assert dist(unit.pos, (4.5, 6.9)) < 0.2


def test_units_ordered_to_one_spot_spread_out_instead_of_stacking() -> None:
    world = flat_world()
    ids = [world.spawn_unit(0, UnitType.FOOTMAN, (2.5 + i, 2.5)).id for i in range(4)]
    world.move(ids, (12.5, 12.5))
    run(world, 10.0)
    units = [world.units[i] for i in ids]
    for a in units:
        assert dist(a.pos, (12.5, 12.5)) < 2.5
        for b in units:
            if a is not b:
                assert dist(a.pos, b.pos) > 0.5


def test_orders_can_be_queued() -> None:
    world = flat_world()
    unit = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    world.move([unit.id], (6.5, 2.5))
    world.move([unit.id], (6.5, 6.5), queue=True)
    assert len(unit.orders) == 2
    run(world, 6.0)
    assert dist(unit.pos, (6.5, 6.5)) < 0.15


# -- Combat -----------------------------------------------------------------------


def test_a_footman_kills_a_peasant_and_the_death_is_reported() -> None:
    world = flat_world()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (6.5, 2.5))
    world.attack([footman.id], peasant.id)
    run(world, 12.0)
    assert peasant.id not in world.units
    assert any(e.kind == "death" and e.entity == peasant.id for e in world.events)
    hits = [e for e in world.events if e.kind == "hit" and e.other == peasant.id]
    assert hits and all(1 <= e.amount <= 9 for e in hits)
    assert footman.state == "idle" and not footman.orders


def test_a_hit_soldier_fights_back_and_idle_soldiers_engage_enemies_in_sight() -> None:
    world = flat_world()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    theirs = world.spawn_unit(1, UnitType.FOOTMAN, (5.5, 2.5))
    run(world, 0.5)
    assert isinstance(ours.order, Attack) and ours.order.target == theirs.id and ours.order.auto
    run(world, 3.0)
    assert ours.hp < ours.max_hp and theirs.hp < theirs.max_hp and isinstance(theirs.order, Attack)
    run(world, 20.0)
    assert (ours.id in world.units) != (theirs.id in world.units)


def test_an_idle_unit_gives_up_the_chase_past_the_leash_and_walks_home() -> None:
    world = flat_world(40, 10)
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 5.5))
    runner = world.spawn_unit(1, UnitType.KNIGHT, (6.5, 5.5))
    world.move([runner.id], (38.5, 5.5))
    run(world, 12.0)
    assert dist(ours.pos, (2.5, 5.5)) < 1.0
    assert runner.hp > 0


def test_attack_move_engages_what_it_meets_then_carries_on() -> None:
    world = flat_world(30, 10)
    ours = world.spawn_unit(0, UnitType.KNIGHT, (2.5, 5.5))
    victim = world.spawn_unit(1, UnitType.PEASANT, (10.5, 5.5))
    world.attack_move([ours.id], (26.5, 5.5))
    run(world, 30.0)
    assert victim.id not in world.units
    assert dist(ours.pos, (26.5, 5.5)) < 0.3


def test_archers_shoot_from_a_distance_and_towers_shoot_on_their_own() -> None:
    world = flat_world()
    archer = world.spawn_unit(0, UnitType.ARCHER, (2.5, 2.5))
    target = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 2.5))
    world.hold([target.id])
    world.attack([archer.id], target.id)
    run(world, 3.0)
    assert 3.5 < dist(archer.pos, target.pos) < 4.9
    assert any(e.kind == "hit" and e.text == "ranged" for e in world.events)
    world.events.clear()
    world.reveal_all(1)
    tower = world.place_building(1, BuildingType.TOWER, (14, 6))
    run(world, 2.0)
    assert not any(e.kind == "hit" and e.entity == tower.id for e in world.events)
    world.move([archer.id], (12.5, 6.5))
    run(world, 5.0)
    assert any(e.kind == "hit" and e.entity == tower.id and e.other == archer.id for e in world.events)


def test_buildings_can_be_razed_and_the_last_loss_ends_the_game() -> None:
    world = flat_world()
    hall = world.place_building(1, BuildingType.TOWN_HALL, (14, 8))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    knights = [world.spawn_unit(0, UnitType.KNIGHT, (8.5, 8.5 + i)).id for i in range(4)]
    world.attack(knights, hall.id)
    run(world, 120.0)
    assert hall.id not in world.buildings
    assert world.winner == 0 and not world.players[1].alive
    assert any(e.kind == "victory" for e in world.events)


def test_being_hit_raises_one_under_attack_alert_per_cooldown() -> None:
    world = flat_world()
    world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 2.5))
    world.spawn_unit(0, UnitType.FOOTMAN, (2.5, 3.5))
    world.place_building(1, BuildingType.FARM, (5, 2))
    run(world, 6.0)
    alerts = [e for e in world.events if e.kind == "under_attack" and e.player == 1]
    assert len(alerts) == 1


# -- Economy ------------------------------------------------------------------------


def base_world() -> tuple[World, int]:
    world = flat_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (4, 8))
    world.place_building(None, BuildingType.GOLD_MINE, (4, 2))
    for x in range(14, 17):
        for y in range(6, 12):
            world.terrain[y][x] = Terrain.TREES
            world._blocked[y * world.width + x] = 1
    world.update_vision()
    return world, hall.id


def test_peasants_mine_gold_and_bring_it_home_again_and_again() -> None:
    world, _hall = base_world()
    mine = world.mines()[0]
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    gold = world.players[0].gold
    world.harvest([peasant.id], mine.id)
    run_until(world, lambda: peasant.inside == mine.id, 4.0)
    assert peasant.hidden and world.unit_at(peasant.pos) is None
    run_until(world, lambda: peasant.inside is None, MINE_TIME + 0.2)
    assert peasant.carrying is Resource.GOLD and peasant.carry == GOLD_PER_TRIP
    assert isinstance(peasant.order, Deposit) and isinstance(peasant.orders[1], Harvest)
    assert mine.gold == MINE_GOLD - GOLD_PER_TRIP
    run_until(world, lambda: world.players[0].gold > gold, 4.0)
    assert world.players[0].gold == gold + GOLD_PER_TRIP and peasant.carrying is None
    deposits = events(world, "deposit")
    assert deposits and deposits[0].amount == GOLD_PER_TRIP and deposits[0].text == "gold"
    run(world, 12.0)
    assert world.players[0].gold >= gold + 2 * GOLD_PER_TRIP


def test_peasants_fell_trees_for_lumber_and_move_on_to_the_next_tree() -> None:
    world, _hall = base_world()
    peasant = world.spawn_unit(0, UnitType.PEASANT, (10.5, 8.5))
    lumber = world.players[0].lumber
    world.harvest([peasant.id], (14, 8))
    run(world, 2.0)
    assert peasant.state == "chop"
    run(world, CHOP_TIME)
    assert world.terrain_at((14, 8)) is Terrain.GRASS and world.passable(14, 8)
    assert peasant.carrying is Resource.LUMBER and peasant.carry == LUMBER_PER_TRIP
    assert events(world, "tree_felled")
    run(world, 8.0)
    assert world.players[0].lumber == lumber + LUMBER_PER_TRIP
    assert isinstance(peasant.order, Harvest) and world.terrain_at(peasant.order.target) is Terrain.TREES


def test_only_peasants_harvest_and_only_at_mines_or_trees() -> None:
    world, _hall = base_world()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 8.5))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 9.5))
    with pytest.raises(RuleError):
        world.harvest([footman.id], world.mines()[0].id)
    with pytest.raises(RuleError):
        world.harvest([peasant.id], (8, 8))


def test_right_click_picks_the_sensible_verb() -> None:
    world, hall_id = base_world()
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 9.5))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (9.5, 12.5))
    world.reveal_all(0)
    world.update_vision()
    assert world.smart([peasant.id, footman.id], tile_center((5, 3))) == "harvest"
    assert isinstance(peasant.order, Harvest) and isinstance(footman.order, Move)
    assert world.smart([peasant.id], tile_center((15, 8))) == "harvest"
    assert world.smart([footman.id], enemy.pos) == "attack" and footman.order.target == enemy.id
    assert world.smart([footman.id], (2.5, 15.5)) == "move"
    world.set_rally(hall_id, (9.5, 9.5))
    assert world.buildings[hall_id].rally == (9.5, 9.5)


# -- Buildings ----------------------------------------------------------------------


def test_placement_rules_say_why_a_site_is_refused() -> None:
    world, _hall = base_world()
    world.reveal_all(0)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (9.5, 8.5))
    assert world.can_place(BuildingType.FARM, (9, 12), 0) is None
    assert world.can_place(BuildingType.FARM, (5, 9), 0) == "Something is in the way"
    assert world.can_place(BuildingType.FARM, (14, 7), 0) == "Needs open ground"
    assert world.can_place(BuildingType.FARM, (23, 5), 0) == "Off the map"
    assert world.can_place(BuildingType.FARM, (9, 8), 0) == "A unit is in the way"
    assert world.can_place(BuildingType.FARM, (9, 8), 0, builder=peasant.id) is None
    assert world.can_place(BuildingType.FARM, (8, 3), 0) == "Too close to the gold mine"
    assert world.can_place(BuildingType.BARRACKS, (9, 12), 0) is None
    assert world.can_place(BuildingType.TOWER, (9, 12), 0) == "Requires a Barracks"
    world.explored[0] = bytearray(len(world.explored[0]))
    assert world.can_place(BuildingType.FARM, (9, 12), 0) == "Unexplored"


def test_a_peasant_builds_a_farm_which_then_feeds_more_units() -> None:
    world, hall_id = base_world()
    world.reveal_all(0)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    gold, lumber = world.players[0].gold, world.players[0].lumber
    assert world.supply(0) == (1, BUILDINGS[BuildingType.TOWN_HALL].supply)
    world.build(peasant.id, BuildingType.FARM, (10, 10))
    run(world, 2.0)
    farm = next(b for b in world.buildings.values() if b.type is BuildingType.FARM)
    assert not farm.done and peasant.constructing == farm.id and peasant.hidden
    assert world.players[0].gold == gold - 500 and world.players[0].lumber == lumber - 250
    assert events(world, "construction")
    run(world, BUILDINGS[BuildingType.FARM].build_time + 0.5)
    assert farm.done and farm.hp == farm.max_hp
    assert peasant.constructing is None and not peasant.hidden
    assert isinstance(peasant.order, Harvest) and peasant.order.auto
    assert world.passable(*peasant.tile) and world.building_at(peasant.tile) is None
    assert world.supply(0)[1] == BUILDINGS[BuildingType.TOWN_HALL].supply + 4
    assert events(world, "built")
    with pytest.raises(RuleError, match="gold"):
        world.players[0].gold = 0
        world.build(peasant.id, BuildingType.FARM, (12, 12))


def test_an_interrupted_site_can_be_cancelled_for_a_refund_or_resumed() -> None:
    world, _hall = base_world()
    world.reveal_all(0)
    a = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    b = world.spawn_unit(0, UnitType.PEASANT, (8.5, 12.5))
    world.build(a.id, BuildingType.FARM, (10, 10))
    run(world, 4.0)
    farm = next(x for x in world.buildings.values() if x.type is BuildingType.FARM)
    world.move([a.id], (2.5, 15.5))
    assert a.constructing is None and farm.builder is None
    progress = farm.progress
    run(world, 2.0)
    assert farm.progress == progress
    world.resume_construction([b.id], farm.id)
    run_until(world, lambda: farm.builder == b.id and farm.progress > progress, 15.0)
    assert farm.builder == b.id and farm.progress > progress
    gold = world.players[0].gold
    world.cancel_building(farm.id)
    assert farm.id not in world.buildings and world.players[0].gold == gold + 500
    assert b.constructing is None and not b.orders


def test_peasants_repair_damaged_buildings_for_a_share_of_the_price() -> None:
    world, hall_id = base_world()
    hall = world.buildings[hall_id]
    farm = world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 4))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (hall.x + 4.5, hall.y + 4.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (hall.x + 4.5, hall.y + 6.5))
    with pytest.raises(RuleError, match="Nothing to repair"):
        world.repair([peasant.id], farm.id)
    farm.hp = 100
    with pytest.raises(RuleError, match="Only peasants"):
        world.repair([footman.id], farm.id)
    gold, lumber = world.players[0].gold, world.players[0].lumber
    assert world.smart([peasant.id, footman.id], farm.center) == "repair"
    assert isinstance(peasant.order, Repair) and isinstance(footman.order, Move)
    run(world, 2.0)  # ten hit points are paid for at a time
    assert peasant.state == "repair" and farm.hp > 100
    run_until(world, lambda: farm.hp >= farm.max_hp, 60.0)
    assert not peasant.orders and peasant.state == "idle"
    least = math.ceil(BUILDINGS[BuildingType.FARM].cost.gold * REPAIR_COST * 300 / farm.max_hp)
    assert least <= gold - world.players[0].gold <= least + 30 and lumber - world.players[0].lumber > 0  # paid per ten hit points, rounded up
    farm.hp = 50
    world.players[0].gold = 0
    world.repair([peasant.id], farm.id)
    run(world, 3.0)
    assert any(e.text.startswith("Cannot repair") for e in events(world, "refused")) and farm.hp <= 60
    assert isinstance(peasant.order, Harvest) and peasant.order.auto
    world.players[0].gold = 1000
    world.repair([peasant.id], farm.id)
    assert isinstance(World.from_dict(world.to_dict()).units[peasant.id].order, Repair)


def test_training_costs_gold_takes_time_and_needs_farms() -> None:
    world, hall_id = base_world()
    hall = world.buildings[hall_id]
    gold = world.players[0].gold
    world.train(hall_id, UnitType.PEASANT)
    assert world.players[0].gold == gold - 400 and hall.queue == [UnitType.PEASANT]
    with pytest.raises(RuleError, match="trained at the Barracks"):
        world.train(hall_id, UnitType.FOOTMAN)
    run(world, UNITS[UnitType.PEASANT].build_time + 0.1)
    peasants = [u for u in world.units.values() if u.type is UnitType.PEASANT]
    assert len(peasants) == 1 and not hall.queue and events(world, "trained")
    assert world.building_at(peasants[0].tile) is None
    world.players[0].gold = 10_000
    for _ in range(4):
        world.train(hall_id, UnitType.PEASANT)
    with pytest.raises(RuleError, match="farms"):
        world.train(hall_id, UnitType.PEASANT)
    world.cancel_train(hall_id)
    assert len(hall.queue) == 3 and world.players[0].gold == 10_000 - 3 * 400


def test_a_rally_point_on_a_mine_sends_new_peasants_to_work() -> None:
    world, hall_id = base_world()
    mine = world.mines()[0]
    world.set_rally(hall_id, mine.center)
    world.train(hall_id, UnitType.PEASANT)
    run(world, UNITS[UnitType.PEASANT].build_time + 0.1)
    peasant = next(u for u in world.units.values())
    assert isinstance(peasant.order, Harvest) and peasant.order.target == mine.id


# -- Fog -------------------------------------------------------------------------------


def test_units_see_around_themselves_and_the_map_stays_explored() -> None:
    world = flat_world()
    unit = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    world.update_vision()
    assert world.is_visible(0, (5, 5)) and world.is_visible(0, (9, 5)) and not world.is_visible(0, (12, 5))
    assert not world.is_visible(1, (5, 5))
    world.move([unit.id], (15.5, 5.5))
    run(world, 6.0)
    assert not world.is_visible(0, (5, 5)) and world.is_explored(0, (5, 5))
    hidden_enemy = world.spawn_unit(1, UnitType.FOOTMAN, (2.5, 2.5))
    world.update_vision()
    assert world.unit_at(hidden_enemy.pos, visible_to=0) is None
    assert world.unit_at(hidden_enemy.pos) is hidden_enemy


# -- Saves -------------------------------------------------------------------------------


def test_a_generated_map_round_trips_through_json_mid_action() -> None:
    world = mapgen.generate(seed=4)
    peasants = [u for u in world.units.values() if u.player == 0]
    world.harvest([p.id for p in peasants[:2]], world.mines()[0].id)
    world.harvest([peasants[2].id], world.nearest_tree(peasants[2].pos, 12))
    run(world, 5.0)
    data = world.to_dict()
    import json

    copy = World.from_dict(json.loads(json.dumps(data)))
    assert copy.to_dict() == data
    run(world, 10.0)
    run(copy, 10.0)
    assert world.to_dict() == copy.to_dict()
    assert world.players[0].gold > 1000 or any(u.carrying for u in world.units.values())


def test_patrol_walks_back_and_forth_and_fights_what_it_meets() -> None:
    world = flat_world(30, 10)
    knight = world.spawn_unit(0, UnitType.KNIGHT, (2.5, 5.5))
    world.patrol([knight.id], (12.5, 5.5))
    run_until(world, lambda: knight.x > 12.0, 8.0)
    run_until(world, lambda: knight.x < 3.0, 8.0)
    assert isinstance(knight.order, __import__("warband.model", fromlist=["Patrol"]).Patrol)
    victim = world.spawn_unit(1, UnitType.PEASANT, (8.5, 5.5))
    run_until(world, lambda: victim.id not in world.units, 15.0)
    run_until(world, lambda: knight.x > 12.0, 10.0)  # and carries on patrolling
