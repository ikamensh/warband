"""The compiled simulation is the simulation: matches played by it hash to the recorded fingerprint, to the bit,
and its C searches and painting answer as the Python does."""

from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from warband import fastsim, model, path, worker_ai
from warband.model import World
from warband.rules import Terrain
from warband.worker_knowledge import WorkerKnowledge

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


def test_the_c_painting_paints_as_the_python_does() -> None:
    native = _native_searches()
    rng = random.Random(918)
    for _ in range(400):
        width, height = rng.randint(1, 50), rng.randint(1, 40)
        world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 1, rng=random.Random(1))
        discs = {((rng.randint(-3, width + 2), rng.randint(-3, height + 2)), rng.randint(0, 9)) for _ in range(rng.randint(0, 8))}
        painted, reference = bytearray(width * height), bytearray(width * height)
        native.stamp_discs(painted, discs, width, height)
        for at, radius in discs:
            world._reveal(reference, at, radius)
        assert painted == reference
        threats = tuple((rng.uniform(-1, width + 1), rng.uniform(-1, height + 1), rng.choice((2.5, 3.0, rng.uniform(0, 9))))
                        for _ in range(rng.randint(0, 6)))
        painted, reference = bytearray(rng.random() < 0.2 for _ in range(width * height)), None
        reference = bytearray(painted)
        native.stamp_threats(painted, threats, width, height)
        worker_ai._stamp_units(reference, threats, width, height)
        assert painted == reference
        target, source = bytearray(rng.random() < 0.3 for _ in range(width * height)), bytes(rng.random() < 0.3 for _ in range(width * height))
        expected = bytearray(target)
        model.or_into(expected, source)
        native.or_into(target, source)
        assert target == expected
        knowledge = WorkerKnowledge(width, height)
        for _ in range(10):
            x, y, size = rng.randint(-4, width + 1), rng.randint(-4, height + 1), rng.randint(1, 4)
            assert native.any_lit(source, x, y, size, width, height) == knowledge.sees(source, x, y, size)
