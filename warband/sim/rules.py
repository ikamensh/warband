"""Static game data.  Nothing here mutates.

Balance values are read once from ``warband/assets/constants/*.toml`` when the
simulation starts. Edit those files and restart to use new values; a running
process keeps its validated snapshot, including races imported later.

Distances are in tiles, times in seconds of simulation time.  A unit's
``range`` is the largest gap between its edge and the target's edge at
which it can strike (or heal); melee units must all but touch.

A blow takes time: the unit pivots to face its target at its ``turn`` rate,
stands through a ``windup`` (the sword drawn back, the bow bent, the
catapult arm cranked down), lands the blow, and waits ``cooldown`` before
the next wind-up may start.  Shots are projectiles: an arrow follows its
mark and strikes when it arrives, a siege stone comes down on the ground it
was fired at, on whoever stands there by then.

Armour classes and attack types (WB-049, :data:`DAMAGE_FACTORS`): peasants, clerics and catapults are unarmoured,
archers and scouts light, footmen and knights heavy, buildings fortified; archers pierce, catapults siege, the rest
and towers strike normally.  Piercing lands ×1.5 on the unarmoured, siege ×1.5 on buildings, everything else ×1.

A building's armour is :data:`BUILDINGS`' once it stands; a frame still going up wears none.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from enum import Enum
from typing import Any, Final

from warband.sim import config


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


MELEE: Final = config.number('MELEE')

def _unit(u: dict[str, Any]) -> UnitInfo:
    return UnitInfo(
        name=u["name"], cost=Cost(u["gold"], u["lumber"]), hp=u["hp"], damage=u["damage"], armor=u["armor"],
        range=MELEE if u["range"] == "melee" else u["range"], cooldown=u["cooldown"], speed=u["speed"], sight=u["sight"],
        build_time=u["build_time"], trained_at=BuildingType(u["trained_at"]), hotkey=u["hotkey"], summary=u["summary"],
        radius=u["radius"], heal=u["heal"], splash=u["splash"], attack=AttackType(u["attack"]),
        armor_class=ArmorClass(u["armor_class"]), formation=u["formation"], mounted=u["mounted"], windup=u["windup"],
        turn=math.radians(u["turn_deg"]), min_range=u["min_range"], regen=u["regen"],
    )


UNITS: Final[dict[UnitType, UnitInfo]] = {UnitType(u): _unit(info) for u, info in config.current().units.items()}

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

WILD_UNITS: Final[dict[UnitType, UnitInfo]] = {UnitType(u): _unit(info) for u, info in config.current().wilds.items()}
UNITS.update(WILD_UNITS)
CREATURES: Final[tuple[UnitType, ...]] = tuple(WILD_UNITS)
#: Buildings nobody names: the two gold deposits and the lair.  No race tweaks them and no race draws them.
WILD_BUILDINGS: Final[frozenset[BuildingType]] = frozenset({BuildingType.GOLD_MINE, BuildingType.GOLD_SEAM, BuildingType.LAIR})
#: What a player builds, in card order: everything the wilds do not own.  Every loop that means "the game's
#: buildings" -- a race's names, the painted sheets, a jittered rulebook, the art lint -- walks this.
BUILT: Final[tuple[BuildingType, ...]] = tuple(bt for bt in BuildingType if bt not in WILD_BUILDINGS)

REGEN_CALM: Final = config.number('REGEN_CALM')


# -- Gold deposits -----------------------------------------------------------------

GOLD_PER_TRIP: Final[int] = config.current().buildings["gold_mine"]["mine_trip"]
MINE_SLOTS: Final[int] = config.current().buildings["gold_mine"]["mine_slots"]
SEAM_PER_TRIP: Final[int] = config.current().buildings["gold_seam"]["mine_trip"]
SEAM_SLOTS: Final[int] = config.current().buildings["gold_seam"]["mine_slots"]
MINE_TIME: Final = config.number('MINE_TIME')
# The face serves its slots every MINE_TIME, so a deposit yields at most slots * trip / MINE_TIME. With the
# walk to the hall on top, a mine next door is saturated by about ten peasants and a distant one by a few
# more (the trips and slots are warband/assets/constants/buildings.toml's): hiring past that earns nothing, and the way
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


def _building(b: dict[str, Any]) -> BuildingInfo:
    mine = MineInfo(b["mine_trip"], b["mine_slots"], b["mine_endless"]) if b["mine_trip"] or b["mine_slots"] else None
    return BuildingInfo(
        name=b["name"], cost=Cost(b["gold"], b["lumber"]), hp=b["hp"], armor=b["armor"], size=b["size"],
        build_time=b["build_time"], sight=b["sight"], supply=b["supply"], hotkey=b["hotkey"],
        summary=b["summary"].replace("{trip}", str(b["mine_trip"])),
        trains=tuple(UnitType(u) for u in b["trains"]), researches=tuple(Upgrade(u) for u in b["researches"]),
        requires=None if b["requires"] is None else BuildingType(b["requires"]),
        deposits=frozenset(Resource(r) for r in b["deposits"]), damage=b["damage"], range=b["range"],
        cooldown=b["cooldown"], mine=mine,
    )


BUILDINGS: Final[dict[BuildingType, BuildingInfo]] = {BuildingType(b): _building(info)
                                                   for b, info in config.current().buildings.items()}


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


def _upgrade(u: dict[str, Any]) -> UpgradeInfo:
    return UpgradeInfo(
        name=u["name"], cost=Cost(u["gold"], u["lumber"]), time=u["time"], hotkey=u["hotkey"], card=u["card"],
        summary=u["summary"].replace("{trip}", str(config.integer("DEEP_MINING_TRIP"))),
        requires=tuple(Upgrade(r) for r in u["requires"]), race=None if u["race"] is None else Race(u["race"]),
    )


UPGRADES: Final[dict[Upgrade, UpgradeInfo]] = {Upgrade(u): _upgrade(info) for u, info in config.current().upgrades.items()}

BLADES_BONUS: Final = config.integer('BLADES_BONUS')
MASTER_WEAPON_BONUS: Final = config.integer('MASTER_WEAPON_BONUS')
ARMOR_BONUS: Final = config.integer('ARMOR_BONUS')
ARROWS_BONUS: Final = config.integer('ARROWS_BONUS')
HORSES_BONUS: Final = config.number('HORSES_BONUS')
SIEGE_RANGE_BONUS: Final = config.number('SIEGE_RANGE_BONUS')
SIEGE_DAMAGE_BONUS: Final = config.number('SIEGE_DAMAGE_BONUS')
BLESSING_BONUS: Final = config.number('BLESSING_BONUS')
FRENZY_BONUS: Final = config.number('FRENZY_BONUS')
BLOODLUST_BONUS: Final = config.number('BLOODLUST_BONUS')
PLUNDER_SHARE: Final = config.number('PLUNDER_SHARE')
LONGBOWS_BONUS: Final = config.number('LONGBOWS_BONUS')
REGROWTH_SECONDS: Final = config.number('REGROWTH_SECONDS')
DEEP_MINING_TRIP: Final = config.integer('DEEP_MINING_TRIP')
BLASTING_POWDER_BONUS: Final = config.number('BLASTING_POWDER_BONUS')
SPLASH_FRACTION: Final = config.number('SPLASH_FRACTION')
DIRECT_HIT: Final = config.number('DIRECT_HIT')
WINDUP_SLACK: Final = config.number('WINDUP_SLACK')
ARROW_SPEED: Final = config.number('ARROW_SPEED')
STONE_SPEED: Final = config.number('STONE_SPEED')
STONE_MIN_FLIGHT: Final = config.number('STONE_MIN_FLIGHT')
HIT_VARIANCE: Final = config.number('HIT_VARIANCE')
#: How hard each kind of blow lands on each kind of armour, before armour is subtracted; a pairing not listed is 1.
#: The one place these multipliers live (WB-049).  Towers strike a normal blow.
DAMAGE_FACTORS: Final[dict[tuple[AttackType, ArmorClass], float]] = {
    (AttackType(b["attack"]), ArmorClass(b["armor"])): b["factor"] for b in config.current().damage_bonus
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


FRIENDLY_MARGIN: Final = config.number('FRIENDLY_MARGIN')
FRIENDLY_WORTH: Final = config.number('FRIENDLY_WORTH')
FORMATION_ARMOR: Final = config.integer('FORMATION_ARMOR')
FORMATION_SPACING: Final = config.number('FORMATION_SPACING')
FORMATION_WIDTH: Final = config.integer('FORMATION_WIDTH')
FORMATION_MARCH: Final = config.number('FORMATION_MARCH')
FORMATION_SLACK: Final = config.number('FORMATION_SLACK')
FORMATION_HOLD: Final = config.number('FORMATION_HOLD')
FORMATION_LOOKAHEAD: Final = config.number('FORMATION_LOOKAHEAD')
SIEGE_STEP: Final = config.number("SIEGE_STEP")
SIEGE_WORTH: Final[dict[UnitType, float]] = {UnitType(u): worth for u, worth in config.current().siege_worth.items()}
SIEGE_BUILDING_WORTH: Final = config.number("SIEGE_BUILDING_WORTH")

LUMBER_PER_TRIP: Final = config.integer('LUMBER_PER_TRIP')
CHOP_TIME: Final = config.number('CHOP_TIME')
REPAIR_RATE: Final = config.number('REPAIR_RATE')
REPAIR_CHUNK: Final = config.integer('REPAIR_CHUNK')
REPAIR_COST: Final = config.number('REPAIR_COST')


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
SALVAGE_RATE: Final = config.number('SALVAGE_RATE')
SALVAGE_HELD_RATE: Final = config.number('SALVAGE_HELD_RATE')
SALVAGE_CHUNK: Final = config.integer('SALVAGE_CHUNK')
SALVAGE_SHARE: Final = config.number('SALVAGE_SHARE')


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
MINE_GOLD: Final = config.integer('MINE_GOLD')
EXPANSION_GOLD: Final = config.integer('EXPANSION_GOLD')
STARTING_GOLD: Final = config.integer('STARTING_GOLD')
STARTING_LUMBER: Final = config.integer('STARTING_LUMBER')
#: The largest body any unit has: what a search that must not miss a unit whose body reaches into it pads by
#: (the bodies themselves are :attr:`UnitInfo.radius`).  A jittered rulebook never moves a radius, so this holds.
MAX_UNIT_RADIUS: Final = max(info.radius for info in UNITS.values())
LEASH: Final = config.number('LEASH')

# -- Creature camps ----------------------------------------------------------------
# A camp is a lair with its guards placed around it, and it resets rather than streaming.  A den that
# emitted units would either eat an army during the fight (no decision in it) or trickle so slowly that
# clearing it is beating down an undefended building; a camp that comes back once it is left alone makes
# the decision crisp instead -- clear the whole thing, lair and all, in one committed push and it is yours
# for good; break off and you paid units for nothing.
CAMP_WATCH: Final = config.number('CAMP_WATCH')
CAMP_HOLD: Final = config.number('CAMP_HOLD')
CAMP_CALM: Final = config.number('CAMP_CALM')
CAMP_REGEN: Final = config.number('CAMP_REGEN')
CAMP_RESPAWN: Final = config.number('CAMP_RESPAWN')
CAMP_POST: Final = config.number('CAMP_POST')
UNDER_ATTACK_COOLDOWN: Final = 20.0
SIM_DT: Final = 0.05  # the simulation runs at 20 Hz regardless of the frame rate
VISION_EVERY: Final = 4  # ticks between fog recomputations
MAX_PLANS: Final = 64  # settlement plans a player may have waiting: each is looked at every second and travels in every online snapshot
MAX_QUEUED_ORDERS: Final = 32  # orders a unit may have queued behind the one it is carrying out


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
