"""Combat impacts: every weapon on every material, three takes each, from generated pieces.

The pieces under ``assets/impacts`` (see :mod:`warband.pieces`; one prompt per weapon, material
and take, in ``tools/pieces.py``) are the whole sound: a blow lands the moment the cue starts, so
the scene can play it on the hit and it sits on the animation.  The bank rotates takes and adds
a little pitch variation so repeated blows differ.
"""

from __future__ import annotations

from functools import partial

import numpy as np

from warband import pieces

FOLDER = "impacts"
WEAPONS = ("sword", "axe", "spear", "lance", "arrow", "stone", "hammer")
MATERIALS = ("flesh", "armor", "wood", "stone")
VARIANTS = 3
PEAK = 0.75


def strike(weapon: str, material: str, take: int) -> np.ndarray:
    """Take *take* of *weapon* hitting *material*, levelled for the bank; the pieces are already cut to the hit."""
    if take >= VARIANTS:
        raise ValueError(f"{weapon} on {material} has {VARIANTS} takes, not {take + 1}")
    return pieces.take(FOLDER, weapon, material, take, PEAK)


SOUNDS = {
    f"{weapon}_{material}_{take}": partial(strike, weapon, material, take)
    for weapon in WEAPONS for material in MATERIALS for take in range(VARIANTS)
}
