"""Generated maps: a symmetric skeleton (hall, main mine, grove, natural, thirds) under five layouts,
everything reachable within the pathfinder's budget."""

import pytest

from warband.sim import mapgen, path
from warband.sim.model import RIFT, World
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
    mines = {m.pos: (m.type, m.gold) for m in world.mines()}
    for m in world.mines():
        if m.gold != EXPANSION_GOLD and players < cols * rows:
            continue  # a cell with no seat has no start mine, only the natural everyone's cell has
        for x, y in images(world, m.pos, 3):
            assert mines.get((x, y)) == (m.type, m.gold), (m.pos, (x, y))
    rifts = set(world.rifts)
    for rift in rifts:
        assert images(world, rift, RIFT) <= rifts, ("a ley rift without its copies", rift)
    if players == cols * rows:
        hall_spots = {h.pos for h in halls(world)}
        for h in halls(world):
            assert images(world, h.pos, 3) <= hall_spots


@pytest.mark.parametrize("players", [pytest.param(players, marks=pytest.mark.slow if players >= 8 else ())
                                     for players in mapgen.SEAT_COUNTS])
def test_every_seat_holds_a_congruent_copy_of_the_first(players: int) -> None:
    """The fairness the audit rests on: each cell is the canonical one, tile for tile, whatever the grid.

    Eight or more seats require whole large boards taking over half a second
    locally to generate and compare; those exact seat grids run in the slow tier.
    """
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


def _bodies(world: World, kind: Terrain) -> list[int]:
    """Sizes of the connected bodies of one terrain kind, biggest first."""
    seen: set[tuple[int, int]] = set()
    sizes: list[int] = []
    for y in range(world.height):
        for x in range(world.width):
            if world.terrain[y][x] is not kind or (x, y) in seen:
                continue
            stack, size = [(x, y)], 0
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                size += 1
                for nxt in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if nxt not in seen and 0 <= nxt[0] < world.width and 0 <= nxt[1] < world.height \
                            and world.terrain[nxt[1]][nxt[0]] is kind:
                        seen.add(nxt)
                        stack.append(nxt)
            sizes.append(size)
    return sorted(sizes, reverse=True)


@pytest.mark.parametrize("seed", range(1, 13))
def test_the_centre_is_one_place_you_can_name(seed: int) -> None:
    """The motif the seed drew is the place a reader finds at the middle of the finished
    ground: the description and the screenshot claim the same centre."""
    world, report = mapgen.build(seed=seed, width=64, height=48, players=2, layout=Layout.PLAINS)
    assert report["motif"] in ("lake", "mesa", "greatwood", "marsh", "field")
    assert mapgen._centre_place(world) == report["motif"]


def test_water_is_a_few_places_not_speckle() -> None:
    """Bodies of water you can point at: a lake is one body holding most of the map's water,
    and no Plains map dissolves into a dozen puddles."""
    for seed in (1, 3, 5, 7, 11):
        world, report = mapgen.build(seed=seed, width=64, height=48, players=2, layout=Layout.PLAINS)
        bodies = [size for size in _bodies(world, Terrain.WATER) if size >= 4]
        assert len(bodies) <= 8, (seed, bodies)
        if report["motif"] == "lake":
            assert bodies and bodies[0] >= 0.5 * sum(bodies), (seed, bodies)


def test_crossings_water_is_one_river() -> None:
    """The only water on a Crossings map is the river: one ribbon edge to edge, cut only where
    the fords cross it, with no ponds pretending to be it and no chain of lakes to wade between."""
    for seed in (1, 3, 5):
        world, report = mapgen.build(seed=seed, width=64, height=48, players=2, layout=Layout.CROSSINGS)
        bodies = _bodies(world, Terrain.WATER)
        reaches = [size for size in bodies if size >= 10]
        assert 2 <= len(reaches) <= 4, (seed, bodies)  # the reaches between the three fords
        assert sum(reaches) >= 0.95 * sum(bodies), (seed, bodies)
        assert report["water"] < 0.09, (seed, report["water"])


@pytest.mark.parametrize("layout", (Layout.PLAINS, Layout.BASTION, Layout.CROSSINGS))
def test_the_natural_sits_in_a_pocket_with_its_mouth_to_home(layout: Layout) -> None:
    """The second base reads as defensible: blocked ground behind it, open ground toward home."""
    world = mapgen.generate(seed=3, width=64, height=48, players=2, layout=layout)
    hall, other = halls(world)
    natural = min((m for m in world.mines() if m.gold == EXPANSION_GOLD
                   and _dist(m.center, hall.center) < _dist(m.center, other.center)),
                  key=lambda m: _dist(m.center, hall.center))
    out = (natural.center[0] - hall.center[0], natural.center[1] - hall.center[1])

    def walled(away: bool) -> float:
        tiles = [(x, y) for y in range(int(natural.center[1]) - 7, int(natural.center[1]) + 8)
                 for x in range(int(natural.center[0]) - 7, int(natural.center[0]) + 8)
                 if 0 <= x < world.width and 0 <= y < world.height
                 and 4.5 <= _dist((x, y), natural.center) <= 7.0
                 and ((x - natural.center[0]) * out[0] + (y - natural.center[1]) * out[1] > 0) == away]
        return sum(world.terrain[y][x] is not Terrain.GRASS for x, y in tiles) / max(1, len(tiles))

    assert walled(True) > walled(False) + 0.15, (layout, walled(True), walled(False))


@pytest.mark.parametrize(("layout", "word"),
                         ((Layout.PLAINS, "centre"), (Layout.FOREST, "road"), (Layout.CROSSINGS, "ford"),
                          (Layout.KLONDIKE, "pit"), (Layout.BASTION, "gate")))
def test_every_map_describes_itself(layout: Layout, word: str) -> None:
    """Two plain sentences naming the layout's decisive ground, the same from the build
    report as read off the finished world, short enough for the New game caption."""
    world, report = mapgen.build(seed=3, width=64, height=48, players=2, layout=layout)
    assert report["story"] == mapgen.describe(world)
    assert word in report["story"].lower() and len(report["story"]) < 170  # it captions the preview on a 680-pixel screen


def test_forest_is_woods_joined_by_winding_roads() -> None:
    world, report = mapgen.build(seed=3, layout=Layout.FOREST)
    assert report["trees"] >= 0.4
    assert report["detour"] >= 1.1


def test_plains_contests_its_mines_with_fewer_thirds() -> None:
    """Open ground where expansions lie exposed: fewer contested mines than the
    woods or the ring, so waiting at home costs."""
    plains, forest = mapgen._SPECS[Layout.PLAINS], mapgen._SPECS[Layout.FOREST]
    assert mapgen._third_orbits(plains, 64, 24) == 1
    assert mapgen._third_orbits(forest, 64, 24) == 2


@pytest.mark.parametrize(("layout", "gold"), ((Layout.PLAINS, 15_000), (Layout.CROSSINGS, 20_000)))
def test_open_and_ford_maps_put_early_pressure_on_the_natural(layout: Layout, gold: int) -> None:
    """The home mine runs short during ordinary matches, while a free natural remains available."""
    world = mapgen.generate(seed=9, players=2, layout=layout)
    for hall in halls(world):
        main = min(world.mines(), key=lambda mine: _dist(mine.center, hall.center))
        assert main.gold == gold
        assert any(mine.gold == EXPANSION_GOLD and 12 <= _dist(mine.center, hall.center) <= 18
                   for mine in world.mines())


def test_crossings_join_the_banks_only_at_the_fords() -> None:
    world, report = mapgen.build(seed=3, layout=Layout.CROSSINGS)
    fords = frozenset(map(tuple, report["fords"]))
    assert fords and all(world.passable(*f) for f in fords)
    a, b = (door(world, h) for h in halls(world))
    assert b in mapgen.reachable(world, a)
    assert b not in mapgen.reachable(world, a, shut=fords)


@pytest.mark.parametrize("players", (2, 4))
@pytest.mark.parametrize("seed", range(1, 7))
def test_crossings_natural_faces_the_central_ford(seed: int, players: int) -> None:
    """The first expansion pulls each seat toward the river instead of back to the rim."""
    world = mapgen.generate(seed=seed, players=players, layout=Layout.CROSSINGS)
    hall = halls(world)[0]
    natural = min((mine for mine in world.mines() if mine.gold == EXPANSION_GOLD),
                  key=lambda mine: _dist(mine.center, hall.center))
    assert _dist(natural.center, (world.width / 2, world.height / 2)) < 14


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


@pytest.mark.slow
def test_bastion_gate_cannot_be_sealed_by_buildings() -> None:
    """Fuzz seed 82, Huge: a farm left one lane into the gate, then a second building
    sealed it and the army gathered inside the ring with no route out.

    Recaptured 2026-10-13 from the same seed and board after the landscape redraw moved
    the ground: the gate still runs through (8, 16), the farm stands at (7, 14) inside it,
    and a tower at (9, 14) would close the last lane.  Generating this exact Huge board
    takes over a second on the Mac; retaining the captured gate geometry puts this
    regression in the slow tier.
    """
    world, report = mapgen.build(seed=82, width=108, height=84, players=2, human=None)
    assert world.layout is Layout.BASTION
    assert (8, 16) in map(tuple, report["gates"])
    world.reveal_all(0)
    assert world._placement_reason(BuildingType.FARM, (7, 14), 0, ignore_units=True) is None
    world.place_building(0, BuildingType.FARM, (7, 14))
    assert world._placement_reason(BuildingType.TOWER, (9, 14), 0, ignore_units=True) == "Keep the gate open"
    assert (9, 14) not in world.placeable(BuildingType.TOWER, 0, [(9, 14)])
    restored = World.from_dict(world.to_dict())
    assert restored.gates == world.gates
    assert restored.gate_links == world.gate_links
    assert restored._placement_reason(BuildingType.TOWER, (9, 14), 0, ignore_units=True) == "Keep the gate open"


@pytest.mark.slow
def test_bastion_gate_cannot_be_sealed_from_beside_it() -> None:
    """Fuzz seed 82, Huge (WB-063's run): a building that touched no gate tile sealed a base
    in from just beside the gate, the ring's trees doing the rest; nothing asked because
    the footprint stood off the gate itself.

    Recaptured 2026-10-13 from the same seed and board after the landscape redraw: a
    barracks at (7, 13) stands across the gate's mouth without touching a gate tile, and
    the same barracks deeper inside at (7, 10), where the way out goes round it, stands
    freely.  Generating this exact Huge board takes over a second on the Mac; retaining
    the captured gate geometry puts this regression in the slow tier.
    """
    world, report = mapgen.build(seed=82, width=108, height=84, players=2, human=None)
    gates = set(map(tuple, report["gates"]))
    assert world.layout is Layout.BASTION and (9, 19) in gates
    world.reveal_all(0)
    footprint = {(7 + dx, 13 + dy) for dx in range(3) for dy in range(3)}
    assert not footprint & gates  # beside the gate, not on it: the reach is what asks
    assert world._placement_reason(BuildingType.BARRACKS, (7, 13), 0, ignore_units=True) == "Keep the gate open"
    assert (7, 13) not in world.placeable(BuildingType.BARRACKS, 0, [(7, 13)])
    assert world._placement_reason(BuildingType.BARRACKS, (7, 10), 0, ignore_units=True) is None  # deeper in, the way out goes round
    assert world._placement_reason(BuildingType.FARM, (7, 17), 0, ignore_units=True) is None  # on the gate's corner, lanes remain


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


@pytest.mark.parametrize("players", (2, 3, 4))
@pytest.mark.parametrize("layout", list(Layout))
def test_every_seat_has_a_ley_rift_by_its_hall_a_vault_can_stand_on(players: int, layout: Layout) -> None:
    """Inside its own cell, a few tiles off the hall: explored from the start, open to walk to, and ground the
    seat may set a vault on as the match begins.  The rift is the seat's own: nearer its hall than any other."""
    world = mapgen.generate(seed=7, width=64, height=48, players=players, layout=layout, magic=True)
    for hall in halls(world):
        own = [r for r in world.rifts if max(abs(r[0] + RIFT / 2 - hall.center[0]), abs(r[1] + RIFT / 2 - hall.center[1])) <= 8]
        assert own, (layout, players, hall.player)
        region = mapgen.reachable(world, door(world, hall))
        for rift in own:
            middle = (rift[0] + RIFT / 2, rift[1] + RIFT / 2)
            assert all(_dist(middle, other.center) > _dist(middle, hall.center) for other in halls(world) if other is not hall)
            assert rift in region
            assert world.can_place(BuildingType.VAULT, rift, hall.player) is None, (layout, players, hall.player, rift)


def test_a_cell_with_room_for_a_middle_gets_a_contested_rift_too() -> None:
    """Medium with two seats: each seat's own and one out in the shared ground, a third mine's distance from
    every hall.  Small with four seats has no middle to put one in."""
    world = mapgen.generate(seed=5, width=64, height=48, players=2, layout=Layout.PLAINS, magic=True)
    assert len(world.rifts) == 4
    far = [r for r in world.rifts if min(_dist((r[0] + 1, r[1] + 1), h.center) for h in halls(world)) >= 12]
    assert len(far) == 2
    small = mapgen.generate(seed=5, width=48, height=40, players=4, layout=Layout.PLAINS, magic=True)
    assert len(small.rifts) == 4
