"""Watching a replay: it plays the recorded match back, at the viewer's pace, and says whether it got there faithfully."""

import pytest

from saga2d import Game
from warband.records.profile import Profile
from warband.records.replay import ReplayStore
from warband.ui.replay_scene import ReplayEndScene, ReplayMenuScene, ReplayScene
from warband.sim.rules import SIM_DT
from warband.ui.scene import GameOverScene, new_game
from warband.ui.style import build_theme
from warband.ui.title import TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband replay", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def tick(game: Game, seconds: float, dt: float = 1 / 60) -> None:
    for _ in range(int(seconds / dt) + 1):
        game.tick(dt)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


@pytest.fixture
def recorded(game):
    """A short rated match, played through the scene and won when the computer resigns; its replay is on disk."""
    Profile.load(game.data_dir).rename("Watcher")
    scene = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
    game.push(scene)
    tick(game, 3.0, 0.1)  # in tenths: the world steps as often, the scene draws a sixth as many frames
    scene.select([u.id for u in scene.world.player_units(scene.human)])  # send the peasants somewhere: an order of the player's own, in the log
    hall = scene.world.player_buildings(scene.human)[0]
    scene.command_smart((hall.center[0] + 6, hall.center[1] + 6))
    tick(game, 2.0, 0.1)
    scene.world.resign(1)
    tick(game, 0.5, 0.1)
    assert isinstance(game.scene, GameOverScene)
    replay = ReplayStore(game.data_dir).load(scene.run_id)
    assert any(row[1] == "smart" for row in replay.orders)
    return replay


def test_a_replay_plays_the_match_back_to_its_recorded_end(game, recorded):
    game.clear_and_push(ReplayScene(recorded, settings={"music": 0, "sfx": 0}))
    scene = game.scene
    tick(game, 0.1)
    assert scene.player.name == "Watcher" and scene.reveal and not scene.brains
    assert any(t.startswith("REPLAY") for t in texts(game))
    press(game, "pageup")
    press(game, "pageup")
    assert scene.speed_factor == 4
    press(game, "pagedown")
    assert scene.speed_factor == 2
    press(game, "f4")
    assert not scene.reveal and not scene.view.reveal
    press(game, "f4")
    assert scene.reveal
    before = scene.world.tick
    tick(game, 1.0)
    assert scene.world.tick > before, "the recording advances"
    assert not scene.attempt("move", [1], (3.0, 3.0)) and "replay" in scene.status, "the viewer gives no orders, and is told so"
    press(game, "end")
    tick(game, 3.0)
    assert isinstance(game.scene, ReplayEndScene)
    assert scene.playback.done and scene.playback.faithful
    assert scene.world.winner == scene.human
    assert any("won" in t for t in texts(game)) and any("matched the recording" in t for t in texts(game))
    press(game, "t")
    assert isinstance(game.scene, TitleScene)


def test_pausing_holds_the_recording_and_the_menu_leads_out(game, recorded):
    game.clear_and_push(ReplayScene(recorded, settings={"music": 0, "sfx": 0}))
    scene = game.scene
    tick(game, 0.5)
    press(game, "f3")
    held = scene.world.tick
    tick(game, 0.5)
    assert scene.world.tick == held
    press(game, "f10")
    assert isinstance(game.scene, ReplayMenuScene)
    press(game, "escape")
    assert game.scene is scene
    press(game, "f3")
    tick(game, 0.5)
    assert scene.world.tick > held


def test_the_end_of_a_left_match_is_shown_as_such(game, recorded):
    """A recording that stops short of a decision ends the replay where the player left."""
    recorded.end = {**recorded.end, "outcome": "left", "tick": recorded.end["tick"] - 20}
    recorded.orders = [row for row in recorded.orders if row[0] < recorded.end["tick"]]
    game.clear_and_push(ReplayScene(recorded, settings={"music": 0, "sfx": 0}))
    scene = game.scene
    press(game, "end")
    tick(game, 3.0)
    assert isinstance(game.scene, ReplayEndScene) and scene.world.tick == recorded.end["tick"]
    assert any("left the match" in t for t in texts(game))
    assert scene.length == pytest.approx(recorded.end["tick"] * SIM_DT)
