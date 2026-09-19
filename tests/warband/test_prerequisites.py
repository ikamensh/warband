"""What needs what (WB-054): a catalogue item the player cannot have yet is greyed out and names what it needs; one
whose prerequisite is on its way reads "after …" and is planned to wait for it."""

import pytest

from saga2d import Game
from warband.art.production import production_image
from warband.sim.rules import BUILDINGS, BuildingType, Race, UnitType, Upgrade
from warband.ui.scene import DEFAULT_SETTINGS, GameScene, new_game
from warband.ui.style import BAD, GOLD, build_theme


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
    """The lines drawn under *button*: its name, then its price or the name of what it lacks, told here as the colour
    and the glyph beside it tell it: "needs …" in red, "after …" in gold."""
    x, y, w, h = button.bounds
    lines = [t for t in game.backend.texts if x <= t["x"] < x + w and y + h <= t["y"] < y + h + 40]
    told = {BAD: "needs ", GOLD: "after "}
    return [told.get(tuple(t["color"]), "") + t["text"] for t in sorted(lines, key=lambda t: t["y"])]


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


def hover(game: Game, button) -> None:
    x, y, w, h = button.bounds
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 60)


def test_hovering_says_what_a_building_unlocks_and_what_an_item_waits_for(game) -> None:
    scene = match(game)
    press(game, "b")
    hover(game, button_of(scene, BuildingType.BARRACKS))
    assert "unlocks the Guard Tower, Blacksmith, Stables and Church" in scene.tooltip
    hover(game, button_of(scene, BuildingType.TOWER))
    assert scene.tooltip.endswith("(Requires a Barracks)")
    hover(game, button_of(scene, BuildingType.FARM))
    assert "unlocks" not in scene.tooltip
    assert scene.attempt("plan_building", scene.human, BuildingType.BARRACKS, open_site(scene, BuildingType.BARRACKS))
    hover(game, button_of(scene, BuildingType.TOWER))
    assert scene.tooltip.endswith("ordered now, it waits for the Barracks")


def test_the_codex_tech_tree_draws_what_needs_what_lit_by_what_the_player_has(game) -> None:
    """F2 then 5: every building, recruit and research of the race is a picture that names itself on hover; a line runs
    into each building from the one it needs; what the player has is bright, what is coming dimmer, the rest faint."""
    from warband.sim.races import RACES
    from warband.ui.tech import TechTree

    scene = match(game, Race.ELF)
    assert scene.attempt("plan_building", scene.human, BuildingType.BARRACKS, open_site(scene, BuildingType.BARRACKS))
    press(game, "f2")
    press(game, "5")
    tree = next(component for component in game.scene.ui.walk() if isinstance(component, TechTree))
    race = RACES[Race.ELF]
    shown = {picture.target: picture for picture in tree.pictures}
    assert set(shown) == {*BuildingType, *UnitType, *(u for u in Upgrade if race.upgrade_allowed(u))} - {BuildingType.GOLD_MINE}
    drawn = {image["image"]: image for image in game.backend.images}
    opacity = {target: drawn[game.assets.image(production_image(game, target, scene.human, Race.ELF))]["opacity"] for target in shown}
    assert opacity[BuildingType.TOWN_HALL] == 1 and opacity[UnitType.PEASANT] == 1
    assert opacity[BuildingType.BARRACKS] == opacity[UnitType.ARCHER] < 1  # planned
    assert opacity[BuildingType.WORKSHOP] < opacity[BuildingType.BARRACKS] and opacity[Upgrade.LONGBOWS] == opacity[BuildingType.WORKSHOP]
    for kind in BuildingType:
        requires = BUILDINGS[kind].requires
        if requires is None:
            continue
        (px, py, pw, _ph), (cx, cy, _cw, ch) = shown[requires].bounds, shown[kind].bounds
        assert any(line["x1"] >= px + pw and line["x2"] <= cx and abs(line["y2"] - (cy + ch / 2)) < 1 for line in game.backend.lines), kind
    x, y, w, h = shown[BuildingType.WORKSHOP].bounds
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert any(text["text"].startswith("Siege Bower") for text in game.backend.texts)
