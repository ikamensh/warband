"""Layered, unpitched combat Foley, generated once by Warband's sound bank.

A weapon supplies its approach and impact weight; the struck material
supplies the crack, resonance and debris. Seeded takes vary those layers
independently, so repeated attacks differ in texture as well as pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

import numpy as np

from saga2d.synth import level, mix, noise, thump, tone

WEAPONS = ("sword", "axe", "spear", "lance", "arrow", "stone")
MATERIALS = ("flesh", "armor", "wood", "stone")
VARIANTS = 3


@dataclass(frozen=True)
class _Weapon:
    approach: float
    air_band: tuple[float, float]
    body_pitch: tuple[float, float]
    weight: float
    decay: float
    peak: float


_WEAPONS = {
    "sword": _Weapon(0.045, (650, 3500), (190, 80), 0.52, 0.22, 0.67),
    "axe": _Weapon(0.068, (260, 2400), (150, 55), 0.85, 0.28, 0.73),
    "spear": _Weapon(0.033, (900, 3100), (220, 95), 0.40, 0.18, 0.62),
    "lance": _Weapon(0.051, (400, 2400), (145, 60), 0.78, 0.29, 0.70),
    "arrow": _Weapon(0.025, (1900, 5100), (360, 150), 0.20, 0.115, 0.55),
    "stone": _Weapon(0.050, (100, 950), (90, 32), 1.80, 0.52, 0.78),
}


def _material(material: str, rng: np.random.Generator) -> np.ndarray:
    """Contact textures have no musical tuning: modes are deliberately inharmonic."""
    def burst(length: float, low: float, high: float, tau: float) -> np.ndarray:
        return noise(length, low, high, tau=tau, seed=int(rng.integers(2**31)))

    def resonances(modes: tuple[float, ...], length: float, tau: float) -> np.ndarray:
        return mix(*[
            tone(
                frequency * rng.uniform(0.94, 1.06), length,
                attack=0.0015, tau=tau * rng.uniform(0.8, 1.2) / (1 + i * 0.4),
                partials=((1, 1),),
            ) * rng.uniform(0.7, 1.0) / (1 + i * 0.55)
            for i, frequency in enumerate(modes)
        ])

    if material == "flesh":
        # A soft body impact and brief cloth/skin rasp; no metallic sustain.
        return mix(
            thump(175, 75, 0.18, tau=0.035) * 0.7,
            burst(0.13, 130, 1100, 0.030) * 0.9,
            (0.004, burst(0.045, 600, 2100, 0.010) * 0.25),
        )
    if material == "armor":
        # Several independently detuned plate modes instead of a bell note.
        return mix(
            resonances((970, 1567, 2381, 3343), 0.36, 0.095) * 0.55,
            burst(0.075, 1500, 5700, 0.017) * 0.7,
            (rng.uniform(0.018, 0.030), burst(0.12, 750, 3100, 0.035) * 0.18),
        )
    if material == "wood":
        # A sharp grain crack, hollow panel knock, and falling splinters.
        return mix(
            thump(330, 120, 0.10, tau=0.025) * 0.5,
            resonances((390, 827, 1261), 0.15, 0.028) * 0.35,
            burst(0.065, 650, 3600, 0.012) * 1.1,
            (rng.uniform(0.022, 0.040), burst(0.10, 1000, 3100, 0.025) * 0.30),
        )
    if material == "stone":
        # Dull masonry mass under a gritty crack and three irregular chips.
        chips = [
            (delay + rng.uniform(0, 0.014), burst(0.035, 1300, 4200, 0.008) * gain)
            for delay, gain in ((0.026, 0.32), (0.065, 0.22), (0.110, 0.12))
        ]
        return mix(
            thump(170, 65, 0.20, tau=0.046) * 0.65,
            burst(0.21, 350, 4300, 0.048) * 0.8,
            *chips,
        )
    raise ValueError(f"Unknown impact material: {material!r}")


def _impact(weapon: str, material: str, variant: int) -> np.ndarray:
    profile = _WEAPONS[weapon]
    rng = np.random.default_rng(4100 + WEAPONS.index(weapon) * 100 + MATERIALS.index(material) * 10 + variant)
    stretch, pitch = rng.uniform(0.92, 1.08, size=2)
    approach = profile.approach * stretch
    contact = approach * 0.75
    duration = profile.decay * stretch
    low, high = profile.air_band
    layers = [
        noise(
            approach, low, high, attack=approach * 0.65, tau=approach * 0.4,
            seed=int(rng.integers(2**31)),
        ) * rng.uniform(0.12, 0.20),
        (contact, thump(
            profile.body_pitch[0] * pitch, profile.body_pitch[1] * pitch,
            duration, tau=duration / 4.5,
        ) * profile.weight),
        (contact + rng.uniform(0.001, 0.004), _material(material, rng) * rng.uniform(0.8, 1.0)),
    ]
    if weapon in ("sword", "axe"):
        # Edge drag is soft through flesh and abrasive on hard surfaces.
        band = (350, 1700) if material == "flesh" else (1600, 4700)
        layers.append((contact + 0.008, noise(
            0.10 * stretch, *band, tau=0.021 if weapon == "axe" else 0.032,
            seed=int(rng.integers(2**31)),
        ) * (0.20 if weapon == "axe" else 0.28)))
    elif weapon in ("spear", "lance", "arrow"):
        # A flexing wooden shaft follows the point; a lance carries more mass.
        layers.append((contact + rng.uniform(0.009, 0.017), mix(
            tone(530 * pitch, 0.11, tau=0.022, partials=((1, 1), (2.7, 0.24))),
            noise(0.06, 450, 2300, tau=0.016, seed=int(rng.integers(2**31))) * 0.45,
        ) * (0.28 if weapon == "lance" else 0.13)))
    else:
        # Siege stones sustain a low, irregular rumble after the initial hit.
        layers.append((contact + 0.015, noise(
            duration, 45, 410, attack=0.015, tau=0.13,
            seed=int(rng.integers(2**31)),
        ) * 0.85))
    return level(mix(*layers), profile.peak)


SOUNDS = {
    f"{weapon}_{material}_{variant}": partial(_impact, weapon, material, variant)
    for weapon in WEAPONS
    for material in MATERIALS
    for variant in range(VARIANTS)
}
