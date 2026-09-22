"""Static game data.  Nothing here mutates.

To change what a unit, building or upgrade costs or does, edit the TOML next
to this file -- ``units.toml``, ``buildings.toml``, ``upgrades.toml`` -- and
run ``uv run python tools/balance_tables.py`` from the repository root, which
rewrites the GENERATED regions below.  Never edit those regions by hand;
``tests/warband/test_balance_tables.py`` fails until the two agree.  The
per-race tweaks live in ``races.toml`` the same way.

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
| catapult | 900+300   | 80 | 36  | 0     | 2..7  | 0.8 + 4.0          | 150°/s| 1.6   | siege: stones land where aimed, splash friend and foe, ×1.5 vs buildings; helpless inside two tiles |
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
    # The neutral creatures: nobody trains them, no race names them, and they are never team-coloured.
    # Their values are :class:`warband.art.monsters.Monster`'s, so the art is reached with ``Monster(unit.type.value)``.
    WOLF = "wolf"
    TROLL = "troll"
    SPIDER = "spider"
    GOLEM = "golem"


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
    GOLD_SEAM = "gold_seam"  # the endless one; :class:`MineInfo` is what tells the two deposits apart
    LAIR = "lair"  # a creature camp's den: nobody's, the guards' respawn anchor and the hoard they sit on


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
    #: Hit points a creature knits back per second once nothing has struck it for :data:`REGEN_CALM` seconds.
    #: Out of combat, never during it: continuous regeneration would put a hard floor under the damage needed to
    #: kill the thing at all, and with blows rolling 75-125 % every camp at that floor would be a coin flip.
    regen: float = 0.0

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
    def siege(self) -> bool:
        """A siege engine: its shot lands on the ground it was fired at and splashes.

        Not merely "its blow splashes": a golem's slam does too, and it is a melee brute that judges
        nothing, aims at nothing and never vetoes its own blow.  Every rule about aiming a stone, the
        crew's own judgement and its minimum range asks this rather than :attr:`splash`.
        """
        return self.splash > 0.0 and not self.melee

    @property
    def soldier(self) -> bool:
        """It fights for a living: a worker's or a healer's blow does not make it one (the unit may still be a worker)."""
        return self.damage > 0 and not self.heal


MELEE: Final = 0.45  # reach of a melee unit: it strikes from the next tile over, diagonals included

# generated-begin units: from warband/sim/units.toml — do not edit by hand; run tools/balance_tables.py
UNITS: Final[dict[UnitType, UnitInfo]] = {
    UnitType.PEASANT: UnitInfo(name='Peasant', cost=Cost(400), hp=30, damage=3, armor=0, range=MELEE, cooldown=1.0, speed=2.4, sight=4, build_time=12.0, trained_at=BuildingType.TOWN_HALL, hotkey='p', summary='Mines gold, chops lumber, builds and repairs', radius=0.36, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.UNARMORED, formation=False, mounted=False, windup=0.25, turn=math.radians(360), min_range=0.0, regen=0.0),
    UnitType.FOOTMAN: UnitInfo(name='Footman', cost=Cost(600), hp=60, damage=7, armor=3, range=MELEE, cooldown=1.0, speed=2.0, sight=5, build_time=15.0, trained_at=BuildingType.BARRACKS, hotkey='f', summary='Slow shield-wall swordsman; tougher with a comrade at each side', radius=0.42, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.HEAVY, formation=True, mounted=False, windup=0.3, turn=math.radians(360), min_range=0.0, regen=0.0),
    UnitType.ARCHER: UnitInfo(name='Archer', cost=Cost(500, 50), hp=40, damage=6, armor=0, range=4.0, cooldown=1.3, speed=2.4, sight=6, build_time=14.0, trained_at=BuildingType.BARRACKS, hotkey='a', summary='Shoots from four tiles away; fragile up close', radius=0.42, heal=0, splash=0.0, attack=AttackType.PIERCING, armor_class=ArmorClass.LIGHT, formation=False, mounted=False, windup=0.35, turn=math.radians(360), min_range=0.0, regen=0.0),
    UnitType.SCOUT: UnitInfo(name='Scout', cost=Cost(350), hp=35, damage=4, armor=0, range=MELEE, cooldown=0.8, speed=4.2, sight=8, build_time=10.0, trained_at=BuildingType.STABLES, hotkey='s', summary='Fast rider who sees far; raids peasants and archers', radius=0.48, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.LIGHT, formation=False, mounted=True, windup=0.25, turn=math.radians(450), min_range=0.0, regen=0.0),
    UnitType.KNIGHT: UnitInfo(name='Knight', cost=Cost(900, 100), hp=90, damage=10, armor=4, range=MELEE, cooldown=1.0, speed=3.4, sight=5, build_time=20.0, trained_at=BuildingType.STABLES, hotkey='k', summary='Fast, heavily armoured shock cavalry', radius=0.56, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.HEAVY, formation=False, mounted=True, windup=0.35, turn=math.radians(270), min_range=0.0, regen=0.0),
    UnitType.CATAPULT: UnitInfo(name='Catapult', cost=Cost(900, 300), hp=80, damage=36, armor=0, range=7.0, cooldown=4.0, speed=1.6, sight=6, build_time=30.0, trained_at=BuildingType.WORKSHOP, hotkey='c', summary='Slow siege engine: stones land where aimed, splash friend and foe, ×1.5 against buildings', radius=0.62, heal=0, splash=1.2, attack=AttackType.SIEGE, armor_class=ArmorClass.UNARMORED, formation=False, mounted=False, windup=0.8, turn=math.radians(150), min_range=2.0, regen=0.0),
    UnitType.CLERIC: UnitInfo(name='Cleric', cost=Cost(700, 50), hp=40, damage=3, armor=0, range=3.0, cooldown=2.0, speed=2.4, sight=5, build_time=20.0, trained_at=BuildingType.CHURCH, hotkey='h', summary='Heals a wounded ally 15 at a cast; a weak blow when no one needs it', radius=0.38, heal=15, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.UNARMORED, formation=False, mounted=False, windup=0.5, turn=math.radians(360), min_range=0.0, regen=0.0),
}
# generated-end units

#: What a player can train, in card order: everything but the neutral creatures.  Every loop that means
#: "the game's units" walks this rather than :class:`UnitType`, which now also holds the wilds.
PLAYABLE_UNITS: Final[tuple[UnitType, ...]] = (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.SCOUT,
                                               UnitType.KNIGHT, UnitType.CATAPULT, UnitType.CLERIC)


# -- The wilds ---------------------------------------------------------------------
#
# Neutral creatures guard the contested deposits.  Each is chosen for a unit the balance data says is
# dead weight, and each is a shape the roster does not already own (docs/warband-monsters.md):
#
# | creature | hp  | dmg | armour        | range | wind-up + cooldown | speed | what it rewards                       |
# |----------|-----|-----|---------------|-------|--------------------|-------|---------------------------------------|
# | wolf     |  40 |   6 | 0 light       | melee | 0.2 + 0.9          | 4.0   | nothing: the cheap minute-two camp    |
# | spider   |  45 |   8 | 0 light       | 5     | 0.4 + 1.6          | 2.2   | the scout, which closes the five tiles|
# | troll    | 220 |  14 | 0 unarmoured  | melee | 0.45 + 1.4         | 1.9   | the archer: piercing lands x1.5 on it |
# | golem    | 170 |  18 | 2 heavy, splash| melee | 0.7 + 2.5         | 1.3   | the archer again, by punishing clumps |
#
# The troll is deliberately *unarmoured* rather than a high-armour sponge: armour is flat subtraction
# with a floor of one, so plating it would make an archer's arrow land for 1 and turn every camp into a
# knights-only check.  High hit points and no armour cost time and exposure instead, and leave the
# archer the efficient answer.  Its regeneration is out-of-combat only (:attr:`UnitInfo.regen`).

# generated-begin wilds: from warband/sim/units.toml — do not edit by hand; run tools/balance_tables.py
WILD_UNITS: Final[dict[UnitType, UnitInfo]] = {
    UnitType.WOLF: UnitInfo(name='Dire Wolf', cost=Cost(0), hp=40, damage=6, armor=0, range=MELEE, cooldown=0.9, speed=4.0, sight=7, build_time=0.0, trained_at=BuildingType.LAIR, hotkey='', summary='A pack hunter: fast, fragile and never alone', radius=0.4, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.LIGHT, formation=False, mounted=False, windup=0.2, turn=math.radians(450), min_range=0.0, regen=0.0),
    UnitType.SPIDER: UnitInfo(name='Venom Spider', cost=Cost(0), hp=45, damage=8, armor=0, range=5.0, cooldown=1.6, speed=2.2, sight=7, build_time=0.0, trained_at=BuildingType.LAIR, hotkey='', summary='Spits venom from five tiles; helpless once something reaches it', radius=0.45, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.LIGHT, formation=False, mounted=False, windup=0.4, turn=math.radians(360), min_range=0.0, regen=0.0),
    UnitType.TROLL: UnitInfo(name='Troll', cost=Cost(0), hp=220, damage=14, armor=0, range=MELEE, cooldown=1.4, speed=1.9, sight=6, build_time=0.0, trained_at=BuildingType.LAIR, hotkey='', summary='Bare-skinned and hard to put down; knits its wounds back once left alone', radius=0.58, heal=0, splash=0.0, attack=AttackType.NORMAL, armor_class=ArmorClass.UNARMORED, formation=False, mounted=False, windup=0.45, turn=math.radians(360), min_range=0.0, regen=8.0),
    UnitType.GOLEM: UnitInfo(name='Stone Golem', cost=Cost(0), hp=170, damage=18, armor=2, range=MELEE, cooldown=2.5, speed=1.3, sight=5, build_time=0.0, trained_at=BuildingType.LAIR, hotkey='', summary='Slams the ground: every enemy around its mark is caught', radius=0.6, heal=0, splash=1.3, attack=AttackType.NORMAL, armor_class=ArmorClass.HEAVY, formation=False, mounted=False, windup=0.7, turn=math.radians(150), min_range=0.0, regen=0.0),
}
# generated-end wilds
UNITS.update(WILD_UNITS)
CREATURES: Final[tuple[UnitType, ...]] = tuple(WILD_UNITS)
#: Buildings nobody names: the two gold deposits and the lair.  No race tweaks them and no race draws them.
WILD_BUILDINGS: Final[frozenset[BuildingType]] = frozenset({BuildingType.GOLD_MINE, BuildingType.GOLD_SEAM, BuildingType.LAIR})
#: What a player builds, in card order: everything the wilds do not own.  Every loop that means "the game's
#: buildings" -- a race's names, the painted sheets, a jittered rulebook, the art lint -- walks this.
BUILT: Final[tuple[BuildingType, ...]] = tuple(bt for bt in BuildingType if bt not in WILD_BUILDINGS)

REGEN_CALM: Final = 6.0  # seconds since the last blow landed on it before a creature's regeneration starts


# -- Gold deposits -----------------------------------------------------------------

# generated-begin deposits: from warband/sim/buildings.toml — do not edit by hand; run tools/balance_tables.py
GOLD_PER_TRIP: Final = 100
MINE_SLOTS: Final = 8
SEAM_PER_TRIP: Final = 20
SEAM_SLOTS: Final = 12
# generated-end deposits
MINE_TIME: Final = 5.0  # seconds a peasant spends inside a deposit per trip
# The face serves its slots every MINE_TIME, so a deposit yields at most slots * trip / MINE_TIME. With the
# walk to the hall on top, a mine next door is saturated by about ten peasants and a distant one by a few
# more (the trips and slots are warband/sim/buildings.toml's): hiring past that earns nothing, and the way
# to more gold is another mine.


@dataclass(frozen=True)
class MineInfo:
    """What a gold deposit gives the peasants who work it.

    *trip* is the gold one brings up (a dwarf's Deep Mining raises it in proportion:
    :meth:`~warband.sim.model.World.gold_per_trip`), *slots* how many work the face at once, and
    *endless* whether the deposit ever runs out.  A mine's :attr:`~warband.sim.model.Building.gold`
    is its stock: it falls with every trip and the mine is gone when it reaches zero.  An endless
    seam holds no stock at all -- its ``gold`` is zero and stays zero -- and keeps giving, so what
    is worth working is asked as :attr:`~warband.sim.model.Building.has_gold`, never of the number.
    """

    trip: int
    slots: int
    endless: bool = False


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
    mine: MineInfo | None = None  # set on the gold deposits alone, and on nothing a player can build


# generated-begin buildings: from warband/sim/buildings.toml — do not edit by hand; run tools/balance_tables.py
BUILDINGS: Final[dict[BuildingType, BuildingInfo]] = {
    BuildingType.TOWN_HALL: BuildingInfo(name='Town Hall', cost=Cost(1200, 800), hp=1200, armor=3, size=3, build_time=60.0, sight=6, supply=5, hotkey='h', summary='Trains peasants; gold and lumber are delivered here; raises the Keep', trains=(UnitType.PEASANT,), researches=(Upgrade.KEEP,), deposits=frozenset({Resource.GOLD, Resource.LUMBER}), damage=0, range=0.0, cooldown=1.0),
    BuildingType.FARM: BuildingInfo(name='Farm', cost=Cost(500, 250), hp=400, armor=2, size=2, build_time=25.0, sight=3, supply=4, hotkey='f', summary='Feeds four units', trains=(), researches=(), damage=0, range=0.0, cooldown=1.0),
    BuildingType.BARRACKS: BuildingInfo(name='Barracks', cost=Cost(700, 450), hp=800, armor=3, size=3, build_time=40.0, sight=5, supply=0, hotkey='b', summary='Trains footmen and archers', trains=(UnitType.FOOTMAN, UnitType.ARCHER), researches=(), requires=BuildingType.TOWN_HALL, damage=0, range=0.0, cooldown=1.0),
    BuildingType.TOWER: BuildingInfo(name='Guard Tower', cost=Cost(700, 250), hp=400, armor=3, size=2, build_time=35.0, sight=8, supply=0, hotkey='t', summary='Shoots at enemies six tiles away', trains=(), researches=(), requires=BuildingType.BARRACKS, damage=8, range=6.0, cooldown=1.5),
    BuildingType.LUMBER_MILL: BuildingInfo(name='Lumber Mill', cost=Cost(600, 450), hp=600, armor=2, size=3, build_time=35.0, sight=4, supply=0, hotkey='m', summary='Lumber is delivered here; researches better arrows', trains=(), researches=(Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.ARROWS_3, Upgrade.MARKSMANSHIP, Upgrade.LONGBOWS, Upgrade.REGROWTH), requires=BuildingType.TOWN_HALL, deposits=frozenset({Resource.LUMBER}), damage=0, range=0.0, cooldown=1.0),
    BuildingType.BLACKSMITH: BuildingInfo(name='Blacksmith', cost=Cost(800, 450), hp=600, armor=3, size=3, build_time=40.0, sight=4, supply=0, hotkey='k', summary='Researches sharper blades and plate armour', trains=(), researches=(Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3, Upgrade.ARMOR_1, Upgrade.ARMOR_2, Upgrade.BLOODLUST, Upgrade.DEEP_MINING), requires=BuildingType.BARRACKS, damage=0, range=0.0, cooldown=1.0),
    BuildingType.STABLES: BuildingInfo(name='Stables', cost=Cost(1000, 300), hp=700, armor=3, size=3, build_time=45.0, sight=4, supply=0, hotkey='s', summary='Trains scouts and knights; breeds faster horses', trains=(UnitType.SCOUT, UnitType.KNIGHT), researches=(Upgrade.HORSES, Upgrade.PLUNDER), requires=BuildingType.BARRACKS, damage=0, range=0.0, cooldown=1.0),
    BuildingType.WORKSHOP: BuildingInfo(name='Workshop', cost=Cost(700, 350), hp=600, armor=3, size=3, build_time=45.0, sight=4, supply=0, hotkey='w', summary='Builds catapults; improves siege engines', trains=(UnitType.CATAPULT,), researches=(Upgrade.SIEGE, Upgrade.BLASTING_POWDER), requires=BuildingType.BLACKSMITH, damage=0, range=0.0, cooldown=1.0),
    BuildingType.CHURCH: BuildingInfo(name='Church', cost=Cost(900, 400), hp=600, armor=3, size=3, build_time=45.0, sight=5, supply=0, hotkey='c', summary='Trains clerics; blesses their healing', trains=(UnitType.CLERIC,), researches=(Upgrade.BLESSING,), requires=BuildingType.BARRACKS, damage=0, range=0.0, cooldown=1.0),
    BuildingType.GOLD_MINE: BuildingInfo(name='Gold Mine', cost=Cost(0), hp=0, armor=0, size=3, build_time=0.0, sight=0, supply=0, hotkey='', summary='Peasants mine gold here', trains=(), researches=(), damage=0, range=0.0, cooldown=1.0, mine=MineInfo(trip=100, slots=8)),
    BuildingType.GOLD_SEAM: BuildingInfo(name='Gold Seam', cost=Cost(0), hp=0, armor=0, size=5, build_time=0.0, sight=0, supply=0, hotkey='', summary=f'A wide seam that never runs dry: {SEAM_PER_TRIP} gold a trip', trains=(), researches=(), damage=0, range=0.0, cooldown=1.0, mine=MineInfo(trip=20, slots=12, endless=True)),
    BuildingType.LAIR: BuildingInfo(name='Lair', cost=Cost(0), hp=900, armor=2, size=3, build_time=0.0, sight=4, supply=0, hotkey='', summary='A creature den: its guards come back from it until it is torn down', trains=(), researches=(), damage=0, range=0.0, cooldown=1.0),
}
# generated-end buildings


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


# generated-begin upgrades: from warband/sim/upgrades.toml — do not edit by hand; run tools/balance_tables.py
UPGRADES: Final[dict[Upgrade, UpgradeInfo]] = {
    Upgrade.KEEP: UpgradeInfo(name='Keep', cost=Cost(1500, 800), time=90.0, hotkey='k', card='Keep', summary='Raises the hall, opening the upper tiers', requires=()),
    Upgrade.BLADES_1: UpgradeInfo(name='Sharpened Blades', cost=Cost(500, 100), time=40.0, hotkey='b', card='Blades I', summary='+2 damage for melee units', requires=()),
    Upgrade.BLADES_2: UpgradeInfo(name='Tempered Blades', cost=Cost(1500, 300), time=60.0, hotkey='b', card='Blades II', summary='+2 more damage for melee units', requires=(Upgrade.BLADES_1, Upgrade.KEEP)),
    Upgrade.BLADES_3: UpgradeInfo(name='Masterwork Blades', cost=Cost(3000, 600), time=120.0, hotkey='b', card='Blades III', summary='+4 more damage for melee units', requires=(Upgrade.BLADES_2, Upgrade.KEEP)),
    Upgrade.ARMOR_1: UpgradeInfo(name='Plate Armour', cost=Cost(300, 300), time=40.0, hotkey='a', card='Armour I', summary='+1 armour for soldiers', requires=()),
    Upgrade.ARMOR_2: UpgradeInfo(name='Heavy Plate', cost=Cost(900, 500), time=60.0, hotkey='a', card='Armour II', summary='+1 more armour for soldiers', requires=(Upgrade.ARMOR_1, Upgrade.KEEP)),
    Upgrade.ARROWS_1: UpgradeInfo(name='Bodkin Arrows', cost=Cost(300, 300), time=40.0, hotkey='r', card='Arrows I', summary='+2 damage for archers and towers', requires=()),
    Upgrade.ARROWS_2: UpgradeInfo(name='Broadhead Arrows', cost=Cost(900, 500), time=60.0, hotkey='r', card='Arrows II', summary='+2 more damage for archers and towers', requires=(Upgrade.ARROWS_1, Upgrade.KEEP)),
    Upgrade.ARROWS_3: UpgradeInfo(name='Masterwork Arrows', cost=Cost(1800, 1000), time=120.0, hotkey='r', card='Arrows III', summary='+4 more damage for archers and towers', requires=(Upgrade.ARROWS_2, Upgrade.KEEP)),
    Upgrade.SIEGE: UpgradeInfo(name='Siege Engineering', cost=Cost(1000, 500), time=60.0, hotkey='e', card='Siege', summary='+1 range and +25 % damage for siege engines', requires=()),
    Upgrade.MARKSMANSHIP: UpgradeInfo(name='Marksmanship', cost=Cost(600, 300), time=45.0, hotkey='m', card='Marksmen', summary='Shooters pick the mark in reach they fell soonest and waste no arrow on the dying', requires=()),
    Upgrade.HORSES: UpgradeInfo(name='Horse Breeding', cost=Cost(900, 300), time=50.0, hotkey='h', card='Horses', summary='+0.8 speed for scouts and knights', requires=(), race=Race.HUMAN),
    Upgrade.BLESSING: UpgradeInfo(name='Blessing', cost=Cost(800, 400), time=50.0, hotkey='l', card='Blessing', summary='Clerics heal half again as fast', requires=(), race=Race.HUMAN),
    Upgrade.BLOODLUST: UpgradeInfo(name='Bloodlust', cost=Cost(700, 300), time=50.0, hotkey='l', card='Bloodlust', summary='Frenzy doubles: wounded orcs deal +50 % damage', requires=(), race=Race.ORC),
    Upgrade.PLUNDER: UpgradeInfo(name='Plunder', cost=Cost(600, 200), time=45.0, hotkey='h', card='Plunder', summary='Razing a building loots a fifth of its gold', requires=(), race=Race.ORC),
    Upgrade.LONGBOWS: UpgradeInfo(name='Longbows', cost=Cost(700, 400), time=50.0, hotkey='l', card='Longbows', summary='+1 range for rangers and towers', requires=(), race=Race.ELF),
    Upgrade.REGROWTH: UpgradeInfo(name='Regrowth', cost=Cost(500, 500), time=45.0, hotkey='g', card='Regrowth', summary='Trees felled by elves grow back after a minute', requires=(), race=Race.ELF),
    Upgrade.DEEP_MINING: UpgradeInfo(name='Deep Mining', cost=Cost(600, 300), time=45.0, hotkey='d', card='Mining', summary='Miners bring 150 gold per trip', requires=(), race=Race.DWARF),
    Upgrade.BLASTING_POWDER: UpgradeInfo(name='Blasting Powder', cost=Cost(900, 400), time=50.0, hotkey='p', card='Powder', summary='Mortar splash reaches half again as far', requires=(), race=Race.DWARF),
}
# generated-end upgrades

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


FRIENDLY_MARGIN: Final = 0.45  # tiles beyond its splash a siege crew counts one of its own as standing under the stone.
# Where a friend will be when the stone lands is a guess: the crew leads it by the walking it does of its own accord, and a
# shove from the crowd is not in that velocity, the more so since a body the size of a knight's is shoved harder and further
# than the old one-size body was.  Over the twelve clash seeds of tests/warband/test_siege_judgement.py, a veto at 0.3 put
# stones on our own footmen in five of them (the shipped 0.35-tile bodies did it in two: the test's first six seeds were
# lucky) and 0.4 in one; 0.45 is the least that was clean.
FRIENDLY_WORTH: Final = 2.0  # what one of our own under a stone costs the crew, against SIEGE_WORTH's 1 for one of theirs.
# A crew on its own judgement used to veto any stone that could touch its own side, which behind a line locked with the enemy
# is every stone there is: in the set piece of docs/balance.md it threw a stone every thirty-one seconds where its reload is
# under four, and seven footmen and two catapults lost to ten footmen.  It weighs the trade instead (World._aim_trade), and
# two of ours for one of theirs is what it takes.  It is the least that is clean: at 1.5 the crew shells its own line on the
# clash seeds of tests/warband/test_siege_judgement.py, and 3.0 is markedly more timid where it is pressed (against twelve
# footmen the same two catapults win 30% of the set piece rather than 72%).
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

LUMBER_PER_TRIP: Final = 100
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
MINE_GOLD: Final = 50_000  # a base mine; expansion mines hold EXPANSION_GOLD, and an endless seam no stock at all
EXPANSION_GOLD: Final = 30_000
STARTING_GOLD: Final = 1000
STARTING_LUMBER: Final = 500
#: The largest body any unit has: what a search that must not miss a unit whose body reaches into it pads by
#: (the bodies themselves are :attr:`UnitInfo.radius`).  A jittered rulebook never moves a radius, so this holds.
MAX_UNIT_RADIUS: Final = max(info.radius for info in UNITS.values())
LEASH: Final = 6.0  # how far an idle unit chases before it walks home

# -- Creature camps ----------------------------------------------------------------
# A camp is a lair with its guards placed around it, and it resets rather than streaming.  A den that
# emitted units would either eat an army during the fight (no decision in it) or trickle so slowly that
# clearing it is beating down an undefended building; a camp that comes back once it is left alone makes
# the decision crisp instead -- clear the whole thing, lair and all, in one committed push and it is yours
# for good; break off and you paid units for nothing.
CAMP_WATCH: Final = 7.0  # tiles from the lair within which an intruder rouses the camp…
CAMP_HOLD: Final = 11.0  # …and beyond which the camp counts it gone and settles back
CAMP_CALM: Final = 8.0  # seconds with nobody in CAMP_HOLD before a camp starts putting itself back together
CAMP_REGEN: Final = 10.0  # hit points a settled guard standing at its post knits back per second
CAMP_RESPAWN: Final = 25.0  # seconds a settled camp takes to bring one fallen guard back out of the lair
CAMP_POST: Final = 2.6  # tiles from the lair's middle a guard is posted
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


#: A seat's name and colour, dealt in this order.  Eight bright hues spread round the wheel first,
#: then deeper and lighter ones between them, so a four- or eight-player game uses the colours that
#: differ most.  Every one keeps enough saturation and brightness to survive the team recolour of a
#: painted sprite (art/textures.recolor scales a sprite by the target's saturation and value, so a
#: pastel or a near-black would give a colourless or a black army), and stands at least as far from
#: every theme's ground as the four that shipped do.  The numbers, including what a protanope and a
#: deuteranope see, are in docs/warband-maps.md; the closest pair for red-green vision is Crimson
#: against Viridian, which is the pair Warband has always had.
PLAYERS: Final[list[PlayerInfo]] = [
    PlayerInfo("Azure", (70, 130, 255)),
    PlayerInfo("Crimson", (225, 70, 60)),
    PlayerInfo("Viridian", (80, 190, 110)),
    PlayerInfo("Amber", (245, 190, 60)),
    PlayerInfo("Violet", (208, 139, 255)),
    PlayerInfo("Aqua", (59, 216, 255)),
    PlayerInfo("Magenta", (217, 54, 125)),
    PlayerInfo("Lime", (196, 247, 36)),
    PlayerInfo("Cobalt", (39, 50, 180)),
    PlayerInfo("Umber", (128, 78, 4)),
    PlayerInfo("Mint", (109, 204, 182)),
    PlayerInfo("Indigo", (99, 8, 225)),
    PlayerInfo("Maroon", (124, 0, 23)),
    PlayerInfo("Olive", (141, 149, 16)),
    PlayerInfo("Rose", (244, 137, 148)),
    PlayerInfo("Slate", (119, 154, 210)),
]
MAX_PLAYERS: Final = len(PLAYERS)  # the seats a match can hold: one to a colour
#: The wilds.  Every world has one seat past its playable ones, and the neutral creatures and their lairs
#: belong to it.  It exists because ``Unit.player`` is a plain ``int`` that the simulation indexes
#: ``self.players`` with on every step: a ``-1`` sentinel would quietly answer with the last real seat.
#: It is alive for ever, owns no purse, no supply and no economy, and is out of victory and elimination;
#: its colour is the bone-grey of the creature sheets, which no player wears.
NEUTRAL: Final = PlayerInfo("Wilds", (150, 148, 140))


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
