"""The balance league: every posture against every other, and what the matches say about the rules.

    uv run python tools/balance_report.py --seeds 8 --workers 5             # play the league, save it, print the readout
    uv run python tools/balance_report.py --from docs/evidence/balance/league.jsonl   # re-read a league already played
    uv run python tools/balance_report.py --agents pro,knights,siege --seeds 4 --usage-of knights

The postures are ``warband.archetypes``; the readout is ``warband.balance``:
the head-to-head matrix and its equilibrium (the mix a player who knew the
matrix would choose), each posture's pathologies (unspent bank, time at the
supply cap, matches at the cap), the races, and what every unit, building and
upgrade was bought and earned.  Read the pathologies first: a posture that
cannot spend its money is a bug, not a price.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import random
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from arena import print_table, run, specs_1v1  # noqa: E402 - the ladder runner in tools/arena.py
from warband import arena, balance  # noqa: E402
from warband.archetypes import NAMES  # noqa: E402
from warband.arena import MatchResult, MatchSpec, win_rate  # noqa: E402
from warband.rules import Race  # noqa: E402

SEED_BASE = 70_000  # far from the seeds the ladders and the tuner use; nothing was tuned here


def with_races(specs: list[MatchSpec]) -> list[MatchSpec]:
    """Draw the two races per map and pairing, tied to the corner, so both corners of a pairing are one fair pair.

    The map generator draws races from the seed alone, which would give a whole
    league on eight seeds only eight race pairs. Drawing per pairing as well
    spreads every race over every posture and every map.
    """
    out = []
    for spec in specs:
        rng = random.Random(f"{spec.seed}:{':'.join(sorted(spec.agents))}")
        out.append(replace(spec, races=tuple(rng.choice(list(Race)).value for _ in spec.agents)))
    return out


def _minutes(seconds: float | None) -> str:
    return f"{seconds / 60:5.1f}" if seconds is not None else "    —"


def _fmt(value: float | None, width: int = 6, digits: int = 2) -> str:
    return f"{value:{width}.{digits}f}" if value is not None else f"{'—':>{width}}"


def report(results: list[MatchResult], agents: list[str], usage_of: str | None) -> None:
    present = [a for a in agents if any(a in r.spec.agents for r in results)]
    print(f"\n== postures ({len(results)} matches) ==")
    print_table(results, "pro" if "pro" in present else present[0], present)

    payoff = [[win_rate(results, a, b)[0] if a != b else 0.5 for b in present] for a in present]
    weights = balance.equilibrium(payoff)
    print("\n  equilibrium — the mix a player who knew the matrix would choose:")
    for name, weight in sorted(zip(present, weights), key=lambda pair: -pair[1]):
        if weight >= 0.005:
            print(f"    {name:<12} {weight * 100:5.1f}%")
    without = [n for n, w in zip(present, weights) if w < 0.005]
    if without:
        print("    no share: " + ", ".join(without))

    print("\n== pathologies (read these before any price) ==")
    print(f"  {'posture':<12} {'games':>5} {'score':>6} {'undecided':>9} {'unspent':>8} {'blocked':>8} {'peak army':>9} {'1st soldier':>11}")
    for p in balance.postures(results):
        print(f"  {p.name:<12} {p.games:5d} {p.score * 100:5.1f}% {p.undecided:9d} {p.unspent:8.0f} {p.blocked * 100:7.0f}% "
              f"{p.peak_army:9.0f} {_minutes(p.first_soldier):>11}")
    print("  unspent: gold+lumber in the bank at the end; blocked: share of minutes at the supply cap; 1st soldier in minutes")

    races, pairs = balance.race_table(results)
    print("\n== races ==")
    for race, (share, games) in sorted(races.items(), key=lambda kv: -kv[1][0]):
        print(f"  {race:<8} {share * 100:5.1f}%  in {games} pairings")
    names = sorted(races)
    print(f"  {'':<8} " + " ".join(f"{n[:6]:>7}" for n in names))
    for a in names:
        cells = [(f"{pairs[a, b][0] * 100:6.1f}%" if (a, b) in pairs else f"{'-':>7}") if a != b else f"{'—':>7}" for b in names]
        print(f"  {a:<8} " + " ".join(cells))

    for label, agent in (("everyone", None), (usage_of, usage_of)):
        if label is None:
            continue
        rows = balance.usage(results, agent)
        print(f"\n== usage, {label} ({rows[0].player_games} player-games) ==")
        print(f"  {'unit':<12} {'bought':>7} {'per game':>8} {'spent':>9} {'value/1000':>10} {'trade':>6} {'lost':>5} {'first':>6}")
        for row in rows:
            if row.kind != "unit":
                continue
            print(f"  {row.key:<12} {row.share * 100:6.0f}% {row.per_game:8.2f} {row.spent:9d} {_fmt(row.value_per_1000, 10, 0)} "
                  f"{_fmt(row.trade)} {row.lost:5d} {_minutes(row.first):>6}")
        print("  bought: share of player-games with one; value/1000: value destroyed per 1000 spent; trade: destroyed per lost")
        print(f"\n  {'building':<12} {'bought':>7} {'per game':>8} {'spent':>9} {'value/1000':>10} {'razed':>5} {'first':>6}")
        for row in rows:
            if row.kind != "building":
                continue
            print(f"  {row.key:<12} {row.share * 100:6.0f}% {row.per_game:8.2f} {row.spent:9d} {_fmt(row.value_per_1000, 10, 0)} "
                  f"{row.lost:5d} {_minutes(row.first):>6}")
        print(f"\n  {'upgrade':<16} {'bought':>7} {'spent':>9} {'first':>6}")
        for row in rows:
            if row.kind != "upgrade":
                continue
            print(f"  {row.key:<16} {row.share * 100:6.0f}% {row.spent:9d} {_minutes(row.first):>6}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agents", default=",".join(NAMES), help="postures to play, comma separated")
    parser.add_argument("--seeds", type=int, default=8, help="maps per pairing; each is played from both corners")
    parser.add_argument("--minutes", type=float, default=arena.DEFAULT_MINUTES)
    parser.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 2))
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence" / "balance" / f"league-{date.today()}.jsonl")
    parser.add_argument("--from", dest="source", type=Path, help="read a league already played instead of playing one")
    parser.add_argument("--usage-of", help="also print the usage table for this posture's seats alone")
    parser.add_argument("--variant", default="standard",
                        help="rulebook to play under: a registered name, shuffle-N, or scale:knight.cost_gold=1.25,tower.hp=0.8")
    args = parser.parse_args()
    agents = args.agents.split(",")
    if args.source is not None:
        results = balance.load(args.source)
        print(f"{len(results)} matches read from {args.source}")
    else:
        specs = with_races(specs_1v1(agents, range(SEED_BASE, SEED_BASE + args.seeds), args.variant, args.minutes))
        print(f"{len(agents)} postures, {len(specs)} matches on {args.workers} workers, rulebook {args.variant}")
        results = run(specs, args.workers, "league")
        balance.save(results, args.out)
        print(f"saved to {args.out}")
    report(results, agents, args.usage_of)


if __name__ == "__main__":
    main()
