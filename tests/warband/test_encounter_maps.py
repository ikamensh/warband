"""Generated neutral encounters offer optional, symmetric expeditions beside safe openings."""

import pytest

from warband.sim import mapgen
from warband.sim.model import dist, tile_center
from warband.sim.rules import CAMP_ENCOUNTERS, CAMP_WATCH, BuildingType, Layout


def test_wilds_toggle_preserves_the_map_the_player_compares() -> None:
    """Removing neutral encounters changes occupants, never terrain or the deposits' deal."""
    wild = mapgen.generate(seed=7, width=64, height=48, layout=Layout.PLAINS)
    bare = mapgen.generate(seed=7, width=64, height=48, layout=Layout.PLAINS, wilds=False)
    assert wild.camps and not bare.camps
    assert wild.terrain == bare.terrain
    assert [(m.type, m.pos, m.gold) for m in wild.mines()] == [(m.type, m.pos, m.gold) for m in bare.mines()]
    assert [b.pos for b in wild.buildings.values() if b.type is BuildingType.TOWN_HALL] == [
        b.pos for b in bare.buildings.values() if b.type is BuildingType.TOWN_HALL]


@pytest.mark.slow
def test_an_ordinary_large_forest_map_offers_a_powerful_optional_encounter() -> None:
    """A whole Large Forest map exceeds the fast budget; the Ancient needs no Huge prize map."""

    width, height = mapgen.dimensions("Large", 2)
    world, report = mapgen.build(seed=7, width=width, height=height, layout=Layout.FOREST)
    assert not report["problems"] and report["connected"]
    assert {CAMP_ENCOUNTERS[c.encounter].tier for c in world.camps} == {"Raid", "Stronghold", "Ancient"}
    assert len(world.camps) == 3 * world.seats


@pytest.mark.parametrize("layout", list(Layout))
def test_medium_encounters_keep_the_opening_and_a_route_between_players_free(layout: Layout) -> None:
    """A player can take the safe economy and reach an opponent without paying a PvE toll."""
    world, report = mapgen.build(seed=7, width=64, height=48, layout=layout)
    assert world.camps and not report["problems"]
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    mines = list(world.mines())
    safe = mines[:world.seats if layout is Layout.KLONDIKE else 2 * world.seats]
    lairs = [world.buildings[c.lair] for c in world.camps]
    assert all(dist(lair.center, hall.center) >= 14 for lair in lairs for hall in halls)
    assert all(dist(lair.center, mine.center) >= 10.5 for lair in lairs for mine in safe)
    unsafe = frozenset((x, y) for y in range(world.height) for x in range(world.width)
                       if any(dist(tile_center((x, y)), lair.center) < CAMP_WATCH for lair in lairs))
    start = world.free_tile_near(halls[0].rect)
    assert start is not None
    region = mapgen.reachable(world, start, shut=unsafe)
    assert all(world.free_tile_near(b.rect) in region for b in halls + safe)
    assert all(world.free_tile_near(lair.rect) in mapgen.reachable(world, start) for lair in lairs)
    identities = {c.encounter for c in world.camps}
    assert len(identities) <= 2
    assert all(sum(c.encounter == key for c in world.camps) == world.seats for key in identities)


@pytest.mark.slow
@pytest.mark.parametrize("layout", list(Layout))
@pytest.mark.parametrize("size", ("Small", "Medium", "Large"))
def test_optional_camps_preserve_map_geometry_and_safe_routes_across_seeds(size: str, layout: Layout) -> None:
    """Multiple complete maps, including Forest retries and magic, exceed the fast budget."""
    width, height = mapgen.dimensions(size, 2)
    for seed in range(1, 9):
        world, report = mapgen.build(seed, width, height, layout=layout, magic=seed % 2 == 0)
        bare, bare_report = mapgen.build(seed, width, height, layout=layout, magic=seed % 2 == 0, wilds=False)
        assert world.terrain == bare.terrain, (size, layout, seed)
        assert report["attempt"] == bare_report["attempt"], (size, layout, seed)
        assert world.rifts == bare.rifts
        assert [(m.type, m.pos, m.gold) for m in world.mines()] == [(m.type, m.pos, m.gold) for m in bare.mines()]
        assert report["connected"] and not report["problems"]
        lairs = [world.buildings[c.lair] for c in world.camps]
        assert len(lairs) <= (1 if size == "Small" else 2 if size == "Medium" else 3) * world.seats
        assert all(dist(a.center, b.center) >= 16
                   for i, a in enumerate(lairs) for b in lairs[i + 1:])


@pytest.mark.slow
@pytest.mark.parametrize("players", (3, 4))
def test_four_players_can_contest_one_shared_ancient_with_safe_bypass_routes(players: int) -> None:
    """A complete four-seat Large Forest needs slow tier; its centre is an optional shared boss."""
    width, height = mapgen.dimensions("Large", players)
    world, report = mapgen.build(seed=7, width=width, height=height, players=players, layout=Layout.FOREST)
    ancients = [c for c in world.camps if CAMP_ENCOUNTERS[c.encounter].tier == "Ancient"]
    assert len(ancients) == 1
    assert not report["problems"]
    lair = world.buildings[ancients[0].lair]
    halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    distances = [dist(h.center, lair.center) for h in halls]
    assert max(distances) - min(distances) < 2
    lairs = [world.buildings[c.lair] for c in world.camps]
    unsafe = frozenset((x, y) for y in range(height) for x in range(width)
                       if any(dist(tile_center((x, y)), other.center) < CAMP_WATCH for other in lairs))
    start = world.free_tile_near(halls[0].rect)
    assert start is not None
    region = mapgen.reachable(world, start, shut=unsafe)
    assert all(world.free_tile_near(b.rect) in region for b in halls + list(world.mines())[:2 * players])
    assert world.free_tile_near(lair.rect) in mapgen.reachable(world, start)


@pytest.mark.slow
@pytest.mark.parametrize("players", (3, 4))
@pytest.mark.parametrize("layout", list(Layout))
def test_shared_expeditions_preserve_fairness_and_bypasses_across_seeds(players: int, layout: Layout) -> None:
    """Several whole multiplayer Large maps and their no-wilds comparisons exceed fast tier."""
    width, height = mapgen.dimensions("Large", players)
    for seed in range(1, 5):
        world, report = mapgen.build(seed, width, height, players, layout=layout, magic=seed % 2 == 0)
        bare, bare_report = mapgen.build(seed, width, height, players, layout=layout, magic=seed % 2 == 0, wilds=False)
        assert world.terrain == bare.terrain, (players, layout, seed)
        assert world.rifts == bare.rifts and report["attempt"] == bare_report["attempt"]
        assert [(m.type, m.pos, m.gold) for m in world.mines()] == [(m.type, m.pos, m.gold) for m in bare.mines()]
        assert report["connected"] and not report["problems"]
        halls = [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
        safe = list(world.mines())[:players if layout is Layout.KLONDIKE else 2 * players]
        lairs = [world.buildings[c.lair] for c in world.camps]
        assert all(dist(a.center, b.center) >= 16
                   for i, a in enumerate(lairs) for b in lairs[i + 1:])
        unsafe = frozenset((x, y) for y in range(height) for x in range(width)
                           if any(dist(tile_center((x, y)), lair.center) < CAMP_WATCH for lair in lairs))
        start = world.free_tile_near(halls[0].rect)
        assert start is not None
        region = mapgen.reachable(world, start, shut=unsafe)
        assert all(world.free_tile_near(b.rect) in region for b in halls + safe), (players, layout, seed)
        assert all(world.free_tile_near(lair.rect) in mapgen.reachable(world, start) for lair in lairs)
        for key in {c.encounter for c in world.camps}:
            count = sum(c.encounter == key for c in world.camps)
            assert count in (1, players) if CAMP_ENCOUNTERS[key].tier == "Ancient" else count == players
