"""Each race's own unit (WB-068): the Humans' gryphon rider, the Orcs' goblin sapper, the Elves' treant and the Dwarves'
rune golem.  Each is a row of ``units.toml`` bound to one race (``race``), waiting for the Keep (``requires``) and kept to
three at once (``limit``), with one mechanic of its own: an armed flyer, a blow that is its end (``blast``), a walk
through the forest (``forest``) and a slam that spares its side (the wild golem's ``splash`` on a melee blow)."""

import random

import pytest

from warband.sim.model import Attack, RuleError, World, dist
from warband.sim.races import RACES
from warband.ui.view import FLIGHT, projectile_point
from warband.sim.rules import OWN_UNITS, SIM_DT, UNITS, BuildingType, Race, Terrain, UnitType, Upgrade


def grass(width: int = 40, height: int = 30, *, trees=(), races=(Race.HUMAN, Race.HUMAN)) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 2, rng=random.Random(1), races=list(races))
    for player in world.players[:world.seats]:
        player.human = True
    world.reveal_all(0)
    world.reveal_all(1)
    return world


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


# -- The gryphon rider: the first armed flyer ------------------------------------------------------------------------


def test_a_gryphon_strikes_a_flyer_and_a_walker_and_only_a_shot_reaches_it() -> None:
    world = grass()
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (10.5, 10.5))
    machine = world.spawn_unit(1, UnitType.FLYING_MACHINE, (14.5, 10.5))
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 20.5))
    archer = world.spawn_unit(1, UnitType.ARCHER, (30.5, 25.5))
    assert world.can_strike(gryphon, machine) and world.can_strike(gryphon, footman)
    assert world.can_strike(archer, gryphon) and not world.can_strike(footman, gryphon)
    with pytest.raises(RuleError):
        world.attack([footman.id], gryphon.id)
    world.attack([gryphon.id], machine.id)
    run(world, 12.0)
    assert machine.id not in world.units, "the gryphon brings the flying machine down"
    world.attack([gryphon.id], footman.id)
    hp = footman.hp
    run(world, 4.0)
    assert footman.hp < hp and gryphon.hp == gryphon.max_hp, "it strikes the walker, which cannot strike back"


def test_a_gryphon_left_to_itself_fights_what_flies_by_and_a_shot_from_it_starts_in_the_air() -> None:
    world = grass()
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (10.5, 10.5))
    machine = world.spawn_unit(1, UnitType.FLYING_MACHINE, (15.5, 10.5))
    world.hold([machine.id])
    for _ in range(round(4.0 / SIM_DT)):
        world.step()
        if world.projectiles:
            break
    assert isinstance(gryphon.order, Attack) and gryphon.order.target == machine.id
    shot = next(iter(world.projectiles.values()))
    assert shot.source_type == UnitType.GRYPHON.value and shot.target == machine.id
    assert projectile_point(shot, world, shot.launched)[2] > FLIGHT, "loosed from the rider's hand, where the view draws it"


# -- The goblin sapper: its blow is its end ----------------------------------------------------------------------------


def orcs() -> World:
    return grass(races=(Race.ORC, Race.HUMAN))


def test_a_sapper_brings_a_tower_down_in_one_blast_and_is_gone_with_it() -> None:
    world = orcs()
    tower = world.place_building(1, BuildingType.TOWER, (20, 10))
    sapper = world.spawn_unit(0, UnitType.SAPPER, (12.5, 11.5))
    world.attack([sapper.id], tower.id)
    events = []
    for _ in range(round(8.0 / SIM_DT)):
        world.step()
        events += world.take_events()
        if sapper.id not in world.units:
            break
    assert sapper.id not in world.units and tower.hp < tower.max_hp * 0.4, tower.hp
    assert [e.kind for e in events].count("blast") == 1 and not any(e.kind == "death" and e.entity == sapper.id for e in events)
    stats = world.players[0].stats
    assert stats["units_lost"] == 0, "spent, not lost"
    assert world.players[1].stats["units_killed"] == 0, "and nobody is credited with it"


def test_a_sappers_blast_takes_its_own_side_and_spares_the_air() -> None:
    world = orcs()
    farm = world.place_building(1, BuildingType.FARM, (20, 10))
    sapper = world.spawn_unit(0, UnitType.SAPPER, (19.0, 12.5))
    friend = world.spawn_unit(0, UnitType.FOOTMAN, (19.0, 13.4))
    foe = world.spawn_unit(1, UnitType.FOOTMAN, (18.3, 12.0))
    over = world.spawn_unit(1, UnitType.FLYING_MACHINE, (19.2, 12.2))
    far = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 20.5))
    for unit in (friend, foe, over, far):
        world.hold([unit.id])
    world.attack([sapper.id], farm.id)
    run(world, 2.0)
    assert sapper.id not in world.units
    assert friend.hp < friend.max_hp and foe.hp < foe.max_hp, "every unit on the ground in the blast, its own side's too"
    assert over.hp == over.max_hp and far.hp == far.max_hp, "a flyer is above it, and the blast reaches 1.5 tiles"
    assert farm.hp < farm.max_hp
    assert world.players[0].stats["units_lost"] == (friend.id not in world.units), "the friend it takes is lost, the sapper is not"


def test_the_orcs_say_what_their_sappers_keg_does_to_the_units_beside_it() -> None:
    """What a player reads of it, on the card and in the codex, is the race's summary: the number is the rules'."""
    summary = RACES[Race.ORC].units[UnitType.SAPPER].summary
    assert f"{UNITS[UnitType.SAPPER].blast_units} to all beside it, yours too" in summary, summary
    assert not any("{" in race.units[u].summary for race in RACES.values() for u in race.units), "a number left unfilled"


def test_a_sapper_picks_no_fight_with_a_unit_of_its_own_accord_and_takes_a_building_in_sight() -> None:
    world = orcs()
    sapper = world.spawn_unit(0, UnitType.SAPPER, (10.5, 10.5))
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (12.5, 10.5))
    world.hold([footman.id])
    footman.orders.clear()  # it stands there without answering either, so only the sapper's own judgement is looked at
    run(world, 2.0)
    assert sapper.id in world.units and not sapper.orders, "a footman beside it is no mark for its keg"
    tower = world.place_building(1, BuildingType.TOWER, (13, 6))
    run(world, 4.0)
    assert sapper.id not in world.units and tower.hp < tower.max_hp


def test_a_sapper_ordered_at_a_unit_blows_beside_it() -> None:
    world = orcs()
    sapper = world.spawn_unit(0, UnitType.SAPPER, (10.5, 10.5))
    knight = world.spawn_unit(1, UnitType.KNIGHT, (14.5, 10.5))
    world.hold([knight.id])
    world.attack([sapper.id], knight.id)
    run(world, 3.0)
    assert sapper.id not in world.units and knight.hp < knight.max_hp


def test_a_sapper_cannot_be_ordered_at_a_flyer() -> None:
    world = orcs()
    sapper = world.spawn_unit(0, UnitType.SAPPER, (10.5, 10.5))
    machine = world.spawn_unit(1, UnitType.FLYING_MACHINE, (12.5, 10.5))
    with pytest.raises(RuleError):
        world.attack([sapper.id], machine.id)


# -- The treant: through the forest ------------------------------------------------------------------------------------


WOOD = [(x, y) for x in range(16, 24) for y in range(2, 30)]  # a wood from the bottom edge to two rows short of the top


def elves(**kwargs) -> World:
    return grass(races=(Race.ELF, Race.HUMAN), **kwargs)


def test_a_treant_crosses_a_forest_a_footman_walks_round() -> None:
    world = elves(trees=WOOD)
    treant = world.spawn_unit(0, UnitType.TREANT, (8.5, 20.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 22.5))
    world.move([treant.id], (32.5, 20.5))
    world.move([footman.id], (32.5, 22.5))
    run(world, 16.0)
    assert dist(treant.pos, (32.5, 20.5)) < 0.2 and not treant.orders, treant.pos
    assert dist(footman.pos, (32.5, 22.5)) > 8.0, "the footman is still on its way round the top of the wood"
    assert not world.passable(20, 20) and world.ground_of(treant)[20 * world.width + 20] == 0, "the trees stay trees"


def test_a_treants_ground_keeps_step_with_felling_regrowth_and_buildings() -> None:
    world = elves(trees=WOOD)
    treant = world.spawn_unit(0, UnitType.TREANT, (8.5, 20.5))
    world.move([treant.id], (12.5, 20.5))
    run(world, 0.5)  # it has planned once: its grid is built
    ground = world.ground_of(treant)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (15.5, 12.5))
    world.harvest([peasant.id], (16, 12))
    run(world, 12.0)
    assert world.terrain_at((16, 12)) is Terrain.GRASS and ground[12 * world.width + 16] == 0, "felled: open as it was"
    world.players[0].upgrades.add(Upgrade.REGROWTH)
    world.regrowth.append(((10, 5), world.time))
    world.terrain[5][10] = Terrain.GRASS
    run(world, 1.5)
    assert world.terrain_at((10, 5)) is Terrain.TREES and ground[5 * world.width + 10] == 0, "grown back: still open to it"
    farm = world.place_building(0, BuildingType.FARM, (26, 19))
    assert all(ground[y * world.width + x] for x, y in farm.tiles()), "a building is as solid to it as to anybody"
    world.move([treant.id], (27.5, 20.0))
    run(world, 14.0)
    assert not farm.contains(treant.pos) and dist(treant.pos, (27.5, 20.0)) < 2.0
    farm.hp = 0  # razed: the ground opens again
    run(world, 0.1)
    assert not any(ground[y * world.width + x] for x, y in farm.tiles())
    world.move([treant.id], (27.5, 20.0))
    run(world, 4.0)
    assert dist(treant.pos, (27.5, 20.0)) < 0.2


def test_a_treant_mends_among_trees_out_of_the_fight_and_nowhere_else() -> None:
    world = elves(trees=[(20, 10)])
    rooted = world.spawn_unit(0, UnitType.TREANT, (21.5, 10.5))  # beside a tree
    bare = world.spawn_unit(0, UnitType.TREANT, (5.5, 25.5))  # on open ground
    for treant in (rooted, bare):
        world.hold([treant.id])
        treant.hp = treant.max_hp - 100
    run(world, 10.0)
    assert bare.hp == bare.max_hp - 100, "no tree near it: nothing mends"
    assert rooted.hp > rooted.max_hp - 100 + 10, "among trees, once the fight is six seconds behind it"
    rooted.hp = rooted.max_hp - 100
    archer = world.spawn_unit(1, UnitType.ARCHER, (25.5, 10.5))
    world.attack([archer.id], rooted.id)
    run(world, 8.0)
    assert rooted.hp < rooted.max_hp - 100, "under the arrows it mends nothing"


# -- The rune golem: the wild golem's slam, bound ----------------------------------------------------------------------


def test_a_rune_golems_slam_catches_the_foes_round_its_mark_and_spares_its_side() -> None:
    world = grass(races=(Race.DWARF, Race.HUMAN))
    golem = world.spawn_unit(0, UnitType.RUNE_GOLEM, (10.5, 10.5))
    mark = world.spawn_unit(1, UnitType.FOOTMAN, (11.6, 10.5))
    beside = world.spawn_unit(1, UnitType.FOOTMAN, (12.2, 11.4))
    friend = world.spawn_unit(0, UnitType.FOOTMAN, (12.2, 9.6))
    for unit in (mark, beside, friend):
        world.hold([unit.id])
        unit.orders.clear()
    world.attack([golem.id], mark.id)
    events = []
    for _ in range(round(3.0 / SIM_DT)):
        world.step()
        events += world.take_events()
    hit = {e.other for e in events if e.kind == "hit" and e.entity == golem.id}
    assert {mark.id, beside.id} <= hit and friend.id not in hit, "the foe beside its mark is caught, its own beside it spared"
    assert not golem.info.living, "a construct: no healer mends it"


def test_blasting_powder_is_the_mortars_not_the_golems() -> None:
    world = grass(races=(Race.DWARF, Race.HUMAN))
    golem = world.spawn_unit(0, UnitType.RUNE_GOLEM, (10.5, 10.5))
    mortar = world.spawn_unit(0, UnitType.CATAPULT, (14.5, 10.5))
    before = world.splash_of(golem), world.splash_of(mortar)
    world.players[0].upgrades.add(Upgrade.BLASTING_POWDER)
    assert world.splash_of(golem) == before[0] and world.splash_of(mortar) > before[1]


# -- Bound to its race, after the Keep, three at once -------------------------------------------------------------------


def raised(race: Race) -> tuple[World, object]:
    """A world where *race* has the building its own unit trains at, the Keep, farms and money for plenty."""
    world = grass(races=(race, Race.HUMAN if race is not Race.HUMAN else Race.ORC))
    unit = OWN_UNITS[race]
    building = world.place_building(0, RACES[race].units[unit].trained_at, (4, 4))
    for i in range(4):
        world.place_building(0, BuildingType.TOWN_HALL, (10 + 4 * i, 20))
    world.players[0].gold = world.players[0].lumber = 100_000
    world.players[0].upgrades.add(Upgrade.KEEP)
    return world, building


@pytest.mark.parametrize("race", list(Race))
def test_a_race_trains_its_own_unit_after_the_keep_and_no_other_races(race: Race) -> None:
    world, building = raised(race)
    own = OWN_UNITS[race]
    for other in Race:
        if other is not race:
            unit = OWN_UNITS[other]
            if unit in building.info.trains:
                assert "unit" in world.can_train(building, unit)
                with pytest.raises(RuleError):
                    world.train(building.id, unit)
            with pytest.raises(RuleError):
                world.order_unit(0, unit)
    world.players[0].upgrades.discard(Upgrade.KEEP)
    assert world.can_train(building, own) == f"Requires {world.upgrade_info(0, Upgrade.KEEP).name}"
    world.players[0].upgrades.add(Upgrade.KEEP)
    assert world.can_train(building, own) is None
    assert RACES[race].unit_allowed(own) and all(not RACES[race].unit_allowed(OWN_UNITS[o]) for o in Race if o is not race)


def test_the_limit_counts_the_living_and_the_queued_and_refuses_the_fourth() -> None:
    world, building = raised(Race.ELF)
    world.spawn_unit(0, UnitType.TREANT, (30.5, 5.5))
    world.train(building.id, UnitType.TREANT)
    world.train(building.id, UnitType.TREANT)
    assert world.unit_count(0, UnitType.TREANT) == 3
    reason = world.can_train(building, UnitType.TREANT)
    assert reason is not None and "at most 3" in reason
    with pytest.raises(RuleError, match="at most 3"):
        world.train(building.id, UnitType.TREANT)
    with pytest.raises(RuleError, match="at most 3"):
        world.order_unit(0, UnitType.TREANT)
    with pytest.raises(RuleError, match="at most 3"):
        world.set_auto_train(building.id, UnitType.TREANT, True)
    world.cancel_train(building.id)
    world.order_unit(0, UnitType.TREANT)  # the one place left, requested: a plan counts at the settlement
    with pytest.raises(RuleError, match="at most 3"):
        world.order_unit(0, UnitType.TREANT)


def test_endless_training_stops_at_the_limit_without_a_word_and_goes_on_when_one_falls() -> None:
    world, building = raised(Race.DWARF)
    world.set_auto_train(building.id, UnitType.RUNE_GOLEM, True)
    events = []
    for _ in range(round(200.0 / SIM_DT)):
        world.step()
        events += world.take_events()
    golems = [u for u in world.units.values() if u.type is UnitType.RUNE_GOLEM]
    assert len(golems) == 3 and not building.queue
    assert not any(e.kind == "refused" for e in events), "the cap is no error to report"
    golems[0].hp = 0
    run(world, 2.0)
    assert building.queue == [UnitType.RUNE_GOLEM], "a place came free: the next one starts"


def test_a_unit_waiting_at_its_limit_holds_up_none_of_its_buildings_other_endless_recruits() -> None:
    """Knights and gryphon riders endless at one Stables: with three gryphons out the knights keep coming, and the
    gryphon, still first in turn, is the next one begun once one of the three falls."""
    world, stables = raised(Race.HUMAN)
    world.set_auto_train(stables.id, UnitType.KNIGHT, True)
    world.set_auto_train(stables.id, UnitType.GRYPHON, True)  # switched on last: first in turn

    def count(kind: UnitType) -> int:
        return sum(u.type is kind for u in world.units.values())

    run(world, 200.0)
    assert count(UnitType.GRYPHON) == 3
    knights = count(UnitType.KNIGHT)
    run(world, 100.0)
    assert count(UnitType.GRYPHON) == 3 and count(UnitType.KNIGHT) >= knights + 4, "the knights go on past the gryphons' limit"
    assert world.auto_train_next(stables) is UnitType.KNIGHT and stables.auto[0] is UnitType.GRYPHON
    next(u for u in world.units.values() if u.type is UnitType.GRYPHON).hp = 0
    run(world, 21.0)  # the knight in hand, then the next
    assert UnitType.GRYPHON in stables.queue, "a place came free: the gryphon's turn"


def test_a_race_s_own_unit_is_not_trained_endlessly_before_the_keep() -> None:
    """Refused as a single recruit is, so a Stables set to knights and gryphons never waits on a Keep nobody raised."""
    world, stables = raised(Race.HUMAN)
    world.players[0].upgrades.discard(Upgrade.KEEP)
    world.set_auto_train(stables.id, UnitType.KNIGHT, True)
    with pytest.raises(RuleError, match="Requires"):
        world.set_auto_train(stables.id, UnitType.GRYPHON, True)
    run(world, 45.0)
    assert stables.auto == [UnitType.KNIGHT] and sum(u.type is UnitType.KNIGHT for u in world.units.values()) >= 2


# -- Saves, snapshots and replays ---------------------------------------------------------------------------------------


def four_races() -> World:
    """A seat of each race, each with its own unit: a gryphon by a machine, a sapper by a tower, a treant by a wood and
    a golem by a line of footmen."""
    terrain = [[Terrain.TREES if 26 <= x < 30 else Terrain.GRASS for x in range(48)] for _ in range(32)]
    world = World(48, 32, terrain, 4, rng=random.Random(2), races=[Race.HUMAN, Race.ORC, Race.ELF, Race.DWARF])
    for player in world.players[:world.seats]:
        player.human = True
        world.reveal_all(player.id)
    world.spawn_unit(0, UnitType.GRYPHON, (6.5, 6.5))
    world.spawn_unit(3, UnitType.FLYING_MACHINE, (10.5, 6.5))
    world.spawn_unit(1, UnitType.SAPPER, (6.5, 20.5))
    world.place_building(0, BuildingType.TOWER, (12, 20))
    world.spawn_unit(2, UnitType.TREANT, (22.5, 12.5))
    world.spawn_unit(3, UnitType.RUNE_GOLEM, (40.5, 20.5))
    for i in range(3):
        world.spawn_unit(0, UnitType.FOOTMAN, (42.0 + 0.9 * i, 21.5))
    return world


def set_to_work(world: World) -> None:
    """The orders that set each of the four about its business."""
    of = {u.type: u for u in world.units.values()}
    tower = next(iter(world.buildings.values()))
    world.attack([of[UnitType.GRYPHON].id], of[UnitType.FLYING_MACHINE].id)
    world.attack([of[UnitType.SAPPER].id], tower.id)
    world.move([of[UnitType.TREANT].id], (36.5, 12.5))
    world.attack([of[UnitType.RUNE_GOLEM].id], of[UnitType.FOOTMAN].id)


def test_a_save_of_the_four_at_work_goes_on_as_the_match_would_have() -> None:
    world = four_races()
    set_to_work(world)
    world.step()
    copy = World.from_dict(world.to_dict())
    for _ in range(round(10.0 / SIM_DT)):
        world.step()
        copy.step()
    assert copy.to_dict() == world.to_dict()


def test_the_four_replay_to_the_bit() -> None:
    from warband.records.replay import Playback, Replay, digest
    from warband.sim.rules import Difficulty

    world = four_races()
    replay = Replay.begin(world, seed=0, difficulty=Difficulty.MEDIUM, human=0)
    set_to_work(world)
    for _ in range(round(12.0 / SIM_DT)):
        world.step()
    assert not any(u.type is UnitType.SAPPER for u in world.units.values()), "the sapper went up"
    replay.finish(world, "stopped")
    playback = Playback(replay)
    playback.run()
    assert playback.faithful and digest(playback.world) == digest(world)


def test_a_seat_sees_a_rivals_own_unit_in_its_snapshot_and_nothing_of_its_errand() -> None:
    from warband.online.authority import WarbandMatch

    match = WarbandMatch(seed=3, races=[Race.ELF, Race.ORC])
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    treant = world.spawn_unit(0, UnitType.TREANT, (hall.center[0] + 3, hall.center[1] + 3))
    sapper = world.spawn_unit(1, UnitType.SAPPER, (hall.center[0] + 4, hall.center[1] + 3))
    world.attack([sapper.id], hall.id)
    for _ in range(4):
        match.step()
    theirs = {u["id"]: u for u in match.snapshot(0)["world"]["units"]}
    assert theirs[sapper.id]["type"] == UnitType.SAPPER.value and theirs[sapper.id]["orders"] == []
    assert theirs[treant.id]["type"] == UnitType.TREANT.value


def test_a_seat_hears_what_its_keg_struck_where_it_no_longer_sees() -> None:
    """A sapper's eyes go up with it, and the fog's next look can come the same step: its side's snapshot still carries
    the blast and the blow it struck on the rival's hall.  Started a tick later each time, one of four lands dark."""
    from warband.online.authority import WarbandMatch

    dark = []
    for delay in range(4):
        match = WarbandMatch(seed=3, races=[Race.ORC, Race.HUMAN])
        world = match.world
        hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
        spot = world.free_tile_near(hall.rect, prefer=world.player_buildings(0, BuildingType.TOWN_HALL)[0].center)
        sapper = world.spawn_unit(0, UnitType.SAPPER, (spot[0] + 0.5, spot[1] + 0.5))
        for _ in range(delay):
            match.step()
        world.attack([sapper.id], hall.id)
        while sapper.id in world.units:
            last = sapper.tile
            match.step()
        dark.append(not world.is_visible(0, last))
        news = [fields for _index, fields in match.snapshot(0)["events"]]
        assert any(e["kind"] == "blast" and e["entity"] == sapper.id for e in news), delay
        assert any(e["kind"] == "hit" and e["entity"] == sapper.id and e["other"] == hall.id for e in news), \
            f"started {delay} ticks late: its side never heard what its keg struck"
    assert any(dark), "no blast landed where its side no longer saw: the case this is for was never played"


def test_a_gryphons_wings_beat_between_its_throws_and_its_throw_is_drawn() -> None:
    """A flying machine's rotor turns on the clock whatever it does; a gryphon rider strikes, so its blow has frames of
    its own, and between blows (its cooldown past the recovery) its wings beat on rather than freezing it in the air."""
    from warband.art.textures import WALK_FRAMES
    from warband.ui.view import unit_frame

    world = grass()
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (10.5, 10.5))
    gryphon.state, gryphon.windup = "attack", 0.2
    assert unit_frame(gryphon, 0.0, 1.0) == "wind"
    gryphon.windup, gryphon.cooldown = 0.0, gryphon.info.cooldown - 0.05
    assert unit_frame(gryphon, 0.0, 1.0) == "strike"
    gryphon.cooldown = 0.2
    assert {unit_frame(gryphon, 0.0, t / 10) for t in range(10)} <= set(WALK_FRAMES)
    assert len({unit_frame(gryphon, 0.0, t / 10) for t in range(10)}) > 1
