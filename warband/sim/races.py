"""The four races: what differs on top of the shared skeleton in :mod:`warband.sim.rules`.

To rename a race's units or retune its edge, edit
``warband/constants/races.toml`` and run ``uv run python tools/balance_tables.py``
from the repository root, which rewrites the GENERATED regions below.  Never
edit those regions by hand; ``tests/warband/test_balance_tables.py`` fails
until the two agree.

Every race fields the same seven roles from the same nine buildings with the
same hotkeys and costs, so the AI, the settlement planner, the saves and the
network protocol never care who is playing.  A race changes the names, a few
numbers per role (built into the :class:`UnitInfo` / :class:`BuildingInfo` a
unit or building reports), what it calls the Keep its hall is raised to, which
two race arts it may research, and one passive mechanic the simulation applies:

| race   | passive                                                  | arts                         |
|--------|----------------------------------------------------------|------------------------------|
| Humans | Drill: units train 15 % faster                            | Horse Breeding, Blessing     |
| Orcs   | Frenzy: +25 % damage below half health; tougher, thinner armour | Bloodlust, Plunder     |
| Elves  | Keen eyes: +2 sight, rangers shoot a tile farther; lighter | Longbows, Regrowth          |
| Dwarves| Stonework: buildings +25 % hp and +2 armour; sturdier, slower | Deep Mining, Blasting Powder |
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from warband.sim.rules import (BUILDINGS, UNITS, UPGRADES, WILD_BUILDINGS, BuildingInfo, BuildingType, Race, UnitInfo, UnitType,
                               Upgrade, UpgradeInfo)


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
        out[building_type] = replace(base, name=t.name, summary=t.summary, hp=int(round(base.hp * t.hp)), armor=base.armor + t.armor)
    return out


def _upgrades(tweaks: dict[Upgrade, UpgradeTweak]) -> dict[Upgrade, UpgradeInfo]:
    """Every upgrade as this race names it: the shared table, with the tweaked ones renamed."""
    out: dict[Upgrade, UpgradeInfo] = {}
    for upgrade, base in UPGRADES.items():
        t = tweaks.get(upgrade)
        out[upgrade] = base if t is None else replace(base, name=t.name, card=t.card)
    return out


def _race(name: str, adjective: str, tagline: str, passive: str, arts: tuple[Upgrade, ...],
          units: dict[UnitType, UnitTweak], buildings: dict[BuildingType, BuildingTweak],
          upgrades: dict[Upgrade, UpgradeTweak]) -> RaceInfo:
    return RaceInfo(name, adjective, tagline, passive, arts, _units(units), _buildings(buildings), _upgrades(upgrades),
                    {bt: t.card for bt, t in buildings.items()})


# generated-begin human_units: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_HUMAN_UNITS: Final = {
    UnitType.PEASANT: UnitTweak('Peasant', 'Mines gold, chops lumber, builds, repairs', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.FOOTMAN: UnitTweak('Footman', 'Slow shield-wall swordsman; tougher with a comrade at each side', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.ARCHER: UnitTweak('Archer', 'Shoots from four tiles; fragile up close', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.SCOUT: UnitTweak('Scout', 'Fast rider who sees far; raids workers', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.KNIGHT: UnitTweak('Knight', 'Fast, heavily armoured shock cavalry', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.CATAPULT: UnitTweak('Catapult', 'Siege engine: splash, ×1.5 vs buildings', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
    UnitType.CLERIC: UnitTweak('Cleric', 'Heals wounded allies; smites weakly when none need healing', hp=1.0, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=0.85, formation=True),
}
# generated-end human_units
# generated-begin human_buildings: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_HUMAN_BUILDINGS: Final = {
    BuildingType.TOWN_HALL: BuildingTweak('Town Hall', 'Hall', 'Trains peasants; takes gold and lumber', hp=1.0, armor=0),
    BuildingType.FARM: BuildingTweak('Farm', 'Farm', 'Feeds four units', hp=1.0, armor=0),
    BuildingType.BARRACKS: BuildingTweak('Barracks', 'Barracks', 'Trains footmen and archers', hp=1.0, armor=0),
    BuildingType.TOWER: BuildingTweak('Guard Tower', 'Tower', 'Shoots at enemies six tiles away', hp=1.0, armor=0),
    BuildingType.LUMBER_MILL: BuildingTweak('Lumber Mill', 'Mill', 'Takes lumber; researches better arrows', hp=1.0, armor=0),
    BuildingType.BLACKSMITH: BuildingTweak('Blacksmith', 'Smith', 'Researches sharper blades and plate armour', hp=1.0, armor=0),
    BuildingType.STABLES: BuildingTweak('Stables', 'Stables', 'Trains scouts and knights; breeds horses', hp=1.0, armor=0),
    BuildingType.WORKSHOP: BuildingTweak('Workshop', 'Workshop', 'Builds catapults; improves siege engines', hp=1.0, armor=0),
    BuildingType.CHURCH: BuildingTweak('Church', 'Church', 'Trains clerics; blesses their healing', hp=1.0, armor=0),
}
# generated-end human_buildings
# generated-begin human_upgrades: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_HUMAN_UPGRADES: Final = {
    Upgrade.KEEP: UpgradeTweak('Keep', 'Keep'),
}
# generated-end human_upgrades

# generated-begin orc_units: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ORC_UNITS: Final = {
    UnitType.PEASANT: UnitTweak('Peon', 'Digs gold, hacks lumber, builds and repairs', hp=1.15, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
    UnitType.FOOTMAN: UnitTweak('Grunt', 'Brutal axeman, fast and alone; hits harder as it bleeds', hp=1.15, damage=1.1, armor=-2, range=0.0, speed=0.4, sight=0, build_time=1.0, formation=False),
    UnitType.ARCHER: UnitTweak('Axethrower', 'Throws axes four tiles; a sturdy shooter', hp=1.15, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
    UnitType.SCOUT: UnitTweak('Wolf Rider', 'Fast wolf rider; hunts peons and throwers', hp=1.15, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
    UnitType.KNIGHT: UnitTweak('Ogre', 'Two-headed brute; thin armour, all frenzy', hp=1.2, damage=1.1, armor=-1, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
    UnitType.CATAPULT: UnitTweak('Catapult', 'Skulled siege engine: splash, ×1.5 vs walls', hp=1.15, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
    UnitType.CLERIC: UnitTweak('Shaman', 'Mends wounded allies; hexes weakly when none need mending', hp=1.15, damage=1.0, armor=0, range=0.0, speed=0.0, sight=0, build_time=1.0, formation=True),
}
# generated-end orc_units
# generated-begin orc_buildings: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ORC_BUILDINGS: Final = {
    BuildingType.TOWN_HALL: BuildingTweak('Great Hall', 'Hall', 'Trains peons; takes gold and lumber', hp=1.0, armor=0),
    BuildingType.FARM: BuildingTweak('Pig Farm', 'Pig Farm', 'Feeds four units', hp=1.0, armor=0),
    BuildingType.BARRACKS: BuildingTweak('War Camp', 'War Camp', 'Trains grunts and axethrowers', hp=1.0, armor=0),
    BuildingType.TOWER: BuildingTweak('Watch Tower', 'Tower', 'Hurls axes at enemies six tiles away', hp=1.0, armor=0),
    BuildingType.LUMBER_MILL: BuildingTweak('Sawmill', 'Sawmill', 'Takes lumber; researches heavier axes', hp=1.0, armor=0),
    BuildingType.BLACKSMITH: BuildingTweak('Forge', 'Forge', 'Researches blades, hide armour, Bloodlust', hp=1.0, armor=0),
    BuildingType.STABLES: BuildingTweak('Kennels', 'Kennels', 'Trains wolf riders and ogres; Plunder', hp=1.0, armor=0),
    BuildingType.WORKSHOP: BuildingTweak('Siege Yard', 'Yard', 'Builds catapults; improves siege engines', hp=1.0, armor=0),
    BuildingType.CHURCH: BuildingTweak('Altar', 'Altar', 'Trains shamans', hp=1.0, armor=0),
}
# generated-end orc_buildings
# generated-begin orc_upgrades: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ORC_UPGRADES: Final = {
    Upgrade.KEEP: UpgradeTweak('Stronghold', 'Stronghold'),
}
# generated-end orc_upgrades

# generated-begin elf_units: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ELF_UNITS: Final = {
    UnitType.PEASANT: UnitTweak('Gatherer', 'Mines gold, fells trees, builds and repairs', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.FOOTMAN: UnitTweak('Sentinel', 'Light swordsman in a line; quick on their feet', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.ARCHER: UnitTweak('Ranger', 'Shoots from five tiles; fragile up close', hp=0.95, damage=1.0, armor=0, range=1.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.SCOUT: UnitTweak('Outrider', 'Fleet deer rider who sees farthest of all', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.KNIGHT: UnitTweak('Stag Knight', 'Antlered shock cavalry, swift but light', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.CATAPULT: UnitTweak('Ballista', 'Living-wood siege engine: splash, ×1.5', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
    UnitType.CLERIC: UnitTweak('Druid', 'Tends wounded allies; stings weakly when none need tending', hp=0.95, damage=1.0, armor=0, range=0.0, speed=0.15, sight=2, build_time=1.0, formation=True),
}
# generated-end elf_units
# generated-begin elf_buildings: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ELF_BUILDINGS: Final = {
    BuildingType.TOWN_HALL: BuildingTweak('Moon Hall', 'Hall', 'Trains gatherers; takes gold and lumber', hp=1.0, armor=0),
    BuildingType.FARM: BuildingTweak('Orchard', 'Orchard', 'Feeds four units', hp=1.0, armor=0),
    BuildingType.BARRACKS: BuildingTweak('Warden Lodge', 'Lodge', 'Trains sentinels and rangers', hp=1.0, armor=0),
    BuildingType.TOWER: BuildingTweak('Watch Tree', 'Eyrie', 'Shoots at enemies six tiles away', hp=1.0, armor=0),
    BuildingType.LUMBER_MILL: BuildingTweak('Grove Mill', 'Mill', 'Takes lumber; arrows, Longbows and Regrowth', hp=1.0, armor=0),
    BuildingType.BLACKSMITH: BuildingTweak('Silversmith', 'Smith', 'Researches keener blades and silver mail', hp=1.0, armor=0),
    BuildingType.STABLES: BuildingTweak('Stag Pens', 'Pens', 'Trains outriders and stag knights', hp=1.0, armor=0),
    BuildingType.WORKSHOP: BuildingTweak('Siege Bower', 'Bower', 'Builds ballistae; improves siege engines', hp=1.0, armor=0),
    BuildingType.CHURCH: BuildingTweak('Moonwell', 'Moonwell', 'Trains druids', hp=1.0, armor=0),
}
# generated-end elf_buildings
# generated-begin elf_upgrades: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_ELF_UPGRADES: Final = {
    Upgrade.KEEP: UpgradeTweak('Moonspire', 'Moonspire'),
}
# generated-end elf_upgrades

# generated-begin dwarf_units: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_DWARF_UNITS: Final = {
    UnitType.PEASANT: UnitTweak('Miner', 'Mines gold, chops lumber, builds, repairs', hp=1.1, damage=1.0, armor=0, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.FOOTMAN: UnitTweak('Ironguard', 'Armoured axeman in a wall of round shields', hp=1.1, damage=1.0, armor=1, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.ARCHER: UnitTweak('Crossbowman', 'Shoots from four tiles; hardy for a shooter', hp=1.1, damage=1.0, armor=0, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.SCOUT: UnitTweak('Ram Rider', 'Fast ram rider; raids miners and crossbows', hp=1.1, damage=1.0, armor=0, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.KNIGHT: UnitTweak('Bear Rider', 'Armoured shock cavalry on a war bear', hp=1.1, damage=1.0, armor=1, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.CATAPULT: UnitTweak('Mortar', 'Iron mortar: wide splash, ×1.5 vs buildings', hp=1.1, damage=1.0, armor=0, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
    UnitType.CLERIC: UnitTweak('Runepriest', 'Heals wounded allies; strikes weakly when none need healing', hp=1.1, damage=1.0, armor=0, range=0.0, speed=-0.15, sight=0, build_time=1.0, formation=True),
}
# generated-end dwarf_units
# generated-begin dwarf_buildings: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_DWARF_BUILDINGS: Final = {
    BuildingType.TOWN_HALL: BuildingTweak('Deep Hold', 'Hold', 'Trains miners; takes gold and lumber', hp=1.25, armor=2),
    BuildingType.FARM: BuildingTweak('Brewhouse', 'Brewery', 'Feeds four units', hp=1.25, armor=2),
    BuildingType.BARRACKS: BuildingTweak('Guard Hall', 'Barracks', 'Trains ironguards and crossbowmen', hp=1.25, armor=2),
    BuildingType.TOWER: BuildingTweak('Bolt Tower', 'Tower', 'Shoots at enemies six tiles away', hp=1.25, armor=2),
    BuildingType.LUMBER_MILL: BuildingTweak('Timber Works', 'Timber', 'Takes lumber; researches better bolts', hp=1.25, armor=2),
    BuildingType.BLACKSMITH: BuildingTweak('Forge', 'Forge', 'Researches axes, plate and Deep Mining', hp=1.25, armor=2),
    BuildingType.STABLES: BuildingTweak('Beast Pens', 'Pens', 'Trains ram riders and bear riders', hp=1.25, armor=2),
    BuildingType.WORKSHOP: BuildingTweak('Engine Works', 'Engines', 'Builds mortars; siege and Blasting Powder', hp=1.25, armor=2),
    BuildingType.CHURCH: BuildingTweak('Rune Shrine', 'Shrine', 'Trains runepriests', hp=1.25, armor=2),
}
# generated-end dwarf_buildings
# generated-begin dwarf_upgrades: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
_DWARF_UPGRADES: Final = {
    Upgrade.KEEP: UpgradeTweak('Stonehold', 'Stonehold'),
}
# generated-end dwarf_upgrades

# generated-begin races: from warband/constants/races.toml — do not edit by hand; run tools/balance_tables.py
RACES: Final[dict[Race, RaceInfo]] = {
    Race.HUMAN: _race('Humans', 'Human', 'Drilled, balanced, and blessed with the fastest horses', 'Drill: every unit trains 15 % faster', (Upgrade.HORSES, Upgrade.BLESSING), _HUMAN_UNITS, _HUMAN_BUILDINGS, _HUMAN_UPGRADES),
    Race.ORC: _race('Orcs', 'Orcish', 'Tough, savage, and deadliest when bleeding', 'Frenzy: soldiers below half health deal +25 % damage', (Upgrade.BLOODLUST, Upgrade.PLUNDER), _ORC_UNITS, _ORC_BUILDINGS, _ORC_UPGRADES),
    Race.ELF: _race('Elves', 'Elven', 'Swift, far-sighted, and at home among the trees', 'Keen eyes: +2 sight for every unit, rangers shoot a tile farther', (Upgrade.LONGBOWS, Upgrade.REGROWTH), _ELF_UNITS, _ELF_BUILDINGS, _ELF_UPGRADES),
    Race.DWARF: _race('Dwarves', 'Dwarven', 'Slow, sturdy, and housed in stone', 'Stonework: buildings have +25 % hit points and +2 armour', (Upgrade.DEEP_MINING, Upgrade.BLASTING_POWDER), _DWARF_UNITS, _DWARF_BUILDINGS, _DWARF_UPGRADES),
}
# generated-end races

