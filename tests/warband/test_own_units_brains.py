"""The computer players and each race's own unit (WB-068, ``warband.brains.unique``): bought only when what the side
knows says it is the answer, and sent at what it is for.  Each decision on a staged world."""

import json
import random

from warband.brains import unique
from warband.brains.ai import Brain
from warband.brains.pro_ai import PRO_VANGUARD, ProBrain
from warband.sim.model import Attack, AttackMove, Move, World, dist
from warband.sim.rules import SIM_DT, BuildingType, Difficulty, Race, Terrain, UnitType, Upgrade

H, O, E, D = Race.HUMAN, Race.ORC, Race.ELF, Race.DWARF


def field(race: Race, *, width: int = 60, height: int = 40, trees=(), rival: Race = Race.HUMAN) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in trees:
        terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 2, rng=random.Random(3), races=[race, rival], human=None)
    world.place_building(0, BuildingType.TOWN_HALL, (3, 3))
    world.place_building(1, BuildingType.TOWN_HALL, (width - 6, height - 6))
    world.reveal_all(0)
    return world


# -- When it is worth buying ------------------------------------------------------------------------------------------


def test_gryphons_answer_catapults_flyers_and_a_shooter_light_army_never_massed_shooters() -> None:
    world = field(H)
    assert unique.wanted(world, 0, {UnitType.CATAPULT: 1, UnitType.FOOTMAN: 6}, False)
    assert unique.wanted(world, 0, {UnitType.FLYING_MACHINE: 1, UnitType.FOOTMAN: 3, UnitType.ARCHER: 1}, False)
    assert unique.wanted(world, 0, {UnitType.FOOTMAN: 5, UnitType.KNIGHT: 3}, False), "a shooter-light army"
    assert not unique.wanted(world, 0, {UnitType.CATAPULT: 2, UnitType.ARCHER: 6, UnitType.FOOTMAN: 4}, False), "massed shooters"
    assert not unique.wanted(world, 0, {UnitType.FOOTMAN: 2, UnitType.ARCHER: 1}, False), "nothing to hunt, too few to judge"
    assert not unique.wanted(world, 0, {}, False)


def test_sappers_answer_a_tower_line_or_a_hall_within_reach() -> None:
    world = field(O, width=120, height=40)
    assert not unique.wanted(world, 0, {}, False), "the rival hall is 110 tiles off and not seen"
    world.place_building(1, BuildingType.TOWER, (60, 20))
    world.reveal_all(0)
    assert not unique.wanted(world, 0, {}, False), "one tower is no line"
    world.place_building(1, BuildingType.TOWER, (63, 20))
    world.reveal_all(0)
    assert unique.wanted(world, 0, {}, False)
    near = field(O, width=40, height=30)
    assert unique.wanted(near, 0, {}, False), "a known rival hall within reach"


def test_golems_answer_a_melee_heavy_army() -> None:
    world = field(D)
    assert unique.wanted(world, 0, {UnitType.FOOTMAN: 5, UnitType.KNIGHT: 2, UnitType.ARCHER: 1}, False)
    assert not unique.wanted(world, 0, {UnitType.FOOTMAN: 2, UnitType.ARCHER: 5}, False)
    assert not unique.wanted(world, 0, {UnitType.FOOTMAN: 3}, False), "too few to be a line worth a slam"


def test_treants_are_worth_it_when_a_forest_route_cuts_the_way_to_the_rival() -> None:
    wood = [(x, y) for x in range(20, 40) for y in range(0, 36)]  # a wood across the map, open only along its bottom
    world = field(E, trees=wood)
    commander = unique.Commander()
    assert commander.route_pays(world, 0) and unique.wanted(world, 0, {}, commander.route_pays(world, 0))
    open_map = field(E)
    assert not unique.Commander().route_pays(open_map, 0), "on open ground the wood is no shortcut"


def keep_and(world: World, building: BuildingType) -> None:
    world.players[0].upgrades.add(Upgrade.KEEP)
    world.players[0].gold = world.players[0].lumber = 20_000
    world.place_building(0, building, (10, 3))
    for i in range(3):
        world.place_building(0, BuildingType.FARM, (3 + 3 * i, 10))
    for i in range(4):
        world.spawn_unit(0, UnitType.PEASANT, (2.5 + i, 14.5))  # a side with nobody left thinks of nothing but recovering
    for i in range(unique.UNIQUE_ARMY):
        world.spawn_unit(0, UnitType.FOOTMAN, (2.5 + i, 17.5))  # the army its own unit is the centrepiece of


def trained(world: World, brain, seconds: float = 3.0) -> list[UnitType]:
    rng = random.Random(0)
    for _ in range(round(seconds / SIM_DT)):
        brain.think(world, rng)
        world.step()
    return [unit_type for b in world.player_buildings(0) for unit_type in b.queue]


def test_master_buys_gryphons_when_it_has_seen_a_catapult_and_not_otherwise() -> None:
    for seen in (False, True):
        world = field(H)
        keep_and(world, BuildingType.STABLES)
        if seen:
            world.spawn_unit(1, UnitType.CATAPULT, (14.5, 8.5))
            world.reveal_all(0)
        assert (UnitType.GRYPHON in trained(world, ProBrain(0, PRO_VANGUARD))) == seen, "nothing seen: knights, as the plan says"


def test_a_posture_that_may_not_buy_its_own_unit_never_does() -> None:
    from dataclasses import replace

    world = field(H)
    keep_and(world, BuildingType.STABLES)
    world.spawn_unit(1, UnitType.CATAPULT, (14.5, 8.5))
    world.reveal_all(0)
    assert UnitType.GRYPHON not in trained(world, ProBrain(0, replace(PRO_VANGUARD, unique=False)))


def test_medium_buys_golems_against_the_melee_it_sees() -> None:
    world = field(D)
    keep_and(world, BuildingType.CHURCH)
    for i in range(6):
        world.spawn_unit(1, UnitType.FOOTMAN, (14.5 + i, 9.5))
    world.reveal_all(0)
    assert UnitType.RUNE_GOLEM in trained(world, Brain(0, Difficulty.MEDIUM))


# -- What it is for ---------------------------------------------------------------------------------------------------


def test_a_gryphon_hunts_a_flying_machine_and_a_lone_archer_but_not_massed_shooters() -> None:
    world = field(H)
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (12.5, 12.5))
    massed = [world.spawn_unit(1, UnitType.ARCHER, (20.5 + i, 12.5)) for i in range(4)]
    commander = unique.Commander()
    world.reveal_all(0)
    assert not commander.step(world, 0, [gryphon], None), "four archers together: no prey there"
    lone = world.spawn_unit(1, UnitType.ARCHER, (12.5, 20.5))
    world.reveal_all(0)
    assert commander.step(world, 0, [gryphon], None) == {gryphon.id}
    assert isinstance(gryphon.order, Attack) and gryphon.order.target == lone.id
    machine = world.spawn_unit(1, UnitType.FLYING_MACHINE, (13.5, 10.5))
    world.reveal_all(0)
    gryphon.orders.clear()
    commander.errands.clear()
    commander.step(world, 0, [gryphon], None)
    assert gryphon.order.target == machine.id, "the nearest prey"
    assert all(a.hp == a.max_hp for a in massed)


def test_a_sapper_runs_at_an_unguarded_tower_near_and_turns_back_when_a_soldier_comes_at_it() -> None:
    world = field(O)
    sapper = world.spawn_unit(0, UnitType.SAPPER, (8.5, 12.5))
    far = world.place_building(1, BuildingType.TOWER, (44, 12))
    world.reveal_all(0)
    unique.Commander().step(world, 0, [sapper], None)
    assert not sapper.orders, "a tower across the map is a sapper met on the way: it waits for a push"
    far.hp = 0  # razed: it goes at the next step
    world.step()
    tower = world.place_building(1, BuildingType.TOWER, (20, 12))
    world.reveal_all(0)
    commander = unique.Commander()
    assert commander.step(world, 0, [sapper], None) == {sapper.id}
    assert isinstance(sapper.order, Attack) and sapper.order.target == tower.id
    for _ in range(round(2.0 / SIM_DT)):
        world.step()
    world.spawn_unit(1, UnitType.KNIGHT, (sapper.x + 2.0, sapper.y))
    world.reveal_all(0)
    commander.step(world, 0, [sapper], None)
    assert isinstance(sapper.order, Move), "caught on the way: it runs back to our side"
    guarded = field(O)
    world, sapper = guarded, guarded.spawn_unit(0, UnitType.SAPPER, (8.5, 12.5))
    tower = world.place_building(1, BuildingType.TOWER, (20, 12))
    for i in range(3):
        world.spawn_unit(1, UnitType.FOOTMAN, (21.5 + i, 15.5))
    world.reveal_all(0)
    unique.Commander().step(world, 0, [sapper], None)
    assert not (isinstance(sapper.order, Attack) and sapper.order.target == tower.id), "a tower with soldiers by it waits for the push"
    unique.Commander().step(world, 0, [sapper], (21.0, 16.0))
    assert isinstance(sapper.order, Attack) and sapper.order.target == tower.id, "the push is its escort"


def test_a_sapper_is_sent_at_the_towers_its_side_remembers_razed_out_of_its_sight_or_not() -> None:
    """Bound by the fog: two towers seen once, then the fog closes and one of them is razed where the side does not
    look.  To the side both stand: sappers are still the answer to them, and the one sent walks to the spot it
    remembers, since what stands there now is not its to know; once it sees a tower there, it goes at the tower."""
    world = field(O)
    razed = world.place_building(1, BuildingType.TOWER, (16, 14))
    world.place_building(1, BuildingType.TOWER, (40, 30))
    world.reveal_all(0)
    sapper = world.spawn_unit(0, UnitType.SAPPER, (4.5, 14.5))
    world.update_vision()  # the fog closes: what the hall and the sapper see
    assert not world.any_visible(0, razed.rect)
    razed.hp = 0
    world.step()
    assert razed.id not in world.buildings and razed.id in world.worker_knowledge[0].buildings
    assert unique.wanted(world, 0, {}, False), "two towers, as far as the side knows"
    commander = unique.Commander()
    commander.step(world, 0, [sapper], None)
    assert isinstance(sapper.order, Move) and dist(sapper.order.target, (17.0, 15.0)) < 0.5, sapper.order
    rebuilt = world.place_building(1, BuildingType.TOWER, (18, 16))  # what it finds there
    for _ in range(round(3.0 / SIM_DT)):
        world.step()
        commander.step(world, 0, [sapper], None)
        if isinstance(sapper.order, Attack):
            break
    assert isinstance(sapper.order, Attack) and sapper.order.target == rebuilt.id, sapper.order


def test_a_side_remembers_the_kind_of_what_it_saw_and_keeps_it_through_a_save() -> None:
    world = field(O)
    tower = world.place_building(1, BuildingType.TOWER, (16, 14))
    world.reveal_all(0)
    assert world.worker_knowledge[0].buildings[tower.id].type is BuildingType.TOWER
    data = json.loads(json.dumps(world.to_dict()))
    assert World.from_dict(data).worker_knowledge[0].buildings[tower.id].type is BuildingType.TOWER
    for knowledge in data["worker_knowledge"]:
        for remembered in knowledge["buildings"]:
            del remembered["type"]
    assert World.from_dict(data).worker_knowledge[0].buildings[tower.id].type is None, "a save from before: a kind not remembered"


def test_a_gryphon_takes_a_shooter_for_lone_when_its_side_sees_no_other_by_it() -> None:
    world = field(H)
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (12.5, 12.5))
    archer = world.spawn_unit(1, UnitType.ARCHER, (16.5, 12.5))
    unseen = world.spawn_unit(1, UnitType.ARCHER, (20.5, 12.5))  # within LONE of it, beyond the gryphon's sight
    world.update_vision()
    assert world.is_visible(0, archer.tile) and not world.is_visible(0, unseen.tile)
    assert unique.Commander().step(world, 0, [gryphon], None) == {gryphon.id}
    assert isinstance(gryphon.order, Attack) and gryphon.order.target == archer.id, "what it cannot see is no company"


def test_a_treant_flanks_the_push_by_the_building_among_the_trees() -> None:
    trees = [(x, y) for x in range(44, 60) for y in range(22, 30)]
    world = field(E, trees=trees)
    near_wood = world.place_building(1, BuildingType.BARRACKS, (48, 30))
    world.place_building(1, BuildingType.FARM, (52, 36))
    world.reveal_all(0)
    treant = world.spawn_unit(0, UnitType.TREANT, (20.5, 20.5))
    commander = unique.Commander()
    assert not commander.step(world, 0, [treant], None), "no push: it stands with the army"
    assert commander.step(world, 0, [treant], (54.0, 34.0)) == {treant.id}
    assert isinstance(treant.order, Attack) and treant.order.target == near_wood.id


def test_a_golem_goes_for_the_thickest_knot_of_melee() -> None:
    world = field(D)
    golem = world.spawn_unit(0, UnitType.RUNE_GOLEM, (10.5, 12.5))
    world.spawn_unit(1, UnitType.FOOTMAN, (14.5, 8.5))  # alone
    knot = [world.spawn_unit(1, UnitType.FOOTMAN, (14.5 + 0.8 * (i % 2), 15.0 + 0.8 * (i // 2))) for i in range(4)]
    world.reveal_all(0)
    assert unique.Commander().step(world, 0, [golem], None) == {golem.id}
    assert isinstance(golem.order, Attack) and golem.order.target in {u.id for u in knot}


def test_a_side_buys_its_own_unit_with_an_army_to_lead_and_invests_in_it_from_idle_gold_alone() -> None:
    world = field(D)
    for i in range(6):
        world.spawn_unit(1, UnitType.FOOTMAN, (14.5 + i, 9.5))
    world.reveal_all(0)
    seen = {UnitType.FOOTMAN: 6.0}
    commander = unique.Commander()
    assert not commander.answer(world, 0, seen), "no army: the opening's soldiers come first"
    for i in range(unique.UNIQUE_ARMY):
        world.spawn_unit(0, UnitType.FOOTMAN, (2.5 + i, 17.5))
    assert commander.answer(world, 0, seen), "the army it would lead: bought, where its building and the Keep stand"
    assert commander.waits_for(world, 0, seen) == () and commander.building(world, 0, seen) is None, \
        "but no Keep and no Rune Shrine out of an army's money"
    world.players[0].gold, world.players[0].lumber = unique.IDLE_GOLD, 1000
    assert commander.waits_for(world, 0, seen) == (Upgrade.KEEP,)
    assert commander.building(world, 0, seen) is BuildingType.CHURCH, "the Rune Shrine it is trained at"
    brain = ProBrain(0, PRO_VANGUARD)
    brain._seen = {1: dict(seen)}  # private: what it remembers of the rival, the melee line, staged rather than played for
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for _ in range(round(3.0 / SIM_DT)):
        brain.think(world, random.Random(0))
        world.step()
    assert hall.research is Upgrade.KEEP, "raised first, the hall kept free of recruits for it"


def test_a_sapper_caught_by_a_knot_of_rivals_takes_them_with_it() -> None:
    world = field(O)
    sapper = world.spawn_unit(0, UnitType.SAPPER, (12.5, 12.5))
    knot = [world.spawn_unit(1, UnitType.FOOTMAN, (13.4 + 0.5 * (i % 2), 11.9 + 0.8 * (i // 2))) for i in range(3)]
    world.reveal_all(0)
    unique.Commander().step(world, 0, [sapper], None)
    assert isinstance(sapper.order, Attack) and sapper.order.target in {u.id for u in knot}
    for _ in range(round(1.5 / SIM_DT)):
        world.step()
    assert sapper.id not in world.units and all(u.hp < u.max_hp for u in knot)
