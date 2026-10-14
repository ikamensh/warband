"""Campaign monuments answer with a shared resonance motif and distinct physical voices.

Bells ring bronze, anchors release a trapped low chord, stone gates slide open, refuges answer
with a warm lantern chord and memorials with a single reverent chime. Every cue is short enough
to leave room for dialogue. There is no looping ambience competing with the match's music.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from sagaforge.synth import BELL, DARK, GLASS, PAD, level, mix, noise, thump, tone


def bell() -> np.ndarray:
    return level(mix(tone("D4", .95, tau=.32, partials=BELL), tone("A4", .8, tau=.27, partials=BELL)*.45,
                     (0.09, tone("E5", .7, tau=.22, partials=GLASS)*.22)), .58)


def anchor() -> np.ndarray:
    return level(mix(tone("D3", .9, attack=.05, tau=.28, partials=DARK)*.7,
                     (0.1, tone("A4", .75, attack=.04, tau=.23, partials=GLASS)),
                     (0.2, tone("D5", .65, attack=.02, tau=.2, partials=BELL)*.55),
                     noise(.45, 1200, 6500, attack=.07, tau=.12, seed=611)*.17), .55)


def gate() -> np.ndarray:
    return level(mix(noise(.6, 80, 1300, attack=.05, tau=.2, seed=612)*.55,
                     tone("D3", .65, attack=.05, tau=.2, partials=PAD)*.5,
                     (0.3, tone("A4", .65, attack=.03, tau=.2, partials=BELL))), .55)


def refuge() -> np.ndarray:
    return level(mix(*[(i*.09, tone(note, .7-i*.06, attack=.035, tau=.22, partials=PAD)*gain)
                      for i, (note, gain) in enumerate((("D4", .8), ("F#4", .6), ("A4", .55), ("D5", .35)))]), .4)


def memorial() -> np.ndarray:
    return level(mix(tone("A4", .95, attack=.015, tau=.3, partials=BELL)*.8,
                     tone("D4", .9, attack=.04, tau=.28, partials=PAD)*.35), .38)


def opened() -> np.ndarray:
    return level(mix(noise(.6, 120, 1400, attack=.08, tau=.16, seed=613)*.6,
                     (0.28, tone("D5", .68, attack=.02, tau=.22, partials=GLASS)*.8),
                     (0.4, tone("A5", .55, attack=.02, tau=.18, partials=BELL)*.5)), .52)


def ruined() -> np.ndarray:
    return level(mix(thump(115, 42, .65, tau=.17), noise(.75, 120, 3500, attack=.008, tau=.16, seed=614)*.5,
                     (0.16, tone("D3", .7, attack=.01, tau=.2, partials=BELL)*.35)), .62)


def cue(kind: str, state: str) -> str | None:
    """An event name for a state change; returning to dormancy makes no affirmative sound."""
    if state == "ruined":
        return "landmark_ruined"
    if state == "open":
        return "landmark_open"
    if state == "active":
        return f"landmark_{kind}"
    return None


SOUNDS: dict[str, Callable[[], np.ndarray]] = {
    "landmark_bell": bell, "landmark_anchor": anchor, "landmark_gate": gate, "landmark_refuge": refuge,
    "landmark_memorial": memorial, "landmark_open": opened, "landmark_ruined": ruined,
}
