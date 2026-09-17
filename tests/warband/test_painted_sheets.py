"""The committed painted sheets carry nothing the cut brought in from beyond the figure (WB-019)."""

import pytest
from sagaforge import restyle

from warband import textures
from warband.rules import Race, Resource, UnitType


def subjects():
    for race in Race:
        for unit in UnitType:
            for carrying in ((None,) if unit is not UnitType.PEASANT else (None, Resource.GOLD, Resource.LUMBER)):
                if textures.restyled_frames(race, unit, carrying) is not None:
                    yield race, unit, carrying
        for look in ("intact", "active", "damaged"):
            if textures.restyled_buildings(race, look) is not None:
                yield race, look, None


def test_the_orc_wolf_rider_has_no_lines_floating_above_it() -> None:
    """The frame the WB-004 scout review caught: thin guide lines along the top of the walk frames."""
    sheet, frames = textures.restyled_frames(Race.ORC, UnitType.SCOUT, None)
    for facing in range(textures.FACINGS):
        for frame in ("stand", *textures.WALK_FRAMES, *textures.ATTACK_FRAMES):
            assert restyle.strays(frames[textures.unit_key(UnitType.SCOUT, 0, facing, frame, None, Race.ORC)]) == [], (facing, frame)


@pytest.mark.parametrize("race, subject, carrying", list(subjects()), ids=lambda v: getattr(v, "value", str(v)))
def test_every_painted_sheet_is_free_of_edge_strays(race, subject, carrying) -> None:
    painted = textures.restyled_buildings(race, subject) if isinstance(subject, str) else textures.restyled_frames(race, subject, carrying)
    sheet, frames = painted
    stray = {key: restyle.strays(frame) for key, frame in frames.items()}
    assert {key: boxes for key, boxes in stray.items() if boxes} == {}
