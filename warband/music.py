"""Warband's music: a suite for each race, the title's night watch and two endings, composed
with :mod:`warband.instruments` and :mod:`sagaforge.synth`.

Each race has two peaceful pieces, which alternate while the player builds, and one battle
piece that takes over when their army is fighting.  A piece is a :class:`Score` of 4/4 bars
filled section by section by layer functions (pad, line, arpeggio, bass, drums); the score
wraps tails round the loop, adds a room and masters to a common loudness.  The
:class:`Director` decides which track to play for a mood and when to rotate or crossfade;
:mod:`warband.sound` owns playback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import math
import random

import numpy as np

from sagaforge.synth import SAMPLE_RATE, highpass, loop_add, pan, reverb, soft_clip
from warband import instruments as inst
from warband.rules import Race

Voice = Callable[..., np.ndarray]
Motif = tuple[tuple[int, float], ...]  # (scale degree relative to the phrase centre, beats)
Progression = tuple[int, ...]  # chord root degrees, one per bar, cycling

MODES = {
    "ionian": (0, 2, 4, 5, 7, 9, 11), "dorian": (0, 2, 3, 5, 7, 9, 10), "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10), "aeolian": (0, 2, 3, 5, 7, 8, 10),
}
_NOTE_INDEX = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
SPREAD = (0, 2, 4, 7, 9, 11, 14)  # chord tones stacked in thirds, degrees above the root


class Key:
    """A root note and a mode; degrees count scale steps from the root (7 is the octave)."""

    def __init__(self, root: str, mode: str) -> None:
        self.root = 12 * (int(root[-1]) + 1) + _NOTE_INDEX[root[:-1]]
        self.steps = MODES[mode]

    def midi(self, degree: int) -> int:
        octave, step = divmod(degree, 7)
        return self.root + 12 * octave + self.steps[step]

    def hz(self, degree: int, octave: int = 0) -> float:
        return 440.0 * 2 ** ((self.midi(degree) + 12 * octave - 69) / 12)


def chord_at(progression: Progression, bar: int) -> int:
    return progression[bar % len(progression)]


class Score:
    """A stereo canvas of *bars* 4/4 bars at *bpm*.  Loops wrap whatever runs past the end round
    to the start; a one-shot keeps *tail* seconds after its last bar for the room to ring."""

    def __init__(self, bpm: float, bars: int, *, loop: bool = True, tail: float = 0.0) -> None:
        self.bpm, self.bars, self.loop = bpm, bars, loop
        self.beat = 60 / bpm
        self.length = bars * 4 * self.beat + (0.0 if loop else tail)
        self.out = np.zeros((int(round(self.length * SAMPLE_RATE)), 2))
        self._notes: dict[tuple, np.ndarray] = {}

    def add(self, clip: np.ndarray, beat: float, *, at: float = 0.0, gain: float = 1.0) -> None:
        """Place a mono clip at *beat* (0 is the first downbeat), panned to *at* (−1…1)."""
        clip = pan(clip * gain, at)
        if self.loop:
            loop_add(self.out, clip, beat * self.beat)
            return
        start = int(round(beat * self.beat * SAMPLE_RATE))
        end = min(len(self.out), start + len(clip))
        if start < end:
            self.out[start:end] += clip[:end - start]

    def note(self, voice: Voice, hz: float, length: float, seed: int = 0) -> np.ndarray:
        """*voice* at *hz* for *length* seconds, memoised: a pad chord or an ostinato note is rendered once."""
        key = (voice, round(hz, 2), round(length, 3), seed)
        if key not in self._notes:
            self._notes[key] = voice(hz, length, seed=seed)
        return self._notes[key]

    def master(self, *, room: float = 2.0, wet: float = 0.25, damping: float = 5000.0, rms: float = 0.11, seed: int = 0) -> np.ndarray:
        """Room, common loudness, soft limiting; the result is ready for ``write_wav``.

        Loudness is measured above 200 Hz, where the ear judges it, so a heavy drum or
        drone cannot push the melody down the way a plain RMS would."""
        out = reverb(self.out, decay=room, mix=wet, damping=damping, wrap=self.loop, seed=seed)
        if not self.loop:  # the room rings into the tail the score reserved, then fades out with it
            out = out[:len(self.out)]
            fade = min(len(out), int(0.4 * SAMPLE_RATE))
            out[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
        heard = highpass(out.mean(axis=1), 200.0, order=2)
        loudness = math.sqrt(float(np.mean(heard ** 2)))
        if loudness == 0:
            raise ValueError("A score with nothing on it cannot be mastered")
        out = soft_clip(out * (rms / loudness))
        peak = float(np.abs(out).max())
        return out * min(1.0, 0.8 / peak)


# -- Layers -------------------------------------------------------------------------


def pad(score: Score, key: Key, progression: Progression, voice: Voice, *, bars: int, start: int = 0, gain: float, at: float = 0.0,
        octave: int = 0, voicing: tuple[int, ...] = (0, 2, 4, 7), width: float = 0.3, overlap: float = 0.6, seed: int = 0) -> None:
    """Hold each chord for as long as it lasts, one voice per tone spread across the stereo field."""
    bar = start
    while bar < start + bars:
        root = chord_at(progression, bar)
        run = 1
        while bar + run < start + bars and chord_at(progression, bar + run) == root:
            run += 1
        for i, tone in enumerate(voicing):
            clip = score.note(voice, key.hz(root + tone, octave), run * 4 * score.beat + overlap, seed + i)
            score.add(clip, bar * 4 - 0.05, at=at + width * (2 * i / max(1, len(voicing) - 1) - 1), gain=gain)
        bar += run


def line(score: Score, key: Key, progression: Progression, motif: Motif, voice: Voice, *, bars: int, start: int = 0, gain: float,
         at: float = 0.0, octave: int = 1, legato: float = 0.95, shapes: tuple[str, ...] = ("A", "A2", "B", "A_end"),
         phrase_bars: int = 2, seed: int = 0) -> None:
    """Sing the motif in two-bar phrases, developing it: the plain shape, a sequence on the chord's
    third, its inversion on the fifth, then a version that comes to rest on the root."""
    rng = random.Random(seed)
    for index, phrase in enumerate(range(0, bars, phrase_bars)):
        bar = start + phrase
        root = chord_at(progression, bar)
        shape = shapes[index % len(shapes)]
        centre = {"A": root, "A2": root + 2, "B": root + 4, "A_end": root, "A_low": root - 7}[shape]
        notes = [(-degree, beats) for degree, beats in motif] if shape == "B" else list(motif)
        if shape == "A_end":
            degree, beats = notes[-1]
            notes[-1] = (0, min(beats * 2, phrase_bars * 4 - sum(b for _, b in notes[:-1])))
        beat = bar * 4
        for degree, beats in notes:
            clip = score.note(voice, key.hz(centre + degree, octave), beats * score.beat * legato, rng.randrange(3))
            score.add(clip, beat + rng.uniform(-0.02, 0.02), at=at + rng.uniform(-0.06, 0.06), gain=gain * rng.uniform(0.85, 1.0))
            beat += beats


def arpeggio(score: Score, key: Key, progression: Progression, voice: Voice, *, bars: int, start: int = 0, gain: float, at: float = 0.0,
             pattern: tuple[int, ...] = (0, 1, 2, 3, 2, 1), step: float = 0.5, octave: int = 0, ring: float = 1.8, width: float = 0.25,
             seed: int = 0) -> None:
    """Chord tones in a repeating pattern every *step* beats; *pattern* indexes the stacked thirds."""
    rng = random.Random(seed)
    per_bar = int(round(4 / step))
    for bar in range(start, start + bars):
        root = chord_at(progression, bar)
        for i in range(per_bar):
            tone = SPREAD[pattern[i % len(pattern)]]
            clip = score.note(voice, key.hz(root + tone, octave), step * score.beat * ring, i % 3)
            score.add(clip, bar * 4 + i * step, at=at + width * math.sin(i * 1.3), gain=gain * rng.uniform(0.8, 1.0))


def bassline(score: Score, key: Key, progression: Progression, *, bars: int, start: int = 0, gain: float, voice: Voice = inst.bass,
             rhythm: tuple[tuple[float, float, int], ...] = ((0, 1.6, 0), (2, 1.2, 0), (3.5, 0.5, 1)), octave: int = -1, seed: int = 0) -> None:
    """Root notes in a rhythm of (beat, length in beats, tone): tone 0 the root, 1 the fifth, 2 the octave."""
    for bar in range(start, start + bars):
        root = chord_at(progression, bar)
        for beat, beats, tone in rhythm:
            clip = score.note(voice, key.hz(root + (0, 4, 7)[tone], octave), beats * score.beat, seed)
            score.add(clip, bar * 4 + beat, gain=gain)


def drums(score: Score, kit: dict[str, tuple[Voice, float, float]], patterns: dict[str, str], *, bars: int, start: int = 0,
          fill: dict[str, str] | None = None, every: int = 8, seed: int = 0, takes: int = 3) -> None:
    """Step patterns per drum: 16 characters a bar (or 8 for eighths); ``X`` hard, ``x`` normal,
    ``o`` soft, ``.`` rest.  *fill* replaces the pattern on the last bar of each *every* bars."""
    rng = random.Random(seed)
    clips = {name: [drum(seed + take) for take in range(takes)] for name, (drum, _, _) in kit.items()}
    for bar in range(start, start + bars):
        filling = fill is not None and (bar + 1) % every == 0
        for name, (_, gain, at) in kit.items():
            pattern = (fill or {}).get(name, patterns.get(name, "")) if filling else patterns.get(name, "")
            if not pattern:
                continue
            step = 4 / len(pattern)
            for i, mark in enumerate(pattern):
                if mark == ".":
                    continue
                velocity = {"X": 1.0, "x": 0.8, "o": 0.5}[mark] * rng.uniform(0.9, 1.0)
                score.add(rng.choice(clips[name]), bar * 4 + i * step, at=at + rng.uniform(-0.03, 0.03), gain=gain * velocity)


def hits(score: Score, voice: Voice, beats: tuple[float, ...], *, gain: float, at: float = 0.0, seed: int = 0) -> None:
    """Single strokes of an unpitched voice at the given beats."""
    for i, beat in enumerate(beats):
        score.add(voice(seed + i), beat, at=at, gain=gain)


# -- Kits and motifs ---------------------------------------------------------------------

# Drum gains sit 6–10 dB over the sustained voices (whose gains are 0.1–0.2), as in a real mix;
# a low drum carries several times a snare's energy, so it needs the least.
MARCH_KIT = {"kick": (inst.kick, 0.3, 0.0), "snare": (inst.field_snare, 0.3, 0.25), "hat": (inst.hat, 0.1, -0.4)}
TRIBAL_KIT = {"war": (inst.war_drum, 0.28, 0.0), "taiko": (inst.taiko, 0.24, 0.2), "tom": (inst.tom, 0.22, -0.4), "rattle": (inst.rattle, 0.2, 0.5),
              "shaker": (inst.shaker, 0.12, -0.5)}
HAND_KIT = {"frame": (inst.frame_drum, 0.3, 0.1), "shaker": (inst.shaker, 0.14, -0.45), "tom": (inst.tom, 0.2, 0.4), "hat": (inst.hat, 0.1, 0.5)}
FORGE_KIT = {"war": (inst.war_drum, 0.28, 0.0), "anvil": (inst.anvil, 0.3, 0.35), "kick": (inst.kick, 0.28, 0.0), "snare": (inst.snare, 0.28, -0.25),
             "shaker": (inst.shaker, 0.12, 0.5)}

HUMAN_MOTIF: Motif = ((0, 1), (2, 1), (4, 1.5), (7, 0.5), (6, 1), (4, 1), (2, 2))
ORC_MOTIF: Motif = ((0, 0.5), (0, 0.5), (1, 1), (0, 1), (-2, 1), (0, 2), (1, 1), (0, 1))
ELF_MOTIF: Motif = ((4, 1), (6, 0.5), (7, 0.5), (6, 1), (4, 1), (2, 1.5), (3, 0.5), (4, 2))
DWARF_MOTIF: Motif = ((0, 1), (0, 0.5), (0, 0.5), (4, 1), (3, 1), (2, 1), (0, 1), (-3, 2))
VIGIL_MOTIF: Motif = ((4, 2), (2, 1), (0, 1), (-1, 2), (0, 2))


# -- Humans: A minor hearths, D dorian banners, D minor clash -------------------------------


def hearth(s: Score) -> np.ndarray:
    """Humans at peace: a lute under a flute, horns answering, a hand drum keeping the fields' time."""
    key, prog = Key("A2", "aeolian"), (0, 0, 5, 5, 2, 2, 6, 6)
    pad(s, key, prog, inst.strings, bars=32, gain=0.10, octave=1, voicing=(0, 4, 7, 9), seed=1)
    arpeggio(s, key, prog, inst.lute, bars=32, gain=0.16, at=-0.35, pattern=(0, 2, 3, 2, 1, 3), octave=1, seed=2)
    bassline(s, key, prog, bars=24, start=8, gain=0.22, seed=3)
    line(s, key, prog, HUMAN_MOTIF, inst.flute, bars=8, start=8, gain=0.20, at=0.2, octave=2, seed=4)
    line(s, key, prog, HUMAN_MOTIF, inst.horn, bars=8, start=16, gain=0.14, at=-0.15, octave=1, shapes=("A_low", "A", "B", "A_end"), seed=5)
    line(s, key, prog, HUMAN_MOTIF, inst.flute, bars=8, start=16, gain=0.11, at=0.35, octave=2, shapes=("B", "A2", "A", "A_end"), seed=6)
    line(s, key, prog, HUMAN_MOTIF, inst.flute, bars=4, start=26, gain=0.15, at=0.2, octave=2, shapes=("A", "A_end"), seed=7)
    drums(s, HAND_KIT, {"frame": "x..o..x...o...o.", "shaker": "..x...x...x...x."}, bars=16, start=8, seed=8)
    drums(s, HAND_KIT, {"frame": "x...o...x...o...", "shaker": "..o...o...o...o."}, bars=8, start=24, seed=9)
    return s.master(room=2.2, wet=0.28, seed=1)


def banners(s: Score) -> np.ndarray:
    """Humans on the move: a field snare march, horns carrying the theme, strings and choir behind."""
    key, prog = Key("D3", "dorian"), (0, 3, 0, 6, 0, 3, 5, 6)
    drums(s, MARCH_KIT, {"kick": "x.......x.......", "snare": "..o.x.o...o.x.oo"}, bars=8, seed=1)
    drums(s, MARCH_KIT, {"kick": "x...x...x...x...", "snare": "x.o.X.oox.o.X.oo", "hat": "..x...x...x...x."}, bars=16, start=8,
          fill={"snare": "xxoxxxoxXxxxXXXX"}, seed=2)
    drums(s, MARCH_KIT, {"kick": "x.......x.......", "snare": "..o.x.o...o.x..."}, bars=8, start=24, seed=3)
    bassline(s, key, prog, bars=32, gain=0.2, rhythm=((0, 1.8, 0), (2, 1.0, 0), (3, 0.9, 1)), seed=4)
    pad(s, key, prog, inst.cello, bars=32, gain=0.09, octave=0, voicing=(0, 4), width=0.2, seed=5)
    line(s, key, prog, HUMAN_MOTIF, inst.horn, bars=16, start=8, gain=0.18, at=-0.1, octave=1, seed=6)
    pad(s, key, prog, inst.strings, bars=16, start=16, gain=0.09, octave=1, voicing=(0, 2, 4, 7), seed=7)
    pad(s, key, prog, inst.choir, bars=8, start=24, gain=0.10, octave=1, voicing=(0, 4, 7), seed=8)
    line(s, key, prog, HUMAN_MOTIF, inst.flute, bars=8, start=24, gain=0.13, at=0.3, octave=2, shapes=("A2", "B", "A", "A_end"), seed=9)
    arpeggio(s, key, prog, inst.lute, bars=8, start=24, gain=0.12, at=0.3, pattern=(0, 3, 2, 3), octave=1, seed=10)
    hits(s, inst.cymbal, (32,), gain=0.12, at=0.3)
    return s.master(room=1.8, wet=0.22, seed=2)


def clash(s: Score) -> np.ndarray:
    """Humans at war: timpani and snare, a driving low-string ostinato, brass stabs and a choir at the height."""
    key, prog = Key("D3", "aeolian"), (0, 0, 5, 6, 0, 0, 3, 6)
    drums(s, MARCH_KIT, {"kick": "x..x..x.x..x..x.", "snare": "....x.......x...", "hat": "x.x.x.x.x.x.x.x."}, bars=32,
          fill={"snare": "x.x.x.x.xxxxXXXX", "kick": "x...x...x...x..."}, seed=1)
    for bar in range(0, 32, 2):
        s.add(inst.timpani(key.hz(chord_at(prog, bar), -1), 1.0, seed=bar), bar * 4, gain=0.14)
        s.add(inst.timpani(key.hz(chord_at(prog, bar + 1) + 4, -1), 0.6, seed=bar + 1), bar * 4 + 6, gain=0.08)
    arpeggio(s, key, prog, inst.cello, bars=32, gain=0.16, at=-0.2, pattern=(0, 0, 2, 0, 1, 0, 3, 2), step=0.5, octave=0, ring=0.95, seed=2)
    arpeggio(s, key, prog, inst.strings, bars=16, start=16, gain=0.10, at=0.3, pattern=(3, 2, 1, 0, 1, 2), step=0.25, octave=1, ring=1.2, seed=3)
    line(s, key, prog, HUMAN_MOTIF, inst.horn, bars=8, start=8, gain=0.3, at=0.1, octave=1, legato=0.6, seed=4)
    line(s, key, prog, HUMAN_MOTIF, inst.horn, bars=8, start=24, gain=0.32, at=0.1, octave=1, legato=0.7, shapes=("A", "B", "A2", "A_end"), seed=5)
    pad(s, key, prog, inst.choir, bars=8, start=24, gain=0.16, octave=1, voicing=(0, 4, 7), seed=6)
    pad(s, key, prog, inst.cello, bars=8, start=16, gain=0.08, octave=0, voicing=(0, 4), seed=7)
    hits(s, inst.cymbal, (0, 32, 64, 96), gain=0.14, at=0.3)
    return s.master(room=1.6, wet=0.2, rms=0.13, seed=3)


# -- Orcs: D phrygian ------------------------------------------------------------------------


def bonfire(s: Score) -> np.ndarray:
    """Orcs at rest: a low horn drone, a slow taiko, rattles, and a chant that circles the flat second."""
    key, prog = Key("D2", "phrygian"), (0, 0, 0, 1, 0, 0, 6, 1)
    pad(s, key, prog, inst.warhorn, bars=32, gain=0.12, octave=1, voicing=(0,), width=0.0, overlap=1.5, seed=1)
    pad(s, key, prog, inst.cello, bars=32, gain=0.07, octave=1, voicing=(0, 4), seed=2)
    bassline(s, key, prog, bars=24, start=8, gain=0.14, rhythm=((0, 3.6, 0),), octave=0, seed=9)
    drums(s, TRIBAL_KIT, {"taiko": "x.......o.......", "shaker": "..x...x...x...x.", "rattle": "......x.......x."}, bars=8, seed=3)
    drums(s, TRIBAL_KIT, {"war": "x...............", "taiko": "x...o...x...o.o.", "tom": "..........x...x.", "shaker": "..x...x...x...x.",
                          "rattle": "......x.......xx"}, bars=16, start=8, fill={"taiko": "x.x.x.x.xxxxxxxx"}, seed=4)
    drums(s, TRIBAL_KIT, {"taiko": "x.......o.......", "rattle": "......x.......x."}, bars=8, start=24, seed=5)
    line(s, key, prog, ORC_MOTIF, inst.male_choir, bars=16, start=8, gain=0.16, octave=1, legato=1.0, seed=6)
    line(s, key, prog, ORC_MOTIF, inst.chanter, bars=8, start=16, gain=0.11, at=0.35, octave=2, shapes=("B", "A", "A2", "A_end"), seed=7)
    line(s, key, prog, ORC_MOTIF, inst.warhorn, bars=8, start=24, gain=0.10, at=-0.2, octave=1, shapes=("A_low", "A_end"), phrase_bars=4, seed=8)
    return s.master(room=2.4, wet=0.3, damping=3500, seed=4)


def warpath(s: Score) -> np.ndarray:
    """Orcs marching: drums on every beat, toms answering, growling horns and shouted chant hits."""
    key, prog = Key("D2", "phrygian"), (0, 0, 1, 0, 0, 0, 2, 1)
    drums(s, TRIBAL_KIT, {"war": "x...x...x...x...", "tom": "..x.....x....x..", "rattle": ".x.x.x.x.x.x.x.x"}, bars=8, seed=1)
    drums(s, TRIBAL_KIT, {"war": "x...x...x...x...", "taiko": "..x...x...x.x.x.", "tom": "......x.......x.", "rattle": ".x.x.x.x.x.x.x.x",
                          "shaker": "x.x.x.x.x.x.x.x."}, bars=24, start=8, fill={"taiko": "x.x.x.x.xxxxxxxx", "tom": "........x.x.xxxx"}, seed=2)
    bassline(s, key, prog, bars=32, gain=0.16, voice=inst.bass, rhythm=((0, 0.9, 0), (1, 0.9, 0), (2, 0.9, 0), (3, 0.9, 0)), octave=1, seed=3)
    line(s, key, prog, ORC_MOTIF, inst.warhorn, bars=16, start=8, gain=0.24, at=-0.1, octave=2, legato=0.8, seed=4)
    pad(s, key, prog, inst.male_choir, bars=8, start=16, gain=0.18, octave=1, voicing=(0, 4, 7), seed=5)
    line(s, key, prog, ORC_MOTIF, inst.chanter, bars=8, start=24, gain=0.16, at=0.3, octave=2, shapes=("A2", "B", "A", "A_end"), seed=6)
    for bar in (3, 7, 11, 15, 19, 23, 27, 31):  # a shout at the end of every fourth bar
        s.add(inst.male_choir(key.hz(0, 1), 0.35, seed=bar), bar * 4 + 3, gain=0.5)
    return s.master(room=1.8, wet=0.22, damping=4000, rms=0.12, seed=5)


def bloodrush(s: Score) -> np.ndarray:
    """Orcs at war: war drums in eighths, taiko accents, a horn ostinato hammering the flat second, shrieking pipes."""
    key, prog = Key("D2", "phrygian"), (0, 0, 1, 0, 0, 2, 1, 0)
    drums(s, TRIBAL_KIT, {"war": "x...x...x...x...", "taiko": "....x.......x.x.", "tom": "x.x.x.x.x.x.x.x.", "rattle": "x.x.x.x.x.x.x.x.",
                          "shaker": ".x.x.x.x.x.x.x.x"}, bars=32, fill={"taiko": "x.x.x.x.xxxxXXXX", "tom": "xxxxxxxxxxxxxxxx"}, every=8, seed=1)
    arpeggio(s, key, prog, inst.warhorn, bars=32, gain=0.2, at=-0.15, pattern=(0, 0, 1, 0, 0, 3, 1, 0), step=0.5, octave=2, ring=0.9, seed=2)
    arpeggio(s, key, prog, inst.cello, bars=16, start=16, gain=0.12, at=0.25, pattern=(0, 2, 3, 2), step=0.25, octave=1, ring=1.1, seed=3)
    line(s, key, prog, ORC_MOTIF, inst.chanter, bars=8, start=8, gain=0.18, at=0.3, octave=3, legato=0.7, seed=4)
    line(s, key, prog, ORC_MOTIF, inst.warhorn, bars=8, start=24, gain=0.24, at=0.0, octave=2, legato=0.7, shapes=("A", "B", "A2", "A_end"), seed=5)
    pad(s, key, prog, inst.male_choir, bars=8, start=24, gain=0.18, octave=1, voicing=(0, 4, 7), seed=6)
    for bar in range(0, 32, 2):
        s.add(inst.male_choir(key.hz(0, 1), 0.3, seed=bar), bar * 4 + 2, gain=0.45, at=0.2)
    hits(s, inst.cymbal, (0, 32, 64, 96), gain=0.13, at=-0.3)
    return s.master(room=1.5, wet=0.18, damping=4000, rms=0.135, seed=6)


# -- Elves: D lydian, D dorian for the hunt ---------------------------------------------------


def moonlight(s: Score) -> np.ndarray:
    """Elves at peace: harp arpeggios under a whistle, bells on the moon's beat, strings breathing."""
    key, prog = Key("D3", "lydian"), (0, 5, 1, 4, 0, 5, 1, 4)
    pad(s, key, prog, inst.strings, bars=32, gain=0.09, octave=0, voicing=(0, 4, 7, 9), seed=1)
    arpeggio(s, key, prog, inst.harp, bars=32, gain=0.15, at=-0.2, pattern=(0, 1, 2, 3, 4, 3, 2, 1), step=0.5, octave=0, ring=2.2, seed=2)
    for bar in range(0, 32, 2):
        s.add(inst.bell(key.hz((0, 4, 7)[bar // 2 % 3], 2), 2.5, seed=bar), bar * 4, at=0.4 * math.sin(bar), gain=0.08)
    line(s, key, prog, ELF_MOTIF, inst.whistle, bars=8, start=8, gain=0.14, at=0.25, octave=2, seed=3)
    pad(s, key, prog, inst.choir, bars=16, start=16, gain=0.08, octave=1, voicing=(0, 2, 4), seed=4)
    line(s, key, prog, ELF_MOTIF, inst.flute, bars=8, start=16, gain=0.14, at=0.2, octave=2, shapes=("A2", "B", "A", "A_end"), seed=5)
    line(s, key, prog, ELF_MOTIF, inst.whistle, bars=8, start=24, gain=0.10, at=-0.3, octave=2, shapes=("B", "A_end"), phrase_bars=4, seed=6)
    drums(s, HAND_KIT, {"frame": "x.......o.......", "shaker": "....x.......x..."}, bars=8, start=16, seed=7)
    return s.master(room=3.0, wet=0.35, damping=6000, rms=0.10, seed=7)


def starfall(s: Score) -> np.ndarray:
    """Elves at peace, later: a choir on a slow lydian tide, shimmering harp sixteenths, chimes, a flute above."""
    key, prog = Key("D3", "lydian"), (0, 0, 1, 1, 5, 5, 4, 4)
    pad(s, key, prog, inst.choir, bars=32, gain=0.10, octave=0, voicing=(0, 4, 7, 9), overlap=1.0, seed=1)
    arpeggio(s, key, prog, inst.harp, bars=24, start=8, gain=0.09, at=0.3, pattern=(3, 5, 4, 6, 5, 4), step=0.25, octave=0, ring=1.4, seed=2)
    arpeggio(s, key, prog, inst.harp, bars=8, gain=0.12, at=-0.3, pattern=(0, 2, 4, 5), step=0.5, octave=0, ring=2.0, seed=3)
    for bar in range(0, 32, 4):
        s.add(inst.chime(key.hz((7, 9, 11, 14)[bar // 4 % 4], 1), 1.8, seed=bar), bar * 4 + 3.5, at=-0.5 + (bar % 8) / 8, gain=0.07)
    line(s, key, prog, ELF_MOTIF, inst.flute, bars=16, start=8, gain=0.13, at=0.15, octave=2, seed=4)
    line(s, key, prog, ELF_MOTIF, inst.strings, bars=8, start=24, gain=0.10, at=-0.2, octave=1, shapes=("A_low", "A_end"), phrase_bars=4, seed=5)
    bassline(s, key, prog, bars=16, start=16, gain=0.14, voice=inst.cello, rhythm=((0, 4.0, 0),), octave=-1, seed=6)
    drums(s, HAND_KIT, {"frame": "x...............", "shaker": "..o...o...o...o.", "hat": "....x.......x..."}, bars=16, start=16, seed=7)
    return s.master(room=3.2, wet=0.38, damping=7000, rms=0.10, seed=8)


def wildhunt(s: Score) -> np.ndarray:
    """Elves at war: a harp ostinato in sixteenths, hand drums running, strings and horns calling the hunt."""
    key, prog = Key("D3", "dorian"), (0, 0, 3, 6, 0, 0, 5, 6)
    drums(s, HAND_KIT, {"frame": "x..x..x...x.x...", "shaker": "x.x.x.x.x.x.x.x.", "tom": "......x.......x.", "hat": "..x...x...x...x."}, bars=32,
          fill={"tom": "x.x.x.x.xxxxxxxx", "frame": "x...x...x...x..."}, seed=1)
    hits(s, inst.kick, tuple(float(b) for b in range(32, 128, 2)), gain=0.25, seed=2)
    arpeggio(s, key, prog, inst.harp, bars=32, gain=0.13, at=-0.25, pattern=(0, 2, 3, 2, 1, 3, 4, 3), step=0.25, octave=0, ring=1.6, seed=3)
    arpeggio(s, key, prog, inst.strings, bars=16, start=8, gain=0.10, at=0.25, pattern=(0, 3, 2, 3), step=0.5, octave=1, ring=1.0, seed=4)
    bassline(s, key, prog, bars=32, gain=0.18, voice=inst.cello, rhythm=((0, 1.0, 0), (1.5, 0.5, 0), (2, 1.0, 1), (3, 1.0, 0)), octave=0, seed=5)
    line(s, key, prog, ELF_MOTIF, inst.whistle, bars=8, start=8, gain=0.13, at=0.3, octave=2, legato=0.8, seed=6)
    line(s, key, prog, ELF_MOTIF, inst.horn, bars=8, start=16, gain=0.16, at=-0.1, octave=1, legato=0.7, shapes=("A", "B", "A2", "A_end"), seed=7)
    line(s, key, prog, ELF_MOTIF, inst.whistle, bars=8, start=24, gain=0.14, at=0.3, octave=2, legato=0.8, shapes=("A2", "B", "A", "A_end"), seed=8)
    pad(s, key, prog, inst.choir, bars=8, start=24, gain=0.10, octave=1, voicing=(0, 4, 7), seed=9)
    hits(s, inst.cymbal, (32, 96), gain=0.11, at=0.3)
    return s.master(room=2.0, wet=0.24, damping=6000, rms=0.125, seed=9)


# -- Dwarves: E aeolian ----------------------------------------------------------------------


def deepforge(s: Score) -> np.ndarray:
    """Dwarves at work: anvils on the beat, a deep drum, low horns and a hammered dulcimer over a male choir."""
    key, prog = Key("E2", "aeolian"), (0, 0, 6, 6, 5, 5, 6, 6)
    pad(s, key, prog, inst.male_choir, bars=32, gain=0.11, octave=1, voicing=(0, 4, 7), width=0.35, seed=1)
    drums(s, FORGE_KIT, {"anvil": "o.......x.......", "war": "x..............."}, bars=8, seed=2)
    drums(s, FORGE_KIT, {"anvil": "x...o...x...o.o.", "war": "x.......x.......", "shaker": "..x...x...x...x."}, bars=16, start=8,
          fill={"anvil": "x.x.x.x.x.x.xxxx"}, seed=3)
    drums(s, FORGE_KIT, {"anvil": "x.......x.......", "war": "x..............."}, bars=8, start=24, seed=4)
    bassline(s, key, prog, bars=24, start=8, gain=0.2, rhythm=((0, 1.8, 0), (2, 1.8, 0)), octave=0, seed=5)
    line(s, key, prog, DWARF_MOTIF, inst.horn, bars=8, start=8, gain=0.17, at=-0.15, octave=1, seed=6)
    arpeggio(s, key, prog, inst.dulcimer, bars=16, start=16, gain=0.11, at=0.35, pattern=(0, 2, 1, 3, 2, 4), step=0.5, octave=1, ring=1.6, seed=7)
    line(s, key, prog, DWARF_MOTIF, inst.cello, bars=8, start=16, gain=0.14, at=-0.2, octave=0, shapes=("A_low", "A", "B", "A_end"), seed=8)
    line(s, key, prog, DWARF_MOTIF, inst.horn, bars=8, start=24, gain=0.12, at=0.1, octave=1, shapes=("A2", "A_end"), phrase_bars=4, seed=9)
    return s.master(room=2.6, wet=0.3, damping=4000, seed=10)


def stonehall(s: Score) -> np.ndarray:
    """Dwarves at ease: a reed drone with a chanter tune, dulcimer, a hall of male voices, a frame drum."""
    key, prog = Key("E2", "dorian"), (0, 0, 3, 3, 0, 0, 6, 6)
    pad(s, key, prog, inst.chanter, bars=32, gain=0.07, octave=1, voicing=(0,), width=0.0, overlap=1.2, seed=1)
    pad(s, key, prog, inst.male_choir, bars=32, gain=0.10, octave=1, voicing=(0, 4, 7), seed=2)
    arpeggio(s, key, prog, inst.dulcimer, bars=32, gain=0.12, at=0.3, pattern=(0, 3, 2, 3, 1, 3), step=0.5, octave=1, ring=1.5, seed=3)
    line(s, key, prog, DWARF_MOTIF, inst.chanter, bars=16, start=8, gain=0.12, at=-0.25, octave=2, seed=4)
    bassline(s, key, prog, bars=24, start=8, gain=0.18, rhythm=((0, 1.8, 0), (2, 1.0, 0), (3, 0.9, 1)), octave=0, seed=5)
    drums(s, HAND_KIT, {"frame": "x...x...x...x.o.", "shaker": "..x...x...x...x."}, bars=16, start=8, seed=6)
    drums(s, FORGE_KIT, {"anvil": "x.......x.......", "war": "x...............", "shaker": "..x...x...x...x."}, bars=8, start=24, seed=7)
    line(s, key, prog, DWARF_MOTIF, inst.horn, bars=8, start=24, gain=0.14, at=0.1, octave=1, shapes=("A", "B", "A2", "A_end"), seed=8)
    return s.master(room=2.8, wet=0.32, damping=4000, seed=11)


def ironwall(s: Score) -> np.ndarray:
    """Dwarves at war: an anvil ostinato, kick and snare, low strings hammering, horns and timpani."""
    key, prog = Key("E2", "aeolian"), (0, 0, 5, 6, 0, 0, 3, 6)
    drums(s, FORGE_KIT, {"anvil": "x.x.x.x.x.x.x.x.", "kick": "x...x...x...x...", "snare": "....x.......x...", "war": "x.......x......."}, bars=32,
          fill={"snare": "x.x.x.x.xxxxxxxx", "anvil": "x...x...x...xxxx"}, seed=1)
    arpeggio(s, key, prog, inst.cello, bars=32, gain=0.15, at=-0.2, pattern=(0, 0, 3, 0, 0, 2, 0, 1), step=0.5, octave=0, ring=0.95, seed=2)
    for bar in range(0, 32, 4):
        s.add(inst.timpani(key.hz(chord_at(prog, bar), 0), 1.0, seed=bar), bar * 4, gain=0.22)
    line(s, key, prog, DWARF_MOTIF, inst.horn, bars=8, start=8, gain=0.3, at=0.1, octave=1, legato=0.7, seed=3)
    line(s, key, prog, DWARF_MOTIF, inst.warhorn, bars=8, start=16, gain=0.22, at=-0.1, octave=2, legato=0.7, shapes=("A_low", "A", "B", "A_end"), seed=4)
    pad(s, key, prog, inst.male_choir, bars=16, start=16, gain=0.16, octave=1, voicing=(0, 4, 7), seed=5)
    line(s, key, prog, DWARF_MOTIF, inst.horn, bars=8, start=24, gain=0.3, at=0.1, octave=1, legato=0.7, shapes=("A", "B", "A2", "A_end"), seed=6)
    arpeggio(s, key, prog, inst.strings, bars=8, start=24, gain=0.09, at=0.3, pattern=(3, 2, 1, 0), step=0.25, octave=1, ring=1.2, seed=7)
    hits(s, inst.cymbal, (0, 32, 64, 96), gain=0.13, at=0.3)
    return s.master(room=1.7, wet=0.2, damping=4500, rms=0.13, seed=12)


# -- The title and the endings -----------------------------------------------------------------


def vigil(s: Score) -> np.ndarray:
    """The night watch on the title: low strings, a bell, distant voices, a harp in the small hours."""
    key, prog = Key("D2", "aeolian"), (0, 0, 5, 5, 2, 2, 6, 6)
    pad(s, key, prog, inst.cello, bars=24, gain=0.10, octave=0, voicing=(0, 4, 7), width=0.25, overlap=1.5, seed=1)
    pad(s, key, prog, inst.strings, bars=24, gain=0.06, octave=1, voicing=(2, 7, 9), overlap=1.5, seed=2)
    for bar in range(0, 24, 2):
        s.add(inst.bell(key.hz((7, 9, 11, 14)[bar // 2 % 4], 1), 3.5, seed=bar), bar * 4 + (0.5 if bar % 4 else 0), at=0.5 * math.sin(bar), gain=0.09)
    pad(s, key, prog, inst.choir, bars=8, start=8, gain=0.07, octave=1, voicing=(0, 4), seed=3)
    arpeggio(s, key, prog, inst.harp, bars=8, start=16, gain=0.09, at=-0.3, pattern=(0, 2, 4, 5, 4, 2), step=1.0, octave=1, ring=2.5, seed=4)
    line(s, key, prog, VIGIL_MOTIF, inst.flute, bars=8, start=8, gain=0.09, at=0.3, octave=2, shapes=("A", "A_end"), phrase_bars=4, seed=5)
    hits(s, inst.war_drum, (32.0, 40.0, 48.0, 56.0), gain=0.15, seed=6)
    return s.master(room=3.5, wet=0.4, damping=4500, rms=0.09, seed=13)


def victory(s: Score) -> np.ndarray:
    """A fanfare in D major: horns rising to the octave over timpani and a cymbal, strings holding the last chord."""
    key = Key("D3", "ionian")
    fanfare = ((0, 0.5), (0, 0.5), (0, 1), (4, 1), (7, 1), (9, 0.5), (7, 0.5), (4, 1))
    beat = 0.0
    for degree, beats in fanfare:
        s.add(inst.horn(key.hz(degree, 1), beats * s.beat * 0.9, seed=int(beat * 2)), beat, gain=0.32)
        s.add(inst.horn(key.hz(degree - 3 if degree else 0, 1), beats * s.beat * 0.9, seed=int(beat * 2) + 1), beat, gain=0.16, at=0.3)
        beat += beats
    for degree, at in ((0, -0.3), (4, 0.3), (7, 0.0), (11, -0.15), (14, 0.15)):
        s.add(inst.horn(key.hz(degree, 1), 3.5, seed=degree), 8, gain=0.24, at=at)
        s.add(inst.strings(key.hz(degree, 1), 6.0, attack=0.4, seed=degree), 8, gain=0.12, at=-at)
    s.add(inst.timpani(key.hz(0, -1), 1.2), 0, gain=0.25)
    s.add(inst.timpani(key.hz(4, -1), 1.2, seed=1), 4, gain=0.2)
    s.add(inst.timpani(key.hz(0, -1), 1.8, seed=2), 8, gain=0.3)
    hits(s, inst.snare, tuple(6 + i * 0.25 for i in range(8)), gain=0.25, at=0.2)
    hits(s, inst.cymbal, (8,), gain=0.18, at=0.3)
    for i, degree in enumerate((7, 11, 14)):
        s.add(inst.bell(key.hz(degree, 1), 3.0, seed=i), 8 + i * 0.5, gain=0.07, at=-0.4 + 0.4 * i)
    return s.master(room=2.4, wet=0.28, rms=0.12, seed=14)


def defeat(s: Score) -> np.ndarray:
    """A lament in D minor: cellos falling stepwise to the low root, a single bell, voices fading, one last drum."""
    key = Key("D2", "aeolian")
    for i, degree in enumerate((7, 6, 5, 4)):
        s.add(inst.cello(key.hz(degree, 0), 3.6, attack=0.3, seed=i), i * 4, gain=0.22, at=-0.2)
        s.add(inst.choir(key.hz(degree - 3, 1), 3.8, seed=i + 10), i * 4 + 0.1, gain=0.09, at=0.3)
    s.add(inst.cello(key.hz(0, 0), 6.0, attack=0.5, seed=5), 16, gain=0.26)
    s.add(inst.cello(key.hz(4, -1), 6.0, attack=0.5, seed=6), 16, gain=0.18, at=0.2)
    s.add(inst.bell(key.hz(0, 2), 4.0, seed=7), 4, gain=0.06, at=0.4)
    s.add(inst.bell(key.hz(0, 1), 5.0, seed=8), 16, gain=0.07, at=-0.4)
    hits(s, inst.war_drum, (0.0, 8.0, 16.0), gain=0.2, seed=9)
    return s.master(room=3.5, wet=0.4, damping=3500, rms=0.09, seed=15)


# -- Catalogue and director -------------------------------------------------------------------


@dataclass(frozen=True)
class Suite:
    peace: tuple[str, ...]
    battle: str


SUITES: dict[Race, Suite] = {
    Race.HUMAN: Suite(("hearth", "banners"), "clash"),
    Race.ORC: Suite(("bonfire", "warpath"), "bloodrush"),
    Race.ELF: Suite(("moonlight", "starfall"), "wildhunt"),
    Race.DWARF: Suite(("deepforge", "stonehall"), "ironwall"),
}
TITLE_TRACK = "vigil"
STINGERS = ("victory", "defeat")


@dataclass(frozen=True)
class Piece:
    """A composition and the canvas it is written on."""

    compose: Callable[[Score], np.ndarray]
    bpm: float
    bars: int
    loop: bool = True
    tail: float = 0.0

    @property
    def seconds(self) -> float:
        """How long one pass takes; a loop's rotation point."""
        return self.bars * 4 * 60 / self.bpm + (0.0 if self.loop else self.tail)

    def render(self) -> np.ndarray:
        return self.compose(Score(self.bpm, self.bars, loop=self.loop, tail=self.tail))


PIECES: dict[str, Piece] = {
    "hearth": Piece(hearth, 96, 32), "banners": Piece(banners, 104, 32), "clash": Piece(clash, 132, 32),
    "bonfire": Piece(bonfire, 84, 32), "warpath": Piece(warpath, 108, 32), "bloodrush": Piece(bloodrush, 140, 32),
    "moonlight": Piece(moonlight, 76, 32), "starfall": Piece(starfall, 88, 32), "wildhunt": Piece(wildhunt, 128, 32),
    "deepforge": Piece(deepforge, 80, 32), "stonehall": Piece(stonehall, 92, 32), "ironwall": Piece(ironwall, 124, 32),
    "vigil": Piece(vigil, 66, 24), "victory": Piece(victory, 120, 6, loop=False, tail=4.0), "defeat": Piece(defeat, 60, 5, loop=False, tail=5.0),
}
TRACKS: dict[str, Callable[[], np.ndarray]] = {name: piece.render for name, piece in PIECES.items()}
MOODS = ("title", "peace", "battle", "victory", "defeat")


@dataclass(frozen=True)
class Choice:
    track: str
    fade: float
    loop: bool


@dataclass
class Director:
    """Turns a mood into track changes.  Peaceful pieces alternate at their loop points, a battle
    piece plays at least :attr:`min_battle` seconds once begun, an ending plays once, and every
    change crossfades.  The caller reports what is actually playing and since when, so a track
    that ended or started late is seen as it is."""

    min_battle: float = 12.0
    rotate_fade: float = 4.0
    _variant: dict[Race, int] = field(default_factory=dict)
    _ended: str | None = None

    def choose(self, mood: str, race: Race | None, now: float, playing: str | None, started: float) -> Choice | None:
        """The track to start for *mood* at *now*, or ``None`` to leave *playing* alone."""
        if mood not in MOODS:
            raise ValueError(f"Unknown mood {mood!r}; moods are {MOODS}")
        if mood in ("peace", "battle") and race is None:
            raise ValueError(f"The {mood} mood needs the player's race")
        if mood in STINGERS:
            if playing == mood or self._ended == mood:
                return None
            self._ended = mood
            return Choice(mood, 1.0 if playing else 0.5, False)
        self._ended = None
        if mood == "title":
            return None if playing == TITLE_TRACK else Choice(TITLE_TRACK, 2.0 if playing else 1.0, True)
        suite = SUITES[race]
        if mood == "battle":
            return None if playing == suite.battle else Choice(suite.battle, 1.5 if playing else 0.5, True)
        if playing == suite.battle and now - started < self.min_battle:
            return None
        if playing in suite.peace:
            if now - started < PIECES[playing].seconds:
                return None
            variant = (suite.peace.index(playing) + 1) % len(suite.peace)
            self._variant[race] = variant
            return Choice(suite.peace[variant], self.rotate_fade, True)
        return Choice(suite.peace[self._variant.get(race, 0)], 3.0 if playing else 1.0, True)
