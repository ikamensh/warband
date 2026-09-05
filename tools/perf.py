"""Frame times of a 150-unit battle on the real backend, with a breakdown of where a frame goes.

    uv run python tools/perf_warband.py [--frames 720] [--profile late.prof]

Two armies of six unit types meet between twelve farms on a large map,
every unit image already rendered (as after the opening's warm-up).  Each
frame is timed with wall-clock wrappers around the world step, the view
sync, the scene and UI draws and the batch draw/flip; cProfile distorts
tight Python loops, so it is optional and only covers the last 120 frames.
The gate (docs/warband-early-access-criteria.md W10) is p95 < 16 ms.
The display must be awake.
"""

from __future__ import annotations

import argparse
import collections
import cProfile
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from warband import path as pathing  # noqa: E402
from warband import textures  # noqa: E402
from warband.model import tile_center  # noqa: E402
from warband.rules import BuildingType, UnitType  # noqa: E402
from warband.scene import new_game  # noqa: E402
from warband.style import build_theme  # noqa: E402


def battle(game: Game):
    scene = new_game(seed=3, width=64, height=48)
    game.push(scene)
    w = scene.world
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
    scene.camera.center_on((hx + 20) * 32, (hy + 7) * 32)
    mine = [u.id for u in w.player_units(0) if not u.is_worker]
    theirs = [u.id for u in w.player_units(1) if not u.is_worker]
    w.attack_move(mine, tile_center((hx + 25, hy + 7)))
    w.attack_move(theirs, tile_center((hx + 8, hy + 7)))
    scene.select(mine[:12])
    for _ in textures.warm_units(game, [p.id for p in w.players]):
        pass
    return scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=720)
    parser.add_argument("--profile", help="dump cProfile stats of the last 120 frames to this file")
    args = parser.parse_args()
    os.environ["SAGA2D_SILENT"] = "1"
    game = Game("Warband perf", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme())
    fonts.load(game)
    scene = battle(game)
    timers: dict[str, float] = collections.defaultdict(float)
    counts: collections.Counter[str] = collections.Counter()

    def wrap(obj, name: str, label: str) -> None:
        fn = getattr(obj, name)

        def timed(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                timers[label] += time.perf_counter() - t0
                counts[label] += 1

        setattr(obj, name, timed)

    wrap(scene.world, "step", "world.step")
    wrap(scene.view, "sync", "view.sync")
    wrap(scene, "draw", "scene.draw")
    wrap(scene.ui, "draw", "ui.draw")
    wrap(scene.effects, "update", "effects.update")
    wrap(game.backend, "end_frame", "backend.end_frame")
    wrap(game.backend.batch, "draw", "batch.draw")
    wrap(game.backend.window, "flip", "window.flip")
    wrap(pathing, "find_path_grid", "find_path_grid")

    t0 = time.perf_counter()
    game.tick(1 / 60)  # the first frame builds the sprites, domains and atlas; a match never sees it in one go
    setup_ms = (time.perf_counter() - t0) * 1000
    timers.clear()
    counts.clear()
    frames: list[float] = []
    profiler = cProfile.Profile() if args.profile else None
    for i in range(args.frames):
        if profiler is not None and i == args.frames - 120:
            profiler.enable()
        t0 = time.perf_counter()
        game.tick(1 / 60)
        frames.append((time.perf_counter() - t0) * 1000)
    if profiler is not None:
        profiler.disable()
        profiler.dump_stats(args.profile)
    ordered = sorted(frames)
    late = sorted(frames[-120:])
    print(f"setup frame {setup_ms:.0f} ms; {len(scene.world.units)} units alive at the end; {len(frames)} frames: p50 {statistics.median(frames):.1f} ms, "
          f"p95 {ordered[int(0.95 * len(ordered))]:.1f} ms, max {max(frames):.1f} ms; last 120 frames: "
          f"p50 {statistics.median(late):.1f} ms, p95 {late[114]:.1f} ms, max {late[-1]:.1f} ms")
    total = sum(frames) / 1000
    print(f"where {total:.2f} s of frames went:")
    for label, seconds in sorted(timers.items(), key=lambda kv: -kv[1]):
        print(f"  {label:18s} {seconds * 1000:8.0f} ms  {100 * seconds / total:5.1f}%  {counts[label]} calls, {seconds * 1000 / max(1, counts[label]):.2f} ms each")
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
