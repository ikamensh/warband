"""The air layer (WB-064): a flying machine flies straight over anything, takes no room on the ground, and only a shot
reaches it.  These are the rules the next flyer inherits by being a row of ``units.toml`` with ``flying = true``."""

import json
import math
import random

import pytest

from warband.brains.ai import answer_flyers
from warband.online.authority import WarbandMatch
from warband.sim import camps
from warband.sim.model import Attack, AttackMove, Move, RuleError, World, dist, tile_center
from warband.sim.rules import CAMP_WATCH, SIM_DT, BuildingType, Race, Terrain, UnitType


def grass(width: int = 40, height: int = 30, *, water=(), trees=()) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in water:
        terrain[y][x] = Terrain.WATER
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 2, rng=random.Random(1))
    for player in world.players[:world.seats]:
        player.human = True
    return world


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def walled_off() -> World:
    """A lake and a wood from edge to edge down the middle: nothing on foot gets across."""
    return grass(water=[(x, y) for x in range(14, 19) for y in range(30)], trees=[(x, y) for x in range(19, 23) for y in range(30)])


# -- Flight ---------------------------------------------------------------------------


def test_a_flyer_crosses_a_lake_and_a_forest_no_walker_can_cross_in_a_straight_line() -> None:
    world = walled_off()
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (5.5, 5.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 20.5))
    goal = (34.5, 12.5)
    world.move([flyer.id], goal)
    world.move([footman.id], (34.5, 20.5))
    worst = 0.0  # its greatest distance from the straight line: a route would bend round the water
    for _ in range(round(12.0 / SIM_DT)):
        world.step()
        ax, ay = 5.5, 5.5
        bx, by = goal
        worst = max(worst, abs((bx - ax) * (ay - flyer.y) - (ax - flyer.x) * (by - ay)) / math.hypot(bx - ax, by - ay))
    assert dist(flyer.pos, goal) < 0.15 and not flyer.orders, flyer.pos
    assert worst < 0.05, f"it strayed {worst:.2f} tiles off the straight line"
    assert footman.x < 14, "nothing on foot crosses the water"


def test_a_flyer_is_kept_on_the_map() -> None:
    world = grass()
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (38.5, 28.5))
    world.move([flyer.id], (400.0, 300.0))
    run(world, 2.0)
    assert 0 < flyer.x < world.width and 0 < flyer.y < world.height and not flyer.orders


def test_a_flyer_over_the_ground_is_in_nobodys_way_and_nobody_is_in_its() -> None:
    """No body on the ground: it does not shove a walker, is not shoved, and does not stop a building going up under it."""
    world = grass()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (10.5, 10.5))
    run(world, 2.0)
    assert footman.pos == (10.5, 10.5) and flyer.pos == (10.5, 10.5)
    walker = world.spawn_unit(0, UnitType.KNIGHT, (4.5, 16.5))
    hovering = world.spawn_unit(1, UnitType.FLYING_MACHINE, (10.5, 16.5))
    world.hold([hovering.id])
    world.move([walker.id], (16.5, 16.5))
    for _ in range(round(5.0 / SIM_DT)):
        world.step()
        assert abs(walker.y - 16.5) < 1e-9 and hovering.pos == (10.5, 16.5), (walker.pos, hovering.pos)
    assert dist(walker.pos, (16.5, 16.5)) < 0.15 and not walker.orders, "it walked straight on under the flyer"
    world.reveal_all(0)
    over = world.spawn_unit(0, UnitType.FLYING_MACHINE, (21.0, 21.0))
    assert world.can_place(BuildingType.FARM, (20, 20), 0) is None, over.pos


def test_flyers_keep_their_elbow_room_from_each_other() -> None:
    world = grass()
    flyers = [world.spawn_unit(0, UnitType.FLYING_MACHINE, (15.5, 15.5)) for _ in range(3)]
    run(world, 6.0)
    worst = min(dist(a.pos, b.pos) - a.radius - b.radius for a in flyers for b in flyers if a.id < b.id)
    assert worst > -0.05, f"still stacked: {worst:.2f}"


def test_flyers_sent_to_one_point_all_arrive() -> None:
    """A point holds one flyer: the rest stop as near as the ones already hovering there let them, and their order ends."""
    world = grass()
    flyers = [world.spawn_unit(0, UnitType.FLYING_MACHINE, (4.5 + i, 4.5)) for i in range(4)]
    world.move([u.id for u in flyers], (25.5, 20.5))
    run(world, 15.0)
    assert not any(u.orders for u in flyers), [(u.pos, list(u.orders)) for u in flyers]
    assert all(dist(u.pos, (25.5, 20.5)) < 2.0 for u in flyers)


@pytest.mark.parametrize("lake", [False, True])
def test_a_flyer_ordered_with_a_mixed_group_goes_with_it_and_takes_no_place_in_its_line(lake) -> None:
    """It keeps the group's pace while the group holds together, marches in no line, and flies straight where the
    walkers go round: over open ground it is never far ahead of them, over a lake it waits for them at the end."""
    world = grass(60, 30, water=[(30, y) for y in range(8, 22)] if lake else ())
    footmen = [world.spawn_unit(0, UnitType.FOOTMAN, (8.5 + i % 3, 14.5 + i // 3)) for i in range(6)]
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (9.5, 13.5))
    world.move([u.id for u in footmen] + [flyer.id], (50.5, 15.5))
    order = flyer.order
    assert isinstance(order, Move) and order.offset is None, "a flyer marches in no line"
    assert all(isinstance(u.order, Move) and u.order.offset is not None for u in footmen)
    lead = 0.0
    for _ in range(round(40.0 / SIM_DT)):
        world.step()
        lead = max(lead, flyer.x - max(u.x for u in footmen))
    assert not flyer.orders and dist(flyer.pos, (50.5, 15.5)) < 1.5
    assert not any(u.orders for u in footmen), "the walkers got there too"
    if not lake:
        assert lead < 3.0, f"it ran {lead:.1f} tiles ahead of the group it was sent with"


def test_a_flyer_sees_over_everything_as_far_as_its_sight_and_its_race_adds() -> None:
    world = grass(trees=[(x, y) for x in range(10, 30) for y in range(10, 20)])
    world.players[1].race = Race.ELF
    ours = world.spawn_unit(0, UnitType.FLYING_MACHINE, (20.5, 15.5))
    theirs = world.spawn_unit(1, UnitType.FLYING_MACHINE, (20.5, 5.5))
    world.update_vision()
    assert ours.info.sight == 9 and theirs.info.sight == 11
    assert world.is_visible(0, (29, 15)) and not world.is_visible(0, (31, 15))
    assert world.is_visible(1, (20, 16))


# -- Who can hit it -------------------------------------------------------------------


def duel(attacker: UnitType, *, target: UnitType = UnitType.FLYING_MACHINE, gap: float = 1.5):
    world = grass()
    ours = world.spawn_unit(0, attacker, (10.5, 10.5))
    theirs = world.spawn_unit(1, target, (10.5 + gap, 10.5))
    world.hold([theirs.id])
    world.update_vision()
    return world, ours, theirs


@pytest.mark.parametrize("striker, reaches", [
    (UnitType.ARCHER, True), (UnitType.CLERIC, True), (UnitType.FOOTMAN, False), (UnitType.KNIGHT, False),
    (UnitType.PEASANT, False), (UnitType.CATAPULT, False),
])
def test_only_a_shot_reaches_a_flyer_left_to_itself(striker, reaches) -> None:
    """Left to themselves, shooters (and a healer's bolt) take a flyer in reach on; melee and a siege crew leave it be."""
    world, ours, flyer = duel(striker, gap=2.5 if striker is not UnitType.CATAPULT else 4.0)
    run(world, 4.0)
    assert (flyer.hp < flyer.max_hp) == reaches, (striker, flyer.hp)
    assert world.can_strike(ours, flyer) == reaches
    if not reaches:
        assert not any(isinstance(o, Attack) for o in ours.orders), list(ours.orders)


def test_a_tower_shoots_a_flyer() -> None:
    world = grass()
    tower = world.place_building(1, BuildingType.TOWER, (10, 10))
    world.reveal_all(1)
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (13.5, 11.5))
    world.hold([flyer.id])
    run(world, 3.0)
    assert flyer.hp < flyer.max_hp and world.can_strike(tower, flyer)


def test_melee_ordered_at_a_flyer_is_refused_and_a_mixed_group_sends_its_shooters() -> None:
    world, footman, flyer = duel(UnitType.FOOTMAN)
    archer = world.spawn_unit(0, UnitType.ARCHER, (9.5, 12.5))
    with pytest.raises(RuleError, match="Only shooters and towers can hit a Flying Machine"):
        world.attack([footman.id], flyer.id)
    assert not footman.orders
    with pytest.raises(RuleError, match="Only shooters"):
        world.smart([footman.id], flyer.pos, target_id=flyer.id)
    world.attack([footman.id, archer.id], flyer.id)
    assert isinstance(archer.order, Attack) and archer.order.target == flyer.id
    assert isinstance(footman.order, Move), "melee follows the fight it cannot strike in"


def test_a_recruit_sent_to_a_rally_point_under_a_rival_flyer_walks_to_the_ground_beneath_it() -> None:
    """A barracks' rally point with a rival flyer hovering over it: the footman trained there is delivered by the
    context order at the point, which once ordered an attack on the flyer, was refused, and raised out of the step
    (seen by the WB-062 race games).  To a unit that cannot strike it, a flyer over a point is the ground under it."""
    world = grass()
    world.players[0].gold = world.players[0].lumber = 5000
    world.place_building(0, BuildingType.TOWN_HALL, (1, 12))  # room for the recruits
    barracks = world.place_building(0, BuildingType.BARRACKS, (4, 4))
    rally = (14.5, 6.5)
    world.set_rally(barracks.id, rally)
    flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, rally)
    world.update_vision()
    assert world.smart([world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 9.5)).id], rally) == "move"
    world.train(barracks.id, UnitType.FOOTMAN)
    run(world, world.unit_info(0, UnitType.FOOTMAN).build_time + 6.0)  # trained, delivered and walked there: no RuleError
    recruits = [u for u in world.units.values() if u.player == 0 and u.type is UnitType.FOOTMAN]
    assert len(recruits) == 2 and min(dist(u.pos, rally) for u in recruits) < 1.5
    assert flyer.hp == flyer.max_hp


def test_a_flying_machine_has_no_weapon_to_order_and_sent_at_an_enemy_it_goes_and_looks() -> None:
    world, flyer, footman = duel(UnitType.FLYING_MACHINE, target=UnitType.FOOTMAN)
    with pytest.raises(RuleError, match="has no weapon"):
        world.attack([flyer.id], footman.id)
    assert world.smart([flyer.id], (20.5, 20.5), target_id=footman.id) == "move"
    world.attack_move([flyer.id], (25.5, 10.5))  # through the footman: no fight to pick
    run(world, 5.0)
    assert footman.hp == footman.max_hp and dist(flyer.pos, (25.5, 10.5)) < 0.2


def test_a_melee_unit_with_a_flyer_for_a_target_drops_it_rather_than_standing_under_it() -> None:
    """However the order came to be (here it is put straight on, as a staged state), a blow that cannot reach is no
    order to keep: the footman lets it go, and does not take it up again on its own."""
    world, footman, flyer = duel(UnitType.FOOTMAN)
    footman.orders.append(Attack(flyer.id, auto=True))
    run(world, 2.0)
    assert not any(isinstance(o, Attack) for o in footman.orders) and flyer.hp == flyer.max_hp


def test_a_stone_and_a_slam_pass_beneath_a_flyer() -> None:
    world = grass()
    crew = world.spawn_unit(0, UnitType.CATAPULT, (5.5, 10.5))
    victim = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 10.5))
    overhead = world.spawn_unit(1, UnitType.FLYING_MACHINE, (11.5, 10.5))
    world.hold([victim.id, overhead.id])
    world.update_vision()
    world.attack([crew.id], victim.id)
    for _ in range(round(8.0 / SIM_DT)):
        world.step()
        if victim.hp < victim.max_hp:
            break
    run(world, 0.5)
    assert victim.hp < victim.max_hp, "the stone came down"
    assert overhead.hp == overhead.max_hp, "on the ground, not on the flyer over it"
    golem = world.spawn_unit(world.neutral, UnitType.GOLEM, (20.5, 20.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (21.5, 20.5))
    ours_overhead = world.spawn_unit(0, UnitType.FLYING_MACHINE, (21.5, 20.5))
    world.hold([footman.id, ours_overhead.id])
    golem.orders.append(Attack(footman.id))
    for _ in range(round(6.0 / SIM_DT)):
        world.step()
        if footman.hp < footman.max_hp:
            break
    assert footman.hp < footman.max_hp and ours_overhead.hp == ours_overhead.max_hp


def test_a_camp_does_not_rouse_for_a_flyer_overhead() -> None:
    world = grass()
    camp = camps.place(world, (18, 12), [UnitType.WOLF, UnitType.WOLF, UnitType.SPIDER], 500)
    lair = world.buildings[camp.lair]
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (lair.center[0], lair.center[1] - CAMP_WATCH + 1.0))
    world.hold([flyer.id])
    run(world, 2.0)
    assert not camp.roused and flyer.hp == flyer.max_hp
    assert not any(isinstance(g.order, Attack) for g in camps.guards(world, camp))


def test_a_healer_mends_the_living_and_never_a_machine() -> None:
    world = grass()
    cleric = world.spawn_unit(0, UnitType.CLERIC, (10.5, 10.5))
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (11.5, 10.5))
    flyer.hp = 20
    run(world, 4.0)
    assert flyer.hp == 20 and not flyer.info.living
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 11.5))
    footman.hp = 20
    run(world, 4.0)
    assert footman.hp > 20


# -- What is kept and what is sent ----------------------------------------------------


def test_a_save_of_a_flyer_in_flight_plays_on_to_the_bit() -> None:
    world = walled_off()
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (5.5, 5.5))
    world.spawn_unit(1, UnitType.ARCHER, (24.5, 9.5))
    world.move([flyer.id], (34.5, 12.5))
    run(world, 2.0)
    copy = World.from_dict(json.loads(json.dumps(world.to_dict())))
    run(world, 4.0)
    run(copy, 4.0)
    assert json.dumps(world.to_dict(), sort_keys=True) == json.dumps(copy.to_dict(), sort_keys=True)


def test_a_seat_that_sees_an_enemy_flyer_is_sent_it_and_one_that_does_not_is_not() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, tile_center((hall.x + 2, hall.y + 5)))
    for _ in range(8):
        match.step()
    seen = json.loads(json.dumps(match.snapshot(0)))
    assert any(u["id"] == flyer.id and u["type"] == "flying_machine" for u in seen["world"]["units"])
    world.units[flyer.id].x, world.units[flyer.id].y = world.width - 1.5, 1.5
    for _ in range(8):
        match.step()
    unseen = json.loads(json.dumps(match.snapshot(0)))
    assert (flyer.id in {u["id"] for u in unseen["world"]["units"]}) == world.is_visible(0, world.units[flyer.id].tile)


# -- Brains ---------------------------------------------------------------------------


def test_a_brain_answers_a_flyer_over_its_ground_with_shooters_and_never_with_melee() -> None:
    world = grass()
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    archers = [world.spawn_unit(0, UnitType.ARCHER, (9.5 + i, 12.5)) for i in range(2)]
    footmen = [world.spawn_unit(0, UnitType.FOOTMAN, (9.5 + i, 13.5)) for i in range(2)]
    flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, (8.5, 7.5))
    world.update_vision()
    answer_flyers(world, 0, archers + footmen, 9.0)
    assert all(isinstance(u.order, AttackMove) for u in archers)
    assert not any(u.orders for u in footmen)
    run(world, 6.0)
    assert flyer.hp < flyer.max_hp
