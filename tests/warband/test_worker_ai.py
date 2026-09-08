"""Idle-worker decisions use the same orders and information as a human player."""

from copy import deepcopy

import pytest

from warband.model import Deposit, Harvest, Move, World, dist
from warband.rules import BuildingType, GOLD_PER_TRIP, MINE_GOLD, Resource, SIM_DT, Terrain, UnitType


def economy():
    terrain = [[Terrain.GRASS] * 24 for _ in range(18)]
    terrain[8][5] = Terrain.TREES
    world = World(24, 18, terrain, 2)
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (19, 13))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (7, 3))
    worker = world.spawn_unit(0, UnitType.PEASANT, (5.5, 6.5))
    world.update_vision()
    return world, worker, mine


def run(world, seconds):
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_idle_worker_mines_when_crystals_are_the_shortage():
    """An unassigned peasant should turn a known nearby deposit into usable income."""
    world, worker, mine = economy()
    world.players[0].gold = 0
    world.players[0].lumber = 1000
    run(world, 15)
    assert world.players[0].gold > 0
    assert mine.gold < MINE_GOLD


def test_idle_worker_chops_when_lumber_is_the_shortage():
    """The same visible choices produce wood income when existing stocks need it."""
    world, worker, mine = economy()
    world.players[0].gold = 2000
    world.players[0].lumber = 0
    run(world, 1.1)
    assert isinstance(worker.order, Harvest) and worker.order.target == (5, 8)
    run(world, 15)
    assert world.players[0].lumber > 0


@pytest.mark.parametrize("command", ["stop", "hold"])
def test_parking_a_worker_survives_save_load(command):
    """Stop and Hold remain player decisions even after several automatic-work checks or a load."""
    world, worker, _mine = economy()
    getattr(world, command)([worker.id])
    saved_position = worker.pos
    world = World.from_dict(world.to_dict())
    worker = world.units[worker.id]
    initial = (world.players[0].gold, world.players[0].lumber)
    run(world, 15)
    assert worker.pos == saved_position
    assert (world.players[0].gold, world.players[0].lumber) == initial


def test_queued_movement_finishes_before_a_worker_resumes_useful_work():
    """A worker completes both player waypoints before automatic harvesting can start."""
    world, worker, _mine = economy()
    world.players[0].gold = 0
    world.players[0].lumber = 1000
    world.move([worker.id], (15.5, 6.5))
    world.move([worker.id], (5.5, 6.5), queue=True)
    run(world, 3)
    assert worker.x > 10
    assert not any(isinstance(order, Harvest) for order in worker.orders)
    assert world.players[0].gold == 0
    run(world, 22)
    assert world.players[0].gold > 0


def test_new_assignments_account_for_workers_already_gathering():
    """Empty stocks need both resources; assigning a batch must not send everyone to the same one."""
    world, first, _mine = economy()
    workers = [first] + [world.spawn_unit(0, UnitType.PEASANT, (5.5 + i * .3, 6.5)) for i in range(1, 5)]
    world.players[0].gold = world.players[0].lumber = 0
    run(world, 1.1)
    targets = [order.target for worker in workers for order in worker.orders if isinstance(order, Harvest)]
    assert any(isinstance(target, int) for target in targets)
    assert targets.count((5, 8)) == 1


def test_visible_archer_danger_makes_a_worker_choose_a_safe_resource():
    """Workers avoid a valuable mine covered by visible enemy fire while still gathering nearby wood."""
    world, worker, _mine = economy()
    scout = world.spawn_unit(0, UnitType.SCOUT, (12.5, 11.5))
    archer = world.spawn_unit(1, UnitType.ARCHER, (11.5, 4.5))
    world.hold([scout.id, archer.id])
    world.players[0].gold = 0
    world.players[0].lumber = 1000
    world.update_vision()
    run(world, 1.1)
    assert isinstance(worker.order, Harvest)
    assert worker.order.target == (5, 8)


@pytest.mark.parametrize("queue", [False, True])
def test_miner_obeys_a_move_given_while_inside_the_deposit(queue):
    """Mining finishes its current trip, then honours a replacement or queued manual command."""
    world, worker, mine = economy()
    world.harvest([worker.id], mine.id)
    for _ in range(100):
        world.step()
        if worker.inside is not None:
            break
    assert worker.inside == mine.id
    target = (5.5, 11.5)
    world.move([worker.id], target, queue=queue)
    for _ in range(120):
        world.step()
        if worker.inside is None:
            break
    assert isinstance(worker.order, Move) and worker.order.target == target
    assert worker.carry > 0


@pytest.mark.parametrize("command", ["stop", "hold"])
def test_a_miner_can_be_parked_without_discarding_its_current_cargo(command):
    """A mining trip may complete, but its automatic delivery must not override Stop or Hold."""
    world, worker, mine = economy()
    world.harvest([worker.id], mine.id)
    for _ in range(100):
        world.step()
        if worker.inside is not None:
            break
    assert worker.inside == mine.id
    getattr(world, command)([worker.id])
    run(world, 6)
    position = worker.pos
    assert worker.inside is None and worker.carry > 0
    run(world, 3)
    assert worker.pos == position
    assert not any(isinstance(order, Harvest) for order in worker.orders)


def distant_mine(*, remembered):
    world = World(32, 20, [[Terrain.GRASS] * 32 for _ in range(20)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (27, 15))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (17, 3))
    worker = world.spawn_unit(0, UnitType.PEASANT, (5.5, 6.5))
    world.players[0].gold, world.players[0].lumber = 0, 1000
    if remembered:
        world.reveal_all(0)
    world.update_vision()
    return world, worker, mine


def test_an_idle_worker_does_not_discover_an_unseen_deposit_by_magic():
    """A resource that has never entered the player's view cannot generate an automatic order."""
    world, worker, mine = distant_mine(remembered=False)
    run(world, 2)
    assert not world.is_explored(0, mine.pos)
    assert not worker.orders


@pytest.mark.parametrize("hidden_change", ["empty_mine", "removed_mine", "terrain", "enemy"])
def test_unobserved_changes_do_not_change_a_remembered_resource_decision(hidden_change):
    """Saved observations must drive identical orders and routes until new facts become visible."""
    original, worker, mine = distant_mine(remembered=True)
    saved = original.to_dict()
    changed = deepcopy(saved)
    if hidden_change == "empty_mine":
        next(building for building in changed["buildings"] if building["id"] == mine.id)["gold"] = 0
    elif hidden_change == "removed_mine":
        changed["buildings"] = [building for building in changed["buildings"] if building["id"] != mine.id]
    elif hidden_change == "terrain":
        row = list(changed["terrain"][6])
        row[12] = Terrain.ROCK.value[0]
        changed["terrain"][6] = "".join(row)
    worlds = [World.from_dict(saved), World.from_dict(changed)]
    if hidden_change == "enemy":
        enemy = worlds[1].spawn_unit(1, UnitType.FOOTMAN, (12.5, 6.5))
        worlds[1].hold([enemy.id])
    observations = []
    for world in worlds:
        actor = world.units[worker.id]
        run(world, 1.4)
        assert not world.is_visible(0, mine.pos)
        assert isinstance(actor.order, Harvest) and actor.order.target == mine.id
        observations.append((actor.pos, actor.path, actor.order))
    assert observations[0] == observations[1]


def test_automatic_harvesting_routes_around_visible_enemy_fire():
    """A safe destination is not enough: every actual journey must avoid a visible archer's range."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (1, 10))
    world.place_building(1, BuildingType.TOWN_HALL, (27, 19))
    world.place_building(None, BuildingType.GOLD_MINE, (15, 10))
    worker = world.spawn_unit(0, UnitType.PEASANT, (5.5, 11.5))
    observer = world.spawn_unit(0, UnitType.SCOUT, (10.5, 1.5))
    enemy = world.spawn_unit(1, UnitType.ARCHER, (10.5, 7.5))
    world.hold([observer.id, enemy.id])
    world.players[0].gold, world.players[0].lumber = 0, 1000
    world.reveal_all(0)
    world.update_vision()
    for _ in range(round(25 / SIM_DT)):
        world.step()
        if not worker.hidden:
            assert dist(worker.pos, enemy.pos) > enemy.info.range + enemy.radius + worker.radius
    assert worker.hp == worker.max_hp
    assert world.players[0].gold > 0


def test_a_remembered_tower_stays_dangerous_until_its_destruction_is_observed():
    """Forgetting an unseen tower would reveal its destruction and send workers into known danger."""
    world, worker, mine = distant_mine(remembered=True)
    tower = world.place_building(1, BuildingType.TOWER, (17, 8))
    world.reveal_all(0)
    world.update_vision()
    saved = world.to_dict()
    changed = deepcopy(saved)
    changed["buildings"] = [building for building in changed["buildings"] if building["id"] != tower.id]
    original, destroyed = World.from_dict(saved), World.from_dict(changed)
    for match in (original, destroyed):
        run(match, 1.4)
        assert not match.is_visible(0, tower.pos)
        assert not match.units[worker.id].orders
    destroyed.reveal_all(0)
    run(destroyed, 1.2)
    order = destroyed.units[worker.id].order
    assert isinstance(order, Harvest) and order.target == mine.id


def test_loading_an_automatic_worker_carrying_crystals_preserves_delivery_and_followup_work():
    """A loaded save must deliver the existing load once, then continue its automatic harvesting cycle."""
    world, worker, _mine = economy()
    world.players[0].gold, world.players[0].lumber = 0, 1000
    for _ in range(round(12 / SIM_DT)):
        world.step()
        if worker.carrying is Resource.GOLD and isinstance(worker.order, Deposit):
            break
    assert worker.carry == GOLD_PER_TRIP
    assert isinstance(worker.order, Deposit) and worker.orders[1].auto
    restored = World.from_dict(world.to_dict())
    loaded = restored.units[worker.id]
    assert loaded.carry == GOLD_PER_TRIP and loaded.carrying is Resource.GOLD
    assert isinstance(loaded.order, Deposit) and loaded.orders[1].auto and loaded.auto_work
    run(restored, 20)
    assert restored.players[0].gold >= 2 * GOLD_PER_TRIP
    assert any(isinstance(order, Harvest) and order.auto for order in loaded.orders)


def test_worker_metadata_preserves_existing_online_order_dictionaries():
    """Old online clients can decode orders while new authority retains automatic-route state."""
    world, worker, _mine = economy()
    world.players[0].gold, world.players[0].lumber = 0, 1000
    run(world, 1.1)
    assert isinstance(worker.order, Harvest) and worker.order.auto
    saved = world.to_dict()
    unit = next(item for item in saved['units'] if item['id'] == worker.id)
    assert set(unit['orders'][0]) == {'kind', 'target'}
    restored = World.from_dict(saved)
    assert restored.units[worker.id].order.auto
    for _ in range(round(12 / SIM_DT)):
        restored.step()
        if isinstance(restored.units[worker.id].order, Deposit):
            break
    saved = restored.to_dict()
    unit = next(item for item in saved['units'] if item['id'] == worker.id)
    assert unit['orders'][0] == {'kind': 'Deposit'}
    assert World.from_dict(saved).units[worker.id].order.auto
