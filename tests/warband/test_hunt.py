"""A side that has lost track of its last rival goes hunting (brains.ai.Hunt): Master mirrors ran to the twenty-minute
cap with the loser down to one peasant nobody went looking for, once the scout riders that used to stumble on it were
gone (WB-064).  Every difficulty finishes such a match, on what the side itself knows."""

from __future__ import annotations

import json
import random

import pytest

from tests.warband.brain_helpers import members
from warband.brains.ai import CAMP_REACH, HUNT_FLYERS_ALONE, make_brain
from warband.brains.pro_assignments import Duty
from warband.brains.pro_ai import PRO, ProBrain
from warband.online.authority import WarbandMatch
from warband.online.online_ai import _PlanningWorld
from warband.sim import camps, mapgen
from warband.sim.model import AttackMove, Move, World, dist
from warband.sim.rules import SIM_DT, BuildingType, Difficulty, Race, Resource, Terrain, UnitType

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
    assert members(brain, Duty.HUNT) and set(members(brain, Duty.HUNT)) == {flyer.id}, "the flyer alone, to begin with"
    assert isinstance(flyer.order, Move)
    play(world, brain, HUNT_FLYERS_ALONE)
    soldiers = [world.units[i] for i in members(brain, Duty.HUNT) if i != flyer.id]
    assert soldiers and all(u.type is UnitType.KNIGHT for u in soldiers[:2]), [u.type for u in soldiers]


@pytest.mark.slow
@pytest.mark.source_only("the bot plans on its seat's snapshot through online_ai._PlanningWorld, a stand-in for a World")
def test_a_lost_prepared_army_clears_the_camp_hiding_the_last_peasant() -> None:
    """Seed 3's wolf den (lair 20) at (25.5, 32.5) watches the pocket where seat 1's last peasant stands at
    (20.5, 39.5): every camp-safe hunt vantage is out of knight sight, so a won online match ran its 1800 s clock
    with no winner.  The bot plans on its seat's snapshot, whose honest fog omits the unseen lair, so the prepared
    army must clear the remembered den all the same; then the hunt finds the peasant.  Slow: a whole endgame
    through the seat snapshot round-trip, several minutes of simulation."""
    match = WarbandMatch(seed=3, races=[Race.DWARF, Race.ORC])
    world = match.world
    for unit in [u for u in world.units.values() if u.player == 1]:
        unit.hp = 0  # staged, as other tests raze with hp = 0: seat 1 is down to its last peasant
    for building in [b for b in world.buildings.values() if b.player == 1]:
        building.hp = 0
    # The last peasant first: seat 1 must hold its captured tile before anything steps, or the razing ends the match.
    worker = world.spawn_unit(1, UnitType.PEASANT, (20.5, 39.5))  # the captured last-unit tile, never seen by seat 0
    # The captured load-bearing state (worker 404): 100 lumber aboard and Harvest (19, 38) queued through the
    # public order; the simulation prepends the Deposit trip for a laden peasant, and home stays None.
    worker.carrying, worker.carry = Resource.LUMBER, 100
    world.harvest([worker.id], (19, 38))
    for _ in range(20):
        match.step()
    world.reveal_all(0)  # seat 0's late-game memory: the whole map honestly learned, both dens known
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for i in range(12):
        world.spawn_unit(0, UnitType.KNIGHT, (hall.center[0] + 2 + i % 4, hall.center[1] + 2 + i // 4))
    world.update_vision()
    peasant = next(u for u in world.units.values() if u.player == 1)
    assert not world.is_visible(0, peasant.tile)
    brain = make_brain(0, Difficulty.HARD, match.seed)
    rng = random.Random(match.seed)
    for _ in range(round(900.0 / SIM_DT)):
        if world.winner is not None:
            break
        if world.time >= brain.next_think:
            planning = _PlanningWorld(json.loads(json.dumps(match.snapshot(0)))["world"])
            brain.think(planning, rng)
            for command in planning.commands:
                match.apply(0, command)
        match.step()
    assert world.winner == 0, "the prepared army never cleared the den hiding the last peasant"


def test_three_searchers_keep_out_of_the_remembered_watch() -> None:
    """The remembered camp is a candidate for the prepared army now, but the hunt's small party must still keep
    out of its watch: every search destination stays outside what the guards hold, through the public orders."""
    world = World(48, 40, [[Terrain.GRASS] * 48 for _ in range(40)], 2,
                  races=[Race.DWARF, Race.ORC], rng=random.Random(5))
    world.scripted = True
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (40, 32)).hp = 0
    camp = camps.place_encounter(world, (30, 25), "wolf_den")
    soldiers = [world.spawn_unit(0, UnitType.KNIGHT, (8.5 + i, 10.5)) for i in range(3)]
    world.spawn_unit(1, UnitType.PEASANT, (45.5, 3.5))
    for _ in range(5):
        world.step()  # the razed hall falls before seat 0 learns the map, so nothing of the rival is remembered
    world.reveal_all(0)
    world.buildings[camp.lair].hp = 0  # remembered and uncleared, as the online copy sees it
    for _ in range(5):
        world.step()
    world.update_vision()
    world.time = 200.0
    ProBrain(0, PRO).think(world, random.Random(5))
    anchor = camps.centre(world, camp)
    destinations = [unit.orders[0].target for unit in soldiers
                    if unit.orders and isinstance(unit.orders[0], (Move, AttackMove))]
    assert destinations, "the lost side sent no searchers out"
    assert all(dist(target, anchor) > CAMP_REACH for target in destinations), \
        "a searcher was sent inside the remembered camp's watch"


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
    assert all(not members(brain, Duty.HUNT) for brain in brains)
