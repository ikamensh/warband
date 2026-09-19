"""A blow takes time: pivot to the target, wind up, land it; shots fly before they land."""

import math
import random

import pytest

from warband.sim.model import Attack, World, dist
from warband.sim.rules import DIRECT_HIT, SIM_DT, SPLASH_FRACTION, UNITS, WINDUP_SLACK, BuildingType, Terrain, UnitType


def flat_world(width: int = 24, height: int = 20) -> World:
    return World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 2, rng=random.Random(1))


def first_hit(world: World, striker_id: int, max_seconds: float = 10.0) -> float:
    """Simulation time of the first blow *striker_id* lands."""
    for _ in range(int(round(max_seconds / SIM_DT))):
        world.step()
        if any(e.kind == "hit" and e.entity == striker_id for e in world.take_events()):
            return world.time
    raise AssertionError(f"no blow within {max_seconds}s")


def test_a_blow_takes_a_turn_and_a_wind_up_before_it_lands() -> None:
    """A footman facing away from a foe pivots to it, then draws back before the first cut; a facing
    footman needs only the wind-up.  The turn is at the unit's rate, so it is visible on screen."""
    info = UNITS[UnitType.FOOTMAN]
    world = flat_world()
    away = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))  # faces +y, the foe is at +x: a quarter turn
    faced = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 12.5))
    faced.facing = 0.0
    for ours, foe_at in ((away, (6.4, 5.5)), (faced, (6.4, 12.5))):
        foe = world.spawn_unit(1, UnitType.FOOTMAN, foe_at)
        world.hold([foe.id])
        world.attack([ours.id], foe.id)
    world.update_vision()
    world.step()
    assert 0.0 < away.facing < math.pi / 2  # part way round after one step, not snapped
    assert first_hit(world, faced.id) == pytest.approx(SIM_DT + info.windup, abs=SIM_DT / 2)  # decided on the first step
    world = flat_world()
    away = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    foe = world.spawn_unit(1, UnitType.FOOTMAN, (6.4, 5.5))
    world.hold([foe.id])
    world.attack([away.id], foe.id)
    assert first_hit(world, away.id) == pytest.approx(SIM_DT + (math.pi / 2) / info.turn + info.windup, abs=2 * SIM_DT)


def test_blows_repeat_every_wind_up_plus_cooldown() -> None:
    world = flat_world()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    ours.facing = 0.0
    foe = world.spawn_unit(1, UnitType.KNIGHT, (6.4, 5.5))
    world.hold([foe.id])
    world.attack([ours.id], foe.id)
    times = [first_hit(world, ours.id) for _ in range(3)]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(gap == pytest.approx(ours.info.period, abs=SIM_DT) for gap in gaps), gaps


def test_a_wind_up_is_committed_and_a_target_that_gets_clear_is_missed() -> None:
    """Once the sword is drawn back the footman swings: a target still within reach plus a little slack
    is struck, one that got clear faster than the footman follows is not, and the swing costs the
    cooldown either way."""
    info = UNITS[UnitType.FOOTMAN]
    world = flat_world()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    ours.facing = 0.0
    foe = world.spawn_unit(1, UnitType.SCOUT, (6.4, 5.5))
    world.hold([foe.id])
    world.attack([ours.id], foe.id)
    world.update_vision()
    world.step()
    assert ours.windup > 0 and ours.state == "attack"
    reach = ours.radius + foe.radius + info.range  # centre to centre, when the swords just touch
    foe.x = ours.x + reach + WINDUP_SLACK + info.speed * info.windup + 0.3  # gone beyond what the run and the slack cover
    for _ in range(int(info.windup / SIM_DT) + 1):
        world.step()
    assert ours.windup == 0 and ours.cooldown > 0 and foe.hp == foe.max_hp
    assert not any(e.kind == "hit" for e in world.take_events())
    ours.cooldown = 0.0
    foe.x, foe.y = 6.4, 5.5
    while ours.windup == 0:
        world.step()
    foe.x = ours.x + reach + WINDUP_SLACK - 0.1  # within the slack: struck without a step
    for _ in range(int(info.windup / SIM_DT) + 1):
        world.step()
    assert foe.hp < foe.max_hp


def test_a_new_order_breaks_off_a_wind_up() -> None:
    world = flat_world()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    ours.facing = 0.0
    foe = world.spawn_unit(1, UnitType.FOOTMAN, (6.4, 5.5))
    world.hold([foe.id])
    world.attack([ours.id], foe.id)
    world.update_vision()
    world.step()
    assert ours.windup > 0
    world.move([ours.id], (2.5, 5.5))
    world.step()
    assert ours.windup == 0 and ours.state == "move"
    for _ in range(20):
        world.step()
    assert foe.hp == foe.max_hp


def test_a_melee_unit_swings_on_the_run_and_catches_a_target_walking_away() -> None:
    """A knight after a fleeing peasant lands its blows: the wind-up does not root it while the peasant walks on."""
    world = flat_world(40, 10)
    knight = world.spawn_unit(0, UnitType.KNIGHT, (3.5, 5.5))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (4.5, 5.5))
    world.move([peasant.id], (38.5, 5.5))
    world.attack([knight.id], peasant.id)
    assert first_hit(world, knight.id) < 2.0
    assert first_hit(world, knight.id) < 4.0  # and keeps landing them while the peasant runs


def test_a_unit_on_hold_turns_winds_up_and_strikes_what_comes_in_reach() -> None:
    world = flat_world()
    ours = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    world.hold([ours.id])
    foe = world.spawn_unit(1, UnitType.PEASANT, (6.4, 5.5))
    world.hold([foe.id])
    world.update_vision()
    assert first_hit(world, ours.id) < 1.0
    assert ours.facing == pytest.approx(0.0, abs=0.01)
    assert dist(ours.pos, (5.5, 5.5)) < 0.01 and not isinstance(ours.order, Attack)  # held its ground


# -- Shots ---------------------------------------------------------------------------


def run(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def test_an_arrow_flies_before_it_strikes_and_a_tower_shoots_the_same_way() -> None:
    """The blow of a shot is dealt when the shot arrives, not when it is loosed; while it flies it is
    a projectile the view can draw."""
    world = flat_world()
    archer = world.spawn_unit(0, UnitType.ARCHER, (2.5, 2.5))
    archer.facing = 0.0
    victim = world.spawn_unit(1, UnitType.KNIGHT, (6.4, 2.5))
    world.hold([victim.id])
    world.attack([archer.id], victim.id)
    while not world.projectiles:
        world.step()
    arrow = next(iter(world.projectiles.values()))
    assert arrow.kind == "arrow" and arrow.target == victim.id and victim.hp == victim.max_hp
    assert arrow.flight == pytest.approx(dist(archer.pos, victim.pos) / 14, abs=0.05)
    while world.projectiles:
        world.step()
    assert victim.hp < victim.max_hp
    tower = world.place_building(1, BuildingType.TOWER, (8, 6))
    world.reveal_all(1)
    scout = world.spawn_unit(0, UnitType.SCOUT, (7.5, 4.5))
    world.hold([scout.id])
    world.step()
    shot = next(p for p in world.projectiles.values() if p.source == tower.id)
    assert shot.target == scout.id and scout.hp == scout.max_hp
    run(world, 1.0)
    assert scout.hp < scout.max_hp


def test_an_arrow_whose_mark_died_in_flight_lands_on_nothing() -> None:
    world = flat_world()
    archer = world.spawn_unit(0, UnitType.ARCHER, (2.5, 2.5))
    archer.facing = 0.0
    victim = world.spawn_unit(1, UnitType.PEASANT, (6.4, 2.5))
    world.hold([victim.id])
    world.attack([archer.id], victim.id)
    while not world.projectiles:
        world.step()
    victim.hp = 0
    world.take_events()
    run(world, 1.0)
    assert not world.projectiles and not any(e.kind == "hit" for e in world.take_events())


def siege_world(catapult_at=(3.5, 8.5)):
    world = flat_world(30, 20)
    catapult = world.spawn_unit(0, UnitType.CATAPULT, catapult_at)
    catapult.facing = 0.0
    return world, catapult


def test_a_stone_comes_down_where_it_was_aimed_and_a_target_that_moved_off_is_missed() -> None:
    """The stone is fired at the ground, so whoever stands there when it lands is hit: the target that
    stayed takes the full blow, a bystander a tile off a share, a target that walked clear nothing."""
    world, catapult = siege_world()
    stayer = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 8.5))
    bystander = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 9.4))
    world.hold([stayer.id, bystander.id])
    world.attack([catapult.id], stayer.id)
    while not world.projectiles:
        world.step()
    stone = next(iter(world.projectiles.values()))
    assert stone.kind == "stone" and stone.target is None and stone.aim == pytest.approx(stayer.pos)
    run(world, stone.flight + SIM_DT)
    assert not world.projectiles
    events = world.take_events()
    hits = {e.other: e.amount for e in events if e.kind == "hit"}
    assert hits[stayer.id] > hits[bystander.id]
    assert any(e.kind == "impact" and e.pos == stone.aim for e in events)
    world, catapult = siege_world()
    dodger = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 8.5))
    world.hold([dodger.id])
    world.attack([catapult.id], dodger.id)
    while not world.projectiles:
        world.step()
    stone = next(iter(world.projectiles.values()))
    world.move([dodger.id], (9.5, 14.5))  # steps out from under it
    run(world, stone.flight + SIM_DT)
    assert not world.projectiles and dodger.hp == dodger.max_hp


def test_a_stone_leads_a_marching_target_and_hits_it() -> None:
    """A unit walking across the field is aimed at where it will be when the stone comes down."""
    world, catapult = siege_world((3.5, 5.5))
    marcher = world.spawn_unit(1, UnitType.FOOTMAN, (9.5, 2.5))
    world.move([marcher.id], (9.5, 17.5))
    world.attack([catapult.id], marcher.id)
    while not world.projectiles:
        world.step()
    stone = next(iter(world.projectiles.values()))
    assert stone.aim[1] > marcher.y + 1.0  # ahead of it, down the road it walks
    run(world, stone.flight + SIM_DT)
    assert marcher.hp < marcher.max_hp


def test_a_stone_hurts_friend_and_foe_where_it_lands() -> None:
    world, catapult = siege_world()
    foe = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 8.5))
    friend = world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 9.4))
    world.hold([foe.id, friend.id])
    world.attack([catapult.id], foe.id)  # the player's own order: the crew fires, and the player answers for it
    while not world.projectiles:
        world.step()
    run(world, next(iter(world.projectiles.values())).flight + SIM_DT)
    assert foe.hp < foe.max_hp and friend.hp < friend.max_hp
    assert not isinstance(friend.order, Attack)  # hurt, but not turned on its own catapult


def test_a_crew_firing_on_its_own_judgement_keeps_stones_off_its_own_side() -> None:
    """A catapult that picked its target itself holds fire while friends stand where the stone would
    fall, and throws as soon as they are clear."""
    world, catapult = siege_world()
    foe = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 8.5))
    friend = world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 9.9))  # out of sword reach of the knight, inside the stone's splash
    world.hold([foe.id, friend.id])
    world.update_vision()
    run(world, 3.0)
    assert isinstance(catapult.order, Attack) and catapult.order.auto and not world.projectiles
    assert foe.hp == foe.max_hp and friend.hp == friend.max_hp
    world.move([friend.id], (9.5, 14.5))
    run(world, 4.0)
    assert foe.hp < foe.max_hp and friend.hp == friend.max_hp


def test_a_catapult_cannot_throw_inside_two_tiles_and_backs_away_to_get_range() -> None:
    world, catapult = siege_world((6.5, 8.5))
    foe = world.spawn_unit(1, UnitType.PEASANT, (8.0, 8.5))
    world.hold([foe.id])
    world.attack([catapult.id], foe.id)
    run(world, 1.0)
    assert foe.hp == foe.max_hp and catapult.x < 6.5  # wheeling back rather than throwing
    run(world, 4.0)
    assert foe.hp < foe.max_hp and dist(catapult.pos, foe.pos) - 2 * catapult.radius >= 2.0


def test_a_catapult_left_to_itself_ignores_what_stands_at_its_wheels_for_what_it_can_throw_at() -> None:
    world, catapult = siege_world((6.5, 8.5))
    close = world.spawn_unit(1, UnitType.PEASANT, (8.0, 8.5))
    far = world.spawn_unit(1, UnitType.PEASANT, (11.5, 8.5))
    world.hold([close.id, far.id])
    world.update_vision()
    run(world, 0.5)
    assert isinstance(catapult.order, Attack) and catapult.order.target == far.id


def test_shots_in_the_air_survive_a_save() -> None:
    world, catapult = siege_world()
    foe = world.spawn_unit(1, UnitType.KNIGHT, (9.5, 8.5))
    world.hold([foe.id])
    world.attack([catapult.id], foe.id)
    while not world.projectiles:
        world.step()
    stone = next(iter(world.projectiles.values()))
    copy = World.from_dict(world.to_dict())
    assert copy.projectiles[stone.id] == stone
    run(copy, stone.flight + SIM_DT)
    assert copy.units[foe.id].hp < foe.max_hp
