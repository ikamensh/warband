"""Settings that persist, saves that are browsed, checked and automatic, and the tutorial strip."""

import json

import pytest

from saga2d import Game, SaveError
from saga2d.settings import Settings
from warband.model import tile_center
from warband.rules import BuildingType, UnitType
from warband.scene import AUTOSAVE_EVERY, DEFAULT_SETTINGS, SAVE_VERSION, GameScene, SaveBrowserScene, SettingsScene, check_save, new_game
from warband.style import build_theme
from warband.title import TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Progress", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g._teardown()


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def tick(game: Game, seconds: float) -> None:
    for _ in range(int(seconds * 60) + 1):
        game.tick(1 / 60)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


# -- Settings ---------------------------------------------------------------------------


def test_settings_screen_changes_persist_to_the_file_and_reach_the_camera(game, tmp_path) -> None:
    settings = game.settings(DEFAULT_SETTINGS)
    scene = new_game(seed=3, settings=settings)
    game.push(scene)
    game.tick(1 / 60)
    assert scene.camera._edge_speed > 0
    press(game, "escape")
    press(game, "s")
    assert isinstance(game.scene, SettingsScene)
    press(game, "down")
    press(game, "down")
    press(game, "right")  # edge scrolling off
    press(game, "down")
    press(game, "right")  # scroll speed ×1.25
    press(game, "down")
    press(game, "right")  # fullscreen on
    assert settings["edge_scroll"] is False and settings["scroll_speed"] == 1.25 and settings["fullscreen"] is True
    press(game, "escape")
    assert scene.camera._edge_speed == 0 and game.backend.fullscreen is True
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["edge_scroll"] is False and saved["scroll_speed"] == 1.25
    again = Settings(tmp_path / "settings.json", DEFAULT_SETTINGS)
    assert again["fullscreen"] is True


# -- Saves ------------------------------------------------------------------------------------


def test_save_browser_writes_slots_with_summaries_and_loads_them(game) -> None:
    scene = new_game(seed=3, players=3)
    game.push(scene)
    game.tick(1 / 60)
    press(game, "escape")
    press(game, "f5")
    assert isinstance(game.scene, SaveBrowserScene) and game.scene.mode == "save"
    assert "empty" in texts(game)
    press(game, "2")
    assert game.scene is scene and any("Saved to slot 2" in t for t in texts(game))
    entry = game.save_manager.list_slots(3)[1]
    assert entry["summary"]["players"] == 3 and entry["summary"]["map"].startswith("Medium") and entry["summary"]["player"] == "Azure (Humans)"
    scene.player.gold = 77
    press(game, "escape")
    press(game, "f9")
    assert isinstance(game.scene, SaveBrowserScene) and game.scene.mode == "load"
    assert any("3 players" in t for t in texts(game))
    press(game, "2")
    assert game.scene is scene and scene.player.gold == 1000


def test_quicksave_and_autosave_slots(game) -> None:
    scene = new_game(seed=3)
    game.push(scene)
    game.tick(1 / 60)
    press(game, "f9")
    assert any("No quicksave yet" in t for t in texts(game))
    press(game, "f5")
    assert game.save_manager.load("quick") is not None
    assert game.save_manager.load("autosave") is None
    scene.world.time = AUTOSAVE_EVERY - 0.1
    tick(game, 0.5)
    assert game.save_manager.load("autosave") is not None and any("Autosaved" in t for t in texts(game))
    assert scene._autosave_at == pytest.approx(2 * AUTOSAVE_EVERY)


def test_damaged_and_foreign_saves_are_refused_with_a_message(game, tmp_path) -> None:
    scene = new_game(seed=3)
    game.push(scene)
    game.tick(1 / 60)
    press(game, "f5")
    path = tmp_path / "saves" / "save_quick.json"
    data = json.loads(path.read_text())
    data["state"]["version"] = SAVE_VERSION + 1
    path.write_text(json.dumps(data))
    with pytest.raises(SaveError, match="another version"):
        check_save(data["state"])
    press(game, "f9")
    assert game.scene is scene and any("Could not load" in t for t in texts(game))
    data["state"]["version"] = SAVE_VERSION
    del data["state"]["world"]["units"]
    with pytest.raises(SaveError, match="damaged"):
        check_save(data["state"])
    path.write_text("{not json")
    press(game, "f9")
    assert game.scene is scene and any("Could not load" in t for t in texts(game))
    gold = scene.player.gold
    tick(game, 0.2)
    assert scene.player.gold == gold  # the match went on untouched


def test_title_continue_takes_the_newest_save_and_the_browser_lists_them(game) -> None:
    first = new_game(seed=5, width=40, height=32)
    game.push(first)
    game.tick(1 / 60)
    first.save_to(1)
    second = new_game(seed=6, width=40, height=32)
    game.clear_and_push(second)
    game.tick(1 / 60)
    second.world.time = 30.0
    second.save_to("quick")
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    assert any("Continue resumes the quick" in t for t in texts(game))
    press(game, "l")
    assert isinstance(game.scene, SaveBrowserScene)
    press(game, "1")
    assert isinstance(game.scene, GameScene) and game.scene.seed == 5
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    press(game, "c")
    assert isinstance(game.scene, GameScene) and game.scene.seed == 6


# -- Tutorial ------------------------------------------------------------------------------------


def test_the_tutorial_ticks_its_objectives_off_from_what_the_player_does(game) -> None:
    settings = game.settings(DEFAULT_SETTINGS)
    scene = new_game(seed=3, settings=settings)
    game.push(scene)
    game.tick(1 / 60)
    assert scene.tutorial is not None and scene.objectives.visible and any(t.startswith("1. Select a peasant") for t in texts(game))
    world = scene.world
    ps = [u for u in world.player_units(scene.human) if u.is_worker]
    scene.select([ps[0].id])
    game.tick(1 / 60)
    assert scene.tutorial.step == 1
    world.harvest([ps[0].id, ps[1].id], world.mines()[0].id)
    world.harvest([ps[2].id], world.nearest_tree(hall_center := world.player_buildings(scene.human)[0].center, 12))
    game.tick(1 / 60)
    assert scene.tutorial.step == 3
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world.place_building(scene.human, BuildingType.FARM, (hall.x + 5, hall.y + 4))
    world.place_building(scene.human, BuildingType.BARRACKS, (hall.x + 5, hall.y))
    world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall.x + 4, hall.y + 7)))
    game.tick(1 / 60)
    assert scene.tutorial.step == 6
    press(game, "a", ctrl=True)
    press(game, "a")
    x, y = scene.camera.world_to_screen((hall.x + 10) * 32, (hall.y + 7) * 32)
    game.backend.inject_click(int(x), int(y))
    game.backend.inject_release(int(x), int(y))
    game.tick(1 / 60)
    assert scene.tutorial.step == 7 and scene.tutorial.finished and settings["tutorial"] is False
    press(game, "f4")
    assert scene.tutorial is None and not scene.objectives.visible
    later = new_game(seed=4, settings=settings)
    game.clear_and_push(later)
    game.tick(1 / 60)
    assert later.tutorial is None
    assert hall_center
