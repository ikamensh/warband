"""Durable local player storage (WB-015): a match's traces survive a new process, damage is reported and restored explicitly,
an interrupted write leaves nothing behind, and a write failure at match end is said rather than thrown."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from saga2d import Game, SaveError
from warband.profile import MatchResult, Profile, standing
from warband.profile_scene import ProfileScene
from warband.scene import DEFAULT_SETTINGS, GameOverScene, new_game
from warband.style import build_theme

ROOT = Path(__file__).resolve().parents[2]

PLAY = '''
import json, sys
from pathlib import Path
from saga2d import Game
from warband.profile import standing
from warband.scene import DEFAULT_SETTINGS, GameOverScene, new_game
from warband.style import build_theme
data = Path(sys.argv[1])
game = Game("Warband", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=data / "saves")
settings = game.settings(DEFAULT_SETTINGS)
settings["music"] = 0.25
settings.save()
scene = new_game(seed=3, settings=settings)
game.push(scene)
for _ in range(30):
    game.tick(1 / 60)
scene.save_to("quick")
scene.resign(standing(scene.world, scene.human))
for _ in range(90):
    game.tick(1 / 60)
assert isinstance(game.scene, GameOverScene), type(game.scene).__name__
print(json.dumps({"run_id": scene.run_id, "name": scene.profile.name, "results": len(scene.profile.results)}))
game._teardown()
'''

RETURN = '''
import json, sys
from pathlib import Path
from saga2d import Game
from warband.profile import Profile
from warband.replay import ReplayStore
from warband.scene import DEFAULT_SETTINGS
from warband.scores import HighScores
from warband.style import build_theme
from warband.title import TitleScene
data, run_id = Path(sys.argv[1]), sys.argv[2]
game = Game("Warband", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=data / "saves")
settings = game.settings(DEFAULT_SETTINGS)
profile = Profile.load(data)
replay = ReplayStore(data).load(run_id)
game.push(TitleScene(settings=settings))
game.tick(1 / 60)
texts = [t["text"] for t in game.backend.texts]
print(json.dumps({"music": settings["music"], "results": [r.run_id for r in profile.results], "name": profile.name,
                  "scores": len(HighScores(data).load()), "replay_orders": len(replay.orders), "ended": replay.end is not None,
                  "quick": game.save_manager.load("quick") is not None,
                  "card": any(profile.name in t for t in texts) and any("Rating" in t for t in texts)}))
game._teardown()
'''


def run(script: str, *args: str) -> dict:
    env = {**os.environ, "SAGA2D_SILENT": "1"}
    done = subprocess.run([sys.executable, "-c", script, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture
def played(tmp_path) -> tuple[Path, dict]:
    """A match resigned in its own process, in an isolated data directory."""
    data = tmp_path / "home" / ".warband"
    return data, run(PLAY, str(data))


def test_a_new_process_finds_the_result_rating_score_replay_save_and_setting(played) -> None:
    data, match = played
    assert match["results"] == 1
    back = run(RETURN, str(data), match["run_id"])
    assert back == {"music": 0.25, "results": [match["run_id"]], "name": match["name"], "scores": 1, "replay_orders": back["replay_orders"],
                    "ended": True, "quick": True, "card": True}
    assert back["replay_orders"] >= 1
    assert {p.name for p in data.iterdir()} >= {"profile", "high_scores", "replays", "saves", "settings.json"}


def test_a_leftover_staged_file_and_a_second_load_change_nothing(played) -> None:
    data, match = played
    (data / "profile" / ".save_1.json.abc123.tmp").write_text("{partial", encoding="utf-8")
    assert [r.run_id for r in Profile.load(data).results] == [match["run_id"]]
    assert [r.run_id for r in Profile.load(data).results] == [match["run_id"]], "loading again duplicates nothing"


def result(run_id: str) -> MatchResult:
    return MatchResult(run_id, "2026-09-18T10:00:00+00:00", "victory", 1.0, "", "medium", 1000, 1, "human", 48, 40, "summer", "plains", 3, 600, True)


def test_a_damaged_profile_is_reported_and_restored_from_its_backup_on_the_profile_screen(tmp_path) -> None:
    data = tmp_path / "data"
    profile = Profile.load(data)
    profile.record(result("first"))
    profile.record(result("second"))  # the file before this write is the backup
    profile.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SaveError):
        Profile.load(data)
    game = Game("Warband", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=data / "saves")
    try:
        game.push(ProfileScene())
        game.tick(1 / 60)
        texts = [t["text"] for t in game.backend.texts]
        assert any("Profile unavailable" in t for t in texts) and any("Restore backup" in t for t in texts)
        game.backend.inject_key("b")
        game.tick(1 / 60)
        texts = [t["text"] for t in game.backend.texts]
        assert any("restored from its backup" in t for t in texts) and any("~/" in t or "live in" in t for t in texts)
        restored = Profile.load(data)
        assert [r.run_id for r in restored.results] == ["first"]
        assert (data / "profile" / "save_1.damaged.json").read_text(encoding="utf-8") == "{broken"
    finally:
        game._teardown()


def test_a_write_failure_at_match_end_is_said_and_the_game_goes_on(tmp_path) -> None:
    data = tmp_path / "data"
    game = Game("Warband", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=data / "saves")
    try:
        scene = new_game(seed=3, settings=dict(DEFAULT_SETTINGS))
        game.push(scene)
        for _ in range(10):
            game.tick(1 / 60)
        assert scene.profile is not None
        (data / "profile").mkdir(parents=True)
        (data / "profile" / "save_1.json").mkdir()  # nothing can be written where the profile goes
        (data / "replays").write_text("in the way", encoding="utf-8")
        scene.resign(standing(scene.world, scene.human))
        for _ in range(90):
            game.tick(1 / 60)
        assert isinstance(game.scene, GameOverScene)
        assert scene.rating_change is None and "save_1.json" in scene.profile_error, "the failure names the file"
        assert (data / "profile" / "save_1.json").is_dir(), "nothing was replaced"
    finally:
        game._teardown()
