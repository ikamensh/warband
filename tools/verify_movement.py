"""Capture actual scene motion and its model/sprite trace on a repeatable field.

    uv run python tools/verify_movement.py docs/evidence/movement/before
    WARBAND_ART=procedural uv run python tools/verify_movement.py docs/evidence/movement/procedural

The native capture needs an awake display and ffmpeg. --backend mock keeps the
same model/scene journey for a quick trace without video. No real player data is
read or written. Frame cost excludes capture/encoding and cooperative pacing.
"""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
import random
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
from saga2d import Game, MatchClient, MatchHost, fonts  # noqa: E402
from saga2d.testing.cpu_budget import CpuBudget  # noqa: E402
from warband import textures  # noqa: E402
from warband.authority import WarbandMatch  # noqa: E402
from warband.model import World  # noqa: E402
from warband.multiplayer import NetworkGameScene  # noqa: E402
from warband.rules import BuildingType, Terrain, UnitType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402


def field(scenario):
    terrain = [[Terrain.GRASS] * 40 for _ in range(30)]
    if scenario == "obstruction":
        for y in range(5, 24):
            if y not in (13, 14):
                terrain[y][17] = Terrain.ROCK
    world = World(40, 30, terrain, 2)
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    owner = 1 if scenario == "online" else 0
    kinds = (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT)
    spacing = 1.5 if scenario == "turns" else 3
    units = [world.spawn_unit(owner, kind, (10.5, 10.5 + row * spacing))
             for row, kind in enumerate(kinds)]
    if scenario == "crowd":
        units = [*units, *(world.spawn_unit(owner, kinds[row % 3], (11.5 + col * 0.9, 10.5 + row * 0.9))
                           for row in range(5) for col in range(3))]
    for unit in units:
        unit.facing = 0.0
    return world, units


def direct(world, units, scenario, frame, fps):
    """Actual player orders, scheduled by display frame for reproducible comparisons."""
    if frame == 0:
        if scenario == "crowd":
            world.move([unit.id for unit in units], (21.5, 13.5))
        else:
            for unit in units:
                world.move([unit.id], (23.5 if scenario == "obstruction" else 30.5, unit.y))
        return "move east"
    if scenario != "turns":
        return None
    if frame in (round(4 * fps), round(6.5 * fps)):
        world.stop([unit.id for unit in units])
        return "stop"
    directions = {round(fps): (4, -3), round(2.5 * fps): (-4, 3), round(5 * fps): (4, -3)}
    if frame in directions:
        dx, dy = directions[frame]
        for unit in units:
            world.move([unit.id], (unit.x + dx, unit.y + dy))
        return f"turn {dx},{dy}"
    return None


def converge(host, client, until):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        host.poll()
        client.poll()
        if until():
            return
        time.sleep(0.001)
    raise RuntimeError("Movement capture socket did not converge")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("pyglet", "mock"), default="pyglet")
    parser.add_argument("--scenario", choices=("straight", "turns", "crowd", "obstruction", "online"), default="straight")
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--cpu-percent", type=float, default=25)
    parser.add_argument("--jitter", type=int, metavar="SEED",
                        help="online: publish at seeded uneven gaps of 4 to 8 frames at 60 FPS instead of every other tick")
    args = parser.parse_args()
    if args.seconds < 2 or args.fps < 20 or (args.scenario == "online" and args.fps % 20):
        parser.error("Use at least two seconds and 20 FPS; online FPS must be divisible by 20")
    args.output.mkdir(parents=True, exist_ok=True)
    budget = CpuBudget(args.cpu_percent)
    world, units = field(args.scenario)
    trace, captures = [], []
    native = args.backend == "pyglet"
    encoder = None
    host = client = None
    actions = []
    arrivals = None
    if args.jitter is not None:  # a network that delivers a hundred milliseconds apart, give or take a third
        rng, arrivals, at = random.Random(args.jitter), set(), 0
        while at < args.seconds * args.fps:
            arrivals.add(at)
            at += rng.randint(4 * args.fps // 60, 8 * args.fps // 60)
    with tempfile.TemporaryDirectory(prefix="warband-motion-") as temporary:
        game = Game("Warband movement", resolution=(1280, 800), backend=args.backend,
                    visible=False, theme=build_theme(), save_dir=Path(temporary) / "saves")
        try:
            fonts.load(game)
            settings = {"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False}
            if args.scenario == "online":
                match = WarbandMatch(seed=0)
                match.world = world
                host = MatchHost('warband-v2', match.apply, match.snapshot, address=('127.0.0.1', 0), token='capture')
                client = MatchClient('warband-v2', host.address, token='capture')
                converge(host, client, lambda: client.ready)
                scene = NetworkGameScene(client, settings=settings)
            else:
                scene = GameScene(world, 0, ranked=False, settings=settings)
            game.push(scene)
            scene._warm = None
            for unit in units[:3]:  # Exclude asset generation from steady motion timing.
                facings = (0,) if args.scenario in ("straight", "online") else range(8)
                for facing in facings:
                    for pose in ("stand", *textures.WALK_FRAMES):
                        textures.unit_image(game, unit.type, unit.player, facing, pose, race=unit.race)
                        budget.checkpoint()
            scene.view.set_reveal(True)
            scene.camera.zoom = args.zoom
            center = (15, 10.5) if args.scenario == "turns" else (17, 13.5)
            scene.camera.center_on(*(coordinate * textures.TILE for coordinate in center))
            scene.select([unit.id for unit in units])
            scene.paused = True
            for _ in range(8):  # Retire the intro banner without advancing the field.
                game.tick(1.0)
                budget.checkpoint()
            scene.paused = False
            if native:
                encoder = subprocess.Popen([
                    "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
                    "-video_size", "1280x800", "-framerate", str(args.fps), "-i", "pipe:0",
                    "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(args.output / "motion.mp4")], stdin=subprocess.PIPE)
            for frame in range(round(args.seconds * args.fps)):
                action = direct(world, units, args.scenario, frame, args.fps)
                if action:
                    actions.append({"frame": frame, "action": action})
                if client is not None and frame % (args.fps // 20) == 0:
                    match.step()
                regular = frame % (args.fps // 20) == 0 and world.tick % 2 == 0  # every other tick, as the room does
                if client is not None and (frame in arrivals if arrivals is not None else regular):
                    host.publish()
                    converge(host, client, lambda: client.state['world']['tick'] == world.tick)
                started = time.perf_counter()
                game.tick(1 / args.fps)
                cost = (time.perf_counter() - started) * 1000
                for unit in units:
                    unit = scene.world.units[unit.id]
                    sprite = scene.view.unit_sprite(unit.id)
                    trace.append({"frame": frame, "tick": scene.world.tick, "host_tick": world.tick, "time": scene.world.time,
                                  "unit_id": unit.id, "kind": unit.type.value, "model": unit.pos, "facing": unit.facing,
                                  "state": unit.state, "sprite": sprite.position, "sprite_size": sprite.size,
                                  "screen": scene.camera.world_to_screen(*sprite.position), "image": sprite.image,
                                  "travel": scene.view._travel.get(unit.id, 0.0), "frame_ms": cost})
                if native:
                    capture = game.backend.capture_frame().convert("RGB").resize(game.resolution)
                    encoder.stdin.write(capture.tobytes())
                    if frame == args.fps:
                        capture.save(args.output / "gameplay.png")
                    if frame % args.fps == 0:
                        capture.save(args.output / f"second-{frame // args.fps:02d}.png")
                    if args.fps <= frame < args.fps + 8:
                        sprite = scene.view.unit_sprite(units[-1].id)
                        sx, sy = scene.camera.world_to_screen(*sprite.position)
                        if not captures:
                            width, height = (math.ceil(size * args.zoom) for size in sprite.size)
                            crop = (round(sx - width / 2) - 12, round(sy) - height - 12,
                                    round(sx + width / 2) + 40, round(sy) + 12)
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
            if client is not None:
                client.close()
                host.close()
    (args.output / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    report = {}
    for unit in units:
        rows = [r for r in trace if r["unit_id"] == unit.id][args.fps:]
        distances = [math.dist(a["sprite"], b["sprite"]) for a, b in zip(rows, rows[1:])]
        report[f"{unit.type.value}.{unit.id}"] = {"stationary_frames": sum(d < 1e-8 for d in distances),
                                   "frame_intervals": len(distances), "max_step_pixels": max(distances),
                                   "median_frame_ms": statistics.median(r["frame_ms"] for r in rows)}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    metadata = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "dirty": bool(subprocess.check_output(["git", "diff", "--name-only"], text=True)),
                "engine": version("saga2d"), "art": os.environ.get("WARBAND_ART", "painted"),
                "scenario": args.scenario, "backend": args.backend, "zoom": args.zoom,
                "fps": args.fps, "seconds": args.seconds, "actions": actions}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    if captures:
        strip = Image.new("RGB", (captures[0].width * len(captures), captures[0].height))
        for index, capture in enumerate(captures):
            strip.paste(capture, (index * capture.width, 0))
        strip.save(args.output / "eight-frames.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
