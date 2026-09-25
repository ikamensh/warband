"""Every unit wears a painted sheet (WB-070), and the committed sheets carry nothing the cut brought in from beyond the
figure (WB-019).

A unit type a race fields, or a neutral creature, is painted or stands in ``textures.UNPAINTED_UNITS`` with the reason
and the date: procedural art is a debt carried on purpose.  ``docs/adding-a-unit.md`` ("Its art") is the procedure."""

import datetime

import numpy as np
import pytest
from sagaforge import restyle

from warband.art import monsters, textures
from warband.sim.races import RACES
from warband.sim.rules import CREATURES, Race, Resource, UnitType


def fielded():
    """Every unit subject a race fields: each unit type its roster names, a peasant also with each load."""
    for race in Race:
        for unit in RACES[race].units:
            for carrying in ((None,) if unit is not UnitType.PEASANT else (None, Resource.GOLD, Resource.LUMBER)):
                yield race, unit, carrying


def holds(name: str, keys: list[str]) -> bool:
    """Whether the committed sheet *name* exists and holds every one of *keys*: read from its layout, not its pixels."""
    stem = textures.RESTYLED / name
    if not (restyle.file(stem, "png").exists() and restyle.file(stem, "json").exists()):
        return False
    return set(keys) <= {cell.key for cell in restyle.Sheet.load(stem).cells}


def owed():
    """Every sheet the protocol asks for, as (unit type, sheet name, the cells it must hold): each fielded unit subject's
    and each creature's."""
    for race, unit, carrying in fielded():
        yield unit, textures.unit_sheet(race, unit, carrying), textures.unit_sheet_keys(race, unit, carrying)
    for creature in CREATURES:
        monster = monsters.Monster(creature.value)
        yield creature, monsters.monster_sheet(monster), monsters.monster_sheet_keys(monster)


def unpainted() -> list[tuple[UnitType, str]]:
    """The owed sheets not committed (or stale), exempt or not."""
    return [(unit, name) for unit, name, keys in owed() if not holds(name, keys)]


def unexempted() -> list[str]:
    return [name for unit, name in unpainted() if unit not in textures.UNPAINTED_UNITS]


def test_every_fielded_unit_and_every_creature_is_painted_or_exempted() -> None:
    """A new unit type comes with its sheets, or with a row in the exemption table saying why not and since when."""
    assert unexempted() == [], \
        "paint these (docs/adding-a-unit.md, 'Its art') or exempt their unit type in textures.UNPAINTED_UNITS with the reason and the date"


def test_every_exemption_is_needed_and_says_why_and_since_when() -> None:
    """An exemption for a unit type whose every sheet is painted is stale; each gives a reason and a date."""
    missing = {unit for unit, _name in unpainted()}
    for unit, (reason, since) in textures.UNPAINTED_UNITS.items():
        assert unit in missing, f"{unit.value} is painted: delete its exemption"
        assert reason.strip(), unit
        datetime.date.fromisoformat(since)


def test_a_unit_without_a_sheet_fails_the_protocol_until_it_is_exempted(tmp_path, monkeypatch) -> None:
    """The table is what lets an unpainted unit pass: with nothing painted, every subject is owed until its row is written."""
    monkeypatch.setattr(textures, "RESTYLED", tmp_path)
    assert {"human.cleric", "dwarf.peasant.lumber", "monster.golem"} <= set(unexempted())
    monkeypatch.setitem(textures.UNPAINTED_UNITS, UnitType.CLERIC, ("a test's", "2026-09-24"))
    assert "human.cleric" not in unexempted() and "human.footman" in unexempted()


def subjects():
    """Every painted subject, listed without loading a sheet: each race's units (the peasant also with each load)
    but those exempted from painting (:data:`~warband.art.textures.UNPAINTED_UNITS`), and its buildings in each look."""
    yield from ((race, unit, carrying) for race, unit, carrying in fielded() if unit not in textures.UNPAINTED_UNITS)
    for race in Race:
        for look in ("intact", "active", "damaged"):
            yield race, look, None


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
