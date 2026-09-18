"""A unit shoved off its path recovers.  Fuzz seeds 1900–1911 on 2026-09-18: six of twelve games had a
peasant bouncing for the rest of the match between its tile centre and a building corner."""

from warband.model import SIM_DT, Deposit, World, dist
from warband.rules import GOLD_PER_TRIP, BuildingType, Resource, Terrain, UnitType


def grass(width: int, height: int) -> World:
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 2)
    for player in world.players:
        player.human = True
    return world


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_a_worker_shoved_onto_a_blocked_corner_plans_again_instead_of_bouncing() -> None:
    """Fuzz seed 1908 (2 players, 80×64, minute 8), moved 60 tiles left and 46 up: peasant 31, carrying
    gold home from (67, 50) along (67, 51), (67, 52), (68, 52), (69, 53) between the blacksmith at
    (64, 51) and the farm at (68, 50), was pushed by the crowd onto (66, 50).  Its next tile was then
    the diagonal neighbour across the blacksmith's corner: a work trip walks against the grid, so every
    step towards it was refused, the unit walked back to its tile centre and set out again, for the
    rest of the match.  (A plain walk cuts the corner and gets on; only a shove of more than a tile
    was recognised as being off the path.)"""
    world = grass(20, 16)
    world.place_building(0, BuildingType.BLACKSMITH, (4, 5))
    world.place_building(0, BuildingType.FARM, (8, 4))
    world.place_building(0, BuildingType.TOWN_HALL, (10, 8))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (7.5, 4.5))
    peasant.carrying, peasant.carry = Resource.GOLD, GOLD_PER_TRIP
    peasant.orders.append(Deposit())
    world.step()
    assert peasant.path == [(7, 5), (7, 6), (8, 6), (9, 7)], peasant.path
    peasant.x, peasant.y = 6.93, 4.93  # the crowd's shove: onto the tile beside the blacksmith's corner
    run(world, 10.0)
    assert peasant.carrying is None and world.players[0].gold == 1000 + GOLD_PER_TRIP, (peasant.pos, peasant.path)
    assert peasant.state == "idle" and not peasant.orders


def test_a_worker_whose_next_tile_turns_dangerous_at_a_waypoint_waits_there_for_its_plan() -> None:
    """The tick's leftover travel goes on through a waypoint (WB-017).  When the next tile has just
    become forbidden ground (an enemy came into view) inside the unit's replan window, the way on is
    refused while the unit stands at its tile centre: it waits there for the plan instead of spending
    the leftover towards the forbidden tile and walking back to the centre next tick."""
    world = grass(30, 20)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    world.place_building(1, BuildingType.TOWN_HALL, (26, 16))
    worker = world.spawn_unit(0, UnitType.PEASANT, (12.5, 9.5))
    worker.carrying, worker.carry = Resource.GOLD, GOLD_PER_TRIP
    worker.orders.append(Deposit(auto=True))
    world.reveal_all(0)
    world.update_vision()
    world.step()
    assert worker.path[:2] == [(11, 9), (10, 9)], worker.path
    per_tick = world.speed_of(worker) * SIM_DT
    while dist(worker.pos, (11.5, 9.5)) > per_tick:
        world.step()
    assert worker.path[0] == (11, 9) and world.time < worker.replan_at
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 9.5))  # its reach covers (10, 9) but not (11, 9)
    world.hold([footman.id])
    world.update_vision()
    world.step()  # arrives at (11.5, 9.5) with travel to spare, and the tile beyond is forbidden now
    assert worker.pos == (11.5, 9.5) and worker.state == "move", (worker.pos, worker.state)
    run(world, 20.0)
    assert worker.carrying is None and world.players[0].gold == 1000 + GOLD_PER_TRIP, (worker.pos, worker.path)
