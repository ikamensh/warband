"""The four races: what differs on top of the shared skeleton in :mod:`warband.rules`.

Every race fields the same seven roles from the same nine buildings with the
same hotkeys and costs, so the AI, the settlement planner, the saves and the
network protocol never care who is playing.  A race changes the names, a few
numbers per role (built into the :class:`UnitInfo` / :class:`BuildingInfo` a
unit or building reports), which two race arts it may research, and one
passive mechanic the simulation applies:

| race   | passive                                                  | arts                         |
|--------|----------------------------------------------------------|------------------------------|
| Humans | Drill: units train 15 % faster                            | Horse Breeding, Blessing     |
| Orcs   | Frenzy: +25 % damage below half health; tougher, slower to arm | Bloodlust, Plunder      |
| Elves  | Keen eyes: +2 sight, rangers shoot a tile farther; lighter | Longbows, Regrowth          |
| Dwarves| Stonework: buildings +25 % hp and +2 armour; sturdier, slower | Deep Mining, Blasting Powder |
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from warband.rules import BUILDINGS, UNITS, UPGRADES, BuildingInfo, BuildingType, Race, UnitInfo, UnitType, Upgrade


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


@dataclass(frozen=True)
class BuildingTweak:
    name: str
    card: str  # short enough for a command-card button
    summary: str
    hp: float = 1.0
    armor: int = 0


@dataclass(frozen=True)
class RaceInfo:
    name: str  # "Orcs"
    adjective: str  # "Orcish"
    tagline: str
    passive: str
    arts: tuple[Upgrade, ...]
    units: dict[UnitType, UnitInfo]
    buildings: dict[BuildingType, BuildingInfo]
    cards: dict[BuildingType, str]

    def upgrade_allowed(self, upgrade: Upgrade) -> bool:
        race = UPGRADES[upgrade].race
        return race is None or upgrade in self.arts


def _units(tweaks: dict[UnitType, UnitTweak]) -> dict[UnitType, UnitInfo]:
    out = {}
    for unit_type, base in UNITS.items():
        t = tweaks[unit_type]
        out[unit_type] = replace(
            base, name=t.name, summary=t.summary, hp=int(round(base.hp * t.hp)), damage=int(round(base.damage * t.damage)),
            armor=base.armor + t.armor, range=base.range + (t.range if base.ranged else 0.0), speed=round(base.speed + t.speed, 2),
            sight=base.sight + t.sight, build_time=round(base.build_time * t.build_time, 2),
        )
    return out


def _buildings(tweaks: dict[BuildingType, BuildingTweak]) -> dict[BuildingType, BuildingInfo]:
    out = {}
    for building_type, base in BUILDINGS.items():
        if building_type is BuildingType.GOLD_MINE:
            out[building_type] = base
            continue
        t = tweaks[building_type]
        out[building_type] = replace(base, name=t.name, summary=t.summary, hp=int(round(base.hp * t.hp)), armor=base.armor + t.armor)
    return out


def _race(name: str, adjective: str, tagline: str, passive: str, arts: tuple[Upgrade, ...],
          units: dict[UnitType, UnitTweak], buildings: dict[BuildingType, BuildingTweak]) -> RaceInfo:
    return RaceInfo(name, adjective, tagline, passive, arts, _units(units), _buildings(buildings),
                    {bt: t.card for bt, t in buildings.items()})


_HUMAN_UNITS = {
    UnitType.PEASANT: UnitTweak("Peasant", "Mines gold, chops lumber, builds, repairs", build_time=0.85),
    UnitType.FOOTMAN: UnitTweak("Footman", "Sturdy swordsman; the line of any army", build_time=0.85),
    UnitType.ARCHER: UnitTweak("Archer", "Shoots from four tiles; fragile up close", build_time=0.85),
    UnitType.SCOUT: UnitTweak("Scout", "Fast rider who sees far; raids workers", build_time=0.85),
    UnitType.KNIGHT: UnitTweak("Knight", "Fast, heavily armoured shock cavalry", build_time=0.85),
    UnitType.CATAPULT: UnitTweak("Catapult", "Siege engine: splash, ×1.5 vs buildings", build_time=0.85),
    UnitType.CLERIC: UnitTweak("Cleric", "Heals wounded allies nearby; cannot fight", build_time=0.85),
}
_HUMAN_BUILDINGS = {
    BuildingType.TOWN_HALL: BuildingTweak("Town Hall", "Hall", "Trains peasants; takes gold and lumber"),
    BuildingType.FARM: BuildingTweak("Farm", "Farm", "Feeds four units"),
    BuildingType.BARRACKS: BuildingTweak("Barracks", "Barracks", "Trains footmen and archers"),
    BuildingType.TOWER: BuildingTweak("Guard Tower", "Tower", "Shoots at enemies six tiles away"),
    BuildingType.LUMBER_MILL: BuildingTweak("Lumber Mill", "Mill", "Takes lumber; researches better arrows"),
    BuildingType.BLACKSMITH: BuildingTweak("Blacksmith", "Smith", "Researches sharper blades and plate armour"),
    BuildingType.STABLES: BuildingTweak("Stables", "Stables", "Trains scouts and knights; breeds horses"),
    BuildingType.WORKSHOP: BuildingTweak("Workshop", "Workshop", "Builds catapults; improves siege engines"),
    BuildingType.CHURCH: BuildingTweak("Church", "Church", "Trains clerics; blesses their healing"),
}

_ORC_UNITS = {
    UnitType.PEASANT: UnitTweak("Peon", "Digs gold, hacks lumber, builds and repairs", hp=1.15),
    UnitType.FOOTMAN: UnitTweak("Grunt", "Brutal axeman; hits harder as it bleeds", hp=1.15, damage=1.1, armor=-1, build_time=1.1),
    UnitType.ARCHER: UnitTweak("Axethrower", "Throws axes four tiles; a sturdy shooter", hp=1.15, build_time=1.1),
    UnitType.SCOUT: UnitTweak("Wolf Rider", "Fast wolf rider; hunts peons and throwers", hp=1.15, build_time=1.1),
    UnitType.KNIGHT: UnitTweak("Ogre", "Two-headed brute; no armour, all frenzy", hp=1.2, damage=1.1, armor=-2, build_time=1.1),
    UnitType.CATAPULT: UnitTweak("Catapult", "Skulled siege engine: splash, ×1.5 vs walls", hp=1.15, build_time=1.1),
    UnitType.CLERIC: UnitTweak("Shaman", "Mends wounded allies nearby; cannot fight", hp=1.15, build_time=1.1),
}
_ORC_BUILDINGS = {
    BuildingType.TOWN_HALL: BuildingTweak("Great Hall", "Hall", "Trains peons; takes gold and lumber"),
    BuildingType.FARM: BuildingTweak("Pig Farm", "Pig Farm", "Feeds four units"),
    BuildingType.BARRACKS: BuildingTweak("War Camp", "War Camp", "Trains grunts and axethrowers"),
    BuildingType.TOWER: BuildingTweak("Watch Tower", "Tower", "Hurls axes at enemies six tiles away"),
    BuildingType.LUMBER_MILL: BuildingTweak("Sawmill", "Sawmill", "Takes lumber; researches heavier axes"),
    BuildingType.BLACKSMITH: BuildingTweak("Forge", "Forge", "Researches blades, hide armour, Bloodlust"),
    BuildingType.STABLES: BuildingTweak("Kennels", "Kennels", "Trains wolf riders and ogres; Plunder"),
    BuildingType.WORKSHOP: BuildingTweak("Siege Yard", "Yard", "Builds catapults; improves siege engines"),
    BuildingType.CHURCH: BuildingTweak("Altar", "Altar", "Trains shamans"),
}

_ELF_UNITS = {
    UnitType.PEASANT: UnitTweak("Gatherer", "Mines gold, fells trees, builds and repairs", hp=0.95, speed=0.3, sight=2),
    UnitType.FOOTMAN: UnitTweak("Sentinel", "Light swordsman; quick on their feet", hp=0.95, speed=0.3, sight=2),
    UnitType.ARCHER: UnitTweak("Ranger", "Shoots from five tiles; fragile up close", hp=0.95, range=1.0, speed=0.3, sight=2),
    UnitType.SCOUT: UnitTweak("Outrider", "Fleet deer rider who sees farthest of all", hp=0.95, speed=0.3, sight=2),
    UnitType.KNIGHT: UnitTweak("Stag Knight", "Antlered shock cavalry, swift but light", hp=0.95, speed=0.3, sight=2),
    UnitType.CATAPULT: UnitTweak("Ballista", "Living-wood siege engine: splash, ×1.5", hp=0.95, speed=0.3, sight=2),
    UnitType.CLERIC: UnitTweak("Druid", "Heals wounded allies nearby; cannot fight", hp=0.95, speed=0.3, sight=2),
}
_ELF_BUILDINGS = {
    BuildingType.TOWN_HALL: BuildingTweak("Moon Hall", "Hall", "Trains gatherers; takes gold and lumber"),
    BuildingType.FARM: BuildingTweak("Orchard", "Orchard", "Feeds four units"),
    BuildingType.BARRACKS: BuildingTweak("Warden Lodge", "Lodge", "Trains sentinels and rangers"),
    BuildingType.TOWER: BuildingTweak("Watch Tree", "Eyrie", "Shoots at enemies six tiles away"),
    BuildingType.LUMBER_MILL: BuildingTweak("Grove Mill", "Mill", "Takes lumber; arrows, Longbows and Regrowth"),
    BuildingType.BLACKSMITH: BuildingTweak("Silversmith", "Smith", "Researches keener blades and silver mail"),
    BuildingType.STABLES: BuildingTweak("Stag Pens", "Pens", "Trains outriders and stag knights"),
    BuildingType.WORKSHOP: BuildingTweak("Siege Bower", "Bower", "Builds ballistae; improves siege engines"),
    BuildingType.CHURCH: BuildingTweak("Moonwell", "Moonwell", "Trains druids"),
}

_DWARF_UNITS = {
    UnitType.PEASANT: UnitTweak("Miner", "Mines gold, chops lumber, builds, repairs", hp=1.1, speed=-0.3),
    UnitType.FOOTMAN: UnitTweak("Ironguard", "Armoured axeman behind a round shield", hp=1.1, armor=1, speed=-0.3),
    UnitType.ARCHER: UnitTweak("Crossbowman", "Shoots from four tiles; hardy for a shooter", hp=1.1, speed=-0.3),
    UnitType.SCOUT: UnitTweak("Ram Rider", "Fast ram rider; raids miners and crossbows", hp=1.1, speed=-0.3),
    UnitType.KNIGHT: UnitTweak("Bear Rider", "Armoured shock cavalry on a war bear", hp=1.1, armor=1, speed=-0.3),
    UnitType.CATAPULT: UnitTweak("Mortar", "Iron mortar: wide splash, ×1.5 vs buildings", hp=1.1, speed=-0.3),
    UnitType.CLERIC: UnitTweak("Runepriest", "Heals wounded allies nearby; cannot fight", hp=1.1, speed=-0.3),
}
_DWARF_BUILDINGS = {
    BuildingType.TOWN_HALL: BuildingTweak("Deep Hold", "Hold", "Trains miners; takes gold and lumber", hp=1.25, armor=2),
    BuildingType.FARM: BuildingTweak("Brewhouse", "Brewery", "Feeds four units", hp=1.25, armor=2),
    BuildingType.BARRACKS: BuildingTweak("Guard Hall", "Barracks", "Trains ironguards and crossbowmen", hp=1.25, armor=2),
    BuildingType.TOWER: BuildingTweak("Bolt Tower", "Tower", "Shoots at enemies six tiles away", hp=1.25, armor=2),
    BuildingType.LUMBER_MILL: BuildingTweak("Timber Works", "Timber", "Takes lumber; researches better bolts", hp=1.25, armor=2),
    BuildingType.BLACKSMITH: BuildingTweak("Forge", "Forge", "Researches axes, plate and Deep Mining", hp=1.25, armor=2),
    BuildingType.STABLES: BuildingTweak("Beast Pens", "Pens", "Trains ram riders and bear riders", hp=1.25, armor=2),
    BuildingType.WORKSHOP: BuildingTweak("Engine Works", "Engines", "Builds mortars; siege and Blasting Powder", hp=1.25, armor=2),
    BuildingType.CHURCH: BuildingTweak("Rune Shrine", "Shrine", "Trains runepriests", hp=1.25, armor=2),
}

RACES: dict[Race, RaceInfo] = {
    Race.HUMAN: _race("Humans", "Human", "Drilled, balanced, and blessed with the fastest horses",
                      "Drill: every unit trains 15 % faster", (Upgrade.HORSES, Upgrade.BLESSING), _HUMAN_UNITS, _HUMAN_BUILDINGS),
    Race.ORC: _race("Orcs", "Orcish", "Tough, savage, and deadliest when bleeding",
                    "Frenzy: soldiers below half health deal +25 % damage", (Upgrade.BLOODLUST, Upgrade.PLUNDER), _ORC_UNITS, _ORC_BUILDINGS),
    Race.ELF: _race("Elves", "Elven", "Swift, far-sighted, and at home among the trees",
                    "Keen eyes: +2 sight for every unit, rangers shoot a tile farther", (Upgrade.LONGBOWS, Upgrade.REGROWTH), _ELF_UNITS, _ELF_BUILDINGS),
    Race.DWARF: _race("Dwarves", "Dwarven", "Slow, sturdy, and housed in stone",
                      "Stonework: buildings have +25 % hit points and +2 armour", (Upgrade.DEEP_MINING, Upgrade.BLASTING_POWDER), _DWARF_UNITS,
                      _DWARF_BUILDINGS),
}

