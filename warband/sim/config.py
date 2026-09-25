"""Read and validate one balance snapshot at startup. Never reload a running game's rules.

The typed simulation tables are built from this snapshot once. League workers
may install their parent's snapshot before importing rules; ordinary launches
read the ten bundled TOMLs. This is the simulation's only file-backed input.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

CONSTANTS: Final = Path(__file__).resolve().parents[1] / "assets" / "constants"
FILES: Final = ("units.toml", "neutrals.toml", "buildings.toml", "upgrades.toml", "races.toml",
               "economy.toml", "combat.toml", "behavior.toml", "buffs.toml", "spells.toml")
UNITS_TOML = Path("units.toml")
BUILDINGS_TOML = Path("buildings.toml")
UPGRADES_TOML = Path("upgrades.toml")
RACES_TOML = Path("races.toml")
NEUTRALS_TOML = Path("neutrals.toml")
ECONOMY_TOML = Path("economy.toml")
COMBAT_TOML = Path("combat.toml")
BEHAVIOR_TOML = Path("behavior.toml")
BUFFS_TOML = Path("buffs.toml")
SPELLS_TOML = Path("spells.toml")

PLAYABLE = ("peasant", "footman", "archer", "knight", "catapult", "flying_machine", "cleric",
            "gryphon", "sapper", "treant", "rune_golem")  # the last four: each race's own unit (units.toml's ``race``)
WILDS = ("wolf", "spider", "troll", "golem")
BUILDINGS = ("town_hall", "farm", "barracks", "tower", "lumber_mill", "blacksmith", "stables", "workshop", "church", "vault",
             "mage_tower", "gold_mine", "gold_seam", "mother_lode", "lair")
DEPOSITS = ("gold_mine", "gold_seam", "mother_lode")
#: What a player builds: everything the wilds do not own (rules.BUILT walks the same set).
BUILT = tuple(b for b in BUILDINGS if b not in DEPOSITS and b != "lair")
#: The research upgrades.toml holds: the shared ladder and the race arts.
LADDER = ("keep", "blades_1", "blades_2", "blades_3", "armor_1", "armor_2", "arrows_1", "arrows_2", "arrows_3", "siege",
          "marksmanship", "horses", "blessing", "bloodlust", "plunder", "longbows", "regrowth", "deep_mining",
          "blasting_powder")
#: The spells (WB-066), researched at the Mage Tower: spells.toml holds them, and what researching one costs is its level's.
SPELLS = ("haste", "mend", "flame_strike", "stoneskin", "entangle", "wither", "meteor", "summon", "battle_fury")
UPGRADES = LADDER + SPELLS
#: The levels of magic, lowest first: a spell of each is researched after one of the level below.
LEVELS = ("I", "II", "III")
#: What a spell brings: units nobody trains and no race names (spells.toml [summons]).
SUMMONS = ("aether_elemental",)
TOUCHES = ("own", "rivals", "all")
RACES = ("human", "orc", "elf", "dwarf")
ATTACKS = ("normal", "piercing", "siege", "crush")
ARMOR_CLASSES = ("unarmoured", "light", "heavy", "fortified")
RESOURCES = ("gold", "lumber")
#: The condition kinds a rule lays on by name (buffs.toml): Rage, Rage under Bloodlust and Bleeding.  Any other row is
#: a kind nothing lays on yet, free to add.
NAMED_BUFFS = ("rage", "bloodlust_rage", "bleeding")


class BalanceError(Exception):
    """A TOML table the simulation cannot start from.  The message names the file, section and key."""


def _read(path: Path, sources: dict[str, str]) -> dict:
    try:
        return tomllib.loads(sources[path.name])
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


def _race_name(entry: dict, key: str, where: str) -> str | None:
    """A race's name, or None when the entry names none."""
    if key not in entry:
        return None
    return _enum(entry, key, where, RACES)


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


def _strings(entry: dict, key: str, where: str) -> list[str]:
    """A list of names checked later against another table (a spell's buffs.toml rows)."""
    value = entry.get(key, [])
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise BalanceError(f"{where}.{key}: expected a list of names, got {value!r}")
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
# Plain values keyed by the enum value each section is named for. Defaults
# are expanded here; the typed tables convert enum names and melee reach.
#
# Scalars land in one flat table keyed by CONSTANT name, whatever file and
# section they come from. What stays in code (SIM_DT, the order bounds, the pathfinder's
# budgets, the seats) is not tunable balance and never enters these schemas.

BUILDING_KEYS = {"name", "gold", "lumber", "hp", "armor", "size", "build_time", "sight", "supply", "hotkey", "summary",
                 "trains", "researches", "requires", "deposits", "damage", "range", "cooldown", "mine_trip", "mine_slots",
                 "mine_endless", "rich_above"}
UPGRADE_KEYS = {"name", "gold", "lumber", "time", "hotkey", "card", "summary", "requires", "race"}
LEVEL_KEYS = {"gold", "lumber", "time", "requires", "aether", "cooldown"}
UPGRADE_TWEAK_KEYS = {"name", "card"}

#: Scalar schemas: section -> {toml key: (CONSTANT, int|float)}.  Sections are
#: required whole: a missing or misspelled key fails, never silently defaults.
ECONOMY_SCHEMA = {
    "work": {"mine_time": ("MINE_TIME", float), "lumber_per_trip": ("LUMBER_PER_TRIP", int),
             "chop_time": ("CHOP_TIME", float)},
    "setup": {"mine_gold": ("MINE_GOLD", int), "expansion_gold": ("EXPANSION_GOLD", int), "lode_gold": ("LODE_GOLD", int),
              "starting_gold": ("STARTING_GOLD", int), "starting_lumber": ("STARTING_LUMBER", int)},
    "repair": {"rate": ("REPAIR_RATE", float), "chunk": ("REPAIR_CHUNK", int), "cost_share": ("REPAIR_COST", float)},
    "salvage": {"rate": ("SALVAGE_RATE", float), "held_rate": ("SALVAGE_HELD_RATE", float),
                "chunk": ("SALVAGE_CHUNK", int), "share": ("SALVAGE_SHARE", float)},
    "aether": {"store": ("AETHER_STORE", int), "every": ("AETHER_EVERY", float), "reach": ("AETHER_REACH", float)},
}
EFFECTS_SCHEMA = {"blades_bonus": ("BLADES_BONUS", int), "master_weapon_bonus": ("MASTER_WEAPON_BONUS", int),
                  "armor_bonus": ("ARMOR_BONUS", int), "arrows_bonus": ("ARROWS_BONUS", int),
                  "horses_bonus": ("HORSES_BONUS", float), "siege_range_bonus": ("SIEGE_RANGE_BONUS", float),
                  "siege_damage_bonus": ("SIEGE_DAMAGE_BONUS", float), "blessing_bonus": ("BLESSING_BONUS", float),
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
    "movement": {"max_push": ("MAX_PUSH", float), "core": ("CORE", float), "spacing": ("SPACING", float),
                 "spacing_weight": ("SPACING_WEIGHT", float), "ease_space": ("EASE_SPACE", float),
                 "ease_every": ("EASE_EVERY", int), "ease_chance": ("EASE_CHANCE", float),
                 "ease_step": ("EASE_STEP", float), "ease_step_variance": ("EASE_STEP_VARIANCE", float),
                 "ease_jitter": ("EASE_JITTER", float), "ease_gain": ("EASE_GAIN", float)},
    "pursuit": {"leash": ("LEASH", float)},
}

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
    buffs: dict[str, dict] = field(default_factory=dict)  # condition kinds, in listed order
    levels: dict[str, dict] = field(default_factory=dict)  # the levels of magic, lowest first
    spells: dict[str, dict] = field(default_factory=dict)  # spell -> its row, in listed order
    summons: dict[str, dict] = field(default_factory=dict)  # what a spell brings, as unit rows
    spell_far: int = 1  # the price beyond every vault's reach, as a multiple of the plain one


def _reach(entry: dict, key: str, where: str) -> float | str:
    if entry.get(key) == "melee":
        return "melee"
    return _float(entry, key, where)


# Field -> (reader, optional reader arguments). One schema validates both a
# shared default and a complete entry; omitted optional fields keep their
# established values.
UNIT_SCHEMA = {
    "name": (_str,), "gold": (_int, 0), "lumber": (_int, 0),
    "hp": (_int,), "damage": (_int,), "armor": (_int,), "range": (_reach,),
    "cooldown": (_float,), "speed": (_float,), "sight": (_int,), "build_time": (_float,),
    "trained_at": (_enum, BUILDINGS), "hotkey": (_str,), "summary": (_str,), "radius": (_float,),
    "heal": (_int, 0), "splash": (_float, 0.0), "attack": (_enum, ATTACKS, "normal"),
    "armor_class": (_enum, ARMOR_CLASSES, "light"), "formation": (_bool, False), "mounted": (_bool, False),
    "windup": (_float,), "turn_deg": (_int, 360), "min_range": (_float, 0.0), "regen": (_float, 0.0),
    "living": (_bool, True), "flying": (_bool, False), "inflicts": (_str, ""), "sound": (_str, ""),
    "lifetime": (_float, 0.0),  # seconds a unit stays before it is gone; 0: for good (a summoned unit's, spells.toml)
    # A race's own unit (WB-068): the one race that fields it, the upgrades it waits for, how many a side may keep.
    "race": (_race_name,), "requires": (_names, UPGRADES), "limit": (_int, 0),
    "blast": (_float, 0.0), "blast_units": (_int, 0), "forest": (_bool, False), "regen_in_trees": (_bool, False),
}
UNIT_TWEAK_SCHEMA = {
    "name": (_str,), "summary": (_str,), "hp_mult": (_float, 1.0), "damage_mult": (_float, 1.0),
    "armor_add": (_int, 0), "range_add": (_float, 0.0), "speed_add": (_float, 0.0),
    "sight_add": (_int, 0), "build_time_mult": (_float, 1.0), "formation": (_bool, True),
}
BUFF_SCHEMA = {
    "name": (_str,), "summary": (_str,), "damage": (_float,), "speed": (_float,), "blow": (_float,), "armor": (_int,),
    "hp_per_second": (_float,), "duration": (_float,), "living": (_bool,), "heal_ends": (_bool,),
    "spares": (_names, ARMOR_CLASSES), "roots": (_bool,),
}
BUILDING_TWEAK_SCHEMA = {
    "name": (_str,), "card": (_str,), "summary": (_str,), "hp_mult": (_float, 1.0), "armor_add": (_int, 0),
}


def _fields(entry: dict, schema: dict, where: str, *, partial: bool = False) -> dict:
    if not isinstance(entry, dict):
        raise BalanceError(f"{where}: expected a table, got {entry!r}")
    _no_extra(entry, set(schema), where)
    return {key: schema[key][0](entry, key, where, *schema[key][1:])
            for key in (entry if partial else schema)}


def _rows(doc: dict, names: tuple[str, ...], schema: dict, where: str) -> dict[str, dict]:
    """Required rows with one optional defaults table; explicit row values win."""
    if not isinstance(doc, dict):
        raise BalanceError(f"{where}: expected a table, got {doc!r}")
    _no_extra(doc, set(names) | {"defaults"}, where)
    # Validate defaults on their own, even when every row overrides a bad value.
    defaults = _fields(doc.get("defaults", {}), schema, f"{where}.defaults", partial=True)
    out = {}
    for name in names:
        location = f"{where}.{name}"
        if name not in doc:
            raise BalanceError(f"{where}: missing [{name}]")
        entry = _fields(doc[name], schema, location, partial=True)
        out[name] = _fields(defaults | entry, schema, location)
    return out


def _building(entry: dict, where: str, section: str) -> dict:
    _no_extra(entry, BUILDING_KEYS, where)
    is_deposit = section in DEPOSITS
    for key in ("mine_trip", "mine_slots", "mine_endless", "rich_above"):
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
        "rich_above": _int(entry, "rich_above", where, 0) if is_deposit else 0,
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
        "choice": "",
        "after": "",
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


def _buffs(doc: dict) -> dict[str, dict]:
    """Every row of buffs.toml, the ones the rules name among them.  A multiplier or a duration that is not
    positive would be a unit that never moves or a condition that is gone before it lands."""
    where = BUFFS_TOML.name
    names = tuple(name for name in doc if name != "defaults")
    for name in NAMED_BUFFS:
        if name not in names:
            raise BalanceError(f"{where}: missing [{name}]")
    rows = _rows(doc, names, BUFF_SCHEMA, where)
    for name, row in rows.items():
        for key in ("damage", "speed", "blow", "duration"):
            if row[key] <= 0:
                raise BalanceError(f"{where} [{name}].{key}: expected a positive number, got {row[key]!r}")
    return rows


SPELL_SCHEMA = {
    "level": (_enum, LEVELS), "name": (_str,), "card": (_str,), "hotkey": (_str,), "summary": (_str,), "radius": (_float,),
    "touches": (_enum, TOUCHES), "flyers": (_bool, True), "lays": (_strings,), "cleanses": (_strings,),
    "damage": (_int, 0), "edge": (_int, -1), "pierces": (_bool, False), "buildings": (_bool, False),
    "building_factor": (_float, 1.0), "delay": (_float, 0.0), "summons": (_str, ""), "count": (_int, 0),
}


def _spells(doc: dict, tables: Tables) -> None:
    """spells.toml: the levels of magic, the spells chosen at each and what they bring (WB-066).  Every spell is also a
    row of the research table, priced by its level: researching one closes the others of its level for the match, and
    a spell above the first level waits for one of the level below (:attr:`~warband.sim.rules.UpgradeInfo.choice`)."""
    where = SPELLS_TOML.name
    _no_extra(doc, {"far", "levels", "spells", "summons"}, where)
    tables.spell_far = _int(doc, "far", where)
    if tables.spell_far < 1:
        raise BalanceError(f"{where}.far: expected at least 1, got {tables.spell_far}")
    levels = doc.get("levels")
    if not isinstance(levels, dict):
        raise BalanceError(f"{where}: missing [levels]")
    _no_extra(levels, set(LEVELS), f"{where} [levels]")
    for level in LEVELS:
        at = f"{where} [levels.{level}]"
        entry = levels.get(level)
        if not isinstance(entry, dict):
            raise BalanceError(f"{where}: missing [levels.{level}]")
        _no_extra(entry, LEVEL_KEYS, at)
        row = {"gold": _int(entry, "gold", at), "lumber": _int(entry, "lumber", at, 0), "time": _float(entry, "time", at),
               "requires": _names(entry, "requires", at, LADDER), "aether": _int(entry, "aether", at),
               "cooldown": _float(entry, "cooldown", at)}
        for key in ("time", "cooldown"):
            if row[key] <= 0:
                raise BalanceError(f"{at}.{key}: expected a positive number, got {row[key]!r}")
        if row["aether"] < 0:
            raise BalanceError(f"{at}.aether: expected no less than 0, got {row['aether']}")
        tables.levels[level] = row
    summons = doc.get("summons", {})
    if not isinstance(summons, dict):
        raise BalanceError(f"{where} [summons]: expected a table, got {summons!r}")
    tables.summons = _rows(summons, SUMMONS, UNIT_SCHEMA, f"{where} [summons]")
    for unit, row in tables.summons.items():
        if row["lifetime"] <= 0:
            raise BalanceError(f"{where} [summons.{unit}].lifetime: a summoned unit is gone after a while, got {row['lifetime']!r}")
    spells = doc.get("spells")
    if not isinstance(spells, dict):
        raise BalanceError(f"{where}: missing [spells]")
    _no_extra(spells, set(SPELLS), f"{where} [spells]")
    for spell in SPELLS:
        at = f"{where} [spells.{spell}]"
        if spell not in spells:
            raise BalanceError(f"{where}: missing [spells.{spell}]")
        row = _fields(spells[spell], SPELL_SCHEMA, at)
        for key in ("lays", "cleanses"):
            for kind in row[key]:
                if kind not in tables.buffs:
                    raise BalanceError(f"{at}.{key}: expected rows of {BUFFS_TOML.name}, got {kind!r}")
        if row["radius"] <= 0:
            raise BalanceError(f"{at}.radius: expected a positive number, got {row['radius']!r}")
        if row["edge"] < 0:
            row["edge"] = row["damage"]
        if row["damage"] < 0 or row["edge"] > row["damage"]:
            raise BalanceError(f"{at}: damage {row['damage']} and edge {row['edge']}: the rim takes no more than the point")
        if row["building_factor"] <= 0 or row["delay"] < 0:
            raise BalanceError(f"{at}: building_factor must be positive and delay no less than 0")
        if bool(row["summons"]) != (row["count"] > 0) or (row["summons"] and row["summons"] not in SUMMONS):
            raise BalanceError(f"{at}: summons names a [summons] row and count how many, both or neither")
        tables.spells[spell] = row
    for spell, row in tables.spells.items():
        level = row["level"]
        price = tables.levels[level]
        below = LEVELS[LEVELS.index(level) - 1] if level != LEVELS[0] else ""
        tables.upgrades[spell] = {"name": row["name"], "gold": price["gold"], "lumber": price["lumber"], "time": price["time"],
                                  "hotkey": row["hotkey"], "card": row["card"], "summary": row["summary"],
                                  "requires": list(price["requires"]), "race": None, "choice": level, "after": below}
    for level in LEVELS:
        if not any(row["level"] == level for row in tables.spells.values()):
            raise BalanceError(f"{where} [levels.{level}]: no spell is chosen at it")


def _race(doc: dict, race: str, units_table: dict[str, dict]) -> dict:
    where = _at(RACES_TOML, race)
    entry = doc.get(race)
    if not isinstance(entry, dict):
        raise BalanceError(f"{RACES_TOML.name}: missing [{race}]")
    _no_extra(entry, {"name", "adjective", "tagline", "passive", "arts", "units", "buildings", "upgrades"}, where)
    # Every role the race fields: the shared ones and its own; another race's own unit is not the race's to name.
    fielded = tuple(unit for unit in PLAYABLE if units_table[unit]["race"] in (None, race))
    units = _rows(entry.get("units", {}), fielded, UNIT_TWEAK_SCHEMA, f"{where}.units")
    buildings = _rows(entry.get("buildings", {}), BUILT, BUILDING_TWEAK_SCHEMA, f"{where}.buildings")
    upgrades = entry.get("upgrades", {})
    if not isinstance(upgrades, dict):
        raise BalanceError(f"{where}.upgrades: expected a table, got {upgrades!r}")
    _no_extra(upgrades, set(UPGRADES), f"{where}.upgrades")
    arts = entry.get("arts", [])
    if not isinstance(arts, list) or any(not isinstance(v, str) or v not in UPGRADES for v in arts):
        raise BalanceError(f"{where}.arts: expected upgrade names, got {arts!r}")
    return {
        "name": _str(entry, "name", where),
        "adjective": _str(entry, "adjective", where),
        "tagline": _str(entry, "tagline", where),
        "passive": _str(entry, "passive", where),
        "arts": list(arts),
        "units": units,
        "buildings": buildings,
        "upgrades": {u: _upgrade_tweak(upgrades[u], _at(RACES_TOML, f"{race}.upgrades.{u}")) for u in upgrades},
    }


def _load(sources: dict[str, str]) -> Tables:
    """Validate a complete snapshot without reading any more files."""
    _no_extra(sources, set(FILES), "constants")
    for name in FILES:
        if name not in sources:
            raise BalanceError(f"constants: missing {name}")
    units_doc = _read(UNITS_TOML, sources)
    neutrals_doc = _read(NEUTRALS_TOML, sources)
    buildings_doc = _read(BUILDINGS_TOML, sources)
    upgrades_doc = _read(UPGRADES_TOML, sources)
    races_doc = _read(RACES_TOML, sources)
    _check_sections(buildings_doc, BUILDINGS_TOML, BUILDINGS, "building")
    _check_sections(upgrades_doc, UPGRADES_TOML, LADDER + ("effects",), "upgrade")
    for race in RACES:
        if race not in races_doc or not isinstance(races_doc[race], dict):
            raise BalanceError(f"{RACES_TOML.name}: missing [{race}]")
    for section in races_doc:
        if section not in RACES:
            raise BalanceError(f"{RACES_TOML.name}: unexpected race [{section}]; known: {', '.join(RACES)}")
    for building in BUILDINGS:
        if building not in buildings_doc:
            raise BalanceError(f"{BUILDINGS_TOML.name}: missing [{building}]")
    for upgrade in LADDER:
        if upgrade not in upgrades_doc:
            raise BalanceError(f"{UPGRADES_TOML.name}: missing [{upgrade}]")
    tables = Tables()
    tables.units = _rows(units_doc, PLAYABLE, UNIT_SCHEMA, UNITS_TOML.name)
    tables.wilds = _rows(neutrals_doc, WILDS, UNIT_SCHEMA, NEUTRALS_TOML.name)
    tables.buildings = {b: _building(buildings_doc[b], _at(BUILDINGS_TOML, b), b) for b in BUILDINGS}
    tables.upgrades = {u: _upgrade(upgrades_doc[u], _at(UPGRADES_TOML, u)) for u in LADDER}
    for unit, info in tables.units.items():
        if unit not in tables.buildings[info["trained_at"]]["trains"]:
            raise BalanceError(f"{UNITS_TOML.name} [{unit}].trained_at: the {info['trained_at']} does not list it in its trains")
    tables.races = {r: _race(races_doc, r, tables.units) for r in RACES}
    economy_doc = _read(ECONOMY_TOML, sources)
    combat_doc = _read(COMBAT_TOML, sources)
    behavior_doc = _read(BEHAVIOR_TOML, sources)
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
    tables.buffs = _buffs(_read(BUFFS_TOML, sources))
    _spells(_read(SPELLS_TOML, sources), tables)
    for path, rows in ((UNITS_TOML, tables.units), (NEUTRALS_TOML, tables.wilds)):
        for unit, row in rows.items():
            if row["inflicts"] and row["inflicts"] not in tables.buffs:
                raise BalanceError(f"{path.name} [{unit}].inflicts: expected a row of {BUFFS_TOML.name}, got {row['inflicts']!r}")
    return tables


def read_sources(constants: Path = CONSTANTS) -> dict[str, str]:
    """Capture every file together, before constructing any rule tables."""
    return {name: (constants / name).read_text(encoding="utf-8") for name in FILES}


def load(constants: Path = CONSTANTS) -> Tables:
    """Validate a directory independently, without changing the running game's snapshot."""
    return _load(read_sources(constants))


_sources: dict[str, str] | None = None
_tables: Tables | None = None


def install(sources: dict[str, str]) -> None:
    """Select a worker's snapshot before rules load. An already selected snapshot cannot change."""
    global _sources, _tables
    if _sources is not None:
        if sources != _sources:
            raise RuntimeError("balance constants are already loaded")
        return
    tables = _load(sources)
    _sources, _tables = dict(sources), tables


def current() -> Tables:
    """The process's validated balance snapshot, captured on its first use."""
    if _tables is None:
        install(read_sources())
    assert _tables is not None
    return _tables


def sources() -> dict[str, str]:
    """A copy of the exact startup inputs, for compiled workers to inherit."""
    current()
    assert _sources is not None
    return dict(_sources)


def integer(name: str) -> int:
    value = current().scalars[name]
    assert isinstance(value, int), name
    return value


def number(name: str) -> float:
    value = current().scalars[name]
    assert isinstance(value, float), name
    return value
