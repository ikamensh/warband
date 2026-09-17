"""Capture actual scene motion and its model/sprite trace on a repeatable field.

    uv run python tools/verify_movement.py docs/evidence/movement/before
    WARBAND_ART=procedural uv run python tools/verify_movement.py docs/evidence/movement/procedural

The native capture needs an awake display and ffmpeg. --backend mock keeps the
same model/scene journey for a quick trace without video. No real player data is
read or written. Frame cost excludes capture/encoding and cooperative pacing.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SAGA2D_SILENT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from saga2d.testing.cpu_budget import CpuBudget  # noqa: E402
from warband import textures  # noqa: E402
from warband.model import World  # noqa: E402
from warband.rules import BuildingType, Terrain, UnitType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402


def field():
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    world.players[1].human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    units = [world.spawn_unit(0, kind, (10.5, 10.5 + row * 3))
             for row, kind in enumerate((UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT))]
    for unit in units:
        unit.facing = 0.0
    return world, units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("pyglet", "mock"), default="pyglet")
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--cpu-percent", type=float, default=25)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    budget = CpuBudget(args.cpu_percent)
    world, units = field()
    trace, captures = [], []
    native = args.backend == "pyglet"
    encoder = None
    with tempfile.TemporaryDirectory(prefix="warband-motion-") as temporary:
        game = Game("Warband movement", resolution=(1280, 800), backend=args.backend,
                    visible=False, theme=build_theme(), save_dir=Path(temporary) / "saves")
        try:
            fonts.load(game)
            scene = GameScene(world, 0, ranked=False,
                              settings={"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False})
            game.push(scene)
            scene._warm = None  # Warm only the three subjects under test before timing.
            for unit in units:
                for pose in ("stand", *textures.WALK_FRAMES):
                    textures.unit_image(game, unit.type, unit.player, textures.facing_index(unit.facing), pose, race=unit.race)
                    budget.checkpoint()
            scene.view.set_reveal(True)
            scene.camera.zoom = args.zoom
            scene.camera.center_on(17 * textures.TILE, 13.5 * textures.TILE)
            scene.paused = True
            for _ in range(8):  # Retire the intro banner without advancing the field.
                game.tick(1.0)
                budget.checkpoint()
            scene.paused = False
            for unit in units:
                world.move([unit.id], (30.5, unit.y))
            if native:
                encoder = subprocess.Popen([
                    "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
                    "-video_size", "1280x800", "-framerate", str(args.fps), "-i", "pipe:0",
                    "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(args.output / "motion.mp4")], stdin=subprocess.PIPE)
            for frame in range(round(args.seconds * args.fps)):
                started = time.perf_counter()
                game.tick(1 / args.fps)
                cost = (time.perf_counter() - started) * 1000
                for unit in units:
                    sprite = scene.view.unit_sprite(unit.id)
                    trace.append({"frame": frame, "tick": world.tick, "time": world.time,
                                  "kind": unit.type.value, "model": unit.pos, "facing": unit.facing,
                                  "state": unit.state, "sprite": sprite.position, "image": sprite.image,
                                  "travel": scene.view._travel.get(unit.id, 0.0), "frame_ms": cost})
                if native:
                    capture = game.backend.capture_frame().convert("RGB").resize(game.resolution)
                    encoder.stdin.write(capture.tobytes())
                    if frame == args.fps:
                        capture.save(args.output / "gameplay.png")
                    if args.fps <= frame < args.fps + 8:
                        sprite = scene.view.unit_sprite(units[-1].id)
                        sx, sy = scene.camera.world_to_screen(*sprite.position)
                        if not captures:
                            crop = (round(sx) - 70, round(sy) - 100, round(sx) + 110, round(sy) + 25)
                        captures.append(capture.crop(crop))
                budget.checkpoint()
                if native:
                    time.sleep(max(0.0, 1 / 30 - (time.perf_counter() - started)))
        finally:
            if encoder is not None:
                encoder.stdin.close()
                if encoder.wait() != 0:
                    raise RuntimeError("Movement video encoding failed")
            game._teardown()
            game.backend.quit()
    (args.output / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    report = {}
    for unit in units:
        rows = [r for r in trace if r["kind"] == unit.type.value][args.fps:]
        distances = [math.dist(a["sprite"], b["sprite"]) for a, b in zip(rows, rows[1:])]
        report[unit.type.value] = {"stationary_frames": sum(d < 1e-8 for d in distances),
                                   "frame_intervals": len(distances), "max_step_pixels": max(distances),
                                   "median_frame_ms": statistics.median(r["frame_ms"] for r in rows)}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    if captures:
        strip = Image.new("RGB", (captures[0].width * len(captures), captures[0].height))
        for index, capture in enumerate(captures):
            strip.paste(capture, (index * capture.width, 0))
        strip.save(args.output / "eight-frames.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
