"""The four races: what differs on top of the shared skeleton in :mod:`warband.sim.rules`.

Names and modifiers come from the process's startup snapshot of
``warband/assets/constants/races.toml``. Edits apply on the next launch.

Every race fields the same seven roles from the same nine buildings with the
same hotkeys and costs, so the AI, the settlement planner, the saves and the
network protocol never care who is playing.  A race changes the names, a few
numbers per role (built into the :class:`UnitInfo` / :class:`BuildingInfo` a
unit or building reports), what it calls the Keep its hall is raised to, which
two race arts it may research, and one passive mechanic the simulation applies:

| race   | passive                                                  | arts                         |
|--------|----------------------------------------------------------|------------------------------|
| Humans | Drill: units train 15 % faster                            | Horse Breeding, Blessing     |
| Orcs   | Rage: +25 % damage for ten seconds once below half health; tougher, thinner armour | Bloodlust, Plunder |
| Elves  | Keen eyes: +2 sight, rangers shoot a tile farther; lighter | Longbows, Regrowth          |
| Dwarves| Stonework: buildings +25 % hp and +2 armour; sturdier, slower | Deep Mining, Blasting Powder |
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from warband.sim import config

from warband.sim.rules import (BUILDINGS, UNITS, UPGRADES, WILD_BUILDINGS, BuildingInfo, BuildingType, Race, UnitInfo, UnitType,
                               Upgrade, UpgradeInfo, fill)


@dataclass(frozen=True)
class UnitTweak:
    name: str
    summary: str
    hp: float = 1.0  # multiplier
    damage: float = 1.0  # multiplier
    armor: int = 0  # added
    range: float = 0.0  # added (ranged units only)
    speed: float = 0.0  # added
    sight: int = 0  # added
    build_time: float = 1.0  # multiplier
    formation: bool = True  # False: this race's unit does not march in a line though the base one does


@dataclass(frozen=True)
class BuildingTweak:
    name: str
    card: str  # short enough for a command-card button
    summary: str
    hp: float = 1.0
    armor: int = 0


@dataclass(frozen=True)
class UpgradeTweak:
    """A race's own name for an upgrade the shared table names once.  Only the Keep is renamed so far: every race
    already names its hall, so the hall it is raised to is the race's own too."""

    name: str
    card: str  # short enough for a command-card button


@dataclass(frozen=True)
class RaceInfo:
    name: str  # "Orcs"
    adjective: str  # "Orcish"
    tagline: str
    passive: str
    arts: tuple[Upgrade, ...]
    units: dict[UnitType, UnitInfo]
    buildings: dict[BuildingType, BuildingInfo]
    upgrades: dict[Upgrade, UpgradeInfo]
    cards: dict[BuildingType, str]

    def upgrade_allowed(self, upgrade: Upgrade) -> bool:
        race = UPGRADES[upgrade].race
        return race is None or upgrade in self.arts


def _units(tweaks: dict[UnitType, UnitTweak]) -> dict[UnitType, UnitInfo]:
    """The seven roles a race fields, as that race names and tweaks them.

    The neutral creatures are not among them: no race names one, so none has an entry for one, and a
    creature's numbers come out of the shared table instead (:func:`warband.sim.model.unit_stats`).
    """
    out: dict[UnitType, UnitInfo] = {}
    for unit_type, t in tweaks.items():
        base = UNITS[unit_type]
        out[unit_type] = replace(
            base, name=t.name, summary=t.summary, hp=int(round(base.hp * t.hp)), damage=int(round(base.damage * t.damage)),
            armor=base.armor + t.armor, range=base.range + (t.range if base.ranged else 0.0), speed=round(base.speed + t.speed, 2),
            sight=base.sight + t.sight, build_time=round(base.build_time * t.build_time, 2), formation=base.formation and t.formation,
        )
    return out


def _buildings(tweaks: dict[BuildingType, BuildingTweak]) -> dict[BuildingType, BuildingInfo]:
    out: dict[BuildingType, BuildingInfo] = {}
    for building_type, base in BUILDINGS.items():
        if building_type in WILD_BUILDINGS:
            out[building_type] = base  # a deposit and a lair are nobody's: no race names them, tweaks them or draws them
            continue
        t = tweaks[building_type]
        out[building_type] = replace(base, name=t.name, summary=fill(t.summary), hp=int(round(base.hp * t.hp)), armor=base.armor + t.armor)
    return out


def _upgrades(tweaks: dict[Upgrade, UpgradeTweak]) -> dict[Upgrade, UpgradeInfo]:
    """Every upgrade as this race names it: the shared table, with the tweaked ones renamed."""
    out: dict[Upgrade, UpgradeInfo] = {}
    for upgrade, base in UPGRADES.items():
        t = tweaks.get(upgrade)
        out[upgrade] = base if t is None else replace(base, name=t.name, card=t.card)
    return out


def _race(race: Race) -> RaceInfo:
    r = config.current().races[race.value]
    units = {UnitType(u): UnitTweak(
        t["name"], t["summary"], hp=t["hp_mult"], damage=t["damage_mult"], armor=t["armor_add"],
        range=t["range_add"], speed=t["speed_add"], sight=t["sight_add"], build_time=t["build_time_mult"],
        formation=t["formation"],
    ) for u, t in r["units"].items()}
    buildings = {BuildingType(b): BuildingTweak(t["name"], t["card"], t["summary"], hp=t["hp_mult"], armor=t["armor_add"])
                 for b, t in r["buildings"].items()}
    upgrades = {Upgrade(u): UpgradeTweak(t["name"], t["card"]) for u, t in r["upgrades"].items()}
    return RaceInfo(r["name"], r["adjective"], r["tagline"], r["passive"], tuple(Upgrade(a) for a in r["arts"]),
                    _units(units), _buildings(buildings), _upgrades(upgrades), {bt: t.card for bt, t in buildings.items()})


RACES: Final[dict[Race, RaceInfo]] = {race: _race(race) for race in Race}
