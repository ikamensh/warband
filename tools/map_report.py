"""Map fairness over many seeds: what every base gets, per size and theme.

    uv run python tools/map_report.py [--seeds 100] [--players 2]

For each size and theme, generates the seeds and prints the range and mean of
open ground around each hall, the distance to the nearest mine and to wood,
the number of expansion mines and the terrain mix, plus how many maps were
not fully connected (the test suite requires zero).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband import mapgen  # noqa: E402
from warband.rules import MapTheme  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--players", type=int, default=2)
    args = parser.parse_args()
    for size, (width, height) in mapgen.SIZES.items():
        for theme in MapTheme:
            opens: list[int] = []
            mines: list[float] = []
            woods: list[float] = []
            expansions: list[int] = []
            trees: list[float] = []
            water: list[float] = []
            disconnected = 0
            no_wood = 0
            for seed in range(1, args.seeds + 1):
                world = mapgen.generate(seed=seed, width=width, height=height, players=args.players, theme=theme)
                report = mapgen.audit(world)
                opens.extend(report["open"])
                mines.extend(report["mine"])
                woods.extend(w for w in report["wood"] if w is not None)
                no_wood += sum(1 for w in report["wood"] if w is None)
                expansions.append(report["expansions"])
                trees.append(report["trees"])
                water.append(report["water"])
                disconnected += not report["connected"]
            print(f"{size:6s} {width}x{height} {theme.value:9s} seeds {args.seeds}: open {min(opens)}-{max(opens)} (mean {statistics.mean(opens):.0f} of 169), "
                  f"mine {min(mines):.0f}-{max(mines):.0f} (mean {statistics.mean(mines):.1f}), wood {min(woods):.0f}-{max(woods):.0f} (mean {statistics.mean(woods):.1f}), "
                  f"expansions {min(expansions)}-{max(expansions)}, trees {statistics.mean(trees):.0%}, water {statistics.mean(water):.0%}, "
                  f"disconnected {disconnected}, bases without wood {no_wood}")


if __name__ == "__main__":
    main()
