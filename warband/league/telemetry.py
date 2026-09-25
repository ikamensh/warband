"""What a match records about itself: purchases, blows, kills and the bank, per player.

The balance readout (`tools/balance_report.py`) is built from these tallies
rather than from watching matches, so every number it prints is a count of
something the simulation did.  A :class:`Telemetry` watches one
:class:`~warband.sim.model.World` through the events it emits; it reads the
world and never writes it, so a tallied match is the same match.

    telemetry = Telemetry(world)
    while ...:
        world.step()
        telemetry.observe(world, world.take_events())
    telemetry.finish(world)
    telemetry.tallies[0].killed["knight"]   # knights of other players this one put down

Keys are the rule tables' string values (``"footman"``, ``"farm"``,
``"blades_1"``), which are distinct across units, buildings and upgrades and
travel between processes as plain data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from warband.sim.model import Building, Event, Unit, World, dist, unit_stats
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, Race, Resource, UnitType, Upgrade

SAMPLE_EVERY = 60.0  # seconds of simulation between rows of the timeline
LOOK_INSIDE_EVERY = 10  # steps between looks at who is inside which deposit: a trip is MINE_TIME (5 s) at the face
HALL_AT = 8.0  # tiles from a hall's middle to a deposit's that make it that deposit's hall (brains.ai.CLAIM_DISTANCE)


@dataclass
class Sample:
    """The state of one player's affairs at one moment."""

    time: float
    gold: int
    lumber: int
    supply_used: int
    supply_cap: int
    peasants: int
    soldiers: int
    army_value: int  # what the soldiers alive cost, gold and lumber together


@dataclass
class PlayerTally:
    race: str
    trained: Counter[str] = field(default_factory=Counter)   # units that came out of a building
    started: Counter[str] = field(default_factory=Counter)   # buildings a peasant began (and paid for)
    completed: Counter[str] = field(default_factory=Counter)
    researched: Counter[str] = field(default_factory=Counter)
    spent: Counter[str] = field(default_factory=Counter)     # gold and lumber together, per thing bought
    first: dict[str, float] = field(default_factory=dict)    # sim seconds when each thing was first finished
    lost: Counter[str] = field(default_factory=Counter)      # own units that died, by type
    razed: Counter[str] = field(default_factory=Counter)     # own buildings destroyed, by type
    killed: Counter[str] = field(default_factory=Counter)    # other players' units this one put down, by victim type
    destroyed: Counter[str] = field(default_factory=Counter)  # other players' buildings, by type
    kill_value: Counter[str] = field(default_factory=Counter)  # cost of what each own unit type (or "tower") put down
    dealt: Counter[str] = field(default_factory=Counter)     # damage landed by each own unit type
    taken: Counter[str] = field(default_factory=Counter)     # damage received by each own unit or building type
    friendly: Counter[str] = field(default_factory=Counter)  # damage own siege landed on own side, by victim type
    lost_to_wilds: Counter[str] = field(default_factory=Counter)  # own units a neutral creature put down, by type
    camps_cleared: int = 0  # creature lairs this player tore down: a camp is cleared for good only when the lair falls
    hoard: int = 0  # gold taken out of the lairs it tore down
    # Gold brought home, by the kind of deposit it came out of (WB-071: who works the lode, and how much).  When a seat
    # first did it is in ``first`` as "mined.<kind>", and when its first hall stood beside one as "hall.<kind>".
    mined: Counter[str] = field(default_factory=Counter)
    unattributed: int = 0  # blows whose striker was gone before the event was read (no dealt/kill credit)
    timeline: list[Sample] = field(default_factory=list)

    @property
    def army_spent(self) -> int:
        return sum(v for k, v in self.spent.items() if k in _UNIT_NAMES and k != UnitType.PEASANT.value)

    def to_record(self) -> dict:
        """Plain JSON data. ``dataclasses.asdict`` is no use here: it rebuilds a Counter from its
        (key, count) pairs, which counts the pairs."""
        row = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in vars(self).items() if k != "timeline"}
        row["timeline"] = [vars(sample).copy() for sample in self.timeline]
        return row

    @classmethod
    def from_record(cls, row: dict) -> "PlayerTally":
        row = dict(row)
        timeline = [Sample(**sample) for sample in row.pop("timeline")]
        counters = {k: Counter(v) for k, v in row.items() if isinstance(v, dict) and k != "first"}
        rest = {k: v for k, v in row.items() if k not in counters}
        return cls(**rest, **counters, timeline=timeline)


_UNIT_NAMES = frozenset(t.value for t in UnitType)  # the wilds too: a creature costs nothing and still has a price
_BUILDING_NAMES = frozenset(t.value for t in BuildingType)


def _price(race: Race, key: str) -> int:
    """What *key* (a unit, building or upgrade value) costs *race*, gold and lumber together."""
    if key in _UNIT_NAMES:
        cost = unit_stats(race, UnitType(key)).cost  # a creature is nobody's: no race names one, and it costs nothing
    elif key in _BUILDING_NAMES:
        cost = RACES[race].buildings[BuildingType(key)].cost
    else:
        cost = UPGRADES[Upgrade(key)].cost
    return cost.gold + cost.lumber


class Telemetry:
    def __init__(self, world: World) -> None:
        # One tally per playing seat.  The wilds keep none: what a creature killed is its victim's loss and
        # the razer's kill, and nobody reads a column for a side that buys nothing and never wins.
        self.tallies: tuple[PlayerTally, ...] = tuple(PlayerTally(race=p.race.value) for p in world.players[:world.seats])
        self._last_hitter: dict[int, tuple[int, str]] = {}  # target id → (striker's player, striker's type)
        # Whose each recruit was: a striker gone before its blow is read -- a sapper spent in its own blast -- is still
        # credited with what the blow did.
        self._recruits: dict[int, tuple[int, str]] = {}
        self._inside: dict[int, str] = {}  # peasant id → the kind of deposit it was last seen working
        self._steps = 0
        self._next_sample = 0.0
        self.observe(world, [])

    def observe(self, world: World, events: list[Event]) -> None:
        if self._steps % LOOK_INSIDE_EVERY == 0:
            for unit in world.units.values():
                if unit.inside is not None:
                    deposit = world.buildings.get(unit.inside)
                    if deposit is not None:
                        self._inside[unit.id] = deposit.type.value
        self._steps += 1
        for event in events:
            handler = _HANDLERS.get(event.kind)
            if handler is not None:
                handler(self, world, event)
        if world.time >= self._next_sample:
            self._sample(world)
            self._next_sample += SAMPLE_EVERY

    def finish(self, world: World) -> None:
        """The closing row of every timeline: the match as it stood when it ended."""
        self._sample(world)

    def _sample(self, world: World) -> None:
        for player, tally in zip(world.players, self.tallies):
            used, cap = world.supply(player.id)
            units = [u for u in world.player_units(player.id) if u.hp > 0]
            soldiers = [u for u in units if not u.is_worker]
            tally.timeline.append(Sample(
                time=world.time, gold=player.gold, lumber=player.lumber, supply_used=used, supply_cap=cap,
                peasants=len(units) - len(soldiers), soldiers=len(soldiers),
                army_value=sum(u.info.cost.gold + u.info.cost.lumber for u in soldiers)))

    # -- Purchases ----------------------------------------------------------------

    def _trained(self, world: World, event: Event) -> None:
        tally = self.tallies[event.player]
        key = event.target_type
        if event.entity is not None:
            self._recruits[event.entity] = (event.player, key)
        tally.trained[key] += 1
        tally.spent[key] += _price(world.players[event.player].race, key)
        tally.first.setdefault(key, world.time)

    def _construction(self, world: World, event: Event) -> None:
        tally = self.tallies[event.player]
        key = event.target_type
        tally.started[key] += 1
        tally.spent[key] += _price(world.players[event.player].race, key)

    def _built(self, world: World, event: Event) -> None:
        tally = self.tallies[event.player]
        tally.completed[event.target_type] += 1
        tally.first.setdefault(event.target_type, world.time)
        if event.target_type == BuildingType.TOWN_HALL.value:
            beside = [m for m in world.mines() if dist(m.center, event.pos) <= HALL_AT]
            if beside:
                tally.first.setdefault(f"hall.{min(beside, key=lambda m: dist(m.center, event.pos)).type.value}", world.time)

    def _deposit(self, world: World, event: Event) -> None:
        """A peasant brought its load home: gold is booked to the kind of deposit it was last seen working."""
        tally = self._tally(event.player)
        if tally is None or event.text != Resource.GOLD.value:
            return
        kind = self._inside.get(event.entity)
        if kind is None:
            return  # gold from a lair's hoard or a salvaged ruin comes home without a trip
        tally.mined[kind] += event.amount
        tally.first.setdefault(f"mined.{kind}", world.time)

    def _researched(self, world: World, event: Event) -> None:
        upgrade = Upgrade(event.target_type)  # never the event's text: each race names its own Keep
        tally = self.tallies[event.player]
        tally.researched[upgrade.value] += 1
        tally.spent[upgrade.value] += UPGRADES[upgrade].cost.gold + UPGRADES[upgrade].cost.lumber
        tally.first.setdefault(upgrade.value, world.time)

    # -- Blows --------------------------------------------------------------------

    def _tally(self, player: int | None) -> PlayerTally | None:
        """The seat's tally, or None for the wilds and for what nobody owns."""
        return self.tallies[player] if player is not None and player < len(self.tallies) else None

    def _hit(self, world: World, event: Event) -> None:
        victim = self._tally(event.player)
        if victim is not None:
            victim.taken[event.target_type] += event.amount
        striker = world.entity(event.entity)
        if striker is not None:
            owner, striker_type = striker.player, striker.type.value
        elif event.entity in self._recruits:
            owner, striker_type = self._recruits[event.entity]
        else:
            if victim is not None:
                victim.unattributed += 1
            return
        if owner == event.player:
            if victim is not None:
                victim.friendly[event.target_type] += event.amount
            return
        dealer = self._tally(owner)
        if dealer is not None:
            dealer.dealt[striker_type] += event.amount
        self._last_hitter[event.other] = (owner, striker_type)

    def _death(self, world: World, event: Event) -> None:
        victim = self._tally(event.player)
        self._fallen(event, victim.lost if victim is not None else None, "killed", victim)

    def _destroyed(self, world: World, event: Event) -> None:
        victim = self._tally(event.player)
        self._fallen(event, victim.razed if victim is not None else None, "destroyed", victim)

    def _hoard(self, world: World, event: Event) -> None:
        tally = self._tally(event.player)
        if tally is not None:
            tally.hoard += event.amount

    def _fallen(self, event: Event, lost: Counter[str] | None, credit: str, victim: PlayerTally | None) -> None:
        if lost is not None:
            lost[event.text] += 1
        hitter = self._last_hitter.pop(event.entity, None)
        if hitter is None:
            return
        player, striker_type = hitter
        tally = self._tally(player)
        if tally is None:
            # A creature's kill.  The wilds keep no book of their own, so what is recorded is the seat's
            # side of it: units lost to a camp are the measure of a brain that feeds one.
            if victim is not None and credit == "killed":
                victim.lost_to_wilds[event.text] += 1
            return
        getattr(tally, credit)[event.text] += 1
        if event.text == BuildingType.LAIR.value:
            tally.camps_cleared += 1  # the lair is the camp: cleared for good only once it is down
        # A creature and its lair cost nothing, so clearing a camp adds no kill value: the hoard is
        # what that is worth, and it arrives as gold.
        tally.kill_value[striker_type] += _price(Race(victim.race if victim is not None else tally.race), event.text)


_HANDLERS = {
    "deposit": Telemetry._deposit,
    "hoard": Telemetry._hoard,
    "trained": Telemetry._trained,
    "construction": Telemetry._construction,
    "built": Telemetry._built,
    "researched": Telemetry._researched,
    "hit": Telemetry._hit,
    "death": Telemetry._death,
    "destroyed": Telemetry._destroyed,
}
