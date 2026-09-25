"""The spells' sounds (WB-066), synthesised with :mod:`sagaforge.synth` like the HUD's cues.

Each spell sounds as it lands (``spell_<key>``: its effect, wherever the player sees it) and a Meteor also as it is cast
(``spell_meteor_fall``: the rumble and rush of its fall beginning, two seconds before it lands).  The families are the
effects' own: glass and bells for the light that mends and quickens, noise for fire and the wind of a fall, low thumps
for stone and roots.  A summoned elemental is a body, not a spell: it dies, struck down or its time run out, in its own
sound family's generated pieces (:mod:`warband.audio.bodies`), and answers its orders with its hum.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from sagaforge.synth import BELL, DARK, GLASS, PAD, level, lowpass, mix, noise, thump, tone


def haste() -> np.ndarray:
    """A quick rising run of glass, a rush of air under it."""
    run = [(i * 0.045, tone(note, 0.16, tau=0.06, partials=GLASS) * (0.5 + 0.1 * i)) for i, note in enumerate(("E5", "A5", "C#6", "E6"))]
    return level(mix(*run, noise(0.35, 2500, 9000, attack=0.05, tau=0.12, seed=201) * 0.35), 0.5)


def mend() -> np.ndarray:
    """A warm chord of bells blooming slowly: the heal chime, held and deepened."""
    chord = [(0.03 * i, tone(note, 0.9, attack=0.06, tau=0.45, partials=BELL) * gain) for i, (note, gain) in enumerate((("A4", 0.5), ("C#5", 0.4), ("E5", 0.4), ("A5", 0.3)))]
    return level(mix(*chord), 0.45)


def flame_strike() -> np.ndarray:
    """A whump of air catching fire, then its crackle."""
    whump = mix(thump(120, 50, 0.3, tau=0.1) * 0.8, noise(0.5, 200, 3000, attack=0.02, tau=0.18, seed=211))
    crackle = mix(*[(0.12 + i * 0.07, noise(0.04, 2000, 8000, tau=0.01, seed=212 + i) * 0.4) for i in range(6)])
    return level(mix(whump, crackle), 0.7)


def stoneskin() -> np.ndarray:
    """Stone grinding shut over flesh: a low scrape and a knock."""
    scrape = lowpass(noise(0.45, 80, 1400, attack=0.08, tau=0.2, seed=221), 900)
    return level(mix(scrape, (0.3, thump(160, 70, 0.2, tau=0.06) * 0.8), tone("A2", 0.5, attack=0.05, tau=0.3, partials=DARK) * 0.4), 0.6)


def entangle() -> np.ndarray:
    """Roots tearing up through the ground: creaks and a low rumble."""
    creaks = [(0.08 * i, tone(180 + 40 * i, 0.18, attack=0.02, tau=0.08, partials=DARK) * 0.4) for i in range(4)]
    return level(mix(lowpass(noise(0.6, 60, 900, attack=0.05, tau=0.25, seed=231), 600) * 0.9, *creaks), 0.6)


def wither() -> np.ndarray:
    """A falling, sickly chord and a sigh of wind."""
    chord = [(0.0, tone(note, 0.9, attack=0.1, tau=0.5, partials=PAD) * 0.3) for note in ("D4", "F4", "G#4")]
    fall = mix(*[(0.18 * i, tone(note, 0.4, attack=0.03, tau=0.2, partials=GLASS) * 0.35) for i, note in enumerate(("G#5", "F5", "D5"))])
    return level(mix(*chord, fall, noise(0.8, 300, 2000, attack=0.2, tau=0.4, seed=241) * 0.3), 0.5)


def meteor() -> np.ndarray:
    """The Meteor comes down: a deep impact, the ground shaking, debris falling."""
    boom = mix(thump(90, 30, 0.8, tau=0.3), noise(1.0, 40, 2500, attack=0.005, tau=0.35, seed=251) * 0.9)
    debris = mix(*[(0.25 + i * 0.09, noise(0.05, 800, 5000, tau=0.02, seed=252 + i) * 0.3) for i in range(7)])
    return level(mix(boom, debris), 0.85)


def meteor_fall() -> np.ndarray:
    """A Meteor called down: a low rumble high up and a rush swelling out of it, the fall begun (it lands two seconds
    after, as :func:`meteor`)."""
    length = 0.9
    rush = noise(length, 300, 4000, attack=length * 0.7, tau=0.12, seed=261)
    rumble = tone("A1", length, attack=0.2, tau=0.4, partials=DARK)
    return level(mix(rush, rumble * 0.6), 0.4)


def summon() -> np.ndarray:
    """Aether taking shape: a shimmer of bells over a swelling low tone."""
    shimmer = [(0.06 * i, tone(note, 0.5, attack=0.02, tau=0.25, partials=BELL) * 0.35) for i, note in enumerate(("E5", "B5", "E6", "G#6", "B6"))]
    return level(mix(tone("E3", 1.0, attack=0.3, tau=0.5, partials=PAD) * 0.5, *shimmer), 0.55)


def battle_fury() -> np.ndarray:
    """A war drum and a snarl of brass: blood up."""
    drum = mix(*[(0.14 * i, thump(110, 55, 0.2, tau=0.08) * (0.8 if i % 2 == 0 else 0.5)) for i in range(4)])
    horn = tone("D3", 0.7, attack=0.04, tau=0.4, partials=((1, 1.0), (2, 0.7), (3, 0.6), (4, 0.45), (5, 0.35)))
    return level(mix(drum, (0.05, horn * 0.6)), 0.7)


SOUNDS: dict[str, Callable[[], np.ndarray]] = {
    "spell_haste": haste, "spell_mend": mend, "spell_flame_strike": flame_strike, "spell_stoneskin": stoneskin,
    "spell_entangle": entangle, "spell_wither": wither, "spell_meteor": meteor, "spell_meteor_fall": meteor_fall,
    "spell_summon": summon, "spell_battle_fury": battle_fury,
}
