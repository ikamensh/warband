"""A side that has lost track of its last rival goes hunting (brains.ai.Hunt): Master mirrors ran to the twenty-minute
cap with the loser down to one peasant nobody went looking for, once the scout riders that used to stumble on it were
gone (WB-064).  Every difficulty finishes such a match, on what the side itself knows."""

from __future__ import annotations

import random

import pytest

from warband.brains.ai import HUNT_FLYERS_ALONE, make_brain
from warband.brains.pro_ai import PRO, ProBrain
from warband.sim import mapgen
from warband.sim.model import Move, World
from warband.sim.rules import SIM_DT, BuildingType, Difficulty, Terrain, UnitType

WIDTH, HEIGHT = 64, 48


def endgame(hideout: tuple[float, float], *, flyer: bool = False) -> World:
    """Seat 0's army stands on the ground its expedition guessed the rival started from, the far corner, and has razed
    everything there; seat 1 is down to one peasant, off in the fog at *hideout*.  A band of trees and a pond on the way,
    so the search is over ground and not across an empty board."""
    terrain = [[Terrain.GRASS] * WIDTH for _ in range(HEIGHT)]
    for y in range(18, 30):
        for x in range(20, 26):
            terrain[y][x] = Terrain.TREES
        for x in range(40, 46):
            terrain[y][x] = Terrain.WATER
    world = World(WIDTH, HEIGHT, terrain, 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(0, BuildingType.FARM, (8, 2))
    for i in range(4):
        world.spawn_unit(0, UnitType.PEASANT, (3.5 + i, 7.5))
    for i, unit_type in enumerate([UnitType.FOOTMAN] * 4 + [UnitType.ARCHER] * 3 + [UnitType.KNIGHT] * 2):
        world.spawn_unit(0, unit_type, (WIDTH - 5.5 + (i % 3), HEIGHT - 5.5 + i // 3))
    if flyer:
        world.spawn_unit(0, UnitType.FLYING_MACHINE, (WIDTH - 7.5, HEIGHT - 7.5))
    world.spawn_unit(1, UnitType.PEASANT, hideout)
    world.update_vision()
    return world


def play(world: World, brain, seconds: float) -> None:
    rng = random.Random(3)
    for _ in range(round(seconds / SIM_DT)):
        if world.winner is not None:
            return
        brain.think(world, rng)
        world.step()
        world.take_events()


@pytest.mark.parametrize("difficulty", [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.MASTER, Difficulty.GRANDMASTER])
@pytest.mark.parametrize("hideout", [(WIDTH - 3.5, 3.5), (3.5, HEIGHT - 3.5)], ids=["far-east", "far-south"])
def test_a_side_that_lost_its_rival_hunts_down_the_last_peasant(difficulty: Difficulty, hideout) -> None:
    world = endgame(hideout)
    peasant = next(u for u in world.units.values() if u.player == 1)
    assert not world.is_visible(0, peasant.tile)
    play(world, make_brain(0, difficulty, 7), 150.0)
    assert world.winner == 0, "the match still has its last peasant standing in the fog"


def test_where_the_hunt_looks_is_what_the_side_knows_not_where_the_rival_is() -> None:
    """Two matches the same but for where the last peasant stands in the fog: the searchers are sent to the same places.
    The hunt reads the side's own fog and memory, never the world's truth."""
    orders = []
    for hideout in [(WIDTH - 3.5, 3.5), (3.5, HEIGHT - 3.5)]:
        world = endgame(hideout)
        brain = ProBrain(0, PRO)
        play(world, brain, 2.0)
        orders.append(sorted((u.id, u.orders[0].target) for u in world.units.values() if u.player == 0 and u.orders
                             and not u.is_worker))
    assert orders[0] and orders[0] == orders[1]


def test_the_flyer_sweeps_first_and_the_fastest_soldiers_join_it() -> None:
    world = endgame((3.5, HEIGHT - 3.5), flyer=True)
    brain = ProBrain(0, PRO)
    flyer = next(u for u in world.units.values() if u.flying)
    play(world, brain, 3.0)
    assert brain.hunt.party and set(brain.hunt.party) == {flyer.id}, "the flyer alone, to begin with"
    assert isinstance(flyer.order, Move)
    play(world, brain, HUNT_FLYERS_ALONE)
    soldiers = [world.units[i] for i in brain.hunt.party if i != flyer.id]
    assert soldiers and all(u.type is UnitType.KNIGHT for u in soldiers[:2]), [u.type for u in soldiers]


def test_nobody_hunts_while_the_expedition_still_has_its_guess_to_look_at() -> None:
    """At the start of a match nothing of the rival is known either: the expedition to where its start is guessed is
    the search then, and no soldier is taken from the army for a hunt."""
    world = mapgen.generate(seed=31, players=2, human=None)
    brains = [make_brain(p.id, Difficulty.MASTER, 31) for p in world.players[:world.seats]]
    rng = random.Random(31)
    for _ in range(round(90.0 / SIM_DT)):
        for brain in brains:
            brain.think(world, rng)
        world.step()
    assert all(not brain.hunt.party for brain in brains)
