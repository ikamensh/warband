"""Playing Warband through the scene with keyboard and mouse (mock backend)."""

import pytest

from saga2d import Game
from warband.model import Repair, Attack, AttackMove, Build, Harvest, Move, tile_center
from warband.rules import BUILDINGS, SIM_DT, UNITS, BuildingType, UnitType
from warband.scene import CARD_NAMES, GameOverScene, GameScene, HelpScene, PauseScene, SettingsScene, new_game
from warband.style import build_theme
from warband.title import NewGameScene, TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Test", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path)
    yield g
    g._teardown()


@pytest.fixture
def play(game):
    scene = new_game(seed=3)
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


def screen_of(scene: GameScene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    return int(sx), int(sy)


def click(game: Game, scene: GameScene, point, button: str = "left", **mods) -> None:
    x, y = screen_of(scene, point)
    game.backend.inject_click(x, y, button, **mods)
    game.backend.inject_release(x, y, button, **mods)
    game.tick(1 / 60)


def drag_box(game: Game, scene: GameScene, a, b) -> None:
    x0, y0 = screen_of(scene, a)
    x1, y1 = screen_of(scene, b)
    game.backend.inject_click(x0, y0)
    game.backend.inject_drag(x1, y1, x1 - x0, y1 - y0)
    game.backend.inject_release(x1, y1)
    game.tick(1 / 60)


def hall_of(scene: GameScene):
    return scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]


def peasants_of(scene: GameScene):
    return [u for u in scene.world.player_units(scene.human) if u.is_worker]


# -- Selection and orders --------------------------------------------------------------


def test_clicking_a_peasant_selects_it_and_shows_its_card(play) -> None:
    game, scene = play
    peasant = peasants_of(scene)[0]
    click(game, scene, peasant.pos)
    assert scene.selection == [peasant.id]
    shown = texts(game)
    assert "Peasant" in shown and any(t.startswith("Damage 3") for t in shown)
    assert [c.label for c in scene._card] == ["Move", "Stop", "Attack", "Hold", "Patrol", "Build", "Repair"]
    assert "select" in scene.recent_sounds


def test_a_drag_box_selects_every_peasant_and_shift_click_toggles(play) -> None:
    game, scene = play
    ps = peasants_of(scene)
    xs, ys = [p.x for p in ps], [p.y for p in ps]
    drag_box(game, scene, (min(xs) - 1, min(ys) - 1), (max(xs) + 1, max(ys) + 1))
    assert sorted(scene.selection) == sorted(p.id for p in ps)
    assert "3 units" in texts(game)
    click(game, scene, ps[0].pos, shift=True)
    assert ps[0].id not in scene.selection and len(scene.selection) == 2
    hall = hall_of(scene)
    click(game, scene, (hall.x + 8.5, hall.y - 2.5))  # empty ground, clear of the HUD
    assert scene.selection == []


def test_right_click_sends_peasants_to_the_mine_and_soldiers_to_fight(play) -> None:
    game, scene = play
    world = scene.world
    ps = peasants_of(scene)
    scene.select([p.id for p in ps])
    mine = world.mines()[0]
    click(game, scene, mine.center, "right")
    assert all(isinstance(p.order, Harvest) and p.order.target == mine.id for p in ps)
    assert "command" in scene.recent_sounds
    footman = world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall_of(scene).x + 4, hall_of(scene).y + 4)))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, tile_center((hall_of(scene).x + 6, hall_of(scene).y + 4)))
    world.update_vision()
    game.tick(1 / 60)
    scene.select([footman.id])
    click(game, scene, enemy.pos, "right")
    assert isinstance(footman.order, Attack) and footman.order.target == enemy.id
    assert "attack_command" in scene.recent_sounds


def test_attack_hotkey_then_click_is_an_attack_move_and_m_is_a_move(play) -> None:
    game, scene = play
    world = scene.world
    footman = world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall_of(scene).x + 4, hall_of(scene).y + 4)))
    game.tick(1 / 60)
    scene.select([footman.id])
    press(game, "a")
    assert scene.pending == "attack"
    click(game, scene, (hall_of(scene).x + 8, hall_of(scene).y + 4))
    assert isinstance(footman.order, AttackMove) and scene.pending is None
    press(game, "m")
    click(game, scene, (hall_of(scene).x + 8, hall_of(scene).y + 6))
    assert isinstance(footman.order, Move)
    press(game, "s")
    assert not footman.orders


def test_build_menu_places_a_farm_where_the_mouse_is(play) -> None:
    game, scene = play
    world = scene.world
    peasant = peasants_of(scene)[0]
    scene.select([peasant.id])
    press(game, "b")
    assert scene.build_menu and [c.label for c in scene._card] == [
        "Farm", "Barracks", "Hall", "Tower", "Mill", "Smith", "Stables", "Workshop", "Church", "Back",
    ]
    press(game, "f")
    assert scene.pending == "build:farm"
    site = (hall_of(scene).x + 5, hall_of(scene).y + 4)
    game.backend.inject_mouse_move(*screen_of(scene, (site[0] + 1, site[1] + 1)))
    game.tick(1 / 60)
    assert scene._ghost() is not None and scene._ghost()[2]
    click(game, scene, (site[0] + 1, site[1] + 1))
    assert isinstance(peasant.order, Build) and peasant.order.type is BuildingType.FARM and peasant.order.pos == site
    tick(game, 3.0)
    assert any(b.type is BuildingType.FARM for b in world.player_buildings(scene.human))


def test_every_building_is_on_the_build_menu_with_its_hotkey_and_its_reason_when_locked(play) -> None:
    # The card once offered only the four opening buildings, so a player could never raise the tech chain.
    game, scene = play
    scene.select([peasants_of(scene)[0].id])
    press(game, "b")
    hotkeys = {c.label: c.hotkey for c in scene._card}
    assert hotkeys == {CARD_NAMES.get(bt, BUILDINGS[bt].name): BUILDINGS[bt].hotkey.upper() for bt in BuildingType if bt is not BuildingType.GOLD_MINE} | {"Back": "Esc"}
    press(game, "k")  # a blacksmith needs a barracks first
    assert scene.pending is None and scene.status == "Requires a Barracks"
    press(game, "m")  # a lumber mill only needs the town hall
    assert scene.pending == "build:lumber_mill"


def test_r_then_a_click_on_a_damaged_building_sends_the_peasants_to_repair_it(play) -> None:
    game, scene = play
    world = scene.world
    hall = hall_of(scene)
    farm = world.place_building(scene.human, BuildingType.FARM, (hall.x + 5, hall.y + 4))
    peasant = peasants_of(scene)[0]
    scene.select([peasant.id])
    press(game, "r")
    assert scene.pending == "repair"
    click(game, scene, farm.center)
    assert scene.pending is None and scene.status == "Nothing to repair"
    farm.hp = 100
    press(game, "r")
    click(game, scene, farm.center)
    assert isinstance(peasant.order, Repair)
    scene.select([peasant.id])
    assert ("B / R", "build / repair") in scene._hint()


def test_the_town_hall_trains_a_peasant_with_p_and_the_rally_point_by_right_click(play) -> None:
    game, scene = play
    world = scene.world
    hall = hall_of(scene)
    click(game, scene, hall.center)
    assert scene.selection == [hall.id] and [c.label for c in scene._card] == ["Peasant", "Cancel"]
    gold = scene.player.gold
    press(game, "p")
    assert hall.queue == [UnitType.PEASANT] and scene.player.gold == gold - 400
    assert any(t.startswith("Training Peasant") for t in texts(game))
    click(game, scene, world.mines()[0].center, "right")
    assert hall.rally == world.mines()[0].center
    press(game, "x")
    assert hall.queue == [] and scene.player.gold == gold
    scene.player.gold = 0
    press(game, "p")
    assert hall.queue == [] and "error" in scene.recent_sounds and any("Not enough gold" in t for t in texts(game))


def test_control_groups_assign_and_recall(play) -> None:
    game, scene = play
    ps = peasants_of(scene)
    scene.select([ps[0].id, ps[1].id])
    press(game, "1", ctrl=True)
    scene.select([])
    press(game, "1")
    assert sorted(scene.selection) == sorted([ps[0].id, ps[1].id])
    scene.select([ps[2].id])
    press(game, "1", shift=True)
    assert len(scene.selection) == 3


def test_tab_cycles_idle_peasants_and_pans_the_camera(play) -> None:
    game, scene = play
    ps = peasants_of(scene)
    scene.world.harvest([ps[0].id], scene.world.mines()[0].id)
    press(game, "tab")
    assert scene.selection == [ps[1].id]
    press(game, "tab")
    assert scene.selection == [ps[2].id]


def test_the_simulation_runs_in_fixed_steps_and_pauses(play) -> None:
    game, scene = play
    world = scene.world
    tick(game, 1.0)
    assert abs(world.time - 1.0) < 2 * SIM_DT + 1 / 60
    press(game, "f3")
    before = world.time
    tick(game, 0.5)
    assert world.time == before and "Paused" in texts(game)
    press(game, "f3")
    tick(game, 0.5)
    assert world.time > before


# -- Overlays ------------------------------------------------------------------------------


def test_escape_opens_the_menu_and_save_load_round_trips(play) -> None:
    game, scene = play
    press(game, "escape")
    assert isinstance(game.scene, PauseScene)
    press(game, "escape")
    assert game.scene is scene
    press(game, "f5")
    scene.player.gold = 9999
    press(game, "f9")
    assert scene.player.gold == 1000
    assert len(scene.world.player_units(scene.human)) == 3


def test_pause_menu_save_and_load_work_despite_the_deferred_pop(play) -> None:
    """Regression: the pause menu's pop is deferred, so saving through it used to
    store the (empty) PauseScene state and loading through it did nothing."""
    game, scene = play
    press(game, "escape")
    press(game, "f5")
    press(game, "1")
    assert game.scene is scene and game.save_manager.load(1)["scene_class"] == "GameScene"
    scene.player.gold = 9999
    press(game, "escape")
    press(game, "f9")
    press(game, "1")
    assert game.scene is scene and scene.player.gold == 1000


def test_help_and_settings_overlays(play) -> None:
    game, scene = play
    press(game, "f1")
    assert isinstance(game.scene, HelpScene)
    press(game, "escape")
    press(game, "escape")
    press(game, "s")
    assert isinstance(game.scene, SettingsScene)
    press(game, "right")
    assert scene.settings["music"] == pytest.approx(0.7)
    press(game, "escape")
    press(game, "escape")
    assert game.scene is scene


def test_losing_every_building_and_unit_ends_the_game(play) -> None:
    game, scene = play
    world = scene.world
    for b in list(world.player_buildings(scene.human)):
        b.hp = 0
    for u in list(world.player_units(scene.human)):
        u.hp = 0
    tick(game, 0.5)
    assert isinstance(game.scene, GameOverScene)
    assert any("Defeat" in t for t in texts(game)) and "defeat" in scene.recent_sounds


def test_an_attack_on_the_base_raises_an_alert_that_space_jumps_to(play) -> None:
    game, scene = play
    world = scene.world
    hall = hall_of(scene)
    enemy = world.spawn_unit(1, UnitType.KNIGHT, tile_center((hall.x + 4, hall.y + 1)))
    world.attack([enemy.id], hall.id)
    scene.camera.center_on(0, 0)
    tick(game, 3.0)
    assert scene.last_alert is not None and "under_attack" in scene.recent_sounds
    assert any("Under attack" in t for t in texts(game))
    press(game, "space")
    tick(game, 0.5)
    left, top, right, bottom = scene.camera.visible_world_rect()
    assert left < scene.last_alert[0] * 32 < right and top < scene.last_alert[1] * 32 < bottom


def test_a_kill_leaves_a_dissolving_sprite_that_is_removed(play) -> None:
    game, scene = play
    world = scene.world
    hall = hall_of(scene)
    victim = world.spawn_unit(1, UnitType.PEASANT, tile_center((hall.x + 4, hall.y + 4)))
    victim.hp = 1
    knight = world.spawn_unit(scene.human, UnitType.KNIGHT, tile_center((hall.x + 3, hall.y + 4)))
    world.attack([knight.id], victim.id)
    tick(game, 1.5)
    assert victim.id not in world.units and scene.stats["units_killed"] == 1
    tick(game, 1.5)
    assert len(scene.effects) == 0
    assert not any(s["image"] == game.assets.image(scene.view._unit_keys.get(victim.id, "")) for s in game.backend.sprites.values() if victim.id in scene.view._unit_keys)


# -- Minimap and camera ---------------------------------------------------------------


def test_clicking_the_minimap_moves_the_camera_and_right_click_orders_there(play) -> None:
    game, scene = play
    x, y, w, h = scene.minimap.bounds
    game.backend.inject_click(x + w // 2, y + h // 2)
    game.backend.inject_release(x + w // 2, y + h // 2)
    game.tick(1 / 60)
    cx, cy = scene.camera.center
    assert abs(cx - scene.world.width * 32 / 2) < 40 and abs(cy - scene.world.height * 32 / 2) < 40
    ps = peasants_of(scene)
    scene.select([ps[0].id])
    game.backend.inject_click(x + w // 2, y + h // 2, "right")
    game.tick(1 / 60)
    assert isinstance(ps[0].order, Move)


def test_scrolling_zooms_about_the_pointer_and_the_camera_stays_in_bounds(play) -> None:
    game, scene = play
    camera = scene.camera
    under = camera.screen_to_world(400, 300)
    game.backend.inject_scroll(400, 300, 0, 3)
    tick(game, 0.5)
    assert camera.zoom > 1.0 and camera.screen_to_world(400, 300) == pytest.approx(under, abs=1e-6)
    camera.scroll(-100000, -100000)
    left, top, _r, _b = camera.visible_world_rect()
    assert left >= -32 and top >= -32


# -- Title ---------------------------------------------------------------------------------


def test_title_new_game_flow_with_hotkeys(game) -> None:
    game.push(TitleScene())
    game.tick(1 / 60)
    assert "WARBAND" in texts(game)
    press(game, "n")
    assert isinstance(game.scene, NewGameScene)
    press(game, "s")
    press(game, "3")
    press(game, "return")
    scene = game.scene
    assert isinstance(scene, GameScene)
    assert (scene.world.width, scene.world.height) == (40, 32) and len(scene.world.players) == 3 and len(scene.brains) == 2


def test_title_continue_loads_the_saved_match(game) -> None:
    played = new_game(seed=11, width=40, height=32)
    game.push(played)
    game.tick(1 / 60)
    played.player.gold = 4242
    press(game, "f5")
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    press(game, "c")
    scene = game.scene
    assert isinstance(scene, GameScene) and scene.seed == 11 and scene.player.gold == 4242 and scene.world.width == 40


# -- Content through the UI ------------------------------------------------------------------


def test_a_blacksmith_researches_with_a_hotkey_and_the_panel_shows_progress(play) -> None:
    from warband.rules import Upgrade

    game, scene = play
    world = scene.world
    hall = hall_of(scene)
    world.reveal_all(scene.human)
    world.place_building(scene.human, BuildingType.BARRACKS, (hall.x + 5, hall.y))
    smith = world.place_building(scene.human, BuildingType.BLACKSMITH, (hall.x + 5, hall.y + 4))
    scene.player.gold, scene.player.lumber = 5000, 5000
    game.tick(1 / 60)
    click(game, scene, smith.center)
    labels = [c.label for c in scene._card]
    assert labels == ["Sharpened Blades", "Plate Armour", "Cancel"]  # tier two waits for tier one
    press(game, "b")
    assert smith.research is Upgrade.BLADES_1
    game.tick(1 / 60)
    assert any(t.startswith("Researching Sharpened Blades") for t in texts(game))
    press(game, "x")
    assert smith.research is None
    scene.player.upgrades.add(Upgrade.BLADES_1)
    scene.select([smith.id])
    assert [c.label for c in scene._card][0] == "Tempered Blades"


def test_the_codex_lists_every_unit_building_and_upgrade(play) -> None:
    from warband.scene import CodexScene

    game, scene = play
    press(game, "f2")
    assert isinstance(game.scene, CodexScene)
    shown = texts(game)
    for unit_type in UnitType:
        assert UNITS[unit_type].name in shown
    press(game, "2")
    shown = texts(game)
    assert "Lumber Mill" in shown and "Church" in shown
    press(game, "tab")
    shown = texts(game)
    assert "Siege Engineering" in shown and "Blessing" in shown
    press(game, "escape")
    assert game.scene is scene


def test_the_title_offers_three_difficulties_and_saves_keep_it(game) -> None:
    from warband.rules import Difficulty

    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "n")
    press(game, "h")
    assert game.scene.difficulty is Difficulty.HARD
    press(game, "return")
    scene = game.scene
    assert isinstance(scene, GameScene) and scene.difficulty is Difficulty.HARD and all(b.difficulty is Difficulty.HARD for b in scene.brains)
    press(game, "f5")
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    press(game, "c")
    assert game.scene.difficulty is Difficulty.HARD


def test_double_click_and_ctrl_click_select_every_unit_of_a_type_on_screen(play) -> None:
    game, scene = play
    ps = peasants_of(scene)
    hall = hall_of(scene)
    footman = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall.x + 4, hall.y + 4)))
    game.tick(1 / 60)
    click(game, scene, ps[0].pos)
    click(game, scene, ps[0].pos)
    assert sorted(scene.selection) == sorted(p.id for p in ps)
    click(game, scene, footman.pos, ctrl=True)
    assert scene.selection == [footman.id]
    press(game, "a", ctrl=True)
    assert scene.selection == [footman.id]


def test_patrol_button_and_camera_bookmarks(play) -> None:
    from warband.model import Patrol

    game, scene = play
    hall = hall_of(scene)
    footman = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall.x + 4, hall.y + 4)))
    game.tick(1 / 60)
    scene.select([footman.id])
    press(game, "p")
    assert scene.pending == "patrol"
    click(game, scene, (hall.x + 8, hall.y + 4))
    assert isinstance(footman.order, Patrol)
    here = scene.camera.center
    press(game, "f6", ctrl=True)
    scene.camera.center_on(here[0] + 400, here[1] + 300)
    press(game, "f6")
    tick(game, 0.4)
    assert scene.camera.center == pytest.approx(here, abs=1.0)
    press(game, "f7")
    assert any("No bookmark 2" in t for t in texts(game))


def test_the_idle_button_shows_only_while_a_peasant_idles(play) -> None:
    game, scene = play
    assert scene.idle_button.visible and "Idle 3" in texts(game)
    scene.world.harvest([p.id for p in peasants_of(scene)], scene.world.mines()[0].id)
    game.tick(1 / 60)
    assert not scene.idle_button.visible
