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


def test_after_a_recorded_reload_the_hud_reads_the_world_the_playback_goes_on_in(game):
    """A recording that went on from a save plays on in a world restored from it, and the HUD's purse, supply and
    clock still read the world before, frozen at the moment of the save."""
    from warband.records.replay import Replay
    from warband.sim import mapgen
    from warband.sim.rules import Difficulty

    world = mapgen.generate(seed=3)
    replay = Replay.begin(world, seed=3, difficulty=Difficulty.EASY, human=0)
    for _ in range(40):
        world.step()
    replay.reloaded(world)
    for _ in range(400):
        world.step()
    replay.finish(world, "left")
    game.clear_and_push(ReplayScene(replay, settings={"music": 0, "sfx": 0}))
    scene = game.scene
    tick(game, 10.0, 0.25)
    gold = scene._resource_rows[0][0].children[1]  # the purse's label: the engine offers no lookup of a label by its role
    assert scene.world.tick > 40 and scene.player.gold != 1000 and gold.text == str(scene.player.gold)


def test_with_the_fog_back_on_a_replay_forgets_what_only_the_reveal_showed(game):
    """Watched from above, then F4, "the map as the player saw it": the rival hall the player never saw stayed on the
    map and the minimap, as if remembered, and could be clicked."""
    from warband.records.replay import Replay
    from warband.sim.rules import BuildingType, Difficulty

    source = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
    replay = Replay.begin(source.world, seed=3, difficulty=Difficulty.MEDIUM, human=source.human)
    replay.end = {"tick": 4000, "digest": "-", "outcome": "defeat"}
    game.clear_and_push(ReplayScene(replay, settings={"music": 0, "sfx": 0}))
    scene = game.scene
    tick(game, 0.1)
    rival = next(p.id for p in scene.world.players if p.id != scene.human)
    hall = scene.world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
    assert scene.reveal and scene.view.sighting(hall.id) is not None
    press(game, "f4")
    tick(game, 0.3)
    assert not scene.reveal and scene.view.sighting(hall.id) is None and scene.view.entity_at(hall.center) is None
    own = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert scene.view.sighting(own.id) is not None
