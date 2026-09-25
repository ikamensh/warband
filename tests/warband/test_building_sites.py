"""Where a computer player puts its buildings: never where one walls its own base in.

Fuzz seeds 98 and 110 (2026-09-24): on Forest maps a brain filled the one gap between two woods that joined its base to
the rest of the map, a blacksmith in one and a farm in the other.  From then on every attack aimed at ground the army
could not reach, so the whole army piled into the corner of the base nearest the target, and the brain sent every
soldier the world let stop there straight back out, for the rest of the match: fuzz read them as wedged.
"""

from __future__ import annotations

import random
from collections import deque

import pytest

from warband.brains import ai
from warband.sim.model import World
from warband.sim.rules import BUILDINGS, BuildingType, Race, Terrain


class Sealed:
    """The ground and the buildings round a site a brain chose, at the moment it chose it, cut out of the seed's map
    (trees beyond, so the cut-out joins nothing the map did not): its race, the site, and a tile on the far side of
    the gap the site filled."""

    def __init__(self, origin, ground, buildings, player, race, kind, site, far) -> None:
        self.origin, self.ground, self.buildings = origin, ground, buildings
        self.player, self.race, self.kind, self.site, self.far = player, race, kind, site, far

    def world(self) -> World:
        letters = {terrain.value[0]: terrain for terrain in Terrain}
        width, height = 144, 108  # the seeds' maps
        terrain = [[Terrain.TREES] * width for _ in range(height)]
        for dy, row in enumerate(self.ground):
            for dx, letter in enumerate(row):
                terrain[self.origin[1] + dy][self.origin[0] + dx] = letters[letter]
        races = [Race.HUMAN] * (self.player + 1)
        races[self.player] = self.race
        world = World(width, height, terrain, self.player + 1, human=None, races=races)
        for owner, kind, pos in self.buildings:
            world.place_building(owner, kind, pos)
        world.reveal_all(self.player)
        return world


# Seed 110 (four players), 162.95 s: the dwarves of player 1 send a peasant to put a blacksmith at (124, 98), in the
# three-tile gap west of their base; their hall's region falls from 3180 tiles to 165 as it goes up.
# Seed 98 (three players, on main at 230ca7c), 337.35 s: the elves of player 2 put a farm at (140, 19), in the two-tile
# corridor south of their base; 3892 tiles to 187.
SEALED = {
    110: Sealed((112, 86), (
    "tttttggggggttttttttttttttttttt", "tttggggggggttttttttttttttttttt", "tttggggggggttttttttttttttttttt",
    "ttggggggggggtttttttttttttttttt", "ttggggggggggtttttttttttttttttt", "ttggggggggggtttttttttttgggtttt",
    "ttggggggggggttttttttgggggggggg", "tttggggggggtttttttgggggggggggg", "tttgggggggggtttttggggggggggggg",
    "tttttgggggggtttttggggggggggggg", "tttttttttgggttttgggggggggggggg", "tttttttttgggttttgggggggggggggg",
    "tttttttttggggggggggggggggggggg", "tttttttttggggggggggggggggggggg", "tttttttttggggggtgggggggggggggg",
    "tttttttttgggggttgggggggggggggg", "ttttttttttgggtttgggggggggggggg", "ttttttttttggttttgggggggggggggg",
    "tttttttttttttttttggggggggggggg", "tttttttttttttttttggggggggggggg", "ttttttttttttttttttgggggggggggt",
    "tttttttttttttttttttttggggggttt",
    ), [
        (1, BuildingType.TOWN_HALL, (134, 98)),
        (None, BuildingType.GOLD_MINE, (139, 102)),
        (None, BuildingType.GOLD_MINE, (118, 90)),
        (1, BuildingType.FARM, (138, 97)),
        (1, BuildingType.FARM, (135, 94)),
        (1, BuildingType.BARRACKS, (129, 99)),
        (1, BuildingType.FARM, (133, 102)),
        (1, BuildingType.LUMBER_MILL, (138, 93)),
        (1, BuildingType.FARM, (130, 95)),
        (1, BuildingType.STABLES, (133, 105)),  # going up
        (1, BuildingType.FARM, (129, 103)),  # going up
    ], 1, Race.DWARF, BuildingType.BLACKSMITH, (124, 98), (121, 99)),
    98: Sealed((116, 0), (
    "tttttttttttttttggggggggggttt", "tttttttttttttttgggggggggggtt", "ttttttttttttttgggggggggggggt",
    "ttttttttttttgggggggggggggggt", "ttttttttttttgggggggggggggggg", "tttttttttttggggggggggggggggg",
    "tttttttttttggggggggggggggggg", "tttttttttttggggggggggggggggg", "tttttttttttggggggggggggggggg",
    "tttttttttttggggggggggggggggg", "ttttttttttgggggggggggggggggg", "ttttttttttgggggggggggggggggg",
    "ttttttttttgggggggggggggggggt", "ttttttttttttgggggggggggggggt", "ttttttttttttggggggggggggggtt",
    "gtttttttttttggggggggggggggtt", "ggtttttttttttgggggggggttggtt", "gggttttttttttttgggggttttggtt",
    "ggggtttttttttttggggtttttggtt", "tggggtttttttttggggttttttggtt", "ttggggggggggggggggttttttggtt",
    "tttgggggggggggggttttttggggtt", "ttttttttttttttttttttgggggggt", "ttttttttttttttttttttgggggggt",
    "tttttttttttttttttttggggggggt", "tttttttttttttttttttggggggggt", "tttggttttttttttttttggggggggt",
    "tttgggtttttttttttttggggggggt", "tttggggtttttttttttttgggggggt", "tttgggggttttttttttttgggggggt",
    "tttggggggtttttttttttttggggtt", "gttggtggggtttttttttttttggttt",
    ), [
        (2, BuildingType.TOWN_HALL, (134, 7)),
        (None, BuildingType.GOLD_MINE, (139, 3)),
        (None, BuildingType.GOLD_MINE, (139, 24)),
        (2, BuildingType.FARM, (134, 3)),
        (2, BuildingType.FARM, (138, 8)),
        (2, BuildingType.BARRACKS, (133, 12)),
        (2, BuildingType.FARM, (130, 5)),
        (2, BuildingType.TOWER, (132, 17)),
        (2, BuildingType.FARM, (130, 8)),
        (2, BuildingType.STABLES, (137, 12)),
        (2, BuildingType.FARM, (130, 2)),
        (2, BuildingType.FARM, (135, 0)),
        (2, BuildingType.TOWER, (128, 20)),
        (2, BuildingType.CHURCH, (141, 8)),
        (2, BuildingType.FARM, (127, 6)),
        (2, BuildingType.FARM, (141, 12)),
        (2, BuildingType.FARM, (128, 12)),
        (2, BuildingType.FARM, (127, 9)),
        (2, BuildingType.FARM, (129, 15)),  # going up
    ], 2, Race.ELF, BuildingType.FARM, (140, 19), (140, 22)),
}


def reaches(world: World, start, goal, shut=frozenset()) -> bool:
    """Whether a walker gets from *start* to *goal* with the tiles *shut* built on (edge to edge is how walkers join up:
    a diagonal step needs both tiles beside it open)."""
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return True
        for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if step not in seen and step not in shut and world.in_bounds(step) and world.passable(*step):
                seen.add(step)
                queue.append(step)
    return False


@pytest.mark.parametrize("seed", sorted(SEALED))
def test_a_computer_player_never_puts_a_building_where_it_walls_its_own_base_in(seed: int) -> None:
    case = SEALED[seed]
    world = case.world()
    hall = world.player_buildings(case.player, BuildingType.TOWN_HALL)[0]
    door = world.free_tile_near(hall.rect)
    size = BUILDINGS[case.kind].size
    footprint = frozenset((x, y) for x in range(case.site[0], case.site[0] + size) for y in range(case.site[1], case.site[1] + size))
    assert world.can_place(case.kind, case.site, case.player) is None, "the rules allow the site: the brain must not want it"
    assert reaches(world, door, case.far) and not reaches(world, door, case.far, footprint), "the site is the seed's seal"

    assert ai.first_site(world, case.kind, case.player, [(0.0, case.site)]) is None
    # The search the brains make, from anchors about the hall and with their random tiebreaks: before, nearly every
    # answer was a site in the same gap (all 33 in seed 98, 27 of 31 in seed 110).  Seed 98's base has no other farm
    # site at that moment that leaves its ground whole, so there the brain builds nothing yet, and a farm later.
    offers = []
    for trial in range(40):
        rng = random.Random(trial)
        anchor = (hall.center[0] + rng.uniform(-4, 4), hall.center[1] + rng.uniform(-4, 4))
        site = ai.site_search(world, case.kind, case.player, anchor, rng, ai.BUILD_MIN_DISTANCE, ai.BUILD_MAX_DISTANCE)
        if site is not None:
            offers.append(site)
    sealing = [site for site in offers
               if not reaches(world, door, case.far, frozenset((x, y) for x in range(site[0], site[0] + size)
                                                                for y in range(site[1], site[1] + size)))]
    assert not sealing, sealing
