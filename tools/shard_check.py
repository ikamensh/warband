"""Every test a split of CI's selects ran in exactly one of its shards: the Tests workflow's last job.

    python3 tools/shard_check.py DIR     # the records under DIR; a --shard run leaves one in .pytest_cache/v/shard/

A record (``tests/conftest.py``) names its split (the command line but ``--shard``), its part I of N, the tests the
split selected and those the part kept.  Each split must have every part 1..N once, the same selection in each, and
each selected test kept by exactly one part, so that a runner that collected otherwise than its siblings, or a part
that never ran, fails the run.  Standard library only: the workflow runs it without installing the project.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def splits(records: list[dict]) -> dict[str, list[dict]]:
    """*records* by the split they are parts of."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[" ".join(record["split"])].append(record)
    return dict(sorted(grouped.items()))


def problems(records: list[dict]) -> list[str]:
    """What keeps *records* from running each test of each split exactly once, a line each; none when nothing does."""
    found = []
    for split, parts in splits(records).items():
        counts, numbers = {part["of"] for part in parts}, sorted(part["part"] for part in parts)
        if len(counts) > 1 or numbers != list(range(1, max(counts) + 1)):
            found.append(f"{split}: parts {numbers} of {sorted(counts)}, not each part once")
        selections = {tuple(part["selected"]) for part in parts}
        if len(selections) > 1:
            found.append(f"{split}: the parts selected different tests, {sorted(len(tests) for tests in selections)} of them")
        selected = {test for tests in selections for test in tests}
        kept = Counter(test for part in parts for test in part["kept"])
        found += [f"{split}: {test} ran in no part" for test in sorted(selected - kept.keys())]
        found += [f"{split}: {test} ran in {times} parts" for test, times in sorted(kept.items()) if times > 1]
        found += [f"{split}: {test} ran but was never selected" for test in sorted(kept.keys() - selected)]
    return found


def main(folder: str) -> int:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(folder).rglob("*")) if path.is_file()]
    if not records:
        print(f"no shard records under {folder}", file=sys.stderr)
        return 1
    if found := problems(records):
        print("\n".join(found[:40]) + (f"\n... and {len(found) - 40} more" if len(found) > 40 else ""), file=sys.stderr)
        return 1
    for split, parts in splits(records).items():
        print(f"{split}: each of the {len(parts[0]['selected'])} tests ran in exactly one of {len(parts)} parts")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
