"""Cancel mode (WB-065): Ctrl+X in every scheme, or the Cancel button beside Plans; then a click takes back a plan not
yet started, a site going up or a building's work, a box everything of the player's inside it, and Esc, a right click
or the key again leaves it.  It gives only orders that already exist, through ``GameScene.attempt``."""

import json
import random

import pytest

from saga2d import Button, Game
from warband.records.replay import Playback, Replay, digest
from warband.sim.model import RuleError, World
from warband.sim.rules import BUILDINGS, BuildingType, Terrain, UnitType, Upgrade
from warband.art.textures import TILE
from warband.ui.controls import SCHEMES
from warband.ui.multiplayer import NetworkGameScene
from warband.sim.races import RACES
from warband.sim.rules import UNITS
from warband.ui.scene import CANCEL_FILL, CANCEL_INK, DEFAULT_SETTINGS, GameScene, HelpScene, plural_name
from warband.ui.style import DANGER_BUTTON, GHOST_BUTTON, build_theme

HALL, BARRACKS, SMITH, FARM = (14, 10), (19, 10), (24, 10), (29, 10)  # the player's base, top-left tiles
ROW = ((14, 16), (17, 16), (20, 16))  # farm sites in a row below it
FAR = (8, 16)  # and one off to the side, outside the row's box (and clear of the command card)
RIVAL = (36, 9)  # a rival's hall in sight


@pytest.fixture
def game(tmp_path):
    g = Game("Warband cancel mode", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def base(game: Game, controls: str = "classic", scene_class: type[GameScene] = GameScene, *, ranked: bool = False) -> GameScene:
    """A hall, a barracks, a blacksmith and an idle farm of the player's, a peasant and a footman, a rich purse, and a
    silent rival's hall far off: nothing moves unless the test orders it."""
    world = World(48, 36, [[Terrain.GRASS] * 48 for _ in range(36)], 2, rng=random.Random(5))
    world.players[1].human = True  # nobody's brain: the rival never gives an order
    for kind, pos in ((BuildingType.TOWN_HALL, HALL), (BuildingType.BARRACKS, BARRACKS), (BuildingType.BLACKSMITH, SMITH), (BuildingType.FARM, FARM)):
        world.place_building(0, kind, pos)
    world.place_building(1, BuildingType.TOWN_HALL, RIVAL)
    world.spawn_unit(0, UnitType.PEASANT, (16.5, 13.5))
    world.spawn_unit(0, UnitType.FOOTMAN, (27.5, 14.5))
    world.players[0].gold = world.players[0].lumber = 20000
    world.update_vision()
    world.reveal_all(0)
    scene = scene_class(world, 5, settings=dict(DEFAULT_SETTINGS, controls=controls, tutorial=False, sfx=0.0, music=0.0), ranked=ranked)
    game.push(scene)
    game.tick(1 / 60)
    scene.camera.center_on(22 * TILE, 15 * TILE)
    game.tick(1 / 60)
    return scene


def own(scene: GameScene, kind: BuildingType):
    return scene.world.player_buildings(scene.human, kind)[0]


def unit(scene: GameScene, kind: UnitType):
    return next(u for u in scene.world.player_units(scene.human) if u.type is kind)


def plans(scene: GameScene) -> list[tuple[int, int]]:
    return [p.pos for p in scene.world.player_plans(scene.human)]


def centre(site, kind: BuildingType = BuildingType.FARM) -> tuple[float, float]:
    size = BUILDINGS[kind].size
    return site[0] + size / 2, site[1] + size / 2


def at(scene: GameScene, point) -> tuple[int, int]:
    """Where *point* (tiles) is on the screen, which must be the map's there and not the HUD's."""
    x, y = scene.camera.world_to_screen(point[0] * TILE, point[1] * TILE)
    assert scene.ui.pointer_target(x, y) is None, f"{point} lies under the HUD"
    return int(x), int(y)


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def point_at(game: Game, scene: GameScene, point) -> None:
    game.backend.inject_mouse_move(*at(scene, point))
    game.tick(1 / 60)


def click(game: Game, scene: GameScene, point, button: str = "left") -> None:
    x, y = at(scene, point)
    game.backend.inject_mouse_move(x, y)
    game.backend.inject_click(x, y, button)
    game.backend.inject_release(x, y, button)
    game.tick(1 / 60)


def drag(game: Game, scene: GameScene, a, b) -> list[tuple[str, str]]:
    """Drag a box from *a* to *b* (tiles) and let go; what the hint bar said just before the release."""
    (x0, y0), (x1, y1) = at(scene, a), at(scene, b)
    game.backend.inject_click(x0, y0)
    game.backend.inject_drag(x1, y1, x1 - x0, y1 - y0)
    game.tick(1 / 60)
    said = scene.hint()
    game.backend.inject_release(x1, y1)
    game.tick(1 / 60)
    return said


def outlined(game: Game) -> set[tuple[int, int]]:
    """The top-left tiles of what was outlined in red on the map in the last frame: a red wash inside a red border."""
    marked = [r for r in game.backend.rects if r["space"] == "world" and r["color"] in (CANCEL_FILL, CANCEL_INK)]
    fills = {(round(r["x"] / TILE), round(r["y"] / TILE)) for r in marked if r["color"] == CANCEL_FILL}
    assert sum(r["color"] == CANCEL_INK for r in marked) == 4 * len(fills), "every red wash has its border"
    return fills


def red_cross(game: Game) -> bool:
    return any(line["color"] == CANCEL_INK and line["space"] == "screen" for line in game.backend.lines)


def cancel_mode(game: Game, scene: GameScene) -> None:
    press(game, "x", ctrl=True)
    assert scene.cancelling


# -- What a click takes back ----------------------------------------------------------------------------------------


def test_a_click_cancels_a_plan_not_yet_started(game) -> None:
    scene = base(game)
    world = scene.world
    for site in ROW:
        world.plan_building(scene.human, BuildingType.FARM, site)
    purse = scene.purse
    cancel_mode(game, scene)
    point_at(game, scene, centre(ROW[0]))
    assert scene.hint()[0] == ("Click", "cancel the planned Farm")
    assert outlined(game) == {ROW[0]} and red_cross(game)
    click(game, scene, centre(ROW[0]))
    assert plans(scene) == list(ROW[1:]) and scene.purse == purse  # a plan was never paid for
    assert scene.cancelling and scene.status == "Cancelled the planned Farm"
    click(game, scene, centre(ROW[1]))  # the mode lasts for the next click
    assert plans(scene) == [ROW[2]]


def test_a_click_cancels_a_site_going_up_with_the_usual_refund(game) -> None:
    scene = base(game)
    site = scene.world.place_building(scene.human, BuildingType.FARM, ROW[0], done=False)
    gold, lumber = scene.purse
    cancel_mode(game, scene)
    point_at(game, scene, centre(ROW[0]))
    assert scene.hint()[0] == ("Click", "cancel the Farm going up (refunded)") and outlined(game) == {ROW[0]}
    click(game, scene, centre(ROW[0]))
    cost = BUILDINGS[BuildingType.FARM].cost
    assert site.id not in scene.world.buildings and scene.purse == (gold + cost.gold, lumber + cost.lumber)


def test_a_click_on_a_building_at_work_leaves_it_making_nothing(game) -> None:
    """Endless training off, the queue emptied and refunded, the research cancelled: one click each, and the
    buildings stay idle afterwards (an emptied queue that stayed endless would start the next recruit at once)."""
    scene = base(game)
    world = scene.world
    barracks, smith = own(scene, BuildingType.BARRACKS), own(scene, BuildingType.BLACKSMITH)
    purse = scene.purse
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)  # starts one at once
    world.train(barracks.id, UnitType.ARCHER)
    world.train(barracks.id, UnitType.ARCHER)
    world.set_auto_train(barracks.id, UnitType.ARCHER, True)
    world.research(smith.id, Upgrade.BLADES_1)
    cancel_mode(game, scene)
    point_at(game, scene, barracks.center)
    assert scene.hint()[0] == ("Click", "cancel Barracks: a Footman and 2 Archers in training, endless Archers and Footmen")
    assert outlined(game) == {BARRACKS}
    click(game, scene, barracks.center)
    assert barracks.auto == [] and barracks.queue == []
    point_at(game, scene, smith.center)
    assert scene.hint()[0] == ("Click", "cancel Blacksmith: researching Sharpened Blades")
    click(game, scene, smith.center)
    assert smith.research is None and scene.purse == purse
    for _ in range(20):
        game.tick(0.1)
    assert barracks.queue == [] and smith.research is None


def test_anything_else_is_left_alone_and_the_hint_says_why(game) -> None:
    scene = base(game)
    world = scene.world
    footman, peasant = unit(scene, UnitType.FOOTMAN), unit(scene, UnitType.PEASANT)
    world.build(peasant.id, BuildingType.FARM, ROW[2])  # a peasant's next site: its own order, not a plan
    scene.select([footman.id])
    cancel_mode(game, scene)
    cases = ((footman.pos, "units are not cancelled, only plans, sites and work"),
             (own(scene, BuildingType.FARM).center, "the Farm makes nothing now"),
             (centre(RIVAL, BuildingType.TOWN_HALL), "nothing of yours here"),
             ((24.5, 20.5), "nothing of yours here"),  # open ground
             (centre(ROW[2]), "the next Farm is its peasant's order; select the peasant and stop it"))
    buildings, purse = set(world.buildings), scene.purse
    for point, why in cases:
        point_at(game, scene, point)
        assert scene.hint()[0] == ("Click", f"nothing: {why}") and outlined(game) == set(), point
        click(game, scene, point)
        assert scene.status == f"Nothing to cancel: {why}"
    assert set(world.buildings) == buildings and scene.purse == purse and not footman.orders
    assert [order.pos for order in peasant.orders] == [ROW[2]]  # still on its way to build
    assert scene.selection == [footman.id] and scene.cancelling


PLURALS = {
    "Aether Elemental": "Aether Elementals", "Archer": "Archers", "Axethrower": "Axethrowers", "Ballista": "Ballistae", "Bear Rider": "Bear Riders", "Catapult": "Catapults",
    "Cleric": "Clerics", "Crossbowman": "Crossbowmen", "Dire Wolf": "Dire Wolves", "Druid": "Druids", "Flying Machine": "Flying Machines",
    "Footman": "Footmen", "Gatherer": "Gatherers", "Goblin Zeppelin": "Goblin Zeppelins", "Grunt": "Grunts", "Gyrocopter": "Gyrocopters",
    "Ironguard": "Ironguards", "Knight": "Knights", "Leafwing Glider": "Leafwing Gliders", "Miner": "Miners", "Mortar": "Mortars",
    "Ogre": "Ogres", "Peasant": "Peasants", "Peon": "Peons", "Ranger": "Rangers", "Runepriest": "Runepriests", "Sentinel": "Sentinels",
    "Shaman": "Shamans", "Stag Knight": "Stag Knights", "Stone Golem": "Stone Golems", "Troll": "Trolls", "Venom Spider": "Venom Spiders",
    # Each race's own unit (WB-068): the orcs' is one goblin with one keg, "Goblin Sappers" only when there are more.
    "Gryphon Rider": "Gryphon Riders", "Goblin Sapper": "Goblin Sappers", "Treant": "Treants", "Rune Golem": "Rune Golems",
}


def test_every_unit_name_of_every_race_has_its_right_plural() -> None:
    """The hint counts recruits by name ("2 Archers in training, endless Footmen"): every name a race or the rules
    give, creatures too, against its plural written out, so a new unit's name must be added here to pass."""
    names = {info.name for race in RACES.values() for info in race.units.values()} | {info.name for info in UNITS.values()}
    assert names == set(PLURALS)
    assert {name: plural_name(name) for name in names} == PLURALS


# -- A box ------------------------------------------------------------------------------------------------------------


def test_a_box_cancels_everything_of_yours_inside_it(game) -> None:
    scene = base(game)
    world = scene.world
    for site in (*ROW, FAR):
        world.plan_building(scene.human, BuildingType.FARM, site)
    footman = unit(scene, UnitType.FOOTMAN)
    scene.select([footman.id])
    cancel_mode(game, scene)
    said = drag(game, scene, (13.2, 15.2), (22.8, 18.8))
    assert said == [("Release", "cancel 3 plans")]
    assert plans(scene) == [FAR] and scene.status == "Cancelled 3 plans"
    assert scene.cancelling and scene.selection == [footman.id]  # a box in cancel mode selects nothing


def test_the_box_is_drawn_red_with_what_it_holds_outlined(game) -> None:
    scene = base(game)
    for site in ROW:
        scene.world.plan_building(scene.human, BuildingType.FARM, site)
    cancel_mode(game, scene)
    (x0, y0), (x1, y1) = at(scene, (13.2, 15.2)), at(scene, (19.5, 18.8))
    game.backend.inject_click(x0, y0)
    game.backend.inject_drag(x1, y1, x1 - x0, y1 - y0)
    game.tick(1 / 60)
    assert outlined(game) == set(ROW[:2])  # the third's centre lies outside
    assert any(r["color"] == CANCEL_INK and r["space"] == "screen" for r in game.backend.rects)
    game.backend.inject_release(x1, y1)
    game.tick(1 / 60)
    assert plans(scene) == [ROW[2]]


# -- In and out -------------------------------------------------------------------------------------------------------


def test_esc_a_right_click_or_the_key_again_leave_it(game) -> None:
    scene = base(game)
    footman = unit(scene, UnitType.FOOTMAN)
    scene.select([footman.id])
    cancel_mode(game, scene)
    press(game, "escape")
    assert not scene.cancelling and scene.selection == [footman.id]  # back one level: the mode, not the selection
    cancel_mode(game, scene)
    click(game, scene, (24.5, 20.5), "right")
    assert not scene.cancelling and not footman.orders  # the right click left the mode and sent nobody anywhere
    cancel_mode(game, scene)
    press(game, "x", ctrl=True)
    assert not scene.cancelling
    press(game, "x", meta=True)  # Cmd on a Mac
    assert scene.cancelling
    game.tick(1 / 60)
    button = scene.cancel_button
    assert button.style is DANGER_BUTTON
    x, y, w, h = button.bounds
    game.backend.inject_click(x + w / 2, y + h / 2)
    game.backend.inject_release(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert not scene.cancelling and button.style is GHOST_BUTTON


def test_it_takes_the_place_of_an_order_waiting_for_its_click_and_gives_way_to_the_next(game) -> None:
    """Entering it disarms a pending order; arming another, or placing a building, leaves it; a control group recalled
    keeps it, since it is the settlement's and not the selection's."""
    scene = base(game)
    footman = unit(scene, UnitType.FOOTMAN)
    scene.select([footman.id])
    press(game, "1", ctrl=True)
    press(game, "a")
    assert scene.pending == "attack"
    cancel_mode(game, scene)
    press(game, "a")
    assert scene.pending == "attack" and not scene.cancelling
    cancel_mode(game, scene)
    scene.select([])
    press(game, "1")
    assert scene.selection == [footman.id] and scene.cancelling
    press(game, "b", ctrl=True)
    press(game, "f")
    assert scene.placing is BuildingType.FARM and not scene.cancelling


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_every_scheme_names_and_takes_the_same_key(game, controls: str) -> None:
    """Ctrl+X in each: on the settlement row, in the tutorial and the help, in the hint bar, and from a building's card
    whose own X (Classic's and Modal's Cancel) stays that card's."""
    scene = base(game, controls)
    barracks = own(scene, BuildingType.BARRACKS)
    scene.world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    scene.select([barracks.id])
    game.tick(1 / 60)
    x, y, w, h = scene.cancel_button.bounds
    caps = {t["text"] for t in game.backend.texts if x <= t["x"] < x + w and y <= t["y"] < y + h}
    assert caps == {"Cancel", "Ctrl+X"} and scene.tutorial_keys()["cancel"] == "Ctrl+X"
    cancel_mode(game, scene)
    assert scene.hint()[-1] == ("Esc / Right click / Ctrl+X", "leave") and barracks.auto == [UnitType.FOOTMAN]
    press(game, "escape")
    if not SCHEMES[controls].positional:
        press(game, "x")  # the card's Cancel, as before
        assert barracks.auto == [] and not scene.cancelling
    game.push(HelpScene(scene.scheme))
    game.tick(1 / 60)
    assert "Ctrl + X" in [t["text"] for t in game.backend.texts]


def test_the_settlement_row_keeps_cancel_beside_plans(game) -> None:
    scene = base(game)
    names = [b.text for b in scene.settlement_row.children if isinstance(b, Button)]
    assert names[names.index("Plans (0)") + 1] == "Cancel"


# -- Refusals and the allowance ---------------------------------------------------------------------------------------


class Refusing(GameScene):
    """A match whose orders go elsewhere, as a network match's do, where the second ``cancel_train`` is refused."""

    refused = "Too many pending orders. Please wait."

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.given: list[str] = []

    def order(self, action, *args, **kwargs) -> None:
        self.given.append(action)
        if action == "cancel_train" and self.given.count(action) == 2:
            raise RuleError(self.refused)
        super().order(action, *args, **kwargs)


def test_a_refusal_stops_the_rest_and_leaves_the_building_idle_rather_than_half_endless(game) -> None:
    """Endless training goes off first and the queue is peeled from the back, so an order refused halfway leaves a
    building that starts nothing new, with the recruit in training still at it; nothing after the refusal is given."""
    scene = base(game, scene_class=Refusing)
    world = scene.world
    barracks, smith = own(scene, BuildingType.BARRACKS), own(scene, BuildingType.BLACKSMITH)
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    world.train(barracks.id, UnitType.ARCHER)
    world.train(barracks.id, UnitType.ARCHER)
    world.research(smith.id, Upgrade.BLADES_1)
    game.tick(0.5)
    progress = barracks.train_progress
    cancel_mode(game, scene)
    said = drag(game, scene, (18.5, 9.5), (27.8, 13.8))  # the barracks and the blacksmith
    assert said == [("Release", "cancel 2 buildings' work")]
    assert scene.given == ["set_auto_train", "cancel_train", "cancel_train"]
    assert barracks.auto == [] and barracks.queue == [UnitType.FOOTMAN, UnitType.ARCHER] and barracks.train_progress >= progress > 0
    assert smith.research is Upgrade.BLADES_1  # after the refusal: never asked
    assert scene.status == Refusing.refused and scene.cancelling


class Metered(GameScene):
    order_burst = 4


def test_cancel_mode_keeps_to_its_allowance_and_takes_the_rest_when_it_comes_back(game) -> None:
    """A network match sets an allowance under its server's rate limit, which drops a client that sends too many orders
    at once: a box over more plans than that cancels what it may and says what is left."""
    assert NetworkGameScene.order_burst is not None and NetworkGameScene.order_burst <= 20
    scene = base(game, scene_class=Metered)
    world = scene.world
    sites = [(x, y) for y in (16, 19) for x in (14, 17, 20)]
    for site in sites:
        world.plan_building(scene.human, BuildingType.FARM, site)
    cancel_mode(game, scene)
    box = (13.2, 15.2), (22.8, 21.8)
    drag(game, scene, *box)
    assert plans(scene) == sites[4:] and scene.status == "Cancelled 4 plans · 2 more: cancel again in a moment"
    drag(game, scene, *box)
    assert plans(scene) == sites[4:] and scene.status == "Nothing cancelled yet · 2 more: cancel again in a moment"
    for _ in range(10):
        game.tick(0.1)
    drag(game, scene, *box)
    assert plans(scene) == [] and scene.status == "Cancelled 2 plans"


# -- Replays ----------------------------------------------------------------------------------------------------------


def test_a_match_that_used_cancel_mode_replays_to_the_bit(game) -> None:
    """Cancel mode gives recorded World orders and nothing else, so its match plays back from its log."""
    scene = base(game, ranked=True)
    world = scene.world
    barracks = own(scene, BuildingType.BARRACKS)
    scene.select([])
    press(game, "b", ctrl=True)
    press(game, "f")
    for site in (*ROW, FAR):
        click(game, scene, centre(site))
        press(game, "f")
    press(game, "escape")
    press(game, "escape")
    scene.select([barracks.id])
    press(game, "f", shift=True)
    press(game, "a")
    for _ in range(5):
        game.tick(0.1)
    cancel_mode(game, scene)
    click(game, scene, centre(FAR))
    drag(game, scene, (13.2, 15.2), (19.8, 18.8))
    click(game, scene, barracks.center)
    for _ in range(5):
        game.tick(0.1)
    assert plans(scene) == [ROW[2]] and barracks.queue == [] and barracks.auto == []
    names = [row[1] for row in scene.replay.orders]
    assert {"cancel_plan", "set_auto_train", "cancel_train"} <= set(names)
    scene.replay.finish(world, "left")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(scene.replay.to_dict()))))
    playback.run()
    assert playback.faithful and digest(playback.world) == digest(world)
