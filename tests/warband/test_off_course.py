"""A unit shoved off its path recovers.  Fuzz seeds 1900–1911 on 2026-09-18: six of twelve games had a
peasant bouncing for the rest of the match between its tile centre and a building corner.  Fuzz seeds
0–15 on 2026-09-20: fifteen footmen marching in a line stood between two points for the rest of theirs."""

from warband.sim.model import SIM_DT, AttackMove, Deposit, Move, World, dist, tile_center
from warband.sim.rules import GOLD_PER_TRIP, BuildingType, Resource, Terrain, UnitType


def grass(width: int, height: int, walls: frozenset[tuple[int, int]] = frozenset()) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in walls:
        terrain[y][x] = Terrain.ROCK
    world = World(width, height, terrain, 2)
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


def test_a_worker_whose_next_tile_turns_dangerous_waits_on_its_own_tile_for_its_plan() -> None:
    """When the tile ahead has just become forbidden ground (an enemy came into view) inside the unit's replan
    window, the way on is refused: the worker keeps off it and waits on its own tile for the plan, rather than
    spending its travel towards the forbidden tile and walking back (WB-017).  A straight walk passes a
    waypoint whose successor is a clear step away without going to its centre first, so the worker is caught
    just onto (11, 9) and already heading for (10, 9)."""
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
    while worker.path[0] != (10, 9):
        world.step()
    assert worker.tile == (11, 9) and world.time < worker.replan_at, (worker.pos, world.time, worker.replan_at)
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 9.5))  # its reach covers (10, 9) but not (11, 9)
    world.hold([footman.id])
    world.update_vision()
    replan = worker.replan_at
    while world.time < replan:
        world.step()
        assert worker.tile == (11, 9), (world.time, worker.pos)
    assert dist(worker.pos, (11.5, 9.5)) < 0.13, worker.pos  # waiting at its centre, not pressing on
    run(world, 20.0)
    assert worker.carrying is None and world.players[0].gold == 1000 + GOLD_PER_TRIP, (worker.pos, worker.path)


# The ground around the footman of fuzz seed 5 who stood still from 09:53 to the end of the match, as the map
# generated it: the window (54, 5)–(70, 21) of an 80×64 wasteland, rock and water south-west of where it stood.
STALL_WINDOW = (54, 5)
STALL_GROUND = ("wgggggggggggggggg", "ggggggggggggggggg", "ggggggggggggggggg", "ggggggggggggggggg",
                "gggggwwgggggggggg", "ggggwwwwggggggggg", "gggggwwwggggggggg", "ggggrrggggggggggg",
                "ggggrrggggggggggg", "ggggrrggggggggggg", "gggrrrggggggggggg", "rrrrrrggggggggggg",
                "rrrgggggggggggggg", "rrrgggggggggggggg", "wrttggggggggggggr", "wwttgggggrggggwww",
                "wrtttgggggggggwww")


def stall_world() -> World:
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    ground = [[Terrain.GRASS] * 71 for _ in range(64)]
    for dy, row in enumerate(STALL_GROUND):
        for dx, letter in enumerate(row):
            ground[STALL_WINDOW[1] + dy][STALL_WINDOW[0] + dx] = letters[letter]
    world = World(71, 64, ground, 2)
    for player in world.players:
        player.human = True
    return world


def test_a_marcher_does_not_take_a_shortcut_that_walks_it_back_up_its_own_path() -> None:
    """A unit in a marching line walks straight at its place in the line while that line is clear, instead of
    pathing to a place that moves every step.  At this spot the shortcut and the route disagreed: the shortcut
    was clear from where the footman stood, and a fifth of a tile along it the shortcut was blocked, so the
    step planned a route that walked it straight back.  It stepped between the two points, 20 times a second,
    for the remaining five minutes of the match.  The staged path and order are the ones the seed produced.
    """
    world = stall_world()
    marcher = world.spawn_unit(0, UnitType.FOOTMAN, (62.029052762287016, 13.033595984741991))
    world.attack_move([marcher.id], (2.5, 61.5))
    # The line it marched in had fallen around it, so its slot sits where the seed left it, and it is part way
    # along a route round the rock: both are state, not an order, and a fresh order would have neither.
    marcher.orders[0] = AttackMove((2.5, 61.5), pace=2.0, offset=(0.3073827445110006, 0.39435497762407523))
    marcher.path = [(62, 12), (62, 11), (62, 10), (62, 9), (61, 8)]
    marcher.path_goal = (2, 61)

    ahead = tile_center(marcher.path[0])
    before = dist(marcher.pos, ahead)
    world.step()
    assert dist(marcher.pos, ahead) < before, "the shortcut walked the marcher back up its own route"

    start = marcher.pos
    for _ in range(round(1.0 / SIM_DT)):
        world.step()
    assert dist(start, marcher.pos) > 1.0, "the marcher stepped between two points instead of getting on"


# The marching line of the gate queue (``tests/warband/test_stuck_units.py``) at 33.45 s, as a Linux run
# left it: five footmen sharing one Move, two of them still queueing at the wall and holding the line's
# middle back at the far side of the wall, and footman 7 walked right in to its slot at the front.
MARCH_TARGET = (30.5, 12.5)
MARCH_PACE = 1.3
MARCH = [
    (UnitType.FOOTMAN, (29.41217186676659, 14.766483390143815), (-0.9940185940857511, 2.2938890632748103)),   # the one that wedged
    (UnitType.FOOTMAN, (18.242869350114134, 15.486105595692344), (-0.5964111564514507, 1.3763334379648862)),
    (UnitType.FOOTMAN, (19.213069653705556, 12.332509738422743), (-0.19880371881715023, 0.45877781265496204)),
    (UnitType.FOOTMAN, (29.986885703775922, 12.313665463555179), (0.19880371881715023, -0.45877781265496204)),
    (UnitType.FOOTMAN, (30.342564602551903, 10.519656713794488), (0.9940185940857511, -2.2938890632748103)),
]


def test_a_marcher_that_has_walked_into_its_slot_does_not_march_back_out_of_it() -> None:
    """A marching line's shortcut aims at the place ahead of the line's middle.  Once a unit has walked in
    to its slot at the end, that place is *behind* it, so the shortcut cleared the unit's plan and walked it
    most of a tile back out; the next step planned the way in again, and it stepped between the two.  Its
    progress watchdog was reset at every turn, so the walk could never end either: in the gate queue of
    ``tests/warband/test_stuck_units.py`` this footman stood on its slot, in the move state, holding an
    order it had already finished, for the last three minutes of the run (on Linux, where that crowd of
    sixty-six takes a turn this Mac does not).

    The positions, the order and the offsets are the ones that run produced at 33.45 s, and the wall with
    its one open tile is what holds the two stragglers, and so the line's middle, back.  Five marchers get
    through it in seconds where sixty-six took minutes, so what is pinned here is the step out itself
    rather than how long it went on: the unit must stay in the place it reached.
    """
    world = grass(40, 24, walls=frozenset((20, y) for y in range(24) if y != 12))  # the queue's wall, one tile open
    marchers = [world.spawn_unit(0, unit_type, pos) for unit_type, pos, _offset in MARCH]
    world.move([u.id for u in marchers], MARCH_TARGET)
    for marcher, (_type, _pos, offset) in zip(marchers, MARCH):
        marcher.orders[0] = Move(MARCH_TARGET, pace=MARCH_PACE, offset=offset)  # the slots that march dealt
    watched, slot = marchers[0], (MARCH_TARGET[0] + MARCH[0][2][0], MARCH_TARGET[1] + MARCH[0][2][1])
    assert dist(watched.pos, slot) < 0.1, "the marcher starts the seed's run all but standing in its place"

    strayed = 0.0
    for _ in range(round(5.0 / SIM_DT)):
        world.step()
        strayed = max(strayed, dist(watched.pos, slot))
    assert strayed < 0.35, f"the shortcut marched it {strayed:.2f} tiles back out of the slot it had reached"
    assert not watched.orders and watched.state == "idle", (watched.pos, list(watched.orders), watched.state)
