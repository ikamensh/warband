"""The endless deposit: what it gives, what it never does, and who knows about it.

A gold seam is five tiles across instead of three, gives :data:`SEAM_PER_TRIP` gold a trip instead of a
hundred, seats :data:`SEAM_SLOTS` peasants at its face instead of eight, and never runs out.  Everything
that decides what is worth mining asks :attr:`Building.has_gold`, of the building or of the deposit a player remembers, never the
stock, because a seam's stock is zero and always was.
"""

from __future__ import annotations

from collections import Counter

import pytest

from warband.sim import mapgen
from warband.sim.model import World, Harvest
from warband.sim.rules import (
    BUILDINGS, DEEP_MINING_TRIP, GOLD_PER_TRIP, MINE_SLOTS, SEAM_PER_TRIP, SEAM_SLOTS,
    BuildingType, Race, Resource, SIM_DT, Terrain, UnitType, Upgrade,
)


def seam_world(races: tuple[Race, Race] = (Race.HUMAN, Race.HUMAN), workers: int = 1) -> tuple[World, object]:
    """A hall, a seam a short walk off and in its sight, and *workers* peasants between them, on open grass."""
    terrain = [[Terrain.GRASS] * 30 for _ in range(22)]
    world = World(30, 22, terrain, 2, races=list(races))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    seam = world.place_building(None, BuildingType.GOLD_SEAM, (10, 7))  # near enough that the base sees it from the start
    for i in range(workers):
        world.spawn_unit(0, UnitType.PEASANT, (6.5 + i % 4, 8.5 + i // 4))
    world.update_vision()
    return world, seam


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def run_until(world: World, condition, max_seconds: float) -> None:
    for _ in range(round(max_seconds / SIM_DT)):
        if condition():
            return
        world.step()
    assert condition(), "the world never reached the state the test waits for"


# -- What it gives ---------------------------------------------------------------------


def test_a_seam_holds_no_stock_and_keeps_giving() -> None:
    """Twenty gold a trip, for ever: the number of trips that would empty a mine leaves the seam standing.

    Thirty trips is 3000 gold, which is half of what the AI calls a mine running out; a deposit holding
    that would be gone.  The seam's own ``gold`` never moves off zero, so nothing may read it as a stock.
    """
    world, seam = seam_world(workers=4)
    world.players[0].gold = 0
    world.harvest([u.id for u in world.player_units(0)], seam.id)
    run_until(world, lambda: world.players[0].gold >= 30 * SEAM_PER_TRIP, 300.0)
    assert seam.id in world.buildings, "an endless deposit is never exhausted"
    assert seam.gold == 0 and seam.has_gold, "a seam's stock is nothing; what it still gives is has_gold"
    assert world.players[0].gold % SEAM_PER_TRIP == 0, "every trip brought up exactly a seam's trip"


def test_a_peasant_carries_a_seam_trip_home() -> None:
    world, seam = seam_world()
    peasant = world.player_units(0)[0]
    world.harvest([peasant.id], seam.id)
    run_until(world, lambda: peasant.carrying is Resource.GOLD, 30.0)
    assert peasant.carry == SEAM_PER_TRIP < GOLD_PER_TRIP
    before = world.players[0].gold
    run_until(world, lambda: world.players[0].gold > before, 20.0)
    assert world.players[0].gold == before + SEAM_PER_TRIP


def test_deep_mining_lifts_a_seam_in_proportion_not_by_a_flat_hundred() -> None:
    """A dwarf's art is in the miners, not in the rock: it multiplies a trip, so 100 becomes 150 and 20 becomes 30.

    Adding the mine's fifty to a seam would treble what an endless deposit is worth to one race alone."""
    world, seam = seam_world((Race.DWARF, Race.HUMAN))
    peasant = world.player_units(0)[0]
    world.harvest([peasant.id], seam.id)
    run_until(world, lambda: peasant.carrying is Resource.GOLD, 30.0)
    assert peasant.carry == SEAM_PER_TRIP
    world.players[0].upgrades.add(Upgrade.DEEP_MINING)
    run_until(world, lambda: peasant.carrying is None, 30.0)
    run_until(world, lambda: peasant.carrying is Resource.GOLD, 40.0)
    assert peasant.carry == SEAM_PER_TRIP * DEEP_MINING_TRIP // GOLD_PER_TRIP == 30


def test_a_seam_seats_more_hands_than_a_mine_and_no_more_than_its_own() -> None:
    world, seam = seam_world(workers=SEAM_SLOTS + 3)
    world.harvest([u.id for u in world.player_units(0)], seam.id)
    busiest = 0
    for _ in range(round(60.0 / SIM_DT)):
        world.step()
        busiest = max(busiest, sum(1 for u in world.player_units(0) if u.inside == seam.id))
    assert MINE_SLOTS < busiest <= SEAM_SLOTS, f"{busiest} at the face of a seam that seats {SEAM_SLOTS}"


def test_the_seam_takes_more_ground_than_a_mine() -> None:
    assert BUILDINGS[BuildingType.GOLD_SEAM].size == 5 > BUILDINGS[BuildingType.GOLD_MINE].size
    world, seam = seam_world()
    assert len(seam.tiles()) == 25 and all(world._blocked[y * world.width + x] for x, y in seam.tiles())


# -- What it never does ------------------------------------------------------------------


def test_a_seam_is_nobody_s_building() -> None:
    world, seam = seam_world()
    assert seam.player is None and seam.hp == 0
    run(world, 2.0)
    assert seam.id in world.buildings, "a deposit with no hit points is never buried with the dead"


# -- Saved, sent and remembered ------------------------------------------------------------


def test_a_seam_survives_a_save_with_its_crew_and_its_kind() -> None:
    world, seam = seam_world(workers=3)
    world.harvest([u.id for u in world.player_units(0)], seam.id)
    run_until(world, lambda: any(u.inside == seam.id for u in world.player_units(0)), 30.0)
    loaded = World.from_dict(world.to_dict())
    kept = loaded.buildings[seam.id]
    assert kept.type is BuildingType.GOLD_SEAM and kept.info.mine is not None and kept.info.mine.endless
    assert kept.has_gold and kept.gold == 0
    assert loaded._mine_crews[seam.id] == sum(1 for u in world.player_units(0) if u.inside == seam.id)


def test_a_player_remembers_a_seam_as_endless_after_the_fog_closes() -> None:
    """The worker knowledge is what every decision under fog reads, so it has to carry the kind, not
    only the stock: a seam remembered as a mine holding nothing is a seam nobody ever walks back to."""
    world, seam = seam_world()
    knowledge = world.worker_knowledge[0]
    known = knowledge.mines[seam.id]
    assert known.endless and known.has_gold and known.gold == 0
    assert known.trip == SEAM_PER_TRIP and known.slots == SEAM_SLOTS and known.size == 5
    restored = World.from_dict(world.to_dict()).worker_knowledge[0].mines[seam.id]
    assert restored == known


def test_a_save_from_before_the_seams_remembers_its_mines_as_mines() -> None:
    world, _seam = seam_world()
    data = world.to_dict()
    for remembered in data["worker_knowledge"]:
        for mine in remembered["mines"]:
            for gone in ("trip", "slots", "endless"):
                del mine[gone]
    restored = World.from_dict(data).worker_knowledge[0]
    assert all(not mine.endless and mine.trip == GOLD_PER_TRIP and mine.slots == MINE_SLOTS
               for mine in restored.mines.values())


# -- The gatherers and the brains ------------------------------------------------------------


def test_the_worker_policy_works_a_seam_when_it_is_the_gold_there_is() -> None:
    """Left to itself, an idle peasant goes to the seam: it is a deposit with gold still coming out of it."""
    world, seam = seam_world(workers=2)
    world.players[0].gold = 0
    world.players[0].lumber = 2000
    run(world, 40.0)
    assert world.players[0].gold >= SEAM_PER_TRIP
    assert any(isinstance(order, Harvest) and order.target == seam.id
               for unit in world.player_units(0) for order in unit.orders)


def both_world(workers: int) -> tuple[World, object, object]:
    """A hall with a seam close by and a gold mine three times as far, the whole map looked at once."""
    terrain = [[Terrain.GRASS] * 44 for _ in range(22)]
    world = World(44, 22, terrain, 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    seam = world.place_building(None, BuildingType.GOLD_SEAM, (9, 7))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (25, 8))
    for i in range(workers):
        world.spawn_unit(0, UnitType.PEASANT, (5.5 + i % 3, 7.5 + i // 3))
    world.reveal_all(0)  # a player who has walked the map once: both deposits are remembered
    return world, seam, mine


def test_a_peasant_walks_past_a_near_seam_to_a_mine_that_pays_five_times_more() -> None:
    """The policy costs a walk in gold, not in tiles: a deposit paying a fifth must be five times nearer.

    Without this an idle peasant took the nearest source it could see and earned a fifth of what the
    mine behind it was paying."""
    world, _seam, mine = both_world(workers=1)
    world.players[0].gold = 0
    world.players[0].lumber = 2000
    run(world, 5.0)
    orders = [order for unit in world.player_units(0) for order in unit.orders if isinstance(order, Harvest)]
    assert orders and all(order.target == mine.id for order in orders), "the policy took the nearer, poorer deposit"


def test_the_seam_takes_the_hands_a_full_mine_cannot() -> None:
    """A mine seats eight; the ninth hand earns more at a seam than standing at a face with no place free."""
    world, seam, mine = both_world(workers=MINE_SLOTS + 4)
    world.players[0].gold = 0
    world.players[0].lumber = 8000  # gold is what this base is short of, so the policy sends everyone for it
    run(world, 40.0)
    on = Counter(order.target for unit in world.player_units(0) for order in unit.orders if isinstance(order, Harvest))
    assert on[mine.id] == MINE_SLOTS, f"the mine should be full, not {on[mine.id]}"
    assert on[seam.id] >= 1, "nobody took the seam once the mine was full"


def test_a_worn_out_mine_hands_its_crew_to_the_seam() -> None:
    """The replacement a spent mine looks for is any deposit that still gives, which is what a seam is."""
    world, seam = seam_world(workers=2)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (6, 3))
    mine.gold = 2 * GOLD_PER_TRIP
    world.update_vision()
    world.harvest([u.id for u in world.player_units(0)], mine.id)
    run_until(world, lambda: mine.id not in world.buildings, 120.0)
    run(world, 30.0)
    assert any(isinstance(order, Harvest) and order.target == seam.id
               for unit in world.player_units(0) for order in unit.orders), "nobody moved on to the seam"


def test_a_brain_takes_a_mine_before_a_seam_and_the_seam_before_nothing() -> None:
    """A hall at a seam earns a fifth of a hall at a mine, so gold that runs out is spent first."""
    from warband.brains.ai import hall_first, worth_a_hall
    from warband.sim.worker_knowledge import KnownMine

    rich = KnownMine(1, 10, 10, 3, 30_000)
    poor = KnownMine(2, 20, 10, 3, 200)
    seam = KnownMine(3, 30, 10, 5, 0, SEAM_PER_TRIP, SEAM_SLOTS, endless=True)
    assert worth_a_hall(rich) and worth_a_hall(seam) and not worth_a_hall(poor)
    assert hall_first(rich, 40.0) < hall_first(seam, 5.0), "a mine across the map beats a seam next door"
    assert hall_first(seam, 30.0) < hall_first(seam, 40.0), "between seams, the nearer one"


# -- On the map ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("size, seats, layout", [("Huge", 2, mapgen.Layout.PLAINS), ("Huge", 4, mapgen.Layout.BASTION),
                                                 ("Giant", 8, mapgen.Layout.CROSSINGS)])
def test_a_big_map_deals_every_seat_a_seam_it_has_to_walk_to(size, seats, layout) -> None:
    """A seam is a whole map to generate and audit, several times over: the slow tier."""
    width, height = mapgen.dimensions(size, seats)
    world, report = mapgen.build(seed=4242, width=width, height=height, players=seats, layout=layout)
    seams = [m for m in world.mines() if m.type is BuildingType.GOLD_SEAM]
    assert len(seams) == seats == report["seams"], "one seam a seat, or none at all: the map is symmetric"
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    for seam in seams:
        assert seam.size == 5 and seam.gold == 0 and seam.has_gold
        assert min(max(abs(seam.center[0] - h.center[0]), abs(seam.center[1] - h.center[1])) for h in halls) >= 12, \
            "a seam is ground to go out and hold, not a second mine at home"
    assert world.free_tile_near(seams[0].rect) is not None, "a seam a peasant cannot stand beside is no seam"


@pytest.mark.slow
def test_the_shipped_sizes_have_no_seams_at_all() -> None:
    """Small, Medium and Large are the maps the difficulty ratings and the balance league were measured on.

    Every layout on every seat count they offer, over several seeds: the slow tier."""
    for size in ("Small", "Medium", "Large"):
        for seats in mapgen.offered(size):
            width, height = mapgen.dimensions(size, seats)
            for layout in mapgen.Layout:
                if mapgen.refusal(width, height, seats, layout) is not None:
                    continue
                for seed in (11, 4177):
                    world = mapgen.generate(seed=seed, width=width, height=height, players=seats, layout=layout)
                    assert not any(m.type is BuildingType.GOLD_SEAM for m in world.mines()), (size, seats, layout, seed)


@pytest.mark.slow
def test_forest_and_klondike_keep_the_economies_they_were_drawn_with() -> None:
    """Neither layout holds a seam at any size: a whole map per size and layout, so the slow tier."""
    for size in ("Huge", "Giant", "Epic"):
        for seats in mapgen.offered(size):
            width, height = mapgen.dimensions(size, seats)
            for layout in (mapgen.Layout.FOREST, mapgen.Layout.KLONDIKE):
                if mapgen.refusal(width, height, seats, layout) is not None:
                    continue
                world = mapgen.generate(seed=99, width=width, height=height, players=seats, layout=layout)
                assert not any(m.type is BuildingType.GOLD_SEAM for m in world.mines()), (size, seats, layout)
