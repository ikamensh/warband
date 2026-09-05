"""Static game data.  Nothing here mutates.

Distances are in tiles, times in seconds of simulation time.  A unit's
``range`` is the largest gap between its edge and the target's edge at
which it can strike (or heal); melee units must all but touch.

Balance in one table (base values; upgrades in :data:`UPGRADES`):

| unit     | cost      | hp | dmg | armor | range | speed | role, counters                          |
|----------|-----------|----|-----|-------|-------|-------|-----------------------------------------|
| peasant  | 400       | 30 | 3   | 0     | melee | 2.4   | economy; anything kills it              |
| footman  | 600       | 60 | 7   | 2     | melee | 2.4   | line; beats archers, loses to knights   |
| archer   | 500+50    | 40 | 5   | 0     | 4     | 2.4   | ranged; beats footmen in numbers, dies to scouts/knights |
| scout    | 350       | 35 | 4   | 0     | melee | 4.2   | fast raider, sight 8; kills archers, peasants; loses to footmen |
| knight   | 800+100   | 90 | 10  | 4     | melee | 3.4   | shock; beats everything at cost; catapults and mass archers wear it down |
| catapult | 900+300   | 80 | 30  | 0     | 7     | 1.6   | siege, splash, ×1.5 vs buildings; helpless up close |
| cleric   | 700+50    | 40 | —   | 0     | 3     | 2.4   | heals 6 hp/s; no attack; protect it     |
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from enum import Enum


class Terrain(Enum):
    GRASS = "grass"
    WATER = "water"
    TREES = "trees"
    ROCK = "rock"


class Resource(Enum):
    GOLD = "gold"
    LUMBER = "lumber"


@dataclass(frozen=True)
class Cost:
    gold: int
    lumber: int = 0

    def __str__(self) -> str:
        return f"{self.gold} gold" + (f", {self.lumber} lumber" if self.lumber else "")


class UnitType(Enum):
    PEASANT = "peasant"
    FOOTMAN = "footman"
    ARCHER = "archer"
    SCOUT = "scout"
    KNIGHT = "knight"
    CATAPULT = "catapult"
    CLERIC = "cleric"


class BuildingType(Enum):
    TOWN_HALL = "town_hall"
    FARM = "farm"
    BARRACKS = "barracks"
    TOWER = "tower"
    LUMBER_MILL = "lumber_mill"
    BLACKSMITH = "blacksmith"
    STABLES = "stables"
    WORKSHOP = "workshop"
    CHURCH = "church"
    GOLD_MINE = "gold_mine"


class Upgrade(Enum):
    BLADES_1 = "blades_1"
    BLADES_2 = "blades_2"
    ARMOR_1 = "armor_1"
    ARMOR_2 = "armor_2"
    ARROWS_1 = "arrows_1"
    ARROWS_2 = "arrows_2"
    HORSES = "horses"
    SIEGE = "siege"
    BLESSING = "blessing"


@dataclass(frozen=True)
class UnitInfo:
    name: str
    cost: Cost
    hp: int
    damage: int
    armor: int
    range: float
    cooldown: float
    speed: float
    sight: int
    build_time: float
    trained_at: BuildingType
    hotkey: str
    summary: str
    heal: int = 0  # hit points restored per second; a healer has no attack
    splash: float = 0.0  # radius around the target that also takes damage
    siege: float = 1.0  # damage multiplier against buildings
    mounted: bool = False  # benefits from HORSES

    @property
    def melee(self) -> bool:
        return self.range < 1 and self.damage > 0

    @property
    def ranged(self) -> bool:
        return self.range >= 1 and self.damage > 0


MELEE = 0.45  # reach of a melee unit: it strikes from the next tile over, diagonals included

UNITS: dict[UnitType, UnitInfo] = {
    UnitType.PEASANT: UnitInfo("Peasant", Cost(400), 30, 3, 0, MELEE, 1.0, 2.4, 4, 12.0, BuildingType.TOWN_HALL, "p",
                               "Mines gold, chops lumber, builds"),
    UnitType.FOOTMAN: UnitInfo("Footman", Cost(600), 60, 7, 2, MELEE, 1.0, 2.4, 5, 15.0, BuildingType.BARRACKS, "f",
                               "Sturdy swordsman; the line of any army"),
    UnitType.ARCHER: UnitInfo("Archer", Cost(500, 50), 40, 5, 0, 4.0, 1.3, 2.4, 6, 14.0, BuildingType.BARRACKS, "a",
                              "Shoots from four tiles away; fragile up close"),
    UnitType.SCOUT: UnitInfo("Scout", Cost(350), 35, 4, 0, MELEE, 0.8, 4.2, 8, 10.0, BuildingType.STABLES, "s",
                             "Fast rider who sees far; raids peasants and archers", mounted=True),
    UnitType.KNIGHT: UnitInfo("Knight", Cost(800, 100), 90, 10, 4, MELEE, 1.0, 3.4, 5, 20.0, BuildingType.STABLES, "k",
                              "Fast, heavily armoured shock cavalry", mounted=True),
    UnitType.CATAPULT: UnitInfo("Catapult", Cost(900, 300), 80, 30, 0, 7.0, 3.0, 1.6, 6, 30.0, BuildingType.WORKSHOP, "c",
                                "Slow siege engine: splash damage, ×1.5 against buildings", splash=1.2, siege=1.5),
    UnitType.CLERIC: UnitInfo("Cleric", Cost(700, 50), 40, 0, 0, 3.0, 1.0, 2.4, 5, 20.0, BuildingType.CHURCH, "l",
                              "Heals wounded allies nearby; cannot fight", heal=6),
}


@dataclass(frozen=True)
class BuildingInfo:
    name: str
    cost: Cost
    hp: int
    armor: int
    size: int
    build_time: float
    sight: int
    supply: int
    hotkey: str
    summary: str
    trains: tuple[UnitType, ...] = ()
    researches: tuple[Upgrade, ...] = ()
    requires: BuildingType | None = None
    deposits: frozenset[Resource] = frozenset()
    damage: int = 0
    range: float = 0.0
    cooldown: float = 1.0


BUILDINGS: dict[BuildingType, BuildingInfo] = {
    BuildingType.TOWN_HALL: BuildingInfo("Town Hall", Cost(1200, 800), 1200, 3, 3, 60.0, 6, 5, "h",
                                         "Trains peasants; gold and lumber are delivered here", trains=(UnitType.PEASANT,),
                                         deposits=frozenset({Resource.GOLD, Resource.LUMBER})),
    BuildingType.FARM: BuildingInfo("Farm", Cost(500, 250), 400, 2, 2, 25.0, 3, 4, "f", "Feeds four units"),
    BuildingType.BARRACKS: BuildingInfo("Barracks", Cost(700, 450), 800, 3, 3, 40.0, 5, 0, "b", "Trains footmen and archers",
                                        trains=(UnitType.FOOTMAN, UnitType.ARCHER), requires=BuildingType.TOWN_HALL),
    BuildingType.TOWER: BuildingInfo("Guard Tower", Cost(500, 200), 400, 3, 2, 35.0, 8, 0, "t", "Shoots at enemies six tiles away",
                                     requires=BuildingType.BARRACKS, damage=8, range=6.0, cooldown=1.5),
    BuildingType.LUMBER_MILL: BuildingInfo("Lumber Mill", Cost(600, 450), 600, 2, 3, 35.0, 4, 0, "m",
                                           "Lumber is delivered here; researches better arrows",
                                           researches=(Upgrade.ARROWS_1, Upgrade.ARROWS_2), requires=BuildingType.TOWN_HALL,
                                           deposits=frozenset({Resource.LUMBER})),
    BuildingType.BLACKSMITH: BuildingInfo("Blacksmith", Cost(800, 450), 600, 3, 3, 40.0, 4, 0, "k",
                                          "Researches sharper blades and plate armour",
                                          researches=(Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARMOR_1, Upgrade.ARMOR_2), requires=BuildingType.BARRACKS),
    BuildingType.STABLES: BuildingInfo("Stables", Cost(1000, 300), 700, 3, 3, 45.0, 4, 0, "s",
                                       "Trains scouts and knights; breeds faster horses",
                                       trains=(UnitType.SCOUT, UnitType.KNIGHT), researches=(Upgrade.HORSES,), requires=BuildingType.BARRACKS),
    BuildingType.WORKSHOP: BuildingInfo("Workshop", Cost(900, 500), 600, 3, 3, 45.0, 4, 0, "w",
                                        "Builds catapults; improves siege engines",
                                        trains=(UnitType.CATAPULT,), researches=(Upgrade.SIEGE,), requires=BuildingType.BLACKSMITH),
    BuildingType.CHURCH: BuildingInfo("Church", Cost(900, 400), 600, 3, 3, 45.0, 5, 0, "c",
                                      "Trains clerics; blesses their healing",
                                      trains=(UnitType.CLERIC,), researches=(Upgrade.BLESSING,), requires=BuildingType.BARRACKS),
    BuildingType.GOLD_MINE: BuildingInfo("Gold Mine", Cost(0), 0, 0, 3, 0.0, 0, 0, "", "Peasants mine gold here"),
}


@dataclass(frozen=True)
class UpgradeInfo:
    name: str
    cost: Cost
    time: float
    hotkey: str
    summary: str
    requires: Upgrade | None = None


UPGRADES: dict[Upgrade, UpgradeInfo] = {
    Upgrade.BLADES_1: UpgradeInfo("Sharpened Blades", Cost(500, 100), 40.0, "b", "+2 damage for melee units"),
    Upgrade.BLADES_2: UpgradeInfo("Tempered Blades", Cost(1500, 300), 60.0, "b", "+2 more damage for melee units", requires=Upgrade.BLADES_1),
    Upgrade.ARMOR_1: UpgradeInfo("Plate Armour", Cost(300, 300), 40.0, "a", "+1 armour for soldiers"),
    Upgrade.ARMOR_2: UpgradeInfo("Heavy Plate", Cost(900, 500), 60.0, "a", "+1 more armour for soldiers", requires=Upgrade.ARMOR_1),
    Upgrade.ARROWS_1: UpgradeInfo("Bodkin Arrows", Cost(300, 300), 40.0, "r", "+2 damage for archers and towers"),
    Upgrade.ARROWS_2: UpgradeInfo("Broadhead Arrows", Cost(900, 500), 60.0, "r", "+2 more damage for archers and towers", requires=Upgrade.ARROWS_1),
    Upgrade.HORSES: UpgradeInfo("Horse Breeding", Cost(900, 300), 50.0, "h", "+0.8 speed for scouts and knights"),
    Upgrade.SIEGE: UpgradeInfo("Siege Engineering", Cost(1000, 500), 60.0, "e", "+1 range and +25 % damage for catapults"),
    Upgrade.BLESSING: UpgradeInfo("Blessing", Cost(800, 400), 50.0, "l", "Clerics heal half again as fast"),
}

BLADES_BONUS = 2
ARMOR_BONUS = 1
ARROWS_BONUS = 2
HORSES_BONUS = 0.8
SIEGE_RANGE_BONUS = 1.0
SIEGE_DAMAGE_BONUS = 1.25
BLESSING_BONUS = 1.5
SPLASH_FRACTION = 0.6  # share of the damage dealt to others inside the splash radius

GOLD_PER_TRIP = 100
LUMBER_PER_TRIP = 100
MINE_TIME = 5.0  # seconds a peasant spends inside a mine per trip
CHOP_TIME = 5.0  # seconds to fell a tree
REPAIR_RATE = 8.0  # hit points a peasant mends per second
REPAIR_CHUNK = 10  # hit points paid for at a time while repairing
REPAIR_COST = 0.5  # share of a building's price that mending all of its hit points costs


def repair_cost(info: BuildingInfo, amount: int, max_hp: int) -> Cost:
    """What mending *amount* of a building's *max_hp* hit points costs: REPAIR_COST of its price, pro rata."""
    share = REPAIR_COST * amount / max_hp
    return Cost(math.ceil(info.cost.gold * share), math.ceil(info.cost.lumber * share))
MINE_GOLD = 50_000  # a base mine; expansion mines hold EXPANSION_GOLD
EXPANSION_GOLD = 30_000
STARTING_GOLD = 1000
STARTING_LUMBER = 500
UNIT_RADIUS = 0.35
LEASH = 6.0  # how far an idle unit chases before it walks home
UNDER_ATTACK_COOLDOWN = 20.0
SIM_DT = 0.05  # the simulation runs at 20 Hz regardless of the frame rate
VISION_EVERY = 4  # ticks between fog recomputations
HIT_VARIANCE = 0.25  # damage rolls between 75 % and 125 % of the listed value


@dataclass(frozen=True)
class PlayerInfo:
    name: str
    color: tuple[int, int, int]


PLAYERS: list[PlayerInfo] = [
    PlayerInfo("Azure", (70, 130, 255)),
    PlayerInfo("Crimson", (225, 70, 60)),
    PlayerInfo("Viridian", (80, 190, 110)),
    PlayerInfo("Amber", (245, 190, 60)),
]


class Difficulty(Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class MapTheme(Enum):
    SUMMER = "summer"
    WINTER = "winter"
    WASTELAND = "wasteland"
