"""Unit deaths: one cue per sound family and take, placed from the family's generated pieces.

A soldier cries out and his weapon, body and gear land; a catapult splinters and crashes; a wolf yelps and
falls.  Each family's stages and gaps are :data:`warband.audio.bodies.FAMILIES`'; the pieces are generated
recordings committed under ``assets/deaths`` (see :mod:`warband.audio.pieces` and ``docs/warband-pieces.md``).
The bank's generator only places and scales them, so a cue is deterministic for a given set of pieces.  A body
whose own blow can end it (a sapper's keg) has a second cue for that end, its ``spent`` stages, placed the same way.
"""

from __future__ import annotations

from functools import partial

import numpy as np

from sagaforge.synth import SAMPLE_RATE, level, mix
from warband.audio import pieces
from warband.audio.bodies import FAMILIES, Stage

FOLDER = "deaths"
PEAK = 0.72


def stages(family: str, *, spent: bool = False) -> tuple[Stage, ...]:
    """The stages of *family*'s death, or of its spent end."""
    return FAMILIES[family].spent if spent else FAMILIES[family].death


def takes(family: str, *, spent: bool = False) -> int:
    """How many cues *family*'s death (or spent end) has: one per committed piece of its first stage."""
    return len(pieces.paths(FOLDER, family, stages(family, spent=spent)[0].kind))


def death(family: str, take: int, *, spent: bool = False) -> np.ndarray:
    """The family's stages in order, each placed from the one before, the mix levelled to :data:`PEAK`."""
    layers, start, end = [], 0.0, 0.0
    for stage in stages(family, spent=spent):
        clip = pieces.take(FOLDER, family, stage.kind, take + stage.rotate, stage.gain)
        if layers:  # from the stage before: its start, or its end
            start = max(start, (end if stage.after_end else start) + stage.gap)
        end = start + len(clip) / SAMPLE_RATE
        layers.append((start, clip))
    return level(mix(*layers), PEAK)


def cue(family: str, *, spent: bool = False) -> str:
    """The event name the scene plays when a body of *family* dies, or is spent; the bank picks the take."""
    return f"{family}_spent" if spent else f"{family}_death"


#: Every cue's family and end: each family's death, and the spent end of those that have one.
ENDS = [(family, spent) for family, body in FAMILIES.items() for spent in (False, True) if body.spent or not spent]
#: Cue name → how many takes the bank can choose from.
CUES = {cue(family, spent=spent): takes(family, spent=spent) for family, spent in ENDS}
#: The explosions (a spent end, ``Family.spent``): heard as a building coming down is, whatever else is sounding.
LOUD = frozenset(cue(family, spent=True) for family, spent in ENDS if spent)
SOUNDS = {f"{cue(family, spent=spent)}_{take}": partial(death, family, take, spent=spent)
          for family, spent in ENDS for take in range(takes(family, spent=spent))}
