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

from warband.sim.model import Building, Event, Unit, World
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, Race, UnitType, Upgrade

SAMPLE_EVERY = 60.0  # seconds of simulation between rows of the timeline


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


_UNIT_NAMES = frozenset(t.value for t in UnitType)
_BUILDING_NAMES = frozenset(t.value for t in BuildingType)
_UPGRADE_BY_NAME = {info.name: upgrade for upgrade, info in UPGRADES.items()}


def _price(race: Race, key: str) -> int:
    """What *key* (a unit, building or upgrade value) costs *race*, gold and lumber together."""
    if key in _UNIT_NAMES:
        cost = RACES[race].units[UnitType(key)].cost
    elif key in _BUILDING_NAMES:
        cost = RACES[race].buildings[BuildingType(key)].cost
    else:
        cost = UPGRADES[Upgrade(key)].cost
    return cost.gold + cost.lumber


class Telemetry:
    def __init__(self, world: World) -> None:
        self.tallies: tuple[PlayerTally, ...] = tuple(PlayerTally(race=p.race.value) for p in world.players)
        self._last_hitter: dict[int, tuple[int, str]] = {}  # target id → (striker's player, striker's type)
        self._next_sample = 0.0
        self.observe(world, [])

    def observe(self, world: World, events: list[Event]) -> None:
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
        unit = world.units[event.entity]
        tally = self.tallies[event.player]
        key = unit.type.value
        tally.trained[key] += 1
        tally.spent[key] += unit.info.cost.gold + unit.info.cost.lumber
        tally.first.setdefault(key, world.time)

    def _construction(self, world: World, event: Event) -> None:
        building = world.buildings[event.entity]
        tally = self.tallies[event.player]
        key = building.type.value
        tally.started[key] += 1
        tally.spent[key] += building.info.cost.gold + building.info.cost.lumber

    def _built(self, world: World, event: Event) -> None:
        building = world.buildings[event.entity]
        tally = self.tallies[event.player]
        tally.completed[building.type.value] += 1
        tally.first.setdefault(building.type.value, world.time)

    def _researched(self, world: World, event: Event) -> None:
        upgrade = _UPGRADE_BY_NAME[event.text]
        tally = self.tallies[event.player]
        tally.researched[upgrade.value] += 1
        tally.spent[upgrade.value] += UPGRADES[upgrade].cost.gold + UPGRADES[upgrade].cost.lumber
        tally.first.setdefault(upgrade.value, world.time)

    # -- Blows --------------------------------------------------------------------

    def _hit(self, world: World, event: Event) -> None:
        victim = self.tallies[event.player] if event.player is not None else None
        if victim is not None:
            victim.taken[event.target_type] += event.amount
        striker = world.entity(event.entity)
        if striker is None:
            if victim is not None:
                victim.unattributed += 1
            return
        striker_type = striker.type.value
        if striker.player == event.player:
            if victim is not None:
                victim.friendly[event.target_type] += event.amount
            return
        self.tallies[striker.player].dealt[striker_type] += event.amount
        self._last_hitter[event.other] = (striker.player, striker_type)

    def _death(self, world: World, event: Event) -> None:
        self._fallen(event, self.tallies[event.player].lost, "killed")

    def _destroyed(self, world: World, event: Event) -> None:
        if event.player is None:
            return
        self._fallen(event, self.tallies[event.player].razed, "destroyed")

    def _fallen(self, event: Event, lost: Counter[str], credit: str) -> None:
        lost[event.text] += 1
        hitter = self._last_hitter.pop(event.entity, None)
        if hitter is None:
            return
        player, striker_type = hitter
        tally = self.tallies[player]
        getattr(tally, credit)[event.text] += 1
        tally.kill_value[striker_type] += _price(Race(self.tallies[event.player].race), event.text)


_HANDLERS = {
    "trained": Telemetry._trained,
    "construction": Telemetry._construction,
    "built": Telemetry._built,
    "researched": Telemetry._researched,
    "hit": Telemetry._hit,
    "death": Telemetry._death,
    "destroyed": Telemetry._destroyed,
}
