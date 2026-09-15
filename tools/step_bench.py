"""Model step times of a 150-unit battle, without a window: the simulation alone.

    uv run python tools/step_bench.py [--steps 300] [--profile]

Two armies of six unit types meet between twelve farms on a large map and
are ordered at each other; the world is then stepped in place.  The step
is timed with a wall clock; ``--profile`` adds a cProfile breakdown of the
same run (the profiler roughly doubles the times, so read it for shares,
not for milliseconds).  ``tools/perf.py`` times whole frames on the real
backend with this same battle.
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband import mapgen  # noqa: E402
from warband.model import World, tile_center  # noqa: E402
from warband.rules import BuildingType, UnitType  # noqa: E402


def battle_world(seed: int = 3, width: int = 64, height: int = 48) -> World:
    """Seventy-five units a side on attack-move towards the other side, twelve farms between them."""
    w = mapgen.generate(seed=seed, width=width, height=height, players=2)
    hall = w.player_buildings(0, BuildingType.TOWN_HALL)[0]
    hx, hy = hall.pos
    w.reveal_all(0)
    types = [UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT, UnitType.SCOUT, UnitType.CATAPULT, UnitType.CLERIC]
    for i in range(75):
        w.spawn_unit(0, types[i % 6], tile_center((hx + 4 + i % 15, hy + 4 + i // 15)))
        w.spawn_unit(1, types[(i + 1) % 6], tile_center((hx + 22 + i % 15, hy + 4 + i // 15)))
    for i in range(12):
        w.place_building(0 if i % 2 == 0 else 1, BuildingType.FARM, (hx + 4 + (i % 6) * 3, hy + 11 + (i // 6) * 3))
    w.update_vision()
    mine = [u.id for u in w.player_units(0) if not u.is_worker]
    theirs = [u.id for u in w.player_units(1) if not u.is_worker]
    w.attack_move(mine, tile_center((hx + 25, hy + 7)))
    w.attack_move(theirs, tile_center((hx + 8, hy + 7)))
    return w


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--profile", action="store_true", help="print a cProfile breakdown of the run")
    args = parser.parse_args()
    world = battle_world()
    profiler = cProfile.Profile() if args.profile else None
    times: list[float] = []
    for _ in range(args.steps):
        started = time.perf_counter()
        if profiler is not None:
            profiler.enable()
        world.step()
        if profiler is not None:
            profiler.disable()
        times.append((time.perf_counter() - started) * 1000)
    ordered = sorted(times)
    print(f"{args.steps} steps, {len(world.units)} units alive at the end, first step {times[0]:.1f} ms")
    print(f"per step: mean {statistics.mean(times):.2f} ms, p50 {ordered[len(ordered) // 2]:.2f} ms, "
          f"p95 {ordered[int(len(ordered) * 0.95)]:.2f} ms, max {ordered[-1]:.2f} ms; total {sum(times):.0f} ms")
    if profiler is not None:
        stats = pstats.Stats(profiler)
        stats.sort_stats("tottime").print_stats(25)
        stats.sort_stats("cumtime").print_stats(25)


if __name__ == "__main__":
    main()
