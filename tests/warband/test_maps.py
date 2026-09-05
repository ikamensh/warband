"""Fairness across seeds, sizes and themes: every base can play the same opening."""

import pytest

from warband import mapgen
from warband.mapgen import audit as fairness
from warband.model import World
from warband.rules import BuildingType, MapTheme, Terrain, UnitType

SEEDS = range(1, 41)


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
