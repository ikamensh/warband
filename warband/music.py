"""Warband's music, synthesised with :mod:`saga2d.synth`: a march for each race and the night
watch for the title.  Every track is sixteen bars at 88 BPM under a detuned drone and loops
seamlessly (clips that run past the end wrap round to the start).
"""

from __future__ import annotations

import random
from collections.abc import Callable

import numpy as np

from saga2d import synth
from saga2d.synth import BELL, BRASS, GLASS, SOFT, hz, level, mix, noise, pan, thump, tone
from saga2d.synth import seconds as sample_times
from warband.rules import Race
from warband.voices import anvil_strike

BPM = 88
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
LOOP_SECONDS = BARS * BAR

Chords = tuple[tuple[int, tuple[str, ...]], ...]  # (bars, chord)


def _add_wrapped(out: np.ndarray, clip: np.ndarray, start_seconds: float) -> None:
    n = len(out)
    start = int(round(start_seconds * synth.SAMPLE_RATE)) % n
    first = min(len(clip), n - start)
    out[start:start + first] += clip[:first]
    out[:len(clip) - first] += clip[first:]


def _drone(chord: tuple[str, ...], length: float) -> np.ndarray:
    t = sample_times(length)
    fade = 1.2
    env = np.sin(np.minimum(1.0, t / fade) * np.pi / 2) * np.sin(np.minimum(1.0, (length - t) / fade) * np.pi / 2)
    out = np.zeros((len(t), 2))
    for note in chord:
        freq = hz(note)
        for channel, detune in ((0, 1.002), (1, 0.998)):
            out[:, channel] += np.sin(2 * np.pi * freq * detune * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * detune * t)
    return out * (env / len(chord))[:, None]


def _bed(chords: Chords, gain: float) -> np.ndarray:
    """A stereo loop holding the drone progression, ready for drums and lines."""
    out = np.zeros((int(round(LOOP_SECONDS * synth.SAMPLE_RATE)), 2))
    start = 0.0
    for bars, chord in chords:
        length = bars * BAR
        _add_wrapped(out, gain * _drone(chord, length + 1.2), start - 0.6)
        start += length
    return out


def _octave_up(note: str) -> str:
    return note[:-1] + str(int(note[-1]) + 1)


def _swell(period_fraction: float, depth: float) -> np.ndarray:
    return (1 - depth) + depth * np.sin(2 * np.pi * sample_times(LOOP_SECONDS) / (LOOP_SECONDS * period_fraction))


_MARCH: Chords = (
    (4, ("A2", "E3", "A3", "C4")), (2, ("F2", "C3", "F3", "A3")), (2, ("G2", "D3", "G3", "B3")),
    (4, ("A2", "E3", "A3", "C4")), (2, ("D3", "A3", "D4", "F4")), (2, ("E2", "B2", "E3", "G#3")),
)


def march() -> np.ndarray:
    """Humans: a slow drum march under an A-minor drone, with a sparse horn line."""
    out = _bed(_MARCH, 0.5)
    rng = random.Random(3)
    kick = thump(110, 45, 0.25, tau=0.09)
    snare = mix(noise(0.14, 600, 4000, tau=0.045, seed=90), thump(200, 120, 0.08, tau=0.03) * 0.5)
    for beat in range(BARS * 4):
        when = beat * BEAT
        if beat % 4 in (0, 2):
            _add_wrapped(out, pan(kick * 0.9, 0.0), when)
        if beat % 4 == 2 or (beat % 8 == 7 and rng.random() < 0.7):
            _add_wrapped(out, pan(snare * 0.35, 0.3), when)
        if beat % 8 == 7:
            _add_wrapped(out, pan(snare * 0.2, -0.3), when + BEAT / 2)
    horn_line = (("E4", 0), ("A4", 3), ("C5", 6), ("B4", 7), ("A4", 9), ("G4", 11), ("E4", 12))
    for note, bar in horn_line:
        clip = tone(note, 1.6, attack=0.08, tau=0.9, partials=BRASS) * 0.22
        _add_wrapped(out, pan(clip, 0.15 * (-1) ** bar), bar * BAR)
    return level(out * _swell(0.5, 0.1)[:, None], 0.45)


_VIGIL: Chords = (
    (4, ("D3", "A3", "D4", "F4")), (4, ("A#2", "F3", "A#3", "D4")), (4, ("C3", "G3", "C4", "E4")), (4, ("D3", "A3", "D4", "F4")),
)


def vigil() -> np.ndarray:
    """The title's quiet track: a slow D-minor drone with a bell every few bars and no drums — the night watch."""
    out = _bed(_VIGIL, 0.55)
    rng = random.Random(11)
    for bar in range(BARS):
        if bar % 2 == 0:
            note = rng.choice(("D5", "F5", "A5", "D6"))
            _add_wrapped(out, pan(tone(note, 2.2, attack=0.02, tau=1.1, partials=BELL) * 0.16, rng.uniform(-0.5, 0.5)), bar * BAR + rng.uniform(0, BEAT))
    return level(out * _swell(1 / 3, 0.15)[:, None], 0.4)


_WARPATH: Chords = (
    (4, ("D2", "A2", "D3", "F3")), (4, ("C2", "G2", "C3", "D#3")), (4, ("D2", "A2", "D3", "F3")),
    (2, ("A#1", "F2", "A#2", "D3")), (2, ("A1", "E2", "A2", "C#3")),
)


def warpath() -> np.ndarray:
    """Orcs: a kick on every beat, toms answering, rattles, and a growling low brass line."""
    out = _bed(_WARPATH, 0.4)
    rng = random.Random(5)
    kick = thump(95, 38, 0.3, tau=0.1)
    tom = thump(160, 70, 0.28, tau=0.09)
    rattle = noise(0.06, 2500, 7000, tau=0.02, seed=91)
    for beat in range(BARS * 4):
        when = beat * BEAT
        _add_wrapped(out, pan(kick * 0.95, 0.0), when)
        if beat % 4 in (1, 3):
            _add_wrapped(out, pan(tom * 0.6, 0.35 if beat % 4 == 1 else -0.35), when)
        if beat % 2 == 1:
            _add_wrapped(out, pan(tom * 0.35, -0.2), when + BEAT / 2)
        for sub in (0.25, 0.75):
            if rng.random() < 0.5:
                _add_wrapped(out, pan(rattle * 0.25, rng.uniform(-0.6, 0.6)), when + sub * BEAT)
    growl_line = (("D3", 0), ("F3", 2), ("D3", 4), ("C3", 6), ("D3", 8), ("A#2", 10), ("A2", 12), ("D3", 14))
    for note, bar in growl_line:
        clip = mix(tone(note, 1.4, attack=0.06, tau=0.7, partials=BRASS), noise(1.0, 90, 600, attack=0.1, tau=0.4, seed=92 + bar) * 0.35) * 0.24
        _add_wrapped(out, pan(clip, 0.1 * (-1) ** bar), bar * BAR)
    for bar in (3, 7, 11, 15):  # a shout at the end of every fourth bar
        _add_wrapped(out, pan(noise(0.35, 200, 1400, attack=0.03, tau=0.12, seed=120 + bar) * 0.3, 0.0), bar * BAR + 3 * BEAT)
    return level(out * _swell(0.5, 0.08)[:, None], 0.5)


_MOONLIGHT: Chords = (
    (4, ("D3", "A3", "D4", "F#4")), (4, ("B2", "F#3", "B3", "D4")), (4, ("G2", "D3", "G3", "B3")), (4, ("A2", "E3", "A3", "C#4")),
)


def moonlight() -> np.ndarray:
    """Elves: no drums; harp arpeggios every half bar under a flute line, bells on the bar."""
    out = _bed(_MOONLIGHT, 0.5)
    rng = random.Random(7)
    when = 0.0
    for bars, chord in _MOONLIGHT:
        for half in range(bars * 2):
            notes = list(chord[1:]) + [_octave_up(chord[1])]
            for i, note in enumerate(notes if half % 2 == 0 else reversed(notes)):
                _add_wrapped(out, pan(tone(note, 0.5, tau=0.25, partials=GLASS) * 0.14, -0.5 + i * 0.3), when + half * BAR / 2 + i * 0.12)
        when += bars * BAR
    flute_line = (("A4", 4), ("D5", 5), ("E5", 6), ("F#5", 7), ("D5", 9), ("B4", 10), ("A4", 11), ("F#4", 13))
    for note, bar in flute_line:
        _add_wrapped(out, pan(tone(note, 1.5, attack=0.06, tau=0.6, partials=SOFT) * 0.2, 0.1 * (-1) ** bar), bar * BAR + rng.uniform(0, 0.05))
    for bar in range(0, BARS, 2):
        _add_wrapped(out, pan(tone(rng.choice(("D6", "A6", "F#6")), 2.0, attack=0.02, tau=1.0, partials=BELL) * 0.1, rng.uniform(-0.4, 0.4)), bar * BAR)
    return level(out * _swell(1 / 3, 0.12)[:, None], 0.42)


_ANVIL: Chords = (
    (4, ("E2", "B2", "E3", "G3")), (4, ("C2", "G2", "C3", "E3")), (4, ("D2", "A2", "D3", "F#3")), (4, ("E2", "B2", "E3", "G3")),
)


def anvil() -> np.ndarray:
    """Dwarves: a deep kick and anvil on the first and third beats, a lighter strike between, and low horns."""
    out = _bed(_ANVIL, 0.45)
    kick = thump(70, 30, 0.35, tau=0.12)
    for beat in range(BARS * 4):
        when = beat * BEAT
        if beat % 4 in (0, 2):
            _add_wrapped(out, pan(kick * 0.9, 0.0), when)
            _add_wrapped(out, pan(anvil_strike(beat) * 0.3, 0.3), when)
        elif beat % 8 == 3:
            _add_wrapped(out, pan(anvil_strike(beat) * 0.18, -0.35), when)
    horn_line = (("E3", 0), ("G3", 3), ("B3", 6), ("A3", 7), ("G3", 9), ("E3", 11), ("D3", 12), ("E3", 14))
    for note, bar in horn_line:
        clip = mix(tone(note, 1.8, attack=0.08, tau=0.9, partials=BRASS), tone(hz(note) / 2, 1.8, attack=0.1, tau=0.8, partials=BRASS) * 0.5) * 0.2
        _add_wrapped(out, pan(clip, 0.12 * (-1) ** bar), bar * BAR)
    return level(out * _swell(0.5, 0.08)[:, None], 0.5)


TRACKS: dict[str, Callable[[], np.ndarray]] = {"march": march, "vigil": vigil, "warpath": warpath, "moonlight": moonlight, "anvil": anvil}
RACE_TRACKS: dict[Race, str] = {Race.HUMAN: "march", Race.ORC: "warpath", Race.ELF: "moonlight", Race.DWARF: "anvil"}
TITLE_TRACK = "vigil"
