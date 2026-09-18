"""The frame-time gate must start with every participating faction's art ready."""
from tools.perf import battle
import pytest

from warband import textures
from warband.rules import Race


@pytest.mark.slow
def test_mixed_army_benchmark_warms_the_actual_factions(game):
    """Human-only warm-up silently measured on-demand elf painting during combat.

    Warming every faction's frames for a 150-unit battle takes two seconds: the slow tier."""
    scene = battle(game)
    assert any(player.race is not Race.HUMAN for player in scene.world.players)
    missing = {
        textures.unit_key(unit.type, unit.player, facing, frame, race=unit.race)
        for unit in scene.world.units.values()
        for facing in range(textures.FACINGS)
        for frame in textures.FRAMES
        if not game.assets.has_image(textures.unit_key(unit.type, unit.player, facing, frame, race=unit.race))
    }
    assert not missing, f"Benchmark started with {len(missing)} cold combat frames"
