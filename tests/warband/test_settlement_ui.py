"""Settlement plans can be issued and managed through the HUD without selecting an entity."""

import math

import pytest

from saga2d import Button, Game, Label, Row
from saga2d.testing import assert_no_text_overlap
from warband.rules import BUILDINGS, UNITS, BuildingType, UnitType, Upgrade
from warband.scene import SettlementPlansScene, new_game
from warband.style import build_theme
from warband.textures import TILE


@pytest.fixture(params=[(1280, 800), (1280, 720)], ids=["1280x800", "1280x720"])
def settlement(tmp_path, request):
    game = Game("settlement", backend="mock", resolution=request.param,
                theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3)
    scene.paused = True
    scene.world.reveal_all(scene.human)
    game.push(scene)
    game.tick(1 / 30)
    game.tick(1 / 30)  # direct scene drawings use the first frame's resolved component bounds
    try:
        yield game, scene
    finally:
        game.close()


def click(game, text):
    button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == text)
    click_button(game, button)


def click_button(game, button):
    assert button.enabled, button.text
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.tick(1 / 30)


def place_blueprint(game, scene, kind):
    """Find legal ground visible outside the HUD, then place through the real input path."""
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    sites = sorted(((x, y) for y in range(scene.world.height) for x in range(scene.world.width)),
                   key=lambda p: math.dist(p, hall.center))
    for site in sites:
        if scene.world.can_plan_building(kind, site, scene.human) is not None:
            continue
        size = BUILDINGS[kind].size
        point = ((site[0] + size / 2) * TILE, (site[1] + size / 2) * TILE)
        x, y = scene.camera.world_to_screen(*point)
        if (20 < x < game.width - 20 and 180 < y < game.height - 180
                and not any(c.visible and c.hit_test(x, y) for c in scene.ui.children)):
            game.backend.inject_click(x, y)
            game.tick(1 / 30)
            return site
    raise AssertionError("No legal visible blueprint site")


def test_settlement_controls_are_available_without_selection(settlement):
    """The unselected opening exposes planning tools and leaves the tutorial clear of the HUD."""
    game, scene = settlement
    assert scene.selection == []
    labels = {b.text for b in scene.ui.walk() if isinstance(b, Button)}
    assert {"Build", "Train", "Upgrade", "Plans (0)", "Assembly point"} <= labels
    assert_no_text_overlap(game)


def test_empty_selection_can_plan_wait_cancel_and_set_assembly(settlement):
    """Unpaid requests survive missing requirements and can be managed without selecting their producer."""
    game, scene = settlement
    world, player = scene.world, scene.player
    player.gold = player.lumber = 0
    click(game, "Build")
    click(game, "Farm")
    site = place_blueprint(game, scene, BuildingType.FARM)
    click(game, "Train")
    click(game, "Footman")
    click(game, "Upgrade")
    click(game, "Blades I")
    plans = world.player_plans(scene.human)
    assert {p.type for p in plans} == {BuildingType.FARM, UnitType.FOOTMAN, Upgrade.BLADES_1}
    assert next(p for p in plans if p.kind == "building").pos == site
    assert player.gold == player.lumber == 0 and scene.selection == []
    scene.paused = False
    for _ in range(32):
        game.tick(1 / 30)
    scene.paused = True
    click(game, "Plans (3)")
    assert isinstance(game.scene, SettlementPlansScene)
    text = "\n".join(item["text"] for item in game.backend.texts)
    assert "Not enough gold" in text and "Requires a Barracks" in text
    assert_no_text_overlap(game, top_scene_only=True)
    row = next(r for r in game.scene.ui.walk() if isinstance(r, Row)
               and any(isinstance(label, Label) and label.text == "Sharpened Blades" for label in r.walk()))
    click_button(game, next(b for b in row.walk() if isinstance(b, Button) and b.text == "Cancel"))
    assert {p.type for p in world.player_plans(scene.human)} == {BuildingType.FARM, UnitType.FOOTMAN}
    click(game, "Back")
    click(game, "Assembly point")
    target = world.player_units(scene.human)[0].pos
    x, y = scene.camera.world_to_screen(target[0] * TILE, target[1] * TILE)
    game.backend.inject_click(x, y)
    game.tick(1 / 30)
    assert player.assembly == pytest.approx(target, abs=0.05)
    click(game, "Plans (2)")
    click(game, "Clear assembly point")
    assert player.assembly is None


def test_global_unit_request_starts_when_funded_and_active_queue_can_be_cancelled(settlement):
    """The Plans panel follows a request into actual production and cancels that building's work."""
    game, scene = settlement
    player, world = scene.player, scene.world
    player.gold = player.lumber = 0
    click(game, "Train")
    click(game, "Peasant")
    assert len(world.player_plans(scene.human)) == 1 and player.gold == 0
    player.gold = UNITS[UnitType.PEASANT].cost.gold
    scene.paused = False
    for _ in range(32):
        game.tick(1 / 30)
    scene.paused = True
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert hall.queue == [UnitType.PEASANT] and not world.player_plans(scene.human)
    click(game, "Plans (1)")
    assert "Training" in "\n".join(item["text"] for item in game.backend.texts)
    click(game, "Cancel last")
    assert not hall.queue and scene.selection == []


def test_long_plan_list_pages_and_keeps_cancellation_visible(settlement):
    """Large requests stay within the screen and deleting a page's final entry returns to a valid page."""
    game, scene = settlement
    scene.player.gold = scene.player.lumber = 0
    click(game, "Train")
    for _ in range(6):
        click(game, "Footman")
    click(game, "Plans (6)")
    game.tick(1 / 30)
    assert_no_text_overlap(game, top_scene_only=True)
    for component in game.scene.ui.walk():
        if isinstance(component, Button):
            x, y, width, height = component.bounds
            assert 0 <= x < x + width <= game.width and 0 <= y < y + height <= game.height
    click(game, "Next")
    assert "2 / 2" in [item["text"] for item in game.backend.texts]
    click(game, "Cancel")
    assert len(scene.world.player_plans(scene.human)) == 5
    assert "1 / 1" in [item["text"] for item in game.backend.texts]
