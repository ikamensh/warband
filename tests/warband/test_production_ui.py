"""Production is readable and operable through portraits: every target has an icon, the queue shows its own."""

import pytest

from saga2d import Game, Scene
from saga2d.testing import text_boxes
from saga2d.ui import Row
from warband.production import ProductionButton, production_image
from warband.races import RACES
from warband.rules import BUILDINGS, UPGRADES, BuildingType, Race, UnitType, Upgrade
from warband.scene import new_game
from warband.style import GOLD, build_theme


def components(parent):
    yield parent
    for child in parent.children:
        yield from components(child)


@pytest.mark.parametrize("race", list(Race))
def test_every_production_target_has_a_distinct_renderable_icon(tmp_path, race) -> None:
    """Units, buildings and every upgrade (race arts included) render inside their buttons under stable keys."""
    game = Game("Production icons", backend="mock", resolution=(1920, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = Scene()
        game.push(scene)
        targets = [*UnitType, *BuildingType, *Upgrade]
        buttons = [ProductionButton(target, 0, race) for target in targets]
        scene.ui.add(Row(*buttons, spacing=4))
        game.tick(1 / 60)
        keys = [production_image(game, target, 0, race) for target in targets]
        assert len(set(keys)) == len(targets)
        assert keys == [production_image(game, target, 0, race) for target in targets]
        for button, image in zip(buttons, game.backend.images, strict=True):
            x, y, w, h = button.bounds
            assert image["image"] == game.assets.image(production_image(game, button.target, 0, race))
            assert x <= image["x"] < image["x"] + image["width"] <= x + w
            assert y <= image["y"] < image["y"] + image["height"] <= y + h
    finally:
        game._teardown()


def test_portrait_and_keycap_clicks_use_normal_button_enabled_behaviour(tmp_path) -> None:
    """Icon children never swallow clicks, and a disabled portrait stays blocked and dims."""
    game = Game("Production clicks", backend="mock", theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = Scene()
        game.push(scene)
        trained = []
        button = ProductionButton(UnitType.PEASANT, 0, Race.HUMAN, hotkey="P", on_click=lambda: trained.append(UnitType.PEASANT))
        scene.ui.add(button)
        game.tick(1 / 60)
        assert "P" in [text["text"] for text in game.backend.texts]
        x, y, width, height = button.bounds
        game.backend.inject_mouse_move(x + width / 2, y + height / 2)
        game.tick(1 / 60)
        assert button.state == "hovered"
        for cx, cy in ((x + width / 2, y + height / 2), (x + width - 5, y + height - 5)):
            game.backend.inject_click(cx, cy)
            game.backend.inject_release(cx, cy)
            game.tick(1 / 60)
        assert trained == [UnitType.PEASANT] * 2
        button.enabled = False
        game.backend.inject_click(x + width / 2, y + height / 2)
        game.tick(1 / 60)
        assert trained == [UnitType.PEASANT] * 2
        assert game.backend.images[0]["opacity"] < 1
    finally:
        game._teardown()


@pytest.fixture(params=[Race.HUMAN, Race.DWARF], ids=["humans", "dwarves"])
def play(tmp_path, request):
    game = Game("Production UI", backend="mock", resolution=(1280, 720), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3, races=[request.param, None])
    game.push(scene)
    scene.paused = True
    scene.effects.clear()
    for _ in range(3):
        game.tick(1 / 60)
    yield game, scene
    game._teardown()


def producer_of(scene, target):
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    kind = (RACES[scene.player.race].units[target].trained_at if isinstance(target, UnitType)
            else next(bt for bt, building in BUILDINGS.items() if target in building.researches))
    return hall if kind is BuildingType.TOWN_HALL else scene.world.place_building(scene.human, kind, (hall.x + 5, hall.y + 4))


@pytest.mark.parametrize("target", [*UnitType, *Upgrade])
def test_every_unit_and_upgrade_of_the_race_has_an_operable_production_icon(play, target) -> None:
    """The portrait names itself on hover, trains or researches on click, and then shows in the panel's readout."""
    game, scene = play
    race = RACES[scene.player.race]
    if isinstance(target, Upgrade) and not race.upgrade_allowed(target):
        pytest.skip(f"{target.value} is another race's art")
    info = race.units[target] if isinstance(target, UnitType) else UPGRADES[target]
    building = producer_of(scene, target)
    if isinstance(target, Upgrade) and info.requires:
        scene.player.upgrades.add(info.requires)
    scene.player.gold = scene.player.lumber = 5000
    scene.select([building.id])
    for _ in range(3):
        game.tick(1 / 60)
    px, py, pw, ph = scene.selection_panel.bounds
    for text in text_boxes(game.backend):
        if text.space == "screen" and px <= text.left < px + pw and py <= text.top < py + ph:
            assert text.right <= px + pw and text.bottom <= py + ph, str(text)
    button = next((c for c in components(scene.ui) if isinstance(c, ProductionButton) and c.target is target), None)
    assert button is not None, f"Missing production icon for {target}"
    handle = game.assets.image(production_image(game, target, scene.human, scene.player.race))
    assert any(image["image"] == handle for image in game.backend.images)
    x, y, w, h = button.bounds
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert scene.tooltip.startswith(info.name)
    game.backend.inject_click(x + w / 2, y + h / 2)
    game.backend.inject_release(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    if isinstance(target, UnitType):
        assert building.queue == [target]
    else:
        assert building.research is target
    assert any(image["image"] == handle and px <= image["x"] < px + pw and py <= image["y"] < py + ph
               for image in game.backend.images), "The active job must show its production target too"


def test_training_progress_never_crosses_the_panel_text(play) -> None:
    """The progress bar sits beside its percentage, never across a line of text."""
    game, scene = play
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    scene.world.train(hall.id, UnitType.PEASANT)
    hall.train_progress = RACES[scene.player.race].units[UnitType.PEASANT].build_time * .95
    scene.select([hall.id])
    game.tick(1 / 60)
    bars = [rect for rect in game.backend.rects if rect["space"] == "screen" and rect["color"] == GOLD and rect["height"] <= 8]
    for polygon in game.backend.polygons:  # rounded bars reach the backend as polygons
        if polygon["space"] == "screen" and polygon["color"] == GOLD:
            xs, ys = zip(*polygon["points"])
            if max(ys) - min(ys) <= 8:
                bars.append({"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)})
    assert bars, "The current production job needs a visible progress bar"
    for bar in bars:
        for text in text_boxes(game.backend):
            assert (min(text.right, bar["x"] + bar["width"]) - max(text.left, bar["x"]) <= 1
                    or min(text.bottom, bar["y"] + bar["height"]) - max(text.top, bar["y"]) <= 1), str(text)


def test_disabled_production_icons_explain_their_name_cost_and_blocker(play) -> None:
    """An unaffordable portrait still teaches its meaning when hovered, but cannot train."""
    game, scene = play
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    worker = RACES[scene.player.race].units[UnitType.PEASANT]
    scene.player.gold = 0
    scene.select([hall.id])
    for _ in range(3):
        game.tick(1 / 60)
    button = next(c for c in components(scene.ui) if isinstance(c, ProductionButton))
    assert not button.enabled
    x, y, w, h = button.bounds
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert worker.name in scene.tooltip and str(worker.cost) in scene.tooltip
    assert scene.world.can_train(hall, UnitType.PEASANT) in scene.tooltip
    game.backend.inject_click(x + w / 2, y + h / 2)
    game.backend.inject_release(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert hall.queue == []


def test_a_full_queue_shows_ordered_portraits_and_cancel_keeps_current_progress(play) -> None:
    """Current and waiting targets stay distinct and hoverable; X still cancels the last one."""
    game, scene = play
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world = scene.world
    barracks = world.place_building(scene.human, BuildingType.BARRACKS, (hall.x + 5, hall.y + 4))
    world.place_building(scene.human, BuildingType.FARM, (hall.x + 8, hall.y + 4))
    scene.player.gold = scene.player.lumber = 5000
    queue = [UnitType.FOOTMAN, UnitType.ARCHER, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.FOOTMAN]
    scene.select([barracks.id])
    for target in queue:
        game.backend.inject_key(RACES[scene.player.race].units[target].hotkey)
        game.tick(1 / 60)
    assert barracks.queue == queue
    barracks.train_progress = 3.0
    game.tick(1 / 60)
    px, py, pw, ph = scene.selection_panel.bounds
    handles = {game.assets.image(production_image(game, target, scene.human, scene.player.race)): target for target in set(queue)}
    displayed = [image for image in game.backend.images if image["image"] in handles and px <= image["x"] <= px + pw and py <= image["y"] <= py + ph]
    assert [handles[image["image"]] for image in displayed] == queue
    assert any(text["text"].endswith("%") for text in game.backend.texts)
    next_icon = displayed[1]
    x, y = next_icon["x"] + next_icon["width"] / 2, next_icon["y"] + next_icon["height"] / 2
    game.backend.inject_mouse_move(x, y)
    game.tick(1 / 60)
    ranged = RACES[scene.player.race].units[UnitType.ARCHER].name
    assert f"Queued 1: {ranged}" in [text["text"] for text in game.backend.texts]
    game.backend.inject_click(x, y)
    game.backend.inject_release(x, y)
    game.tick(1 / 60)
    assert scene.selection == [barracks.id] and barracks.queue == queue
    game.backend.inject_key("x")
    game.tick(1 / 60)
    assert barracks.queue == queue[:-1] and barracks.train_progress == 3.0
