"""Settlement plans can be issued and managed through the HUD without selecting an entity."""

import math

import pytest

from saga2d import Button, Game, Label, Row
from saga2d.testing import assert_no_text_overlap
from warband.sim.rules import BUILDINGS, UNITS, BuildingType, UnitType, Upgrade
from warband.ui.scene import SettlementPlansScene, new_game
from warband.ui.style import build_theme
from warband.art.textures import TILE


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
    """Click a labelled button, or a command-card portrait by the caption under it."""
    button = next((b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == text), None)
    if button is None:
        button = next(b for c, b in zip(game.scene.card, game.scene.card_buttons) if c.label == text)
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


def stand(scene, kind):
    """A finished *kind* of the player's, for a test about something other than prerequisites: what it opens can be
    ordered at once (WB-054 greys out what is not even on its way)."""
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    sites = sorted(((x, y) for y in range(scene.world.height) for x in range(scene.world.width)), key=lambda p: math.dist(p, hall.center))
    site = next(site for site in sites if scene.world.can_plan_building(kind, site, scene.human) is None
                and not scene.world.units_in_rect(site[0] - 1, site[1] - 1, site[0] + BUILDINGS[kind].size + 1, site[1] + BUILDINGS[kind].size + 1))
    return scene.world.place_building(scene.human, kind, site)


def test_settlement_controls_are_available_without_selection(settlement):
    """The unselected opening exposes planning tools and leaves the tutorial clear of the HUD."""
    game, scene = settlement
    assert scene.selection == []
    labels = {b.text for b in scene.ui.walk() if isinstance(b, Button)}
    assert {"Build", "Train", "Upgrade", "Plans (0)", "Assembly"} <= labels
    assert_no_text_overlap(game)


def test_empty_selection_can_plan_wait_cancel_and_set_assembly(settlement):
    """Unpaid requests survive missing requirements (the money, a prerequisite on its way) and can be managed without
    selecting their producer."""
    game, scene = settlement
    world, player = scene.world, scene.player
    player.gold = player.lumber = 0
    click(game, "Build")
    click(game, "Barracks")
    site = place_blueprint(game, scene, BuildingType.BARRACKS)
    click(game, "Smith")  # after the barracks
    place_blueprint(game, scene, BuildingType.BLACKSMITH)
    click(game, "Train")
    click(game, "Footman")
    click(game, "Upgrade")
    click(game, "Blades I")  # after the smith
    plans = world.player_plans(scene.human)
    assert [p.type for p in plans] == [BuildingType.BARRACKS, BuildingType.BLACKSMITH, UnitType.FOOTMAN, Upgrade.BLADES_1]
    assert plans[0].pos == site
    assert player.gold == player.lumber == 0 and scene.selection == []
    scene.paused = False
    for _ in range(32):
        game.tick(1 / 30)
    scene.paused = True
    click(game, "Plans (4)")
    assert isinstance(game.scene, SettlementPlansScene)
    text = "\n".join(item["text"] for item in game.backend.texts)
    assert "Not enough gold" in text and "Requires a Barracks" in text
    assert_no_text_overlap(game, top_scene_only=True)
    row = next(r for r in game.scene.ui.walk() if isinstance(r, Row)
               and any(isinstance(label, Label) and label.text == "Sharpened Blades" for label in r.walk()))
    click_button(game, next(b for b in row.walk() if isinstance(b, Button) and b.text == "Cancel"))
    assert {p.type for p in world.player_plans(scene.human)} == {BuildingType.BARRACKS, BuildingType.BLACKSMITH, UnitType.FOOTMAN}
    click(game, "Back")
    click(game, "Assembly")
    target = world.player_units(scene.human)[0].pos
    x, y = scene.camera.world_to_screen(target[0] * TILE, target[1] * TILE)
    game.backend.inject_click(x, y)
    game.tick(1 / 30)
    assert player.assembly == pytest.approx(target, abs=0.05)
    click(game, "Plans (3)")
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


def key(game, name, **mods):
    game.backend.inject_key(name, **mods)
    game.tick(1 / 30)


def test_plain_letters_plan_without_a_selection(settlement):
    """With nothing selected, T opens Train, F orders one, Shift+F trains footmen endlessly at every barracks (and
    stops), T closes; B / U / G do their jobs."""
    game, scene = settlement
    key(game, "t")
    assert scene.catalogue == "train"
    assert "Footman" in [c.label for c in scene.card]
    for mods in ({}, {"shift": True}):  # no barracks, none coming: neither an order nor endless training
        key(game, "f", **mods)
        assert scene.status == "Requires a Barracks" and not scene.world.player_plans(scene.human)
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    camps = [scene.world.place_building(scene.human, BuildingType.BARRACKS, (hall.x + 6, hall.y + dy)) for dy in (0, 4)]
    key(game, "f")
    assert len(scene.world.player_plans(scene.human)) == 1
    sounds = len(scene.recent_sounds)
    key(game, "f", shift=True)
    assert [c.auto for c in camps] == [[UnitType.FOOTMAN]] * 2 and scene.status == "Footman endlessly at 2 Barracks"
    assert list(scene.recent_sounds)[sounds:] == ["button"] and next(c for c in scene.card if c.label == "Footman").endless()
    key(game, "f", shift=True)
    assert [c.auto for c in camps] == [[], []] and scene.status == "No more endless Footman"
    key(game, "t")
    assert scene.catalogue is None
    key(game, "b")
    assert scene.catalogue == "build"
    key(game, "u")
    assert scene.catalogue == "upgrade"
    key(game, "b", ctrl=True)  # in the Upgrade catalogue B is Blades: the chord switches catalogues past the card
    assert scene.catalogue == "build"
    key(game, "f")
    assert scene.placing is BuildingType.FARM
    key(game, "g")
    assert scene.pending == "assembly" and scene.catalogue is None
    key(game, "p", ctrl=True)
    assert isinstance(game.scene, SettlementPlansScene)


def test_selection_commands_win_over_settlement_letters(settlement):
    """A peasant's B opens the Build catalogue for it, where T is the tower; Esc steps back a level at a time; T then
    opens Train; Ctrl+B builds whatever the card shows."""
    game, scene = settlement
    stand(scene, BuildingType.BARRACKS)
    peasant = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    scene.select([peasant.id])
    key(game, "b")
    assert scene.catalogue == "build" and scene.card[0].label == "Farm"
    key(game, "t")  # the tower: the card answers, the Train catalogue stays shut
    assert scene.placing is BuildingType.TOWER and scene.catalogue == "build"
    key(game, "escape")
    assert scene.pending is None and scene.catalogue == "build"
    key(game, "escape")
    assert scene.catalogue is None and scene.selection == [peasant.id] and scene.card[0].label == "Move"
    key(game, "t")
    assert scene.catalogue == "train" and scene.selection == [peasant.id]
    key(game, "t")
    assert scene.catalogue is None
    key(game, "b", ctrl=True)
    assert scene.catalogue == "build" and scene.selection == [peasant.id]


def test_settlement_row_advertises_shortcuts_that_bypass_the_command_card(settlement):
    """The global Train hint must work even while the build catalogue owns plain T for Tower."""
    game, scene = settlement
    stand(scene, BuildingType.BARRACKS)
    key(game, "b")
    key(game, "f")
    assert scene.placing is BuildingType.FARM
    for label, cap in (("Build", "Ctrl+B"), ("Train", "Ctrl+T"), ("Upgrade", "Ctrl+U"), ("Assembly", "Ctrl+G")):
        button = next(b for b in scene.ui.walk() if isinstance(b, Button) and b.text == label)
        x, y, width, height = button.bounds
        assert any(item["text"] == cap and x <= item["x"] < x + width and y <= item["y"] < y + height
                   for item in game.backend.texts)
    key(game, "t", ctrl=True)
    assert scene.catalogue == "train" and scene.pending is None
    key(game, "f")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [UnitType.FOOTMAN]


def test_the_build_catalogue_stays_while_placing_so_its_letters_switch_the_building(settlement):
    """Placing a worker's farm, the card still shows the catalogue: T switches to the tower; Ctrl+T leaves for Train."""
    game, scene = settlement
    stand(scene, BuildingType.BARRACKS)
    worker = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    scene.select([worker.id])
    key(game, "b")
    key(game, "f")
    assert scene.placing is BuildingType.FARM
    key(game, "t")
    assert scene.placing is BuildingType.TOWER and scene.catalogue == "build"
    key(game, "t", ctrl=True)
    assert scene.catalogue == "train" and scene.pending is None
    key(game, "f")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [UnitType.FOOTMAN]


def test_long_plan_list_pages_and_keeps_cancellation_visible(settlement):
    """Large requests stay within the screen and deleting a page's final entry returns to a valid page."""
    game, scene = settlement
    stand(scene, BuildingType.BARRACKS)
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


def test_upgrade_letters_order_the_next_tier(settlement):
    """U then B orders Blades I, B again Blades II (after Blades I); a third B is answered by the card rather than
    opening Build.  A chain shows its next tier to order in one slot, so every upgrade, Marksmanship the tenth, has a
    key on a nine-key grid."""
    game, scene = settlement
    stand(scene, BuildingType.BLACKSMITH)
    key(game, "u")
    caps = {c.label: c.hotkey for c in scene.card}
    assert caps["Blades I"] == "B" and "Blades II" not in caps and caps["Horses"] == "H" and caps["Marksmen"] == "M"
    key(game, "b")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [Upgrade.BLADES_1]
    assert {c.label: c.hotkey for c in scene.card}["Blades II"] == "B"
    key(game, "b")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [Upgrade.BLADES_1, Upgrade.BLADES_2]
    key(game, "b")
    assert scene.catalogue == "upgrade" and scene.status == "Already ordered"


def test_cards_count_what_is_already_ordered(settlement):
    """Two F presses caption the portrait 'Footman ×2'; a peasant plan keeps counting once the hall is training it."""
    game, scene = settlement
    world, player = scene.world, scene.player
    stand(scene, BuildingType.BARRACKS)
    player.gold = player.lumber = 0
    key(game, "t")
    key(game, "f")
    key(game, "f")
    key(game, "p")
    texts = [item["text"] for item in game.backend.texts]
    assert "Footman ×2" in texts and "Peasant ×1" in texts and "Archer" in texts
    player.gold = UNITS[UnitType.PEASANT].cost.gold
    scene.paused = False
    for _ in range(32):
        game.tick(1 / 30)
    scene.paused = True
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert hall.queue == [UnitType.PEASANT] and not any(p.type is UnitType.PEASANT for p in world.player_plans(scene.human))
    assert "Peasant ×1" in [item["text"] for item in game.backend.texts]
    key(game, "b")
    key(game, "f")
    place_blueprint(game, scene, BuildingType.FARM)
    assert "Farm ×1" in [item["text"] for item in game.backend.texts]


def test_selection_panel_overviews_production_and_manages_it(settlement):
    """Nothing selected: a portrait per item training, queued or waiting; hover explains, click selects the producer, right-click cancels."""
    game, scene = settlement
    world, player = scene.world, scene.player
    player.gold, player.lumber = 800, 0
    key(game, "t")
    key(game, "p")
    key(game, "p")
    key(game, "b")
    key(game, "f")
    place_blueprint(game, scene, BuildingType.FARM)
    key(game, "escape")
    assert scene.catalogue is None and scene.selection == []
    scene.paused = False
    for _ in range(32):
        game.tick(1 / 30)
    scene.paused = True
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert hall.queue == [UnitType.PEASANT, UnitType.PEASANT]
    farm = next(p for p in world.player_plans(scene.human) if p.type is BuildingType.FARM)
    game.tick(1 / 30)
    assert "Production · 2 in progress · 1 waiting" in [item["text"] for item in game.backend.texts]
    hits = scene.queue_hits
    assert [entry.target for _rect, entry in hits] == [UnitType.PEASANT, UnitType.PEASANT, BuildingType.FARM]
    (x, y, w, h), _first = hits[0]
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 30)
    assert scene.tooltip.startswith("Peasant · training") and "Town Hall" in scene.tooltip
    (x, y, w, h), _farm = hits[2]
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 30)
    assert scene.tooltip.startswith("Farm · ") and farm.status in scene.tooltip
    game.backend.inject_click(x + w / 2, y + h / 2, "right")
    game.tick(1 / 30)
    assert farm.id not in {p.id for p in world.player_plans(scene.human)}
    (x, y, w, h), _first = scene.queue_hits[0]
    game.backend.inject_click(x + w / 2, y + h / 2)
    game.tick(1 / 30)
    assert scene.selection == [hall.id]


def test_group_portrait_click_picks_one_unit(settlement):
    """Clicking a portrait in a group selects that unit alone; Shift-click drops it from the group instead."""
    game, scene = settlement
    peasants = [u.id for u in scene.world.player_units(scene.human) if u.is_worker]
    scene.select(peasants)
    game.tick(1 / 30)
    entity_id, (x, y, size, _) = scene.portraits[1]
    game.backend.inject_click(x + size / 2, y + size / 2, shift=True)
    game.tick(1 / 30)
    assert scene.selection == [i for i in peasants if i != entity_id]
    entity_id, (x, y, size, _) = scene.portraits[0]
    game.backend.inject_click(x + size / 2, y + size / 2)
    game.tick(1 / 30)
    assert scene.selection == [entity_id]
