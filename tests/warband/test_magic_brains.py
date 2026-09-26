"""The computer players and magic (WB-067, ``warband.brains.magic``): Hard, Master and the bred postures raise a vault
on their own rift, a Mage Tower and a spell a level, and cast from what their side can see; Easy and Medium never touch
magic.  Each decision on a staged world."""

import json
import random
from dataclasses import replace

import pytest
from saga2d import CommandError

from warband.brains import magic
from warband.brains.ai import Brain
from warband.brains.bred import BRED, BRED_FOR_LAYOUT
from warband.brains.pro_ai import PRO_RUSH, PRO_VANGUARD, PRO_WARDEN, ProBrain
from warband.brains.pro_profiles import PRO_HARD
from warband.online.authority import SPELL_EVENTS, WarbandMatch
from warband.online.online_ai import _PlanningWorld
from warband.sim.model import Build, World, dist, rect_gap
from warband.sim.rules import SIM_DT, SPELLS, BuildingType, Difficulty, Race, Terrain, UnitType, Upgrade

OWN_RIFT = (10, 4)  # by seat 0's hall
MIDDLE = (24, 14)  # nearer seat 0's hall than seat 1's
THEIRS = (46, 30)  # by seat 1's hall
VAULT_REACH = (11.0, 5.0)  # the middle of a vault on OWN_RIFT: ten tiles round it is within reach


def field(*, rifts=(OWN_RIFT, MIDDLE, THEIRS)) -> World:
    """Open grass, 60 by 40: seat 0's hall in the north-west, seat 1's in the south-east, three ley rifts."""
    world = World(60, 40, [[Terrain.GRASS] * 60 for _ in range(40)], 2, rng=random.Random(3), races=[Race.HUMAN, Race.ORC],
                  human=None)
    world.lay_rifts(rifts)
    world.place_building(0, BuildingType.TOWN_HALL, (3, 3))
    world.place_building(1, BuildingType.TOWN_HALL, (54, 34))
    world.reveal_all(0)
    return world


def caster(world: World, *spells: Upgrade, aether: int = 150) -> World:
    """Seat 0 with a vault on its rift, a tower, *spells* researched and *aether* in store."""
    world.place_building(0, BuildingType.VAULT, OWN_RIFT)
    world.place_building(0, BuildingType.MAGE_TOWER, (3, 12))
    world.players[0].upgrades.update(spells)
    world.players[0].aether = aether
    return world


def held(world: World, player: int, unit_type: UnitType, point):
    unit = world.spawn_unit(player, unit_type, point)
    world.hold([unit.id])
    return unit


def line(world: World, player: int, unit_type: UnitType, x: float, y: float, count: int, step: float = 0.9):
    return [held(world, player, unit_type, (x + step * i, y)) for i in range(count)]


def seen(world: World) -> World:
    world.update_vision()
    return world


# -- What it chooses --------------------------------------------------------------------------------------------------


def test_each_posture_takes_its_spells_and_a_profile_may_choose_its_own() -> None:
    assert magic.spells(PRO_RUSH) == (Upgrade.HASTE, Upgrade.ENTANGLE, Upgrade.BATTLE_FURY)
    assert magic.spells(PRO_VANGUARD) == (Upgrade.FLAME_STRIKE, Upgrade.ENTANGLE, Upgrade.BATTLE_FURY)
    assert magic.spells(PRO_WARDEN) == magic.spells(PRO_HARD) == (Upgrade.MEND, Upgrade.STONESKIN, Upgrade.METEOR)
    assert magic.spells(replace(PRO_VANGUARD, min_army=8, attack_ratio=1.0)) == magic.MIXED_SPELLS
    assert magic.spells(replace(PRO_VANGUARD, spell_2=Upgrade.WITHER)) == (Upgrade.FLAME_STRIKE, Upgrade.WITHER, Upgrade.BATTLE_FURY)
    with pytest.raises(ValueError, match="no level I spell"):
        magic.spells(replace(PRO_VANGUARD, spell_1=Upgrade.METEOR))
    for postures in (*BRED.values(), *BRED_FOR_LAYOUT.values()):
        for profile in postures:
            assert profile.magic and len(set(magic.spells(profile))) == 3, "the bred postures cast, by their posture"


def orders(world: World) -> list[Build]:
    return [u.order for u in world.player_units(0) if isinstance(u.order, Build)]


def economy(world: World, profile, seconds: float = 1.0) -> ProBrain:
    """Seat 0 with a barracks, farms, peasants and a bank, thinking for *seconds*."""
    world.place_building(0, BuildingType.BARRACKS, (10, 12))
    world.place_building(0, BuildingType.LUMBER_MILL, (14, 12))
    for i in range(4):
        world.place_building(0, BuildingType.FARM, (3 + 3 * i, 20))
    for i in range(8):
        world.spawn_unit(0, UnitType.PEASANT, (2.5 + i, 26.5))
    world.players[0].gold = world.players[0].lumber = 20_000
    brain = ProBrain(0, profile)
    rng = random.Random(0)
    for _ in range(round(seconds / SIM_DT)):
        brain.think(world, rng)
        world.step()
    return brain


def test_the_vault_goes_up_square_on_its_own_rift_in_the_mid_game_and_not_before() -> None:
    early = field()
    economy(early, replace(PRO_VANGUARD, vault_from=1e9))
    assert not any(order.type is BuildingType.VAULT for order in orders(early)), "not before the mid game"
    world = field()
    economy(world, replace(PRO_VANGUARD, vault_from=0.0))
    vaults = [order for order in orders(world) if order.type is BuildingType.VAULT]
    assert [order.pos for order in vaults] == [OWN_RIFT], "one vault, square on the rift by its hall"


def test_magic_takes_a_builder_and_never_a_site_of_the_build_order() -> None:
    """A vault or tower in flight held two of max_sites for the minute and a half the two take, and the tower or the
    lumber mill the plan had next waited behind it with the bank full: an early vault cost Master a dozen points free."""
    for sites in (1, 2):
        plain, magical = field(), field()
        economy(plain, replace(PRO_VANGUARD, vault_from=0.0, max_sites=sites, magic=False))
        economy(magical, replace(PRO_VANGUARD, vault_from=0.0, max_sites=sites))
        planned = [order.type for order in orders(plain)]
        assert len(planned) == sites
        assert [order.type for order in orders(magical)] == [*planned, BuildingType.VAULT]


def test_once_the_vault_stands_the_tower_then_a_spell_a_level_then_a_second_vault_nearer_us() -> None:
    world = field()
    world.place_building(0, BuildingType.VAULT, OWN_RIFT)
    economy(world, replace(PRO_WARDEN, vault_from=0.0))
    assert BuildingType.MAGE_TOWER in [order.type for order in orders(world)]
    world = field()
    world.place_building(0, BuildingType.VAULT, OWN_RIFT)
    tower = world.place_building(0, BuildingType.MAGE_TOWER, (3, 12))
    economy(world, replace(PRO_WARDEN, vault_from=0.0))
    assert tower.research is Upgrade.MEND, "the warden's level I spell"
    assert [order.pos for order in orders(world) if order.type is BuildingType.VAULT] == [MIDDLE], "not the rift by their hall"
    world = field()
    world.place_building(0, BuildingType.VAULT, OWN_RIFT)
    tower = world.place_building(0, BuildingType.MAGE_TOWER, (3, 12))
    world.players[0].upgrades.update({Upgrade.MEND, Upgrade.KEEP})
    economy(world, replace(PRO_WARDEN, vault_from=0.0))
    assert tower.research is Upgrade.STONESKIN


def test_a_rival_passing_a_vault_is_no_raid_on_the_base() -> None:
    """A second vault stands mid-map, where the armies meet: an army that ran home to every rival passing it fought
    where the rival chose.  A rival by the hall is a raid as ever."""
    world = field()
    world.place_building(0, BuildingType.VAULT, MIDDLE)
    passing = held(world, 1, UnitType.FOOTMAN, (MIDDLE[0] + 3.5, MIDDLE[1] + 1.0))
    brain = ProBrain(0, PRO_VANGUARD)
    assert brain._threats(world) == []
    passing.x, passing.y = 7.5, 5.5  # by the hall
    assert brain._threats(world) == [passing]


def test_easy_and_medium_never_touch_magic_and_a_posture_without_it_neither() -> None:
    for brain in (Brain(0, Difficulty.EASY), Brain(0, Difficulty.MEDIUM)):
        world = field()
        world.place_building(0, BuildingType.BARRACKS, (10, 12))
        for i in range(8):
            world.spawn_unit(0, UnitType.PEASANT, (2.5 + i, 26.5))
        world.players[0].gold = world.players[0].lumber = 50_000
        rng = random.Random(0)
        for _ in range(round(20.0 / SIM_DT)):
            brain.think(world, rng)
            world.step()
        assert not any(order.type in (BuildingType.VAULT, BuildingType.MAGE_TOWER) for order in orders(world))
        assert not world.player_buildings(0, BuildingType.VAULT)
    world = field()
    economy(world, replace(PRO_VANGUARD, vault_from=0.0, magic=False))
    assert not any(order.type is BuildingType.VAULT for order in orders(world))


# -- When and where it casts ------------------------------------------------------------------------------------------


def test_a_buff_goes_over_our_army_where_it_engages_and_never_into_nothing() -> None:
    world = seen(caster(field(), Upgrade.HASTE))
    ours = line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 5)
    mage = magic.Magus(PRO_RUSH)
    assert mage.cast(world, 0) == [], "nobody to fight"
    rivals = line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 3)
    seen(world)
    [(spell, point)] = mage.cast(world, 0)
    assert spell is Upgrade.HASTE and world.players[0].aether == 120
    assert sum(1 for u in ours if u.condition(SPELLS[Upgrade.HASTE].lays[0])) >= 4, "the point covering most of it"
    assert not any(u.conditions for u in rivals)


def test_mend_goes_over_an_army_half_spent_in_a_fight_and_not_over_a_whole_one() -> None:
    """A unit counts for its wounds up to half its life: a mend that heals more than a footman holds still wants the
    army it is cast for wounded, and one worn down to half wants no more."""
    world = seen(caster(field(), Upgrade.MEND))
    ours = line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 5)
    line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 5)
    seen(world)
    mage = magic.Magus(PRO_WARDEN)
    assert mage.cast(world, 0) == [], "nobody hurt yet"
    for u in ours:
        u.hp = u.max_hp // 2
    assert [spell for spell, _point in mage.cast(world, 0)] == [Upgrade.MEND]
    assert all(u.condition(SPELLS[Upgrade.MEND].lays[0]) for u in ours)


def test_a_rival_out_of_sight_is_never_cast_at() -> None:
    world = caster(field(), Upgrade.FLAME_STRIKE)
    line(world, 1, UnitType.ARCHER, 16.5, 9.5, 3, step=0.6)
    world.update_vision()  # the hall and the vault see a few tiles round them: the archers stand in the fog
    assert not magic.Magus(PRO_VANGUARD).cast(world, 0)
    held(world, 0, UnitType.PEASANT, (15.5, 8.5))
    seen(world)
    assert [spell for spell, _point in magic.Magus(PRO_VANGUARD).cast(world, 0)] == [Upgrade.FLAME_STRIKE]


def test_flame_strike_falls_on_a_clump_and_not_on_a_lone_footman() -> None:
    world = seen(caster(field(), Upgrade.FLAME_STRIKE))
    lone = held(world, 1, UnitType.FOOTMAN, (15.5, 9.5))
    seen(world)
    assert not magic.Magus(PRO_VANGUARD).cast(world, 0), "a footman's half life is not worth the aether"
    lone.hp = 0
    world.step()
    clump = line(world, 1, UnitType.ARCHER, 15.5, 9.5, 3, step=0.6)
    held(world, 0, UnitType.FOOTMAN, (15.5, 7.5))
    seen(world)
    [(_spell, point)] = magic.Magus(PRO_VANGUARD).cast(world, 0)
    assert all(dist(point, a.pos) - a.radius <= SPELLS[Upgrade.FLAME_STRIKE].radius for a in clump)


def test_a_meteor_weighs_our_own_under_it_as_a_siege_crew_does() -> None:
    world = seen(caster(field(), Upgrade.METEOR, aether=150))
    clump = line(world, 1, UnitType.ARCHER, 15.5, 9.5, 4, step=0.6)
    ours = line(world, 0, UnitType.FOOTMAN, 15.5, 10.4, 3, step=0.6)
    seen(world)
    assert not magic.Magus(PRO_WARDEN).cast(world, 0), "our own line is in the fight with them"
    for u in ours:
        world.move([u.id], (4.5, 30.5))
        u.x, u.y = 6.5 + u.id % 3, 22.5  # staged: they have walked away
    held(world, 0, UnitType.PEASANT, (15.5, 6.0))  # and a peasant out of the blast keeps the archers in sight
    seen(world)
    [(spell, point)] = magic.Magus(PRO_WARDEN).cast(world, 0)
    assert spell is Upgrade.METEOR and all(dist(point, a.pos) <= 2.5 for a in clump)


def test_a_meteor_takes_a_tower_with_the_rivals_by_it_over_as_many_rivals_alone() -> None:
    """A building under it counts as a siege crew counts a wall, a tower twice: of two clumps alike, the one by a tower."""
    world = caster(field(), Upgrade.METEOR)
    line(world, 1, UnitType.FOOTMAN, 14.5, 3.5, 4)  # the first of two equals, both within the vault's reach
    tower = world.place_building(1, BuildingType.TOWER, (14, 11))
    line(world, 1, UnitType.FOOTMAN, 13.5, 14.0, 4)
    seen(world)
    world.reveal_all(0)
    [(spell, point)] = magic.Magus(PRO_WARDEN).cast(world, 0)
    assert spell is Upgrade.METEOR and rect_gap(point, tower.rect) <= SPELLS[Upgrade.METEOR].radius


def test_a_meteor_falls_where_archers_stop_to_shoot_and_not_past_it() -> None:
    """Led the whole two seconds of the fall, archers walking up to shoot stood on our own line, which the Meteor then
    spared; they stop at their reach, and that is where it falls on them."""
    world = caster(field(), Upgrade.METEOR)
    ours = line(world, 0, UnitType.FOOTMAN, 12.5, 8.5, 3, step=1.5)
    archers = [held(world, 1, UnitType.ARCHER, (12.5 + 1.5 * i, 15.5)) for i in range(3)]
    seen(world)
    for archer, footman in zip(archers, ours):
        world.attack([archer.id], footman.id)
    for _ in range(round(0.3 / SIM_DT)):
        world.step()
    world.reveal_all(0)
    assert all(a.vx or a.vy for a in archers), "still walking up"
    [(spell, _point)] = magic.Magus(PRO_WARDEN).cast(world, 0)
    for _ in range(round(SPELLS[Upgrade.METEOR].delay / SIM_DT) + 2):
        world.step()
    assert spell is Upgrade.METEOR and all(a.hp <= 0 for a in archers) and all(u.hp > 0 for u in ours)


def test_entangle_holds_rivals_running_from_our_army() -> None:
    world = seen(caster(field(), Upgrade.ENTANGLE))
    ours = line(world, 0, UnitType.FOOTMAN, 8.5, 8.5, 4)
    runners = line(world, 1, UnitType.FOOTMAN, 9.5, 10.5, 4, step=0.7)
    seen(world)
    assert not magic.Magus(PRO_RUSH).cast(world, 0), "standing their ground: nobody is running"
    world.move([u.id for u in runners], (9.5, 30.5))
    for _ in range(round(1.0 / SIM_DT)):
        world.step()
    world.reveal_all(0)  # a second on, still in sight
    [(spell, _point)] = magic.Magus(PRO_RUSH).cast(world, 0)
    assert spell is Upgrade.ENTANGLE and sum(1 for u in runners if u.conditions) >= 3
    assert not any(u.conditions for u in ours)


def test_entangle_holds_rivals_chasing_our_army_as_it_falls_back() -> None:
    world = seen(caster(field(), Upgrade.ENTANGLE))
    ours = line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 4)
    chasers = line(world, 1, UnitType.FOOTMAN, 13.5, 13.5, 4, step=0.7)
    seen(world)
    world.move([u.id for u in ours], (14.85, 1.5))  # falling back to the hall
    world.move([u.id for u in chasers], (14.85, 1.5))  # and after them
    for _ in range(round(1.0 / SIM_DT)):
        world.step()
    world.reveal_all(0)
    [(spell, _point)] = magic.Magus(PRO_RUSH).cast(world, 0)
    assert spell is Upgrade.ENTANGLE and sum(1 for u in chasers if u.conditions) >= 3
    assert not any(u.conditions for u in ours)


def test_buffs_wither_and_summon_wait_for_the_fight_to_be_joined_and_summon_stays_within_reach() -> None:
    """Cast at first contact over the few in front, what lasts a fight had run out by the time the rest came up."""
    mage = magic.Magus(replace(PRO_VANGUARD, spell_2=Upgrade.WITHER, spell_3=Upgrade.SUMMON))
    for spell in (Upgrade.HASTE, Upgrade.WITHER, Upgrade.SUMMON):
        world = seen(caster(field(), Upgrade.KEEP, spell))
        line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 2)
        rear = line(world, 0, UnitType.FOOTMAN, 13.5, 4.0, 4)  # within a fight's reach of the front, not in it yet
        line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 6)
        seen(world)
        assert not mage.cast(world, 0), f"{spell.value}: two of six in the fight"
        for u in rear:
            u.y = 8.6  # staged: they have come up
        seen(world)
        assert [s for s, _point in mage.cast(world, 0)] == [spell]
    # Beyond reach, with two vaults' store for the far price and a caster glad to pay it: only the reach refuses it.
    far = caster(field(), Upgrade.KEEP, Upgrade.SUMMON, aether=300)
    far.place_building(0, BuildingType.VAULT, THEIRS)  # the second vault, fifteen tiles from the fight
    line(far, 0, UnitType.FOOTMAN, 32.5, 25.5, 3)
    line(far, 1, UnitType.FOOTMAN, 32.5, 27.2, 6)
    seen(far)
    middle = (33.9, 26.4)  # between the two lines, where it would be summoned
    assert not far.in_reach(0, middle) and far.can_cast(0, Upgrade.SUMMON, middle) is None
    assert not magic.Magus(replace(mage.profile, far_worth=1.0)).cast(far, 0), "beyond every vault's reach"


def test_a_buff_is_not_laid_again_over_units_that_carry_it() -> None:
    world = seen(caster(field(), Upgrade.MEND, Upgrade.KEEP, Upgrade.STONESKIN))
    line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 5)
    line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 3)
    seen(world)
    mage = magic.Magus(PRO_WARDEN)
    assert [spell for spell, _point in mage.cast(world, 0)] == [Upgrade.STONESKIN]
    world.players[0].cooldowns.clear()
    world.players[0].aether = 150
    assert not mage.cast(world, 0), "all five carry it still: laid again it would only start over"


def test_summon_defends_the_base_when_no_army_of_ours_is_there() -> None:
    world = caster(field(), Upgrade.KEEP, Upgrade.SUMMON)
    line(world, 0, UnitType.FOOTMAN, 40.5, 20.5, 4)  # our army, far off and in no fight
    line(world, 1, UnitType.FOOTMAN, 8.5, 9.0, 5)  # raiders at the hall
    seen(world)
    world.reveal_all(0)
    [(spell, point)] = magic.Magus(replace(PRO_VANGUARD, spell_3=Upgrade.SUMMON)).cast(world, 0)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    assert spell is Upgrade.SUMMON and dist(point, hall.center) < magic.FIGHT


def test_a_cast_the_world_refuses_is_skipped_and_never_raised() -> None:
    world = seen(caster(field(), Upgrade.HASTE))
    line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 5)
    line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 3)
    seen(world)
    world.players[0].alive = False  # a refusal the caster does not foresee: this side may cast nothing now
    assert magic.Magus(PRO_RUSH).cast(world, 0) == []


def test_a_far_cast_wants_more_and_a_near_one_that_would_do_goes_first() -> None:
    world = seen(caster(field(), Upgrade.HASTE, aether=140))  # short of full: a full store would halve the bar
    far = line(world, 0, UnitType.FOOTMAN, 33.5, 25.5, 5)
    line(world, 1, UnitType.FOOTMAN, 33.5, 27.2, 5)
    seen(world)
    assert not world.in_reach(0, far[0].pos)
    assert not magic.Magus(PRO_RUSH).cast(world, 0), "five bodies do for thirty aether, not for sixty"
    near = line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 4)
    line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 3)
    seen(world)
    [(_spell, point)] = magic.Magus(PRO_RUSH).cast(world, 0)
    assert world.in_reach(0, point) and world.players[0].aether == 110
    assert all(not u.conditions for u in far) and any(u.conditions for u in near)


def test_a_lower_spell_leaves_only_what_the_vaults_cannot_draw_before_the_level_three_spell_is_ready() -> None:
    """One vault holds 150.  Kept whole while the Meteor cooled, its 120 held a Stoneskin (60) at 180 aether, which the
    vault never holds, and a level I cast at a full store; a lower cast now leaves only what the vault cannot draw, an
    aether a second, before the Meteor is ready again, and never so much that a full store could not pay for it."""

    def stoneskin(aether: int, *, cooling: float | None = None, researched: float | None = None) -> bool:
        """Whether the warden casts Stoneskin over a joined fight with *aether* in store, the Meteor *cooling* that many
        seconds more, or *researched* that many seconds into its research."""
        world = caster(field(), Upgrade.MEND, Upgrade.KEEP, Upgrade.STONESKIN, aether=aether)
        if researched is None:
            world.players[0].upgrades.add(Upgrade.METEOR)
            world.players[0].cooldowns[Upgrade.METEOR] = world.tick + round((cooling or 0.0) / SIM_DT)
        else:
            tower = world.player_buildings(0, BuildingType.MAGE_TOWER)[0]
            tower.research, tower.research_progress = Upgrade.METEOR, researched
        line(world, 0, UnitType.FOOTMAN, 13.5, 9.5, 5)
        line(world, 1, UnitType.FOOTMAN, 13.5, 11.2, 3)  # our own stand among them: no Meteor here
        seen(world)
        return [spell for spell, _point in magic.Magus(PRO_WARDEN).cast(world, 0)] == [Upgrade.STONESKIN]

    assert stoneskin(90, cooling=90.0), "cast a moment ago: the thirty left and the ninety drawn by then pay for it"
    assert not stoneskin(80, cooling=90.0)
    assert not stoneskin(100, cooling=60.0), "sixty seconds to go: the forty left and sixty drawn are not the 120"
    assert stoneskin(120, cooling=60.0)
    assert stoneskin(150, cooling=5.0), "a full store pays for it all the same: aether kept at the cap is aether lost"
    assert not stoneskin(140, cooling=5.0)
    assert stoneskin(150), "ready and not worth casting here: a full store still casts the level below"
    assert stoneskin(70, researched=10.0), "its research has 110 seconds to run"
    assert not stoneskin(100, researched=115.0)


# -- Online: a seat's snapshot --------------------------------------------------------------------------------------------


@pytest.mark.source_only("the brain plans on online_ai's stand-in for a World, which online_ai runs on the source")
def test_online_a_brain_casts_from_its_snapshot_its_store_stays_its_own_and_a_refusal_breaks_nothing() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    world.players[1].upgrades |= {Upgrade.FLAME_STRIKE}
    world.players[1].aether = 1000  # no vault stands: every cast is the dearer one
    x, y = hall.center
    for i in range(3):
        held(world, 1, UnitType.FOOTMAN, (x - 3.0 + i, y - 3.0))
        held(world, 0, UnitType.ARCHER, (x - 3.0 + 0.6 * i, y - 4.5))
    world.update_vision()
    brain = ProBrain(1, PRO_VANGUARD)

    def plan() -> list[dict]:
        planning = _PlanningWorld(json.loads(json.dumps(match.snapshot(1)))['world'])
        brain._combat(planning)  # the pass that casts
        return [c for c in planning.commands if c['action'] == 'cast']

    [command] = plan()
    theirs = match.snapshot(0)['world']['players'][1]
    assert theirs['aether'] == 0 and theirs['upgrades'] == [] and theirs['cooldowns'] == {}, "the rival's snapshot"
    world.players[1].aether = 10  # spent on the server before the order arrived: a refusal the brain could not see
    with pytest.raises(CommandError, match="Not enough aether"):
        match.apply(1, command)
    world.players[1].aether = 1000
    [command] = plan()  # and it goes on casting as before
    match.apply(1, command)
    news = [(event['kind'], event['text']) for _i, event in match.snapshot(0)['events'] if event['kind'] in SPELL_EVENTS]
    assert ('cast', 'flame_strike') in news, "seat 0 sees the ground it fell on"
