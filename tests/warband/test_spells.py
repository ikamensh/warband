"""The Mage Tower and the spells (WB-066): research by choice, the cast order, each spell's effect, and the records.

Three levels of magic are researched at the tower, each a choice of one spell of three that closes the other two for the
match.  A side casts from its store of aether at any point of the map, a spell on its own cooldown, both twice as dear
beyond every vault's reach.  A spell is a row of spells.toml: the conditions it lays, those it ends, its blow at
once or after a delay, and what it summons.  Saves, replays and the online snapshots carry all of it, and a rival's
research, aether and cooldowns stay that rival's.
"""

import json
import random

import pytest

from warband.online.authority import SPELL_EVENTS, WarbandMatch
from warband.records.replay import Playback, Replay, digest
from warband.sim.model import Move, RuleError, World, tile_center
from warband.sim.rules import (AETHER_REACH, AETHER_STORE, BLEEDING, BUFFS, SIM_DT, SPELL_FAR, SPELLS, UNITS, BuildingType, Difficulty, Race, Terrain,
                               UnitType, Upgrade)

HERE = (10.5, 10.5)  # within the reach of seat 0's vault
FAR = (34.5, 10.5)  # beyond it (the rest of the tests cast within it, round x = 20)


def field() -> World:
    """Open grass, 40 by 24: seat 0's hall, vault (on a rift), finished Mage Tower and 100 aether, seat 1's hall."""
    world = World(40, 24, [[Terrain.GRASS] * 40 for _ in range(24)], 2, rng=random.Random(4))
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.lay_rifts([(16, 4)])
    world.place_building(0, BuildingType.VAULT, (16, 4))  # its reach, ten tiles round (17, 5), holds the middle of the field
    world.place_building(0, BuildingType.MAGE_TOWER, (0, 5))
    world.place_building(1, BuildingType.TOWN_HALL, (36, 20))
    for player in world.players[:world.seats]:
        player.gold = player.lumber = 20_000
        world.reveal_all(player.id)
    world.players[0].aether = 100
    return world


def knowing(world: World, *spells: Upgrade) -> World:
    world.players[0].upgrades.update(spells)
    return world


def step(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def held(world: World, player: int, unit_type: UnitType, point: tuple[float, float]):
    unit = world.spawn_unit(player, unit_type, point)
    world.hold([unit.id])
    return unit


def tower(world: World):
    return world.player_buildings(0, BuildingType.MAGE_TOWER)[0]


# -- Research: one spell of three a level --------------------------------------------------------------------------------


def test_a_level_is_a_choice_of_one_spell_that_closes_the_other_two() -> None:
    world = field()
    mage = tower(world)
    assert world.can_research(mage, Upgrade.STONESKIN) == "Requires Keep and a level I spell"
    world.research(mage.id, Upgrade.HASTE)
    assert world.can_research(mage, Upgrade.MEND) == "Closed while Haste is being researched"
    world.cancel_research(mage.id)  # a cancel opens the level again
    assert world.can_research(mage, Upgrade.MEND) is None
    world.research(mage.id, Upgrade.MEND)
    step(world, world.upgrade_info(0, Upgrade.MEND).time + 0.1)
    assert Upgrade.MEND in world.players[0].upgrades
    for other in (Upgrade.HASTE, Upgrade.FLAME_STRIKE):
        assert world.can_research(mage, other) == "Closed: Mend was chosen"
        with pytest.raises(RuleError, match="Closed"):
            world.order_upgrade(0, other)  # a plan for it would wait for ever
    assert world.can_research(mage, Upgrade.STONESKIN) == "Requires Keep"
    world.players[0].upgrades.add(Upgrade.KEEP)
    assert world.can_research(mage, Upgrade.METEOR) == "Requires a level II spell"
    assert world.can_research(mage, Upgrade.WITHER) is None


def test_the_levels_are_priced_as_the_table_says() -> None:
    """300/100 in 25 s, 1000/400 in 90 s behind the Keep, 1600/600 in 120 s; 30, 60 and 120 aether cooling 20, 40 and 90
    seconds (WB-067)."""
    world = field()
    for spells, (gold, lumber, time, aether, cooldown) in (
            ((Upgrade.HASTE, Upgrade.MEND, Upgrade.FLAME_STRIKE), (300, 100, 25.0, 30, 20.0)),
            ((Upgrade.STONESKIN, Upgrade.ENTANGLE, Upgrade.WITHER), (1000, 400, 90.0, 60, 40.0)),
            ((Upgrade.METEOR, Upgrade.SUMMON, Upgrade.BATTLE_FURY), (1600, 600, 120.0, 120, 90.0))):
        for spell in spells:
            info = world.upgrade_info(0, spell)
            assert (info.cost.gold, info.cost.lumber, info.time) == (gold, lumber, time), spell
            assert (SPELLS[spell].aether, SPELLS[spell].cooldown * SIM_DT) == (aether, cooldown), spell
    assert Upgrade.KEEP in world.upgrade_info(0, Upgrade.WITHER).requires


# -- The cast ----------------------------------------------------------------------------------------------------------


def test_a_cast_pays_its_aether_and_starts_its_cooldown_in_whole_steps() -> None:
    world = knowing(field(), Upgrade.HASTE)
    world.cast(0, Upgrade.HASTE, HERE)
    assert world.players[0].aether == 70
    assert world.cooldown_left(0, Upgrade.HASTE) == SPELLS[Upgrade.HASTE].cooldown == 400
    with pytest.raises(RuleError, match="ready in 20 s"):
        world.cast(0, Upgrade.HASTE, HERE)
    step(world, 20.0)
    assert world.cooldown_left(0, Upgrade.HASTE) == 0
    world.cast(0, Upgrade.HASTE, HERE)


def test_beyond_every_vaults_reach_a_cast_costs_and_cools_twice_as_much() -> None:
    world = knowing(field(), Upgrade.HASTE)
    vault = world.vaults(0)[0]
    edge = (vault.center[0] + AETHER_REACH, vault.center[1])
    assert world.cast_price(0, Upgrade.HASTE, edge) == (30, 400)  # the edge is in reach
    assert world.cast_price(0, Upgrade.HASTE, (edge[0] + 0.01, edge[1])) == (30 * SPELL_FAR, 400 * SPELL_FAR) == (60, 800)
    world.cast(0, Upgrade.HASTE, FAR)
    assert world.players[0].aether == 40 and world.cooldown_left(0, Upgrade.HASTE) == 800
    world.players[0].aether = 59
    world.players[0].cooldowns.clear()
    with pytest.raises(RuleError, match=r"Not enough aether \(60 needed, 2x beyond your vaults' reach\)"):
        world.cast(0, Upgrade.HASTE, FAR)


def test_a_cast_into_the_fog_lands_blind() -> None:
    world = knowing(field(), Upgrade.FLAME_STRIKE)
    foe = held(world, 1, UnitType.FOOTMAN, (8.5, 8.5))
    world.update_vision()  # seat 0 sees round its buildings only
    world.visible[0][:] = bytes(len(world.visible[0]))
    assert not world.is_visible(0, foe.tile)
    world.cast(0, Upgrade.FLAME_STRIKE, foe.pos)
    assert foe.hp == foe.max_hp - 30


# -- The spells, one by one -------------------------------------------------------------------------------------------


def test_haste_quickens_the_casters_own_units_near_the_point_and_nobody_else() -> None:
    world = knowing(field(), Upgrade.HASTE)
    near = held(world, 0, UnitType.FOOTMAN, (11.5, 10.5))
    far = held(world, 0, UnitType.FOOTMAN, (16.5, 10.5))
    foe = held(world, 1, UnitType.FOOTMAN, (10.5, 11.5))
    base = world.speed_of(near)
    world.cast(0, Upgrade.HASTE, HERE)
    assert world.speed_of(near) == pytest.approx(base * 1.4) and near.blow_mult == pytest.approx(0.45)
    assert not far.conditions and not foe.conditions
    step(world, 14.05)
    assert not near.conditions


def test_mend_heals_fifteen_a_second_for_ten_seconds_and_staunches_a_bleeding_wound() -> None:
    world = knowing(field(), Upgrade.MEND)
    hurt = held(world, 0, UnitType.ARCHER, HERE)
    hurt.hp = 5
    world._lay(hurt, BLEEDING, 1)  # staging: an archer's wound, without the archer
    engine = held(world, 0, UnitType.CATAPULT, (12.5, 10.5))
    engine.hp = 50
    world.cast(0, Upgrade.MEND, HERE)
    assert hurt.condition(BLEEDING) is None and hurt.condition(BUFFS["mend"]) is not None
    assert not engine.conditions  # a machine is not mended
    step(world, 2.0)
    assert hurt.hp == 35 and engine.hp == 50
    step(world, 8.05)
    assert hurt.hp == hurt.max_hp and hurt.condition(BUFFS["mend"]) is None


def test_flame_strike_burns_through_armour_and_lands_on_buildings_at_once() -> None:
    world = knowing(field(), Upgrade.FLAME_STRIKE)
    foe = held(world, 1, UnitType.FOOTMAN, (20.5, 10.5))
    friend = held(world, 0, UnitType.FOOTMAN, (21.2, 10.5))
    farm = world.place_building(1, BuildingType.FARM, (21, 11))
    world.cast(0, Upgrade.FLAME_STRIKE, (20.5, 10.5))
    assert foe.hp == foe.max_hp - 30  # through its three armour, and no roll
    assert farm.hp == farm.max_hp - 30 - 8  # the burn's whole drain at once: a building carries no condition
    assert friend.hp == friend.max_hp and not friend.conditions
    step(world, 4.0)
    assert foe.hp == foe.max_hp - 38 and not foe.conditions


def test_stoneskin_adds_five_armour_for_fifteen_seconds() -> None:
    world = knowing(field(), Upgrade.STONESKIN)
    footman = held(world, 0, UnitType.FOOTMAN, HERE)
    before = world.armor_of(footman)
    world.cast(0, Upgrade.STONESKIN, HERE)
    assert world.armor_of(footman) == before + 5
    step(world, 15.05)
    assert world.armor_of(footman) == before


def test_entangle_holds_ground_units_where_they_stand_and_thorns_them_but_they_still_strike() -> None:
    world = knowing(field(), Upgrade.ENTANGLE)
    walker = world.spawn_unit(1, UnitType.KNIGHT, (20.5, 10.5))
    world.move([walker.id], (30.5, 10.5))
    fighter = held(world, 1, UnitType.FOOTMAN, (20.5, 12.0))
    target = held(world, 0, UnitType.PEASANT, (20.5, 12.8))
    flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, (21.5, 10.5))
    world.move([flyer.id], (30.5, 12.5))
    step(world, 0.2)
    world.cast(0, Upgrade.ENTANGLE, (20.5, 11.0))
    assert walker.rooted and fighter.rooted and not flyer.rooted  # flyers are out of reach
    where, hp = walker.pos, target.hp
    shoved = held(world, 1, UnitType.FOOTMAN, (walker.x + 0.2, walker.y))  # a body pushing into it
    step(world, 3.9)
    assert walker.pos == where, "rooted: neither its order nor the crowd moved it"
    assert walker.progress == 0.0 and isinstance(walker.order, Move)  # its watchdog waited, and its order stands
    assert target.hp < hp, "it still strikes what is in its reach"
    assert walker.hp < walker.max_hp and flyer.hp == flyer.max_hp, "the thorns bleed what the roots hold, through armour"
    assert flyer.x > 23.0 and shoved.pos != (walker.x + 0.2, walker.y)
    step(world, 2.7)
    assert not walker.rooted and walker.hp == walker.max_hp - 26
    step(world, 1.0)
    assert walker.x > where[0] + 0.5


def test_roots_hold_a_flyer_too_when_a_kind_that_roots_is_laid_on_one() -> None:
    """No spell of the table roots a flyer (Entangle passes beneath them), but roots are the kind's rule, not Entangle's:
    laid on a flyer they hold it in the air as they hold a walker on the ground, and its flight waits for them."""
    world = field()
    flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, (20.5, 10.5))
    world.move([flyer.id], (30.5, 10.5))
    world._lay(flyer, BUFFS["entangled"], 0)  # staging: the kind on its own, which no spell of the table lays on a flyer
    step(world, 3.9)
    assert flyer.pos == (20.5, 10.5) and isinstance(flyer.order, Move)
    step(world, 2.7)
    assert not flyer.rooted and flyer.x > 21.0


def test_an_entangled_healer_heals_whom_it_reaches_and_waits_for_the_rest() -> None:
    """A healer weighs its patients by the walk to each; roots are no speed of its own, so a rooted cleric weighs them as
    ever, heals the one in its reach and later walks to the other.  An Entangle on a healer beside a wounded comrade
    raised ZeroDivisionError out of the step: a crashed match, and online a crashed room."""
    world = knowing(field(), Upgrade.ENTANGLE)
    cleric = world.spawn_unit(1, UnitType.CLERIC, (20.5, 10.5))
    near = held(world, 1, UnitType.FOOTMAN, (22.5, 10.5))
    beyond = held(world, 1, UnitType.FOOTMAN, (20.5, 15.5))
    near.hp = beyond.hp = 10
    world.cast(0, Upgrade.ENTANGLE, (18.5, 10.5))  # the cleric at its middle, the comrade just outside its thorns
    assert cleric.rooted and not beyond.rooted
    step(world, 3.9)
    assert cleric.pos == (20.5, 10.5) and near.hp > 10
    step(world, 8.0)  # the one in its reach mended whole, it walks to the other
    assert cleric.pos != (20.5, 10.5) and beyond.hp > 10


def test_a_stone_weighs_a_friend_quickened_by_haste_and_fury_from_as_far_as_it_walks() -> None:
    """Haste and Battle Fury together quicken a knight past any listed speed.  A catapult weighing its own side under a
    stone looks out as far as a friend can walk before the stone lands, so it sees the knight coming through the spot
    from ten and a half tiles off (the fastest listed speed alone looked a tile short)."""
    world = field()
    world.players[0].upgrades.add(Upgrade.HORSES)
    catapult = held(world, 0, UnitType.CATAPULT, (10.5, 15.5))
    knight = world.spawn_unit(0, UnitType.KNIGHT, (31.5, 15.5))
    for kind in ("haste", "battle_fury"):
        world._lay(knight, BUFFS[kind], 0)  # staging: the two conditions alone
    world.move([knight.id], (5.5, 15.5))  # through the landing spot, in the stone's flight
    world.step()
    # The own-side weighing every crew's choice of a stone asks (_siege_choice, _aim_trade); nothing public returns it.
    assert world._friendly_cost(catapult, (20.5, 15.5)) > 0.0


def test_a_marching_line_does_not_wait_for_a_comrade_held_by_roots() -> None:
    """The rest of the line walks on at its pace while one of it is rooted: a row does not dress on a unit that cannot
    move (WB-066).  Left six tiles behind, it lets the group's pace go as any comrade left behind does."""
    world = knowing(field(), Upgrade.ENTANGLE)
    world.players[1].upgrades.add(Upgrade.ENTANGLE)
    world.players[1].aether = 1000
    line = [world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 14.5 + 1.2 * i)) for i in range(4)]
    world.move([u.id for u in line], (36.5, 15.5))
    step(world, 1.0)
    held_one = line[1]
    world.cast(1, Upgrade.ENTANGLE, held_one.pos)  # seat 1's roots on one of seat 0's line, and on no other of it
    for other in line:
        if other is not held_one and other.rooted:
            world._end(other, BUFFS["entangled"])  # staging: the roots on the one alone
    starts = {u.id: u.x for u in line}
    step(world, 3.0)
    walked = [line[i].x - starts[line[i].id] for i in (0, 2, 3)]
    assert held_one.x == starts[held_one.id]
    assert min(walked) > 0.8 * 3.0 * world.listed_speed(line[0]), walked


def test_wither_saps_enemies_damage_and_speed_machines_too() -> None:
    world = knowing(field(), Upgrade.WITHER)
    foe = held(world, 1, UnitType.FOOTMAN, (20.5, 10.5))
    engine = held(world, 1, UnitType.CATAPULT, (21.5, 11.5))
    friend = held(world, 0, UnitType.FOOTMAN, (19.5, 10.5))
    damage, speed = world.damage_of(foe), world.speed_of(foe)
    world.cast(0, Upgrade.WITHER, (20.5, 10.5))
    assert world.damage_of(foe) == int(round(damage * 0.4)) and world.speed_of(foe) == pytest.approx(speed * 0.8)
    assert engine.condition(BUFFS["withered"]) is not None and not friend.conditions


def test_a_meteor_lands_two_seconds_after_the_cast_on_friend_foe_and_buildings_alike() -> None:
    world = knowing(field(), Upgrade.METEOR)
    world.players[0].aether = 200
    point = (20.5, 10.5)
    heart = held(world, 1, UnitType.KNIGHT, point)
    edge = held(world, 0, UnitType.KNIGHT, (point[0] + 3.0 + UNITS[UnitType.KNIGHT].radius - 0.01, point[1]))
    flyer = held(world, 1, UnitType.FLYING_MACHINE, (point[0], point[1] + 1.0))
    wall = world.place_building(1, BuildingType.TOWN_HALL, (21, 8))
    world.cast(0, Upgrade.METEOR, point)
    (shot,) = world.projectiles.values()
    assert shot.spell is Upgrade.METEOR and shot.aim == point
    step(world, 1.95)
    assert heart.hp == heart.max_hp, "it has not landed yet"
    step(world, 0.1)
    armor = world.armor_of(heart)
    assert heart.hp == heart.max_hp - (150 - armor)
    assert edge.hp == edge.max_hp - (75 - world.armor_of(edge))  # the rim, and the caster's own knight
    assert flyer.hp < flyer.max_hp  # it falls through the air
    gap = max(0.0, 21 - point[0])
    assert wall.hp == wall.max_hp - (int(round((150 - 75 * gap / 3.0) * 1.5)) - world.armor_of(wall))
    assert not world.projectiles


def test_summon_brings_two_elementals_of_the_casters_that_are_gone_after_twenty_five_seconds() -> None:
    world = knowing(field(), Upgrade.SUMMON)
    world.players[0].aether = 200
    used = world.supply(0)[0]
    world.cast(0, Upgrade.SUMMON, (20.5, 10.5))
    elementals = [u for u in world.units.values() if u.type is UnitType.AETHER_ELEMENTAL]
    assert len(elementals) == 2 and all(u.player == 0 and u.hp == 85 and not u.info.living for u in elementals)
    assert world.damage_of(elementals[0]) == 12 and elementals[0].info.melee
    assert world.supply(0)[0] == used, "what a spell brings takes no room in the farms"
    lost = world.players[0].stats["units_lost"]
    world.take_events()
    step(world, 25.0)
    assert not any(u.type is UnitType.AETHER_ELEMENTAL for u in world.units.values())
    assert world.players[0].stats["units_lost"] == lost, "gone, not lost"
    assert sum(e.kind == "expired" for e in world.take_events()) == 2


def test_a_summoning_over_water_stands_its_elementals_on_the_nearest_ground_or_is_refused() -> None:
    world = knowing(field(), Upgrade.SUMMON)
    world.players[0].aether = 1000
    for y in range(2, 20):
        for x in range(14, 30):
            world.terrain[y][x] = Terrain.WATER
            world._blocked[y * world.width + x] = 1  # staging a lake: the grid follows the terrain
    world.cast(0, Upgrade.SUMMON, (15.5, 10.5))  # two tiles off the shore
    assert all(world.passable(u.tile[0], u.tile[1]) for u in world.units.values() if u.type is UnitType.AETHER_ELEMENTAL)
    world.players[0].cooldowns.clear()
    before = world.to_dict()
    with pytest.raises(RuleError, match="No open ground there"):
        world.cast(0, Upgrade.SUMMON, (21.5, 10.5))
    assert world.to_dict() == before, "refused before it paid for anything"


def test_one_vault_holds_any_spell_within_its_reach() -> None:
    """The store is sized to the dearest plain price (level III's): a side with one vault casts any spell it chose within
    that vault's reach, once the store fills.  Beyond every vault's reach the price is SPELL_FAR times, and that is what
    takes more vaults."""
    assert max(info.aether for info in SPELLS.values()) <= AETHER_STORE
    world = knowing(field(), Upgrade.METEOR)
    world.players[0].aether = world.aether_cap(0)
    assert world.aether_cap(0) == AETHER_STORE  # the field's one vault
    world.cast(0, Upgrade.METEOR, HERE)
    assert world.players[0].aether == AETHER_STORE - SPELLS[Upgrade.METEOR].aether


def test_a_far_cast_dearer_than_the_vaults_hold_says_what_will_pay_for_it() -> None:
    """Beyond every vault's reach a level II spell costs 120, which one vault holds, and a level III 240, more than one
    holds, so no wait pays for it: the refusal says what the vaults hold and what will (a cast within their reach, or
    another vault).  A second vault, even off the rifts, holds a far level III once the store fills."""
    world = knowing(field(), Upgrade.METEOR, Upgrade.WITHER)
    world.players[0].aether = world.aether_cap(0)  # the field's one vault, its store full
    level_2, level_3 = SPELLS[Upgrade.WITHER].aether * SPELL_FAR, SPELLS[Upgrade.METEOR].aether * SPELL_FAR
    assert level_2 <= AETHER_STORE < level_3 <= 2 * AETHER_STORE  # one vault and two
    world.cast(0, Upgrade.WITHER, FAR)
    assert world.players[0].aether == AETHER_STORE - level_2
    world.players[0].aether = world.aether_cap(0)
    before = world.to_dict()
    with pytest.raises(RuleError, match=rf"^Not enough aether \({level_3} needed, {SPELL_FAR}x beyond your vaults' reach\): they hold {AETHER_STORE}, "
                                        r"cast it within their reach or build another$"):
        world.cast(0, Upgrade.METEOR, FAR)
    assert world.to_dict() == before
    world.place_building(0, BuildingType.VAULT, (4, 18))  # off the rift: it stores, and draws nothing
    world.players[0].aether = world.aether_cap(0)  # full again, at the cap two vaults hold
    world.cast(0, Upgrade.METEOR, FAR)
    assert world.players[0].aether == 2 * AETHER_STORE - level_3


def test_battle_fury_drives_the_casters_units_within_six_tiles() -> None:
    world = knowing(field(), Upgrade.BATTLE_FURY)
    world.players[0].aether = 200
    near = held(world, 0, UnitType.FOOTMAN, (15.5, 10.5))
    base_damage, base_speed = world.damage_of(near), world.speed_of(near)
    world.cast(0, Upgrade.BATTLE_FURY, HERE)
    assert world.damage_of(near) == int(round(base_damage * 1.55)) and world.speed_of(near) == pytest.approx(base_speed * 1.2)


def test_a_killing_spell_is_the_casters_kill_and_its_dead_are_off_the_map_at_once() -> None:
    """A cast comes between steps, and what reads the world before the next one reads the living: a footman struck dead
    by a Flame Strike once stood in its army at minus hit points until the step (WB-067)."""
    world = knowing(field(), Upgrade.FLAME_STRIKE)
    foe = held(world, 1, UnitType.PEASANT, (20.5, 10.5))
    foe.hp = 10
    world.cast(0, Upgrade.FLAME_STRIKE, foe.pos)
    assert foe.id not in world.units and world.players[0].stats["units_killed"] == 1
    assert world.players[1].stats["units_lost"] == 1 and any(e.kind == "death" for e in world.take_events())


# -- Records ------------------------------------------------------------------------------------------------------------


def test_research_cooldowns_a_falling_meteor_and_summoned_units_ride_a_save_to_the_bit() -> None:
    world = knowing(field(), Upgrade.METEOR, Upgrade.ENTANGLE)
    world.players[0].aether = 1000  # the summoning is out of reach: the dearer price
    foe = world.spawn_unit(1, UnitType.FOOTMAN, (20.5, 10.5))
    world.move([foe.id], (30.5, 10.5))
    world.research(tower(world).id, Upgrade.HASTE)
    world.cast(0, Upgrade.ENTANGLE, (20.5, 10.5))
    world.cast(0, Upgrade.METEOR, (22.5, 10.5))
    world.players[0].upgrades.add(Upgrade.SUMMON)
    world.cast(0, Upgrade.SUMMON, (26.5, 12.5))
    step(world, 0.5)
    saved = json.loads(json.dumps(world.to_dict()))
    loaded = World.from_dict(saved)
    assert loaded.to_dict() == world.to_dict()
    for _ in range(int(round(45.0 / SIM_DT))):
        world.step()
        loaded.step()
    assert loaded.to_dict() == world.to_dict()


def test_a_match_with_casts_replays_faithfully() -> None:
    world = knowing(field(), Upgrade.FLAME_STRIKE, Upgrade.METEOR, Upgrade.SUMMON)
    world.players[0].aether = 1000
    for i in range(4):
        world.spawn_unit(1, UnitType.FOOTMAN, (20.5 + i, 10.5))
    replay = Replay.begin(world, seed=1, difficulty=Difficulty.MEDIUM, human=0)
    step(world, 1.0)
    world.cast(0, Upgrade.FLAME_STRIKE, (20.5, 10.5))
    step(world, 1.0)
    world.cast(0, Upgrade.METEOR, (22.5, 10.5))
    try:
        world.cast(0, Upgrade.METEOR, (22.5, 10.5))  # refused on its cooldown, and refused again on playback
    except RuleError:
        pass
    world.cast(0, Upgrade.SUMMON, (18.5, 12.5))
    step(world, 5.0)
    replay.finish(world, "unfinished")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    playback.run()
    assert playback.faithful and playback.world.to_dict() == world.to_dict()


# -- Online -------------------------------------------------------------------------------------------------------------


def online() -> WarbandMatch:
    match = WarbandMatch(seed=3)
    world = match.world
    world.players[0].upgrades |= {Upgrade.KEEP, Upgrade.FLAME_STRIKE, Upgrade.WITHER, Upgrade.METEOR}
    world.players[0].aether = 1000  # no vault stands: every cast is the dearer one
    return match


def test_nobody_trains_an_elemental_neither_at_the_tower_nor_by_a_plan_nor_online() -> None:
    """Only the spell brings an elemental, for its aether and its cooldown.  Its row names the tower its spell is
    researched at, and that once let a tower train one: free, at once, and taking no supply."""
    world = field()
    assert world.can_train(tower(world), UnitType.AETHER_ELEMENTAL) == "Nobody trains an Aether Elemental"
    with pytest.raises(RuleError, match="Nobody trains an Aether Elemental"):
        world.order_unit(0, UnitType.AETHER_ELEMENTAL)
    from saga2d import CommandError

    match = online()
    mage = match.world.place_building(0, BuildingType.MAGE_TOWER, (2, 2))
    with pytest.raises(CommandError, match="Nobody trains"):
        match.apply(0, {"action": "train", "args": [mage.id, "aether_elemental"]})
    assert not any(u.type is UnitType.AETHER_ELEMENTAL for u in match.world.units.values()) and not mage.queue


def test_a_seat_casts_its_own_spells_and_nobody_elses() -> None:
    from saga2d import CommandError

    match = online()
    hall = match.world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    match.apply(0, {"action": "cast", "args": [0, "wither", list(hall.center)]})
    assert match.world.players[0].aether == 1000 - SPELL_FAR * 60  # no vault stands: everywhere is beyond reach
    with pytest.raises(CommandError, match="your own spells"):
        match.apply(1, {"action": "cast", "args": [0, "flame_strike", list(hall.center)]})
    with pytest.raises(CommandError, match="not a spell"):
        match.apply(0, {"action": "cast", "args": [0, "blades_1", list(hall.center)]})
    with pytest.raises(CommandError, match="inside the map"):
        match.apply(0, {"action": "cast", "args": [0, "flame_strike", [-1.0, 3.0]]})


def test_a_rivals_research_aether_and_cooldowns_stay_private() -> None:
    match = online()
    hall = match.world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    match.apply(0, {"action": "cast", "args": [0, "wither", list(hall.center)]})
    mine, theirs = match.snapshot(0)["world"]["players"][0], match.snapshot(1)["world"]["players"][0]
    assert mine["cooldowns"] == {"wither": match.world.players[0].cooldowns[Upgrade.WITHER]} and mine["aether"] == 1000 - SPELL_FAR * 60
    assert theirs["cooldowns"] == {} and theirs["aether"] == 0 and theirs["upgrades"] == []


def test_a_cast_is_news_only_where_a_seat_sees_the_ground_it_touches_and_so_is_a_meteors_shadow() -> None:
    match = online()
    world = match.world
    rival = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    home = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    match.apply(0, {"action": "cast", "args": [0, "meteor", list(rival.center)]})  # blind: seat 0 does not see it
    match.apply(0, {"action": "cast", "args": [0, "wither", list(home.center)]})  # at home: seat 1 does not see it
    news = [(seat, event["kind"], event["text"]) for seat in (0, 1) for _i, event in match.snapshot(seat)["events"]
            if event["kind"] in SPELL_EVENTS]
    assert (1, "cast", "meteor") in news and (1, "cast", "wither") not in news and (1, "spell", "wither") not in news
    assert (0, "cast", "meteor") in news and (0, "spell", "wither") in news
    assert [shot["spell"] for shot in match.snapshot(1)["world"]["projectiles"]] == ["meteor"]  # its own ground
    assert match.snapshot(0)["world"]["projectiles"], "and its caster's"
    far = next((x, y) for y in range(world.height) for x in range(world.width) if not any(world.is_visible(s, (x, y)) for s in (0, 1)))
    world.players[0].cooldowns.clear()
    match.apply(0, {"action": "cast", "args": [0, "meteor", [far[0] + 0.5, far[1] + 0.5]]})
    assert len(match.snapshot(1)["world"]["projectiles"]) == 1, "a shadow on ground nobody sees is not seat 1's"
    assert len(match.snapshot(0)["world"]["projectiles"]) == 2


def test_a_snapshot_of_a_world_with_spells_restores() -> None:
    match = online()
    rival = match.world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    match.apply(0, {"action": "cast", "args": [0, "meteor", list(rival.center)]})
    for seat in (0, 1):
        World.from_dict(json.loads(json.dumps(match.snapshot(seat)["world"])))


def test_every_spell_says_its_numbers() -> None:
    """A summary promises numbers in words: a number moved in spells.toml or buffs.toml without its words is a card that
    lies."""
    for spell, info in SPELLS.items():
        assert f"{info.radius:g} tiles" in info.summary or info.summons is not None, spell
        for kind in info.lays:
            assert f"{kind.duration:g} s" in info.summary, (spell, kind.key)
    assert "40 %" in SPELLS[Upgrade.HASTE].summary and "30 through armour" in SPELLS[Upgrade.FLAME_STRIKE].summary
    assert "+5 armour" in SPELLS[Upgrade.STONESKIN].summary and "Two" in SPELLS[Upgrade.SUMMON].summary
    assert "60 % less damage" in SPELLS[Upgrade.WITHER].summary and "55 % more damage" in SPELLS[Upgrade.BATTLE_FURY].summary
    assert "+15 hp a second" in SPELLS[Upgrade.MEND].summary and "thorns 4/s" in SPELLS[Upgrade.ENTANGLE].summary
    assert f"{UNITS[UnitType.AETHER_ELEMENTAL].lifetime:g} s" in SPELLS[Upgrade.SUMMON].summary
