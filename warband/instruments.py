"""Warband's orchestra: pitched voices and a drum kit, each a mono clip built on :mod:`saga2d.synth`.

Voices take a note name or a frequency and a length in seconds and return a clip whose
peak is near one; the score sets the gain.  Drums take no pitch.  Every function is
deterministic for a given *seed*, so a cached track is reproducible.
"""

from __future__ import annotations

import numpy as np

from saga2d.synth import AH, BELL, BRASS, GLASS, OH, formant, hz, level, lowpass, mix, noise, pluck, seconds, sustained, thump, tone

SAW = tuple((k, 1 / k) for k in range(1, 13))
REED = tuple((k, 1 / k) for k in range(1, 12, 2))  # odd harmonics: a chanter, a clarinet
BREATHY = ((1, 1.0), (2, 0.35), (3, 0.12), (4, 0.05))
CLEAR = ((1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12), (5, 0.06))

Note = str | float


def _freq(note: Note) -> float:
    return hz(note) if isinstance(note, str) else float(note)


# -- Bowed and blown -------------------------------------------------------------


def strings(note: Note, length: float, *, attack: float = 0.25, seed: int = 0) -> np.ndarray:
    """A violin section: three detuned saws with slow vibrato, warmed by a low-pass."""
    voice = sustained(note, length, partials=SAW, attack=attack, release=0.3, vibrato=(5.2, 0.004), voices=3, detune=0.004, seed=seed)
    return lowpass(voice, 2800) + noise(length, 1200, 4000, attack=attack, tau=length, seed=seed + 1) * 0.02


def cello(note: Note, length: float, *, attack: float = 0.2, seed: int = 0) -> np.ndarray:
    """Low strings: the same bow, darker."""
    voice = sustained(note, length, partials=SAW, attack=attack, release=0.25, vibrato=(4.8, 0.005), voices=2, detune=0.003, seed=seed)
    return lowpass(voice, 1600)


def horn(note: Note, length: float, *, attack: float = 0.08, seed: int = 0) -> np.ndarray:
    """A French horn section: bright partials, a soft-edged attack, a little unison shimmer."""
    voice = sustained(note, length, partials=BRASS, attack=attack, decay=0.4, sustain=0.85, release=0.15, vibrato=(5.0, 0.002), voices=2, detune=0.002, seed=seed)
    return lowpass(voice, 2500)


def warhorn(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A carnyx: a growling, over-blown low horn with a throaty flutter."""
    t = seconds(length)
    voice = sustained(note, length, partials=SAW, attack=0.15, release=0.2, vibrato=(4.0, 0.004), voices=2, detune=0.006, seed=seed)
    voice *= 1 + 0.25 * np.sin(2 * np.pi * 28 * t)
    return lowpass(voice, 1400) + noise(length, 200, 900, attack=0.15, tau=length, seed=seed + 1) * 0.06


def flute(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A wooden flute: soft partials, vibrato that sets in after the attack, and breath."""
    voice = sustained(note, length, partials=BREATHY, attack=0.06, release=0.12, vibrato=(5.5, 0.007), seed=seed)
    return voice + noise(length, 1500, 6000, attack=0.06, tau=length * 0.4, seed=seed + 1) * 0.04


def whistle(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A tin whistle: purer and brighter than the flute, with a quicker, wider vibrato."""
    voice = sustained(note, length, partials=CLEAR, attack=0.03, release=0.08, vibrato=(6.0, 0.009), seed=seed)
    return lowpass(voice, 7000) + noise(length, 2500, 8000, attack=0.03, tau=length * 0.3, seed=seed + 1) * 0.025


def chanter(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A reedy pipe: odd harmonics, nearly no vibrato, steady as a drone."""
    voice = sustained(note, length, partials=REED, attack=0.05, release=0.1, vibrato=(4.5, 0.001), voices=2, detune=0.002, seed=seed)
    return lowpass(voice, 3200)


def choir(note: Note, length: float, *, vowel=AH, attack: float = 0.3, seed: int = 0) -> np.ndarray:
    """Voices on a vowel: four detuned singers shaped by formants."""
    voice = sustained(note, length, partials=SAW[:10], attack=attack, release=0.4, vibrato=(4.5, 0.005), voices=4, detune=0.007, seed=seed)
    return lowpass(formant(voice, vowel), 4500)


def male_choir(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    return choir(note, length, vowel=OH, attack=0.4, seed=seed)


# -- Plucked and struck ----------------------------------------------------------


def harp(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    return pluck(note, length, brightness=0.7, tau=0.8, seed=seed)


def lute(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A gut-strung lute: dull pick, quick decay, a touch of pick scrape."""
    string = pluck(note, length, brightness=0.35, tau=0.35, seed=seed)
    return mix(string, noise(0.02, 2000, 7000, attack=0.002, tau=0.006, seed=seed + 1) * 0.12)


def dulcimer(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A hammered dulcimer: two bright strings a hair apart, shimmering."""
    f = _freq(note)
    return level(mix(pluck(f, length, brightness=0.85, tau=0.7, seed=seed), pluck(f * 1.0025, length, brightness=0.8, tau=0.6, seed=seed + 1) * 0.7), 1.0)


def bass(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    """A plucked bass with a sub under it."""
    f = _freq(note)
    voice = lowpass(sustained(f, length, partials=((1, 1.0), (2, 0.45), (3, 0.2), (4, 0.08)), attack=0.008, decay=0.35, sustain=0.5, release=0.06, seed=seed), 600)
    if f >= 80:  # below that it is already a sub; an octave lower would only be rumble
        voice += sustained(f / 2, length, partials=((1, 1.0),), attack=0.01, decay=0.3, sustain=0.4, release=0.06) * 0.3
    return voice * 0.5  # a near-sine peaks high for its loudness; sit with the other voices


def bell(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    return tone(note, length, attack=0.003, tau=length * 0.45, partials=BELL)


def chime(note: Note, length: float, *, seed: int = 0) -> np.ndarray:
    return tone(note, length, attack=0.003, tau=length * 0.35, partials=GLASS)


def timpani(note: Note, length: float = 1.2, *, seed: int = 0) -> np.ndarray:
    f = _freq(note)
    return level(mix(thump(f * 1.3, f, length, attack=0.003, tau=length * 0.18),
                     tone(f, length, attack=0.003, tau=length * 0.25, partials=((1, 1.0), (1.5, 0.5), (1.98, 0.3), (2.44, 0.15))) * 0.6,
                     noise(0.04, 200, 2000, tau=0.012, seed=seed) * 0.25), 1.0)


# -- Drums -----------------------------------------------------------------------


def kick(seed: int = 0) -> np.ndarray:
    return level(mix(thump(120, 44, 0.28, tau=0.07), noise(0.012, 1000, 5000, tau=0.004, seed=seed) * 0.3), 1.0)


def taiko(seed: int = 0) -> np.ndarray:
    """A big barrel drum: deep pitch drop, a skin slap, a long body."""
    return level(mix(thump(95, 48, 0.5, attack=0.003, tau=0.12),
                     tone(140, 0.4, attack=0.003, tau=0.06, partials=((1, 0.6), (1.59, 0.35), (2.14, 0.2))) * 0.5,
                     noise(0.08, 150, 1400, tau=0.03, seed=seed) * 0.5), 1.0)


def war_drum(seed: int = 0) -> np.ndarray:
    """Deeper and longer than the taiko; the one that shakes the ground."""
    return level(mix(thump(82, 46, 0.55, attack=0.004, tau=0.13), noise(0.12, 90, 900, tau=0.045, seed=seed) * 0.5), 1.0)


def snare(seed: int = 0) -> np.ndarray:
    return level(mix(noise(0.2, 400, 6500, tau=0.06, seed=seed), thump(220, 140, 0.1, tau=0.04) * 0.6), 1.0)


def field_snare(seed: int = 0) -> np.ndarray:
    """A deep military snare with a longer rattle."""
    return level(mix(noise(0.26, 250, 5000, tau=0.085, seed=seed), thump(180, 110, 0.12, tau=0.05) * 0.7), 1.0)


def tom(seed: int = 0, *, pitch: float = 150.0) -> np.ndarray:
    return level(mix(thump(pitch * 1.4, pitch * 0.7, 0.35, tau=0.12), noise(0.02, 300, 2500, tau=0.008, seed=seed) * 0.3), 1.0)


def frame_drum(seed: int = 0) -> np.ndarray:
    """A hand drum: a dry, quick skin with a fingertip on top."""
    return level(mix(thump(180, 95, 0.25, tau=0.08), noise(0.03, 500, 3000, tau=0.01, seed=seed) * 0.4), 1.0)


def hat(seed: int = 0, *, open: bool = False) -> np.ndarray:
    return noise(0.25 if open else 0.05, 6000, 14000, tau=0.09 if open else 0.015, seed=seed)


def shaker(seed: int = 0) -> np.ndarray:
    return noise(0.07, 3000, 9000, attack=0.012, tau=0.02, seed=seed)


def rattle(seed: int = 0) -> np.ndarray:
    return noise(0.06, 2500, 7000, tau=0.02, seed=seed)


def cymbal(seed: int = 0) -> np.ndarray:
    return level(mix(noise(1.4, 3000, 12000, attack=0.004, tau=0.45, seed=seed),
                     tone(3100, 1.2, attack=0.004, tau=0.4, partials=((1, 1.0), (1.48, 0.7), (2.13, 0.5), (2.9, 0.3))) * 0.25), 1.0)


def woodblock(seed: int = 0) -> np.ndarray:
    return tone(1200, 0.06, attack=0.001, tau=0.015, partials=((1, 1.0), (2.4, 0.4)))


def anvil(seed: int = 0) -> np.ndarray:
    from warband.voices import anvil_strike

    return level(anvil_strike(seed), 1.0)
