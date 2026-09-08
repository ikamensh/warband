"""Settlement requests execute through the shared World simulation."""

import pytest

from warband.model import Build, Hold, Move, RuleError, World, dist
from warband.rules import BUILDINGS, SIM_DT, UNITS, UPGRADES, BuildingType, Terrain, UnitType, Upgrade


def settlement():
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 18))
    world.reveal_all(0)
    return world


def advance_until(world, condition, seconds=60):
    for _ in range(round(seconds / SIM_DT)):
        if condition():
            return
        world.step()
    raise AssertionError("Settlement request did not complete")


def test_a_building_planned_without_workers_survives_save_and_uses_a_new_worker():
    """Planning neither needs a selected builder nor spends money before work starts."""
    world = settlement()
    cost = BUILDINGS[BuildingType.FARM].cost
    plan_id = world.plan_building(0, BuildingType.FARM, (10, 10))
    initial = (world.players[0].gold, world.players[0].lumber)
    for _ in range(25):
        world.step()
    assert (world.players[0].gold, world.players[0].lumber) == initial
    world = World.from_dict(world.to_dict())
    assert world.player_plans(0)[0].id == plan_id
    worker = world.spawn_unit(0, UnitType.PEASANT, (8.5, 10.5))
    advance_until(world, lambda: bool(world.player_buildings(0, BuildingType.FARM, done=True)))
    advance_until(world, lambda: not world.player_plans(0), seconds=2)
    assert worker.constructing is None
    assert (world.players[0].gold, world.players[0].lumber) == (initial[0] - cost.gold, initial[1] - cost.lumber)


@pytest.mark.parametrize("rally", [None, (13.5, 7.5)])
def test_saved_assembly_gathers_combat_recruits_and_preserves_worker_help_and_local_rallies(rally):
    """A player assembly is the combat fallback; explicit building rallies still win."""
    world = settlement()
    barracks = world.place_building(0, BuildingType.BARRACKS, (8, 2))
    assembly = (16.5, 10.5)
    world.set_assembly(0, assembly)
    world.set_rally(barracks.id, rally)
    world.order_unit(0, UnitType.FOOTMAN)
    world.order_unit(0, UnitType.PEASANT)
    world = World.from_dict(world.to_dict())
    assert world.players[0].assembly == assembly
    advance_until(world, lambda: len(world.player_units(0)) == 2)
    infantry = next(unit for unit in world.player_units(0) if not unit.is_worker)
    worker = next(unit for unit in world.player_units(0) if unit.is_worker)
    assert not isinstance(worker.order, Move) and worker.auto_work
    target = rally if rally is not None else assembly
    advance_until(world, lambda: dist(infantry.pos, target) < .2)


def test_global_recruits_wait_then_share_available_producers_and_pay_once():
    """Requests can precede their barracks and funds; ready barracks share the work."""
    world = settlement()
    world.players[0].gold = 0
    for _ in range(2):
        world.order_unit(0, UnitType.FOOTMAN)
    for _ in range(25):
        world.step()
    assert len(world.player_plans(0)) == 2
    assert all("Barracks" in plan.status for plan in world.player_plans(0))
    world = World.from_dict(world.to_dict())
    first = world.place_building(0, BuildingType.BARRACKS, (7, 2))
    second = world.place_building(0, BuildingType.BARRACKS, (12, 2))
    for _ in range(20):
        world.step()
    assert all("gold" in plan.status for plan in world.player_plans(0))
    assert not first.queue and not second.queue
    world.players[0].gold = 2000
    advance_until(world, lambda: not world.player_plans(0), seconds=2)
    assert first.queue == second.queue == [UnitType.FOOTMAN]
    assert world.players[0].gold == 2000 - 2 * UNITS[UnitType.FOOTMAN].cost.gold
    advance_until(world, lambda: len(world.player_units(0)) == 2)


def test_global_upgrades_wait_for_prerequisites_without_a_stalled_unit_blocking_them():
    """Research is settlement-wide, unique, and follows its prerequisite through completion."""
    world = settlement()
    world.players[0].gold = world.players[0].lumber = 10_000
    world.place_building(0, BuildingType.BLACKSMITH, (8, 2))
    world.order_unit(0, UnitType.CATAPULT)  # no workshop; this queue must not block research
    world.order_upgrade(0, Upgrade.BLADES_1)
    world.order_upgrade(0, Upgrade.BLADES_2)
    with pytest.raises(RuleError, match="planned"):
        world.order_upgrade(0, Upgrade.BLADES_1)
    advance_until(world, lambda: Upgrade.BLADES_2 in world.players[0].upgrades, seconds=110)
    assert Upgrade.BLADES_1 in world.players[0].upgrades
    assert len(world.player_plans(0)) == 1 and world.player_plans(0)[0].type is UnitType.CATAPULT
    assert world.players[0].gold == 10_000 - sum(UPGRADES[item].cost.gold for item in (Upgrade.BLADES_1, Upgrade.BLADES_2))
    with pytest.raises(RuleError, match="researched"):
        world.order_upgrade(0, Upgrade.BLADES_2)


@pytest.mark.parametrize("interrupt", ["stop", "hold", "death"])
def test_a_planned_site_finds_a_replacement_when_its_builder_leaves(interrupt):
    """An unfinished settlement request survives a parked or dead builder without charging twice."""
    world = settlement()
    first = world.spawn_unit(0, UnitType.PEASANT, (9.5, 10.5))
    second = world.spawn_unit(0, UnitType.PEASANT, (7.5, 12.5))
    world.plan_building(0, BuildingType.FARM, (10, 10))
    advance_until(world, lambda: first.constructing is not None, seconds=5)
    farm = world.buildings[first.constructing]
    if interrupt == "death":
        first.hp = 0
        world.step()
    else:
        getattr(world, interrupt)([first.id])
    paid = (world.players[0].gold, world.players[0].lumber)
    advance_until(world, lambda: farm.builder == second.id, seconds=10)
    assert first.id not in world.units or not first.auto_work
    advance_until(world, lambda: farm.done)
    assert (world.players[0].gold, world.players[0].lumber) == paid


@pytest.mark.parametrize("phase", ["pending", "travelling", "building"])
def test_cancelling_a_saved_building_plan_releases_its_worker_and_refunds_only_paid_work(phase):
    """Cancellation stays safe before payment, during approach, and after a construction shell exists."""
    world = settlement()
    initial = (world.players[0].gold, world.players[0].lumber)
    plan_id = world.plan_building(0, BuildingType.FARM, (10, 10))
    if phase != "pending":
        worker = world.spawn_unit(0, UnitType.PEASANT, (7.5, 10.5))
        advance_until(world, lambda: world.player_plans(0)[0].worker is not None, seconds=2)
        if phase == "building":
            advance_until(world, lambda: worker.constructing is not None, seconds=5)
    world = World.from_dict(world.to_dict())
    world.cancel_plan(0, plan_id)
    for _ in range(40):
        world.step()
    assert not world.player_plans(0)
    assert not world.player_buildings(0, BuildingType.FARM)
    assert all(unit.constructing is None for unit in world.player_units(0))
    assert (world.players[0].gold, world.players[0].lumber) == initial


def test_planning_reassigns_a_gatherer_but_keeps_explicit_movement_and_hold():
    """Settlement work may redirect gathering, while another worker's manual task stays intact."""
    world = settlement()
    mine = world.place_building(None, BuildingType.GOLD_MINE, (16, 3))
    gatherer = world.spawn_unit(0, UnitType.PEASANT, (7.5, 7.5))
    moving = world.spawn_unit(0, UnitType.PEASANT, (9.5, 10.5))
    parked = world.spawn_unit(0, UnitType.PEASANT, (10.5, 13.5))
    world.harvest([gatherer.id], mine.id)
    world.move([moving.id], (4.5, 20.5))
    world.hold([parked.id])
    world.plan_building(0, BuildingType.FARM, (10, 10))
    for _ in range(20):
        world.step()
    assert world.player_plans(0)[0].worker == gatherer.id
    assert isinstance(gatherer.order, Build)
    assert isinstance(moving.order, Move) and moving.order.target == (4.5, 20.5)
    assert isinstance(parked.order, Hold)
    advance_until(world, lambda: bool(world.player_buildings(0, BuildingType.FARM, done=True)))


def test_blueprints_validate_space_without_requiring_money_or_finished_prerequisites():
    """A future workshop is legal; overlapping or unseen footprints are not."""
    world = settlement()
    world.players[0].gold = world.players[0].lumber = 0
    assert world.can_plan_building(BuildingType.WORKSHOP, (10, 10), 0) is None
    world.plan_building(0, BuildingType.WORKSHOP, (10, 10))
    with pytest.raises(RuleError, match="planned"):
        world.plan_building(0, BuildingType.FARM, (11, 11))
    with pytest.raises(RuleError, match="Off the map"):
        world.plan_building(0, BuildingType.FARM, (31, 23))
    assert world.can_plan_building(BuildingType.FARM, (20, 10), 1) == "Unexplored"
    for _ in range(20):
        world.step()
    assert "Blacksmith" in world.player_plans(0)[0].status
