"""Unit deaths: one cue per sound family and take, placed from the family's generated pieces.

A soldier cries out and his weapon, body and gear land; a catapult splinters and crashes; a wolf yelps and
falls.  Each family's stages and gaps are :data:`warband.audio.bodies.FAMILIES`'; the pieces are generated
recordings committed under ``assets/deaths`` (see :mod:`warband.audio.pieces` and ``docs/warband-pieces.md``).
The bank's generator only places and scales them, so a cue is deterministic for a given set of pieces.
"""

from __future__ import annotations

from functools import partial

import numpy as np

from sagaforge.synth import SAMPLE_RATE, level, mix
from warband.audio import pieces
from warband.audio.bodies import FAMILIES

FOLDER = "deaths"
PEAK = 0.72


def takes(family: str) -> int:
    """How many death cues *family* has: one per committed piece of its first stage."""
    return len(pieces.paths(FOLDER, family, FAMILIES[family].death[0].kind))


def death(family: str, take: int) -> np.ndarray:
    """The family's stages in order, each placed from the one before, the mix levelled to :data:`PEAK`."""
    layers, start, end = [], 0.0, 0.0
    for stage in FAMILIES[family].death:
        clip = pieces.take(FOLDER, family, stage.kind, take + stage.rotate, stage.gain)
        if layers:  # from the stage before: its start, or its end
            start = max(start, (end if stage.after_end else start) + stage.gap)
        end = start + len(clip) / SAMPLE_RATE
        layers.append((start, clip))
    return level(mix(*layers), PEAK)


def cue(family: str) -> str:
    """The event name the scene plays when a body of *family* dies; the bank picks the take."""
    return f"{family}_death"


#: Cue name → how many takes the bank can choose from.
CUES = {cue(family): takes(family) for family in FAMILIES}
SOUNDS = {f"{cue(family)}_{take}": partial(death, family, take) for family in FAMILIES for take in range(takes(family))}
