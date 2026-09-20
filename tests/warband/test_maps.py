"""Fairness across seeds, sizes and layouts: every base can play the same opening."""

import pytest

from warband.sim import mapgen
from warband.sim.mapgen import audit as fairness
from warband.sim.model import World
from warband.sim.rules import Layout, MapTheme, UnitType

SEEDS = [pytest.param(range(1, 4), id="seeds 1-3"), pytest.param(range(4, 41), id="seeds 4-40", marks=pytest.mark.slow)]


@pytest.mark.parametrize("seeds", SEEDS)
@pytest.mark.parametrize("layout", list(Layout))
@pytest.mark.parametrize("size", list(mapgen.SIZES))
def test_every_seed_gives_every_player_a_fair_start(size: str, layout: Layout, seeds: range) -> None:
    """Forty seeds of every size and layout take about twenty seconds, so the fast tier checks the first three
    of each and the slow tier the other thirty-seven.  Each seed takes the next seat count the size offers for
    the layout, so every offered pairing is generated."""
    counts = mapgen.offered(size, layout)
    assert counts, (size, layout, "no seat count at all", mapgen.refusal(*mapgen.dimensions(size, 2), 2, layout))
    for seed in seeds:
        players = counts[seed % len(counts)]
        width, height = mapgen.dimensions(size, players)
        world = mapgen.generate(seed=seed, width=width, height=height, players=players, layout=layout)
        r = fairness(world)
        assert r["connected"], (size, layout, seed, "unreachable base or mine")
        assert all(o >= 90 for o in r["open"]), (size, layout, seed, "cramped base", r["open"])
        assert all(m <= 9 for m in r["mine"]), (size, layout, seed, "mine too far", r["mine"])
        assert all(w is not None and w <= 12 for w in r["wood"]), (size, layout, seed, "no wood in reach", r["wood"])
        assert r["expansions"] >= 2, (size, layout, seed, "too few mines beyond the main ones")
        assert r["players"] == players, (size, layout, seed, "a seat lost its hall")
        low, high = (0.35, 0.80) if layout is Layout.FOREST else (0.08, 0.50)
        assert low <= r["trees"] <= high and r["water"] <= 0.25, (size, layout, seed, r["trees"], r["water"])
        peasants = [u for u in world.units.values() if u.type is UnitType.PEASANT]
        assert len(peasants) == 3 * players and all(world.passable(*p.tile) for p in peasants)


@pytest.mark.parametrize("theme", list(MapTheme))
def test_every_theme_survives_a_save(theme: MapTheme) -> None:
    world = mapgen.generate(seed=7, theme=theme)
    assert World.from_dict(world.to_dict()).theme is theme
