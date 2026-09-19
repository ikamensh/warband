"""What needs what (WB-054): a catalogue item the player cannot have yet is greyed out and names what it needs; one
whose prerequisite is on its way reads "after …" and is planned to wait for it."""

import pytest

from saga2d import Game
from warband.art.production import production_image
from warband.sim.rules import BuildingType, Race, UnitType
from warband.ui.scene import DEFAULT_SETTINGS, GameScene, new_game
from warband.ui.style import build_theme


@pytest.fixture
def game(tmp_path):
    g = Game("Warband prerequisites", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def match(game: Game, race: Race = Race.HUMAN) -> GameScene:
    """Seed 3 at its start: the player has a town hall and three peasants, nothing else."""
    scene = new_game(seed=3, settings=dict(DEFAULT_SETTINGS, tutorial=False, sfx=0.0, music=0.0), races=[race, None])
    game.push(scene)
    game.tick(1 / 60)
    return scene


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def button_of(scene: GameScene, target):
    return next(button for command, button in zip(scene.card, scene.card_buttons) if command.target is target)


def open_site(scene: GameScene, kind: BuildingType) -> tuple[int, int]:
    """The nearest spot to the hall where *kind* may be planned."""
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    spots = sorted(((x, y) for y in range(scene.world.height) for x in range(scene.world.width)),
                   key=lambda spot: abs(spot[0] - hall.x) + abs(spot[1] - hall.y))
    return next(spot for spot in spots if scene.world.can_plan_building(kind, spot, scene.human) is None)


def caption_under(game: Game, button) -> list[str]:
    """The lines drawn under *button*: its name, then its price or what it waits for."""
    x, y, w, h = button.bounds
    lines = [t for t in game.backend.texts if x <= t["x"] < x + w and y + h <= t["y"] < y + h + 40]
    return [t["text"] for t in sorted(lines, key=lambda t: t["y"])]


def test_a_recruit_without_its_building_is_greyed_out_names_it_and_is_refused(game) -> None:
    scene = match(game)
    press(game, "t")
    assert scene.shown_catalogue == "train"
    game.tick(1 / 60)
    knight, peasant = button_of(scene, UnitType.KNIGHT), button_of(scene, UnitType.PEASANT)
    assert not knight.enabled and peasant.enabled
    assert caption_under(game, knight) == ["Knight", "needs Stables"]
    assert caption_under(game, peasant) == ["Peasant", "400 / 0"]
    press(game, "k")
    assert scene.status == "Requires a Stables" and not scene.world.player_plans(scene.human)


def test_once_its_building_is_planned_a_recruit_reads_after_it_and_is_planned_to_wait(game) -> None:
    scene = match(game)
    for key in ("b", "b", "b"):  # Build, Barracks, and its key again: the planner picks the spot
        press(game, key)
    assert [plan.type for plan in scene.world.player_plans(scene.human)] == [BuildingType.BARRACKS]
    press(game, "escape")
    press(game, "t")
    game.tick(1 / 60)
    footman = button_of(scene, UnitType.FOOTMAN)
    assert footman.enabled and caption_under(game, footman) == ["Footman", "after Barracks"]
    assert caption_under(game, button_of(scene, UnitType.KNIGHT)) == ["Knight", "needs Stables"]  # the stables are not coming
    press(game, "f")
    plans = scene.world.player_plans(scene.human)
    assert [plan.type for plan in plans] == [BuildingType.BARRACKS, UnitType.FOOTMAN]


def test_a_building_waits_on_the_card_for_its_prerequisite_to_be_on_its_way(game) -> None:
    """The Build catalogue greys a tower out until a barracks is at least planned; Shift, which keeps placing, is refused
    as its plain key is.  Planned after the barracks, the tower waits for it."""
    scene = match(game)
    press(game, "b")
    tower = button_of(scene, BuildingType.TOWER)
    assert not tower.enabled and caption_under(game, tower) == ["Tower", "needs Barracks"]
    for mods in ({}, {"shift": True}):
        press(game, "t", **mods)
        assert scene.placing is None and scene.status == "Requires a Barracks"
    press(game, "b")
    press(game, "b")  # the barracks, where the planner puts it
    game.tick(1 / 60)
    tower = button_of(scene, BuildingType.TOWER)  # placing restyles the barracks' button, and the card is laid out afresh
    assert tower.enabled and caption_under(game, tower) == ["Tower", "after Barracks"]
    press(game, "t")
    press(game, "t")
    assert [plan.type for plan in scene.world.player_plans(scene.human)] == [BuildingType.BARRACKS, BuildingType.TOWER]
    assert scene.status == "Guard Tower planned · it waits for a Barracks"


def test_the_greyed_out_item_carries_a_bright_picture_of_what_it_needs(game) -> None:
    """The dimmed knight shows the stables in its corner at full strength: the picture says what to build first."""
    scene = match(game, Race.ORC)
    press(game, "t")
    game.tick(1 / 60)
    x, y, w, h = button_of(scene, UnitType.KNIGHT).bounds
    kennels = game.assets.image(production_image(game, BuildingType.STABLES, scene.human, Race.ORC))
    drawn = [image for image in game.backend.images if image["image"] == kennels and x <= image["x"] and image["x"] + image["width"] <= x + w
             and y <= image["y"] and image["y"] + image["height"] <= y + h]
    assert len(drawn) == 1 and drawn[0]["opacity"] == 1 and drawn[0]["width"] < w / 3


def test_the_caption_follows_the_need_after_the_card_is_refreshed_unchanged(game) -> None:
    """Coming back from an overlay refreshes the card with fresh commands and the same layout: the caption once kept
    reading the commands it was built with, and showed "needs Barracks" under a footman whose barracks was planned."""
    scene = match(game)
    press(game, "t")
    press(game, "f1")
    press(game, "escape")
    assert scene.attempt("plan_building", scene.human, BuildingType.BARRACKS, open_site(scene, BuildingType.BARRACKS))
    game.tick(1 / 60)
    assert caption_under(game, button_of(scene, UnitType.FOOTMAN)) == ["Footman", "after Barracks"]
