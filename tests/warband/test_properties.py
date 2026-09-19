"""Properties of the path finder and the model over many inputs rather than a few chosen ones (WB-042): a path steps
legally and is the shortest there is; a seed the game chooses leads to a fair map; two loads of a save play on alike;
an order the rules refuse leaves no trace, and nothing but a RuleError refuses one; a recording with orders of any
kind and value plays back to its match. Each runs a few examples in the fast tier and many in the slow one."""

import json
import math
import random

import pytest
from hypothesis import HealthCheck, assume, given, reject, settings
from hypothesis import strategies as st

from warband.sim import mapgen, path
from warband.brains.ai import make_brain
from warband.sim.model import RuleError, World
from warband.records.replay import Playback, Replay, digest
from warband.sim.rules import BuildingType, Difficulty, Layout, UnitType, Upgrade
from warband.ui.scene import FAIR_TRIES, fair_map

FEW = settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
MANY = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


# -- Paths --------------------------------------------------------------------------


@st.composite
def grids(draw):
    """A small grid with some of it blocked, and two open tiles on it."""
    width, height = draw(st.integers(3, 14)), draw(st.integers(3, 14))
    density = draw(st.sampled_from((0.0, 0.2, 0.35, 0.5)))
    rng = random.Random(draw(st.integers(0, 2**32 - 1)))
    blocked = bytearray(1 if rng.random() < density else 0 for _ in range(width * height))
    open_tiles = [(i % width, i // width) for i in range(width * height) if not blocked[i]]
    assume(len(open_tiles) >= 2)
    return width, height, blocked, draw(st.sampled_from(open_tiles)), draw(st.sampled_from(open_tiles))


def legal(a, b, blocked, width, height) -> bool:
    """One move from tile *a* to *b*: a neighbour, open, and not across a blocked corner."""
    (ax, ay), (bx, by) = a, b
    if not (0 <= bx < width and 0 <= by < height) or blocked[by * width + bx]:
        return False
    dx, dy = bx - ax, by - ay
    if max(abs(dx), abs(dy)) != 1:
        return False
    return not (dx and dy and (blocked[ay * width + bx] or blocked[by * width + ax]))


def shortest(start, blocked, width, height) -> dict:
    """Every tile reachable from *start* with the cost of the cheapest way there: Dijkstra on the same moves."""
    import heapq

    costs, frontier = {start: 0.0}, [(0.0, start)]
    while frontier:
        cost, tile = heapq.heappop(frontier)
        if cost > costs[tile]:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                step = (tile[0] + dx, tile[1] + dy)
                if (dx or dy) and legal(tile, step, blocked, width, height):
                    nxt = cost + (math.sqrt(2) if dx and dy else 1.0)
                    if nxt < costs.get(step, math.inf) - 1e-12:
                        costs[step] = nxt
                        heapq.heappush(frontier, (nxt, step))
    return costs


def octile(a, b) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


def check_path(case) -> None:
    width, height, blocked, start, goal = case
    route = path.find_path_grid(start, goal, blocked, width, height)
    here, cost = start, 0.0
    for tile in route:
        assert legal(here, tile, blocked, width, height), (here, tile)
        cost += math.sqrt(2) if tile[0] != here[0] and tile[1] != here[1] else 1.0
        here = tile
    reachable = shortest(start, blocked, width, height)
    if goal in reachable:
        assert here == goal and cost == pytest.approx(reachable[goal]), (route, reachable[goal])
    else:  # as near the goal as anything reachable, by the same measure the search steers with
        assert octile(here, goal) == pytest.approx(min(octile(tile, goal) for tile in reachable))


@FEW
@given(grids())
def test_a_path_steps_legally_and_is_the_shortest_there_is(case) -> None:
    check_path(case)


@pytest.mark.slow
@MANY
@given(grids())
def test_a_path_steps_legally_and_is_the_shortest_there_is_on_many_grids(case) -> None:
    """Three hundred grids: the slow tier."""
    check_path(case)


# -- Maps ---------------------------------------------------------------------------


def check_fair_map(seed: int, size: str, players: int, layout: Layout | None) -> None:
    """At the sizes, seat counts and layouts New game offers (WB-046)."""
    width, height = mapgen.SIZES[size]
    chosen, world = fair_map(seed, width, height, players, layout=layout)
    assert seed <= chosen < seed + FAIR_TRIES and (world.width, world.height, len(world.players)) == (width, height, players)


SETTINGS = (st.integers(1, 2**31 - 1), st.sampled_from(sorted(mapgen.SIZES)), st.integers(2, 4), st.sampled_from([None, *Layout]))


@FEW
@given(*SETTINGS)
def test_a_seed_the_game_chooses_leads_to_a_fair_map(seed: int, size: str, players: int, layout: Layout | None) -> None:
    check_fair_map(seed, size, players, layout)


@pytest.mark.slow
@MANY
@given(*SETTINGS)
def test_a_seed_the_game_chooses_leads_to_a_fair_map_at_every_setting_it_offers(seed: int, size: str, players: int, layout: Layout | None) -> None:
    """Three hundred seeds, a map generated for each and some many times over: the slow tier."""
    check_fair_map(seed, size, players, layout)


# -- Saves --------------------------------------------------------------------------


def small_map(seed: int) -> World:
    """The small two-seat map of *seed*. A seed that can make no fair one is no example: a few in a thousand cannot,
    which is how WB-042 found that the New game screen crashed on one (WB-046)."""
    try:
        return mapgen.generate(seed=seed, width=48, height=40, players=2, human=None)
    except mapgen.NoFairMap:
        reject()


def played(seed: int, ticks: int) -> World:
    """A small map two Medium brains have played for *ticks* ticks."""
    world = small_map(seed)
    brains, rng = [make_brain(player, Difficulty.MEDIUM, seed) for player in range(2)], random.Random(seed)
    for _ in range(ticks):
        for brain in brains:
            brain.think(world, rng)
        world.step()
    return world


def check_save(seed: int, ticks: int) -> None:
    """Two loads of one save are the same world and play on alike: loading is all in the save, with nothing left
    over from another world. Not the original, WB-042 found, twice over: a load brings sight up to date with where
    the units stand, where a match only does so every few ticks, so it can know a few more tiles than was saved; and
    a unit's path, its replanning clock and its progress watchdog are not saved, so a peasant walking when the match
    was saved plans afresh (one stood idle 18 steps on where the original walked). Nothing needs more: replays play
    from the start and the order log, and the online authority is the one world there is."""
    saved = json.dumps(played(seed, ticks).to_dict())
    first, second = World.from_dict(json.loads(saved)), World.from_dict(json.loads(saved))
    for _ in range(40):
        assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)
        first.step()
        second.step()


@settings(max_examples=2, deadline=None)
@given(st.integers(0, 10**6), st.integers(0, 60))
def test_two_loads_of_a_save_play_on_alike(seed: int, ticks: int) -> None:
    check_save(seed, ticks)


@pytest.mark.slow
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(0, 10**6), st.integers(0, 1200))
def test_two_loads_of_a_save_play_on_alike_from_any_moment(seed: int, ticks: int) -> None:
    """Forty matches up to a minute in: the slow tier."""
    check_save(seed, ticks)


# -- Orders -------------------------------------------------------------------------


def order(data, world: World):
    """A World order with arguments of the right kinds and any values: ids that exist or do not, points on the map
    or off it, any building, unit or upgrade, for any seat in the match."""
    ids = sorted(world.units) + sorted(world.buildings) + [0, 9999]
    units = data.draw(st.lists(st.sampled_from(ids), max_size=4))
    one = data.draw(st.sampled_from(ids))
    point = (data.draw(st.floats(-2.0, world.width + 2.0)), data.draw(st.floats(-2.0, world.height + 2.0)))
    tile = (data.draw(st.integers(-1, world.width)), data.draw(st.integers(-1, world.height)))
    # The seats in the match: an order for one that is not raises IndexError (or, for -1, acts for the last seat),
    # which nothing online can send, since the authority gives each seat's orders with that seat's own index.
    player = data.draw(st.integers(0, len(world.players) - 1))
    queue = data.draw(st.booleans())
    building, unit = data.draw(st.sampled_from(list(BuildingType))), data.draw(st.sampled_from(list(UnitType)))
    upgrade = data.draw(st.sampled_from(list(Upgrade)))
    orders = {
        "move": lambda: world.move(units, point, queue=queue),
        "attack_move": lambda: world.attack_move(units, point, queue=queue),
        "patrol": lambda: world.patrol(units, point, queue=queue),
        "attack": lambda: world.attack(units, one, queue=queue),
        "stop": lambda: world.stop(units),
        "hold": lambda: world.hold(units),
        "release_workers": lambda: world.release_workers(units),
        "harvest a mine": lambda: world.harvest(units, one, queue=queue),
        "harvest a tree": lambda: world.harvest(units, tile, queue=queue),
        "build": lambda: world.build(one, building, tile, queue=queue, plan_if_short=data.draw(st.booleans())),
        "repair": lambda: world.repair(units, one, queue=queue),
        "train": lambda: world.train(one, unit),
        "cancel_train": lambda: world.cancel_train(one, data.draw(st.integers(-3, 3))),
        "research": lambda: world.research(one, upgrade),
        "cancel_research": lambda: world.cancel_research(one),
        "set_rally": lambda: world.set_rally(one, data.draw(st.none() | st.just(point))),
        "set_auto_train": lambda: world.set_auto_train(one, unit, data.draw(st.booleans())),
        "smart": lambda: world.smart(units, point, queue=queue),
        "cancel_building": lambda: world.cancel_building(one),
        "resume_construction": lambda: world.resume_construction(units, one),
        "plan_building": lambda: world.plan_building(player, building, tile),
        "order_unit": lambda: world.order_unit(player, unit),
        "order_upgrade": lambda: world.order_upgrade(player, upgrade),
        "cancel_plan": lambda: world.cancel_plan(player, data.draw(st.integers(-1, 5))),
        "set_assembly": lambda: world.set_assembly(player, data.draw(st.none() | st.just(point))),
    }
    return data.draw(st.sampled_from(sorted(orders))), orders


def check_orders(data, world: World) -> None:
    for _ in range(data.draw(st.integers(1, 6))):
        name, orders = order(data, world)
        before = json.dumps(world.to_dict(), sort_keys=True)
        try:
            orders[name]()
        except RuleError:
            assert json.dumps(world.to_dict(), sort_keys=True) == before, f"{name} was refused and still changed the match"
        world.step()


@FEW
@given(st.data())
def test_a_refused_order_leaves_no_trace(data) -> None:
    check_orders(data, played(7, 0))


@pytest.mark.slow
@MANY
@given(st.data(), st.integers(0, 10**6), st.integers(0, 600))
def test_a_refused_order_leaves_no_trace_at_any_moment_of_a_match(data, seed: int, ticks: int) -> None:
    """Three hundred sequences of orders put to matches up to half a minute in: the slow tier."""
    check_orders(data, played(seed, ticks))


# -- Replays ------------------------------------------------------------------------


def check_replay(data, seed: int, ticks: int) -> None:
    """Orders of any kind and value given among two brains' at any moments: the recording, through JSON, plays back
    to the match it recorded, bit for bit."""
    world = small_map(seed)
    replay = Replay.begin(world, seed=seed, difficulty=Difficulty.MEDIUM, human=0)
    brains, rng = [make_brain(player, Difficulty.MEDIUM, seed) for player in range(2)], random.Random(seed)
    moments = sorted(data.draw(st.lists(st.integers(0, ticks), max_size=8)))
    for tick in range(ticks + 1):
        for _ in range(moments.count(tick)):
            name, orders = order(data, world)
            try:
                orders[name]()
            except RuleError:
                pass
        for brain in brains:
            brain.think(world, rng)
        world.step()
    replay.finish(world, "victory")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    assert digest(playback.run()) == digest(world)
    assert json.dumps(playback.world.to_dict(), sort_keys=True) == json.dumps(world.to_dict(), sort_keys=True)


@settings(max_examples=3, deadline=None)
@given(st.data(), st.integers(0, 10**6), st.integers(0, 60))
def test_a_recording_with_any_orders_plays_back_to_the_match(data, seed: int, ticks: int) -> None:
    check_replay(data, seed, ticks)


@pytest.mark.slow
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.data(), st.integers(0, 10**6), st.integers(0, 600))
def test_a_recording_with_any_orders_plays_back_to_the_match_at_any_length(data, seed: int, ticks: int) -> None:
    """Sixty matches up to half a minute long: the slow tier."""
    check_replay(data, seed, ticks)
