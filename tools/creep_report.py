#!/usr/bin/env python
"""Can the computer players clear a creature camp?  The gate the whole feature stands on.

Camps are only a feature if every side can use them.  If the brains cannot creep, a camp is a
human-only advantage -- you clear one and snowball while the AI never does -- and the measured
difficulty ladder (``warband.brains.ai.DIFFICULTY_ELO``) quietly stops describing the game.  So this
plays whole matches on maps with camps and prints, per agent:

``camps``    lairs torn down per match: a camp is cleared for good only when its lair falls, so this
             counts finished jobs, not skirmishes with the guards.
``killed``   creatures put down per match.
``lost``     own units a creature put down per match.
``trickle``  units lost to the wilds per lair cleared, over the whole run.  This is the failure the
             design is most exposed to: a camp mends its wounded and calls its dead back out of the
             den, so a brain that feeds soldiers in a few at a time pours them into a sink with no
             bottom.  A number that climbs while ``camps`` stays near zero is that failure.
``hoard``    gold taken out of the lairs, per match.

    uv run python tools/creep_report.py --agents pro,hard --seeds 12
    uv run python tools/creep_report.py --agents medium,medium --seeds 8 --size Large
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its workers, not as a library
    fastsim.activate()

from warband.league import arena  # noqa: E402
from warband.league.arena import MatchSpec  # noqa: E402
from warband.sim import mapgen  # noqa: E402
from warband.sim.rules import CREATURES  # noqa: E402

CREATURE_NAMES = frozenset(t.value for t in CREATURES)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default="pro,pro", help="comma-separated agent names, one per seat")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--size", default="Medium", choices=list(mapgen.SIZES))
    ap.add_argument("--layout", default=None, help="one layout, or every one the map can hold")
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() // 4))
    args = ap.parse_args(argv)

    agents = tuple(args.agents.split(","))
    width, height = mapgen.dimensions(args.size, len(agents))
    layouts = [args.layout] if args.layout else [l.value for l in mapgen.layouts_for(width, height, len(agents))]
    specs = [MatchSpec(seed=1000 + seed, agents=agents, width=width, height=height, minutes=args.minutes, layout=layout)
             for seed in range(args.seeds) for layout in layouts]
    rows: dict[str, list[tuple[int, int, int, int]]] = {name: [] for name in agents}
    packed = [tuple(spec.__dict__[f] for f in arena.SPEC_FIELDS) for spec in specs]
    if args.workers <= 1:
        results = list(map(arena.play_spec_tuple, packed))
    else:
        with mp.get_context("spawn").Pool(args.workers) as workers:
            results = list(workers.imap_unordered(arena.play_spec_tuple, packed, chunksize=1))
    for result in results:
        for seat, name in enumerate(result.spec.agents):
            tally = result.tallies[seat]
            rows[name].append((tally.camps_cleared, sum(v for k, v in tally.killed.items() if k in CREATURE_NAMES),
                               sum(tally.lost_to_wilds.values()), tally.hoard))
    print(f"{len(specs)} matches, {args.size} {width}x{height}, layouts {','.join(layouts)}")
    print(f"{'agent':10} {'camps':>7} {'killed':>7} {'lost':>7} {'trickle':>8} {'hoard':>7}")
    for name, seats in rows.items():
        if not seats:
            continue
        camps = sum(r[0] for r in seats)
        lost = sum(r[2] for r in seats)
        print(f"{name:10} {statistics.mean(r[0] for r in seats):7.2f} {statistics.mean(r[1] for r in seats):7.2f} "
              f"{statistics.mean(r[2] for r in seats):7.2f} {lost / camps if camps else float('inf'):8.2f} "
              f"{statistics.mean(r[3] for r in seats):7.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
