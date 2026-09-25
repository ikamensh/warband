"""Every unit and every building wears a painted sheet (WB-070), and the committed sheets carry nothing the cut brought
in from beyond the figure (WB-019).

A unit type a race fields, a spell summons, or a neutral creature, is painted or stands in ``textures.UNPAINTED_UNITS``
with the reason and the date, and a building in ``textures.UNPAINTED``: procedural art is a debt carried on purpose.
``docs/adding-a-unit.md`` ("Its art") is the procedure for a unit, ``docs/warband-art.md`` ("A new building") for a
building."""

import datetime

import numpy as np
import pytest
from sagaforge import restyle

from warband.art import monsters, textures
from warband.sim.races import RACES
from warband.sim.rules import BUILT, CREATURES, SUMMONED, BuildingType, Race, Resource, UnitType


def fielded():
    """Every unit subject a race fields: each unit type its roster names, a peasant also with each load; its table
    holds the other races' own units too (WB-068), which it never fields."""
    for race in Race:
        for unit in filter(RACES[race].unit_allowed, RACES[race].units):
            for carrying in ((None,) if unit is not UnitType.PEASANT else (None, Resource.GOLD, Resource.LUMBER)):
                yield race, unit, carrying


def holds(name: str, keys: list[str]) -> bool:
    """Whether the committed sheet *name* exists and holds every one of *keys*: read from its layout, not its pixels."""
    stem = textures.RESTYLED / name
    if not (restyle.file(stem, "png").exists() and restyle.file(stem, "json").exists()):
        return False
    return set(keys) <= {cell.key for cell in restyle.Sheet.load(stem).cells}


def owed():
    """Every sheet the protocol asks for, as (unit type, sheet name, the cells it must hold): each fielded unit subject's,
    each summoned unit's in every caster's race (the art looks a unit's sheet up by its side's race) and each creature's."""
    for race, unit, carrying in fielded():
        yield unit, textures.unit_sheet(race, unit, carrying), textures.unit_sheet_keys(race, unit, carrying)
    for race in Race:
        for unit in SUMMONED:
            yield unit, textures.unit_sheet(race, unit), textures.unit_sheet_keys(race, unit)
    for creature in CREATURES:
        monster = monsters.Monster(creature.value)
        yield creature, monsters.monster_sheet(monster), monsters.monster_sheet_keys(monster)


def unpainted() -> list[tuple[UnitType, str]]:
    """The owed sheets not committed (or stale), exempt or not."""
    return [(unit, name) for unit, name, keys in owed() if not holds(name, keys)]


def unexempted() -> list[str]:
    return [name for unit, name in unpainted() if unit not in textures.UNPAINTED_UNITS]


def test_every_fielded_summoned_or_wild_unit_is_painted_or_exempted() -> None:
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


def test_a_summoned_unit_is_painted_once_for_every_caster() -> None:
    """A summoned unit is no race's and looks the same whoever casts it: its sheet and its images name no race, so one
    painting serves every caster (and its image registers once per player, not once per race and player)."""
    for unit in SUMMONED:
        assert {textures.unit_sheet(race, unit) for race in Race} == {unit.value}
        assert {textures.unit_key(unit, 1, 2, "stand", None, race) for race in Race} == {f"unit.{unit.value}.1.2.stand"}
    assert textures.unit_sheet(Race.ORC, UnitType.FOOTMAN) == "orc.footman", "a race's own soldiers keep their race's sheets"


def unpainted_buildings() -> list[tuple[BuildingType, str]]:
    """Each building a race's sheet in some look lacks, exempt or not, with that sheet's name."""
    return [(bt, f"{race.value}.buildings.{look}") for race in Race for look in textures.BUILDING_LOOKS for bt in BUILT
            if not holds(f"{race.value}.buildings.{look}", [textures.building_key(bt, 0, race, look)])]


def test_every_building_is_painted_in_every_look_or_exempted() -> None:
    """A new building comes with its cell in every race's sheet of every look, or with a row saying why not and since when."""
    assert [f"{bt.value} in {name}" for bt, name in unpainted_buildings() if bt not in textures.UNPAINTED] == [], \
        "paint these (tools/restyle.py --buildings --add) or exempt them in textures.UNPAINTED with the reason and the date"


def test_every_building_exemption_is_needed_and_says_why_and_since_when() -> None:
    missing = {bt for bt, _name in unpainted_buildings()}
    for bt, (reason, since) in textures.UNPAINTED.items():
        assert bt in missing, f"{bt.value} is painted: delete its exemption"
        assert reason.strip(), bt
        datetime.date.fromisoformat(since)


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
