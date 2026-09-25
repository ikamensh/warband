"""Shared fixtures (a mock-backend Game torn down after every test, from saga2d.testing.fixtures) and the suite's two tiers.

``uv run pytest -q`` runs the fast tier: every test not marked ``slow``. ``--slow`` adds the slow tier, and
``--slow -m slow`` runs it alone; a slow test's docstring (or its module's, for a module marked slow) says why it
cannot be fast. ``--budget SECONDS`` fails a fast-tier test whose setup, call or teardown takes longer.

The suite runs the simulation from source, the reference. ``--compiled`` runs it on the compiled simulation
(``warband.league.fastsim``), as the game does: a value the game's own code hands the simulation that its annotations
refuse is a ``TypeError`` only there. A test that inspects the source itself (counts calls by patching a function,
reads a module's file) is marked ``source_only`` and is left out.

``--shard I/N`` runs the I-th of N parts of whatever else selects, so CI spreads a tier over N runners: :func:`deal`
gives each test to exactly one part, heaviest first to the lightest part, by the seconds ``shard_weights.json`` records
for it on a runner (a test it does not name weighs its ``other``), and a part runs its heavy tests first. A stale table
only unbalances the parts; ``tools/shard_weights.py`` reweighs it from a CI run. Each part records what it kept of the
selection in the pytest cache (``.pytest_cache/v/shard/``), where CI's last job, ``tools/shard_check.py``, reads them.
"""
import json
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

WEIGHTS = Path(__file__).with_name("shard_weights.json")

pytest_plugins = ["saga2d.testing.fixtures"]


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="also run the slow tier: tests marked slow")
    parser.addoption("--budget", type=float, metavar="SECONDS",
                     help="fail a fast-tier test whose setup, call or teardown takes longer than SECONDS")
    parser.addoption("--compiled", action="store_true", help="run on the compiled simulation, as the game does")
    parser.addoption("--shard", type=shard, metavar="I/N", help="run the I-th of N parts of the selected tests (CI's runners)")


def shard(text: str) -> tuple[int, int]:
    index, count = (int(part) for part in text.split("/"))
    if not 1 <= index <= count:
        raise ValueError(text)
    return index, count


def deal(nodeids: Iterable[str], count: int, seconds: Mapping[str, float], other: float) -> list[list[str]]:
    """*nodeids* in *count* parts of about equal *seconds*, every one in exactly one: the heaviest first, each to the
    lightest part so far.  A function of the set of ids alone, so every process that collected them deals them alike."""
    parts: list[list[str]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for nodeid in sorted(set(nodeids), key=lambda nodeid: (-seconds.get(nodeid, other), nodeid)):
        lightest = loads.index(min(loads))
        parts[lightest].append(nodeid)
        loads[lightest] += seconds.get(nodeid, other)
    return parts


def weights(compiled: bool) -> tuple[dict[str, float], float]:
    """The recorded runner seconds of the heavy tests, source or compiled, and what any other test weighs."""
    table = json.loads(WEIGHTS.read_text())["compiled" if compiled else "source"]
    return table["tests"], table["other"]


def pytest_xdist_auto_num_workers(config):
    """``-n auto`` (the default, in pyproject.toml) spreads a whole tier over four workers; a run that names its
    files or tests, or keeps their output (-s), stays in this process, where prints and debuggers work."""
    if config.option.capture == "no" or any(arg.split("::")[0].endswith(".py") for arg in config.args):
        return 0
    return 4


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: too slow for the fast tier, its docstring says why; runs with --slow")
    config.addinivalue_line("markers", "source_only(why): inspects the simulation's source; --compiled leaves it out")
    if config.getoption("--compiled"):  # before any test module imports the simulation; workers take this build
        from warband.league import fastsim

        fastsim.activate()


def why_slow(item) -> str | None:
    """The docstring of the node that marks *item* slow: the test itself, its class or its module."""
    node = next(node for node in reversed(item.listchain()) if any(mark.name == "slow" for mark in node.own_markers))
    return node.obj.__doc__


@pytest.hookimpl(trylast=True)  # after -m and -k have deselected: a shard is a part of what is left
def pytest_collection_modifyitems(config, items):
    config.collected = [item.nodeid for item in items]  # the slow tier too, even when left out: test_ci_shards.py deals it
    if config.getoption("--compiled"):
        for item in items:
            if marker := item.get_closest_marker("source_only"):
                item.add_marker(pytest.mark.skip(reason=f"source only: {marker.args[0]}"))
    slow = [item for item in items if item.get_closest_marker("slow")]
    for item in slow:
        if not why_slow(item):
            raise pytest.UsageError(f"{item.nodeid} is marked slow without a docstring saying why it cannot be fast")
    if not config.getoption("--slow") and slow:
        config.hook.pytest_deselected(items=slow)
        items[:] = [item for item in items if not item.get_closest_marker("slow")]
        config.slow_deselected = len(slow)
        if hasattr(config, "workeroutput"):  # an xdist worker: the controller adds nothing up by itself
            config.workeroutput["slow_deselected"] = len(slow)
    if part := config.getoption("--shard"):
        index, count = part
        seconds, other = weights(config.getoption("--compiled"))
        mine = set(deal((item.nodeid for item in items), count, seconds, other)[index - 1])
        config.hook.pytest_deselected(items=[item for item in items if item.nodeid not in mine])
        config.shard_record = {"part": index, "of": count, "selected": sorted(item.nodeid for item in items), "kept": sorted(mine)}
        # the heavy tests first, so that none starts late on a worker and holds up the end; the rest keep their order
        items[:] = sorted((item for item in items if item.nodeid in mine), key=lambda item: -seconds.get(item.nodeid, other))
        if hasattr(config, "workeroutput"):
            config.workeroutput["shard_record"] = config.shard_record


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    node.config.slow_deselected = max(getattr(node.config, "slow_deselected", 0), node.workeroutput.get("slow_deselected", 0))
    if "shard_record" in node.workeroutput:
        node.config.shard_record = node.workeroutput["shard_record"]


def pytest_sessionfinish(session):
    """A shard's record of what it kept, for ``tools/shard_check.py``, written once, by the process workers report to;
    its split is the command line but the ``--shard``, which the split's other parts share."""
    config = session.config
    if (record := getattr(config, "shard_record", None)) and not hasattr(config, "workeroutput"):
        args, split = list(config.invocation_params.args), []
        while args:
            arg = args.pop(0)
            if arg == "--shard":
                args.pop(0)
            elif not arg.startswith("--shard="):
                split.append(arg)
        config.cache.set(f"shard/{record['part']}-of-{record['of']}", {"split": split, **record})


def pytest_terminal_summary(terminalreporter, config):
    """The fast tier says what it left out, and a shard what share it ran, with or without workers."""
    if getattr(config, "slow_deselected", 0):
        terminalreporter.write_sep("-", f"{config.slow_deselected} slow tests deselected: --slow runs them too")
    if record := getattr(config, "shard_record", None):
        terminalreporter.write_sep("-", f"shard {record['part']}/{record['of']}: {len(record['kept'])} of the "
                                        f"{len(record['selected'])} selected tests, the other shards run the rest")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    budget = item.config.getoption("--budget")
    if budget is not None and report.passed and report.duration > budget and not item.get_closest_marker("slow"):
        report.outcome = "failed"
        report.longrepr = (f"{report.when} took {report.duration:.2f} s, over the fast tier's budget of {budget:g} s: "
                           "make it faster, or mark it slow with a docstring saying why")
    return report


@pytest.fixture(scope="session", autouse=True)
def ground_painted_once():
    """A chunk of painted ground is a pure function of the terrain around it, its place, scale, theme and water
    phase, so the session paints each once rather than once per scene: painting took a quarter of the fast tier."""
    from warband.art import textures

    paint, painted = textures.ground_chunk, OrderedDict()

    def ground_chunk(terrain_at, in_bounds, cx, cy, scale, theme=textures.MapTheme.SUMMER, phase=0):
        x0, y0, n = cx * textures.CHUNK - 3, cy * textures.CHUNK - 3, textures.CHUNK + 6  # the chunk, its margin, the shores' neighbours
        around = tuple(terrain_at((x, y)) if in_bounds((x, y)) else None for y in range(y0, y0 + n) for x in range(x0, x0 + n))
        key = (around, cx, cy, scale, theme, phase)
        if key in painted:
            painted.move_to_end(key)
        else:
            painted[key] = paint(terrain_at, in_bounds, cx, cy, scale, theme, phase)
            if len(painted) > 192:  # the last few maps' chunks, some 80 MB: tests of one map come together
                painted.popitem(last=False)
        return painted[key]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(textures, "ground_chunk", ground_chunk)
        yield
