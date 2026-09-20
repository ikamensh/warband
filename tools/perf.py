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
import csv
import gc
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from saga2d.testing import FrameTimer  # noqa: E402
from warband.sim import path as pathing  # noqa: E402
from warband.art import textures  # noqa: E402
from warband.sim.rules import BuildingType, Layout  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from tools.step_bench import battle_world, standing  # noqa: E402


class PhaseTimer(FrameTimer):
    """A FrameTimer that also keeps each frame's phase times, so a slow frame can say where it went."""

    def __init__(self) -> None:
        super().__init__()
        self.phases: list[dict[str, float]] = []  # per frame: label -> ms
        self._current: dict[str, float] = {}

    def wrap(self, obj, name: str, label: str | None = None) -> None:
        fn = getattr(obj, name)
        label = label or name

        def timed(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                spent = time.perf_counter() - t0
                self.seconds[label] += spent
                self.calls[label] += 1
                self._current[label] = self._current.get(label, 0.0) + spent * 1000

        setattr(obj, name, timed)

    def frame(self, fn) -> float:
        self._current = {}
        ms = super().frame(fn)
        self.phases.append(self._current)
        return ms

    def watch_gc(self) -> None:
        """Count the garbage collector's pauses as a phase of the frame they land in, by generation."""
        started: dict[int, float] = {}

        def on_gc(phase: str, info: dict) -> None:
            generation = info["generation"]
            if phase == "start":
                started[generation] = time.perf_counter()
            elif generation in started:
                label = f"gc[gen{generation}]"
                spent = time.perf_counter() - started.pop(generation)
                self.seconds[label] += spent
                self.calls[label] += 1
                self._current[label] = self._current.get(label, 0.0) + spent * 1000

        gc.callbacks.append(on_gc)

    def slowest(self, count: int) -> str:
        """The slowest frames with their phase breakdown: what a p95 frame spends its time on."""
        order = sorted(range(len(self.frames)), key=lambda i: -self.frames[i])[:count]
        lines = [f"slowest {len(order)} frames:"]
        for i in order:
            parts = ", ".join(f"{label} {ms:.1f}" for label, ms in sorted(self.phases[i].items(), key=lambda kv: -kv[1]) if ms >= 0.05)
            lines.append(f"  frame {i:4d}: {self.frames[i]:6.1f} ms  ({parts})")
        return "\n".join(lines)

    def write_csv(self, path: Path) -> None:
        labels = sorted({label for phase in self.phases for label in phase})
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["frame", "ms", *labels])
            for i, (ms, phase) in enumerate(zip(self.frames, self.phases)):
                writer.writerow([i, f"{ms:.3f}", *(f"{phase.get(label, 0.0):.3f}" for label in labels)])


def four_player_world():
    """Four armies of seventy-five, one per player, sent at the map's centre over an 80×64 map."""
    from warband.sim import mapgen
    from warband.sim.model import tile_center
    from warband.sim.rules import UnitType
    w = mapgen.generate(seed=3, width=80, height=64, players=4)
    w.reveal_all(0)
    types = [UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT, UnitType.SCOUT, UnitType.CATAPULT, UnitType.CLERIC]
    corners = [(24, 18), (44, 18), (24, 34), (44, 34)]
    for player, (cx, cy) in enumerate(corners):
        for i in range(75):
            w.spawn_unit(player, types[(i + player) % 6], tile_center((cx + i % 15, cy + i // 15)))
    w.update_vision()
    for p in w.players:
        w.attack_move([u.id for u in w.player_units(p.id) if not u.is_worker], tile_center((40, 30)))
    return w


def crowd_world(seats: int = 16, each: int = 40):
    """*seats* armies on the biggest map that seats them, all sent at its middle.

    A sixteen-player match is not the reference battle with more units: it is sixteen fog layers,
    sixteen memories of the ground and sixteen sets of team-recoloured sprites as well.  Forty
    soldiers a seat is what a long free-for-all looks like when the middle is finally fought over.
    """
    from warband.sim import mapgen
    from warband.sim.model import tile_center
    from warband.sim.rules import UnitType
    size = mapgen.sizes_for(seats)[-1]
    width, height = mapgen.dimensions(size, seats)
    w = mapgen.generate(seed=3, width=width, height=height, players=seats, layout=Layout.PLAINS)
    w.reveal_all(0)
    types = [UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT, UnitType.SCOUT, UnitType.CATAPULT, UnitType.CLERIC]
    middle = (width / 2, height / 2)
    for player, hall in enumerate(sorted((b for b in w.buildings.values() if b.type is BuildingType.TOWN_HALL and b.player is not None),
                                         key=lambda b: b.player)):
        hx, hy = hall.pos
        for i in range(each):
            spot = (min(width - 2, hx + 4 + i % 8), min(height - 2, hy + 4 + i // 8))
            w.spawn_unit(player, types[(i + player) % 6], standing(w, spot))
    w.update_vision()
    for p in w.players:
        w.attack_move([u.id for u in w.player_units(p.id) if not u.is_worker], tile_center((int(middle[0]), int(middle[1]))))
    return w


def deaths_world():
    """Two armies spawned in each other's faces: most of them die within the first minute, and their bodies and blood stay."""
    from warband.sim.model import tile_center
    from warband.sim.rules import UnitType
    w = battle_world()
    hall = w.player_buildings(0, BuildingType.TOWN_HALL)[0]
    hx, hy = hall.pos
    for u in list(w.units.values()):
        if not u.is_worker:
            column = (u.id * 7) % 15
            u.x, u.y = tile_center((hx + 12 + column + (0 if u.player == 0 else 2), hy + 4 + (u.id * 3) % 5))
    w.update_vision()
    return w


def battle(game: Game, world=None, *, camera_on: tuple[float, float] | None = None):
    scene = GameScene(battle_world() if world is None else world, 3)
    game.push(scene)
    w = scene.world
    hall = w.player_buildings(0, BuildingType.TOWN_HALL)[0]
    hx, hy = hall.pos
    scene.camera.center_on(*(camera_on if camera_on is not None else ((hx + 20) * 32, (hy + 7) * 32)))
    scene.select([u.id for u in w.player_units(0) if not u.is_worker][:12])
    for _ in textures.warm_units(game, [p.id for p in w.players], [p.race for p in w.players]):
        pass
    return scene


def restarts(game: Game, first, args) -> None:
    """Three matches in a row: the first frames of each (setup, warm-up) apart from its steady play."""
    scene = first
    for match in range(3):
        if match:
            game.pop()
            scene = battle(game)
        timer = PhaseTimer()
        timer.watch_gc()
        opening = [timer.frame(lambda: game.tick(1 / 60)) for _ in range(30)]
        steady = [timer.frame(lambda: game.tick(1 / 60)) for _ in range(180)]
        steady_sorted = sorted(steady)
        print(f"match {match + 1}: first 30 frames max {max(opening):.0f} ms, sum {sum(opening):.0f} ms; then 180 frames p50 "
              f"{statistics.median(steady):.1f} ms, p95 {steady_sorted[int(0.95 * len(steady_sorted))]:.1f} ms, max {steady_sorted[-1]:.1f} ms; "
              f"gen2 pauses {timer.calls['gc[gen2]']} ({timer.seconds['gc[gen2]'] * 1000:.0f} ms), {len(gc.get_objects())} tracked objects")
    game._teardown()
    game.backend.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", choices=("reference", "four-player", "sixteen-player", "pan-zoom", "deaths", "restarts"), default="reference",
                        help="the 150-unit reference battle; four armies of 75; sixteen armies of 40 on the biggest map that seats them; "
                             "the reference battle under a panning, zooming camera; two armies dying in each other's faces; "
                             "or three fresh matches in a row with their first frames set apart")
    parser.add_argument("--frames", type=int, default=720)
    parser.add_argument("--profile", help="dump cProfile stats of the last 120 frames to this file")
    parser.add_argument("--csv", type=Path, help="write every frame's time and each phase's share of it to this file")
    parser.add_argument("--slowest", type=int, default=5, help="how many of the slowest frames to break down in the report")
    parser.add_argument("--gc", choices=("auto", "off", "freeze"), default="auto",
                        help="the garbage collector during the timed frames: as the game runs it, disabled, or with the loaded match frozen out of its scans")
    args = parser.parse_args()
    os.environ["SAGA2D_SILENT"] = "1"
    game = Game("Warband perf", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme())
    fonts.load(game)
    if args.scenario == "four-player":
        scene = battle(game, four_player_world(), camera_on=(40 * 32, 30 * 32))
    elif args.scenario == "sixteen-player":
        crowd = crowd_world()
        scene = battle(game, crowd, camera_on=(crowd.width * 16, crowd.height * 16))
    elif args.scenario == "deaths":
        scene = battle(game, deaths_world())
    else:
        scene = battle(game)
    if args.scenario == "restarts":
        restarts(game, scene, args)
        return
    timer = PhaseTimer()
    timer.wrap(scene.world, "step", "world.step")
    timer.wrap(scene.view, "sync", "view.sync")
    timer.wrap(scene, "draw", "scene.draw")
    timer.wrap(scene.ui, "draw", "ui.draw")
    timer.wrap(scene.effects, "update", "effects.update")
    timer.wrap(game.backend, "end_frame", "backend.end_frame")
    timer.wrap(game.backend.batch, "draw", "batch.draw")
    timer.wrap(game.backend.window, "flip", "window.flip")
    timer.wrap(pathing, "find_path_grid", "find_path_grid")
    timer.wrap(scene, "update", "scene.update")
    timer.wrap(game.backend, "poll_events", "backend.poll_events")
    timer.wrap(game, "save", "game.save")
    for brain in scene.brains:
        timer.wrap(brain, "think", f"brain.think[{brain.player}]")
    timer.wrap(scene._ui, "_update_tree", "ui.update_tree")
    timer.wrap(game._timer_manager, "update", "timers.update")
    timer.wrap(game._tween_manager, "update", "tweens.update")
    timer.wrap(scene.camera, "update", "camera.update")
    if game._audio is not None:
        timer.wrap(game._audio, "update", "audio.update")
    from saga2d.rendering import sprite as sprite_module
    timer.wrap(sprite_module.Sprite, "update_animation", "sprites.update_animation")
    timer.wrap(sprite_module.Sprite, "update_action", "sprites.update_action")
    timer.wrap(game._scene_stack, "draw", "stack.draw")
    timer.wrap(game._scene_stack, "update", "stack.update")
    timer.wrap(time, "sleep", "time.sleep")  # a cooperative sleep anywhere in a frame would hide from every other phase
    timer.wrap(game.backend, "begin_frame", "backend.begin_frame")
    timer.wrap(game.backend.window, "clear", "window.clear")
    timer.wrap(game.backend, "set_camera", "backend.set_camera")
    import inspect
    for name, _ in inspect.getmembers(type(scene.view), inspect.isfunction):
        if name.startswith(("_sync", "_register", "draw", "before_step", "_prune")) and name != "draw":
            timer.wrap(scene.view, name, f"view.{name}")
    for name in ("register_image", "update_image", "load_image", "register_static", "measure_text"):
        if hasattr(game.backend, name):
            timer.wrap(game.backend, name, f"backend.{name}")
    timer.watch_gc()
    import threading
    print("threads:", [t.name for t in threading.enumerate()])
    setup_ms = timer.frame(lambda: game.tick(1 / 60))  # the first frame builds the sprites, domains and atlas; a match never sees it in one go
    timer.frames.clear()
    timer.seconds.clear()
    timer.calls.clear()
    timer.phases.clear()
    if args.gc == "off":
        gc.disable()
    elif args.gc == "freeze":
        gc.collect()
        gc.freeze()
    from collections import Counter
    kinds_before = Counter(type(o).__name__ for o in gc.get_objects())
    objects_before = sum(kinds_before.values())
    batch_before = (f"{len(game.backend.batch.top_groups)} top groups, {len(game.backend.batch.group_map)} groups, "
                    f"{sum(len(d) for d in game.backend.batch.group_map.values())} domains, draw list {len(game.backend.batch._draw_list)}")
    profiler = cProfile.Profile() if args.profile else None
    start = scene.camera.offset
    for i in range(args.frames):
        if profiler is not None and i == args.frames - 120:
            profiler.enable()
        if args.scenario == "pan-zoom":
            # A slow pan across the fight, and a zoom in and back out every four seconds.
            phase = (i % 240) / 240
            scene.camera.zoom = 1.0 + (phase if phase < 0.5 else 1.0 - phase)
            width, height = game.resolution
            scene.camera.center_on(start[0] + width / 2 + 3 * i, start[1] + height / 2 + i)
        timer.frame(lambda: game.tick(1 / 60))
    if profiler is not None:
        profiler.disable()
        profiler.dump_stats(args.profile)
    late = sorted(timer.frames[-120:])
    p95 = late[min(len(late) - 1, int(0.95 * len(late)))]
    print(f"setup frame {setup_ms:.0f} ms; {len(scene.world.units)} units alive at the end; last {len(late)} frames: p50 {statistics.median(late):.1f} ms, p95 {p95:.1f} ms, max {late[-1]:.1f} ms")
    print(timer.report())
    print(timer.slowest(args.slowest))
    batch = game.backend.batch
    print(f"batch: {len(batch.top_groups)} top groups, {len(batch.group_map)} groups, "
          f"{sum(len(domains) for domains in batch.group_map.values())} domains, draw list {len(batch._draw_list)} "
          f"(after the timed frames; {batch_before} before)")
    kinds_after = Counter(type(o).__name__ for o in gc.get_objects())
    print(f"tracked objects: {objects_before} before the timed frames, {sum(kinds_after.values())} after "
          f"(a collector pause scans them all unless they are frozen; gen2 pauses grow with them)")
    growth = sorted(((kinds_after[k] - kinds_before.get(k, 0), k) for k in kinds_after), reverse=True)[:8]
    print("  grew most: " + ", ".join(f"{k} +{n}" for n, k in growth if n > 0))
    if args.csv is not None:
        timer.write_csv(args.csv)
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
