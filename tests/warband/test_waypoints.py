"""A walk keeps its pace through the waypoints of its path (WB-017): the tick's travel is spent in full, the last step never overshoots."""

import math

import pytest

from warband.sim.model import ARRIVE, SIM_DT, World
from warband.sim.rules import BuildingType, Terrain, UnitType


def field(blocked: set[tuple[int, int]] = frozenset()) -> World:
    terrain = [[Terrain.ROCK if (x, y) in blocked else Terrain.GRASS for x in range(40)] for y in range(40)]
    world = World(40, 40, terrain, 2)
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 36))
    world.place_building(1, BuildingType.TOWN_HALL, (36, 36))
    return world


def walk(world: World, unit, target: tuple[float, float], *, limit: int = 2000) -> list[float]:
    """Step until the unit arrives; the distance it covered each tick."""
    world.move([unit.id], target)
    covered = []
    for _ in range(limit):
        before = unit.pos
        world.step()
        covered.append(math.dist(before, unit.pos))
        if unit.state == "idle":
            return covered
    raise AssertionError(f"still walking after {limit} ticks at {unit.pos}")


@pytest.mark.parametrize("target", [(25.5, 5.5), (20.5, 20.5)], ids=["straight", "diagonal"])
def test_a_long_walk_keeps_an_even_pace_and_takes_the_distance_over_the_speed(target) -> None:
    world = field()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 5.5))
    footman.facing = math.atan2(target[1] - 5.5, target[0] - 5.5)
    covered = walk(world, footman, target)
    distance, per_tick = math.dist((5.5, 5.5), target), footman.info.speed * SIM_DT
    assert len(covered) <= math.ceil(distance / per_tick) + 2, "the walk takes the distance over the speed"
    steady = covered[1:-2]
    assert steady and max(steady) <= per_tick * 1.02 and min(steady) >= per_tick * 0.98, f"no rhythm: {min(steady):.3f}–{max(steady):.3f} against {per_tick:.3f}"
    assert math.dist(footman.pos, target) <= ARRIVE, "and ends at the destination without overshooting"


def test_the_final_segment_never_overshoots() -> None:
    world = field()
    peasant = world.spawn_unit(0, UnitType.PEASANT, (5.5, 5.5))
    for target in ((5.9, 5.5), (7.2, 5.5), (9.03, 6.1)):
        walk(world, peasant, target)
        assert math.dist(peasant.pos, target) <= ARRIVE and peasant.x <= target[0] + 1e-9


def test_a_corner_is_taken_at_the_turn_rate_without_losing_the_pace() -> None:
    """A wall forces the path round a corner; the walk turns as fast as it may and spends every tick's travel."""
    wall = {(15, y) for y in range(0, 12)}  # from the top edge down to row 11: the way round is below
    world = field(wall)
    knight = world.spawn_unit(0, UnitType.KNIGHT, (10.5, 5.5))
    knight.facing = 0.0
    facings, covered = [], []
    world.move([knight.id], (20.5, 5.5))
    for _ in range(2000):
        before, heading = knight.pos, knight.facing
        world.step()
        covered.append(math.dist(before, knight.pos))
        facings.append(abs((knight.facing - heading + math.pi) % (2 * math.pi) - math.pi))
        if knight.state == "idle":
            break
    assert knight.state == "idle" and math.dist(knight.pos, (20.5, 5.5)) <= ARRIVE
    per_tick = knight.info.speed * SIM_DT
    assert max(facings) <= knight.info.turn * SIM_DT + 1e-6, "no turn beyond the turn rate in a tick"
    moving = [c for c in covered[:-2] if c > 0]
    assert sum(1 for c in moving if c < per_tick * 0.9) <= 3, "the pace holds through the corners of the path"
