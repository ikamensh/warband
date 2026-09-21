"""Generated maps: a symmetric skeleton (hall, main mine, grove, natural, thirds) under five layouts,
everything reachable within the pathfinder's budget."""

import pytest

from warband.sim import mapgen, path
from warband.sim.model import World
from warband.sim.rules import EXPANSION_GOLD, MINE_GOLD, BuildingType, Layout, MapTheme, Terrain, UnitType


def halls(world: World) -> list:
    return sorted((b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL), key=lambda b: b.player)


def door(world: World, building) -> tuple[int, int]:
    spot = world.free_tile_near(building.rect)
    assert spot is not None
    return spot


def images(world: World, pos: tuple[int, int], size: int = 1) -> set[tuple[int, int]]:
    """Where the map's symmetry sends a tile, or the top-left of a *size* square: one copy a cell."""
    return set(mapgen.cell_images(world.width, world.height, world.seats, pos, size))


@pytest.mark.parametrize("seed", range(1, 7))
@pytest.mark.parametrize("players", (2, 4))
@pytest.mark.parametrize("layout", list(Layout))
def test_every_base_has_a_hall_a_mine_a_wood_and_a_way_to_the_others(seed: int, players: int, layout: Layout) -> None:
    world = mapgen.generate(seed=seed, players=players, layout=layout)
    assert world.layout is layout
    bases = halls(world)
    assert len(bases) == players and {h.player for h in bases} == set(range(players))
    doors = []
    for hall in bases:
        peasants = [u for u in world.units.values() if u.player == hall.player and u.type is UnitType.PEASANT]
        assert len(peasants) == 3 and all(world.passable(*p.tile) for p in peasants)
        assert any(abs(m.center[0] - hall.center[0]) < 9 and abs(m.center[1] - hall.center[1]) < 9 for m in world.mines())
        assert world.nearest_tree(hall.center, 12) is not None
        doors.append(door(world, hall))
        assert world.is_visible(hall.player, hall.pos)
    region = mapgen.reachable(world, doors[0])
    assert all(d in region for d in doors)
    for mine in world.mines():
        assert door(world, mine) in region
    assert len(world.mines()) >= players + 1


@pytest.mark.parametrize("players", (2, 3, 4))
@pytest.mark.parametrize("layout", list(Layout))
def test_the_map_is_symmetric_so_every_seat_gets_the_same(players: int, layout: Layout) -> None:
    """Terrain and mines map onto themselves under the symmetry; halls onto other halls."""
    _assert_congruent(mapgen.generate(seed=5, players=players, layout=layout), players)


def _assert_congruent(world: World, players: int) -> None:
    cols, rows = mapgen.grid(players)
    cw, ch = world.width // cols, world.height // rows
    rim = lambda x, y: x in (0, world.width - 1) or y in (0, world.height - 1)
    for y in range(ch):
        for x in range(cw):
            spots = images(world, (x, y))
            if any(rim(*spot) for spot in spots):
                continue  # the map's rim is a frame outside play, not a cell's ground: mapgen._Canvas.frame
            for ix, iy in spots:
                assert world.terrain[iy][ix] is world.terrain[y][x], (x, y, ix, iy)
    mines = {m.pos for m in world.mines()}
    for m in world.mines():
        if m.gold != EXPANSION_GOLD and players < cols * rows:
            continue  # a cell with no seat has no start mine, only the natural everyone's cell has
        for x, y in images(world, m.pos, 3):
            assert (x, y) in mines, (m.pos, (x, y))
    if players == cols * rows:
        hall_spots = {h.pos for h in halls(world)}
        for h in halls(world):
            assert images(world, h.pos, 3) <= hall_spots


@pytest.mark.parametrize("players", mapgen.SEAT_COUNTS)
def test_every_seat_holds_a_congruent_copy_of_the_first(players: int) -> None:
    """The fairness the audit rests on: each cell is the canonical one, tile for tile, whatever the grid."""
    width, height = mapgen.dimensions(mapgen.sizes_for(players)[0], players)
    world = mapgen.generate(seed=5, width=width, height=height, players=players)
    assert world.seats == players
    _assert_congruent(world, players)


def test_three_players_leave_the_fourth_corner_to_a_neutral_mine() -> None:
    world = mapgen.generate(seed=2, players=3, layout=Layout.PLAINS)
    assert len(halls(world)) == 3
    corner = [m for m in world.mines() if m.x > world.width // 2 and m.y > world.height // 2 or m.x < world.width // 2 and m.y > world.height // 2]
    assert any(m.gold == EXPANSION_GOLD and all(abs(m.center[0] - h.center[0]) + abs(m.center[1] - h.center[1]) > 12 for h in halls(world))
               for m in corner)


@pytest.mark.parametrize("layout", [each for each in Layout if each is not Layout.KLONDIKE])
def test_every_player_has_a_natural_expansion_of_their_own(layout: Layout) -> None:
    """A 30 000 mine ten to eighteen tiles out, nearer its owner than any rival by half again."""
    for players in (2, 4):
        world = mapgen.generate(seed=9, players=players, layout=layout)
        for hall in halls(world):
            own = [m for m in world.mines() if m.gold == EXPANSION_GOLD
                   and 9 <= max(abs(m.center[0] - hall.center[0]), abs(m.center[1] - hall.center[1])) <= 18]
            assert any(all(_dist(m.center, other.center) >= 1.4 * _dist(m.center, hall.center) for other in halls(world) if other is not hall)
                       for m in own), (layout, players, hall.player)


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


@pytest.mark.parametrize("layout", list(Layout))
def test_every_route_is_found_within_the_pathfinders_budget(layout: Layout) -> None:
    """A flood fill proving a mine reachable is not enough: the bounded A* units use must get there too."""
    world = mapgen.generate(seed=4, width=80, height=64, players=4, layout=layout)
    start = door(world, halls(world)[0])
    blocked = bytearray(0 if world.passable(x, y) else 1 for y in range(world.height) for x in range(world.width))
    for goal in [door(world, h) for h in halls(world)[1:]] + [door(world, m) for m in world.mines()]:
        route = path.find_path_grid(start, goal, blocked, world.width, world.height)
        assert route and route[-1] == goal, (layout, goal)


def test_forest_is_woods_joined_by_winding_roads() -> None:
    world, report = mapgen.build(seed=3, layout=Layout.FOREST)
    assert report["trees"] >= 0.4
    assert report["detour"] >= 1.1


def test_crossings_join_the_banks_only_at_the_fords() -> None:
    world, report = mapgen.build(seed=3, layout=Layout.CROSSINGS)
    fords = frozenset(map(tuple, report["fords"]))
    assert fords and all(world.passable(*f) for f in fords)
    a, b = (door(world, h) for h in halls(world))
    assert b in mapgen.reachable(world, a)
    assert b not in mapgen.reachable(world, a, shut=fords)


def test_klondike_keeps_its_gold_in_a_pit_behind_gates() -> None:
    world, report = mapgen.build(seed=3, players=2, layout=Layout.KLONDIKE)
    golds = sorted(m.gold for m in world.mines())
    assert golds == [mapgen.POOR_GOLD] * 2 + [mapgen.KLONDIKE_START_GOLD] * 2 + [EXPANSION_GOLD] * 2
    gates = frozenset(map(tuple, report["gates"]))
    pit = [m for m in world.mines() if m.gold == EXPANSION_GOLD]
    a = door(world, halls(world)[0])
    assert all(door(world, m) in mapgen.reachable(world, a) for m in pit)
    assert not any(door(world, m) in mapgen.reachable(world, a, shut=gates) for m in pit)


def test_bastion_walls_every_base_behind_one_gate() -> None:
    world, report = mapgen.build(seed=3, players=4, layout=Layout.BASTION)
    gates = frozenset(map(tuple, report["gates"]))
    for hall in halls(world):
        inside = mapgen.reachable(world, door(world, hall), shut=gates)
        assert all(_dist(tile, hall.center) < 13 for tile in inside), hall.player
        assert any(door(world, m) in inside for m in world.mines() if m.gold == MINE_GOLD)  # the main mine is inside the ring
        assert not any(door(world, m) in inside for m in world.mines() if m.gold == EXPANSION_GOLD)  # the natural is outside


def test_a_seed_always_draws_the_same_layout() -> None:
    """Two maps of one seed are the same layout: the cheap half of the draw's claim, and the fast tier's."""
    assert mapgen.generate(seed=17).layout is mapgen.generate(seed=17).layout


@pytest.mark.slow
def test_every_layout_is_drawn_by_some_seed() -> None:
    """Every layout comes up over fifty-nine seeds.

    Fifty-nine whole maps, over a second on the Mac and four times that on a runner at four workers:
    the slow tier's.  A seed here and there makes no fair map at all
    (tests/warband/test_fair_seeds.py), and which ones move whenever the generator draws differently;
    the claim is about the draw, so a refused seed is passed over rather than pinned down."""
    drawn = set()
    for seed in range(1, 60):
        try:
            drawn.add(mapgen.generate(seed=seed).layout)
        except mapgen.NoFairMap:
            continue
    assert drawn == set(Layout)


def test_map_edges_are_forest_and_sizes_are_respected() -> None:
    world = mapgen.generate(seed=3, width=48, height=40, layout=Layout.PLAINS)
    assert world.width == 48 and world.height == 40
    assert all(world.terrain_at((x, 0)) is Terrain.TREES and world.terrain_at((x, 39)) is Terrain.TREES for x in range(48))
    assert all(world.terrain_at((0, y)) is Terrain.TREES and world.terrain_at((47, y)) is Terrain.TREES for y in range(40))
    kinds = {t for row in world.terrain for t in row}
    assert Terrain.WATER in kinds and Terrain.TREES in kinds and Terrain.GRASS in kinds


def test_maps_narrower_than_forty_tiles_are_refused() -> None:
    with pytest.raises(ValueError, match="at least 40"):
        mapgen.generate(seed=3, width=40, height=32)


def test_the_same_seed_makes_the_same_map_and_themes_only_change_the_palette() -> None:
    assert mapgen.generate(seed=11).to_dict() == mapgen.generate(seed=11).to_dict()
    assert mapgen.generate(seed=11, theme=MapTheme.WINTER).terrain == mapgen.generate(seed=11, theme=MapTheme.WASTELAND).terrain
    assert World.from_dict(mapgen.generate(seed=11, layout=Layout.BASTION).to_dict()).layout is Layout.BASTION


@pytest.mark.parametrize("layout", list(Layout))
def test_no_building_stands_on_trees_water_or_rock(layout: Layout) -> None:
    """Fuzz seed 81 found a Bastion ring painted under a mine's corner: dug out, the tile was
    open to walk on but still forest to look at and to chop."""
    for players, seed in ((2, 81), (4, 81), (3, 5)):
        world = mapgen.generate(seed=seed, width=64, height=48, players=players, layout=layout)
        for building in world.buildings.values():
            assert all(world.terrain_at(tile) is Terrain.GRASS for tile in building.tiles()), (layout, players, building.pos)
