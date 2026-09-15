"""Building collapses: the structure cracks, the mass comes down, the debris settles; one cue per material and take.

Timber and masonry each have their own generated pieces under ``assets/wreckage`` (see
:mod:`warband.pieces` and ``docs/warband-deaths.md``); the cue places the collapse on the crack
and lets the debris start before the collapse has died away.
"""

from __future__ import annotations

from functools import partial

import numpy as np

from sagaforge.synth import SAMPLE_RATE, level, mix
from warband import pieces
from warband.rules import BuildingType

FOLDER = "wreckage"
MATERIALS = ("wood", "stone")
STAGES = ("crack", "collapse", "debris")
#: Seconds from the crack to the mass coming down, and from the end of the collapse piece to the debris.
CRACK_TO_COLLAPSE = 0.3
COLLAPSE_TO_DEBRIS = -0.35
GAINS = {"crack": 0.7, "collapse": 0.9, "debris": 0.55}
PEAK = 0.8
#: What a building is made of once it stands; a site under construction is scaffolding, so wood.
BUILDING_MATERIALS = {
    BuildingType.TOWN_HALL: "stone", BuildingType.TOWER: "stone", BuildingType.BLACKSMITH: "stone", BuildingType.CHURCH: "stone",
    BuildingType.FARM: "wood", BuildingType.BARRACKS: "wood", BuildingType.LUMBER_MILL: "wood", BuildingType.STABLES: "wood",
    BuildingType.WORKSHOP: "wood",
}


def material(building: BuildingType, complete: bool = True) -> str:
    return BUILDING_MATERIALS[building] if complete else "wood"


def takes(material: str) -> int:
    """How many collapse cues a material has: one per committed crack."""
    return len(pieces.paths(FOLDER, material, "crack"))


def _piece(material: str, kind: str, take: int) -> np.ndarray:
    return pieces.take(FOLDER, material, kind, take, GAINS[kind])


def collapse(material: str, take: int) -> np.ndarray:
    """Crack *take*, the collapse on its heels, and the debris (rotated one take) settling under its tail."""
    crack = _piece(material, "crack", take)
    falling = _piece(material, "collapse", take)
    debris_at = CRACK_TO_COLLAPSE + len(falling) / SAMPLE_RATE + COLLAPSE_TO_DEBRIS
    return level(mix(crack, (CRACK_TO_COLLAPSE, falling), (max(CRACK_TO_COLLAPSE, debris_at), _piece(material, "debris", take + 1))), PEAK)


def cue(material: str) -> str:
    """The event name the scene plays when a building of *material* falls; the bank picks the take."""
    return f"{material}_collapse"


#: Cue name → how many takes the bank can choose from.
CUES = {cue(material): takes(material) for material in MATERIALS}
SOUNDS = {f"{cue(material)}_{take}": partial(collapse, material, take) for material in MATERIALS for take in range(takes(material))}
