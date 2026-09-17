"""Frame times of a 150-unit battle on the real backend, with a breakdown of where a frame goes.

    uv run python tools/perf.py [--frames 720] [--profile late.prof]

Two armies of six unit types meet between twelve farms on a large map
(``tools/step_bench.py`` times the same battle without a window), every
unit image already rendered (as after the opening's warm-up).  Each
frame is timed with wall-clock wrappers around the world step, the view
sync, the scene and UI draws and the batch draw/flip; cProfile distorts
tight Python loops, so it is optional and only covers the last 120 frames.
The gate (docs/warband-early-access-criteria.md W10) is p95 < 16 ms.
The display must be awake.
"""

from __future__ import annotations

import argparse
import cProfile
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from saga2d.testing import FrameTimer  # noqa: E402
from warband import path as pathing  # noqa: E402
from warband import textures  # noqa: E402
from warband.rules import BuildingType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402
from tools.step_bench import battle_world  # noqa: E402


def battle(game: Game):
    scene = GameScene(battle_world(), 3)
    game.push(scene)
    w = scene.world
    hall = w.player_buildings(0, BuildingType.TOWN_HALL)[0]
    hx, hy = hall.pos
    scene.camera.center_on((hx + 20) * 32, (hy + 7) * 32)
    scene.select([u.id for u in w.player_units(0) if not u.is_worker][:12])
    for _ in textures.warm_units(game, [p.id for p in w.players], [p.race for p in w.players]):
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
    timer = FrameTimer()
    timer.wrap(scene.world, "step", "world.step")
    timer.wrap(scene.view, "sync", "view.sync")
    timer.wrap(scene, "draw", "scene.draw")
    timer.wrap(scene.ui, "draw", "ui.draw")
    timer.wrap(scene.effects, "update", "effects.update")
    timer.wrap(game.backend, "end_frame", "backend.end_frame")
    timer.wrap(game.backend.batch, "draw", "batch.draw")
    timer.wrap(game.backend.window, "flip", "window.flip")
    timer.wrap(pathing, "find_path_grid", "find_path_grid")
    setup_ms = timer.frame(lambda: game.tick(1 / 60))  # the first frame builds the sprites, domains and atlas; a match never sees it in one go
    timer.frames.clear()
    timer.seconds.clear()
    timer.calls.clear()
    profiler = cProfile.Profile() if args.profile else None
    for i in range(args.frames):
        if profiler is not None and i == args.frames - 120:
            profiler.enable()
        timer.frame(lambda: game.tick(1 / 60))
    if profiler is not None:
        profiler.disable()
        profiler.dump_stats(args.profile)
    late = sorted(timer.frames[-120:])
    p95 = late[min(len(late) - 1, int(0.95 * len(late)))]
    print(f"setup frame {setup_ms:.0f} ms; {len(scene.world.units)} units alive at the end; last {len(late)} frames: p50 {statistics.median(late):.1f} ms, p95 {p95:.1f} ms, max {late[-1]:.1f} ms")
    print(timer.report())
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
