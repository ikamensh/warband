"""The balance readout: what a league of postures says about the rules.

`tools/balance_report.py` plays every archetype against every other and
hands the results here.  Three readings come out:

* the **payoff matrix** between postures and its **equilibrium** — the mix
  a player who knew the matrix would choose.  A posture with all the weight
  names an ingredient too cheap or a counter that is missing; a posture with
  none was not worth what it cost;
* **usage** — what every unit, building and upgrade was bought, when, what
  it killed for what it cost, across every player of every match;
* **pathologies** per posture — unspent bank at the end, time spent
  supply-blocked, matches that ran to the cap — which are bugs to fix before
  any price is read.

Nothing here plays a match; it reads :class:`~warband.league.arena.MatchResult`
tallies (see :mod:`warband.league.telemetry`).
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from warband.league.arena import MatchResult
from warband.sim.rules import BUILDINGS, BuildingType, UnitType, Upgrade


def equilibrium(payoff: list[list[float]], rounds: int = 20_000, step: float = 2.0) -> list[float]:
    """The symmetric Nash equilibrium of a round robin: how a player who knew the matrix would mix.

    *payoff[i][j]* is the share row *i* scored against column *j* (0.5 on the
    diagonal).  Both sides play multiplicative weights against each other; the
    time average converges to an equilibrium of the zero-sum game the matrix
    defines, within about ``sqrt(log n / rounds)``.
    """
    n = len(payoff)
    if n == 0:
        return []
    edge = [[payoff[i][j] - 0.5 for j in range(n)] for i in range(n)]
    log_weights = [0.0] * n
    total = [0.0] * n
    for _ in range(rounds):
        top = max(log_weights)
        weights = [math.exp(w - top) for w in log_weights]
        norm = sum(weights)
        strategy = [w / norm for w in weights]
        for i in range(n):
            total[i] += strategy[i]
            log_weights[i] += step * sum(edge[i][j] * strategy[j] for j in range(n))
    return [t / rounds for t in total]


# -- Usage -------------------------------------------------------------------------

@dataclass
class Usage:
    """One unit, building or upgrade across every player of every match."""

    key: str
    kind: str                 # "unit", "building" or "upgrade"
    player_games: int = 0     # players observed (two per 1v1 match)
    bought_in: int = 0        # …of which bought this at least once
    bought: int = 0
    spent: int = 0
    lost: int = 0             # died (units) or razed (buildings)
    killed_value: int = 0     # what this unit type (or tower) destroyed, priced at the victims' cost
    dealt: int = 0
    taken: int = 0
    _first: list[float] = field(default_factory=list)

    @property
    def share(self) -> float:
        """Share of player-games in which it was bought at all."""
        return self.bought_in / self.player_games if self.player_games else 0.0

    @property
    def per_game(self) -> float:
        return self.bought / self.player_games if self.player_games else 0.0

    @property
    def first(self) -> float | None:
        """Mean sim seconds until the first one stood, over the games that had one."""
        return statistics.mean(self._first) if self._first else None

    @property
    def value_per_1000(self) -> float | None:
        """Value destroyed per thousand spent on it: what a unit of this kind earned."""
        return self.killed_value / self.spent * 1000 if self.spent else None

    @property
    def trade(self) -> float | None:
        """Value destroyed per value lost: above one it wins its exchanges."""
        if not self.lost or not self.bought:
            return None
        return self.killed_value / (self.lost * self.spent / self.bought)


def usage(results: Iterable[MatchResult], agent: str | None = None) -> list[Usage]:
    """Every unit, building and upgrade, over all players (or only *agent*'s seats)."""
    rows: dict[str, Usage] = {}
    for kind, names in (("unit", (t.value for t in UnitType)), ("building", (t.value for t in BuildingType)),
                        ("upgrade", (u.value for u in Upgrade))):
        for key in names:
            rows[key] = Usage(key=key, kind=kind)
    for kind, info in BUILDINGS.items():
        if info.mine is not None:
            rows.pop(kind.value)  # a deposit is nobody's: no player ever builds one
    for result in results:
        for seat, tally in enumerate(result.tallies):
            if agent is not None and result.spec.agents[seat] != agent:
                continue
            for row in rows.values():
                row.player_games += 1
            for counter in (tally.trained, tally.started, tally.researched):
                for key, n in counter.items():
                    rows[key].bought += n
                    rows[key].bought_in += 1
            for key, n in tally.spent.items():
                rows[key].spent += n
            for key, t in tally.first.items():
                rows[key]._first.append(t)
            for counter in (tally.lost, tally.razed):
                for key, n in counter.items():
                    rows[key].lost += n
            for key, v in tally.kill_value.items():
                if key in rows:
                    rows[key].killed_value += v
            for key, v in tally.dealt.items():
                if key in rows:
                    rows[key].dealt += v
            for key, v in tally.taken.items():
                if key in rows:
                    rows[key].taken += v
    return list(rows.values())


# -- Postures ----------------------------------------------------------------------

@dataclass
class Posture:
    """How one agent's games went, read off its own tallies: the pathologies before the prices."""

    name: str
    games: int = 0
    wins: float = 0.0
    undecided: int = 0
    _unspent: list[int] = field(default_factory=list)
    _blocked: list[float] = field(default_factory=list)
    _peak: list[int] = field(default_factory=list)
    _first_soldier: list[float] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def unspent(self) -> float:
        """Gold and lumber in the bank when the match ended, on average."""
        return statistics.mean(self._unspent) if self._unspent else 0.0

    @property
    def blocked(self) -> float:
        """Share of the timeline spent at the supply cap."""
        return statistics.mean(self._blocked) if self._blocked else 0.0

    @property
    def peak_army(self) -> float:
        return statistics.mean(self._peak) if self._peak else 0.0

    @property
    def first_soldier(self) -> float | None:
        return statistics.mean(self._first_soldier) if self._first_soldier else None


def postures(results: Iterable[MatchResult]) -> list[Posture]:
    table: dict[str, Posture] = {}
    for result in results:
        for seat, (name, tally) in enumerate(zip(result.spec.agents, result.tallies)):
            posture = table.setdefault(name, Posture(name))
            posture.games += 1
            posture.wins += sum(result.score(seat, other) for other in range(result.spec.players) if other != seat) \
                / max(1, result.spec.players - 1)
            posture.undecided += not result.decided
            if tally.timeline:
                last = tally.timeline[-1]
                posture._unspent.append(last.gold + last.lumber)
                posture._blocked.append(sum(1 for s in tally.timeline if s.supply_used >= s.supply_cap) / len(tally.timeline))
                posture._peak.append(max(s.army_value for s in tally.timeline))
            soldiers = [t for k, t in tally.first.items() if k in _SOLDIERS]
            if soldiers:
                posture._first_soldier.append(min(soldiers))
    return sorted(table.values(), key=lambda p: -p.score)


_SOLDIERS = frozenset(t.value for t in UnitType if t is not UnitType.PEASANT)


def fielded(results: Iterable[MatchResult]) -> dict[str, Counter[str]]:
    """Units trained per game by each agent, averaged over its seats: whether a posture did what its name says."""
    totals: dict[str, Counter[str]] = {}
    seats: Counter[str] = Counter()
    for result in results:
        for name, tally in zip(result.spec.agents, result.tallies):
            totals.setdefault(name, Counter()).update(tally.trained)
            seats[name] += 1
    return {name: Counter({k: v / seats[name] for k, v in total.items()}) for name, total in totals.items()}


# -- Races -------------------------------------------------------------------------

def race_table(results: Iterable[MatchResult]) -> tuple[dict[str, tuple[float, int]], dict[tuple[str, str], tuple[float, int]]]:
    """``(race → (score share, games), (race, race) → (share the first took, games))`` over every pairing."""
    wins: dict[str, float] = {}
    games: dict[str, int] = {}
    pair_wins: dict[tuple[str, str], float] = {}
    pair_games: dict[tuple[str, str], int] = {}
    for result in results:
        races = [t.race for t in result.tallies]
        for i, mine in enumerate(races):
            for j, theirs in enumerate(races):
                if i == j:
                    continue
                score = result.score(i, j)
                wins[mine] = wins.get(mine, 0.0) + score
                games[mine] = games.get(mine, 0) + 1
                pair_wins[mine, theirs] = pair_wins.get((mine, theirs), 0.0) + score
                pair_games[mine, theirs] = pair_games.get((mine, theirs), 0) + 1
    return ({r: (wins[r] / games[r], games[r]) for r in games},
            {pair: (pair_wins[pair] / pair_games[pair], pair_games[pair]) for pair in pair_games})
