"""The balance tables in plain TOML, generated into the simulation.

    uv run python tools/balance_tables.py          # rewrite the GENERATED regions of warband/sim/rules.py and races.py
    uv run python tools/balance_tables.py --check  # fail if a region differs (tests/warband/test_balance_tables.py runs this)

The numbers a tuner edits live in ``warband/constants/units.toml``,
``neutrals.toml``, ``buildings.toml``, ``upgrades.toml``, ``races.toml``,
``economy.toml``, ``combat.toml`` and ``behavior.toml``; this tool rewrites
the matching Python tables from them.  The simulation itself keeps running
plain Python literals: the online contract (``tools/ci_compatibility.py``)
hashes the simulation's sources and forbids file-backed rules there, so the
TOML never loads at runtime.  Every generated region carries the same fields,
explicitly and in dataclass order, except a building's ``mine`` which is
omitted when there is none.
"""

from __future__ import annotations

import argparse
import difflib
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIM = ROOT / "warband" / "sim"
CONSTANTS = ROOT / "warband" / "constants"
UNITS_TOML = CONSTANTS / "units.toml"
BUILDINGS_TOML = CONSTANTS / "buildings.toml"
UPGRADES_TOML = CONSTANTS / "upgrades.toml"
RACES_TOML = CONSTANTS / "races.toml"
NEUTRALS_TOML = CONSTANTS / "neutrals.toml"
ECONOMY_TOML = CONSTANTS / "economy.toml"
COMBAT_TOML = CONSTANTS / "combat.toml"
BEHAVIOR_TOML = CONSTANTS / "behavior.toml"

RULES_PY = SIM / "rules.py"
RACES_PY = SIM / "races.py"
MODEL_PY = SIM / "model.py"

PLAYABLE = ("peasant", "footman", "archer", "scout", "knight", "catapult", "cleric")
WILDS = ("wolf", "spider", "troll", "golem")
BUILDINGS = ("town_hall", "farm", "barracks", "tower", "lumber_mill", "blacksmith", "stables", "workshop", "church",
             "gold_mine", "gold_seam", "lair")
DEPOSITS = ("gold_mine", "gold_seam")
#: What a player builds: everything the wilds do not own (rules.BUILT walks the same set).
BUILT = tuple(b for b in BUILDINGS if b not in DEPOSITS and b != "lair")
UPGRADES = ("keep", "blades_1", "blades_2", "blades_3", "armor_1", "armor_2", "arrows_1", "arrows_2", "arrows_3", "siege",
            "marksmanship", "horses", "blessing", "bloodlust", "plunder", "longbows", "regrowth", "deep_mining",
            "blasting_powder")
RACES = ("human", "orc", "elf", "dwarf")
ATTACKS = ("normal", "piercing", "siege")
ARMOR_CLASSES = ("unarmoured", "light", "heavy", "fortified")
RESOURCES = ("gold", "lumber")


class BalanceError(Exception):
    """A TOML table this tool cannot build the simulation from.  The message names the file, section and key."""


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BalanceError(f"{path.name}: malformed TOML: {exc}") from exc


def _at(path: Path, section: str, key: str | None = None) -> str:
    where = f"{path.name} [{section}]"
    return f"{where}.{key}" if key is not None else where


def _reject_bool(value, where: str, what: str) -> None:
    if isinstance(value, bool):
        raise BalanceError(f"{where}: {what} must not be a boolean")


def _int(entry: dict, key: str, where: str, default: int | None = None) -> int:
    if key not in entry:
        if default is not None:
            return default
        raise BalanceError(f"{where}: missing {key}")
    value = entry[key]
    _reject_bool(value, where, key)
    if not isinstance(value, int):
        raise BalanceError(f"{where}.{key}: expected an int, got {value!r}")
    return value


def _float(entry: dict, key: str, where: str, default: float | None = None) -> float:
    if key not in entry:
        if default is not None:
            return default
        raise BalanceError(f"{where}: missing {key}")
    value = entry[key]
    _reject_bool(value, where, key)
    if not isinstance(value, (int, float)):
        raise BalanceError(f"{where}.{key}: expected a number, got {value!r}")
    return float(value)


def _str(entry: dict, key: str, where: str, default: str | None = None) -> str:
    if key not in entry:
        if default is not None:
            return default
        raise BalanceError(f"{where}: missing {key}")
    value = entry[key]
    if not isinstance(value, str):
        raise BalanceError(f"{where}.{key}: expected a string, got {value!r}")
    return value


def _bool(entry: dict, key: str, where: str, default: bool | None = None) -> bool:
    if key not in entry:
        if default is not None:
            return default
        raise BalanceError(f"{where}: missing {key}")
    value = entry[key]
    if not isinstance(value, bool):
        raise BalanceError(f"{where}.{key}: expected true/false, got {value!r}")
    return value


def _enum(entry: dict, key: str, where: str, choices: tuple[str, ...], default: str | None = None) -> str:
    value = _str(entry, key, where, default)
    if value not in choices:
        raise BalanceError(f"{where}.{key}: expected one of {', '.join(choices)}, got {value!r}")
    return value


def _names(entry: dict, key: str, where: str, choices: tuple[str, ...]) -> list[str]:
    if key not in entry:
        return []
    value = entry[key]
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise BalanceError(f"{where}.{key}: expected a list of names, got {value!r}")
    for v in value:
        if v not in choices:
            raise BalanceError(f"{where}.{key}: expected one of {', '.join(choices)}, got {v!r}")
    return list(value)


def _no_extra(entry: dict, known: set[str], where: str) -> None:
    for key in entry:
        if key not in known:
            raise BalanceError(f"{where}: unexpected {key}")


def _check_sections(doc: dict, path: Path, known: tuple[str, ...], what: str) -> None:
    for section in doc:
        if section not in known:
            raise BalanceError(f"{path.name}: unexpected {what} [{section}]; known: {', '.join(known)}")


# -- Normalized tables ---------------------------------------------------------
#
# Plain values keyed by the enum value each section is named for: "melee" is
# resolved to the shared reach, missing keys to the dataclass defaults, so the
# emitter and the drift check share one reading of the TOML.
#
# Scalars land in one flat table keyed by CONSTANT name, whatever file and
# section they come from; a region is just the CONSTANTs it emits, in file
# order.  What stays in code (SIM_DT, the order bounds, the pathfinder's
# budgets, the seats) is not tunable balance and never enters these schemas.

UNIT_KEYS = {"name", "gold", "lumber", "hp", "damage", "armor", "range", "cooldown", "speed", "sight", "build_time",
             "trained_at", "hotkey", "summary", "radius", "heal", "splash", "attack", "armor_class", "formation",
             "mounted", "windup", "turn_deg", "min_range", "regen"}
BUILDING_KEYS = {"name", "gold", "lumber", "hp", "armor", "size", "build_time", "sight", "supply", "hotkey", "summary",
                 "trains", "researches", "requires", "deposits", "damage", "range", "cooldown", "mine_trip", "mine_slots",
                 "mine_endless"}
UPGRADE_KEYS = {"name", "gold", "lumber", "time", "hotkey", "card", "summary", "requires", "race"}
UNIT_TWEAK_KEYS = {"name", "summary", "hp_mult", "damage_mult", "armor_add", "range_add", "speed_add", "sight_add",
                   "build_time_mult", "formation"}
BUILDING_TWEAK_KEYS = {"name", "card", "summary", "hp_mult", "armor_add"}
UPGRADE_TWEAK_KEYS = {"name", "card"}

#: Scalar schemas: section -> {toml key: (CONSTANT, int|float)}.  Sections are
#: required whole: a missing or misspelled key fails, never silently defaults.
ECONOMY_SCHEMA = {
    "work": {"mine_time": ("MINE_TIME", float), "lumber_per_trip": ("LUMBER_PER_TRIP", int),
             "chop_time": ("CHOP_TIME", float)},
    "setup": {"mine_gold": ("MINE_GOLD", int), "expansion_gold": ("EXPANSION_GOLD", int),
              "starting_gold": ("STARTING_GOLD", int), "starting_lumber": ("STARTING_LUMBER", int)},
    "repair": {"rate": ("REPAIR_RATE", float), "chunk": ("REPAIR_CHUNK", int), "cost_share": ("REPAIR_COST", float)},
    "salvage": {"rate": ("SALVAGE_RATE", float), "held_rate": ("SALVAGE_HELD_RATE", float),
                "chunk": ("SALVAGE_CHUNK", int), "share": ("SALVAGE_SHARE", float)},
}
EFFECTS_SCHEMA = {"blades_bonus": ("BLADES_BONUS", int), "master_weapon_bonus": ("MASTER_WEAPON_BONUS", int),
                  "armor_bonus": ("ARMOR_BONUS", int), "arrows_bonus": ("ARROWS_BONUS", int),
                  "horses_bonus": ("HORSES_BONUS", float), "siege_range_bonus": ("SIEGE_RANGE_BONUS", float),
                  "siege_damage_bonus": ("SIEGE_DAMAGE_BONUS", float), "blessing_bonus": ("BLESSING_BONUS", float),
                  "frenzy_bonus": ("FRENZY_BONUS", float), "bloodlust_bonus": ("BLOODLUST_BONUS", float),
                  "plunder_share": ("PLUNDER_SHARE", float), "longbows_bonus": ("LONGBOWS_BONUS", float),
                  "regrowth_seconds": ("REGROWTH_SECONDS", float), "deep_mining_trip": ("DEEP_MINING_TRIP", int),
                  "blasting_powder_bonus": ("BLASTING_POWDER_BONUS", float)}
COMBAT_SCALARS = {"melee_range": ("MELEE", float), "arrow_speed": ("ARROW_SPEED", float),
                  "stone_speed": ("STONE_SPEED", float), "stone_min_flight": ("STONE_MIN_FLIGHT", float),
                  "windup_slack": ("WINDUP_SLACK", float), "hit_variance": ("HIT_VARIANCE", float),
                  "splash_fraction": ("SPLASH_FRACTION", float), "direct_hit": ("DIRECT_HIT", float)}
SIEGE_SCALARS = {"step": ("SIEGE_STEP", float), "building_worth": ("SIEGE_BUILDING_WORTH", float)}
FRIENDLY_SCALARS = {"margin": ("FRIENDLY_MARGIN", float), "worth": ("FRIENDLY_WORTH", float)}
BEHAVIOR_SCHEMA = {
    "formation": {"armor": ("FORMATION_ARMOR", int), "spacing": ("FORMATION_SPACING", float),
                  "width": ("FORMATION_WIDTH", int), "march": ("FORMATION_MARCH", float),
                  "slack": ("FORMATION_SLACK", float), "hold": ("FORMATION_HOLD", float),
                  "lookahead": ("FORMATION_LOOKAHEAD", float)},
    "camps": {"watch": ("CAMP_WATCH", float), "hold": ("CAMP_HOLD", float), "calm": ("CAMP_CALM", float),
              "regen": ("CAMP_REGEN", float), "respawn": ("CAMP_RESPAWN", float), "post": ("CAMP_POST", float),
              "regen_calm": ("REGEN_CALM", float)},
    "movement": {"max_push": ("MAX_PUSH", float), "spacing": ("SPACING", float),
                 "spacing_weight": ("SPACING_WEIGHT", float), "ease_space": ("EASE_SPACE", float),
                 "ease_every": ("EASE_EVERY", int), "ease_chance": ("EASE_CHANCE", float),
                 "ease_step": ("EASE_STEP", float), "ease_step_variance": ("EASE_STEP_VARIANCE", float),
                 "ease_jitter": ("EASE_JITTER", float), "ease_gain": ("EASE_GAIN", float)},
    "pursuit": {"leash": ("LEASH", float)},
}

#: Generated scalar regions: region -> the CONSTANTs it emits, in file order.
#: The drift test reads this same table, so regions and checks cannot drift apart.
SCALAR_REGIONS = {
    "melee": ("MELEE",),
    "mine_time": ("MINE_TIME",),
    "lumber": ("LUMBER_PER_TRIP", "CHOP_TIME"),
    "repair": ("REPAIR_RATE", "REPAIR_CHUNK", "REPAIR_COST"),
    "salvage": ("SALVAGE_RATE", "SALVAGE_HELD_RATE", "SALVAGE_CHUNK", "SALVAGE_SHARE"),
    "setup": ("MINE_GOLD", "EXPANSION_GOLD", "STARTING_GOLD", "STARTING_LUMBER"),
    "upgrade_effects": ("BLADES_BONUS", "MASTER_WEAPON_BONUS", "ARMOR_BONUS", "ARROWS_BONUS", "HORSES_BONUS",
                        "SIEGE_RANGE_BONUS", "SIEGE_DAMAGE_BONUS", "BLESSING_BONUS", "FRENZY_BONUS",
                        "BLOODLUST_BONUS", "PLUNDER_SHARE", "LONGBOWS_BONUS", "REGROWTH_SECONDS",
                        "DEEP_MINING_TRIP", "BLASTING_POWDER_BONUS"),
    "combat": ("SPLASH_FRACTION", "DIRECT_HIT", "WINDUP_SLACK", "ARROW_SPEED", "STONE_SPEED", "STONE_MIN_FLIGHT",
               "HIT_VARIANCE"),
    "friendly_fire": ("FRIENDLY_MARGIN", "FRIENDLY_WORTH"),
    "formation": ("FORMATION_ARMOR", "FORMATION_SPACING", "FORMATION_WIDTH", "FORMATION_MARCH", "FORMATION_SLACK",
                  "FORMATION_HOLD", "FORMATION_LOOKAHEAD"),
    "regen_calm": ("REGEN_CALM",),
    "camps": ("CAMP_WATCH", "CAMP_HOLD", "CAMP_CALM", "CAMP_REGEN", "CAMP_RESPAWN", "CAMP_POST"),
    "pursuit": ("LEASH",),
    "movement": ("MAX_PUSH", "SPACING", "SPACING_WEIGHT", "EASE_SPACE", "EASE_EVERY", "EASE_CHANCE", "EASE_STEP",
                 "EASE_STEP_VARIANCE", "EASE_JITTER", "EASE_GAIN"),
}
#: Where a scalar region's CONSTANTs live: rules, except the crowd's in model.
SCALAR_MODULE = {"movement": "model"}


@dataclass
class Tables:
    units: dict[str, dict] = field(default_factory=dict)  # playable roles, in card order
    wilds: dict[str, dict] = field(default_factory=dict)  # neutral creatures
    buildings: dict[str, dict] = field(default_factory=dict)
    upgrades: dict[str, dict] = field(default_factory=dict)
    races: dict[str, dict] = field(default_factory=dict)
    scalars: dict[str, int | float] = field(default_factory=dict)  # CONSTANT -> value, from every TOML
    damage_bonus: list[dict] = field(default_factory=list)  # {attack, armor, factor}, in listed order
    siege_worth: dict[str, float] = field(default_factory=dict)  # unit value -> worth


def _unit(entry: dict, where: str) -> dict:
    _no_extra(entry, UNIT_KEYS, where)
    ranged = entry.get("range")
    if isinstance(ranged, str):
        if ranged != "melee":
            raise BalanceError(f"{where}.range: expected a distance in tiles or \"melee\", got {ranged!r}")
        reach: float | str = "melee"
    else:
        reach = _float(entry, "range", where)
    return {
        "name": _str(entry, "name", where),
        "gold": _int(entry, "gold", where, 0),
        "lumber": _int(entry, "lumber", where, 0),
        "hp": _int(entry, "hp", where),
        "damage": _int(entry, "damage", where),
        "armor": _int(entry, "armor", where),
        "range": reach,
        "cooldown": _float(entry, "cooldown", where),
        "speed": _float(entry, "speed", where),
        "sight": _int(entry, "sight", where),
        "build_time": _float(entry, "build_time", where),
        "trained_at": _enum(entry, "trained_at", where, BUILDINGS + ("lair",)),
        "hotkey": _str(entry, "hotkey", where),
        "summary": _str(entry, "summary", where),
        "radius": _float(entry, "radius", where),
        "heal": _int(entry, "heal", where, 0),
        "splash": _float(entry, "splash", where, 0.0),
        "attack": _enum(entry, "attack", where, ATTACKS, "normal"),
        "armor_class": _enum(entry, "armor_class", where, ARMOR_CLASSES, "light"),
        "formation": _bool(entry, "formation", where, False),
        "mounted": _bool(entry, "mounted", where, False),
        "windup": _float(entry, "windup", where),
        "turn_deg": _int(entry, "turn_deg", where, 360),
        "min_range": _float(entry, "min_range", where, 0.0),
        "regen": _float(entry, "regen", where, 0.0),
    }


def _building(entry: dict, where: str, section: str) -> dict:
    _no_extra(entry, BUILDING_KEYS, where)
    is_deposit = section in DEPOSITS
    for key in ("mine_trip", "mine_slots", "mine_endless"):
        if not is_deposit and key in entry:
            raise BalanceError(f"{where}: {key} belongs on the deposits ({', '.join(DEPOSITS)}) alone")
    requires = entry.get("requires")
    if requires is not None and (not isinstance(requires, str) or requires not in BUILDINGS):
        raise BalanceError(f"{where}.requires: expected a building, got {requires!r}")
    return {
        "name": _str(entry, "name", where),
        "gold": _int(entry, "gold", where, 0),
        "lumber": _int(entry, "lumber", where, 0),
        "hp": _int(entry, "hp", where),
        "armor": _int(entry, "armor", where),
        "size": _int(entry, "size", where),
        "build_time": _float(entry, "build_time", where),
        "sight": _int(entry, "sight", where),
        "supply": _int(entry, "supply", where),
        "hotkey": _str(entry, "hotkey", where),
        "summary": _str(entry, "summary", where),
        "trains": _names(entry, "trains", where, PLAYABLE),
        "researches": _names(entry, "researches", where, UPGRADES),
        "requires": requires,
        "deposits": _names(entry, "deposits", where, RESOURCES),
        "damage": _int(entry, "damage", where, 0),
        "range": _float(entry, "range", where, 0.0),
        "cooldown": _float(entry, "cooldown", where, 1.0),
        "mine_trip": _int(entry, "mine_trip", where, 0) if is_deposit else 0,
        "mine_slots": _int(entry, "mine_slots", where, 0) if is_deposit else 0,
        "mine_endless": _bool(entry, "mine_endless", where, False) if is_deposit else False,
    }


def _upgrade(entry: dict, where: str) -> dict:
    _no_extra(entry, UPGRADE_KEYS, where)
    race = entry.get("race")
    if race is not None and (not isinstance(race, str) or race not in RACES):
        raise BalanceError(f"{where}.race: expected a race, got {race!r}")
    requires = entry.get("requires", [])
    if not isinstance(requires, list) or any(not isinstance(v, str) or v not in UPGRADES for v in requires):
        raise BalanceError(f"{where}.requires: expected upgrade names, got {requires!r}")
    return {
        "name": _str(entry, "name", where),
        "gold": _int(entry, "gold", where, 0),
        "lumber": _int(entry, "lumber", where, 0),
        "time": _float(entry, "time", where),
        "hotkey": _str(entry, "hotkey", where),
        "card": _str(entry, "card", where),
        "summary": _str(entry, "summary", where),
        "requires": list(requires),
        "race": race,
    }


def _unit_tweak(entry: dict, where: str) -> dict:
    _no_extra(entry, UNIT_TWEAK_KEYS, where)
    return {
        "name": _str(entry, "name", where),
        "summary": _str(entry, "summary", where),
        "hp_mult": _float(entry, "hp_mult", where, 1.0),
        "damage_mult": _float(entry, "damage_mult", where, 1.0),
        "armor_add": _int(entry, "armor_add", where, 0),
        "range_add": _float(entry, "range_add", where, 0.0),
        "speed_add": _float(entry, "speed_add", where, 0.0),
        "sight_add": _int(entry, "sight_add", where, 0),
        "build_time_mult": _float(entry, "build_time_mult", where, 1.0),
        "formation": _bool(entry, "formation", where, True),
    }


def _building_tweak(entry: dict, where: str) -> dict:
    _no_extra(entry, BUILDING_TWEAK_KEYS, where)
    return {
        "name": _str(entry, "name", where),
        "card": _str(entry, "card", where),
        "summary": _str(entry, "summary", where),
        "hp_mult": _float(entry, "hp_mult", where, 1.0),
        "armor_add": _int(entry, "armor_add", where, 0),
    }


def _upgrade_tweak(entry: dict, where: str) -> dict:
    _no_extra(entry, UPGRADE_TWEAK_KEYS, where)
    return {"name": _str(entry, "name", where), "card": _str(entry, "card", where)}


def _schema_section(doc: dict, path: Path, section: str, schema: dict[str, tuple[str, type]], scalars: dict) -> None:
    """File [section]'s numbers into *scalars* by CONSTANT name; a missing or misspelled key fails."""
    where = _at(path, section)
    entry = doc.get(section)
    if not isinstance(entry, dict):
        raise BalanceError(f"{path.name}: missing [{section}]")
    _no_extra(entry, set(schema), where)
    for key, (const, kind) in schema.items():
        scalars[const] = _int(entry, key, where) if kind is int else _float(entry, key, where)


def _combat(doc: dict, tables: Tables) -> None:
    where = COMBAT_TOML.name
    _no_extra(doc, set(COMBAT_SCALARS) | {"damage_bonus", "siege", "friendly_fire"}, where)
    for key in COMBAT_SCALARS:
        if key not in doc:
            raise BalanceError(f"{where}: missing {key}")
    for key, (const, kind) in COMBAT_SCALARS.items():
        tables.scalars[const] = _int(doc, key, where) if kind is int else _float(doc, key, where)
    bonuses = doc.get("damage_bonus")
    if not isinstance(bonuses, list) or not bonuses:
        raise BalanceError(f"{where}: [[damage_bonus]] needs at least one pairing")
    for bonus in bonuses:
        if not isinstance(bonus, dict):
            raise BalanceError(f"{where}: a damage bonus must be a table, got {bonus!r}")
        _no_extra(bonus, {"attack", "armor", "factor"}, where)
        tables.damage_bonus.append({
            "attack": _enum(bonus, "attack", where, ATTACKS),
            "armor": _enum(bonus, "armor", where, ARMOR_CLASSES),
            "factor": _float(bonus, "factor", where),
        })
    siege = doc.get("siege")
    if not isinstance(siege, dict):
        raise BalanceError(f"{where}: missing [siege]")
    _no_extra(siege, set(SIEGE_SCALARS) | {"target_worth"}, _at(COMBAT_TOML, "siege"))
    for key, (const, kind) in SIEGE_SCALARS.items():
        tables.scalars[const] = _float(siege, key, _at(COMBAT_TOML, "siege"))
    worth = siege.get("target_worth")
    if not isinstance(worth, dict) or not worth:
        raise BalanceError(f"{where}: [siege.target_worth] needs at least one unit")
    for unit, factor in worth.items():
        if unit not in PLAYABLE:
            raise BalanceError(f"{_at(COMBAT_TOML, 'siege.target_worth')}: expected a unit, got {unit!r}")
        _reject_bool(factor, _at(COMBAT_TOML, "siege.target_worth"), unit)
        if not isinstance(factor, (int, float)):
            raise BalanceError(f"{_at(COMBAT_TOML, 'siege.target_worth')}.{unit}: expected a number, got {factor!r}")
        tables.siege_worth[unit] = float(factor)
    friendly = doc.get("friendly_fire")
    if not isinstance(friendly, dict):
        raise BalanceError(f"{where}: missing [friendly_fire]")
    _no_extra(friendly, set(FRIENDLY_SCALARS), _at(COMBAT_TOML, "friendly_fire"))
    for key, (const, kind) in FRIENDLY_SCALARS.items():
        tables.scalars[const] = _float(friendly, key, _at(COMBAT_TOML, "friendly_fire"))


def _race(doc: dict, race: str) -> dict:
    where = _at(RACES_TOML, race)
    entry = doc.get(race)
    if not isinstance(entry, dict):
        raise BalanceError(f"{RACES_TOML.name}: missing [{race}]")
    _no_extra(entry, {"name", "adjective", "tagline", "passive", "arts", "units", "buildings", "upgrades"}, where)
    units = entry.get("units", {})
    buildings = entry.get("buildings", {})
    upgrades = entry.get("upgrades", {})
    built = BUILT
    for kind, table, known in (("units", units, PLAYABLE), ("buildings", buildings, built), ("upgrades", upgrades, UPGRADES)):
        if not isinstance(table, dict):
            raise BalanceError(f"{where}.{kind}: expected a table, got {table!r}")
        for key in table:
            if key not in known:
                raise BalanceError(f"{where}.{kind}: unexpected [{key}]")
    for unit in PLAYABLE:
        if unit not in units:
            raise BalanceError(f"{where}.units: missing [{unit}]: every race fields every role")
    for building in BUILDINGS:
        if building in DEPOSITS or building == "lair":
            if building in buildings:
                raise BalanceError(f"{where}.buildings: [{building}] is nobody's: no race names it")
        elif building not in buildings:
            raise BalanceError(f"{where}.buildings: missing [{building}]: every race names every building")
    arts = entry.get("arts", [])
    if not isinstance(arts, list) or any(not isinstance(v, str) or v not in UPGRADES for v in arts):
        raise BalanceError(f"{where}.arts: expected upgrade names, got {arts!r}")
    return {
        "name": _str(entry, "name", where),
        "adjective": _str(entry, "adjective", where),
        "tagline": _str(entry, "tagline", where),
        "passive": _str(entry, "passive", where),
        "arts": list(arts),
        "units": {u: _unit_tweak(units[u], _at(RACES_TOML, f"{race}.units.{u}")) for u in PLAYABLE},
        "buildings": {b: _building_tweak(buildings[b], _at(RACES_TOML, f"{race}.buildings.{b}"))
                      for b in BUILDINGS if b not in DEPOSITS and b != "lair"},
        "upgrades": {u: _upgrade_tweak(upgrades[u], _at(RACES_TOML, f"{race}.upgrades.{u}")) for u in upgrades},
    }


def load() -> Tables:
    """The TOML files as normalized tables, or a BalanceError naming what is wrong."""
    units_doc = _read(UNITS_TOML)
    neutrals_doc = _read(NEUTRALS_TOML)
    buildings_doc = _read(BUILDINGS_TOML)
    upgrades_doc = _read(UPGRADES_TOML)
    races_doc = _read(RACES_TOML)
    _check_sections(units_doc, UNITS_TOML, PLAYABLE, "unit")
    _check_sections(neutrals_doc, NEUTRALS_TOML, WILDS, "neutral")
    _check_sections(buildings_doc, BUILDINGS_TOML, BUILDINGS, "building")
    _check_sections(upgrades_doc, UPGRADES_TOML, UPGRADES + ("effects",), "upgrade")
    for race in RACES:
        if race not in races_doc or not isinstance(races_doc[race], dict):
            raise BalanceError(f"{RACES_TOML.name}: missing [{race}]")
    for section in races_doc:
        if section not in RACES:
            raise BalanceError(f"{RACES_TOML.name}: unexpected race [{section}]; known: {', '.join(RACES)}")
    for unit in PLAYABLE:
        if unit not in units_doc:
            raise BalanceError(f"{UNITS_TOML.name}: missing [{unit}]")
    for unit in WILDS:
        if unit not in neutrals_doc:
            raise BalanceError(f"{NEUTRALS_TOML.name}: missing [{unit}]")
    for building in BUILDINGS:
        if building not in buildings_doc:
            raise BalanceError(f"{BUILDINGS_TOML.name}: missing [{building}]")
    for upgrade in UPGRADES:
        if upgrade not in upgrades_doc:
            raise BalanceError(f"{UPGRADES_TOML.name}: missing [{upgrade}]")
    tables = Tables()
    tables.units = {u: _unit(units_doc[u], _at(UNITS_TOML, u)) for u in PLAYABLE}
    tables.wilds = {u: _unit(neutrals_doc[u], _at(NEUTRALS_TOML, u)) for u in WILDS}
    tables.buildings = {b: _building(buildings_doc[b], _at(BUILDINGS_TOML, b), b) for b in BUILDINGS}
    tables.upgrades = {u: _upgrade(upgrades_doc[u], _at(UPGRADES_TOML, u)) for u in UPGRADES}
    tables.races = {r: _race(races_doc, r) for r in RACES}
    economy_doc = _read(ECONOMY_TOML)
    combat_doc = _read(COMBAT_TOML)
    behavior_doc = _read(BEHAVIOR_TOML)
    for doc, path, sections in ((economy_doc, ECONOMY_TOML, tuple(ECONOMY_SCHEMA)),
                                (behavior_doc, BEHAVIOR_TOML, tuple(BEHAVIOR_SCHEMA))):
        for section in doc:
            if section not in sections:
                raise BalanceError(f"{path.name}: unexpected [{section}]; known: {', '.join(sections)}")
        for section in sections:
            if section not in doc:
                raise BalanceError(f"{path.name}: missing [{section}]")
    for section, schema in ECONOMY_SCHEMA.items():
        _schema_section(economy_doc, ECONOMY_TOML, section, schema, tables.scalars)
    for section, schema in BEHAVIOR_SCHEMA.items():
        _schema_section(behavior_doc, BEHAVIOR_TOML, section, schema, tables.scalars)
    _schema_section(upgrades_doc, UPGRADES_TOML, "effects", EFFECTS_SCHEMA, tables.scalars)
    _combat(combat_doc, tables)
    return tables


# -- Emission ------------------------------------------------------------------

def _unit_type(value: str) -> str:
    return f"UnitType.{value.upper()}"


def _building_type(value: str) -> str:
    return f"BuildingType.{value.upper()}"


def _upgrade_member(value: str) -> str:
    return f"Upgrade.{value.upper()}"


def _race_member(value: str) -> str:
    return f"Race.{value.upper()}"


def _attack(value: str) -> str:
    return f"AttackType.{value.upper()}"


def _armor_class(value: str) -> str:
    return {"unarmoured": "ArmorClass.UNARMORED"}.get(value, f"ArmorClass.{value.upper()}")


def _num(value: int | float) -> str:
    return repr(value)


def _cost(gold: int, lumber: int) -> str:
    return f"Cost({gold})" if not lumber else f"Cost({gold}, {lumber})"


def _unit_entry(unit: str, u: dict) -> str:
    reach = "MELEE" if u["range"] == "melee" else _num(u["range"])
    return (f"    {_unit_type(unit)}: UnitInfo(name={u['name']!r}, cost={_cost(u['gold'], u['lumber'])}, "
            f"hp={u['hp']}, damage={u['damage']}, armor={u['armor']}, range={reach}, cooldown={_num(u['cooldown'])}, "
            f"speed={_num(u['speed'])}, sight={u['sight']}, build_time={_num(u['build_time'])}, "
            f"trained_at={_building_type(u['trained_at'])}, hotkey={u['hotkey']!r}, summary={u['summary']!r}, "
            f"radius={_num(u['radius'])}, heal={u['heal']}, splash={_num(u['splash'])}, attack={_attack(u['attack'])}, "
            f"armor_class={_armor_class(u['armor_class'])}, formation={u['formation']}, mounted={u['mounted']}, "
            f"windup={_num(u['windup'])}, turn=math.radians({u['turn_deg']}), min_range={_num(u['min_range'])}, "
            f"regen={_num(u['regen'])}),")


def _mine(info: dict) -> str:
    if not info["mine_trip"] and not info["mine_slots"]:
        return ""
    endless = ", endless=True" if info["mine_endless"] else ""
    return f", mine=MineInfo(trip={info['mine_trip']}, slots={info['mine_slots']}{endless})"


def _summary(building: str, info: dict) -> str:
    # The seam's card says its true trip: {trip} is rendered from the deposit below at codegen time.
    if "{trip}" in info["summary"]:
        assert building == "gold_seam", "only the seam's summary names its trip"
        return repr(info["summary"].replace("{trip}", str(info["mine_trip"])))
    assert building != "gold_seam", "only the seam's summary names its trip"
    return repr(info["summary"])


def _building_entry(building: str, b: dict) -> str:
    trains = "(" + ", ".join(_unit_type(t) for t in b["trains"]) + ("," if len(b["trains"]) == 1 else "") + ")"
    researches = "(" + ", ".join(_upgrade_member(u) for u in b["researches"]) + ("," if len(b["researches"]) == 1 else "") + ")"
    requires = f", requires={_building_type(b['requires'])}" if b["requires"] is not None else ""
    deposits = (", deposits=frozenset({" + ", ".join(f"Resource.{d.upper()}" for d in b["deposits"]) + "})"
                if b["deposits"] else "")
    return (f"    {_building_type(building)}: BuildingInfo(name={b['name']!r}, cost={_cost(b['gold'], b['lumber'])}, "
            f"hp={b['hp']}, armor={b['armor']}, size={b['size']}, build_time={_num(b['build_time'])}, sight={b['sight']}, "
            f"supply={b['supply']}, hotkey={b['hotkey']!r}, summary={_summary(building, b)}, trains={trains}, "
            f"researches={researches}{requires}{deposits}, damage={b['damage']}, range={_num(b['range'])}, "
            f"cooldown={_num(b['cooldown'])}{_mine(b)}),")


def _upgrade_entry(upgrade: str, u: dict, trip: int) -> str:
    requires = "(" + ", ".join(_upgrade_member(r) for r in u["requires"]) + ("," if len(u["requires"]) == 1 else "") + ")"
    race = f", race={_race_member(u['race'])}" if u["race"] is not None else ""
    return (f"    {_upgrade_member(upgrade)}: UpgradeInfo(name={u['name']!r}, cost={_cost(u['gold'], u['lumber'])}, "
            f"time={_num(u['time'])}, hotkey={u['hotkey']!r}, card={u['card']!r}, summary={_upgrade_summary(upgrade, u, trip)}, "
            f"requires={requires}{race}),")


def _upgrade_summary(upgrade: str, u: dict, trip: int) -> str:
    # Deep Mining's card says its true trip: {trip} is rendered from [effects] at codegen time.
    if "{trip}" in u["summary"]:
        if upgrade != "deep_mining":
            raise BalanceError(f"{UPGRADES_TOML.name} [{upgrade}].summary: only deep_mining names its trip")
        return repr(u["summary"].replace("{trip}", str(trip)))
    return repr(u["summary"])


def _unit_tweak_entry(unit: str, t: dict) -> str:
    return (f"    {_unit_type(unit)}: UnitTweak({t['name']!r}, {t['summary']!r}, hp={_num(t['hp_mult'])}, "
            f"damage={_num(t['damage_mult'])}, armor={t['armor_add']}, range={_num(t['range_add'])}, "
            f"speed={_num(t['speed_add'])}, sight={t['sight_add']}, build_time={_num(t['build_time_mult'])}, "
            f"formation={t['formation']}),")


def _building_tweak_entry(building: str, t: dict) -> str:
    return (f"    {_building_type(building)}: BuildingTweak({t['name']!r}, {t['card']!r}, {t['summary']!r}, "
            f"hp={_num(t['hp_mult'])}, armor={t['armor_add']}),")


def emit(tables: Tables) -> dict[str, str]:
    """The GENERATED region bodies keyed by region name."""
    mine, seam = tables.buildings["gold_mine"], tables.buildings["gold_seam"]
    regions = {
        "units": "UNITS: Final[dict[UnitType, UnitInfo]] = {\n" + "\n".join(
            _unit_entry(u, tables.units[u]) for u in PLAYABLE) + "\n}",
        "wilds": "WILD_UNITS: Final[dict[UnitType, UnitInfo]] = {\n" + "\n".join(
            _unit_entry(u, tables.wilds[u]) for u in WILDS) + "\n}",
        "deposits": (f"GOLD_PER_TRIP: Final = {mine['mine_trip']}\n"
                     f"MINE_SLOTS: Final = {mine['mine_slots']}\n"
                     f"SEAM_PER_TRIP: Final = {seam['mine_trip']}\n"
                     f"SEAM_SLOTS: Final = {seam['mine_slots']}"),
        "buildings": "BUILDINGS: Final[dict[BuildingType, BuildingInfo]] = {\n" + "\n".join(
            _building_entry(b, tables.buildings[b]) for b in BUILDINGS) + "\n}",
        "upgrades": "UPGRADES: Final[dict[Upgrade, UpgradeInfo]] = {\n" + "\n".join(
            _upgrade_entry(u, tables.upgrades[u], tables.scalars["DEEP_MINING_TRIP"]) for u in UPGRADES) + "\n}",
    }
    for race in RACES:
        r = tables.races[race]
        prefix = race.upper()
        regions[f"{race}_units"] = f"_{prefix}_UNITS: Final = {{\n" + "\n".join(
            _unit_tweak_entry(u, r["units"][u]) for u in PLAYABLE) + "\n}"
        built = BUILT
        regions[f"{race}_buildings"] = f"_{prefix}_BUILDINGS: Final = {{\n" + "\n".join(
            _building_tweak_entry(b, r["buildings"][b]) for b in built) + "\n}"
        regions[f"{race}_upgrades"] = f"_{prefix}_UPGRADES: Final = {{\n" + "\n".join(
            f"    {_upgrade_member(u)}: UpgradeTweak({r['upgrades'][u]['name']!r}, {r['upgrades'][u]['card']!r}),"
            for u in r["upgrades"]) + "\n}"
    regions["races"] = "RACES: Final[dict[Race, RaceInfo]] = {\n" + "\n".join(
        f"    {_race_member(race)}: _race({tables.races[race]['name']!r}, {tables.races[race]['adjective']!r}, "
        f"{tables.races[race]['tagline']!r}, {tables.races[race]['passive']!r}, "
        f"({', '.join(_upgrade_member(a) for a in tables.races[race]['arts'])}), "
        f"_{race.upper()}_UNITS, _{race.upper()}_BUILDINGS, _{race.upper()}_UPGRADES)," for race in RACES) + "\n}"
    for region, consts in SCALAR_REGIONS.items():
        try:
            values = [(const, tables.scalars[const]) for const in consts]
        except KeyError as exc:
            raise BalanceError(f"no value for {exc} (a schema forgot it)") from exc
        regions[region] = "\n".join(f"{const}: Final = {value!r}" for const, value in values)
    regions["damage_factors"] = (
        "DAMAGE_FACTORS: Final[dict[tuple[AttackType, ArmorClass], float]] = {\n" + "\n".join(
            f"    ({_attack(b['attack'])}, {_armor_class(b['armor'])}): {b['factor']!r},"
            for b in tables.damage_bonus) + "\n}")
    regions["siege"] = (
        f"SIEGE_STEP: Final = {tables.scalars['SIEGE_STEP']!r}\n"
        "SIEGE_WORTH: Final = {" + ", ".join(f"{_unit_type(u)}: {f!r}" for u, f in tables.siege_worth.items()) + "}\n"
        f"SIEGE_BUILDING_WORTH: Final = {tables.scalars['SIEGE_BUILDING_WORTH']!r}")
    return regions


# -- Regions -------------------------------------------------------------------

#: (python file, region name): the marker lines name the TOML source, so the
#: file itself says where its numbers come from.
TARGETS: tuple[tuple[Path, str, str], ...] = (
    (RULES_PY, "units", "units.toml"),
    (RULES_PY, "wilds", "neutrals.toml"),
    (RULES_PY, "deposits", "buildings.toml"),
    (RULES_PY, "buildings", "buildings.toml"),
    (RULES_PY, "upgrades", "upgrades.toml"),
    (RACES_PY, "human_units", "races.toml"),
    (RACES_PY, "human_buildings", "races.toml"),
    (RACES_PY, "human_upgrades", "races.toml"),
    (RACES_PY, "orc_units", "races.toml"),
    (RACES_PY, "orc_buildings", "races.toml"),
    (RACES_PY, "orc_upgrades", "races.toml"),
    (RACES_PY, "elf_units", "races.toml"),
    (RACES_PY, "elf_buildings", "races.toml"),
    (RACES_PY, "elf_upgrades", "races.toml"),
    (RACES_PY, "dwarf_units", "races.toml"),
    (RACES_PY, "dwarf_buildings", "races.toml"),
    (RACES_PY, "dwarf_upgrades", "races.toml"),
    (RACES_PY, "races", "races.toml"),
    (RULES_PY, "melee", "combat.toml"),
    (RULES_PY, "upgrade_effects", "upgrades.toml"),
    (RULES_PY, "mine_time", "economy.toml"),
    (RULES_PY, "lumber", "economy.toml"),
    (RULES_PY, "repair", "economy.toml"),
    (RULES_PY, "salvage", "economy.toml"),
    (RULES_PY, "setup", "economy.toml"),
    (RULES_PY, "combat", "combat.toml"),
    (RULES_PY, "damage_factors", "combat.toml"),
    (RULES_PY, "friendly_fire", "combat.toml"),
    (RULES_PY, "siege", "combat.toml"),
    (RULES_PY, "formation", "behavior.toml"),
    (RULES_PY, "regen_calm", "behavior.toml"),
    (RULES_PY, "camps", "behavior.toml"),
    (RULES_PY, "pursuit", "behavior.toml"),
    (MODEL_PY, "movement", "behavior.toml"),
)


def _begin(name: str, source: str) -> str:
    return f"# generated-begin {name}: from warband/constants/{source} — do not edit by hand; run tools/balance_tables.py"


def _end(name: str) -> str:
    return f"# generated-end {name}"


def render(path: Path, name: str, source: str, body: str) -> str:
    """*path*'s text with the region replaced by *body*."""
    text = path.read_text(encoding="utf-8")
    begin, end = _begin(name, source), _end(name)
    before, sep, rest = text.partition(begin + "\n")
    if not sep:
        raise BalanceError(f"{path.name}: missing marker {begin}")
    _, sep, after = rest.partition("\n" + end)
    if not sep:
        raise BalanceError(f"{path.name}: missing marker {end} after {begin}")
    return before + begin + "\n" + body + "\n" + end + after


def check() -> list[str]:
    """The drift between the TOML and the simulation, one line per region: empty when they agree."""
    regions = emit(load())
    found = []
    for path, name, source in TARGETS:
        try:
            want = render(path, name, source, regions[name])
        except BalanceError as exc:
            return [str(exc)]
        if want != path.read_text(encoding="utf-8"):
            have = path.read_text(encoding="utf-8").splitlines()
            diff = "\n".join(list(difflib.unified_diff(have, want.splitlines(), lineterm="", n=1))[:24])
            found.append(f"{path.relative_to(ROOT).as_posix()} region {name!r} differs from warband/constants/{source}:\n{diff}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a GENERATED region differs instead of rewriting it")
    args = parser.parse_args()
    try:
        regions = emit(load())
    except BalanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if args.check:
        found = check()
        if found:
            print("\n\n".join(found), file=sys.stderr)
            print("\nrun `uv run python tools/balance_tables.py` to regenerate.", file=sys.stderr)
            raise SystemExit(1)
        print("the balance tables match their TOML")
        return
    for path, name, source in TARGETS:
        updated = render(path, name, source, regions[name])
        if updated != path.read_text(encoding="utf-8"):
            path.write_text(updated, encoding="utf-8")
            print(f"rewrote {path.relative_to(ROOT).as_posix()} region {name!r}")
        else:
            print(f"unchanged {path.relative_to(ROOT).as_posix()} region {name!r}")


if __name__ == "__main__":
    main()
