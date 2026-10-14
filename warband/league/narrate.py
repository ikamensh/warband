"""Match stories: what a match's thousands of unit-steps add up to, and why the winner won.

The telemetry (:mod:`warband.league.telemetry`) counts what was bought, lost
and killed, and the arena's style medians say how an agent generally plays,
but neither reads one match as a sequence of decisions.  A :class:`Narrator`
watches a world the way the telemetry does — it reads and never writes, so a
narrated match is the same match — and at the end tells its *story*:

* a five-second timeline per seat (workers, soldiers, army value and
  strength, the bank, supply, what stands),
* *episodes*, the logical actions the orders add up to: the opening build
  order, an expansion, a push, a defence, a camp cleared, a raid, a supply
  block with gold in hand,
* *battles*: the fights the hit and death events cluster into, each with the
  value both sides lost in it and where it happened,
* *factors*, one number per seat per thing that can decide a game (gold
  mined, seconds supply-blocked, value traded, workers killed, …), and
* a *verdict* for a duel: the two or three factors whose gap, priced in
  gold, accounts for most of the result, each with its numbers.  It is
  accounting, not causation — it says where the winner's edge accumulated,
  which is the question a brain change has to answer next.

Brain logs (``agent.log``) name the pushes and camp trips where a brain kept
them; everything else is read off the world and its events, so the same
narrator reads a human's replay, where there are no logs, through the orders
and events alone (``tools/replay_report.py`` drives that).

    from warband.league.arena import MatchSpec
    from warband.league.narrate import narrate, render
    print(render(narrate(MatchSpec(seed=7, agents=("master", "medium")))))
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from warband.brains.pro_force import strength
from warband.league.telemetry import PlayerTally, Telemetry, _price
from warband.sim import mapgen
from warband.sim.model import Event, Point, World, dist
from warband.sim.rules import SIM_DT, BuildingType, Layout, MapTheme, Race, UnitType

SAMPLE_SECONDS: Final = 5.0   # timeline rows: fine enough to see a block or a float, coarse enough to read
BATTLE_GAP: Final = 8.0       # seconds of quiet that end a battle
BATTLE_RADIUS: Final = 16.0   # tiles from a running battle's middle a blow still belongs to it
MIN_BATTLE_DAMAGE: Final = 150  # damage a cluster needs to count as a battle rather than a skirmish
BLOCK_GOLD: Final = 350       # a full supply cap only blocks a seat that could have spent this much gold
HOME_RADIUS: Final = 14.0     # tiles from a seat's nearest hall that make a fight "at its base"
CAMP_RADIUS: Final = 12.0     # tiles from a lair that make a fight a camp fight

#: The factor names :func:`factors_of` reports per seat, in report order.
FACTOR_FIELDS: Final = ("mined_gold", "gathered", "workers_peak", "supply_blocked_s", "avg_bank", "peak_bank",
                        "producer_idle_share", "halls_peak", "expand_s", "first_attack_s", "peak_army",
                        "peak_army_value", "kills_value", "losses_value", "net_trade", "damage_dealt",
                        "damage_taken", "worker_kills", "workers_lost", "camps_cleared", "hoard",
                        "upgrades", "casts", "towers_peak", "barracks_peak")


@dataclass
class PlayerSample:
    """One seat's affairs at one moment (see :data:`SAMPLE_SECONDS`)."""

    time: float
    gold: int
    lumber: int
    supply_used: int
    supply_cap: int
    workers: int
    soldiers: int
    army_value: int    # what the living soldiers cost, gold and lumber together
    army_strength: float  # pro_force.strength of them: the square-law fight in them
    worth: float       # everything standing, priced and wounded as the arena prices it
    halls: int
    barracks: int
    towers: int
    producers_idle: int  # finished military buildings with nothing queued
    producers: int
    upgrades: int


@dataclass(frozen=True)
class Episode:
    """One logical action: *kind* by *player* (None for a shared battle), from *start* to *end*."""

    player: int | None
    kind: str
    start: float
    end: float
    text: str
    facts: tuple[tuple[str, float], ...] = ()


@dataclass
class Battle:
    """A cluster of blows in one place at one time, and what each side lost in it."""

    start: float
    end: float
    x: float
    y: float
    place: str  # "P0 base" / "P1 base" / "a camp" / "open ground"
    damage_taken: dict[int, int] = field(default_factory=dict)   # seat -> hit points its side absorbed
    losses_value: dict[int, int] = field(default_factory=dict)   # seat -> price of what it lost
    deaths: dict[int, int] = field(default_factory=dict)         # seat -> units and buildings lost
    workers_lost: dict[int, int] = field(default_factory=dict)   # seat -> peasants among them
    wilds: bool = False  # a side in it was the neutral creatures

    @property
    def damage(self) -> int:
        return sum(self.damage_taken.values())

    def net_for(self, player: int) -> int:
        """Value the other seats lost minus what *player* lost: positive when the fight went its way."""
        theirs = sum(v for p, v in self.losses_value.items() if p != player)
        return theirs - self.losses_value.get(player, 0)


@dataclass
class Reason:
    """One line of a verdict: the factor, its gold-equivalent weight for the winner, and its sentence."""

    kind: str
    weight: float
    text: str


@dataclass
class MatchStory:
    """The whole reading of one match.  Plain data throughout, so it travels as JSON (:meth:`to_record`)."""

    agents: tuple[str, ...]
    seed: int
    races: tuple[str, ...]
    layout: str
    width: int
    height: int
    winner: int | None
    placements: tuple[int, ...]
    seconds: float
    samples: tuple[tuple[PlayerSample, ...], ...]  # by moment, then by seat
    episodes: tuple[Episode, ...]
    battles: tuple[Battle, ...]
    factors: tuple[dict[str, float], ...]  # by seat
    tallies: tuple[PlayerTally, ...]
    verdict: tuple[Reason, ...] = ()

    def to_record(self) -> dict:
        return {"agents": list(self.agents), "seed": self.seed, "races": list(self.races), "layout": self.layout,
                "width": self.width, "height": self.height, "winner": self.winner,
                "placements": list(self.placements), "seconds": self.seconds,
                "samples": [[vars(s) for s in row] for row in self.samples],
                "episodes": [{"player": e.player, "kind": e.kind, "start": e.start, "end": e.end,
                              "text": e.text, "facts": dict(e.facts)} for e in self.episodes],
                "battles": [{"start": b.start, "end": b.end, "x": b.x, "y": b.y, "place": b.place,
                             "damage_taken": b.damage_taken, "losses_value": b.losses_value,
                             "deaths": b.deaths, "workers_lost": b.workers_lost, "wilds": b.wilds}
                            for b in self.battles],
                "factors": [dict(f) for f in self.factors],
                "tallies": [t.to_record() for t in self.tallies],
                "verdict": [{"kind": r.kind, "weight": r.weight, "text": r.text} for r in self.verdict]}


# A blow as the battle clustering reads it: (time, x, y, victim seat or -1 for the wilds/nobody,
# damage, price of what fell, was it a peasant, did something fall).
_Blow = tuple[float, float, float, int, int, int, bool, bool]

_PRODUCERS: Final = frozenset({BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,
                               BuildingType.CHURCH})


class Narrator:
    """Watches one world and keeps what its story needs.  Feed it every step's events, then :meth:`finish`."""

    def __init__(self, world: World) -> None:
        self.seats = world.seats
        self.telemetry = Telemetry(world)
        self.samples: list[tuple[PlayerSample, ...]] = []
        self._next_sample = 0.0
        self._blows: list[_Blow] = []
        self.gathered: list[Counter] = [Counter() for _ in range(world.seats)]  # deposits home, by resource
        self.casts: list[tuple[float, int, str, Point]] = []
        # Where each seat's halls stood at each sample, and where the lairs stand: how a battle is placed.
        self._halls_at: list[tuple[tuple[Point, ...], ...]] = []
        self._lairs: tuple[Point, ...] = tuple(b.center for b in world.buildings.values()
                                                if b.type is BuildingType.LAIR)
        self._sample(world)

    def observe(self, world: World, events: list[Event]) -> None:
        self.telemetry.observe(world, events)
        for event in events:
            if event.kind == "hit" and event.amount:
                victim = event.player if event.player is not None and event.player < self.seats else -1
                self._blows.append((world.time, event.pos[0], event.pos[1], victim, event.amount, 0, False, False))
            elif event.kind in ("death", "destroyed"):
                victim = event.player if event.player is not None and event.player < self.seats else -1
                price = _price(world.players[victim].race, event.text) if victim >= 0 else 0
                self._blows.append((world.time, event.pos[0], event.pos[1], victim, 0, price,
                                    event.text == UnitType.PEASANT.value, True))
            elif event.kind == "deposit" and event.player is not None and event.player < self.seats:
                self.gathered[event.player][event.text] += event.amount
            elif event.kind == "cast" and event.player is not None and event.player < self.seats:
                self.casts.append((world.time, event.player, event.text, event.pos))
        if world.time >= self._next_sample:
            self._sample(world)

    def _sample(self, world: World) -> None:
        self._next_sample = world.time + SAMPLE_SECONDS
        row: list[PlayerSample] = []
        halls: list[tuple[Point, ...]] = []
        for seat in range(self.seats):
            player = world.players[seat]
            used, cap = world.supply(seat)
            units = [u for u in world.player_units(seat) if u.hp > 0]
            soldiers = [u for u in units if not u.is_worker]
            buildings = world.player_buildings(seat)
            producers = [b for b in buildings if b.done and b.type in _PRODUCERS]
            row.append(PlayerSample(
                time=world.time, gold=player.gold, lumber=player.lumber, supply_used=used, supply_cap=cap,
                workers=len(units) - len(soldiers), soldiers=len(soldiers),
                army_value=sum(u.info.cost.gold + u.info.cost.lumber for u in soldiers),
                army_strength=strength(world, soldiers) if soldiers else 0.0,
                worth=_worth(world, seat),
                halls=sum(1 for b in buildings if b.done and b.type is BuildingType.TOWN_HALL),
                barracks=sum(1 for b in buildings if b.done and b.type is BuildingType.BARRACKS),
                towers=sum(1 for b in buildings if b.done and b.type is BuildingType.TOWER),
                producers_idle=sum(1 for b in producers if not b.queue), producers=len(producers),
                upgrades=len(player.upgrades)))
            halls.append(tuple(b.center for b in buildings if b.type is BuildingType.TOWN_HALL))
        self.samples.append(tuple(row))
        self._halls_at.append(tuple(halls))

    def finish(self, world: World, *, agents: Sequence = (), agent_names: Sequence[str] = (),
               seed: int = 0, winner: int | None = None, placements: Sequence[int] = ()) -> MatchStory:
        """The story of the match as it stands.  *agents* are the brains, for their logs; a replay has none."""
        self.telemetry.finish(world)
        self._sample(world)
        battles = tuple(self._battles())
        episodes = tuple(sorted((*_log_episodes(agents), *_world_episodes(self, battles)),
                                key=lambda e: (e.start, e.player is not None)))
        names = tuple(agent_names) or tuple(f"P{p}" for p in range(self.seats))
        story = MatchStory(
            agents=names, seed=seed, races=tuple(p.race.value for p in world.players[:self.seats]),
            layout=world.layout.value, width=world.width, height=world.height,
            winner=winner if winner is not None else world.winner,
            placements=tuple(placements) or _placements(world, self.seats), seconds=world.time,
            samples=tuple(self.samples), episodes=episodes, battles=battles,
            factors=tuple(factors_of(self, seat, battles) for seat in range(self.seats)),
            tallies=self.telemetry.tallies)
        story.verdict = tuple(_verdict(story)) if self.seats == 2 else ()
        return story

    def _battles(self) -> list[Battle]:
        """Cluster the blows: one battle while the fighting stays within reach and never rests."""
        out: list[Battle] = []
        current: Battle | None = None
        weight = 0  # blows in the running battle, for its moving middle
        for time, x, y, victim, damage, price, worker, fell in sorted(self._blows):
            if current is None or time - current.end > BATTLE_GAP or dist((x, y), (current.x, current.y)) > BATTLE_RADIUS:
                if current is not None and current.damage >= MIN_BATTLE_DAMAGE:
                    out.append(current)
                current = Battle(start=time, end=time, x=x, y=y, place="open ground")
                weight = 0
            weight += 1
            current.x += (x - current.x) / weight
            current.y += (y - current.y) / weight
            current.end = time
            if victim < 0:
                current.wilds = True
            if damage:
                current.damage_taken[victim] = current.damage_taken.get(victim, 0) + damage
            if fell:
                current.losses_value[victim] = current.losses_value.get(victim, 0) + price
                current.deaths[victim] = current.deaths.get(victim, 0) + 1
                if worker:
                    current.workers_lost[victim] = current.workers_lost.get(victim, 0) + 1
        if current is not None and current.damage >= MIN_BATTLE_DAMAGE:
            out.append(current)
        for battle in out:
            battle.place = self._place(battle)
            for table in (battle.damage_taken, battle.losses_value, battle.deaths, battle.workers_lost):
                table.pop(-1, None)  # the wilds keep no column; their part is the flag and the place
        return out

    def _place(self, battle: Battle) -> str:
        point = (battle.x, battle.y)
        if any(dist(point, lair) <= CAMP_RADIUS for lair in self._lairs):
            return "a camp"
        row = min(range(len(self.samples)), key=lambda i: abs(self.samples[i][0].time - battle.start))
        for seat, halls in enumerate(self._halls_at[row]):
            if any(dist(point, hall) <= HOME_RADIUS for hall in halls):
                return f"P{seat} base"
        return "open ground"


def _worth(world: World, seat: int) -> float:
    """What a seat still has on the map, priced in gold and lumber, wounds counted (the arena's measure)."""
    total = 0.0
    for unit in world.units.values():
        if unit.player == seat and unit.hp > 0:
            total += (unit.info.cost.gold + unit.info.cost.lumber) * unit.hp / max(1, unit.max_hp)
    for building in world.player_buildings(seat):
        total += (building.info.cost.gold + building.info.cost.lumber) * building.hp / max(1, building.max_hp)
    return total


def _placements(world: World, seats: int) -> tuple[int, ...]:
    """Survivors by what they have left, then the fallen: enough for a story (the arena ranks its own)."""
    order = sorted(range(seats), key=lambda s: (not world.players[s].alive, -_worth(world, s)))
    out = [0] * seats
    for place, seat in enumerate(order, 1):
        out[seat] = place
    return tuple(out)


_LOG_KINDS: Final = (("attack", "push"), ("withdraw", "retreat"), ("defend", "defend"),
                     ("clear the camp", "creep"), ("camp cleared", "creep_done"),
                     ("break off the camp", "creep_off"), ("raid", "raid"),
                     ("rush:", "tower_rush"), ("strike tower", "strike_tower"),
                     ("hunt peasant", "hunt"), ("cast ", "cast"), ("prospect:", "prospect"),
                     ("siege answer", "siege_answer"), ("recover", "recover"))


def _log_episodes(agents: Sequence) -> list[Episode]:
    """The decisions a brain wrote down for itself, normalised to kinds (build/train trivia left out).

    A brain notes some of them every think for as long as they last (a Medium
    defence is a line twice a second), so a run of one kind with no kind
    between its lines is one episode spanning the run, its first line's text kept.
    """
    out: list[Episode] = []
    for seat, agent in enumerate(agents):
        run: Episode | None = None
        for time, what in getattr(agent, "log", []):
            kind = next((k for prefix, k in _LOG_KINDS if what.startswith(prefix)), None)
            if kind is None:
                continue
            if run is not None and run.kind == kind and time - run.end <= 10.0:
                run = Episode(run.player, run.kind, run.start, time, run.text)
                out[-1] = run
            else:
                run = Episode(seat, kind, time, time, what)
                out.append(run)
    return out


def _world_episodes(narrator: Narrator, battles: Sequence[Battle]) -> list[Episode]:
    """What the world itself shows: openings, expansions, research, blocks, casts and the battles."""
    out: list[Episode] = []
    for seat, tally in enumerate(narrator.telemetry.tallies):
        built = sorted((t, name) for name, t in tally.first.items()
                       if "." not in name and name in _BUILDING_NAMES)
        if built:
            out.append(Episode(seat, "opening", 0.0, built[-1][0],
                               "opening: " + ", ".join(f"{name} @{_clock(t)}" for t, name in built)))
        for name, t in sorted(tally.first.items(), key=lambda row: row[1]):
            if name in _UPGRADE_NAMES:
                out.append(Episode(seat, "research", t, t, f"researched {name}"))
        out.extend(_block_episodes(narrator, seat))
        expand = next((row[seat].time for row in narrator.samples if row[seat].halls >= 2), None)
        if expand is not None:
            out.append(Episode(seat, "expand", expand, expand, "second hall standing"))
    for time, seat, spell, _pos in narrator.casts:
        out.append(Episode(seat, "cast", time, time, f"cast {spell}"))
    for battle in battles:
        losses = ", ".join(f"P{p} lost {v}" for p, v in sorted(battle.losses_value.items()) if v)
        out.append(Episode(None, "battle", battle.start, battle.end,
                           f"battle at {battle.place} ({battle.damage} damage{'; ' + losses if losses else ''})",
                           facts=(("damage", float(battle.damage)),)))
    return out


def _block_episodes(narrator: Narrator, seat: int) -> list[Episode]:
    """Stretches at a full supply cap with gold unspent: the mirror-match killer (docs/ai-ladder.md)."""
    out: list[Episode] = []
    start: float | None = None
    peak = 0
    rows = narrator.samples
    for row in rows:
        sample = row[seat]
        blocked = sample.supply_used >= sample.supply_cap > 0 and sample.gold >= BLOCK_GOLD
        if blocked and start is None:
            start, peak = sample.time, sample.gold
        elif blocked:
            peak = max(peak, sample.gold)
        elif start is not None:
            if sample.time - start >= SAMPLE_SECONDS * 2:
                out.append(Episode(seat, "supply_block", start, sample.time,
                                   f"supply-blocked {sample.time - start:.0f}s with up to {peak} gold banked",
                                   facts=(("blocked_s", sample.time - start), ("peak_gold", float(peak)))))
            start = None
    if start is not None and rows and rows[-1][seat].time - start >= SAMPLE_SECONDS * 2:
        out.append(Episode(seat, "supply_block", start, rows[-1][seat].time,
                           f"supply-blocked {rows[-1][seat].time - start:.0f}s with up to {peak} gold banked",
                           facts=(("blocked_s", rows[-1][seat].time - start), ("peak_gold", float(peak)))))
    return out


from warband.sim.rules import UPGRADES  # noqa: E402 - after the episode helpers that name tables

_BUILDING_NAMES: Final = frozenset(t.value for t in BuildingType)
_UPGRADE_NAMES: Final = frozenset(u.value for u in UPGRADES)


def factors_of(narrator: Narrator, seat: int, battles: Sequence[Battle]) -> dict[str, float]:
    """One seat's numbers for everything that can decide a game (see :data:`FACTOR_FIELDS`)."""
    tally = narrator.telemetry.tallies[seat]
    rows = [row[seat] for row in narrator.samples]
    race = Race(tally.race)
    losses = sum(_price(race, name) * n for name, n in tally.lost.items()) \
        + sum(_price(race, name) * n for name, n in tally.razed.items())
    blocked = sum(SAMPLE_SECONDS for s in rows if s.supply_used >= s.supply_cap > 0 and s.gold >= BLOCK_GOLD)
    producing = [s for s in rows if s.producers]
    late = [s for s in rows if s.time >= 60.0] or rows
    attacks = [b.start for b in battles if b.place == f"P{1 - seat} base"] if narrator.seats == 2 else []
    return {
        "mined_gold": float(sum(tally.mined.values())),
        "gathered": float(sum(narrator.gathered[seat].values())),
        "workers_peak": float(max((s.workers for s in rows), default=0)),
        "supply_blocked_s": float(blocked),
        "avg_bank": statistics.fmean(s.gold + s.lumber for s in late) if late else 0.0,
        "peak_bank": float(max((s.gold + s.lumber for s in rows), default=0)),
        "producer_idle_share": (statistics.fmean(s.producers_idle / s.producers for s in producing)
                                if producing else 0.0),
        "halls_peak": float(max((s.halls for s in rows), default=0)),
        "expand_s": next((s.time for s in rows if s.halls >= 2), math.nan),
        "first_attack_s": min(attacks) if attacks else math.nan,
        "peak_army": float(max((s.soldiers for s in rows), default=0)),
        "peak_army_value": float(max((s.army_value for s in rows), default=0)),
        "kills_value": float(sum(tally.kill_value.values())),
        "losses_value": float(losses),
        "net_trade": float(sum(tally.kill_value.values()) - losses),
        "damage_dealt": float(sum(tally.dealt.values())),
        "damage_taken": float(sum(tally.taken.values())),
        "worker_kills": float(tally.killed.get(UnitType.PEASANT.value, 0)),
        "workers_lost": float(tally.lost.get(UnitType.PEASANT.value, 0)),
        "camps_cleared": float(tally.camps_cleared),
        "hoard": float(tally.hoard),
        "upgrades": float(sum(tally.researched.values())),
        "casts": float(sum(tally.cast.values())),
        "towers_peak": float(max((s.towers for s in rows), default=0)),
        "barracks_peak": float(max((s.barracks for s in rows), default=0)),
    }


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _verdict(story: MatchStory) -> list[Reason]:
    """Why the winner of a duel won, as accounting: the largest gold-priced gaps that favour it."""
    if story.winner is None:
        leader = story.placements.index(1)
        if story.samples and abs(story.samples[-1][0].worth - story.samples[-1][1].worth) < 500:
            return [Reason("even", 0.0, "no winner: the seats ended within 500 of each other in worth")]
        win = leader
    else:
        win = story.winner
    lose = 1 - win
    w, l = story.factors[win], story.factors[lose]
    out: list[Reason] = []

    def add(kind: str, weight: float, text: str) -> None:
        if weight > 0:
            out.append(Reason(kind, weight, text))

    mined = w["mined_gold"] - l["mined_gold"]
    add("mining", mined, f"out-mined P{lose} by {mined:.0f} gold ({w['mined_gold']:.0f} to {l['mined_gold']:.0f})")
    add("trade", w["net_trade"],
        f"out-traded P{lose}: killed {w['kills_value']:.0f} of value for {w['losses_value']:.0f} lost "
        f"(P{lose}: {l['kills_value']:.0f} for {l['losses_value']:.0f})")
    blocked = l["supply_blocked_s"] - w["supply_blocked_s"]
    add("supply", blocked * 12.0,
        f"P{lose} sat supply-blocked {l['supply_blocked_s']:.0f}s with gold in hand against P{win}'s "
        f"{w['supply_blocked_s']:.0f}s")
    floated = l["avg_bank"] - w["avg_bank"]
    add("float", floated * 0.5, f"P{lose} floated more unspent (bank averaging {l['avg_bank']:.0f} "
                                f"against {w['avg_bank']:.0f}) while its producers idled "
                                f"{l['producer_idle_share']:.0%} of sampled time")
    add("camps", w["hoard"] - l["hoard"],
        f"took {w['hoard']:.0f} of camp hoards (P{lose}: {l['hoard']:.0f}) from {w['camps_cleared']:.0f} camps")
    raided = w["worker_kills"] - l["worker_kills"]
    add("raid", raided * 450.0, f"killed {w['worker_kills']:.0f} of P{lose}'s peasants "
                                f"(lost {w['workers_lost']:.0f} of its own)")
    add("tech", (w["upgrades"] - l["upgrades"]) * 400.0,
        f"researched {w['upgrades']:.0f} upgrades to P{lose}'s {l['upgrades']:.0f}")
    if w["halls_peak"] > l["halls_peak"]:
        add("expansion", 900.0 * (w["halls_peak"] - l["halls_peak"]),
            f"held {w['halls_peak']:.0f} halls to P{lose}'s {l['halls_peak']:.0f}")
    clash = next((b for b in story.battles if not b.wilds and len(b.losses_value) > 1), None)
    if clash is not None and clash.net_for(win) > 600:
        add("first_clash", float(clash.net_for(win)),
            f"won the first clash at {_clock(clash.start)} on {clash.place}: "
            f"P{lose} lost {clash.losses_value.get(lose, 0)} of value, P{win} {clash.losses_value.get(win, 0)}")
    if not math.isnan(w["first_attack_s"]) and (math.isnan(l["first_attack_s"])
                                                or l["first_attack_s"] - w["first_attack_s"] > 60):
        add("tempo", 500.0, f"attacked first, at {_clock(w['first_attack_s'])}"
                            + (f" against {_clock(l['first_attack_s'])}" if not math.isnan(l["first_attack_s"]) else ""))
    out.sort(key=lambda r: -r.weight)
    return out[:3] if out else [Reason("even", 0.0, "won on accumulated small edges; no single factor dominates")]


def narrate(spec, *, settle: bool = True) -> MatchStory:
    """Play one :class:`warband.league.arena.MatchSpec` and tell its story (the arena plays its own)."""
    from warband.league import arena  # late: the arena registers every agent at import

    arena.ensure_variant(spec.variant)
    races = tuple(Race(r) for r in spec.races) if spec.races is not None else None
    world = mapgen.generate(seed=spec.seed, width=spec.width, height=spec.height, players=spec.players,
                            human=None, theme=MapTheme(spec.theme), races=races,
                            layout=Layout(spec.layout) if spec.layout is not None else None, wilds=spec.wilds,
                            prize=BuildingType(spec.prize) if spec.prize is not None else None)
    agents = [arena.make_agent(name, player, spec.seed) for player, name in enumerate(spec.agents)]
    rngs = [random.Random(spec.seed * 1000003 + player) for player in range(spec.players)]
    narrator = Narrator(world)
    eliminated: dict[int, float] = {}
    leader: int | None = None
    leader_since = 0.0
    settled: int | None = None
    steps = 0
    for _ in range(int(spec.minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for agent, rng in zip(agents, rngs):
            agent.think(world, rng)
        world.step()
        narrator.observe(world, world.take_events())
        steps += 1
        for player in world.players[:spec.players]:
            if not player.alive and player.id not in eliminated:
                eliminated[player.id] = world.time
        if settle and steps % arena.SETTLED_EVERY == 0:
            ahead = arena._runaway(world, eliminated, spec.players)
            if ahead is None or ahead != leader:
                leader, leader_since = ahead, world.time
            elif world.time - leader_since >= arena.SETTLED_SECONDS:
                settled = leader
                break
    winner = world.winner if world.winner is not None else settled
    story = narrator.finish(world, agents=agents, agent_names=spec.agents, seed=spec.seed, winner=winner,
                            placements=arena._placements(world, eliminated, spec.players))
    for seat, factors in enumerate(story.factors):
        pushes = [e.start for e in story.episodes if e.player == seat and e.kind == "push"]
        if pushes:
            factors["first_attack_s"] = min(pushes)
    story.verdict = tuple(_verdict(story)) if story.placements and len(story.agents) == 2 else story.verdict
    return story


def render(story: MatchStory, *, max_episodes: int = 48) -> str:
    """The story as a page of text: header, the minute-by-minute state, episodes, factors, verdict."""
    seats = len(story.agents)
    lines = [f"seed {story.seed} · {story.layout} {story.width}x{story.height} · {_clock(story.seconds)} · "
             + ("no winner" if story.winner is None else f"P{story.winner} ({story.agents[story.winner]}) wins")]
    for seat in range(seats):
        lines.append(f"  P{seat} {story.agents[seat]:<14} {story.races[seat]}")
    head = "  " + " ".join(f"P{s} wkr/sold/army/bank" for s in range(seats))
    lines += ["", " time  " + head]
    minute = -1
    for row in story.samples:
        if int(row[0].time // 60) == minute and row is not story.samples[-1]:
            continue
        minute = int(row[0].time // 60)
        cells = "  ".join(f"{s.workers:>2}/{s.soldiers:>2}/{s.army_value:>5}/{s.gold + s.lumber:>5}" for s in row)
        lines.append(f" {_clock(row[0].time):>5}  {cells}")
    lines += ["", " episodes:"]
    shown = [e for e in story.episodes if e.kind != "research"][:max_episodes]
    for e in shown:
        who = "  · " if e.player is None else f" P{e.player} "
        span = f"-{_clock(e.end)}" if e.end - e.start > 1.0 else ""
        lines.append(f"  {_clock(e.start):>5}{span:<6}{who}{e.text}")
    if len(story.episodes) > len(shown):
        lines.append(f"  … {len(story.episodes) - len(shown)} more (research lines and overflow)")
    lines += ["", " factors:"]
    lines.append("  " + "".join(f"{'P' + str(s):>12}" for s in range(seats)) + "  factor")
    for name in FACTOR_FIELDS:
        cells = "".join(f"{'-':>12}" if math.isnan(story.factors[s][name])
                        else f"{story.factors[s][name]:>12.2f}" if name == "producer_idle_share"
                        else f"{story.factors[s][name]:>12.0f}" for s in range(seats))
        lines.append(f"  {cells}  {name}")
    if story.verdict:
        claim = f"P{story.winner} won" if story.winner is not None else f"P{story.placements.index(1)} leads"
        lines += ["", f" verdict — why {claim}:"]
        lines += [f"  - {r.text}" for r in story.verdict]
    return "\n".join(lines)


def factor_gaps(stories: Iterable[MatchStory]) -> dict[str, tuple[float, float]]:
    """Per factor, the median winner's and loser's value over decided duels: what winning looks like."""
    won: dict[str, list[float]] = {f: [] for f in FACTOR_FIELDS}
    lost: dict[str, list[float]] = {f: [] for f in FACTOR_FIELDS}
    for story in stories:
        if len(story.agents) != 2 or story.winner is None:
            continue
        for f in FACTOR_FIELDS:
            for table, seat in ((won, story.winner), (lost, 1 - story.winner)):
                value = story.factors[seat][f]
                if not math.isnan(value):
                    table[f].append(value)
    return {f: (statistics.median(won[f]) if won[f] else math.nan,
                statistics.median(lost[f]) if lost[f] else math.nan) for f in FACTOR_FIELDS}


def lead_holds(stories: Iterable[MatchStory], at: float, key: str = "worth") -> tuple[float, int]:
    """How often the seat ahead on *key* (a sample field) at *at* seconds won a decided duel, and over how many."""
    held = total = 0
    for story in stories:
        if len(story.agents) != 2 or story.winner is None or not story.samples:
            continue
        row = min(story.samples, key=lambda r: abs(r[0].time - at))
        if abs(row[0].time - at) > SAMPLE_SECONDS or getattr(row[0], key) == getattr(row[1], key):
            continue
        total += 1
        held += int((getattr(row[0], key) > getattr(row[1], key)) == (story.winner == 0))
    return (held / total if total else math.nan, total)


def autopsy(stories: Iterable[MatchStory], agent: str) -> list[str]:
    """How *agent* loses its decided duels: its opponents' verdict lines, counted, with the median deficits."""
    losses = [s for s in stories if len(s.agents) == 2 and s.winner is not None
              and agent in s.agents and s.agents[s.winner] != agent]
    if not losses:
        return [f"{agent} lost no decided duel in these stories"]
    kinds = Counter(r.kind for s in losses for r in s.verdict[:1])
    lines = [f"{agent} lost {len(losses)} decided duels; the top verdict line against it:"]
    lines += [f"  {kind}: {n}" for kind, n in kinds.most_common()]
    for f in ("mined_gold", "supply_blocked_s", "net_trade", "workers_peak", "peak_army_value", "first_attack_s"):
        mine = [s.factors[s.agents.index(agent)][f] for s in losses]
        theirs = [s.factors[1 - s.agents.index(agent)][f] for s in losses]
        mine = [v for v in mine if not math.isnan(v)]
        theirs = [v for v in theirs if not math.isnan(v)]
        if mine and theirs:
            lines.append(f"  in those losses, median {f}: {statistics.median(mine):.0f} "
                         f"against the winner's {statistics.median(theirs):.0f}")
    return lines
