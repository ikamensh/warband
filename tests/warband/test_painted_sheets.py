"""The committed painted sheets carry nothing the cut brought in from beyond the figure (WB-019)."""

import numpy as np
import pytest
from sagaforge import restyle

from warband.art import textures
from warband.sim.rules import PLAYABLE_UNITS, Race, Resource, UnitType


def subjects():
    """Every painted subject, listed without loading a sheet: each race's units (the peasant also with each load)
    and its buildings in each look."""
    for race in Race:
        for unit in PLAYABLE_UNITS:
            for carrying in ((None,) if unit is not UnitType.PEASANT else (None, Resource.GOLD, Resource.LUMBER)):
                yield race, unit, carrying
        for look in ("intact", "active", "damaged"):
            yield race, look, None


def test_the_orc_wolf_rider_has_no_lines_floating_above_it() -> None:
    """The frame the WB-004 scout review caught: thin guide lines along the top of the walk frames."""
    sheet, frames = textures.restyled_frames(Race.ORC, UnitType.SCOUT, None)
    for facing in range(textures.FACINGS):
        for frame in ("stand", *textures.WALK_FRAMES, *textures.ATTACK_FRAMES):
            assert restyle.strays(frames[textures.unit_key(UnitType.SCOUT, 0, facing, frame, None, Race.ORC)]) == [], (facing, frame)


@pytest.mark.slow
@pytest.mark.parametrize("race, subject, carrying", list(subjects()), ids=lambda v: getattr(v, "value", str(v)))
def test_every_painted_sheet_is_free_of_edge_strays(race, subject, carrying) -> None:
    """Every race's every unit and building look is painted, and its frames carry nothing from beyond the figure.
    Each sheet is loaded and examined frame by frame, seven seconds for them all: the slow tier, which a change to
    the art runs before it is pushed. The wolf rider's check stays in the fast tier."""
    painted = textures.restyled_buildings(race, subject) if isinstance(subject, str) else textures.restyled_frames(race, subject, carrying)
    assert painted is not None, "this subject has no painted sheet, or a stale one"
    sheet, frames = painted
    stray = {key: restyle.strays(frame) for key, frame in frames.items()}
    assert {key: boxes for key, boxes in stray.items() if boxes} == {}
    field = {key: int(restyle.residue(np.asarray(frame)[..., 3]).sum()) for key, frame in frames.items()}
    assert {key: count for key, count in field.items() if count} == {}, "the key's faint field far from the figure"
