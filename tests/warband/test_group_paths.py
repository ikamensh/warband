"""A group ordered together marches one shared corridor, not one full search per soldier.

A mass order makes every unit plan its whole route on the same step, each on the budget a big
map allows.  These march a crowd at a wall with a single gap and hold the shared trunk to its
contract: one full search for the corridor, short local searches for each soldier's way onto it
and to its own slot, every unit arriving, the same match playing the same twice, and a building
dropped across the corridor not stranding anyone.
"""

import random

import pytest

from warband.sim import path as pathing
from warband.sim.model import LOCAL_EXPANSIONS, World, dist
from warband.sim.rules import BuildingType, Terrain, UnitType


def field(width: int = 48, height: int = 32, walls: frozenset[tuple[int, int]] = frozenset()) -> World:
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for x, y in walls:
        terrain[y][x] = Terrain.ROCK
    return World(width, height, terrain, 2, rng=random.Random(11))


def gap_wall(width: int = 48, height: int = 32, gap: int = 16) -> frozenset[tuple[int, int]]:
    return frozenset((20, y) for y in range(height) if y != gap)


def march(world: World, count: int = 12) -> list:
    units = [world.spawn_unit(0, UnitType.FOOTMAN, (4.5 + (i % 6) * 1.2, 6.5 + (i // 6) * 1.2)) for i in range(count)]
    world.attack_move([u.id for u in units], (44.5, 16.5))
    return units


def play(world: World, seconds: float) -> None:
    for _ in range(int(seconds / 0.05)):
        world.step()
        world.take_events()


class Counter:
    """Counts grid searches by budget, delegating to the real search."""

    def __init__(self) -> None:
        self.full = 0
        self.local = 0
        self._real = pathing.find_path_grid

    def __call__(self, start, goal, blocked, width, height, *, max_expansions=3000):
        if max_expansions == LOCAL_EXPANSIONS:
            self.local += 1
        else:
            self.full += 1
        return self._real(start, goal, blocked, width, height, max_expansions=max_expansions)


@pytest.mark.source_only("counts searches by patching path.find_path_grid, which compiled callers call directly")
def test_group_move_plans_one_corridor(monkeypatch) -> None:
    world = field(walls=gap_wall())
    counter = Counter()
    monkeypatch.setattr(pathing, "find_path_grid", counter)
    units = march(world)
    play(world, 60.0)
    assert counter.full == 1, f"one trunk for the group, not one search per soldier: {counter.full} full, {counter.local} local"
    for u in units:
        assert not u.orders, f"unit {u.id} never arrived: {u.pos} with {u.orders}"
        assert dist(u.pos, (44.5, 16.5)) < 12.0, f"unit {u.id} ended far from the march: {u.pos}"


def test_group_march_is_deterministic() -> None:
    def run() -> list:
        world = field(walls=gap_wall())
        units = march(world)
        play(world, 25.0)
        return [(u.x, u.y) for u in units]

    assert run() == run()


@pytest.mark.source_only("counts searches by patching path.find_path_grid, which compiled callers call directly")
def test_split_group_still_arrives(monkeypatch) -> None:
    world = field(walls=frozenset((20, y) for y in range(32)))  # a wall with no gap: two regions
    counter = Counter()
    monkeypatch.setattr(pathing, "find_path_grid", counter)
    west = [world.spawn_unit(0, UnitType.FOOTMAN, (4.5 + i, 6.5)) for i in range(4)]
    east = [world.spawn_unit(0, UnitType.FOOTMAN, (30.5 + i, 6.5)) for i in range(4)]
    world.attack_move([u.id for u in west + east], (44.5, 16.5))
    play(world, 60.0)
    assert counter.full == 2, f"one trunk per side of the wall: {counter.full} full"
    for u in west + east:
        assert not u.orders, f"unit {u.id} never finished: {u.pos} with {u.orders}"


def test_building_across_the_corridor_restarts_it() -> None:
    world = field(walls=gap_wall())
    units = march(world)
    play(world, 4.0)
    assert world._route_cache, "the march should have shared a trunk by now"
    world.place_building(0, BuildingType.FARM, (19, 15))
    assert not world._route_cache, "a new wall drops the old corridor"
    play(world, 60.0)
    for u in units:
        assert not u.orders, f"unit {u.id} stranded by the new building: {u.pos} with {u.orders}"
