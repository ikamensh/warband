"""Symbols, ambience and bodies: the HUD reads at a glance, buildings live, and the fallen stay a while."""

import pytest

from saga2d import Game
from warband.icons import Icon
from warband.model import tile_center
from warband.rules import BuildingType, UnitType
from warband.scene import new_game
from warband.style import build_theme


@pytest.fixture
def play(tmp_path):
    game = Game("Warband presentation", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3)
    game.push(scene)
    game.tick(1 / 60)
    yield game, scene
    game._teardown()


def hover(game, scene, x, y):
    scene.mouse = (x, y)
    game.backend.inject_mouse_move(x, y)
    game.tick(1 / 60)


def test_the_hud_shows_resources_as_symbols_that_explain_themselves(play) -> None:
    game, scene = play
    icons = [c for c in scene.ui.walk() if isinstance(c, Icon)]
    assert [icon.name for icon in icons] == ["gold", "lumber", "supply"]
    texts = [t["text"] for t in game.backend.texts]
    assert str(scene.player.gold) in texts and str(scene.player.lumber) in texts and not any(t.startswith("Gold ") for t in texts)
    x, y, w, h = icons[1].bounds
    hover(game, scene, x + w / 2, y + h / 2)
    assert scene.tooltip.startswith("Lumber")
    hover(game, scene, 640, 400)
    assert scene.tooltip == ""


def test_a_selected_unit_shows_its_numbers_beside_symbols_with_hints(play) -> None:
    game, scene = play
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    archer = world.spawn_unit(scene.human, UnitType.ARCHER, tile_center((hall.x + 4, hall.y + 4)))
    before = len([p for p in game.backend.polygons if p["space"] == "screen"])
    scene.select([archer.id])
    game.tick(1 / 60)
    texts = [t["text"] for t in game.backend.texts]
    assert {"5", "0", "4", "2.4"} <= set(texts)
    assert len([p for p in game.backend.polygons if p["space"] == "screen"]) > before
    px, py, pw, ph = scene.selection_panel.bounds
    x, y = px + 16, py + 14  # the card's origin; its damage symbol sits at (x + 88, y + 45)
    hover(game, scene, x + 88 + 10, y + 52)
    assert scene.tooltip == "Damage per strike"
    hover(game, scene, x + 88 + 78 * 2 + 10, y + 52)
    assert scene.tooltip == "Attack range in tiles"


def test_a_visible_mine_glitters_and_a_forge_smokes(play) -> None:
    game, scene = play
    world = scene.world
    mine = world.mines()[0]
    scene.camera.center_on(mine.center[0] * 32, mine.center[1] * 32)
    game.tick(1 / 60)
    motes = [p for p in game.backend.polygons if p["space"] == "world" and len(p["points"]) == 4]
    assert motes, "a mine with gold left should glitter"
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world.reveal_all(scene.human)
    world.place_building(scene.human, BuildingType.BLACKSMITH, (hall.x + 4, hall.y + 4))
    scene.camera.center_on((hall.x + 5.5) * 32, (hall.y + 5.5) * 32)
    circles = len([c for c in game.backend.circles if c["space"] == "world"])
    game.tick(1 / 60)
    assert len([c for c in game.backend.circles if c["space"] == "world"]) > circles
