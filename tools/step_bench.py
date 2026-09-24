"""Model step times without a window: the simulation alone.

    uv run python tools/step_bench.py [--steps 300] [--repeat 3] [--profile]
    uv run python tools/step_bench.py --scenario seats --seats 16 [--steps 3000]

Two armies of six unit types meet between twelve farms on a large map and
are ordered at each other; the world is then stepped in place.  The step
is timed with a wall clock, and the run with the lowest mean of ``--repeat``
is reported (other work on the machine only ever makes a run slower).
``--profile`` adds a cProfile breakdown of the last run (the profiler
roughly doubles the times, so read it for shares, not for milliseconds).  ``tools/perf.py`` times whole frames on the real
backend with this same battle.

``--scenario seats`` plays a real match of ``--seats`` computer players instead, on the biggest map
that seats them, and times the step and the brains apart: what a match of many seats costs is fog,
worker memory and brains per seat as much as it is units.  The simulation runs at 20 Hz, so a step
over 50 ms is a match that cannot keep time.
"""

from __future__ import annotations

import argparse
import cProfile
import random
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its worker processes, not as a library
    fastsim.activate()  # the compiled simulation, unless WARBAND_INTERPRETED is set

from warband.sim import mapgen  # noqa: E402
from warband.sim.model import World, tile_center  # noqa: E402  (Difficulty and make_brain are imported where used: the brains are only wanted by --scenario seats)
from warband.sim.rules import BuildingType, Layout, Terrain, UnitType  # noqa: E402


def standing(w: World, tile: tuple[int, int]) -> tuple[float, float]:
    """*tile*'s centre, or the nearest free one beside a building standing on it (a mine lies in the field)."""
    if w.building_at(tile) is None:
        return tile_center(tile)
    free = w.free_tile_near((tile[0], tile[1], 1, 1), prefer=tile_center(tile))
    assert free is not None, tile
    return tile_center(free)


def battle_world(seed: int = 3, width: int = 64, height: int = 48) -> World:
    """Seventy-five units a side on attack-move towards the other side, twelve farms between them.

    The battlefield is cleared to grass, as map generation carves a road: once the seed drew its own layout,
    its trees held 72 of the 150 soldiers where they were placed, and 41 were still in them 300 steps on,
    planning a way out every 0.6 s (WB-024).
    """
    w = mapgen.generate(seed=seed, width=width, height=height, players=2, layout=Layout.PLAINS)
    hall = w.player_buildings(0, BuildingType.TOWN_HALL)[0]
    hx, hy = hall.pos
    for y in range(hy + 3, min(height, hy + 19)):
        for x in range(hx + 3, min(width, hx + 40)):
            if w.building_at((x, y)) is None:
                w.terrain[y][x] = Terrain.GRASS
                w._blocked[y * w.width + x] = 0
    w.reveal_all(0)
    types = [UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT, UnitType.FLYING_MACHINE, UnitType.CATAPULT, UnitType.CLERIC]
    for i in range(75):
        w.spawn_unit(0, types[i % 6], standing(w, (hx + 4 + i % 15, hy + 4 + i // 15)))
        w.spawn_unit(1, types[(i + 1) % 6], standing(w, (hx + 22 + i % 15, hy + 4 + i // 15)))
    for i in range(12):
        w.place_building(0 if i % 2 == 0 else 1, BuildingType.FARM, (hx + 4 + (i % 6) * 3, hy + 11 + (i // 6) * 3))
    w.update_vision()
    mine = [u.id for u in w.player_units(0) if not u.is_worker]
    theirs = [u.id for u in w.player_units(1) if not u.is_worker]
    w.attack_move(mine, tile_center((hx + 25, hy + 7)))
    w.attack_move(theirs, tile_center((hx + 8, hy + 7)))
    return w


def seats_world(seats: int, seed: int = 3) -> tuple[World, list]:
    """A match of *seats* computer players on the biggest map that seats them, and their brains."""
    from warband.brains.ai import make_brain
    from warband.sim.rules import Difficulty
    size = mapgen.sizes_for(seats)[-1]
    width, height = mapgen.dimensions(size, seats)
    world = mapgen.generate(seed=seed, width=width, height=height, players=seats, human=None, layout=Layout.PLAINS)
    return world, [make_brain(p.id, Difficulty.HARD, seed) for p in world.players[:world.seats]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--repeat", type=int, default=1, help="runs; the one with the lowest mean is reported")
    parser.add_argument("--profile", action="store_true", help="print a cProfile breakdown of the last run")
    parser.add_argument("--scenario", choices=("battle", "seats"), default="battle",
                        help="the 150-unit reference battle, or a real match of --seats computer players")
    parser.add_argument("--seats", type=int, default=16, help="seats for --scenario seats")
    args = parser.parse_args()
    profiler = cProfile.Profile() if args.profile else None
    runs: list[tuple[list[float], World, list[float]]] = []
    for run in range(args.repeat):
        thinking: list[float] = []
        rng = random.Random(7)
        if args.scenario == "seats":
            world, brains = seats_world(args.seats)
        else:
            world, brains = battle_world(), []
        times: list[float] = []
        for _ in range(args.steps):
            if brains:
                started = time.perf_counter()
                for brain in brains:
                    brain.think(world, rng)
                thinking.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            if profiler is not None and run == args.repeat - 1:
                profiler.enable()
            world.step()
            if profiler is not None and run == args.repeat - 1:
                profiler.disable()
            times.append((time.perf_counter() - started) * 1000)
        runs.append((times, world, thinking))
    times, world, thinking = min(runs, key=lambda run: statistics.mean(run[0]))
    ordered = sorted(times)
    if thinking:
        think_order = sorted(thinking)
        print(f"{world.seats} seats on {world.width}x{world.height}: brains mean {statistics.mean(thinking):.2f} ms, "
              f"p95 {think_order[int(len(think_order) * 0.95)]:.2f} ms, max {think_order[-1]:.2f} ms a step")
    print(f"{args.steps} steps, {len(world.units)} units alive at the end, first step {times[0]:.1f} ms")
    print(f"per step: mean {statistics.mean(times):.2f} ms, p50 {ordered[len(ordered) // 2]:.2f} ms, "
          f"p95 {ordered[int(len(ordered) * 0.95)]:.2f} ms, max {ordered[-1]:.2f} ms; total {sum(times):.0f} ms")
    if profiler is not None:
        stats = pstats.Stats(profiler)
        stats.sort_stats("tottime").print_stats(25)
        stats.sort_stats("cumtime").print_stats(25)


if __name__ == "__main__":
    main()
