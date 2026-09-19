"""Endless training and sites left as plans: the two rules the controls rework asked of the simulation.

A building can train one or several unit types for ever; several take turns.  It starts a recruit only when
it stands idle and the player can pay from what their unpaid orders (plans, builders on their way) have not
claimed: what a player asked for comes before what they left running.  A builder a player sends out with
``plan_if_short`` leaves a site it cannot pay for as a plan instead of giving it up.
"""

import json

import pytest

from warband.records.replay import Playback, Replay, digest
from warband.sim.model import Build, RuleError, World
from warband.sim.rules import BUILDINGS, SIM_DT, UNITS, UPGRADES, BuildingType, Cost, Difficulty, Terrain, UnitType, Upgrade


def settlement(*, gold: int = 10_000, lumber: int = 10_000, farms: int = 3) -> World:
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 18))
    for i in range(farms):
        world.place_building(0, BuildingType.FARM, (2 + 3 * i, 20))
    world.reveal_all(0)
    world.players[0].gold, world.players[0].lumber = gold, lumber
    return world


def run(world: World, seconds: float) -> list[str]:
    """Step *seconds* of match and return what player 0 trained meanwhile, in order."""
    trained = []
    for _ in range(round(seconds / SIM_DT)):
        world.step()
        trained += [e.target_type for e in world.take_events() if e.kind == "trained" and e.player == 0]
    return trained


def run_until(world: World, condition, seconds: float = 120) -> list[str]:
    trained = []
    for _ in range(round(seconds / SIM_DT)):
        if condition(trained):
            return trained
        trained += run(world, SIM_DT)
    raise AssertionError(f"not reached in {seconds} s; trained {trained}")


def test_two_types_on_endless_training_take_turns() -> None:
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    world.set_auto_train(barracks.id, UnitType.ARCHER, True)
    trained = run_until(world, lambda t: len(t) == 4)
    assert trained == ["footman", "archer", "footman", "archer"]
    gold = sum(UNITS[t].cost.gold for t in (UnitType.FOOTMAN, UnitType.ARCHER)) * 2 + UNITS[UnitType.FOOTMAN].cost.gold  # the fifth is under way
    assert world.players[0].gold == 10_000 - gold and barracks.queue == [UnitType.FOOTMAN]


def test_switched_on_endless_training_starts_at_once() -> None:
    """A player switched it on, saw nothing happen for half a second and clicked again, which switched it off (their
    autosave of 2026-09-19): an idle building that can pay starts the recruit as the order is given."""
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    run(world, 0.5)  # between two of the building's once-a-second looks
    world.set_auto_train(barracks.id, UnitType.ARCHER, True)
    assert barracks.queue == [UnitType.ARCHER]


def test_a_new_building_takes_up_the_endless_training_its_kind_shares() -> None:
    """A player met it (their autosave of 2026-09-19): endless archers at their barracks, two more barracks built, and
    those stood idle for over a minute until the order was given again.  A site takes up what every building of its
    kind its owner has trains endlessly, and trains it once it stands; kin that disagree hand down nothing."""
    world = settlement()
    first = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(first.id, UnitType.ARCHER, True)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (14.5, 8.5))
    world.build(peasant.id, BuildingType.BARRACKS, (14, 2))
    run_until(world, lambda t: peasant.constructing is not None, seconds=10)
    second = world.buildings[peasant.constructing]
    assert second.auto == [UnitType.ARCHER]
    run_until(world, lambda t: bool(second.queue), seconds=BUILDINGS[BuildingType.BARRACKS].build_time + 2)
    assert second.queue == [UnitType.ARCHER]
    world.set_auto_train(second.id, UnitType.ARCHER, False)
    assert world.place_building(0, BuildingType.BARRACKS, (20, 2)).auto == []


def test_a_recruit_walks_out_and_the_next_starts_the_same_step() -> None:
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    run_until(world, lambda t: bool(barracks.queue), seconds=1.1)
    run_until(world, lambda t: t == ["footman"])
    assert barracks.queue == [UnitType.FOOTMAN] and barracks.train_progress == 0.0


def test_endless_training_waits_for_gold_and_farms_and_says_why() -> None:
    world = settlement(gold=0, farms=0)
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    run(world, 2.0)
    assert barracks.queue == [] and world.auto_train_blocker(barracks) == "Not enough gold (600 needed)"
    world.players[0].gold = 600
    run(world, 1.05)
    assert barracks.queue == [UnitType.FOOTMAN] and world.players[0].gold == 0
    world.players[0].gold = 10_000
    for i in range(4):  # the hall feeds five: one in training, four standing
        world.spawn_unit(0, UnitType.PEASANT, (6.5 + i, 8.5))
    run_until(world, lambda t: t == ["footman"])
    run(world, 2.0)
    assert barracks.queue == [] and world.auto_train_blocker(barracks) == "Not enough farms"


def test_a_plan_waiting_for_lumber_holds_back_no_gold() -> None:
    """What a player asked for is paid first, but gold does not sit idle while the lumber a plan waits for comes in.

    The case a player met (their autosave of 2026-09-19): a Barracks planned without its lumber held its 700 gold
    back from the hall, whose endless peasants stood idle for seconds with 1000 gold in the purse.  Once its lumber
    is there the plan holds its gold as well, so endless training cannot starve it; cancelled, it holds nothing."""
    world = settlement(gold=1000, lumber=0)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    plan = world.plan_building(0, BuildingType.BARRACKS, (12, 12))
    world.set_auto_train(hall.id, UnitType.PEASANT, True)
    run(world, 1.05)
    assert hall.queue == [UnitType.PEASANT] and world.committed(0) == Cost(0, 0)
    barracks = BUILDINGS[BuildingType.BARRACKS].cost
    world.players[0].gold, world.players[0].lumber = 1000, barracks.lumber  # no worker to send: the plan waits, its money there
    assert world.committed(0) == barracks and world.auto_train_blocker(hall) == "Your plans are paid first"
    world.cancel_plan(0, plan)
    assert world.committed(0) == Cost(0, 0) and world.auto_train_blocker(hall) is None


def test_a_builder_on_its_way_holds_the_price_of_its_site() -> None:
    world = settlement(gold=1200)
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (3.5, 16.5))
    world.build(peasant.id, BuildingType.BARRACKS, (24, 2))
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    run(world, 2.0)
    assert world.committed(0) == BUILDINGS[BuildingType.BARRACKS].cost and barracks.queue == []  # 500 gold spare, a footman is 600
    run_until(world, lambda t: isinstance(peasant.order, Build) and peasant.order.building is not None, seconds=30)
    assert world.committed(0).gold == 0 and world.players[0].gold == 500
    world.players[0].gold = UNITS[UnitType.FOOTMAN].cost.gold
    run(world, 1.05)
    assert barracks.queue == [UnitType.FOOTMAN] and world.players[0].gold == 0


def test_research_planned_at_an_endless_building_goes_after_the_recruit_in_training() -> None:
    world = settlement()
    church = world.place_building(0, BuildingType.CHURCH, (8, 2))
    world.set_auto_train(church.id, UnitType.CLERIC, True)
    run_until(world, lambda t: bool(church.queue), seconds=1.1)
    world.order_upgrade(0, Upgrade.BLESSING)
    trained = run_until(world, lambda t: church.research is Upgrade.BLESSING, seconds=30)
    assert trained == ["cleric"] and church.queue == []
    run_until(world, lambda t: Upgrade.BLESSING in world.players[0].upgrades, seconds=UPGRADES[Upgrade.BLESSING].time + 1)
    run(world, 1.05)
    assert church.queue == [UnitType.CLERIC]


def test_a_recruit_ordered_by_hand_goes_before_the_endless_ones() -> None:
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(barracks.id, UnitType.ARCHER, True)
    run_until(world, lambda t: bool(barracks.queue), seconds=1.1)
    world.train(barracks.id, UnitType.FOOTMAN)
    assert run_until(world, lambda t: len(t) == 3) == ["archer", "footman", "archer"]


def test_switched_off_the_recruit_in_training_still_walks_out() -> None:
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    run_until(world, lambda t: bool(barracks.queue), seconds=1.1)
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, False)
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, False)  # off twice is still off
    assert run(world, 30.0) == ["footman"] and barracks.queue == [] and barracks.auto == []


def test_a_site_going_up_keeps_its_standing_order_and_a_save_keeps_the_turn() -> None:
    world = settlement()
    site = world.place_building(0, BuildingType.BARRACKS, (8, 2), done=False)
    world.set_auto_train(site.id, UnitType.FOOTMAN, True)
    world.set_auto_train(site.id, UnitType.ARCHER, True)
    world.set_auto_train(site.id, UnitType.ARCHER, True)  # on twice is still on, and keeps its place
    run(world, 2.0)
    assert site.queue == [] and site.auto == [UnitType.ARCHER, UnitType.FOOTMAN]  # the one switched on last goes next
    site.progress = site.info.build_time
    run(world, 1.05)
    assert site.queue == [UnitType.ARCHER] and site.auto == [UnitType.FOOTMAN, UnitType.ARCHER]
    world = World.from_dict(world.to_dict())
    assert world.buildings[site.id].auto == [UnitType.FOOTMAN, UnitType.ARCHER]
    assert run_until(world, lambda t: len(t) == 2) == ["archer", "footman"]


def test_a_rival_or_nobody_cannot_be_told_to_train_endlessly() -> None:
    world = settlement()
    mine = world.place_building(None, BuildingType.GOLD_MINE, (14, 10))
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    with pytest.raises(RuleError, match="No such building"):
        world.set_auto_train(mine.id, UnitType.PEASANT, True)
    with pytest.raises(RuleError, match="trained at the Barracks"):
        world.set_auto_train(hall.id, UnitType.FOOTMAN, True)
    assert hall.auto == []


def test_a_site_its_builder_cannot_pay_for_waits_as_a_plan_and_is_built_when_the_money_comes() -> None:
    world = settlement(gold=500, lumber=250)  # one farm's worth
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    world.build(peasant.id, BuildingType.FARM, (10, 8), plan_if_short=True)
    world.build(peasant.id, BuildingType.FARM, (13, 8), queue=True, plan_if_short=True)
    deferred = []
    for _ in range(round(40 / SIM_DT)):
        world.step()
        deferred += [e for e in world.take_events() if e.kind == "deferred"]
        if deferred:
            break
    assert deferred[0].text == "Not enough gold (500 needed): the Farm waits as a plan"
    assert [(p.type, p.pos) for p in world.player_plans(0)] == [(BuildingType.FARM, (13, 8))]
    world.players[0].gold, world.players[0].lumber = 500, 250
    run_until(world, lambda t: len(world.player_buildings(0, BuildingType.FARM, done=True)) == 5, seconds=60)
    run(world, 1.05)  # the settlement lets go of a finished plan on its next second
    assert not world.player_plans(0) and world.players[0].gold == 0


def test_without_the_flag_a_site_is_refused_as_before_and_with_it_the_builder_sets_out_unpaid() -> None:
    world = settlement(gold=500, lumber=250)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    world.build(peasant.id, BuildingType.FARM, (10, 8))
    world.build(peasant.id, BuildingType.FARM, (13, 8), queue=True)  # the purse still holds one farm when it is given
    refused = []
    for _ in range(round(40 / SIM_DT)):
        world.step()
        refused += [e.text for e in world.take_events() if e.kind in ("refused", "deferred")]
    assert refused == ["Cannot build: Not enough gold (500 needed)"] and not world.player_plans(0)
    with pytest.raises(RuleError, match="Not enough gold"):
        world.build(peasant.id, BuildingType.FARM, (13, 12))
    world.build(peasant.id, BuildingType.FARM, (13, 12), plan_if_short=True)
    assert peasant.order == Build(BuildingType.FARM, (13, 12), plan_if_short=True)


def test_a_match_with_endless_training_and_sites_left_as_plans_replays_to_the_bit() -> None:
    """The standing order is logged once and the simulation does the rest, the same way on playback."""
    world = settlement(gold=3000, lumber=800)  # the two sites claim 1000 gold and 500 lumber first
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    replay = Replay.begin(world, seed=1, difficulty=Difficulty.EASY, human=0)
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    world.set_auto_train(barracks.id, UnitType.ARCHER, True)
    world.build(peasant.id, BuildingType.FARM, (10, 8), plan_if_short=True)
    world.build(peasant.id, BuildingType.FARM, (13, 8), queue=True, plan_if_short=True)
    assert run(world, 40.0) == ["footman", "archer", "footman"]
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, False)
    run(world, 20.0)
    replay.finish(world, "victory")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    playback.run()
    assert playback.faithful and digest(playback.world) == digest(world)
    assert [row[1] for row in replay.orders][:4] == ["set_auto_train", "set_auto_train", "build", "build"]
