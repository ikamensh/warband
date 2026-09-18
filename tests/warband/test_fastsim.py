"""The compiled simulation is the simulation: matches played by it hash to the recorded fingerprint, to the bit,
and its C searches answer as path.py does."""

from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from warband import fastsim, path

ROOT = Path(__file__).resolve().parents[2]


def test_the_compiled_simulation_plays_the_recorded_fingerprint() -> None:
    build = fastsim.build()
    script = ("import sys; sys.path.insert(0, '.')\n"
              "import warband.model, warband.pro_ai\n"
              f"assert warband.model.__file__.startswith({str(build)!r}), warband.model.__file__\n"
              f"assert warband.pro_ai.__file__.startswith({str(build)!r}), warband.pro_ai.__file__\n"
              "from tools.sim_fingerprint import fingerprint\n"
              "print(fingerprint())\n")
    env = {k: v for k, v in os.environ.items() if k != fastsim.OPT_OUT} | {fastsim.ENV: str(build)}
    done = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == (ROOT / "tools" / "sim_fingerprint.txt").read_text().strip()


def test_a_build_of_other_sources_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ImportError, match="other sources"):
        fastsim.attach(tmp_path / "0123456789abcdef0123")


def _native_searches():
    """The C searches of the current build, loaded beside the Python ones this process runs."""
    build = fastsim.build()
    location = next((build / "warband").glob("_native.*"))
    spec = importlib.util.spec_from_file_location("warband._native", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _random_grid(rng: random.Random) -> tuple[bytearray, int, int]:
    width, height = rng.randint(1, 40), rng.randint(1, 30)
    density = rng.choice((0.0, 0.1, 0.3, 0.5, 0.7))
    return bytearray(rng.random() < density for _ in range(width * height)), width, height


def _tile(rng: random.Random, width: int, height: int) -> tuple[int, int]:
    return rng.randrange(width), rng.randrange(height)


def test_the_c_searches_answer_as_path_py_does() -> None:
    native = _native_searches()
    assert path._native is None  # this process runs the source, so path's functions are the Python ones
    rng = random.Random(20260918)
    for _ in range(1500):
        blocked, width, height = _random_grid(rng)
        start, goal = _tile(rng, width, height), _tile(rng, width, height)
        budget = rng.choice((path.MAX_EXPANSIONS, 5, 60))
        assert (native.find_path_grid(start, goal, blocked, width, height, budget)
                == path.find_path_grid(start, goal, blocked, width, height, max_expansions=budget))
        goals = {_tile(rng, width, height): rng.choice((0, 0.0, 1.5, rng.random() * 9)) for _ in range(rng.randint(0, 6))}
        assert native.find_work_path(start, goals, blocked, width, height) == path.find_work_path(start, goals, blocked, width, height)
        starts = [rng.randrange(width * height) for _ in range(rng.randint(0, 4))]
        assert native.distance_field(iter(starts), blocked, width, height) == path.distance_field(iter(starts), blocked, width, height)
        regions = path.Regions(blocked, width, height)
        labels = array("i", bytes(4 * width * height))
        assert native.region_labels(blocked, width, height, labels) == max(regions.labels, default=0)
        assert list(labels) == regions.labels
        region = regions.label(start)
        if region and regions.label(goal) != region:  # the case reachable_goal scans the region for
            assert native.nearest_in_region(labels, region, goal, width) == regions.reachable_goal(start, goal)
