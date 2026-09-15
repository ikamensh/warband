"""Fairness across seeds, sizes and layouts: every base can play the same opening."""

import pytest

from warband import mapgen
from warband.mapgen import audit as fairness
from warband.model import World
from warband.rules import Layout, MapTheme, UnitType

SEEDS = range(1, 41)


@pytest.mark.parametrize("layout", list(Layout))
@pytest.mark.parametrize("size", list(mapgen.SIZES))
def test_every_seed_gives_every_player_a_fair_start(size: str, layout: Layout) -> None:
    width, height = mapgen.SIZES[size]
    for seed in SEEDS:
        players = 2 + seed % 3
        world = mapgen.generate(seed=seed, width=width, height=height, players=players, layout=layout)
        r = fairness(world)
        assert r["connected"], (size, layout, seed, "unreachable base or mine")
        assert all(o >= 90 for o in r["open"]), (size, layout, seed, "cramped base", r["open"])
        assert all(m <= 9 for m in r["mine"]), (size, layout, seed, "mine too far", r["mine"])
        assert all(w is not None and w <= 12 for w in r["wood"]), (size, layout, seed, "no wood in reach", r["wood"])
        assert r["expansions"] >= 2, (size, layout, seed, "too few mines beyond the main ones")
        low, high = (0.35, 0.80) if layout is Layout.FOREST else (0.08, 0.50)
        assert low <= r["trees"] <= high and r["water"] <= 0.25, (size, layout, seed, r["trees"], r["water"])
        peasants = [u for u in world.units.values() if u.type is UnitType.PEASANT]
        assert len(peasants) == 3 * players and all(world.passable(*p.tile) for p in peasants)


@pytest.mark.parametrize("theme", list(MapTheme))
def test_every_theme_survives_a_save(theme: MapTheme) -> None:
    world = mapgen.generate(seed=7, theme=theme)
    assert World.from_dict(world.to_dict()).theme is theme
