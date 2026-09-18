"""Run the ladder: agents against each other, in parallel, and the rating table that follows.

    uv run python tools/arena.py ladder --seeds 8                       # every pair, both corners
    uv run python tools/arena.py ladder --agents medium,hard,master --seeds 40     # two agents, a lot of games
    uv run python tools/arena.py ladder --agents hard,master,pro-x --neighbours 1 --anchor master --anchor-elo 1420
    uv run python tools/arena.py ffa --players 4 --seeds 12              # free-for-all placements
    uv run python tools/arena.py variants --shuffles 6 --seeds 6         # the same ladder under jittered balance
    uv run python tools/arena.py report --seeds 24                       # 1v1, FFA and variants in one go
    uv run python tools/arena.py ladder --agents pro,pro2 --seeds 60 --save runs/pro2.jsonl   # keep every match
    uv run python tools/arena.py rate --from runs/*.jsonl --anchor pro --anchor-elo 1450      # one table over saved runs

Matches are independent and fully determined by their seed, so they are
handed to a process pool; ``--workers`` defaults to most of the machine.
Every pairing is played from every corner of the map, so a seed that
favours a starting position cannot favour an agent.
"""

from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband import arena, mapgen  # noqa: E402
from warband.arena import AGENTS, MatchResult, MatchSpec, playable, rate, win_rate  # noqa: E402
from warband.rules import Layout  # noqa: E402


#: Sizes a ladder walks through, one per seed. The layout is drawn from the
#: seed by mapgen itself, so all five appear without being asked for. The land
#: is not varied: summer, winter and wasteland generate identical terrain —
#: same trees, grass, rock and water, tile for tile — and differ only in how
#: they are drawn, so cycling them would buy a ladder nothing.
SIZES = list(mapgen.SIZES.values())


def _board(seed: int) -> dict:
    """The size and layout this seed is played on, so both corners share a map.

    Both are cycled rather than drawn: eight seeds left to themselves drew
    plains five times and forest never, and a posture's score swings by
    thirty points between layouts (docs/balance.md).
    """
    width, height = SIZES[seed % len(SIZES)]
    layouts = [layout.value for layout in Layout]
    return {"width": width, "height": height, "layout": layouts[seed % len(layouts)]}


def specs_1v1(agents: list[str], seeds: range, variant: str, minutes: float,
              neighbours: int | None = None, against: list[str] | None = None) -> list[MatchSpec]:
    """Every unordered pair, on every seed, from both corners.

    With *neighbours*, only agents within that many places of each other in
    the list meet: a chain of rungs rather than every pair, which is where the
    information is once the list is in rating order. With *against*, a panel:
    every agent meets only the agents in that list.
    """
    out = []
    for i, j in itertools.combinations(range(len(agents)), 2):
        if neighbours is not None and j - i > neighbours:
            continue
        a, b = agents[i], agents[j]
        if against is not None and a not in against and b not in against:
            continue
        for seed in seeds:
            board = _board(seed)
            out.append(MatchSpec(seed=seed, agents=(a, b), variant=variant, minutes=minutes, **board))
            out.append(MatchSpec(seed=seed, agents=(b, a), variant=variant, minutes=minutes, **board))
    return out


def specs_ffa(agents: list[str], seeds: range, players: int, variant: str, minutes: float) -> list[MatchSpec]:
    """Every combination of *players* agents, each rotated through every corner."""
    out = []
    for group in itertools.combinations(agents, players):
        for seed in seeds:
            for turn in range(players):
                board = _board(seed)
                board["width"] = max(board["width"], 64)  # four players need room
                spec = MatchSpec(seed=seed, agents=group, variant=variant, minutes=minutes, **board)
                out.append(spec.rotated(turn))
    return out


def drop_unfair(specs: list[MatchSpec]) -> list[MatchSpec]:
    """Leave out the seeds mapgen cannot make a fair map from, and say how many."""
    usable: dict[tuple, bool] = {}
    kept = []
    for spec in specs:
        key = (spec.seed, spec.width, spec.height, spec.players, spec.layout)
        if key not in usable:
            usable[key] = playable(spec)
        if usable[key]:
            kept.append(spec)
    dropped = len(usable) - sum(usable.values())
    if dropped:
        print(f"  ({dropped} of {len(usable)} seeds have no fair map at this size and were left out)")
    return kept


def run(specs: list[MatchSpec], workers: int, label: str, save: Path | None = None) -> list[MatchResult]:
    specs = drop_unfair(specs)
    started = time.perf_counter()
    packed = [tuple(s.__dict__[f] for f in arena.SPEC_FIELDS) for s in specs]
    results: list[MatchResult] = []
    out = open(save, "a") if save is not None else None
    try:
        if workers <= 1:
            for result in map(arena.play_spec_tuple, packed):
                results.append(result)
                _keep(out, result)
                _progress(label, results, len(specs), started)
        else:
            with mp.get_context("spawn").Pool(workers) as pool:
                for result in pool.imap_unordered(arena.play_spec_tuple, packed, chunksize=1):
                    results.append(result)
                    _keep(out, result)
                    _progress(label, results, len(specs), started)
    finally:
        if out is not None:
            out.close()
    print()
    return results


def _keep(out, result: MatchResult) -> None:
    """Append a finished match to the save file at once, so a killed run still leaves its games."""
    if out is not None:
        out.write(json.dumps(arena.to_record(result)) + "\n")
        out.flush()


def load(paths: list[str]) -> list[MatchResult]:
    results = []
    for path in paths:
        with open(path) as f:
            results += [arena.from_record(json.loads(line)) for line in f if line.strip()]
    return results


def _progress(label: str, results: list[MatchResult], total: int, started: float) -> None:
    done = len(results)
    if done % 10 and done != total:
        return
    elapsed = time.perf_counter() - started
    rate_per_s = done / elapsed if elapsed else 0
    left = (total - done) / rate_per_s if rate_per_s else 0
    print(f"\r  {label}: {done}/{total} matches, {elapsed:.0f}s elapsed, {rate_per_s:.1f}/s, {left:.0f}s left   ",
          end="", flush=True)


def print_table(results: list[MatchResult], anchor: str, agents: list[str], anchor_elo: float = 1000.0,
                proximity: float | None = arena.PROXIMITY) -> None:
    ratings = rate(results, anchor=anchor, anchor_elo=anchor_elo, proximity=proximity)
    width = max(len(r.name) for r in ratings)
    print(f"\n  {'agent':<{width}}  {'elo':>7}  {'90% interval':>16}  {'games':>6}  {'score':>6}")
    for r in ratings:
        print(f"  {r.name:<{width}}  {r.elo:7.0f}  {r.low:7.0f} .. {r.high:<6.0f}  {r.games:6d}  {r.score * 100:5.1f}%")
    print(f"\n  head to head (row's score against column, {len(results)} matches):")
    print(f"  {'':<{width}}  " + "  ".join(f"{name[:8]:>8}" for name in agents))
    for a in agents:
        cells = []
        for b in agents:
            if a == b:
                cells.append(f"{'—':>8}")
                continue
            share, games = win_rate(results, a, b)
            cells.append(f"{share * 100:7.1f}%" if games else f"{'-':>8}")
        print(f"  {a:<{width}}  " + "  ".join(cells))
    decided = sum(1 for r in results if r.decided)
    minutes = sorted(r.minutes for r in results)
    print(f"\n  {decided}/{len(results)} decided; match length median {minutes[len(minutes) // 2]:.1f} sim-minutes")
    print_styles(results, agents)


def print_by_race(results: list[MatchResult], agents: list[str]) -> None:
    """Each agent's score by the race it was drawn: where a brain's losses come from."""
    table = arena.score_by_race(results)
    if not table:
        return
    races = sorted({race for rows in table.values() for race in rows})
    width = max(len(name) for name in agents)
    print(f"\n  score by race drawn (results in brackets):")
    print(f"  {'':<{width}}  " + "  ".join(f"{race:>12}" for race in races))
    for name in agents:
        if name not in table:
            continue
        cells = [f"{table[name][r][0] * 100:5.1f}% ({table[name][r][1]:3d})" if r in table[name] else f"{'-':>12}"
                 for r in races]
        print(f"  {name:<{width}}  " + "  ".join(cells))


def print_styles(results: list[MatchResult], agents: list[str]) -> None:
    """Medians of how each agent played: whether two agents of one strength are two players."""
    table = arena.styles(results)
    width = max(len(name) for name in agents)
    print(f"\n  how they play (medians):")
    print(f"  {'':<{width}}  " + "  ".join(f"{f[:8]:>8}" for f in arena.STYLE_FIELDS))
    for name in agents:
        if name not in table:
            continue
        cells = [f"{table[name][f]:8.0f}" for f in arena.STYLE_FIELDS]
        print(f"  {name:<{width}}  " + "  ".join(cells))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("ladder", "ffa", "variants", "report", "rate"))
    parser.add_argument("--save", type=Path, default=None, help="append every match to this JSON-lines file")
    parser.add_argument("--from", dest="sources", nargs="*", default=[], help="rate: saved runs to pool")
    parser.add_argument("--agents", default=None, help="comma separated; default every registered agent")
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--first-seed", type=int, default=1000)
    parser.add_argument("--players", type=int, default=3, help="free-for-all size")
    parser.add_argument("--shuffles", type=int, default=4, help="jittered balance variants to rate under")
    parser.add_argument("--spread", type=float, default=0.25, help="how far a jittered variant moves a number")
    parser.add_argument("--minutes", type=float, default=arena.DEFAULT_MINUTES)
    parser.add_argument("--anchor", default="medium", help="the agent pinned at --anchor-elo")
    parser.add_argument("--anchor-elo", type=float, default=1000.0)
    parser.add_argument("--proximity", type=float, default=arena.PROXIMITY,
                        help="Elo gap at which a pair's games count half; 0 counts every game the same")
    parser.add_argument("--neighbours", type=int, default=None,
                        help="1v1: only agents this close in the --agents list meet (default: every pair)")
    parser.add_argument("--against", default=None,
                        help="1v1: comma separated panel; every agent meets only these (default: every pair)")
    parser.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 2))
    args = parser.parse_args()

    if args.mode == "rate":
        results = load(args.sources)
        agents = args.agents.split(",") if args.agents else sorted({n for r in results for n in r.spec.agents})
        results = [r for r in results if all(n in agents for n in r.spec.agents)]
        print(f"{len(results)} matches from {len(args.sources)} file(s)")
        print_table(results, args.anchor, agents, args.anchor_elo, args.proximity or None)
        print_by_race(results, agents)
        return
    agents = args.agents.split(",") if args.agents else sorted(AGENTS)
    against = args.against.split(",") if args.against else None
    for name in against or []:
        if name not in agents:
            agents.append(name)
    for name in agents:
        if name not in AGENTS:
            raise SystemExit(f"unknown agent {name!r}; known: {', '.join(sorted(AGENTS))}")
    seeds = range(args.first_seed, args.first_seed + args.seeds)
    print(f"agents: {', '.join(agents)}; {args.seeds} seeds from {args.first_seed}; {args.workers} workers")
    proximity = args.proximity or None
    table = lambda results: print_table(results, args.anchor, agents, args.anchor_elo, proximity)  # noqa: E731

    if args.mode in ("ladder", "report"):
        print("\n== 1v1 ==")
        results = run(specs_1v1(agents, seeds, "standard", args.minutes, args.neighbours, against), args.workers, "1v1",
                      args.save)
        table(results)
    if args.mode in ("ffa", "report"):
        players = args.players if args.mode == "ffa" else min(4, max(3, len(agents)))
        if len(agents) >= players:
            print(f"\n== free-for-all, {players} players ==")
            results = run(specs_ffa(agents, seeds, players, "standard", args.minutes), args.workers, "ffa", args.save)
            table(results)
        else:
            print(f"\n(skipping free-for-all: {players} players need {players} agents)")
    if args.mode in ("variants", "report"):
        print(f"\n== balance variants ({args.shuffles} jittered rulebooks, spread {args.spread}) ==")
        names = []
        for i in range(args.shuffles):
            variant = arena.shuffled_variant(9000 + i, spread=args.spread)
            if variant.name not in arena.VARIANTS:
                arena.register_variant(variant)
            names.append(variant.name)
        every: list[MatchResult] = []
        for name in names:
            results = run(specs_1v1(agents, seeds, name, args.minutes), args.workers, name, args.save)
            every += results
            line = "   ".join(f"{a} {win_rate(results, a, args.anchor)[0] * 100:.0f}%" for a in agents if a != args.anchor)
            print(f"  {name}: against {args.anchor} — {line}")
        print("\n  pooled over every jittered rulebook:")
        table(every)


if __name__ == "__main__":
    main()
