"""Combat impacts, from generated pieces, are playable and keep their physical contrasts."""

import numpy as np

from sagaforge import synth
from warband.audio import combat_sound


def test_every_weapon_material_pair_has_safe_impacts() -> None:
    """Every hit can be cached and mixed without clipping or abrupt sample jumps."""
    for weapon in combat_sound.WEAPONS:
        for material in combat_sound.MATERIALS:
            for variant in range(combat_sound.VARIANTS):
                name = f"{weapon}_{material}_{variant}"
                samples = combat_sound.SOUNDS[name]()
                assert samples.ndim == 1 and np.isfinite(samples).all(), name
                assert 0.05 <= len(samples) / synth.SAMPLE_RATE <= 1, name
                assert 0.5 <= np.abs(samples).max() <= 0.8, name
                assert abs(samples[0]) < 0.01 and abs(samples[-1]) < 0.01, name
                # Band-limited to 9 kHz, a bright clang can swing nearly its whole peak between two samples;
                # a click would be a reversal, more than the peak in one step.
                assert np.abs(np.diff(samples)).max() < np.abs(samples).max(), name


def test_hard_armor_rings_brighter_than_flesh_and_siege_stones_land_an_octave_lower_than_arrows() -> None:
    """The mix keeps audible material and weapon contrasts: every take for the material, the takes together for the weight."""
    def brightness(samples: np.ndarray) -> float:
        frequency, power = np.fft.rfftfreq(len(samples), 1 / synth.SAMPLE_RATE), abs(np.fft.rfft(samples)) ** 2
        return float(np.sum(frequency * power) / power.sum())

    for variant in range(combat_sound.VARIANTS):
        for weapon in combat_sound.WEAPONS:
            armor = combat_sound.SOUNDS[f"{weapon}_armor_{variant}"]()
            flesh = combat_sound.SOUNDS[f"{weapon}_flesh_{variant}"]()
            assert brightness(armor) > brightness(flesh) * 1.4, (weapon, variant)
    for material in combat_sound.MATERIALS:
        # Anything into flesh is a thud, so one take cannot carry this; the three together must.
        stone = np.mean([brightness(combat_sound.SOUNDS[f"stone_{material}_{v}"]()) for v in range(combat_sound.VARIANTS)])
        arrow = np.mean([brightness(combat_sound.SOUNDS[f"arrow_{material}_{v}"]()) for v in range(combat_sound.VARIANTS)])
        assert stone < arrow / 2, (material, stone, arrow)


def test_takes_are_repeatable_but_do_not_reuse_the_same_waveform() -> None:
    """Caching is deterministic, while successive attacks can use distinct textures."""
    for weapon in combat_sound.WEAPONS:
        for material in combat_sound.MATERIALS:
            takes = [combat_sound.SOUNDS[f"{weapon}_{material}_{variant}"]()
                     for variant in range(combat_sound.VARIANTS)]
            for variant, samples in enumerate(takes):
                assert np.array_equal(samples, combat_sound.SOUNDS[f"{weapon}_{material}_{variant}"]())
            for first, second in zip(takes, takes[1:]):
                overlap = min(len(first), len(second))
                assert abs(np.corrcoef(first[:overlap], second[:overlap])[0, 1]) < 0.95, (weapon, material)
