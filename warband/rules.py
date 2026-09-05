"""Static game data.  Nothing here mutates.

Distances are in tiles, times in seconds of simulation time.  A unit's
``range`` is the largest gap between its edge and the target's edge at
which it can strike; melee units must all but touch.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    KNIGHT = "knight"


class BuildingType(Enum):
    TOWN_HALL = "town_hall"
    FARM = "farm"
    BARRACKS = "barracks"
    TOWER = "tower"
    GOLD_MINE = "gold_mine"


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

    @property
    def melee(self) -> bool:
        return self.range < 1


MELEE = 0.45  # reach of a melee unit: it strikes from the next tile over, diagonals included

UNITS: dict[UnitType, UnitInfo] = {
    UnitType.PEASANT: UnitInfo("Peasant", Cost(400), 30, 3, 0, MELEE, 1.0, 2.4, 4, 12.0, BuildingType.TOWN_HALL, "p",
                               "Mines gold, chops lumber, builds"),
    UnitType.FOOTMAN: UnitInfo("Footman", Cost(600), 60, 7, 2, MELEE, 1.0, 2.4, 5, 15.0, BuildingType.BARRACKS, "f",
                               "Sturdy swordsman"),
    UnitType.ARCHER: UnitInfo("Archer", Cost(500, 50), 40, 5, 0, 4.0, 1.3, 2.4, 6, 14.0, BuildingType.BARRACKS, "a",
                              "Shoots from four tiles away"),
    UnitType.KNIGHT: UnitInfo("Knight", Cost(800, 100), 90, 10, 4, MELEE, 1.0, 3.4, 5, 20.0, BuildingType.BARRACKS, "k",
                              "Fast, heavily armoured"),
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
    requires: BuildingType | None = None
    damage: int = 0
    range: float = 0.0
    cooldown: float = 1.0


BUILDINGS: dict[BuildingType, BuildingInfo] = {
    BuildingType.TOWN_HALL: BuildingInfo("Town Hall", Cost(1200, 800), 1200, 3, 3, 60.0, 6, 5, "h",
                                         "Trains peasants; gold and lumber are delivered here", trains=(UnitType.PEASANT,)),
    BuildingType.FARM: BuildingInfo("Farm", Cost(500, 250), 400, 2, 2, 25.0, 3, 4, "f", "Feeds four units"),
    BuildingType.BARRACKS: BuildingInfo("Barracks", Cost(700, 450), 800, 3, 3, 40.0, 5, 0, "b", "Trains footmen, archers and knights",
                                        trains=(UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT), requires=BuildingType.TOWN_HALL),
    BuildingType.TOWER: BuildingInfo("Guard Tower", Cost(500, 200), 400, 3, 2, 35.0, 8, 0, "t", "Shoots at enemies six tiles away",
                                     requires=BuildingType.BARRACKS, damage=8, range=6.0, cooldown=1.5),
    BuildingType.GOLD_MINE: BuildingInfo("Gold Mine", Cost(0), 0, 0, 3, 0.0, 0, 0, "", "Peasants mine gold here"),
}

GOLD_PER_TRIP = 100
LUMBER_PER_TRIP = 100
MINE_TIME = 3.0  # seconds a peasant spends inside a mine per trip
CHOP_TIME = 5.0  # seconds to fell a tree
MINE_GOLD = 12_000
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
