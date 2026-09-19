"""Native frames of the profile, the revamped title, the rating on the results screen, the leave confirmation and a replay.

Run: uv run python tools/verify_profile.py docs/evidence/profile
Isolated from the player's own profile, saves and replays (a temporary data directory).  Look at the PNGs.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts
from warband.records.profile import EARLY_EXIT_WEIGHT, MatchResult, Profile, standing
from warband.ui.profile_scene import NameScene, ProfileScene
from warband.records.replay import ReplayStore
from warband.ui.replay_scene import ReplayEndScene, ReplayScene
from warband.sim.rules import Difficulty
from warband.ui.scene import GameOverScene, LeaveScene, new_game
from warband.ui.style import build_theme
from warband.ui.title import TitleScene


def verify(out: Path, resolution: tuple[int, int] = (1280, 800)) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-profile-") as temp:
        game = Game("Warband", resolution=resolution, backend="pyglet", visible=False, theme=build_theme(), save_dir=Path(temp) / "saves")
        fonts.load(game)
        settings = {"music": 0, "sfx": 0, "tutorial": False}

        def frames(count: int = 3) -> None:
            for _ in range(count):
                game.tick(1 / 60)

        def shot(name: str) -> None:
            frames()
            path = out / f"{name}.png"
            game.backend.capture_frame().save(path)
            print(path, flush=True)

        try:
            profile = Profile.load(game.data_dir)
            profile.rename("Ilya")
            for i, (outcome, difficulty, weight, reason) in enumerate([
                    ("victory", "medium", 1.0, ""), ("victory", "hard", 1.0, ""), ("defeat", "master", 1.0, ""),
                    ("left", "hard", EARLY_EXIT_WEIGHT, "left with no enemy at the gates and no material disadvantage: 0.2 of a loss"),
                    ("victory", "master", 1.0, "")]):
                profile.record(MatchResult(f"match-{i}", f"2026-09-{10 + i}T18:00:00+00:00", outcome, weight, reason, difficulty,
                                           {"easy": 770, "medium": 1000, "hard": 1220, "master": 1420}[difficulty], 1 + (i % 2), "orc" if i % 2 else "human",
                                           48, 40, "summer", "plains", 100 + i, 700 + 100 * i, False))
            # A real match, won when the computer resigns: its replay is kept and it is the newest result.
            scene = new_game(7, settings=settings)
            game.push(scene)
            for _ in range(240):
                game.tick(1 / 60)
            scene.select([u.id for u in scene.world.player_units(scene.human)])
            hall = scene.world.player_buildings(scene.human)[0]
            scene.command_smart((hall.center[0] + 5, hall.center[1] + 5))
            for _ in range(120):
                game.tick(1 / 60)
            scene.world.resign(1)
            frames(10)
            assert isinstance(game.scene, GameOverScene) and scene.rating_change is not None
            shot("results-rating")
            run_id = scene.run_id
            assert ReplayStore(game.data_dir).exists(run_id)
            game.clear_and_push(TitleScene(settings=settings))
            shot("title")
            game.push(ProfileScene(settings=settings))
            shot("profile")
            game.push(NameScene(profile))
            shot("rename")
            game.pop()
            game.pop()
            # Leaving an undecided match: on even terms, and under attack.
            scene = new_game(8, settings=settings)
            game.clear_and_push(scene)
            frames(30)
            game.push(LeaveScene(scene, standing(scene.world, scene.human), "Back to title", lambda: None))
            shot("leave-even")
            game.pop()
            frames()
            from warband.sim.rules import UnitType
            scene.world.spawn_unit(1, UnitType.FOOTMAN, (hall.center[0] + 2, hall.center[1] + 2))
            game.push(LeaveScene(scene, standing(scene.world, scene.human), "Resign", lambda: None))
            shot("leave-attacked")
            # The replay of the won match, mid-way and over.
            replay = ReplayStore(game.data_dir).load(run_id)
            watching = ReplayScene(replay, settings=settings)
            game.clear_and_push(watching)
            frames(60)
            watching.faster()
            frames(30)
            shot("replay")
            watching.toggle_reveal()
            frames(10)
            shot("replay-fog")
            watching.skip_to_end()
            for _ in range(200):
                game.tick(1 / 60)
                if isinstance(game.scene, ReplayEndScene):
                    break
            assert isinstance(game.scene, ReplayEndScene), "the replay reaches its end"
            assert watching.playback.faithful, "playback matches the recording"
            shot("replay-over")
            print("PASS: results rating, title card, profile, rename, leave (even and attacked), replay (whole map, fog, over)", flush=True)
        finally:
            game._teardown()
            game.backend.quit()


if __name__ == "__main__":
    verify(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/evidence/profile"))
