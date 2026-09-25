"""CI spreads a tier over runners with ``--shard I/N`` (``tests/conftest.py``): no test may fall between them.

The Tests workflow's last job holds every run to it: each shard leaves a record of what it kept, and
``tools/shard_check.py`` fails the run unless every part of each split ran and every selected test ran in exactly one.
These tests catch it before a push: the workflow runs every part of each split, :func:`deal` gives every test the
session collected (both tiers, in the fast tier's run: the whole suite) to exactly one part, and the check refuses
records that lose a test, repeat one, lack a part or disagree about the selection.
"""

import re
from collections import defaultdict
from itertools import chain
from pathlib import Path

import pytest

from tests.conftest import deal, weights
from tools import shard_check

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml"


def splits() -> dict[tuple[str, int], set[int]]:
    """Each sharded command of the workflow, with the shard spec taken out and its count, to the parts it runs."""
    parts: dict[tuple[str, int], set[int]] = defaultdict(set)
    for line in WORKFLOW.read_text().splitlines():
        if found := re.search(r"--shard (\d+)/(\d+)", line):
            parts[(line.replace(found[0], "").strip(), int(found[2]))].add(int(found[1]))
    return parts


def test_the_workflow_runs_every_part_of_each_split() -> None:
    assert splits(), "the workflow shards nothing: this test and --shard have lost their point"
    for (command, count), parts in splits().items():
        assert parts == set(range(1, count + 1)), (command, count, sorted(parts))


@pytest.mark.parametrize("compiled", [False, True])
def test_every_collected_test_is_in_exactly_one_part_of_each_split(request, compiled: bool) -> None:
    collected = set(request.config.collected)
    for count in sorted({count for _, count in splits()}):
        parts = deal(collected, count, *weights(compiled))
        assert len(parts) == count
        assert sorted(chain.from_iterable(parts)) == sorted(collected), count


def records(collected: set[str], count: int, split: tuple[str, ...] = ("-q", "--slow")) -> list[dict]:
    """The records the *count* shards of *split* would leave for *collected*."""
    return [{"split": list(split), "part": index, "of": count, "selected": sorted(collected), "kept": sorted(kept)}
            for index, kept in enumerate(deal(collected, count, *weights(False)), 1)]


def test_the_check_passes_the_parts_deal_makes_and_nothing_less(request) -> None:
    collected = set(request.config.collected)
    good = records(collected, 3)
    assert shard_check.problems(good) == []

    lost = records(collected, 3)
    test = lost[1]["kept"].pop()
    assert shard_check.problems(lost) == [f"-q --slow: {test} ran in no part"]
    for part in (lost[0], lost[2]):
        part["kept"].append(test)
    assert shard_check.problems(lost) == [f"-q --slow: {test} ran in 2 parts"]

    assert "not each part once" in shard_check.problems(good[:2])[0]
    other = records(collected - {test}, 3)
    assert "selected different tests" in shard_check.problems([*good[:2], other[2]])[0]
    assert shard_check.problems(good + records(collected - {test}, 2, ("--compiled",))) == []  # a split of its own
