"""The title's player card, the profile screen and renaming, through the mock backend."""

import pytest

from saga2d import Game
from warband.ai import DIFFICULTY_ELO
from warband.profile import MatchResult, Profile
from warband.profile_scene import NameScene, ProfileScene
from warband.replay import Replay, ReplayStore
from warband.replay_scene import ReplayScene
from warband.rules import Difficulty
from warband.scene import new_game
from warband.style import build_theme
from warband.title import TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband profile", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


def result(run_id: str, outcome: str, difficulty: Difficulty, when: str) -> MatchResult:
    return MatchResult(run_id, f"{when}T12:00:00+00:00", outcome, 1.0, "", difficulty.value, DIFFICULTY_ELO[difficulty], 1, "elf", 48, 40,
                       "summer", "plains", 9, 700, False)


def test_the_title_shows_who_is_playing_and_how_they_stand(game):
    profile = Profile.load(game.data_dir)
    profile.rename("Ilya")
    game.push(TitleScene())
    game.tick(1 / 60)
    assert "Ilya" in texts(game) and "Rating 1000 ± 350 · provisional" in texts(game)
    assert any(t.startswith("No rated matches yet") for t in texts(game))
    profile.record(result("a", "victory", Difficulty.HARD, "2026-09-10"))
    profile.record(result("b", "defeat", Difficulty.MASTER, "2026-09-11"))
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    shown = texts(game)
    assert "1 victory · 1 defeat · 0 left early" in shown
    assert any("Defeat · Master · 2 players · 2026-09-11" in t for t in shown)
    assert any(t.startswith(f"Rating {round(profile.rating.value)} ±") for t in shown)


def test_the_profile_screen_lists_the_matches_and_leads_to_a_replay(game):
    profile = Profile.load(game.data_dir)
    for i in range(10):
        profile.record(result(f"m{i}", "victory" if i % 3 else "defeat", Difficulty.MEDIUM, f"2026-08-{10 + i}"))
    scene = new_game(seed=4)
    replay = Replay.begin(scene.world, seed=4, difficulty=Difficulty.MEDIUM, human=scene.human)
    scene.world.step()
    replay.finish(scene.world, "victory")
    ReplayStore(game.data_dir).save("m9", replay, {})
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "p")
    assert isinstance(game.scene, ProfileScene)
    shown = texts(game)
    assert "2026-08-19" in shown and "2026-08-12" in shown and "2026-08-11" not in shown, "eight newest rows on the first page"
    assert "Page 1 of 2" in shown and "Watch" in shown
    press(game, "pagedown")
    assert "2026-08-11" in texts(game) and "Page 2 of 2" in texts(game)
    press(game, "pageup")
    press(game, "w")
    assert isinstance(game.scene, ReplayScene)
    assert game.scene.playback.replay.seed == 4


def test_renaming_from_the_profile_screen_is_typed_and_kept(game):
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "p")
    press(game, "r")
    assert isinstance(game.scene, NameScene)
    for _ in range(20):
        press(game, "backspace")
    for key in "ilya":
        press(game, key, shift=key == "i")
    press(game, "space")
    press(game, "9")
    press(game, "return")
    assert isinstance(game.scene, ProfileScene)
    assert Profile.load(game.data_dir).name == "Ilya 9"
    assert "Ilya 9" in texts(game)
    press(game, "r")
    for _ in range(20):
        press(game, "backspace")
    press(game, "return")
    assert isinstance(game.scene, NameScene), "an empty name is refused, with the reason shown"
    assert any("at least one character" in t for t in texts(game))
    press(game, "escape")
    assert Profile.load(game.data_dir).name == "Ilya 9"


def test_a_deleted_replay_leaves_the_result_in_the_record(game):
    profile = Profile.load(game.data_dir)
    profile.record(result("m", "victory", Difficulty.EASY, "2026-09-01"))
    scene = new_game(seed=4)
    replay = Replay.begin(scene.world, seed=4, difficulty=Difficulty.EASY, human=scene.human)
    replay.finish(scene.world, "victory")
    store = ReplayStore(game.data_dir)
    store.save("m", replay, {})
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "p")
    game.scene.delete("m")
    game.tick(1 / 60)
    assert not store.exists("m") and "Watch" not in texts(game)
    assert Profile.load(game.data_dir).counts()["victories"] == 1
