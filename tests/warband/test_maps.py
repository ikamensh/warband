"""Fairness across seeds, sizes and themes: every base can play the same opening."""

from collections import deque

import pytest

from warband import mapgen
from warband.model import World
from warband.rules import BuildingType, MapTheme, Terrain, UnitType

SEEDS = range(1, 41)


def reachable(world: World, start) -> set:
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in seen and world.passable(*n):
                seen.add(n)
                queue.append(n)
    return seen


def fairness(world: World) -> dict:
    """The numbers a base needs; every failure message names the seed's problem."""
    halls = world.player_buildings(None) if False else [b for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    doors = [world.free_tile_near(h.rect) for h in halls]
    region = reachable(world, doors[0])
    report = {"players": len(halls), "open": [], "mine": [], "wood": []}
    for hall in halls:
        cx, cy = int(hall.center[0]), int(hall.center[1])
        open_ground = sum(1 for dx in range(-6, 7) for dy in range(-6, 7) if world.passable(cx + dx, cy + dy))
        report["open"].append(open_ground)
        report["mine"].append(min(max(abs(m.center[0] - hall.center[0]), abs(m.center[1] - hall.center[1])) for m in world.mines()))
        tree = world.nearest_tree(hall.center, 12)
        report["wood"].append(None if tree is None else max(abs(tree[0] - cx), abs(tree[1] - cy)))
    report["connected"] = all(d in region for d in doors) and all(world.free_tile_near(m.rect) in region for m in world.mines())
    report["expansions"] = len(world.mines()) - len(halls)
    total = world.width * world.height
    report["trees"] = sum(1 for row in world.terrain for t in row if t is Terrain.TREES) / total
    report["water"] = sum(1 for row in world.terrain for t in row if t is Terrain.WATER) / total
    return report


@pytest.mark.parametrize("theme", list(MapTheme))
@pytest.mark.parametrize("size", list(mapgen.SIZES))
def test_every_seed_gives_every_player_a_fair_start(size: str, theme: MapTheme) -> None:
    width, height = mapgen.SIZES[size]
    for seed in SEEDS:
        players = 2 + seed % 3
        world = mapgen.generate(seed=seed, width=width, height=height, players=players, theme=theme)
        r = fairness(world)
        assert r["connected"], (size, theme, seed, "unreachable base or mine")
        assert all(o >= 90 for o in r["open"]), (size, theme, seed, "cramped base", r["open"])
        assert all(m <= 9 for m in r["mine"]), (size, theme, seed, "mine too far", r["mine"])
        assert all(w is not None and w <= 12 for w in r["wood"]), (size, theme, seed, "no wood in reach", r["wood"])
        assert r["expansions"] >= 2, (size, theme, seed, "too few expansion mines")
        assert 0.10 <= r["trees"] <= 0.60 and r["water"] <= 0.25, (size, theme, seed, r["trees"], r["water"])
        peasants = [u for u in world.units.values() if u.type is UnitType.PEASANT]
        assert len(peasants) == 3 * players and all(world.passable(*p.tile) for p in peasants)


def test_themes_differ_in_terrain_mix_and_survive_a_save() -> None:
    mixes = {theme: fairness(mapgen.generate(seed=7, theme=theme)) for theme in MapTheme}
    assert mixes[MapTheme.WASTELAND]["trees"] < mixes[MapTheme.SUMMER]["trees"]
    assert mixes[MapTheme.WASTELAND]["water"] <= mixes[MapTheme.SUMMER]["water"]
    world = mapgen.generate(seed=7, theme=MapTheme.WINTER)
    assert World.from_dict(world.to_dict()).theme is MapTheme.WINTER
