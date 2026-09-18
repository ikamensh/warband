"""A rated match through the scenes: recorded as it is played, rated when it ends, and what leaving costs."""

import pytest

from saga2d import Game
from warband.profile import EARLY_EXIT_WEIGHT, Profile
from warband.replay import Playback, ReplayStore
from warband.rules import BuildingType, UnitType
from warband.scene import GameOverScene, LeaveScene, PauseScene, load_game, new_game
from warband.style import build_theme
from warband.title import TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband rated", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


@pytest.fixture
def play(game):
    Profile.load(game.data_dir).rename("Tester")
    scene = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
    game.push(scene)
    game.tick(1 / 60)
    return game, scene


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def tick(game: Game, seconds: float) -> None:
    for _ in range(int(seconds * 60) + 1):
        game.tick(1 / 60)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


def test_a_victory_is_rated_and_its_replay_kept(play):
    """The results screen says what the match did to the rating; the profile and a faithful replay are on disk."""
    game, scene = play
    assert scene.player.name == "Tester"
    tick(game, 2.0)
    world = scene.world
    world.resign(1)  # the computer concedes: an order, so the replay carries it
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene) and world.winner == scene.human
    change = scene.rating_change
    assert change is not None and change.delta > 0 and change.result.outcome == "victory" and change.result.weight == 1.0
    assert any(t.startswith("Rating 1000 →") and "replay saved" in t for t in texts(game))
    profile = Profile.load(game.data_dir)
    assert profile.counts()["victories"] == 1 and profile.rating == change.after
    store = ReplayStore(game.data_dir)
    assert store.exists(scene.run_id)
    playback = Playback(store.load(scene.run_id))
    playback.run()
    assert playback.faithful and playback.world.winner == scene.human
    assert playback.world.players[scene.human].name == "Tester"


@pytest.mark.parametrize("players", [2, 3])
def test_rival_falls_notice_only_appears_while_the_match_continues(game, players):
    """FFA still announces an eliminated rival; victory must not freeze a new toast behind the result."""
    scene = new_game(seed=3, players=players, settings={"music": 0, "sfx": 0, "tutorial": False})
    game.push(scene)
    game.tick(1 / 60)
    scene.world.resign(1)
    tick(game, 0.5)
    assert ("A rival falls" in texts(game)) == (players == 3)
    assert isinstance(game.scene, GameOverScene) == (players == 2)


def test_resigning_on_even_terms_asks_first_and_counts_a_fifth_of_a_loss(play):
    """Resign from the pause menu: the confirmation names the cost, Escape keeps playing, Enter concedes."""
    game, scene = play
    press(game, "f3")
    press(game, "escape")
    press(game, "r")
    assert isinstance(game.scene, LeaveScene)
    assert any("no enemy at the gates" in t for t in texts(game))
    press(game, "escape")
    assert isinstance(game.scene, PauseScene) and scene.player.alive
    press(game, "r")
    press(game, "return")
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene) and not scene.player.alive
    change = scene.rating_change
    assert change is not None and change.result.outcome == "resigned" and change.result.weight == EARLY_EXIT_WEIGHT
    assert change.delta < 0 and "no enemy at the gates" in change.result.reason
    assert Profile.load(game.data_dir).counts() == {"victories": 0, "defeats": 0, "left": 1}


def test_resigning_under_attack_costs_a_full_loss(play):
    game, scene = play
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world.spawn_unit(1, UnitType.FOOTMAN, (hall.center[0] + 3, hall.center[1] + 3))
    press(game, "f3")
    press(game, "escape")
    press(game, "r")
    assert isinstance(game.scene, LeaveScene) and any("under attack" in t for t in texts(game))
    press(game, "return")
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene)
    assert scene.rating_change.result.weight == 1.0


def test_leaving_for_the_title_is_recorded_as_a_loss_and_the_replay_kept(play):
    """Back to title through the pause menu records the abandoned match; the title then shows the new rating."""
    game, scene = play
    press(game, "escape")
    press(game, "t")
    assert isinstance(game.scene, LeaveScene)
    press(game, "return")
    assert isinstance(game.scene, TitleScene)
    profile = Profile.load(game.data_dir)
    assert profile.counts()["left"] == 1 and profile.results[-1].outcome == "left"
    assert ReplayStore(game.data_dir).exists(scene.run_id)
    replay = ReplayStore(game.data_dir).load(scene.run_id)
    assert replay.end["outcome"] == "left"


def test_leaving_a_decided_match_costs_nothing(play):
    game, scene = play
    scene.world.winner = 1
    press(game, "escape")
    press(game, "t")
    assert isinstance(game.scene, TitleScene)
    assert Profile.load(game.data_dir).results == []


def test_a_loaded_save_goes_on_recording_and_replays_faithfully(play):
    """Save, play on, load, finish: the replay carries the reload and still ends in the recorded world."""
    game, scene = play
    tick(game, 1.0)
    press(game, "f5")
    tick(game, 1.0)
    press(game, "f9")
    tick(game, 1.0)
    scene = game.scene  # a load is a new match scene, which goes on with the recording
    world = scene.world
    world.resign(1)  # the computer concedes: an order, so the replay carries it
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene)
    replay = ReplayStore(game.data_dir).load(scene.run_id)
    assert [row[1] for row in replay.orders].count("reload") == 1
    playback = Playback(replay)
    playback.run()
    assert playback.faithful


def test_a_finished_save_reopened_does_not_rate_the_match_twice(play):
    game, scene = play
    state = scene.get_save_state()
    world = scene.world
    world.resign(1)  # the computer concedes: an order, so the replay carries it
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene)
    first = Profile.load(game.data_dir)
    game.clear_and_push(load_game(state, settings=scene.settings))
    tick(game, 0.1)
    assert not isinstance(game.scene, GameOverScene)
    game.scene.world.resign(1)
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene)
    assert game.scene.game_scene.rating_change.replaced
    again = Profile.load(game.data_dir)
    assert len(again.results) == len(first.results) == 1
