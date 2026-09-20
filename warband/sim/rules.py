"""Static game data.  Nothing here mutates.

Distances are in tiles, times in seconds of simulation time.  A unit's
``range`` is the largest gap between its edge and the target's edge at
which it can strike (or heal); melee units must all but touch.

A blow takes time: the unit pivots to face its target at its ``turn`` rate,
stands through a ``windup`` (the sword drawn back, the bow bent, the
catapult arm cranked down), lands the blow, and waits ``cooldown`` before
the next wind-up may start.  Shots are projectiles: an arrow follows its
mark and strikes when it arrives, a siege stone comes down on the ground it
was fired at, on whoever stands there by then.

Balance in one table (base values; upgrades in :data:`UPGRADES`):

| unit     | cost      | hp | dmg | armor | range | wind-up + cooldown | turn  | speed | role, counters                          |
|----------|-----------|----|-----|-------|-------|--------------------|-------|-------|-----------------------------------------|
| peasant  | 400       | 30 | 3   | 0     | melee | 0.25 + 1.0         | 360°/s| 2.4   | economy; anything kills it              |
| footman  | 600       | 60 | 7   | 3     | melee | 0.3 + 1.0          | 360°/s| 2.0   | line: +1 armour per footman at its side, marches in formation; beats archers, loses to knights |
| archer   | 500+50    | 40 | 6   | 0     | 4     | 0.35 + 1.3         | 360°/s| 2.4   | ranged; the answer to armour, dies to scouts/knights |
| scout    | 350       | 35 | 4   | 0     | melee | 0.25 + 0.8         | 450°/s| 4.2   | fast raider, sight 8; kills archers, peasants; loses to footmen |
| knight   | 900+100   | 90 | 10  | 4     | melee | 0.35 + 1.0         | 270°/s| 3.4   | shock; beats everything at cost; catapults and mass archers wear it down |
| catapult | 700+200   |100 | 36  | 0     | 2..7  | 0.8 + 3.0          | 150°/s| 1.6   | siege: stones land where aimed, splash friend and foe, ×1.5 vs buildings; helpless inside two tiles |
| cleric   | 700+50    | 40 | 3   | 0     | 3     | 0.5 + 2.0          | 360°/s| 2.4   | heals 15 a cast (6 hp/s); a weak blow only when no one needs healing; protect it |

Armour classes and attack types (WB-049, :data:`DAMAGE_FACTORS`): peasants, clerics and catapults are unarmoured,
archers and scouts light, footmen and knights heavy, buildings fortified; archers pierce, catapults siege, the rest
and towers strike normally.  Piercing lands ×1.5 on the unarmoured, siege ×1.5 on buildings, everything else ×1.

A building's armour is :data:`BUILDINGS`' once it stands; a frame still going up wears none.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from enum import Enum
from typing import Final


class IdentityEnum(Enum):
    """An enum whose members hash by identity.  The rule tables are keyed by these in the hottest
    loops, and Enum's own hash goes through a Python frame and the member's name."""

    __hash__ = object.__hash__


class Terrain(IdentityEnum):
    GRASS = "grass"
    WATER = "water"
    TREES = "trees"
    ROCK = "rock"


class Resource(IdentityEnum):
    GOLD = "gold"
    LUMBER = "lumber"


@dataclass(frozen=True)
class Cost:
    gold: int
    lumber: int = 0

    def __str__(self) -> str:
        return f"{self.gold} gold" + (f", {self.lumber} lumber" if self.lumber else "")


class UnitType(IdentityEnum):
    PEASANT = "peasant"
    FOOTMAN = "footman"
    ARCHER = "archer"
    SCOUT = "scout"
    KNIGHT = "knight"
    CATAPULT = "catapult"
    CLERIC = "cleric"


class BuildingType(IdentityEnum):
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


class Race(IdentityEnum):
    """Who a player leads.  The tech skeleton (unit roles, buildings, hotkeys, costs) is shared;
    :mod:`warband.sim.races` gives each race its names, numbers, upgrades and mechanics."""

    HUMAN = "human"
    ORC = "orc"
    ELF = "elf"
    DWARF = "dwarf"


class Upgrade(IdentityEnum):
    KEEP = "keep"  # the hall itself: the gate in front of the upper rungs of the stat ladders
    BLADES_1 = "blades_1"
    BLADES_2 = "blades_2"
    BLADES_3 = "blades_3"
    ARMOR_1 = "armor_1"
    ARMOR_2 = "armor_2"
    ARROWS_1 = "arrows_1"
    ARROWS_2 = "arrows_2"
    ARROWS_3 = "arrows_3"
    SIEGE = "siege"
    MARKSMANSHIP = "marksmanship"
    # Race arts: only that race researches them.
    HORSES = "horses"
    BLESSING = "blessing"
    BLOODLUST = "bloodlust"
    PLUNDER = "plunder"
    LONGBOWS = "longbows"
    REGROWTH = "regrowth"
    DEEP_MINING = "deep_mining"
    BLASTING_POWDER = "blasting_powder"


class ArmorClass(IdentityEnum):
    """What a unit or building wears, for :data:`DAMAGE_FACTORS`."""
    UNARMORED = "unarmoured"
    LIGHT = "light"
    HEAVY = "heavy"
    FORTIFIED = "fortified"  # every building


class AttackType(IdentityEnum):
    """What kind of blow a unit or building strikes, for :data:`DAMAGE_FACTORS`."""
    NORMAL = "normal"
    PIERCING = "piercing"  # arrows, thrown axes, bolts
    SIEGE = "siege"  # stones


@dataclass(frozen=True)
class UnitInfo:
    name: str
    cost: Cost
    hp: int
    damage: int
    armor: int
    range: float
    cooldown: float  # seconds after a blow before the next wind-up may start
    speed: float
    sight: int
    build_time: float
    trained_at: BuildingType
    hotkey: str
    summary: str
    #: Tiles from its centre the unit's body fills: what it may not be pushed into, and what a blow, a
    #: stone's splash and a click all measure from.  A little under the drawn figure's own footprint;
    #: the numbers and how they were measured are in ``docs/unit-motion.md`` part 7.  The races draw the
    #: same role at different sizes but share one body, and a jittered rulebook never moves a radius, so
    #: :data:`MAX_UNIT_RADIUS` holds for the whole match.
    radius: float
    heal: int = 0  # hit points one cast restores, a wind-up and a cooldown apart; a healer's own blow is weak and its last resort
    splash: float = 0.0  # radius around where a stone lands that also takes damage; a siege engine
    attack: AttackType = AttackType.NORMAL
    armor_class: ArmorClass = ArmorClass.LIGHT
    formation: bool = False  # marches in a line and wears FORMATION_ARMOR more for each such neighbour beside it
    mounted: bool = False  # benefits from HORSES
    windup: float = 0.0  # seconds from the decision to strike to the blow landing; the unit stands committed meanwhile
    turn: float = math.radians(360)  # radians per second the unit pivots
    min_range: float = 0.0  # nothing closer than this gap can be struck (a catapult cannot drop a stone at its own wheels)

    @property
    def melee(self) -> bool:
        return self.range < 1 and self.damage > 0

    @property
    def period(self) -> float:
        """Seconds from one blow to the next at best: the wind-up plus the cooldown."""
        return self.windup + self.cooldown

    @property
    def ranged(self) -> bool:
        """A shooter: Arrows and Longbows are its upgrades (a healer's blow is not)."""
        return self.range >= 1 and self.damage > 0 and not self.heal

    @property
    def soldier(self) -> bool:
        """It fights for a living: a worker's or a healer's blow does not make it one (the unit may still be a worker)."""
        return self.damage > 0 and not self.heal


MELEE: Final = 0.45  # reach of a melee unit: it strikes from the next tile over, diagonals included

UNITS: Final[dict[UnitType, UnitInfo]] = {
    UnitType.PEASANT: UnitInfo("Peasant", Cost(400), 30, 3, 0, MELEE, 1.0, 2.4, 4, 12.0, BuildingType.TOWN_HALL, "p",
                               "Mines gold, chops lumber, builds and repairs", radius=0.36, windup=0.25, armor_class=ArmorClass.UNARMORED),
    UnitType.FOOTMAN: UnitInfo("Footman", Cost(600), 60, 7, 3, MELEE, 1.0, 2.0, 5, 15.0, BuildingType.BARRACKS, "f",
                               "Slow shield-wall swordsman; tougher with a comrade at each side", radius=0.42, windup=0.3,
                               armor_class=ArmorClass.HEAVY, formation=True),
    UnitType.ARCHER: UnitInfo("Archer", Cost(500, 50), 40, 6, 0, 4.0, 1.3, 2.4, 6, 14.0, BuildingType.BARRACKS, "a",
                              "Shoots from four tiles away; fragile up close", radius=0.42, windup=0.35, attack=AttackType.PIERCING),
    UnitType.SCOUT: UnitInfo("Scout", Cost(350), 35, 4, 0, MELEE, 0.8, 4.2, 8, 10.0, BuildingType.STABLES, "s",
                             "Fast rider who sees far; raids peasants and archers", radius=0.48, mounted=True, windup=0.25, turn=math.radians(450)),
    UnitType.KNIGHT: UnitInfo("Knight", Cost(900, 100), 90, 10, 4, MELEE, 1.0, 3.4, 5, 20.0, BuildingType.STABLES, "k",
                              "Fast, heavily armoured shock cavalry", radius=0.56, mounted=True, windup=0.35, turn=math.radians(270),
                              armor_class=ArmorClass.HEAVY),
    UnitType.CATAPULT: UnitInfo("Catapult", Cost(700, 200), 100, 36, 0, 7.0, 3.0, 1.6, 6, 30.0, BuildingType.WORKSHOP, "c",
                                "Slow siege engine: stones land where aimed, splash friend and foe, ×1.5 against buildings",
                                radius=0.62, splash=1.2, windup=0.8, turn=math.radians(150), min_range=2.0, attack=AttackType.SIEGE,
                                armor_class=ArmorClass.UNARMORED),
    UnitType.CLERIC: UnitInfo("Cleric", Cost(700, 50), 40, 3, 0, 3.0, 2.0, 2.4, 5, 20.0, BuildingType.CHURCH, "h",  # H for healer: L is Blessing at the church
                              "Heals a wounded ally 15 at a cast; a weak blow when no one needs it", radius=0.38, heal=15, windup=0.5,
                              armor_class=ArmorClass.UNARMORED),
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


BUILDINGS: Final[dict[BuildingType, BuildingInfo]] = {
    BuildingType.TOWN_HALL: BuildingInfo("Town Hall", Cost(1200, 800), 1200, 3, 3, 60.0, 6, 5, "h",
                                         "Trains peasants; gold and lumber are delivered here; raises the Keep",
                                         trains=(UnitType.PEASANT,), researches=(Upgrade.KEEP,),
                                         deposits=frozenset({Resource.GOLD, Resource.LUMBER})),
    BuildingType.FARM: BuildingInfo("Farm", Cost(500, 250), 400, 2, 2, 25.0, 3, 4, "f", "Feeds four units"),
    BuildingType.BARRACKS: BuildingInfo("Barracks", Cost(700, 450), 800, 3, 3, 40.0, 5, 0, "b", "Trains footmen and archers",
                                        trains=(UnitType.FOOTMAN, UnitType.ARCHER), requires=BuildingType.TOWN_HALL),
    BuildingType.TOWER: BuildingInfo("Guard Tower", Cost(700, 250), 400, 3, 2, 35.0, 8, 0, "t", "Shoots at enemies six tiles away",
                                     requires=BuildingType.BARRACKS, damage=8, range=6.0, cooldown=1.5),
    BuildingType.LUMBER_MILL: BuildingInfo("Lumber Mill", Cost(600, 450), 600, 2, 3, 35.0, 4, 0, "m",
                                           "Lumber is delivered here; researches better arrows",
                                           researches=(Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.ARROWS_3, Upgrade.MARKSMANSHIP,
                                                       Upgrade.LONGBOWS, Upgrade.REGROWTH),
                                           requires=BuildingType.TOWN_HALL, deposits=frozenset({Resource.LUMBER})),
    BuildingType.BLACKSMITH: BuildingInfo("Blacksmith", Cost(800, 450), 600, 3, 3, 40.0, 4, 0, "k",
                                          "Researches sharper blades and plate armour",
                                          researches=(Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3, Upgrade.ARMOR_1, Upgrade.ARMOR_2,
                                                      Upgrade.BLOODLUST, Upgrade.DEEP_MINING),
                                          requires=BuildingType.BARRACKS),
    BuildingType.STABLES: BuildingInfo("Stables", Cost(1000, 300), 700, 3, 3, 45.0, 4, 0, "s",
                                       "Trains scouts and knights; breeds faster horses",
                                       trains=(UnitType.SCOUT, UnitType.KNIGHT), researches=(Upgrade.HORSES, Upgrade.PLUNDER),
                                       requires=BuildingType.BARRACKS),
    BuildingType.WORKSHOP: BuildingInfo("Workshop", Cost(700, 350), 600, 3, 3, 45.0, 4, 0, "w",
                                        "Builds catapults; improves siege engines",
                                        trains=(UnitType.CATAPULT,), researches=(Upgrade.SIEGE, Upgrade.BLASTING_POWDER), requires=BuildingType.BLACKSMITH),
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
    card: str  # short enough for a command-card button (each race's own are in :mod:`warband.sim.races`)
    summary: str
    requires: tuple[Upgrade, ...] = ()  # every upgrade this one waits for: its own lower tier, the Keep, or both
    race: Race | None = None  # a race art: nobody else can research it


UPGRADES: Final[dict[Upgrade, UpgradeInfo]] = {
    Upgrade.KEEP: UpgradeInfo("Keep", Cost(1500, 800), 90.0, "k", "Keep", "Raises the hall, opening the upper tiers"),
    Upgrade.BLADES_1: UpgradeInfo("Sharpened Blades", Cost(500, 100), 40.0, "b", "Blades I", "+2 damage for melee units"),
    Upgrade.BLADES_2: UpgradeInfo("Tempered Blades", Cost(1500, 300), 60.0, "b", "Blades II", "+2 more damage for melee units",
                                  requires=(Upgrade.BLADES_1, Upgrade.KEEP)),
    Upgrade.BLADES_3: UpgradeInfo("Masterwork Blades", Cost(3000, 600), 120.0, "b", "Blades III", "+4 more damage for melee units",
                                  requires=(Upgrade.BLADES_2, Upgrade.KEEP)),
    Upgrade.ARMOR_1: UpgradeInfo("Plate Armour", Cost(300, 300), 40.0, "a", "Armour I", "+1 armour for soldiers"),
    Upgrade.ARMOR_2: UpgradeInfo("Heavy Plate", Cost(900, 500), 60.0, "a", "Armour II", "+1 more armour for soldiers",
                                 requires=(Upgrade.ARMOR_1, Upgrade.KEEP)),
    Upgrade.ARROWS_1: UpgradeInfo("Bodkin Arrows", Cost(300, 300), 40.0, "r", "Arrows I", "+2 damage for archers and towers"),
    Upgrade.ARROWS_2: UpgradeInfo("Broadhead Arrows", Cost(900, 500), 60.0, "r", "Arrows II", "+2 more damage for archers and towers",
                                  requires=(Upgrade.ARROWS_1, Upgrade.KEEP)),
    Upgrade.ARROWS_3: UpgradeInfo("Masterwork Arrows", Cost(1800, 1000), 120.0, "r", "Arrows III",
                                  "+4 more damage for archers and towers", requires=(Upgrade.ARROWS_2, Upgrade.KEEP)),
    Upgrade.SIEGE: UpgradeInfo("Siege Engineering", Cost(1000, 500), 60.0, "e", "Siege", "+1 range and +25 % damage for siege engines"),
    Upgrade.MARKSMANSHIP: UpgradeInfo("Marksmanship", Cost(600, 300), 45.0, "m", "Marksmen",
                                      "Shooters pick the mark in reach they fell soonest and waste no arrow on the dying"),
    Upgrade.HORSES: UpgradeInfo("Horse Breeding", Cost(900, 300), 50.0, "h", "Horses", "+0.8 speed for scouts and knights", race=Race.HUMAN),
    Upgrade.BLESSING: UpgradeInfo("Blessing", Cost(800, 400), 50.0, "l", "Blessing", "Clerics heal half again as fast", race=Race.HUMAN),
    Upgrade.BLOODLUST: UpgradeInfo("Bloodlust", Cost(700, 300), 50.0, "l", "Bloodlust", "Frenzy doubles: wounded orcs deal +50 % damage",
                                   race=Race.ORC),
    Upgrade.PLUNDER: UpgradeInfo("Plunder", Cost(600, 200), 45.0, "h", "Plunder", "Razing a building loots a fifth of its gold", race=Race.ORC),
    Upgrade.LONGBOWS: UpgradeInfo("Longbows", Cost(700, 400), 50.0, "l", "Longbows", "+1 range for rangers and towers", race=Race.ELF),
    Upgrade.REGROWTH: UpgradeInfo("Regrowth", Cost(500, 500), 45.0, "g", "Regrowth", "Trees felled by elves grow back after a minute",
                                  race=Race.ELF),
    Upgrade.DEEP_MINING: UpgradeInfo("Deep Mining", Cost(600, 300), 45.0, "d", "Mining", "Miners bring 150 gold per trip", race=Race.DWARF),
    Upgrade.BLASTING_POWDER: UpgradeInfo("Blasting Powder", Cost(900, 400), 50.0, "p", "Powder", "Mortar splash reaches half again as far",
                                         race=Race.DWARF),
}

BLADES_BONUS: Final = 2
#: The master weapons are worth two of the tiers below them, for well over twice their price and twice their hour.
MASTER_WEAPON_BONUS: Final = 4
ARMOR_BONUS: Final = 1
ARROWS_BONUS: Final = 2
HORSES_BONUS: Final = 0.8
SIEGE_RANGE_BONUS: Final = 1.0
SIEGE_DAMAGE_BONUS: Final = 1.25
BLESSING_BONUS: Final = 1.5
FRENZY_BONUS: Final = 1.25  # an orc below half health hits this much harder…
BLOODLUST_BONUS: Final = 1.5  # …and this much with Bloodlust
PLUNDER_SHARE: Final = 0.2  # of a razed building's gold cost
LONGBOWS_BONUS: Final = 1.0
REGROWTH_SECONDS: Final = 60.0
DEEP_MINING_TRIP: Final = 150
BLASTING_POWDER_BONUS: Final = 1.5
SPLASH_FRACTION: Final = 0.6  # share of the damage a stone deals beyond DIRECT_HIT of where it lands, out to the splash radius
DIRECT_HIT: Final = 0.5  # tiles from where a stone lands within which it deals its full damage
WINDUP_SLACK: Final = 0.5  # tiles a target may slip beyond weapon reach during the wind-up and still be struck
ARROW_SPEED: Final = 14.0  # tiles per second an arrow, axe or bolt flies; it follows its mark and strikes on arrival
STONE_SPEED: Final = 7.0  # tiles per second a siege stone covers; it comes down on the ground it was fired at
STONE_MIN_FLIGHT: Final = 0.4  # seconds even the shortest lob spends in the air
#: How hard each kind of blow lands on each kind of armour, before armour is subtracted; a pairing not listed is 1.
#: The one place these multipliers live (WB-049).  Towers strike a normal blow.
DAMAGE_FACTORS: Final[dict[tuple[AttackType, ArmorClass], float]] = {
    (AttackType.PIERCING, ArmorClass.UNARMORED): 1.5,
    (AttackType.SIEGE, ArmorClass.FORTIFIED): 1.5,
}


def damage_factor(attack: AttackType, armor: ArmorClass) -> float:
    return DAMAGE_FACTORS.get((attack, armor), 1.0)


def listing(names: list[str]) -> str:
    """"A", "A and B", "A, B and C"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def an(name: str) -> str:
    """*name* behind its indefinite article.  The races name an Altar, an Orchard and an Engine Works, so
    every message that puts "a" in front of one of these tables' names goes through this."""
    return f"{'an' if name[:1].upper() in 'AEIOU' else 'a'} {name}"


FRIENDLY_MARGIN: Final = 0.45  # tiles beyond its splash a siege crew keeps a stone from its own side when firing on its own.
# The crew leads a friend by the walking it does of its own accord; a shove from the crowd is not in that velocity, and a
# body the size of a knight's is shoved harder and further than the old one-size body was.  Over the twelve clash seeds of
# tests/warband/test_siege_judgement.py, 0.3 put stones on our own footmen in five of them (the shipped 0.35-tile bodies
# did it in two: the test's first six seeds were lucky) and 0.4 in one; 0.45 is the least that is clean.  It is also as far
# as this can go: at 0.5 the crew holds fire behind a line locked with the enemy and a catapult's damage falls by a third.
FORMATION_ARMOR: Final = 1  # armour a formation unit gains for each such friend at its left and at its right
FORMATION_SPACING: Final = 1.0  # tiles between neighbours in a marching line: a footman's body is 0.84 wide, so a line still has daylight in it
FORMATION_WIDTH: Final = 8  # a line this long; more stand in rows behind
FORMATION_MARCH: Final = 4.0  # tiles a group must go before its formation units form a line; nearer, they gather
FORMATION_SLACK: Final = 1.0  # tiles nearer its slot than the line's laggard before a marcher waits for it
FORMATION_HOLD: Final = 0.6  # of its speed a marcher that is ahead of its line walks
FORMATION_LOOKAHEAD: Final = 3.0  # tiles ahead of a marching line's middle each member aims for its place
SIEGE_STEP: Final = 3.0  # tiles beyond its reach a siege crew on its own judgement will roll forward for a clear shot
SIEGE_WORTH: Final = {UnitType.CATAPULT: 3.0, UnitType.CLERIC: 3.0, UnitType.ARCHER: 2.0}  # what a stone on them is worth to a crew; any other unit 1
SIEGE_BUILDING_WORTH: Final = 0.5  # a building under a stone, beside a unit's 1: soldiers first, walls when no soldier can be reached

GOLD_PER_TRIP: Final = 100
LUMBER_PER_TRIP: Final = 100
MINE_SLOTS: Final = 8  # peasants at a mine's face at once; the rest wait their turn at the mouth.
# The face serves MINE_SLOTS peasants every MINE_TIME, so a mine yields at most
# MINE_SLOTS * GOLD_PER_TRIP / MINE_TIME.  With the walk to the hall on top, a
# mine next door is saturated by about ten peasants and a distant one by a few
# more: hiring past that earns nothing, and the way to more gold is another mine.
MINE_TIME: Final = 5.0  # seconds a peasant spends inside a mine per trip
CHOP_TIME: Final = 5.0  # seconds to fell a tree
REPAIR_RATE: Final = 8.0  # hit points a peasant mends per second
REPAIR_CHUNK: Final = 10  # hit points paid for at a time while repairing
REPAIR_COST: Final = 0.5  # share of a building's price that mending all of its hit points costs


def repair_cost(info: BuildingInfo, hp_before: int, hp_after: int, max_hp: int) -> Cost:
    """What mending a building from *hp_before* to *hp_after* of *max_hp* costs: REPAIR_COST of its price, pro rata.

    Charged as the difference of two rounded-up running totals, so a repair
    costs the same however many chunks it is paid in: rounding each chunk up
    on its own charged a farm 160 lumber for a 125-lumber repair."""
    def so_far(price: int, hp: int) -> int:
        return math.ceil(price * REPAIR_COST * hp / max_hp)
    return Cost(so_far(info.cost.gold, hp_after) - so_far(info.cost.gold, hp_before),
                so_far(info.cost.lumber, hp_after) - so_far(info.cost.lumber, hp_before))


# Salvage is repair run backwards: a peasant tears hit points out of a building and carries the materials home.
# A ruin nobody holds comes apart at the rate one is mended at; a building someone still holds resists, and comes
# apart at a quarter of it, which is why a peasant crew is never a siege engine (a catapult puts about fourteen
# hit points a second into a building from seven tiles away, a salvaging peasant two from arm's length).
SALVAGE_RATE: Final = 8.0  # hit points a peasant tears out of a ruin per second
SALVAGE_HELD_RATE: Final = 2.0  # hit points a second out of a building its owner still holds
SALVAGE_CHUNK: Final = 10  # hit points torn out at a time, each paid out on its own
SALVAGE_SHARE: Final = 0.25  # share of a building's price that tearing all of its hit points out returns


def salvage_yield(info: BuildingInfo, hp_before: int, hp_after: int, max_hp: int) -> int:
    """What tearing a building from *hp_before* down to *hp_after* of *max_hp* is worth, as one number.

    SALVAGE_SHARE of the whole price, gold and lumber together, pro rata over the hit points and counted from
    full: what somebody else's blows already broke is value nobody gets back, so a building bombarded to a
    sliver holds almost nothing and the prize is one still standing whole.  As :func:`repair_cost` does, it is
    the difference of two running totals, so a salvage is worth the same however many chunks it is torn out in;
    rounded down, so it never pays out more than the share.  Which resource the payout comes as is
    :func:`salvage_resource`'s draw."""
    price = info.cost.gold + info.cost.lumber
    def so_far(gone: int) -> int:
        return math.floor(price * SALVAGE_SHARE * gone / max_hp)
    return so_far(max_hp - hp_after) - so_far(max_hp - hp_before)


def salvage_resource(info: BuildingInfo, roll: float) -> Resource:
    """Which resource a salvaged chunk comes out as, drawn from *roll* in [0, 1).

    Weighted by what the building is made of, so a farm that cost 500 gold and 250 lumber gives up gold twice as
    often as lumber and a full salvage is worth, on average, exactly the share of each: it reads as pulling
    materials out of the building that is there."""
    price = info.cost.gold + info.cost.lumber
    return Resource.GOLD if roll * price < info.cost.gold else Resource.LUMBER
MINE_GOLD: Final = 50_000  # a base mine; expansion mines hold EXPANSION_GOLD
EXPANSION_GOLD: Final = 30_000
STARTING_GOLD: Final = 1000
STARTING_LUMBER: Final = 500
#: The largest body any unit has: what a search that must not miss a unit whose body reaches into it pads by
#: (the bodies themselves are :attr:`UnitInfo.radius`).  A jittered rulebook never moves a radius, so this holds.
MAX_UNIT_RADIUS: Final = max(info.radius for info in UNITS.values())
LEASH: Final = 6.0  # how far an idle unit chases before it walks home
UNDER_ATTACK_COOLDOWN: Final = 20.0
SIM_DT: Final = 0.05  # the simulation runs at 20 Hz regardless of the frame rate
VISION_EVERY: Final = 4  # ticks between fog recomputations
MAX_PLANS: Final = 64  # settlement plans a player may have waiting: each is looked at every second and travels in every online snapshot
MAX_QUEUED_ORDERS: Final = 32  # orders a unit may have queued behind the one it is carrying out
HIT_VARIANCE: Final = 0.25  # damage rolls between 75 % and 125 % of the listed value


@dataclass(frozen=True)
class PlayerInfo:
    name: str
    color: tuple[int, int, int]


PLAYERS: Final[list[PlayerInfo]] = [
    PlayerInfo("Azure", (70, 130, 255)),
    PlayerInfo("Crimson", (225, 70, 60)),
    PlayerInfo("Viridian", (80, 190, 110)),
    PlayerInfo("Amber", (245, 190, 60)),
]


class Difficulty(IdentityEnum):
    """What the player is up against, weakest first.

    The three settings that shipped before were two: measured over 720 games,
    Normal and Hard sat at 994 and 1000 Elo and won 55% against each other,
    which is not a difficulty step. They are one setting now, and the steps
    above them are :mod:`warband.brains.pro_ai` brains. See ``docs/ai-ladder.md``.
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    MASTER = "master"
    GRANDMASTER = "grandmaster"  # postures bred by a genetic search, a race's own for each race (warband/brains/bred.py)


class MapTheme(IdentityEnum):
    SUMMER = "summer"
    WINTER = "winter"
    WASTELAND = "wasteland"


class Layout(IdentityEnum):
    """The shape of a generated map: what its walls are made of and where the gold lies.
    One row of the new-game screen; the recipes are in :mod:`warband.sim.mapgen` and docs/warband-maps.md."""

    PLAINS = "plains"
    FOREST = "forest"
    CROSSINGS = "crossings"
    KLONDIKE = "klondike"
    BASTION = "bastion"
