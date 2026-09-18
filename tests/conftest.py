"""Shared fixtures (a mock-backend Game torn down after every test, from saga2d.testing.fixtures) and the suite's two tiers.

``uv run pytest -q`` runs the fast tier: every test not marked ``slow``. ``--slow`` adds the slow tier, and
``--slow -m slow`` runs it alone; a slow test's docstring (or its module's, for a module marked slow) says why it
cannot be fast. ``--budget SECONDS`` fails a fast-tier test whose setup, call or teardown takes longer.
"""
from collections import OrderedDict

import pytest

pytest_plugins = ["saga2d.testing.fixtures"]


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="also run the slow tier: tests marked slow")
    parser.addoption("--budget", type=float, metavar="SECONDS",
                     help="fail a fast-tier test whose setup, call or teardown takes longer than SECONDS")


def pytest_xdist_auto_num_workers(config):
    """``-n auto`` (the default, in pyproject.toml) spreads a whole tier over four workers; a run that names its
    files or tests, or keeps their output (-s), stays in this process, where prints and debuggers work."""
    if config.option.capture == "no" or any(arg.split("::")[0].endswith(".py") for arg in config.args):
        return 0
    return 4


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: too slow for the fast tier, its docstring says why; runs with --slow")


def why_slow(item) -> str | None:
    """The docstring of the node that marks *item* slow: the test itself, its class or its module."""
    node = next(node for node in reversed(item.listchain()) if any(mark.name == "slow" for mark in node.own_markers))
    return node.obj.__doc__


def pytest_collection_modifyitems(config, items):
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


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    node.config.slow_deselected = max(getattr(node.config, "slow_deselected", 0), node.workeroutput.get("slow_deselected", 0))


def pytest_terminal_summary(terminalreporter, config):
    """The fast tier says what it left out, with or without workers."""
    if getattr(config, "slow_deselected", 0):
        terminalreporter.write_sep("-", f"{config.slow_deselected} slow tests deselected: --slow runs them too")


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
    from warband import textures

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
