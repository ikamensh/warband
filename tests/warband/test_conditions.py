"""Timed conditions (WB-062): Rage and Bleeding, rows of buffs.toml a unit carries for a while.

Laying on a kind a unit already carries restarts it, never stacks it; a living kind never lands on a machine; buildings
never carry one.  Rage is the orcs' passive: a soldier below half health is enraged, and stays so for the whole ten
seconds after a Shaman mends it.  Bleeding is what an archer's wounding shot opens: a point a second through armour and a
fifth slower, until it runs out or a healer's cast staunches it, never on heavy armour, and a death by it is the
shooter's side's kill.
"""

import json
import math
import random

from warband.online.authority import WarbandMatch
from warband.sim.races import RACES
from warband.sim.model import STEPS_A_SECOND, Hold, Unit, World, tile_center
from warband.sim.rules import (BLEEDING, BLOODLUST_RAGE, BUFFS, RAGE, SIM_DT, ArmorClass, BuffInfo, BuildingType, Race, Terrain,
                                UnitType, Upgrade)


def field(races: tuple[Race, ...] = (Race.HUMAN, Race.HUMAN)) -> World:
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], len(races), rng=random.Random(4), races=races)
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 16))
    for player in world.players[:world.seats]:
        world.reveal_all(player.id)
    return world


def step(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def wound(world: World, victim: Unit) -> Unit:
    """One of seat 0's archers puts a single arrow into *victim* and falls at once (a staged state: nothing else of
    seat 0's is left to strike it), so what follows is the wound alone."""
    archer = world.spawn_unit(0, UnitType.ARCHER, (victim.x - 3.0, victim.y))
    world.attack([archer.id], victim.id)
    hp = victim.hp
    for _ in range(int(round(3.0 / SIM_DT))):
        world.step()
        if victim.hp < hp:
            archer.hp = 0
            world.step()
            return archer
    raise AssertionError("the arrow never landed")


def held(world: World, player: int, unit_type: UnitType, point: tuple[float, float]) -> Unit:
    unit = world.spawn_unit(player, unit_type, point)
    world.hold([unit.id])
    return unit


# -- Bleeding -------------------------------------------------------------------------------------------------------
#
# The victims are archers: light armour takes the wound, and heavy armour never does (test_heavy_armour_is_never_bled).


def test_an_archers_wound_drains_a_point_a_second_through_armour_for_five_seconds() -> None:
    world = field()
    world.players[1].upgrades |= {Upgrade.ARMOR_1, Upgrade.ARMOR_2}  # staged: two points of armour on a light shooter
    victim = held(world, 1, UnitType.ARCHER, (10.5, 10.5))
    assert world.armor_of(victim) == 2
    wound(world, victim)
    assert victim.condition(BLEEDING) is not None
    hp = victim.hp
    step(world, BLEEDING.duration + 1.0)
    assert hp - victim.hp == int(-BLEEDING.hp_per_second * BLEEDING.duration) == 5
    assert victim.conditions == []


def test_heavy_armour_is_never_bled() -> None:
    """Heavy armour turns the barb (buffs.toml's ``spares``): a footman and a knight take the arrow and never bleed."""
    world = field()
    for kind in (UnitType.FOOTMAN, UnitType.KNIGHT):
        target = held(world, 1, kind, (10.5, 4.5 + 6 * (kind is UnitType.KNIGHT)))
        wound(world, target)
        assert target.hp < target.max_hp and target.conditions == [], kind


def test_a_bleeding_unit_walks_a_fifth_slower_until_the_wound_closes() -> None:
    world = field()
    wounded, whole = held(world, 1, UnitType.ARCHER, (10.5, 10.5)), held(world, 1, UnitType.ARCHER, (10.5, 14.5))
    wound(world, wounded)
    assert world.speed_of(wounded) == world.speed_of(whole) * BLEEDING.speed == world.speed_of(whole) * 0.8
    starts = wounded.x, whole.x
    world.move([wounded.id], (25.5, 10.5))
    world.move([whole.id], (25.5, 14.5))
    step(world, 2.0)
    walked = wounded.x - starts[0], whole.x - starts[1]
    assert abs(walked[0] - BLEEDING.speed * walked[1]) < 0.05, walked
    step(world, BLEEDING.duration)
    assert world.speed_of(wounded) == world.speed_of(whole)


#: A kind that slows, staged, so that the pace is held to what a slow does however the wound is tuned.
MIRED = BuffInfo(key="mired", name="Mired", summary="", speed=0.5, duration=5.0, ticks=100)


def test_a_slow_holds_back_its_bearer_and_never_the_march_it_is_ordered_on() -> None:
    """A group walks at the pace of its slowest member as listed, conditions left out: a slowed rider ordered off with
    its troop falls behind, and the troop keeps its pace.  It used to take the slowed one's pace for the whole order,
    long after the condition had worn off (an army crawling for one scratch)."""
    world = field()
    troop = [held(world, 1, UnitType.KNIGHT, (4.5, 7.5 + 2 * i)) for i in range(3)]
    world._lay(troop[0], MIRED, 0)  # staged: private, a slow of its own that no rule lays
    world.move([u.id for u in troop], (26.5, 9.5))
    step(world, 0.6)  # turned and under way
    starts = [u.pos for u in troop]
    step(world, 1.0)
    walked = [math.dist(u.pos, start) for u, start in zip(troop, starts)]
    listed = world.listed_speed(troop[1])
    assert world.speed_of(troop[0]) == MIRED.speed * listed
    assert all(abs(w - listed) < 0.15 for w in walked[1:]), (walked, listed)
    assert abs(walked[0] - MIRED.speed * listed) < 0.1, (walked, listed)


def test_a_bleeding_archer_marching_with_footmen_walks_at_their_pace_slowed() -> None:
    """The group's pace is its slowest member's listed speed, and each member walks it at its own condition's rate: a
    bleeding archer among footmen walks a fifth slower than they do, not at its own bled speed, which is faster."""
    world = field()
    footmen = [held(world, 1, UnitType.FOOTMAN, (4.5, 5.5 + 2 * i)) for i in range(2)]
    archer = held(world, 1, UnitType.ARCHER, (4.5, 9.5))
    wound(world, archer)
    pace = world.listed_speed(footmen[0])
    assert world.speed_of(archer) > BLEEDING.speed * pace  # alone, bled, it would walk faster than that
    world.move([u.id for u in (*footmen, archer)], (26.5, 7.5))
    step(world, 0.6)  # turned and under way
    starts = [u.pos for u in (*footmen, archer)]
    step(world, 1.0)
    walked = [math.dist(u.pos, start) for u, start in zip((*footmen, archer), starts)]
    assert archer.condition(BLEEDING) is not None
    assert all(abs(w - pace) < 0.15 for w in walked[:2]), (walked, pace)
    assert abs(walked[2] - BLEEDING.speed * pace) < 0.1, (walked, pace)


def test_a_wound_opened_again_and_again_still_bleeds_a_point_a_second() -> None:
    """Arrows landing faster than the drain's second renew the wound without restarting its count: the drain is
    counted from the steps it has been worn, so it takes its point every second however often it is opened again."""
    world = field()
    victim = held(world, 1, UnitType.ARCHER, (12.5, 10.5))
    victim.hp = 10_000  # staged: it outlasts the volley
    archers = [world.spawn_unit(0, UnitType.ARCHER, (9.5, 8.5 + 1.5 * i)) for i in range(4)]
    for archer in archers:
        archer.hp = 10_000  # and so do they, shot back at
    world.attack([a.id for a in archers], victim.id)
    while victim.condition(BLEEDING) is None:
        world.step()
    world.take_events()
    hp, seconds, hits, struck = victim.hp, 6, 0, 0
    for _ in range(seconds * STEPS_A_SECOND):
        world.step()
        landed = [e for e in world.take_events() if e.kind == "hit" and e.other == victim.id]
        hits += len(landed)
        struck += sum(e.amount for e in landed)
    assert hits >= 2 * seconds  # opened again more often than it drains
    assert hp - victim.hp - struck == seconds * int(-BLEEDING.hp_per_second)


def test_a_bleeding_unit_felled_by_a_blow_is_counted_once() -> None:
    """A killing blow and the wound's drain can land on the same step.  The dead are buried at the end of the step,
    and the felled unit's own update, after its killer's, drained it again and counted the kill a second time.  Each
    of a second's twenty steps is tried as the one the drain lands on, so one of them is the blow's."""
    felled = set()
    for phase in range(STEPS_A_SECOND):
        world = field()
        knight = world.spawn_unit(0, UnitType.KNIGHT, (9.4, 10.5))  # before its victim: first to act in each step
        victim = held(world, 1, UnitType.ARCHER, (10.6, 10.5))
        world._lay(victim, BLEEDING, 0)  # staged: seat 0's wound, without an archer of seat 0's that could strike too
        cut = victim.condition(BLEEDING)
        assert cut is not None
        cut.worn = phase  # the drain lands STEPS_A_SECOND - phase steps from now
        victim.hp = 3  # a drain from two points, a blow from death
        world.attack([knight.id], victim.id)
        for steps in range(1, STEPS_A_SECOND + 1):
            world.step()
            if victim.id not in world.units:
                assert any(e.kind == "hit" and e.entity == knight.id and e.other == victim.id for e in world.take_events())
                felled.add(steps)
                break
        stats = world.players[0].stats
        assert (stats["units_killed"], stats["destroyed_value"]) == (1, victim.info.cost.gold + victim.info.cost.lumber), phase
    assert len(felled) == 1  # the same blow in every run, within the second: one of the phases is its step


def test_a_second_wound_restarts_the_bleeding_and_never_doubles_it() -> None:
    world = field()
    victim = held(world, 1, UnitType.ARCHER, (10.5, 10.5))
    archers = [world.spawn_unit(0, UnitType.ARCHER, (7.5, 9.5 + 2 * i)) for i in range(2)]
    world.attack([a.id for a in archers], victim.id)
    hits = 0
    for _ in range(int(round(6.0 / SIM_DT))):
        world.step()
        hits += sum(1 for e in world.take_events() if e.kind == "hit" and e.other == victim.id)
        assert len(victim.conditions) <= 1
        if hits >= 3:
            break
    assert hits >= 3
    wound = victim.condition(BLEEDING)
    assert wound is not None and world.seconds_left(wound) == BLEEDING.duration  # from the last arrow
    for archer in archers:
        archer.hp = 0
    while world.projectiles:  # the arrows already loosed still land
        world.step()
    hp = victim.hp
    step(world, 2.0)
    assert hp - victim.hp == int(-BLEEDING.hp_per_second * 2.0) == 2  # at its own rate, however many arrows opened it


def test_a_heal_staunches_the_bleeding() -> None:
    world = field()
    victim = held(world, 1, UnitType.ARCHER, (10.5, 10.5))
    wound(world, victim)
    assert victim.condition(BLEEDING) is not None
    world.spawn_unit(1, UnitType.CLERIC, (12.5, 10.5))
    step(world, 1.5)
    assert any(e.kind == "heal" and e.other == victim.id for e in world.take_events())
    assert victim.condition(BLEEDING) is None


def test_a_death_by_bleeding_is_the_shooters_sides_kill() -> None:
    world = field()
    victim = held(world, 1, UnitType.ARCHER, (10.5, 10.5))
    wound(world, victim)
    victim.hp = 2  # staged: the arrow left it two points from death
    kills = world.players[0].stats["units_killed"]
    step(world, 3.0)
    assert victim.id not in world.units
    assert world.players[0].stats["units_killed"] == kills + 1


def test_machines_neither_bleed_nor_rage_nor_are_healed() -> None:
    world = field((Race.HUMAN, Race.ORC))
    catapult = held(world, 1, UnitType.CATAPULT, (10.5, 10.5))
    wound(world, catapult)
    assert catapult.conditions == []
    golem = world.spawn_unit(world.neutral, UnitType.GOLEM, (10.5, 4.5))
    wound(world, golem)
    assert golem.conditions == []
    catapult.hp = catapult.max_hp // 3
    step(world, 0.5)
    assert catapult.conditions == []  # an orc engine is below half, and still no rage
    world.spawn_unit(1, UnitType.CLERIC, (12.5, 10.5))
    hp = catapult.hp
    step(world, 4.0)
    assert catapult.hp == hp
    assert not any(e.kind == "heal" for e in world.take_events())


def test_an_arrow_lands_on_a_flying_machine_and_opens_no_wound() -> None:
    """A flyer is hit by shots (WB-064), and a flying machine is a machine: the archer's arrow hurts it and it never
    bleeds."""
    world = field()
    flyer = held(world, 1, UnitType.FLYING_MACHINE, (10.5, 10.5))
    wound(world, flyer)
    assert flyer.hp < flyer.max_hp and flyer.conditions == []


def test_towers_and_clerics_open_no_wound_and_buildings_never_bleed() -> None:
    world = field()
    world.place_building(0, BuildingType.TOWER, (8, 9))
    cleric = world.spawn_unit(0, UnitType.CLERIC, (13.5, 13.5))
    target, struck = held(world, 1, UnitType.ARCHER, (12.5, 10.5)), held(world, 1, UnitType.ARCHER, (15.5, 13.5))
    world.attack([cleric.id], struck.id)
    step(world, 4.0)
    assert target.hp < target.max_hp and struck.hp < struck.max_hp
    assert target.conditions == [] and struck.conditions == []
    farm = world.place_building(1, BuildingType.FARM, (20, 4))
    archer = world.spawn_unit(0, UnitType.ARCHER, (18.5, 3.5))
    world.attack([archer.id], farm.id)
    hits = 0
    for _ in range(int(round(6.0 / SIM_DT))):
        hp = farm.hp
        world.step()
        struck_now = [e for e in world.take_events() if e.kind == "hit" and e.other == farm.id]
        hits += len(struck_now)
        assert farm.hp == hp - sum(e.amount for e in struck_now)  # nothing between the arrows
    assert hits >= 2


# -- Rage -----------------------------------------------------------------------------------------------------------


def test_rage_holds_while_below_half_and_outlasts_a_heal_by_its_ten_seconds() -> None:
    world = field((Race.ORC, Race.HUMAN))
    grunt = held(world, 0, UnitType.FOOTMAN, (10.5, 10.5))
    calm = world.damage_of(grunt)
    grunt.hp = grunt.max_hp // 2 - 1  # staged: wounded below half
    step(world, 15.0)
    rage = grunt.condition(RAGE)
    assert rage is not None and world.seconds_left(rage) == RAGE.duration  # renewed every step it stays below half
    assert world.damage_of(grunt) == int(round(calm * RAGE.damage)) == int(round(calm * 1.25))
    world.spawn_unit(0, UnitType.CLERIC, (12.5, 10.5))
    for _ in range(int(round(5.0 / SIM_DT))):
        world.step()
        if grunt.hp * 2 >= grunt.max_hp:
            break
    mended = world.time
    assert grunt.hp * 2 >= grunt.max_hp
    while grunt.condition(RAGE) is not None:
        assert world.damage_of(grunt) > calm
        world.step()
    assert abs(world.time - mended - RAGE.duration) <= 2 * SIM_DT
    assert world.damage_of(grunt) == calm


def test_bloodlust_doubles_rage_in_its_place() -> None:
    world = field((Race.ORC, Race.HUMAN))
    grunt, peon = held(world, 0, UnitType.FOOTMAN, (10.5, 10.5)), world.spawn_unit(0, UnitType.PEASANT, (12.5, 12.5))
    footman = held(world, 1, UnitType.FOOTMAN, (14.5, 14.5))
    calm = world.damage_of(grunt)
    grunt.hp, peon.hp, footman.hp = grunt.max_hp // 2 - 1, 1, 1  # staged wounds
    world.step()
    assert grunt.condition(RAGE) is not None and peon.conditions == [] and footman.conditions == []
    world.players[0].upgrades.add(Upgrade.BLOODLUST)
    world.step()
    assert [c.kind for c in grunt.conditions] == [BLOODLUST_RAGE]
    assert world.damage_of(grunt) == int(round(calm * 1.5))


# -- Saves and snapshots --------------------------------------------------------------------------------------------


def test_conditions_ride_a_save_to_the_bit() -> None:
    world = field((Race.ORC, Race.HUMAN))
    grunt = held(world, 0, UnitType.FOOTMAN, (10.5, 10.5))
    shooter = held(world, 1, UnitType.ARCHER, (12.5, 13.5))
    grunt.hp = grunt.max_hp // 2 - 1
    wound(world, shooter)
    assert grunt.conditions and shooter.conditions
    saved = json.loads(json.dumps(world.to_dict()))
    loaded = World.from_dict(saved)
    assert loaded.to_dict() == world.to_dict()
    for _ in range(int(round(BLEEDING.duration / 2 / SIM_DT))):
        world.step()
        loaded.step()
    assert loaded.to_dict() == world.to_dict()
    assert loaded.units[shooter.id].condition(BLEEDING) is not None


def test_a_seat_sees_the_conditions_of_a_rival_unit_in_its_sight() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    near = tile_center((hall.x + hall.size + 2, hall.y + 1))
    rival = world.spawn_unit(1, UnitType.ARCHER, near)
    rival.orders.append(Hold())  # staged: it stands where seat 0 sees it
    world.update_vision()
    wound(world, rival)
    match.step()
    seen = next(u for u in match.snapshot(0)["world"]["units"] if u["id"] == rival.id)
    assert [c["kind"] for c in seen["conditions"]] == ["bleeding"]
    assert set(BUFFS) >= {c["kind"] for c in seen["conditions"]}


def test_the_words_say_the_numbers() -> None:
    """The orcs' passive, Bloodlust's card and each condition's own tooltip promise numbers in words: a number moved
    in buffs.toml without its words is a card that lies."""
    assert f"+{round((RAGE.damage - 1) * 100)} % damage" in RACES[Race.ORC].passive
    assert f"{RAGE.duration:g} s" in RACES[Race.ORC].passive
    assert f"+{round((BLOODLUST_RAGE.damage - 1) * 100)} % damage" in RACES[Race.ORC].upgrades[Upgrade.BLOODLUST].summary
    assert f"+{round((BLOODLUST_RAGE.damage - 1) * 100)} % damage" in BLOODLUST_RAGE.summary
    assert f"+{round((RAGE.damage - 1) * 100)} % damage" in RAGE.summary
    assert (BLEEDING.hp_per_second, BLEEDING.speed, BLEEDING.spares) == (-1.0, 0.8, frozenset({ArmorClass.HEAVY}))
    assert all(words in BLEEDING.summary for words in ("a hit point a second", "a fifth slower", "heavy armour is not bled"))
