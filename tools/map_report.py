"""Map fairness over many seeds: what every base gets, per size and layout.

    uv run python tools/map_report.py [--seeds 100] [--players 2]

Only the sizes and layouts that can seat that many players are reported; ``mapgen.sizes_for`` and
``mapgen.layouts_for`` say which those are.

For each size and layout, generates the seeds and prints the range and mean of
open ground around each hall, the distance to the nearest mine and to wood,
the number of mines beyond the main ones and how many of those are endless
gold seams, the terrain mix, the detour a walk
between the first two halls makes over the straight line, how many seeds
needed a retry to pass the audit, how many seeds had no fair map after every
retry, and how many maps were not fully connected (the test suite requires zero).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.sim import mapgen  # noqa: E402
from warband.sim.rules import Layout  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--players", type=int, default=2)
    args = parser.parse_args()
    for size in mapgen.sizes_for(args.players):
        width, height = mapgen.dimensions(size, args.players)
        for layout in mapgen.layouts_for(width, height, args.players):
            opens: list[int] = []
            detours: list[float] = []
            retried = 0
            mines: list[float] = []
            woods: list[float] = []
            expansions: list[int] = []
            seams: list[int] = []
            trees: list[float] = []
            water: list[float] = []
            disconnected = 0
            no_wood = 0
            refused = 0
            for seed in range(1, args.seeds + 1):
                try:
                    world, report = mapgen.build(seed, width, height, args.players, layout=layout)
                except mapgen.NoFairMap:
                    refused += 1
                    continue
                retried += report["attempt"] > 0
                if report["detour"] is not None:
                    detours.append(report["detour"])
                opens.extend(report["open"])
                mines.extend(report["mine"])
                woods.extend(w for w in report["wood"] if w is not None)
                no_wood += sum(1 for w in report["wood"] if w is None)
                expansions.append(report["expansions"])
                seams.append(report["seams"])
                trees.append(report["trees"])
                water.append(report["water"])
                disconnected += not report["connected"]
            if not opens:
                raise RuntimeError(f"no fair {layout.value} map at {size} for {args.players} players")
            print(f"{size:6s} {width}x{height} {layout.value:9s} seeds {args.seeds}: open {min(opens)}-{max(opens)} (mean {statistics.mean(opens):.0f} of 169), "
                  f"mine {min(mines):.0f}-{max(mines):.0f} (mean {statistics.mean(mines):.1f}), wood {min(woods):.0f}-{max(woods):.0f} (mean {statistics.mean(woods):.1f}), "
                  f"expansions {min(expansions)}-{max(expansions)}, seams {min(seams)}-{max(seams)}, trees {statistics.mean(trees):.0%}, water {statistics.mean(water):.0%}, "
                  f"detour {min(detours):.2f}-{max(detours):.2f}, retried {retried}, refused {refused}, disconnected {disconnected}, bases without wood {no_wood}")


if __name__ == "__main__":
    main()
