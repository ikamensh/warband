"""Wall time of whole arena matches on one core: what a ladder, a league or a tune pays per game.

    uv run python tools/sim_bench.py                 # the standard set, once
    uv run python tools/sim_bench.py --repeat 3      # best of three runs per match
    uv run python tools/sim_bench.py --check tools/sim_bench.txt   # and the results are the recorded ones

The standard set is nine matches as the ladder plays them (sizes and layouts
cycled by seed, settled matches stopped early): Master mirrors, Hard against
Master, Medium against Hard and a four-player free-for-all.  Each match is
timed by the processor time it took, which other work on the machine
disturbs far less than the wall clock, and the fastest of ``--repeat`` runs
counts.  The simulation is the compiled one (:mod:`warband.fastsim`) unless
``WARBAND_INTERPRETED=1``.

The digest covers every match's result as the arena records it (placements,
steps, and each player's tallies with their per-minute timeline), wall time
left out, so a speed change that is only a speed change prints the same
digest.  ``tools/sim_fingerprint.py`` is the finer guard: it hashes the
world itself every ten seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband import fastsim  # noqa: E402

if __name__ == "__main__":  # run as a program, not imported: its worker processes follow through WARBAND_FASTSIM
    fastsim.activate()  # the compiled simulation, unless WARBAND_INTERPRETED is set

from warband import arena  # noqa: E402
from warband.arena import MatchSpec  # noqa: E402
from tools.arena import _board  # noqa: E402

MATCHES = (
    (1, ("master", "master")),
    (2, ("master", "master")),
    (3, ("master", "master")),
    (4, ("master", "master")),
    (5, ("hard", "master")),
    (6, ("master", "hard")),
    (7, ("medium", "hard")),
    (8, ("hard", "medium")),
    (9, ("master", "hard", "medium", "master")),
)


def specs() -> list[MatchSpec]:
    out = []
    for seed, agents in MATCHES:
        board = _board(seed)
        if len(agents) > 2:
            board["width"] = max(board["width"], 64)  # four players need room, as tools/arena.py gives them
        out.append(MatchSpec(seed=seed, agents=agents, **board))
    return out


def digest(records: list[dict]) -> str:
    rows = [{k: v for k, v in record.items() if k != "wall"} for record in records]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=1, help="runs per match; the fastest counts")
    parser.add_argument("--check", type=Path, help="a file holding a recorded digest; exit 1 when the results differ")
    parser.add_argument("--write", type=Path, help="record the digest into this file")
    args = parser.parse_args()
    records, total, total_steps = [], 0.0, 0
    for spec in specs():
        best = None
        for _ in range(args.repeat):
            started = time.process_time()
            result = arena.play(spec)
            spent = time.process_time() - started
            best = spent if best is None else min(best, spent)
        record = arena.to_record(result)
        records.append(record)
        total += best
        total_steps += result.steps
        print(f"seed {spec.seed:>2} {'-'.join(spec.agents):<28} {spec.width}x{spec.height} {spec.layout:<9} "
              f"{result.steps:>6} steps  {best:6.2f} s  {1000 * best / result.steps:.3f} ms/step", flush=True)
    print(f"total {total:.2f} s for {total_steps} steps, {1000 * total / total_steps:.3f} ms/step")
    got = digest(records)
    print(f"digest {got}")
    if args.write:
        args.write.write_text(got + "\n")
    if args.check:
        want = args.check.read_text().strip()
        if want != got:
            print(f"DRIFT: recorded {want}, got {got}", file=sys.stderr)
            raise SystemExit(1)
        print("matches the recorded digest")


if __name__ == "__main__":
    main()
