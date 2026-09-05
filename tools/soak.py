"""Soak Warband on the real backend: whole matches rendered frame by frame, with frame-time and memory reports.

    uv run python tools/soak_warband.py --minutes 30 [--seed 1] [--out DIR]

An AI brain plays the human side too, so the match runs itself through the
real GameScene (HUD, effects, fog, minimap, sounds through the silent
driver) in a hidden window at simulation speed; a new match starts when
one ends.  Every frame is timed; the report gives p50/p95/max per match,
Python heap growth and a frame saved at the end of each match to look at.
The display must be awake.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from warband import sound  # noqa: E402
from warband.ai import Brain  # noqa: E402
from warband.rules import Difficulty  # noqa: E402
from warband.scene import DEFAULT_SETTINGS, GameOverScene, GameScene, new_game  # noqa: E402
from warband.style import build_theme  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default="/tmp/warband_soak")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import os

    os.environ["SAGA2D_SILENT"] = "1"
    save_dir = Path(tempfile.mkdtemp()) / "saves"
    game = Game("Warband soak", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme(), save_dir=save_dir)
    fonts.load(game)
    sound.install(game)
    settings = dict(DEFAULT_SETTINGS)
    settings["tutorial"] = False
    tracemalloc.start()
    started = time.time()
    seed = args.seed
    matches = 0
    worst = 0.0
    baseline = None
    while time.time() - started < args.minutes * 60:
        scene = new_game(seed, players=2 + seed % 2, difficulty=list(Difficulty)[seed % 3], settings=settings)
        game.clear_and_push(scene)
        scene.brains.append(Brain(scene.human, Difficulty.NORMAL))  # the human side plays itself
        scene.speed = 1.0
        frames: list[float] = []
        while not isinstance(game.scene, GameOverScene) and time.time() - started < args.minutes * 60:
            t0 = time.perf_counter()
            game.tick(1 / 60)
            frames.append((time.perf_counter() - t0) * 1000)
            if len(frames) % 600 == 0:
                # Something a player might do: pan, zoom, select, pause the odd time.
                scene.camera.center_on(*[c + 40 for c in scene.camera.center])
                units = [u.id for u in scene.world.player_units(scene.human)][:8]
                if units:
                    scene.select(units)
        if frames:
            frames.sort()
            p50, p95, mx = statistics.median(frames), frames[int(0.95 * len(frames))], frames[-1]
            worst = max(worst, p95)
            heap = tracemalloc.get_traced_memory()[0] / 1e6
            if baseline is None:
                baseline = heap
            game.backend.capture_frame().save(out / f"match_{matches:02d}_seed{seed}.png")
            print(f"match {matches} seed {seed}: {len(frames)} frames, {scene.world.time / 60:.1f} sim min, winner {scene.world.winner}, "
                  f"p50 {p50:.1f} ms, p95 {p95:.1f} ms, max {mx:.1f} ms, heap {heap:.1f} MB (+{heap - baseline:.1f})", flush=True)
        matches += 1
        seed += 1
    print(f"soak: {matches} matches in {(time.time() - started) / 60:.1f} min, worst p95 {worst:.1f} ms, heap growth {tracemalloc.get_traced_memory()[0] / 1e6 - (baseline or 0):.1f} MB")
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
