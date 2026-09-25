#!/usr/bin/env python
"""Who takes the shared ground's prize, and when: the same big maps played with a seam and with a Mother Lode.

The prize (a seam or a lode, dealt by the seed: ``mapgen.deal_prize``) lies only on maps bigger than the three
shipped sizes, which no ladder, race report or balance league plays.  So this plays them: every seed twice, once
with each prize on the same ground (``MatchSpec.prize``), every pairing from both corners, the layouts that hold a
prize cycled by seed.  Two panels:

``races``   every pair of races under one difficulty, as ``tools/race_report.py`` plays them: a race's share of the
            decided matches, with a seam and with a lode.
``agents``  every pair of the named agents, as the ladder plays them: each agent's score, with a seam and a lode.
``ffa``     the named agents (four) on a four-seat map, each through every corner, where the prize lies in every cell.

and, for both, what the league's telemetry says about the prize (``PlayerTally.mined`` and ``first``): in how many
matches somebody put a hall at it and when, how much gold came out of it, and whether the seat that drew the most
from it won.

    uv run python tools/prize_report.py races --difficulty master --seeds 4 --save /tmp/prize-races.jsonl
    uv run python tools/prize_report.py agents --agents medium,hard,master --seeds 4 --save /tmp/prize-agents.jsonl
    uv run python tools/prize_report.py ffa --agents easy,medium,hard,master --seeds 4 --save /tmp/prize-ffa.jsonl
    uv run python tools/prize_report.py read /tmp/prize-races.jsonl       # the tables again, from a saved run
"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its workers, not as a library
    fastsim.activate()

from warband.league import arena  # noqa: E402
from warband.league.arena import MatchResult, MatchSpec  # noqa: E402
from warband.sim import mapgen  # noqa: E402
from warband.sim.rules import BuildingType, Layout, Race  # noqa: E402

PRIZES = (BuildingType.GOLD_SEAM.value, BuildingType.MOTHER_LODE.value)
LAYOUTS = (Layout.PLAINS.value, Layout.CROSSINGS.value, Layout.BASTION.value)  # the layouts that hold a prize


def board(seed: int, size: str, seats: int) -> dict:
    width, height = mapgen.dimensions(size, seats)
    return {"width": width, "height": height, "layout": LAYOUTS[seed % len(LAYOUTS)]}


def race_specs(difficulty: str, seeds: range, size: str, minutes: float) -> list[MatchSpec]:
    return [MatchSpec(seed=seed, agents=(difficulty, difficulty), races=(a.value, b.value), minutes=minutes, prize=prize,
                      **board(seed, size, 2))
            for first, second in itertools.combinations(Race, 2) for seed in seeds for a, b in ((first, second), (second, first))
            for prize in PRIZES]


def agent_specs(agents: list[str], seeds: range, size: str, minutes: float) -> list[MatchSpec]:
    return [MatchSpec(seed=seed, agents=pair, minutes=minutes, prize=prize, **board(seed, size, 2))
            for a, b in itertools.combinations(agents, 2) for seed in seeds for pair in ((a, b), (b, a)) for prize in PRIZES]


def ffa_specs(agents: list[str], seeds: range, size: str, minutes: float) -> list[MatchSpec]:
    """Four seats, each agent through every corner: on a four-seat map the prize lies in every cell, eighteen tiles out."""
    group = tuple(agents)
    return [MatchSpec(seed=seed, agents=group, minutes=minutes, prize=prize, **board(seed, size, len(group))).rotated(turn)
            for seed in seeds for turn in range(len(group)) for prize in PRIZES]


def play(specs: list[MatchSpec], workers: int, save: Path | None) -> list[MatchResult]:
    fair: dict[tuple, bool] = {}  # a map is its seed, size, seats, layout and prize: generated once for every pairing on it
    for s in specs:
        key = (s.seed, s.width, s.height, s.players, s.layout, s.prize)
        if key not in fair:
            fair[key] = arena.playable(s)
    specs = [s for s in specs if fair[(s.seed, s.width, s.height, s.players, s.layout, s.prize)]]
    packed = [tuple(getattr(s, f) for f in arena.SPEC_FIELDS) for s in specs]
    results: list[MatchResult] = []
    started = time.perf_counter()
    out = open(save, "a") if save is not None else None
    try:
        with mp.get_context("spawn").Pool(workers) as pool:
            for result in pool.imap_unordered(arena.play_spec_tuple, packed, chunksize=1):
                results.append(result)
                if out is not None:
                    out.write(json.dumps(arena.to_record(result)) + "\n")
                    out.flush()
                print(f"\r  {len(results)}/{len(specs)} matches, {time.perf_counter() - started:.0f}s", end="", flush=True)
    finally:
        if out is not None:
            out.close()
    print()
    return results


def prize_of(result: MatchResult) -> str:
    return result.spec.prize or mapgen.deal_prize(result.spec.seed).value


def first(result: MatchResult) -> int | None:
    """Who won: the winner of a duel (or the side a settled one was settled for), the one seat placed first in a
    free-for-all, which ranks the seats still standing at the time cap by what they have left; None for a tie."""
    if len(result.spec.agents) == 2:
        return result.winner
    top = [seat for seat, place in enumerate(result.placements) if place == 1]
    return top[0] if len(top) == 1 else None


def shares(results: list[MatchResult], side) -> dict[str, dict[str, tuple[int, int]]]:
    """Per prize, per side (a race or an agent, as *side* names seat *i* of a result): (won, lost) of decided matches."""
    table: dict[str, dict[str, list[int]]] = {}
    for r in results:
        winner = first(r)
        if winner is None:
            continue
        for seat in range(len(r.spec.agents)):
            row = table.setdefault(prize_of(r), {}).setdefault(side(r, seat), [0, 0])
            row[0 if winner == seat else 1] += 1
    return {prize: {name: (w, l) for name, (w, l) in rows.items()} for prize, rows in table.items()}


def print_shares(results: list[MatchResult], side, title: str) -> None:
    table = shares(results, side)
    names = sorted({name for rows in table.values() for name in rows})
    undecided = Counter(prize_of(r) for r in results if first(r) is None)
    print(f"\n  {title}: won-lost (share of decided matches)")
    print(f"  {'':10}" + "".join(f"{prize:>24}" for prize in PRIZES))
    for name in names:
        cells = []
        for prize in PRIZES:
            won, lost = table.get(prize, {}).get(name, (0, 0))
            cells.append(f"{won:>6}-{lost:<4} ({100 * won / max(1, won + lost):5.1f}%)" if won + lost else f"{'-':>24}")
        print(f"  {name:10}" + "".join(f"{c:>24}" for c in cells))
    print(f"  {'undecided':10}" + "".join(f"{undecided[prize]:>24}" for prize in PRIZES))
    played = Counter(prize_of(r) for r in results)
    print(f"  {'matches':10}" + "".join(f"{played[prize]:>24}" for prize in PRIZES))


def print_prize(results: list[MatchResult], side) -> None:
    """What the telemetry says about the prize: who took it, when, what came out of it, and what it was worth."""
    print("\n  the prize, from the league's telemetry:")
    for prize in PRIZES:
        mine = [r for r in results if prize_of(r) == prize]
        if not mine:
            continue
        halls = [min(t.first[f"hall.{prize}"] for t in r.tallies if f"hall.{prize}" in t.first) for r in mine
                 if any(f"hall.{prize}" in t.first for t in r.tallies)]
        worked = [r for r in mine if any(t.mined[prize] for t in r.tallies)]
        first_trip = [min(t.first[f"mined.{prize}"] for t in r.tallies if f"mined.{prize}" in t.first) for r in worked]
        drawn = [sum(t.mined[prize] for t in r.tallies) for r in mine]
        share = [sum(t.mined[prize] for t in r.tallies) / max(1, sum(sum(t.mined.values()) for t in r.tallies)) for r in mine]
        # Did the seat that drew the most from the prize win?  Decided matches where somebody drew anything from it.
        telling = [r for r in worked if first(r) is not None]
        drew_most_won = sum(1 for r in telling if max(range(len(r.tallies)), key=lambda i: r.tallies[i].mined[prize]) == first(r))
        takers = Counter(side(r, i) for r in mine for i, t in enumerate(r.tallies) if f"hall.{prize}" in t.first)
        print(f"  {prize}: {len(mine)} matches")
        print(f"    a hall at it in {len(halls)} ({100 * len(halls) / len(mine):.0f}%), the first at "
              f"{_median_minutes(halls)} (median); halls by {dict(takers) or 'nobody'}")
        print(f"    worked in {len(worked)} ({100 * len(worked) / len(mine):.0f}%), the first trip home at {_median_minutes(first_trip)} (median)")
        print(f"    gold out of it a match: median {statistics.median(drawn):,.0f}, mean {statistics.mean(drawn):,.0f}, "
              f"max {max(drawn):,}; {100 * statistics.mean(share):.1f}% of all the gold mined")
        print(f"    the seat that drew the most from it won {drew_most_won} of {len(telling)} decided matches it was worked in")
        minutes = sorted(r.minutes for r in mine)
        print(f"    match length median {minutes[len(minutes) // 2]:.1f} min")


def _median_minutes(seconds: list[float]) -> str:
    return f"{statistics.median(seconds) / 60:.1f} min" if seconds else "never"


def report(results: list[MatchResult]) -> None:
    by_race = any(r.spec.races is not None and r.spec.agents[0] == r.spec.agents[1] for r in results)
    side = (lambda r, i: r.races[i]) if by_race else (lambda r, i: r.spec.agents[i])
    print_shares(results, side, "by race" if by_race else "by agent")
    print_prize(results, side)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("races", "agents", "ffa", "read"))
    ap.add_argument("sources", nargs="*", type=Path, help="read: saved runs")
    ap.add_argument("--difficulty", default="master", help="races: the brain every race plays")
    ap.add_argument("--agents", default="medium,hard,master", help="agents: who meets whom")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--first-seed", type=int, default=7100)
    ap.add_argument("--size", default="Huge", choices=[s for s in mapgen.SIZES if s not in ("Small", "Medium", "Large")])
    ap.add_argument("--minutes", type=float, default=arena.DEFAULT_MINUTES)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--save", type=Path, default=None, help="append every match to this JSON-lines file")
    args = ap.parse_args(argv)
    if args.mode == "read":
        results = [arena.from_record(json.loads(line)) for path in args.sources for line in path.read_text().splitlines() if line.strip()]
    else:
        seeds = range(args.first_seed, args.first_seed + args.seeds)
        makers = {"races": lambda: race_specs(args.difficulty, seeds, args.size, args.minutes),
                  "agents": lambda: agent_specs(args.agents.split(","), seeds, args.size, args.minutes),
                  "ffa": lambda: ffa_specs(args.agents.split(","), seeds, args.size, args.minutes)}
        specs = makers[args.mode]()
        print(f"{len(specs)} matches on {args.size} ({args.seeds} seeds from {args.first_seed}, both prizes, both corners), {args.workers} workers")
        results = play(specs, args.workers, args.save)
    report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
