"""A body's presence: the sound a machine answers its player's order with, and a creature makes as its camp rouses.

A family with a ``presence`` (:data:`warband.audio.bodies.FAMILIES`) has generated pieces under
``assets/presence``, ``<family>_<kind>_<take>.wav`` (``tools/pieces.py``); the cue is the piece itself, as an
impact is, and the bank rotates the takes.  The soldiers of a race have none: the race's own order cues answer them
(:mod:`warband.audio.voices`).
"""

from __future__ import annotations

from functools import partial

import numpy as np

from warband.audio import pieces
from warband.audio.bodies import FAMILIES

FOLDER = "presence"
PEAK = 0.6
#: The families heard alive, and the kind of piece each answers with.
KINDS = {name: family.presence for name, family in FAMILIES.items() if family.presence is not None}


def takes(family: str) -> int:
    return len(pieces.paths(FOLDER, family, KINDS[family]))


def presence(family: str, take: int) -> np.ndarray:
    return pieces.take(FOLDER, family, KINDS[family], take, PEAK)


def cue(family: str) -> str | None:
    """The event name the scene plays when a body of *family* makes itself heard; ``None`` when it has no presence."""
    return f"{family}_presence" if family in KINDS else None


#: Cue name → how many takes the bank can choose from.
CUES = {f"{family}_presence": takes(family) for family in KINDS}
SOUNDS = {f"{family}_presence_{take}": partial(presence, family, take) for family in KINDS for take in range(takes(family))}
