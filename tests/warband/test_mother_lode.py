"""The Mother Lode: the shared ground's other prize (WB-071).

A lode is a seam's five tiles and twelve places at the face with a mine's trip, and it runs out: it holds
:data:`LODE_GOLD`.  Where a big map puts its prize, the seed deals a seam or a lode on the same site, so the
ground is the same either way and a seed that made a fair map still makes one.
"""

from __future__ import annotations

import itertools

import pytest

from warband.sim import mapgen
from warband.sim.model import World
from warband.sim.rules import (BUILDINGS, GOLD_PER_TRIP, LODE_GOLD, LODE_PER_TRIP, LODE_SLOTS, MINE_SLOTS, SEAM_SLOTS, BuildingType,
                               Resource, SIM_DT, Terrain, UnitType)


def lode_world(workers: int = 1, gold: int | None = None) -> tuple[World, object]:
    """A hall, a lode a short walk off and in its sight, and *workers* peasants between them, on open grass."""
    terrain = [[Terrain.GRASS] * 30 for _ in range(22)]
    world = World(30, 22, terrain, 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    lode = world.place_building(None, BuildingType.MOTHER_LODE, (10, 7))
    if gold is not None:
        lode.gold = gold
    for i in range(workers):
        world.spawn_unit(0, UnitType.PEASANT, (6.5 + i % 4, 8.5 + i // 4))
    world.update_vision()
    return world, lode


def run_until(world: World, condition, max_seconds: float) -> None:
    for _ in range(round(max_seconds / SIM_DT)):
        if condition():
            return
        world.step()
    assert condition(), "the world never reached the state the test waits for"


# -- What it gives -------------------------------------------------------------------------


def test_a_lode_is_a_seams_ground_with_a_mines_trip_and_a_fortune_in_it() -> None:
    lode, seam, mine = (BUILDINGS[kind] for kind in (BuildingType.MOTHER_LODE, BuildingType.GOLD_SEAM, BuildingType.GOLD_MINE))
    assert lode.size == seam.size == 5 and lode.mine is not None and seam.mine is not None and mine.mine is not None
    assert lode.mine.slots == seam.mine.slots == LODE_SLOTS == SEAM_SLOTS > MINE_SLOTS
    assert lode.mine.trip == mine.mine.trip == LODE_PER_TRIP == GOLD_PER_TRIP
    assert not lode.mine.endless and lode.mine.rate == 1.5 * mine.mine.rate
    _world, placed = lode_world()
    assert placed.gold == LODE_GOLD and placed.has_gold, "a lode placed without a stock holds its hundred thousand"


def test_a_lode_hands_over_what_it_holds_and_is_gone_when_it_is_worked_out() -> None:
    """Three and a half trips of gold: three full loads, a half load, and the lode is exhausted like a mine."""
    stock = 3 * LODE_PER_TRIP + LODE_PER_TRIP // 2
    world, lode = lode_world(workers=4, gold=stock)
    world.players[0].gold = 0
    world.harvest([u.id for u in world.player_units(0)], lode.id)
    run_until(world, lambda: lode.id not in world.buildings, 120.0)
    assert any(e.kind == "exhausted" and e.entity == lode.id for e in world.take_events())
    run_until(world, lambda: all(u.carrying is None for u in world.player_units(0)), 60.0)
    assert world.players[0].gold == stock, "every coin in the lode came home, and not one more"


def test_a_lode_seats_a_seams_twelve_at_its_face() -> None:
    world, lode = lode_world(workers=LODE_SLOTS + 3)
    world.harvest([u.id for u in world.player_units(0)], lode.id)
    busiest = 0
    for _ in range(round(60.0 / SIM_DT)):
        world.step()
        busiest = max(busiest, sum(1 for u in world.player_units(0) if u.inside == lode.id))
    assert MINE_SLOTS < busiest <= LODE_SLOTS, f"{busiest} at the face of a lode that seats {LODE_SLOTS}"


def test_a_peasant_carries_a_mines_trip_out_of_a_lode() -> None:
    world, lode = lode_world()
    peasant = world.player_units(0)[0]
    world.harvest([peasant.id], lode.id)
    run_until(world, lambda: peasant.carrying is Resource.GOLD, 30.0)
    assert peasant.carry == LODE_PER_TRIP and lode.gold == LODE_GOLD - LODE_PER_TRIP


# -- Saved and remembered ----------------------------------------------------------------------


def test_a_lode_survives_a_save_with_its_kind_and_what_is_left() -> None:
    world, lode = lode_world(workers=2)
    world.harvest([u.id for u in world.player_units(0)], lode.id)
    run_until(world, lambda: lode.gold < LODE_GOLD, 40.0)
    kept = World.from_dict(world.to_dict()).buildings[lode.id]
    assert kept.type is BuildingType.MOTHER_LODE and kept.gold == lode.gold and kept.has_gold


def test_a_player_remembers_a_lode_as_a_rich_mine_with_twelve_places() -> None:
    """What a brain decides under fog it decides from the memory, so the memory carries the lode's own numbers."""
    world, lode = lode_world()
    known = world.worker_knowledge[0].mines[lode.id]
    assert (known.trip, known.slots, known.endless, known.gold, known.size) == (LODE_PER_TRIP, LODE_SLOTS, False, LODE_GOLD, 5)


# -- The deal ------------------------------------------------------------------------------


def test_the_seed_deals_a_seam_or_a_lode_at_even_odds_and_neighbouring_seeds_apart() -> None:
    """A ladder plays neighbouring seeds, so a seed's deal must say nothing of the next one's: a neighbour deals
    the same prize half the time, as a fair coin's next toss would.  Both bounds are over four standard errors
    of 2000 fair tosses wide."""
    deals = [mapgen.deal_prize(seed) for seed in range(2000)]
    assert set(deals) == {BuildingType.GOLD_SEAM, BuildingType.MOTHER_LODE}
    assert 0.45 < deals.count(BuildingType.MOTHER_LODE) / len(deals) < 0.55
    assert 0.45 < sum(a is b for a, b in itertools.pairwise(deals)) / (len(deals) - 1) < 0.55, "neighbours deal apart"
    assert deals == [mapgen.deal_prize(seed) for seed in range(2000)], "the deal is the seed's, every time"


def test_a_map_takes_no_prize_but_the_two() -> None:
    with pytest.raises(ValueError, match="prize"):
        mapgen.build(seed=1, width=108, height=84, players=2, prize=BuildingType.GOLD_MINE)


@pytest.mark.slow
@pytest.mark.parametrize("size, seats, layout", [("Huge", 2, mapgen.Layout.PLAINS), ("Huge", 4, mapgen.Layout.CROSSINGS),
                                                 ("Giant", 8, mapgen.Layout.BASTION)])
def test_a_lode_and_a_seam_are_dealt_on_the_same_ground(size, seats, layout) -> None:
    """The same seed with either prize is the same map, tile for tile, deposit for deposit and camp for camp, and the
    same retries: which prize a seed deals can never make a fair seed unfair.  Two big maps per case: the slow tier."""
    width, height = mapgen.dimensions(size, seats)
    seam_world, seam_report = mapgen.build(seed=4242, width=width, height=height, players=seats, layout=layout,
                                           prize=BuildingType.GOLD_SEAM)
    lode_world, lode_report = mapgen.build(seed=4242, width=width, height=height, players=seats, layout=layout,
                                           prize=BuildingType.MOTHER_LODE)
    assert lode_world.terrain == seam_world.terrain and lode_world.rifts == seam_world.rifts
    assert lode_report["attempt"] == seam_report["attempt"] and lode_report["problems"] == seam_report["problems"] == []

    def ground(world: World) -> list[tuple]:
        return sorted((b.rect, b.player, b.type.value if b.info.mine is None or b.size == 3 else "prize",
                       b.gold if b.size == 3 else 0) for b in world.buildings.values())

    assert ground(lode_world) == ground(seam_world)
    assert [c.lair for c in lode_world.camps] == [c.lair for c in seam_world.camps]
    lodes = [m for m in lode_world.mines() if m.type is BuildingType.MOTHER_LODE]
    assert len(lodes) == seats == lode_report["lodes"] and lode_report["seams"] == 0 and seam_report["seams"] == seats
    assert all(lode.gold == LODE_GOLD for lode in lodes), "every seat's lode holds the same fortune"
    for lode in lodes:  # camps guard a lode as they guard a seam: the big one, beside it
        lairs = [lode_world.buildings[c.lair] for c in lode_world.camps]
        assert min(max(abs(lair.center[0] - lode.center[0]), abs(lair.center[1] - lode.center[1])) for lair in lairs) <= 9.5


@pytest.mark.slow
def test_a_seed_deals_its_own_prize_to_every_seat() -> None:
    """Left to the seed, the prize is the one :func:`mapgen.deal_prize` names, one to a seat: the first seeds to deal
    each prize, twice over.  Whole maps: the slow tier."""
    width, height = mapgen.dimensions("Huge", 2)
    dealing = {kind: [seed for seed in range(1, 100) if mapgen.deal_prize(seed) is kind][:2]
               for kind in (BuildingType.GOLD_SEAM, BuildingType.MOTHER_LODE)}
    for seed in sorted(dealing[BuildingType.GOLD_SEAM] + dealing[BuildingType.MOTHER_LODE]):
        world, report = mapgen.build(seed=seed, width=width, height=height, players=2, layout=mapgen.Layout.PLAINS)
        dealt = mapgen.deal_prize(seed)
        assert {m.type for m in world.mines() if m.size == 5} == {dealt}
        assert report["lodes" if dealt is BuildingType.MOTHER_LODE else "seams"] == 2


# -- The brains ------------------------------------------------------------------------------


def test_a_brain_values_a_deposit_by_its_pace_and_its_stock_not_its_kind() -> None:
    """A lode pays half as fast again as a mine, so a brain takes it over a mine up to two thirds of its walk away;
    gold that runs out still goes before a seam that never does; and a lode is low when it holds the work a low
    mine holds at its own pace."""
    from warband.brains.ai import LOW_MINE_GOLD, hall_first, pace, worth_a_hall
    from warband.sim.rules import SEAM_PER_TRIP
    from warband.sim.worker_knowledge import KnownMine

    third = KnownMine(1, 10, 10, 3, 30_000)
    lode = KnownMine(2, 40, 10, 5, LODE_GOLD, LODE_PER_TRIP, LODE_SLOTS)
    seam = KnownMine(3, 70, 10, 5, 0, SEAM_PER_TRIP, SEAM_SLOTS, endless=True)
    assert pace(third) == 1.0 and pace(lode) == 1.5 and pace(seam) == pytest.approx(0.3)
    assert hall_first(lode, 25.0) < hall_first(third, 18.0), "a lode half as far again ranks with a mine"
    assert hall_first(third, 12.0) < hall_first(lode, 25.0), "a mine at half the walk still goes first"
    assert hall_first(lode, 90.0) < hall_first(seam, 5.0), "gold that runs out before gold that never does"
    low = LOW_MINE_GOLD * pace(lode)
    assert worth_a_hall(KnownMine(2, 40, 10, 5, round(low), LODE_PER_TRIP, LODE_SLOTS))
    assert not worth_a_hall(KnownMine(2, 40, 10, 5, round(low) - 1, LODE_PER_TRIP, LODE_SLOTS))
    assert worth_a_hall(KnownMine(1, 10, 10, 3, LOW_MINE_GOLD)) and not worth_a_hall(KnownMine(1, 10, 10, 3, LOW_MINE_GOLD - 1))


def test_the_league_books_the_gold_a_seat_brings_out_of_a_lode() -> None:
    """Telemetry names the deposit every load came out of, so a league can say who took the lode and when."""
    from warband.league.telemetry import Telemetry

    world, lode = lode_world(workers=3)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (4, 2))
    world.update_vision()
    world.players[0].gold = 0
    telemetry = Telemetry(world)
    peasants = [u.id for u in world.player_units(0)]
    world.harvest(peasants[:2], lode.id)
    world.harvest(peasants[2:], mine.id)
    for _ in range(round(60.0 / SIM_DT)):
        world.step()
        telemetry.observe(world, world.take_events())
    tally = telemetry.tallies[0]
    assert tally.mined["mother_lode"] == LODE_GOLD - lode.gold > 0 and tally.mined["gold_mine"] > 0
    assert sum(tally.mined.values()) == world.players[0].gold, "every coin booked to the deposit it came out of"
    assert 0 < tally.first["mined.mother_lode"] < 60.0


def camp_world(prize: BuildingType, rival_at: tuple[int, int] | None = None) -> tuple[World, object]:
    """A hall in one corner, the prize forty tiles out with a lair beside it, the whole ground seen; a rival's farm at
    *rival_at*, when given, seen too."""
    from warband.sim import camps

    world = World(80, 40, [[Terrain.GRASS] * 80 for _ in range(40)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 18))
    world.place_building(None, prize, (40, 18))
    camps.place(world, (47, 19), [UnitType.WOLF], 100)
    if rival_at is not None:
        world.place_building(1, BuildingType.FARM, rival_at)
    world.reveal_all(0)
    record = next(r for r in world.worker_knowledge[0].buildings.values() if r.player == world.neutral)
    return world, record


def test_a_camp_is_worth_the_walk_the_gold_it_keeps_is_worth_when_that_gold_is_ours_to_take() -> None:
    """A lode's camp is worth twice the ordinary walk (its hundred thousand over an expansion's thirty, capped at
    ai.CAMP_WALK); a seam's the ordinary walk; and a lode nearer a rival than us is not ours to take yet."""
    from warband.brains.ai import CAMP_WALK, camp_worth

    world, record = camp_world(BuildingType.MOTHER_LODE)
    assert camp_worth(world, 0, record) == CAMP_WALK == 2.0
    world, record = camp_world(BuildingType.GOLD_SEAM)
    assert camp_worth(world, 0, record) == 1.0
    world, record = camp_world(BuildingType.MOTHER_LODE, rival_at=(50, 16))
    assert camp_worth(world, 0, record) == 1.0


@pytest.mark.slow
def test_on_the_shipped_sizes_every_deposit_paces_as_a_mine_and_every_camp_is_worth_the_ordinary_walk() -> None:
    """The brains value a deposit by its pace and its stock, and a camp by the stock it keeps.  On the three shipped
    sizes every deposit paces as a mine and no camp keeps more than an expansion's thirty thousand, so every one of
    those values is exactly one and the brains decide there what they decided when the difficulty ratings and the
    balance league were measured.  Every layout and seat count, several seeds: the slow tier."""
    from warband.brains.ai import CAMP_REACH
    from warband.sim.model import dist
    from warband.sim.rules import EXPANSION_GOLD

    for size in ("Small", "Medium", "Large"):
        for seats in mapgen.offered(size):
            width, height = mapgen.dimensions(size, seats)
            for layout in mapgen.Layout:
                if mapgen.refusal(width, height, seats, layout) is not None:
                    continue
                for seed in (3, 77, 4177):
                    world = mapgen.generate(seed=seed, width=width, height=height, players=seats, layout=layout)
                    assert all(m.info.mine.trip * m.info.mine.slots == GOLD_PER_TRIP * MINE_SLOTS for m in world.mines())
                    for camp in world.camps:
                        lair = world.buildings[camp.lair]
                        near = [m for m in world.mines() if dist(m.center, lair.center) < CAMP_REACH]
                        assert not near or min(near, key=lambda m: dist(m.center, lair.center)).gold <= EXPANSION_GOLD, \
                            (size, seats, layout, seed)
