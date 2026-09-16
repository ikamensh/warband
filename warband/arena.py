"""The ladder: headless matches between AI agents, and the ratings that come out of them.

The difficulties Warband ships are only as good as the evidence that ranks
them, so the ranking lives next to the AI rather than in a script. Nothing
here touches saga2d — it is the model, the agents and arithmetic.

    from warband.arena import MatchSpec, play, rate
    result = play(MatchSpec(seed=1, agents=("hard", "normal")))

Three things it has to get right:

*Fairness.* A match is fully determined by its :class:`MatchSpec`, and every
pairing is played from both sides of the same map (``mirrored``), so a seed
that favours the north-west corner cannot favour an agent.

*Free-for-all.* Three and four player games finish with a placement per
player, not a winner: whoever is eliminated last places higher, and players
still standing at the time cap are ranked by what they have left on the map.

*Ratings that survive perfect records.* Sequential Elo depends on the order
the games are fed in, and a agent that never loses runs away to infinity.
:func:`rate` instead fits a Bradley-Terry model over all pairwise results at
once (order-independent), smoothed with half a virtual win and loss per pair
that actually met, and reports a bootstrap interval. The scale is Elo's, and
one agent is anchored so the numbers mean something across runs.
"""

from __future__ import annotations

import math
import random
import statistics
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from warband import mapgen
from warband.ai import make_brain
from warband.model import World
from warband.races import RACES
from warband.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, Difficulty, MapTheme, Race, SIM_DT, UnitType, Upgrade
from warband.telemetry import PlayerTally, Telemetry

ELO_SCALE = 400.0 / math.log(10.0)  # Elo points per unit of Bradley-Terry log-strength
DEFAULT_MINUTES = 20.0


# -- Agents ------------------------------------------------------------------------

class Agent:
    """What the arena needs of a brain: ``think`` once per simulation step.

    :class:`warband.ai.Brain` and :class:`warband.pro_ai.ProBrain` satisfy this
    already; the protocol is written down so new agents have something to
    implement.
    """

    def think(self, world: World, rng: random.Random) -> None:  # pragma: no cover - interface
        raise NotImplementedError


AgentFactory = Callable[[int], Agent]
#: Name → how to build that agent for a player slot. Names travel between
#: processes, so the arena can hand a match to a worker as plain data.
AGENTS: dict[str, AgentFactory] = {}


def register(name: str, factory: AgentFactory) -> None:
    """Make *name* playable. Registering a name twice is a mistake, not an update."""
    if name in AGENTS:
        raise ValueError(f"agent {name!r} is already registered")
    AGENTS[name] = factory


def make_agent(name: str, player: int) -> Agent:
    if name not in AGENTS:
        raise KeyError(f"unknown agent {name!r}; known: {', '.join(sorted(AGENTS))}")
    return AGENTS[name](player)


# The shipped settings, under their own names. Hard and Master are ProBrain
# profiles, so these overlap with the pro-* names below; both spellings play.
for _difficulty in Difficulty:
    register(_difficulty.value, lambda player, d=_difficulty: make_brain(player, d))

from warband.pro_ai import PRO_PROFILES, ProBrain  # noqa: E402 - after register() exists

for _name, _profile in PRO_PROFILES.items():
    register(_name, lambda player, p=_profile: ProBrain(player, p))

from warband.archetypes import ARCHETYPES  # noqa: E402 - the balance league's postures play under their names too

for _profile in ARCHETYPES:
    if _profile.name not in AGENTS:
        register(_profile.name, lambda player, p=_profile: ProBrain(player, p))


# -- Balance variants --------------------------------------------------------------

#: Multiplicative knobs a variant may turn. ``cost_gold``/``cost_lumber`` scale a
#: price; the rest scale the matching field of the unit, building or upgrade.
UNIT_FIELDS = ("hp", "damage", "speed", "range", "build_time", "cost_gold", "cost_lumber")
BUILDING_FIELDS = ("hp", "build_time", "cost_gold", "cost_lumber")
UPGRADE_FIELDS = ("cost_gold", "cost_lumber", "time")


@dataclass(frozen=True)
class Variant:
    """A balance patch: what each thing's numbers get multiplied by.

    The point of a variant is not that it is balanced — it is that an agent
    which only wins under the numbers it was tuned against has learnt the
    table, not the game.
    """

    name: str
    units: Mapping[UnitType, Mapping[str, float]] = field(default_factory=dict)
    buildings: Mapping[BuildingType, Mapping[str, float]] = field(default_factory=dict)
    upgrades: Mapping[Upgrade, Mapping[str, float]] = field(default_factory=dict)


STANDARD = Variant("standard")
VARIANTS: dict[str, Variant] = {STANDARD.name: STANDARD}


def register_variant(variant: Variant) -> None:
    if variant.name in VARIANTS:
        raise ValueError(f"variant {variant.name!r} is already registered")
    VARIANTS[variant.name] = variant


def _scaled_cost(cost, factors: Mapping[str, float]):
    gold = max(0, round(cost.gold * factors.get("cost_gold", 1.0)))
    lumber = max(0, round(cost.lumber * factors.get("cost_lumber", 1.0)))
    return replace(cost, gold=gold, lumber=lumber)


def _scaled_unit(info, factors: Mapping[str, float]):
    return replace(
        info,
        hp=max(1, round(info.hp * factors.get("hp", 1.0))),
        damage=max(0, round(info.damage * factors.get("damage", 1.0))),
        speed=round(info.speed * factors.get("speed", 1.0), 3),
        range=info.range if info.range < 1 else round(info.range * factors.get("range", 1.0), 3),
        build_time=max(0.5, round(info.build_time * factors.get("build_time", 1.0), 3)),
        cost=_scaled_cost(info.cost, factors),
    )


def _scaled_building(info, factors: Mapping[str, float]):
    return replace(
        info,
        hp=max(1, round(info.hp * factors.get("hp", 1.0))),
        build_time=max(0.5, round(info.build_time * factors.get("build_time", 1.0), 3)),
        cost=_scaled_cost(info.cost, factors),
    )


class _Balance:
    """Applies a variant to the live rule tables, and puts them back.

    Every stat the simulation reads goes through ``RACES[race].units`` /
    ``.buildings`` (derived from :mod:`warband.rules` at import time) while the
    AI prices buildings straight out of ``rules.BUILDINGS``, so both have to be
    patched, in place, so that names already bound elsewhere see the change.
    """

    def __init__(self) -> None:
        self.applied: str = STANDARD.name
        self._base_races = {race: (dict(info.units), dict(info.buildings)) for race, info in RACES.items()}
        self._base_units = dict(UNITS)
        self._base_buildings = dict(BUILDINGS)
        self._base_upgrades = dict(UPGRADES)

    def restore(self) -> None:
        for race, (units, buildings) in self._base_races.items():
            RACES[race] = replace(RACES[race], units=dict(units), buildings=dict(buildings))
        UNITS.clear(), UNITS.update(self._base_units)
        BUILDINGS.clear(), BUILDINGS.update(self._base_buildings)
        UPGRADES.clear(), UPGRADES.update(self._base_upgrades)
        self.applied = STANDARD.name

    def apply(self, variant: Variant) -> None:
        if self.applied == variant.name:
            return
        self.restore()
        if variant.name == STANDARD.name:
            return
        for race, (units, buildings) in self._base_races.items():
            new_units = {t: (_scaled_unit(i, variant.units[t]) if t in variant.units else i) for t, i in units.items()}
            new_buildings = {t: (_scaled_building(i, variant.buildings[t]) if t in variant.buildings else i)
                             for t, i in buildings.items()}
            RACES[race] = replace(RACES[race], units=new_units, buildings=new_buildings)
        for unit_type, factors in variant.units.items():
            UNITS[unit_type] = _scaled_unit(self._base_units[unit_type], factors)
        for building_type, factors in variant.buildings.items():
            BUILDINGS[building_type] = _scaled_building(self._base_buildings[building_type], factors)
        for upgrade, factors in variant.upgrades.items():
            base = self._base_upgrades[upgrade]
            UPGRADES[upgrade] = replace(base, cost=_scaled_cost(base.cost, factors),
                                        time=max(1.0, round(base.time * factors.get("time", 1.0), 3)))
        self.applied = variant.name


_BALANCE: _Balance | None = None


def use_variant(name: str) -> None:
    """Patch the rule tables of this process to *name*. Idempotent, and reversible with ``"standard"``."""
    global _BALANCE
    if _BALANCE is None:
        _BALANCE = _Balance()  # snapshot the untouched tables the first time, before anything is patched
    if name not in VARIANTS:
        raise KeyError(f"unknown variant {name!r}; known: {', '.join(sorted(VARIANTS))}")
    _BALANCE.apply(VARIANTS[name])


def shuffled_variant(seed: int, spread: float = 0.25) -> Variant:
    """Every unit and building jittered by up to *spread*, drawn from *seed*.

    This is the generalisation test: a fixed named variant can be tuned
    against, a family drawn from a seed cannot.
    """
    rng = random.Random(seed ^ 0xBA1A)
    jitter = lambda: math.exp(rng.uniform(-spread, spread))  # noqa: E731 - symmetric in multiply and divide
    units = {t: {f: jitter() for f in ("hp", "damage", "cost_gold", "build_time")} for t in UnitType}
    buildings = {t: {f: jitter() for f in ("hp", "cost_gold", "build_time")} for t in BuildingType
                 if t is not BuildingType.GOLD_MINE}
    return Variant(f"shuffle-{seed}", units=units, buildings=buildings)


def ensure_variant(name: str) -> None:
    """Register ``shuffle-N`` on demand, so a variant name is all a worker needs."""
    if name not in VARIANTS and name.startswith("shuffle-"):
        register_variant(shuffled_variant(int(name.split("-", 1)[1])))
    use_variant(name)


# -- Matches -----------------------------------------------------------------------

@dataclass(frozen=True)
class MatchSpec:
    """Everything that determines a match. Equal specs give equal results."""

    seed: int
    agents: tuple[str, ...]
    variant: str = STANDARD.name
    minutes: float = DEFAULT_MINUTES
    width: int = 48
    height: int = 40
    races: tuple[str, ...] | None = None  # race value per player; None draws them from the seed
    theme: str = MapTheme.SUMMER.value
    # The layout is always drawn from the seed, so a ladder spans all five of
    # them without being told to. Size and land are not, so they are spelled
    # out here and varied per seed by the runner.

    @property
    def players(self) -> int:
        return len(self.agents)

    def rotated(self, by: int) -> "MatchSpec":
        """The same map and seed with the agents moved round the corners."""
        n = self.players
        return replace(self, agents=tuple(self.agents[(i - by) % n] for i in range(n)))


@dataclass(frozen=True)
class MatchResult:
    spec: MatchSpec
    placements: tuple[int, ...]  # 1 is best; equal numbers are a tie
    winner: int | None
    minutes: float
    steps: int
    wall: float
    tallies: tuple[PlayerTally, ...] = ()  # what each player bought, lost and killed; see :mod:`warband.telemetry`

    @property
    def decided(self) -> bool:
        return self.winner is not None

    def score(self, i: int, j: int) -> float:
        """What player *i* scored against player *j*: 1 win, 0 loss, 0.5 tie."""
        if self.placements[i] == self.placements[j]:
            return 0.5
        return 1.0 if self.placements[i] < self.placements[j] else 0.0


def _power(world: World, player: int) -> float:
    """What a player still has on the map, priced in gold and lumber.

    Only used to rank players who are both still alive when time runs out.
    """
    total = 0.0
    for unit in world.units.values():
        if unit.player == player and unit.hp > 0:
            cost = unit.info.cost
            total += (cost.gold + cost.lumber) * unit.hp / max(1, unit.max_hp)
    for building in world.player_buildings(player):
        cost = building.info.cost
        total += (cost.gold + cost.lumber) * building.hp / max(1, building.max_hp)
    return total


def _placements(world: World, eliminated: dict[int, float], players: int) -> tuple[int, ...]:
    """Rank the players: survivors first by what they have left, then the dead in reverse order of death."""
    alive = [p for p in range(players) if p not in eliminated]
    ranked: list[list[int]] = []
    if alive:
        by_power: dict[int, float] = {p: _power(world, p) for p in alive}
        for p in sorted(alive, key=lambda p: -by_power[p]):
            # survivors within a per-cent of each other are a genuine tie, not a coin flip on rounding
            if ranked and abs(by_power[ranked[-1][0]] - by_power[p]) <= 0.01 * max(1.0, by_power[ranked[-1][0]]):
                ranked[-1].append(p)
            else:
                ranked.append([p])
    for p in sorted(eliminated, key=lambda p: -eliminated[p]):
        ranked.append([p])
    out = [0] * players
    place = 1
    for group in ranked:
        for p in group:
            out[p] = place
        place += len(group)
    return tuple(out)


def playable(spec: MatchSpec) -> bool:
    """Whether a map exists for this spec at all.

    ``mapgen.generate`` refuses a seed whose layout it cannot make fair — too
    straight a road, a start with no wood — and says so. A ladder should leave
    such a seed out rather than die on it a hundred matches in.
    """
    try:
        mapgen.generate(seed=spec.seed, width=spec.width, height=spec.height,
                        players=spec.players, human=None, theme=MapTheme(spec.theme))
    except ValueError:
        return False
    return True


def play(spec: MatchSpec) -> MatchResult:
    """Run one match to a winner or the time cap."""
    ensure_variant(spec.variant)
    races = tuple(Race(r) for r in spec.races) if spec.races is not None else None
    world = mapgen.generate(seed=spec.seed, width=spec.width, height=spec.height, players=spec.players,
                            human=None, theme=MapTheme(spec.theme), races=races)
    agents = [make_agent(name, player) for player, name in enumerate(spec.agents)]
    # A stream per player: whose turn it is to draw must not depend on who else is playing.
    rngs = [random.Random(spec.seed * 1000003 + player) for player in range(spec.players)]
    eliminated: dict[int, float] = {}
    telemetry = Telemetry(world)
    started = time.perf_counter()
    steps = 0
    for _ in range(int(spec.minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for agent, rng in zip(agents, rngs):
            agent.think(world, rng)
        world.step()
        telemetry.observe(world, world.take_events())
        steps += 1
        for player in world.players:
            if not player.alive and player.id not in eliminated:
                eliminated[player.id] = world.time
    telemetry.finish(world)
    return MatchResult(spec=spec, placements=_placements(world, eliminated, spec.players), winner=world.winner,
                       minutes=world.time / 60, steps=steps, wall=time.perf_counter() - started,
                       tallies=telemetry.tallies)


def register_profiles(profiles: Sequence[tuple[str, object]]) -> None:
    """Pool initialiser: make agents that exist only for this run playable in a worker.

    Agent names travel to workers as plain strings, so a profile invented by a
    search has to be handed over separately — once per worker, at start-up.
    """
    from warband.pro_ai import ProBrain

    for name, profile in profiles:
        if name not in AGENTS:
            register(name, lambda player, p=profile: ProBrain(player, p))


#: The order :func:`play_spec_tuple` expects, and the only thing that crosses
#: a process boundary.
SPEC_FIELDS = ("seed", "agents", "variant", "minutes", "width", "height", "races", "theme")


def play_spec_tuple(packed: tuple) -> MatchResult:
    """``play`` behind a picklable single argument, for :mod:`multiprocessing` pools."""
    return play(MatchSpec(*packed))


# -- Ratings -----------------------------------------------------------------------

@dataclass(frozen=True)
class Rating:
    name: str
    elo: float
    low: float      # 5th percentile of the bootstrap
    high: float     # 95th
    games: int      # matches played
    pairings: int   # head-to-head results in them; a four player game is three
    wins: float     # counting a tie as a half

    @property
    def score(self) -> float:
        """Share of the head-to-head results taken, 0 to 1."""
        return self.wins / self.pairings if self.pairings else 0.0


def pairwise(results: Iterable[MatchResult]) -> dict[tuple[str, str], float]:
    """``(winner, loser) → games won``, a tie counting a half to each side."""
    table: dict[tuple[str, str], float] = {}
    for result in results:
        agents = result.spec.agents
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                if agents[i] == agents[j]:
                    continue  # a mirror tells us nothing about who is better
                score = result.score(i, j)
                table[(agents[i], agents[j])] = table.get((agents[i], agents[j]), 0.0) + score
                table[(agents[j], agents[i])] = table.get((agents[j], agents[i]), 0.0) + (1.0 - score)
    return table


def _fit(table: Mapping[tuple[str, str], float], names: Sequence[str], smoothing: float) -> dict[str, float]:
    """Bradley-Terry strengths by the standard MM iteration, in log space at the end.

    *smoothing* adds that many virtual wins to each side of every pair that
    actually played, which is what keeps a perfect record finite.
    """
    strength = {name: 1.0 for name in names}
    played: dict[tuple[str, str], float] = {}
    for (a, b), _ in table.items():
        if a < b:
            played[(a, b)] = table.get((a, b), 0.0) + table.get((b, a), 0.0) + 2 * smoothing
    wins = {name: 0.0 for name in names}
    for (a, b), games in played.items():
        wins[a] += table.get((a, b), 0.0) + smoothing
        wins[b] += table.get((b, a), 0.0) + smoothing
    for _ in range(500):
        new = {}
        for name in names:
            denominator = 0.0
            for (a, b), games in played.items():
                if a == name:
                    denominator += games / (strength[name] + strength[b])
                elif b == name:
                    denominator += games / (strength[name] + strength[a])
            new[name] = wins[name] / denominator if denominator > 0 else strength[name]
        scale = statistics.fmean(new.values()) or 1.0
        new = {name: value / scale for name, value in new.items()}
        if max(abs(new[n] - strength[n]) for n in names) < 1e-12:
            strength = new
            break
        strength = new
    return {name: math.log(max(value, 1e-12)) for name, value in strength.items()}


def rate(results: Sequence[MatchResult], *, anchor: str | None = None, anchor_elo: float = 1000.0,
         smoothing: float = 0.5, bootstrap: int = 200, seed: int = 0) -> list[Rating]:
    """Elo-scale ratings for every agent that played, strongest first.

    *anchor* is pinned at *anchor_elo* so runs are comparable; without one the
    mean rating is pinned there instead. The interval is a bootstrap over
    matches, so it widens honestly when an agent has played few games.
    """
    names = sorted({name for r in results for name in r.spec.agents})
    if not names:
        return []
    table = pairwise(results)

    def elos(rows: Sequence[MatchResult]) -> dict[str, float]:
        log_strength = _fit(pairwise(rows), names, smoothing)
        points = {name: value * ELO_SCALE for name, value in log_strength.items()}
        offset = anchor_elo - (points[anchor] if anchor in points else statistics.fmean(points.values()))
        return {name: value + offset for name, value in points.items()}

    point = elos(results)
    samples: dict[str, list[float]] = {name: [] for name in names}
    rng = random.Random(seed)
    for _ in range(bootstrap):
        drawn = [results[rng.randrange(len(results))] for _ in range(len(results))]
        if len({n for r in drawn for n in r.spec.agents}) < len(names):
            continue
        for name, value in elos(drawn).items():
            samples[name].append(value)
    out = []
    for name in names:
        games = sum(1 for r in results for i, a in enumerate(r.spec.agents) if a == name
                    and any(b != name for b in r.spec.agents))
        wins = sum(table.get((name, other), 0.0) for other in names if other != name)
        pairings = round(sum(table.get((name, other), 0.0) + table.get((other, name), 0.0)
                             for other in names if other != name))
        spread = sorted(samples[name])
        low = spread[int(0.05 * len(spread))] if spread else point[name]
        high = spread[int(0.95 * (len(spread) - 1))] if spread else point[name]
        out.append(Rating(name=name, elo=point[name], low=low, high=high, games=games,
                          pairings=pairings, wins=wins))
    return sorted(out, key=lambda r: -r.elo)


def win_rate(results: Iterable[MatchResult], a: str, b: str) -> tuple[float, int]:
    """``(share of games *a* scored against *b*, games played)``."""
    table = pairwise(results)
    won = table.get((a, b), 0.0)
    lost = table.get((b, a), 0.0)
    total = won + lost
    return (won / total if total else 0.0), round(total)


def elo_gap(rate_a_over_b: float) -> float:
    """The Elo difference a win rate implies, capped where a perfect record would run away."""
    p = min(max(rate_a_over_b, 1e-6), 1 - 1e-6)
    return ELO_SCALE * math.log(p / (1 - p))
