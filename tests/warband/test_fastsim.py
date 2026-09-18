"""The compiled simulation is the simulation: matches played by it hash as the source's do on the same machine, to
the bit, and its C searches and painting answer as the Python does.

The first test to need the build compiles the simulation with mypyc, a minute or more on a fresh machine, so the
module is the slow tier's."""

from __future__ import annotations

import importlib.util
import math
import os
import random
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from warband import ai, fastsim, mapgen, model, path, worker_ai
from warband.ai import make_brain
from warband.model import World
from warband.rules import BUILDINGS, BuildingType, Difficulty, Terrain
from warband.worker_knowledge import WorkerKnowledge

pytestmark = [pytest.mark.slow, pytest.mark.xdist_group("fastsim")]  # one worker, one compile

ROOT = Path(__file__).resolve().parents[2]


def _run_compiled(script: str) -> str:
    """What *script* prints, run in a fresh process on the compiled simulation of the current sources."""
    build = fastsim.build()
    prelude = ("import sys; sys.path.insert(0, '.')\n"
               "from warband import fastsim\n"
               f"fastsim.attach({str(build)!r})\n"
               "import warband.model, warband.pro_ai\n"
               f"assert warband.model.__file__.startswith({str(build)!r}), warband.model.__file__\n"
               f"assert warband.pro_ai.__file__.startswith({str(build)!r}), warband.pro_ai.__file__\n")
    env = {k: v for k, v in os.environ.items() if k not in (fastsim.OPT_OUT, fastsim.ENV)}
    done = subprocess.run([sys.executable, "-c", prelude + script], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=900)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_compiled_simulation_plays_the_source_fingerprint() -> None:
    """Compiled or not, the fingerprint matches hash the same on this machine.  Not necessarily to the recorded
    hash: that one is macOS's, and glibc and the Windows runtime round some sines, cosines and arctangents
    differently in the last bit, the source's as much as the compiled simulation's."""
    from tools.sim_fingerprint import fingerprint

    printed = _run_compiled("from tools.sim_fingerprint import fingerprint\nprint(fingerprint())\n")
    assert printed.strip() == fingerprint()


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
        field = array("d", bytes(8 * width * height))
        native.distance_field(iter(starts), blocked, width, height, field)
        assert list(field) == path.distance_field(iter(starts), blocked, width, height)
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
            assert native.any_lit(source, x, y, size, size, width, height) == knowledge.sees(source, x, y, size)
            w, h = rng.randint(1, 4), rng.randint(1, 4)
            world.visible[0][:] = source
            assert native.any_lit(source, x, y, w, h, width, height) == world.any_visible(0, (x, y, w, h))


def test_the_c_terrain_scan_finds_what_the_python_finds() -> None:
    native = _native_searches()
    rng = random.Random(1809)
    kinds = list(Terrain)
    for _ in range(300):
        width, height = rng.randint(1, 50), rng.randint(1, 40)
        rows = [[rng.choice(kinds) for _ in range(width)] for _ in range(height)]
        knowledge = WorkerKnowledge(width, height)
        knowledge.terrain = [rng.choice((None, rows[i // width][i % width], rng.choice(kinds))) for i in range(width * height)]
        visible = bytearray(rng.random() < rng.random() for _ in range(width * height))
        assert native.stale_tiles(visible, rows, knowledge.terrain, width, height) == knowledge._stale(rows, visible)


def test_the_c_tree_choice_is_the_python_choice() -> None:
    native = _native_searches()
    rng = random.Random(4242)
    chosen = 0
    for _ in range(600):
        blocked, width, height = _random_grid(rng)
        size = width * height
        remembered = [rng.choice((None, Terrain.GRASS, Terrain.TREES, Terrain.TREES)) for _ in range(size)]
        trees = tuple(sorted(rng.sample(range(size), min(size, rng.randint(0, 25)))))  # mostly trees, some not any more
        felling = set(rng.sample(trees, min(len(trees), rng.randint(0, 3))))
        depots = [rng.randrange(size) for _ in range(rng.randint(0, 3))]
        field = array("d", bytes(8 * size))
        native.distance_field(depots, blocked, width, height, field)
        start = _tile(rng, width, height)
        expected = worker_ai._choose_tree(start, trees, felling, remembered, list(field), blocked, width, height)
        assert native.choose_tree(start, trees, felling, remembered, Terrain.TREES, field, blocked, worker_ai._reach(1, 1),
                                  width, height) == expected
        chosen += expected is not None
    assert chosen > 100  # most searches found a tree, so the comparison covered the tie-breaks too


def test_the_c_site_search_finds_the_python_site() -> None:
    native = _native_searches()
    rng = random.Random(55)
    found = 0
    for seed in (5, 11):
        world = mapgen.generate(seed=seed, players=2, human=None)
        brains = [make_brain(0, Difficulty.HARD), make_brain(1, Difficulty.MEDIUM)]
        for step in range(2400):
            for brain in brains:
                brain.think(world, rng)
            world.step()
            if step % 300 != 299:
                continue
            for player in (0, 1):
                hall = world.player_buildings(player, BuildingType.TOWN_HALL)[0]
                for building_type in BuildingType:
                    anchor = (hall.x + rng.uniform(-6, 6), hall.y + rng.uniform(-6, 6))
                    taken = [((hall.x + rng.randint(-9, 9), hall.y + rng.randint(-9, 9)), rng.randint(1, 4)) for _ in range(3)]
                    size = BUILDINGS[building_type].size
                    draws = random.Random(rng.random())
                    twin = random.Random()
                    twin.setstate(draws.getstate())
                    answer = native.site_search(ai.site_ring(2 + size, 12), int(anchor[0]) - size // 2, int(anchor[1]) - size // 2,
                                                draws.random, *ai.site_inputs(world, building_type, player, taken))
                    assert answer == ai.site_search(world, building_type, player, anchor, twin, 2, 12, taken)
                    assert draws.getstate() == twin.getstate()  # the same numbers were drawn, found or not
                    found += answer is not None
    assert found > 20


def _hypot_cases(rng: random.Random, count: int) -> list[tuple[float, float]]:
    """Coordinate pairs as the simulation meets them (differences of positions on a map, tile offsets, a hair
    apart) and as it never does (vast and tiny magnitudes, zeros, infinities and NaNs)."""
    specials = [0.0, -0.0, 1.0, 0.5, 1e-300, 5e-324, 1e300, math.inf, -math.inf, math.nan, 2.0 ** -1000, 2.0 ** 1000]
    cases = [(a, b) for a in specials for b in specials]
    for _ in range(count):
        kind = rng.randrange(6)
        if kind == 0:
            a, b = rng.uniform(-200, 200), rng.uniform(-200, 200)
        elif kind == 1:
            a, b = rng.randint(-40, 40) + rng.choice((0.0, 0.5)), rng.randint(-40, 40) + rng.choice((0.0, 0.5))
        elif kind == 2:
            p, q = rng.uniform(0, 100), rng.uniform(0, 100)
            a, b = p - (p + rng.choice((1e-15, 1e-9, 1e-6))), q - rng.uniform(0, 100)
        elif kind == 3:
            a, b = 10.0 ** rng.uniform(-30, 30), 10.0 ** rng.uniform(-30, 30)
        elif kind == 4:
            a, b = rng.uniform(-1, 1) * 10.0 ** rng.uniform(-300, 300), rng.uniform(-1, 1) * 10.0 ** rng.uniform(-300, 300)
        else:
            a = rng.uniform(-50, 50)
            b = a * rng.choice((1.0, -1.0, 0.0, 1e-160, 1e160))
        cases.append((a, b))
    return cases


def test_the_hypot_port_is_math_hypot_run_from_source() -> None:
    port = model.hypot_port
    assert model.hypot is math.hypot  # the source runs math's own
    for a, b in _hypot_cases(random.Random(3), 60000):
        assert math.hypot(a, b).hex() == port(a, b).hex() or math.isnan(math.hypot(a, b)) and math.isnan(port(a, b)), (a, b)


def test_the_compiled_hypot_is_math_hypot() -> None:
    printed = _run_compiled("import math, random\n"
                            "import warband.model as model\n"
                            "from tests.warband.test_fastsim import _hypot_cases\n"
                            "assert model.hypot is not math.hypot and model.hypot_port is model.hypot\n"
                            "bad = [(a, b) for a, b in _hypot_cases(random.Random(4), 3_000_000)\n"
                            "       if model.hypot(a, b).hex() != math.hypot(a, b).hex() and not math.isnan(math.hypot(a, b))]\n"
                            "print(len(bad), bad[:5])\n")
    assert printed.startswith("0 "), printed
