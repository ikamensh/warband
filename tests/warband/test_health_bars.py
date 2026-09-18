"""Health bars and progress bars (WB-008): who gets one, how it is drawn, and what tells work from wounds."""

import pytest

from saga2d import Game
from warband.rules import BuildingType, UnitType, Upgrade
from warband.scene import GameScene
from warband.style import build_theme
from warband.textures import TILE

from tests.warband.battlefield import SETTINGS, field

HEALTH = {(110, 230, 110, 255), (240, 200, 80, 255), (240, 90, 70, 255)}
GOLD = (255, 214, 110, 255)


@pytest.fixture
def play(tmp_path):
    game = Game("Warband bars", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    scene.view.set_reveal(True)
    scene.camera.center_on(16 * TILE, 12 * TILE)
    game.tick(1 / 60)
    yield game, scene
    game._teardown()


def frame(game: Game) -> None:
    for _ in range(2):
        game.tick(1 / 60)


def health_bars(game: Game, *, units_only: bool = True) -> list[dict]:
    """The coloured fills of health bars this frame (a unit's is 25.6 px wide, a building's follows its footprint)."""
    return [r for r in game.backend.rects if r["space"] == "world" and tuple(r["color"]) in HEALTH and (r["width"] <= TILE or not units_only)]


def progress_bars(game: Game) -> list[dict]:
    zoom = game.scene.camera.zoom
    return [r for r in game.backend.rects if r["space"] == "world" and tuple(r["color"]) == GOLD and r["height"] == pytest.approx(5 / zoom)]


def work_marks(game: Game) -> list[dict]:
    return [c for c in game.backend.circles if c["space"] == "world" and tuple(c["color"][:3]) == GOLD[:3]]


def test_wounded_units_show_a_bar_and_healthy_ones_do_not(play) -> None:
    game, scene = play
    world = scene.world
    sound = world.spawn_unit(0, UnitType.FOOTMAN, (14.5, 12.5))
    hurt = world.spawn_unit(0, UnitType.FOOTMAN, (16.5, 12.5))
    hurt.hp = hurt.max_hp // 3
    frame(game)
    bars = health_bars(game)
    assert len(bars) == 1 and tuple(bars[0]["color"]) == (240, 200, 80, 255)
    hurt.hp = hurt.max_hp // 5
    frame(game)
    assert [tuple(b["color"]) for b in health_bars(game)] == [(240, 90, 70, 255)]
    hurt.hp = hurt.max_hp
    frame(game)
    assert health_bars(game) == [] and sound.hp == sound.max_hp


def test_selection_hover_and_alt_show_bars_at_full_health(play) -> None:
    game, scene = play
    world = scene.world
    units = [world.spawn_unit(0, UnitType.FOOTMAN, (14.5 + i * 2, 12.5)) for i in range(3)]
    frame(game)
    assert health_bars(game) == []
    scene.select([units[0].id])
    frame(game)
    assert len(health_bars(game)) == 1
    x, y = scene.camera.world_to_screen(units[1].x * TILE, units[1].y * TILE)
    game.backend.inject_mouse_move(int(x), int(y - 8))
    frame(game)
    assert len(health_bars(game)) == 2, "the hovered one too"
    game.backend.inject_key("f12", alt=True)  # any input while Alt is held carries the flag
    frame(game)
    assert len(health_bars(game)) == 3 and len(health_bars(game, units_only=False)) == 5, "every unit and both halls while Alt is held"
    game.backend.inject_key("f12")
    frame(game)
    assert len(health_bars(game)) == 2, "and no longer once it is released"
    game.backend.inject_key("f11")
    frame(game)
    assert len(health_bars(game)) == 3, "F11 keeps them on"
    game.backend.inject_key("f11")
    frame(game)
    assert len(health_bars(game)) == 2


def test_bars_keep_their_screen_height_at_any_zoom(play) -> None:
    game, scene = play
    hurt = scene.world.spawn_unit(0, UnitType.FOOTMAN, (16.5, 12.5))
    hurt.hp = hurt.max_hp // 2
    for wanted in (0.5, 1.0, 2.0):
        scene.camera.zoom = wanted
        zoom = scene.camera.zoom  # the camera clamps to its own range
        frame(game)
        (bar,) = health_bars(game)
        assert bar["height"] == pytest.approx(5 / zoom) and bar["width"] == pytest.approx(TILE * 0.8 * hurt.hp / hurt.max_hp)


def test_a_site_shows_progress_and_own_work_shows_a_bar_and_a_mark_but_a_rivals_does_not(play) -> None:
    game, scene = play
    world = scene.world
    site = world.place_building(0, BuildingType.TOWER, (14, 10), done=False)
    site.progress = site.info.build_time * 0.4
    frame(game)
    assert health_bars(game) == [] and len(progress_bars(game)) == 1 and work_marks(game) == []
    world.players[0].gold = world.players[0].lumber = 5000
    barracks = world.place_building(0, BuildingType.BARRACKS, (18, 10))
    world.train(barracks.id, UnitType.FOOTMAN)
    frame(game)
    assert len(progress_bars(game)) == 2 and len(work_marks(game)) == 1, "training shows its bar and mark"
    world.players[1].gold = world.players[1].lumber = 5000
    theirs = world.place_building(1, BuildingType.BARRACKS, (22, 10))
    world.train(theirs.id, UnitType.FOOTMAN)
    frame(game)
    assert len(progress_bars(game)) == 2 and len(work_marks(game)) == 1, "a rival's work stays hidden"
    scene.select([site.id])
    frame(game)
    assert len(health_bars(game)) == 1, "a selected site shows its health as well"
