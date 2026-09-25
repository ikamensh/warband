"""Reweigh ``tests/shard_weights.json`` from a finished Tests run, so that CI's shards stay about as long as each other.

    uv run python tools/shard_weights.py RUN_ID     # the run's id: gh run list --workflow tests.yml

Every shard prints each test's setup, call and teardown times (``--durations=0``); a test's weight is their sum on
the runner.  The table names the tests of ten seconds or more, for the source slow tier and for the compiled tiers,
and weighs every other test the mean of the rest.  Refresh it when a shard runs markedly longer than its siblings.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "tests" / "shard_weights.json"
HEAVY = 10.0  # seconds: a test this long is named, the rest weigh their mean
MODES = {"slow tier ": "source", "compiled tiers ": "compiled"}  # the shard jobs' names, by the mode they run
LINE = re.compile(r"^(?P<job>[^\t]+)\t[^\t]*\t\S+ (?P<seconds>\d+\.\d+)s (?:setup|call|teardown) +(?P<test>\S.*)$")


def weigh(log: str) -> dict[str, dict]:
    """The table for the shards' durations in *log*, a run's log as ``gh run view --log`` prints it."""
    seconds: dict[str, dict[str, float]] = {mode: defaultdict(float) for mode in MODES.values()}
    for line in log.splitlines():
        if found := LINE.match(line):
            for prefix, mode in MODES.items():
                if found["job"].startswith(prefix):
                    seconds[mode][found["test"]] += float(found["seconds"])
    table = {}
    for mode, tests in seconds.items():
        rest = [spent for spent in tests.values() if spent < HEAVY]
        if not rest:
            raise SystemExit(f"no {mode} shard printed its durations: is this a Tests run with --durations=0?")
        table[mode] = {"other": round(sum(rest) / len(rest), 2),
                       "tests": {test: round(spent, 1) for test, spent in sorted(tests.items()) if spent >= HEAVY}}
    return table


def main() -> None:
    log = subprocess.run(["gh", "run", "view", sys.argv[1], "--log"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    TABLE.write_text(json.dumps(weigh(log), indent=1) + "\n")
    print(f"{TABLE.relative_to(ROOT)}: " + ", ".join(f"{mode} {len(t['tests'])} named, others {t['other']} s"
                                                     for mode, t in json.loads(TABLE.read_text()).items()))


if __name__ == "__main__":
    main()
