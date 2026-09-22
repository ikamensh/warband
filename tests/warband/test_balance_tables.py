"""The balance tables are edited as TOML and generated into the simulation.

A tuner edits the files in ``warband/constants/`` (units, neutrals,
buildings, upgrades, races, economy, combat, behaviour), then runs
``uv run python tools/balance_tables.py`` to rewrite the GENERATED regions of
``warband/sim/rules.py``, ``races.py`` and ``model.py``.  This holds the two
together: the regions must be exactly what the tool emits from the TOML, and
the live tables and constants must say what the TOML says.  Either drift
fails here with the command that fixes it.
"""

import json
import math
import shutil
import subprocess
import sys
import tomllib

import pytest


@pytest.fixture
def constants(tmp_path):
    from tools.balance_tables import CONSTANTS

    return shutil.copytree(CONSTANTS, tmp_path / "constants")


def _write_toml(path, doc):
    """Write test inputs independently of the checked-in TOML's layout."""
    def value(item):
        if isinstance(item, dict):
            return "{ " + ", ".join(f"{k} = {value(v)}" for k, v in item.items()) + " }"
        return json.dumps(item)

    path.write_text("\n".join(f"{k} = {value(v)}" for k, v in doc.items()), encoding="utf-8")


@pytest.mark.parametrize("filename,section,key", [
    ("units.toml", (), "armor"),
    ("neutrals.toml", (), "trained_at"),
    ("races.toml", ("orc", "units"), "hp_mult"),
    ("races.toml", ("dwarf", "buildings"), "hp_mult"),
])
def test_shared_defaults_and_explicit_exceptions_generate_the_same_game(constants, filename, section, key):
    """Factoring repeated values into defaults preserves every generated rule, including exceptions."""
    from tools.balance_tables import emit, load

    before = emit(load())
    path = constants / filename
    doc = tomllib.loads(path.read_text())
    rows = doc
    for part in section:
        rows = rows[part]
    inherited = rows.pop("defaults", {})
    for name, row in rows.items():
        rows[name] = inherited | row
    _write_toml(path, doc)
    assert emit(load(constants)) == before

    entries = list(rows.values())
    shared = entries[0][key]
    rows["defaults"] = {key: shared}
    for row in entries:
        if row.get(key) == shared:
            del row[key]
    _write_toml(path, doc)

    assert emit(load(constants)) == before


@pytest.mark.parametrize("key,shared,override", [
    ("armor_add", 3, 0), ("hp_mult", 1.2, 1.0), ("formation", True, False),
])
def test_explicit_neutral_and_false_modifiers_override_shared_defaults(constants, key, shared, override):
    """An explicit zero, one or false resets a shared modifier; it is never treated as absent."""
    from tools.balance_tables import load

    path = constants / "races.toml"
    doc = tomllib.loads(path.read_text())
    units = doc["human"]["units"]
    units.setdefault("defaults", {})[key] = shared
    for name, row in units.items():
        if name != "defaults":
            row.pop(key, None)
    units["footman"][key] = override
    _write_toml(path, doc)

    loaded = load(constants).races["human"]["units"]
    assert loaded["peasant"][key] == shared
    assert loaded["footman"][key] == override


@pytest.mark.parametrize("section,key,bad", [
    ("defaults", "armour", 0),
    ("defaults", "hp", True),
    ("defaults", "speed", "fast"),
    ("defaults", "attack", "magic"),
    ("peasant", "armor", False),
    ("peasant", "formation", 1),
    ("peasant", "range", "near"),
])
def test_invalid_values_fail_even_in_overridden_defaults(constants, section, key, bad):
    """Misspellings and wrong types must name the bad field, even when defaults would go unused."""
    from tools.balance_tables import BalanceError, load

    path = constants / "units.toml"
    doc = tomllib.loads(path.read_text())
    doc.setdefault(section, {})[key] = bad
    _write_toml(path, doc)

    with pytest.raises(BalanceError, match=rf"units\.toml\.{section}.*{key}"):
        load(constants)


@pytest.mark.parametrize("missing", ["hp", "peasant"])
def test_defaults_do_not_hide_missing_required_stats_or_roles(constants, missing):
    """Defaults may supply a field, but cannot invent a missing role or an unspecified required stat."""
    from tools.balance_tables import BalanceError, load

    path = constants / "units.toml"
    doc = tomllib.loads(path.read_text())
    if missing == "hp":
        doc["peasant"].pop("hp", None)
        doc.get("defaults", {}).pop("hp", None)
    else:
        del doc[missing]
    _write_toml(path, doc)

    with pytest.raises(BalanceError, match=rf"units\.toml.*missing.*{missing}"):
        load(constants)


@pytest.mark.slow
def test_editing_and_regenerating_constants_leaves_a_running_game_unchanged(tmp_path):
    """A real isolated process keeps playing its original rules after a tuner regenerates its files."""
    from tools.balance_tables import ROOT

    package = tmp_path / "warband"
    package.mkdir()
    shutil.copy(ROOT / "warband/__init__.py", package)
    for folder in ("sim", "constants"):
        shutil.copytree(ROOT / "warband" / folder, package / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "tools").mkdir()
    shutil.copy(ROOT / "tools/balance_tables.py", tmp_path / "tools")
    script = '''
from pathlib import Path
import re
import subprocess
import sys
from warband.sim.model import World
from warband.sim.rules import Race, Terrain, UnitType

world = World(20, 20, [[Terrain.GRASS] * 20 for _ in range(20)], 2,
              races=[Race.HUMAN, Race.ORC], scripted=True)
world.spawn_unit(0, UnitType.FOOTMAN, (6.5, 6.5))
world.spawn_unit(1, UnitType.ARCHER, (10.5, 6.5))
world.step()

def play(match):
    knight = match.spawn_unit(0, UnitType.KNIGHT, (5.5, 5.5))
    match.attack_move([knight.id], (10.5, 6.5))
    for _ in range(100):
        match.step()
    return match.to_dict()

expected = play(World.from_dict(world.to_dict()))
old_hp = world.unit_info(0, UnitType.FOOTMAN).hp
path = Path("warband/constants/units.toml")
source = path.read_text()
path.write_text(re.sub(r"(?m)^hp = .*", "hp = 9999", source))
subprocess.run([sys.executable, "tools/balance_tables.py"], check=True, capture_output=True)
assert "hp=9999" in Path("warband/sim/rules.py").read_text()
assert world.unit_info(0, UnitType.FOOTMAN).hp == old_hp
# Even broken TOML cannot affect an already launched match or its new units.
for path in Path("warband/constants").glob("*.toml"):
    path.write_text("this is no longer valid TOML")
assert play(world) == expected
'''
    done = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr


def _norm(value):
    """A table field as the TOML says it: enums by value, in order, except sets which have none."""
    if isinstance(value, (frozenset, set)):
        return sorted(getattr(v, "value", v) for v in value)
    if isinstance(value, (tuple, list)):
        return [getattr(v, "value", v) for v in value]
    return getattr(value, "value", value)


def test_the_toml_balance_tables_match_the_simulation() -> None:
    from tools.balance_tables import SCALAR_REGIONS, check, load

    from warband.sim import model, races, rules

    regions = check()
    assert not regions, ("the GENERATED regions are not what the TOML says:\n" + "\n\n".join(regions)
                         + "\nrun `uv run python tools/balance_tables.py` to regenerate.")
    tables = load()
    found = []

    def agree(what: str, live, want) -> None:
        if _norm(live) != _norm(want):
            found.append(f"{what}: the simulation says {live!r}, the TOML says {want!r}")

    for unit, u in {**tables.units, **tables.wilds}.items():
        live = rules.UNITS[rules.UnitType(unit)]
        reach = tables.scalars["MELEE"] if u["range"] == "melee" else u["range"]
        for key, want in (("name", u["name"]), ("hp", u["hp"]), ("damage", u["damage"]), ("armor", u["armor"]),
                          ("range", reach), ("cooldown", u["cooldown"]), ("speed", u["speed"]), ("sight", u["sight"]),
                          ("build_time", u["build_time"]), ("hotkey", u["hotkey"]), ("summary", u["summary"]),
                          ("radius", u["radius"]), ("heal", u["heal"]), ("splash", u["splash"]),
                          ("windup", u["windup"]), ("min_range", u["min_range"]), ("regen", u["regen"])):
            agree(f"units.toml [{unit}].{key}", getattr(live, key), want)
        agree(f"units.toml [{unit}].gold", live.cost.gold, u["gold"])
        agree(f"units.toml [{unit}].lumber", live.cost.lumber, u["lumber"])
        agree(f"units.toml [{unit}].trained_at", live.trained_at, u["trained_at"])
        agree(f"units.toml [{unit}].attack", live.attack, u["attack"])
        agree(f"units.toml [{unit}].armor_class", live.armor_class, u["armor_class"])
        agree(f"units.toml [{unit}].formation", live.formation, u["formation"])
        agree(f"units.toml [{unit}].mounted", live.mounted, u["mounted"])
        agree(f"units.toml [{unit}].turn", live.turn, math.radians(u["turn_deg"]))

    mine, seam = tables.buildings["gold_mine"], tables.buildings["gold_seam"]
    for key, want in (("GOLD_PER_TRIP", mine["mine_trip"]), ("MINE_SLOTS", mine["mine_slots"]),
                      ("SEAM_PER_TRIP", seam["mine_trip"]), ("SEAM_SLOTS", seam["mine_slots"])):
        agree(f"buildings.toml deposit {key}", getattr(rules, key), want)
    for building, b in tables.buildings.items():
        live = rules.BUILDINGS[rules.BuildingType(building)]
        keys = (("name", b["name"]), ("hp", b["hp"]), ("armor", b["armor"]), ("size", b["size"]),
                ("build_time", b["build_time"]), ("sight", b["sight"]), ("supply", b["supply"]),
                ("hotkey", b["hotkey"]), ("damage", b["damage"]), ("range", b["range"]),
                ("cooldown", b["cooldown"]))
        for key, want in keys:
            agree(f"buildings.toml [{building}].{key}", getattr(live, key), want)
        if building == "gold_seam":
            pass  # its summary renders {trip} from the deposit; checked below
        else:
            agree(f"buildings.toml [{building}].summary", live.summary, b["summary"])
        agree(f"buildings.toml [{building}].gold", live.cost.gold, b["gold"])
        agree(f"buildings.toml [{building}].lumber", live.cost.lumber, b["lumber"])
        agree(f"buildings.toml [{building}].trains", live.trains, b["trains"])
        agree(f"buildings.toml [{building}].researches", live.researches, b["researches"])
        agree(f"buildings.toml [{building}].requires", live.requires, b["requires"])
        agree(f"buildings.toml [{building}].deposits", live.deposits, b["deposits"])
        if building in ("gold_mine", "gold_seam"):
            agree(f"buildings.toml [{building}].trip", live.mine.trip, b["mine_trip"])
            agree(f"buildings.toml [{building}].slots", live.mine.slots, b["mine_slots"])
            agree(f"buildings.toml [{building}].endless", live.mine.endless, b["mine_endless"])
        else:
            agree(f"buildings.toml [{building}].mine", live.mine, None)
    agree("buildings.toml [gold_seam].summary", rules.BUILDINGS[rules.BuildingType.GOLD_SEAM].summary,
          seam["summary"].replace("{trip}", str(seam["mine_trip"])))

    for region, consts in SCALAR_REGIONS.items():
        home = model if region == "movement" else rules
        for const in consts:
            agree(f"warband/constants {const}", getattr(home, const), tables.scalars[const])
    agree("combat.toml [[damage_bonus]]",
          sorted((attack.value, armor.value, factor) for (attack, armor), factor in rules.DAMAGE_FACTORS.items()),
          sorted((b["attack"], b["armor"], b["factor"]) for b in tables.damage_bonus))
    agree("combat.toml [siege.target_worth]",
          {unit.value: factor for unit, factor in rules.SIEGE_WORTH.items()}, tables.siege_worth)
    agree("upgrades.toml [deep_mining].summary", rules.UPGRADES[rules.Upgrade.DEEP_MINING].summary,
          tables.upgrades["deep_mining"]["summary"].replace("{trip}", str(tables.scalars["DEEP_MINING_TRIP"])))

    for upgrade, u in tables.upgrades.items():
        live = rules.UPGRADES[rules.Upgrade(upgrade)]
        keys = (("name", u["name"]), ("time", u["time"]), ("hotkey", u["hotkey"]), ("card", u["card"]),
                ("summary", u["summary"]))
        if upgrade == "deep_mining":
            keys = keys[:-1]  # its summary renders {trip} from [effects]; checked below
        for key, want in keys:
            agree(f"upgrades.toml [{upgrade}].{key}", getattr(live, key), want)
        agree(f"upgrades.toml [{upgrade}].gold", live.cost.gold, u["gold"])
        agree(f"upgrades.toml [{upgrade}].lumber", live.cost.lumber, u["lumber"])
        agree(f"upgrades.toml [{upgrade}].requires", live.requires, u["requires"])
        agree(f"upgrades.toml [{upgrade}].race", live.race, u["race"])

    for race, r in tables.races.items():
        live = races.RACES[rules.Race(race)]
        for key, want in (("name", r["name"]), ("adjective", r["adjective"]), ("tagline", r["tagline"]),
                          ("passive", r["passive"])):
            agree(f"races.toml [{race}].{key}", getattr(live, key), want)
        agree(f"races.toml [{race}].arts", live.arts, r["arts"])
        for unit, t in r["units"].items():
            # The arithmetic of races._units, spelled out so this test holds the data, not the helper.
            base = rules.UNITS[rules.UnitType(unit)]
            info = live.units[rules.UnitType(unit)]
            agree(f"races.toml [{race}.units.{unit}].name", info.name, t["name"])
            agree(f"races.toml [{race}.units.{unit}].summary", info.summary, t["summary"])
            agree(f"races.toml [{race}.units.{unit}].hp", info.hp, int(round(base.hp * t["hp_mult"])))
            agree(f"races.toml [{race}.units.{unit}].damage", info.damage, int(round(base.damage * t["damage_mult"])))
            agree(f"races.toml [{race}.units.{unit}].armor", info.armor, base.armor + t["armor_add"])
            agree(f"races.toml [{race}.units.{unit}].range", info.range,
                  base.range + (t["range_add"] if base.ranged else 0.0))
            agree(f"races.toml [{race}.units.{unit}].speed", info.speed, round(base.speed + t["speed_add"], 2))
            agree(f"races.toml [{race}.units.{unit}].sight", info.sight, base.sight + t["sight_add"])
            agree(f"races.toml [{race}.units.{unit}].build_time", info.build_time,
                  round(base.build_time * t["build_time_mult"], 2))
            agree(f"races.toml [{race}.units.{unit}].formation", info.formation, base.formation and t["formation"])
        for building, t in r["buildings"].items():
            base = rules.BUILDINGS[rules.BuildingType(building)]
            info = live.buildings[rules.BuildingType(building)]
            agree(f"races.toml [{race}.buildings.{building}].name", info.name, t["name"])
            agree(f"races.toml [{race}.buildings.{building}].summary", info.summary, t["summary"])
            agree(f"races.toml [{race}.buildings.{building}].hp", info.hp, int(round(base.hp * t["hp_mult"])))
            agree(f"races.toml [{race}.buildings.{building}].armor", info.armor, base.armor + t["armor_add"])
        for upgrade, t in r["upgrades"].items():
            info = live.upgrades[rules.Upgrade(upgrade)]
            agree(f"races.toml [{race}.upgrades.{upgrade}].name", info.name, t["name"])
            agree(f"races.toml [{race}.upgrades.{upgrade}].card", info.card, t["card"])

    assert not found, ("the TOML and the simulation disagree:\n" + "\n".join(found)
                       + "\nrun `uv run python tools/balance_tables.py` to regenerate.")
