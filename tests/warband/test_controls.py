"""The control schemes (warband.ui.controls): every command reachable by one key in each, the modes and modifiers they
share, and what the rework added — endless training, Shift-placing a row of buildings, the planner's spot."""

import math

import pytest

from saga2d import Button, CommandError, Game
from warband.online.authority import WarbandMatch
from warband.sim.model import Build, Harvest, tile_center
from warband.sim.rules import BUILDINGS, BuildingType, Race, UnitType
from warband.ui.controls import CHORDS, GRID_KEYS, SCHEMES
from warband.ui.scene import BUILD_ORDER, DEFAULT_SETTINGS, GameScene, HelpScene, SettingsScene, new_game
from warband.ui.style import build_theme


def match(game: Game, controls: str = "classic", race: Race = Race.HUMAN) -> GameScene:
    scene = new_game(seed=3, settings=dict(DEFAULT_SETTINGS, controls=controls, tutorial=False, sfx=0.0, music=0.0),
                     races=[race, None])
    scene.world.reveal_all(scene.human)
    game.push(scene)
    game.tick(1 / 60)
    return scene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband controls", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def screen_of(scene: GameScene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    return int(sx), int(sy)


def click(game: Game, scene: GameScene, point, button: str = "left", **mods) -> None:
    x, y = screen_of(scene, point)
    game.backend.inject_click(x, y, button, **mods)
    game.backend.inject_release(x, y, button, **mods)
    game.tick(1 / 60)


def click_button(game: Game, button: Button, which: str = "left", **mods) -> None:
    x, y, w, h = button.bounds
    game.backend.inject_click(x + w / 2, y + h / 2, which, **mods)
    game.backend.inject_release(x + w / 2, y + h / 2, which, **mods)
    game.tick(1 / 60)


def keycap(game: Game, button: Button) -> str:
    """The keycap drawn on *button*: the text inside it that is not its name."""
    x, y, w, h = button.bounds
    return next(t["text"] for t in game.backend.texts if x <= t["x"] < x + w and y <= t["y"] < y + h and t["text"] != button.text)


def settlement_caps(game: Game, scene: GameScene) -> dict[str, str]:
    game.tick(1 / 60)
    return {b.text: keycap(game, b) for b in scene.settlement_row.children if isinstance(b, Button)}


def hall_of(scene: GameScene):
    return scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]


def peasants_of(scene: GameScene):
    return [u for u in scene.world.player_units(scene.human) if u.is_worker]


def open_ground(scene: GameScene, kind: BuildingType, near, *, skip=()) -> tuple[int, int]:
    """A site near *near* where *kind* may go, prerequisite or not: open ground, clear of units and of the sites in *skip*."""
    world, size = scene.world, BUILDINGS[kind].size
    for reach in range(3, 14):
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                site = (int(near[0]) + dx, int(near[1]) + dy)
                if (world.can_plan_building(kind, site, scene.human) is None and not world.units_in_rect(site[0] - 1, site[1] - 1, site[0] + size + 1, site[1] + size + 1)
                        and not any(abs(site[0] - s[0]) < size + 1 and abs(site[1] - s[1]) < size + 1 for s in skip)):
                    return site
    raise AssertionError(f"no room for a {kind.value}")


def stand(scene: GameScene, *kinds: BuildingType) -> None:
    """Finished *kinds* of the player's by the hall, for a test about keys rather than prerequisites: what they open can
    be ordered at once (WB-054 greys out what is not even on its way)."""
    for kind in kinds:
        scene.world.place_building(scene.human, kind, open_ground(scene, kind, hall_of(scene).center))


def centre(kind: BuildingType, site) -> tuple[float, float]:
    size = BUILDINGS[kind].size
    return site[0] + size / 2, site[1] + size / 2


# -- Every scheme: one key per command, none claimed twice ----------------------------------------------------------


def contexts(scene: GameScene):
    """Every card the player can bring up: the unit cards, each building's (finished, going up), the three catalogues."""
    world, human = scene.world, scene.human
    hall = hall_of(scene)
    yield "soldiers", lambda: scene.select([world.spawn_unit(human, UnitType.FOOTMAN, tile_center((hall.x + 5, hall.y + 5))).id])
    yield "peasants", lambda: scene.select([peasants_of(scene)[0].id])
    for kind in BUILD_ORDER:
        def building(kind=kind):
            site = open_ground(scene, kind, hall.center)
            scene.select([world.place_building(human, kind, site).id])
        yield kind.value, building
    yield "site", lambda: scene.select([world.place_building(human, BuildingType.FARM, open_ground(scene, BuildingType.FARM, hall.center), done=False).id])
    for catalogue in ("build", "train", "upgrade"):
        yield catalogue, lambda catalogue=catalogue: (scene.select([]), scene.open_catalogue(catalogue))


@pytest.mark.parametrize("controls", list(SCHEMES))
@pytest.mark.parametrize("race", list(Race))
def test_every_card_gives_each_command_a_key_of_its_own(game, controls: str, race: Race) -> None:
    """In each scheme and for each race: every command of every card has a key, no two share one, and in Grid none
    is a key the scheme keeps for its global actions (they sit beside the grid)."""
    scene = match(game, controls, race)
    scheme = SCHEMES[controls]
    for name, bring_up in contexts(scene):
        bring_up()
        keys = [c.hotkey for c in scene.card]
        assert keys or name in ("farm", "tower"), (controls, race, name)  # what neither trains nor researches has no card
        # A tier waiting behind the one before shares its chain's letter, which only the next tier to order shows.
        assert all(k or (name == "upgrade" and not scheme.positional) for k in keys), (controls, race, name, keys)
        taken = [k.lower() for k in keys if k]
        assert len(taken) == len(set(taken)), (controls, race, name, keys)
        if scheme.positional:
            assert set(taken) <= set(GRID_KEYS) and not set(taken) & set(scheme.keys.values()), (name, keys)


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_a_card_command_answers_to_its_key(game, controls: str) -> None:
    """The key a button shows is the key it answers to: each of the Build catalogue's buildings starts its placement."""
    scene = match(game, controls)
    stand(scene, BuildingType.BARRACKS, BuildingType.BLACKSMITH)  # every building open
    scene.open_catalogue("build")
    for command in list(scene.card):
        press(game, command.key)
        assert scene.placing is command.target, (controls, command.label, command.hotkey)
        press(game, "escape")
        assert scene.pending is None and scene.catalogue == "build"


# -- Grid ---------------------------------------------------------------------------------------------------------


def test_grid_keys_go_by_the_card_position(game) -> None:
    scene = match(game, "grid")
    stand(scene, BuildingType.BARRACKS)
    peasant = peasants_of(scene)[0]
    scene.select([peasant.id])
    assert [(c.label, c.hotkey) for c in scene.card] == [("Move", "Q"), ("Stop", "W"), ("Hold", "E"), ("Attack", "A"), ("Patrol", "S"),
                                                         ("Build", "D"), ("Repair", "Z")]
    press(game, "a")
    assert scene.pending == "attack"
    press(game, "escape")
    press(game, "d")
    assert scene.catalogue == "build" and [c.hotkey for c in scene.card] == [k.upper() for k in GRID_KEYS]
    press(game, "q")
    assert scene.placing is BuildingType.FARM
    press(game, "t")  # beside the grid: the Train catalogue, whatever the card shows
    assert scene.catalogue == "train" and scene.pending is None
    press(game, "w")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [UnitType.FOOTMAN]
    press(game, "g")
    assert scene.catalogue == "upgrade"
    press(game, "r")
    assert scene.pending == "assembly"
    assert settlement_caps(game, scene) == {"Build": "B", "Train": "T", "Upgrade": "G", "Plans (1)": "F", "Assembly": "R"}


def test_the_tutorial_and_the_help_name_the_keys_of_the_scheme(game) -> None:
    scene = match(game, "grid")
    assert scene.tutorial_keys() == {"build": "D", "farm": "Q", "barracks": "W", "footman": "Q", "attack": "A"}
    game.push(HelpScene(scene.scheme))
    game.tick(1 / 60)
    shown = [t["text"] for t in game.backend.texts]
    assert "How to play · Grid controls" in shown and "Q W E / A S D / Z X C" in shown


# -- Modal ---------------------------------------------------------------------------------------------------------


def test_modal_nothing_selected_is_the_train_catalogue_and_dot_repeats(game) -> None:
    scene = match(game, "modal")
    stand(scene, BuildingType.BARRACKS)
    scene.select([])
    assert scene.shown_catalogue == "train" and scene.card[1].label == "Footman"
    press(game, "f")
    press(game, "period")
    assert [p.type for p in scene.world.player_plans(scene.human)] == [UnitType.FOOTMAN, UnitType.FOOTMAN]
    press(game, "escape")  # home has nowhere to go back to: the menu
    assert type(game.scene).__name__ == "PauseScene"
    press(game, "escape")
    press(game, "b")
    assert scene.catalogue == "build" and scene.card[0].label == "Farm"
    press(game, "escape")
    assert scene.catalogue is None and scene.shown_catalogue == "train"


def test_modal_placing_lasts_until_esc(game) -> None:
    scene = match(game, "modal")
    scene.select([])
    hall = hall_of(scene)
    press(game, "b")
    press(game, "f")
    first = open_ground(scene, BuildingType.FARM, hall.center)
    click(game, scene, centre(BuildingType.FARM, first))
    second = open_ground(scene, BuildingType.FARM, hall.center, skip=(first,))
    click(game, scene, centre(BuildingType.FARM, second))
    assert scene.placing is BuildingType.FARM  # no Shift, and the next farm is still ready
    assert sorted(p.pos for p in scene.world.player_plans(scene.human)) == sorted([first, second])
    press(game, "escape")
    assert scene.pending is None and scene.catalogue == "build"


# -- Endless training ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_shift_with_a_recruits_key_trains_it_endlessly_and_cancel_stops_it(game, controls: str) -> None:
    scene = match(game, controls)
    world = scene.world
    barracks = world.place_building(scene.human, BuildingType.BARRACKS, open_ground(scene, BuildingType.BARRACKS, hall_of(scene).center))
    scene.select([barracks.id])
    footman, archer = scene.card[0], scene.card[1]
    press(game, footman.key, shift=True)
    assert barracks.queue == [UnitType.FOOTMAN]  # switched on at an idle barracks, the first starts at once
    press(game, archer.key, shift=True)
    assert barracks.auto == [UnitType.ARCHER, UnitType.FOOTMAN] and footman.endless()  # the archer goes next
    assert scene.status == "Barracks: Archer, Footman endlessly in turn"
    for _ in range(12):
        game.tick(0.1)
    assert barracks.queue == [UnitType.FOOTMAN]
    cancel = next(c for c in scene.card if c.label == "Cancel")
    press(game, cancel.key)
    assert barracks.auto == [] and barracks.queue == [] and scene.status == "Endless training stopped"


def test_a_right_click_on_a_recruit_toggles_endless_training_as_autocast_did(game) -> None:
    scene = match(game)
    barracks = scene.world.place_building(scene.human, BuildingType.BARRACKS, open_ground(scene, BuildingType.BARRACKS, hall_of(scene).center))
    scene.select([barracks.id])
    game.tick(1 / 60)
    archer = scene.card_buttons[1]
    click_button(game, archer, "right")
    assert barracks.auto == [UnitType.ARCHER] and barracks.queue == [UnitType.ARCHER]  # endless, which starts the first at once
    click_button(game, archer, "left", shift=True)
    assert barracks.auto == [] and barracks.queue == [UnitType.ARCHER]  # no longer endless; the one in training goes on
    click_button(game, archer)
    assert barracks.queue == [UnitType.ARCHER, UnitType.ARCHER]  # a plain click orders one


def test_a_recruit_the_purse_cannot_pay_for_yet_is_still_made_endless_by_a_right_click(game) -> None:
    scene = match(game)
    barracks = scene.world.place_building(scene.human, BuildingType.BARRACKS, open_ground(scene, BuildingType.BARRACKS, hall_of(scene).center))
    scene.player.gold = 0
    scene.select([barracks.id])
    game.tick(1 / 60)
    footman = scene.card_buttons[0]
    assert not footman.enabled
    click_button(game, footman)
    assert barracks.queue == [] and barracks.auto == []  # the plain click stays blocked
    click_button(game, footman, "right")
    assert barracks.auto == [UnitType.FOOTMAN]


def test_the_building_panel_says_what_is_endless_and_why_it_waits(game) -> None:
    scene = match(game)
    world = scene.world
    barracks = world.place_building(scene.human, BuildingType.BARRACKS, open_ground(scene, BuildingType.BARRACKS, hall_of(scene).center))
    scene.select([barracks.id])
    scene.player.gold = 0
    press(game, "a", shift=True)
    for _ in range(12):
        game.tick(0.1)
    shown = [t["text"] for t in game.backend.texts]
    assert "Endless: Archer" in shown and "Not enough gold (500 needed)" in shown


# -- Placing buildings -------------------------------------------------------------------------------------------------


def shift_place_two_farms(game: Game) -> tuple[GameScene, object, tuple[int, int], tuple[int, int]]:
    """A peasant sent to the gold mine, then Shift-placing two farms with one farm's money."""
    scene = match(game)
    world = scene.world
    peasant = peasants_of(scene)[0]
    world.harvest([peasant.id], world.mines()[0].id)
    scene.player.gold, scene.player.lumber = 500, 250
    scene.select([peasant.id])
    press(game, "b")
    press(game, "f")
    first = open_ground(scene, BuildingType.FARM, hall_of(scene).center)
    click(game, scene, centre(BuildingType.FARM, first), shift=True)
    second = open_ground(scene, BuildingType.FARM, hall_of(scene).center, skip=(first,))
    click(game, scene, centre(BuildingType.FARM, second), shift=True)
    return scene, peasant, first, second


def test_shift_placing_with_a_gathering_peasant_queues_every_site(game) -> None:
    """The regression under Shift-build: a site queued behind a harvest, which never ends, was never built."""
    scene, peasant, first, second = shift_place_two_farms(game)
    assert scene.placing is BuildingType.FARM
    assert [(type(o).__name__, getattr(o, "pos", None)) for o in peasant.orders] == [("Build", first), ("Build", second)]
    assert scene.pending_sites() == [(BuildingType.FARM, first, True), (BuildingType.FARM, second, True)]
    assert next(c for c in scene.card if c.target is BuildingType.FARM).count() == 2
    click(game, scene, centre(BuildingType.FARM, first))  # the ghost refuses a site already taken
    assert scene.status == "Another building is planned here"


@pytest.mark.slow
def test_shift_placed_sites_are_all_built_the_one_short_of_money_as_a_plan(game) -> None:
    """Slow: two farms go up, a minute of the match."""
    scene, _peasant, first, second = shift_place_two_farms(game)
    world = scene.world
    for _ in range(600):
        game.tick(0.1)
        if any(b.pos == first and b.done for b in world.player_buildings(scene.human, BuildingType.FARM)) and world.player_plans(scene.human):
            break
    assert [p.pos for p in world.player_plans(scene.human)] == [second]  # left as a plan: nothing placed is lost
    scene.player.gold, scene.player.lumber = 500, 250
    for _ in range(600):
        game.tick(0.1)
        if not world.player_plans(scene.human):
            break
    assert {b.pos for b in world.player_buildings(scene.human, BuildingType.FARM)} >= {first, second}


def test_a_site_its_builder_cannot_pay_for_says_it_waits_as_a_plan(game) -> None:
    """The builder leaves a site the purse cannot pay for as a plan (a private "deferred" event); the scene never said
    so, and the player saw the builder walk away from bare ground."""
    scene = match(game)
    peasant = next(p for p in peasants_of(scene) if not p.hidden)
    scene.select([peasant.id])
    scene.player.gold = 0
    press(game, "b")
    press(game, "f")
    click(game, scene, centre(BuildingType.FARM, open_ground(scene, BuildingType.FARM, peasant.pos)))
    for _ in range(150):
        game.tick(0.1)
        if scene.world.player_plans(scene.human):
            break
    assert scene.status == "Not enough gold (500 needed): the Farm waits as a plan"


def test_several_peasants_share_the_sites_placed(game) -> None:
    scene = match(game)
    workers = peasants_of(scene)[:3]
    scene.select([w.id for w in workers])
    press(game, "b")
    press(game, "f")
    taken = []
    for _ in range(3):
        site = open_ground(scene, BuildingType.FARM, hall_of(scene).center, skip=tuple(taken))
        click(game, scene, centre(BuildingType.FARM, site), shift=True)
        taken.append(site)
    assert sorted(len([o for o in w.orders if isinstance(o, Build)]) for w in workers) == [1, 1, 1]


def test_a_buildings_key_again_lets_the_planner_pick_the_spot(game) -> None:
    scene = match(game)
    world = scene.world
    press(game, "b")
    press(game, "f")
    press(game, "f", shift=True)  # the farm's key again: the planner places it, and Shift keeps the farm ready
    press(game, "f", shift=True)
    plans = world.player_plans(scene.human)
    assert [p.type for p in plans] == [BuildingType.FARM, BuildingType.FARM] and scene.placing is BuildingType.FARM
    press(game, "f")  # without Shift: one more, and the pointer is free
    assert len(world.player_plans(scene.human)) == 3 and scene.pending is None and scene.catalogue == "build"
    hall = hall_of(scene)
    for plan in world.player_plans(scene.human):
        assert math.dist(centre(BuildingType.FARM, plan.pos), hall.center) <= 12
    press(game, "h")
    press(game, "h")  # a hall goes by a gold mine that no hall of the player's has claimed
    site = next(p for p in world.player_plans(scene.human) if p.type is BuildingType.TOWN_HALL).pos
    mine = min(world.mines(), key=lambda m: math.dist(m.center, centre(BuildingType.TOWN_HALL, site)))
    assert math.dist(mine.center, centre(BuildingType.TOWN_HALL, site)) < 8 and math.dist(mine.center, hall.center) > 8


def test_a_peasant_asked_for_a_building_whose_prerequisite_is_only_coming_plans_it(game) -> None:
    """A tower needs a barracks: refused while none is coming; once the peasant is sent to build one, the tower placed
    is a plan that waits for it (the peasant cannot start it)."""
    scene = match(game)
    peasant = peasants_of(scene)[0]
    scene.select([peasant.id])
    press(game, "b")
    press(game, "t")
    assert scene.placing is None and scene.status == "Requires a Barracks"
    press(game, "b")
    barracks = open_ground(scene, BuildingType.BARRACKS, hall_of(scene).center)
    click(game, scene, centre(BuildingType.BARRACKS, barracks))
    assert isinstance(peasant.order, Build) and peasant.order.type is BuildingType.BARRACKS
    press(game, "t")
    site = open_ground(scene, BuildingType.TOWER, hall_of(scene).center, skip=[barracks])
    click(game, scene, centre(BuildingType.TOWER, site))
    assert [(p.type, p.pos) for p in scene.world.player_plans(scene.human)] == [(BuildingType.TOWER, site)]
    assert scene.status == "Guard Tower planned · it waits for a Barracks"


# -- Settings ----------------------------------------------------------------------------------------------------------


def test_the_settings_switch_the_scheme_and_every_keycap_follows(game) -> None:
    scene = match(game)
    scene.select([peasants_of(scene)[0].id])
    assert [c.hotkey for c in scene.card][:3] == ["M", "S", "H"]
    settings = SettingsScene(scene)
    game.push(settings)
    game.tick(1 / 60)
    settings.ui.focus(next(row for row, key in settings.row_keys.items() if key == "controls"))
    press(game, "right")
    assert scene.settings["controls"] == "grid" and "Grid" in [t["text"] for t in game.backend.texts]
    press(game, "escape")
    assert [c.hotkey for c in scene.card][:3] == ["Q", "W", "E"]
    assert settlement_caps(game, scene)["Train"] == "T"
    game.push(SettingsScene(scene))
    game.tick(1 / 60)
    game.scene.ui.focus(next(row for row, key in game.scene.row_keys.items() if key == "controls"))
    press(game, "right")
    press(game, "escape")
    assert scene.scheme.name == "Modal" and [c.hotkey for c in scene.card][:3] == ["M", "S", "H"]
    assert settlement_caps(game, scene)["Train"] == "Ctrl+T"


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_ctrl_chords_reach_the_settlement_in_every_scheme(game, controls: str) -> None:
    scene = match(game, controls)
    scene.select([peasants_of(scene)[0].id])
    for letter, action in CHORDS.items():
        press(game, letter, ctrl=True)
        if action == "plans":
            assert type(game.scene).__name__ == "SettlementPlansScene"
        else:
            expected = {"build": ("build", None), "train": ("train", None), "upgrade": ("upgrade", None), "assembly": (None, "assembly")}[action]
            assert (scene.catalogue, scene.pending) == expected, (controls, letter)
        press(game, "escape")


# -- Online ------------------------------------------------------------------------------------------------------------


def test_the_authority_takes_endless_training_for_a_seats_own_buildings_only() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    hall, theirs = (world.player_buildings(seat, BuildingType.TOWN_HALL)[0] for seat in (0, 1))
    match.apply(0, {"action": "set_auto_train", "args": [hall.id, "peasant", True]})
    assert hall.auto == [UnitType.PEASANT]
    with pytest.raises(CommandError, match="own units and buildings"):
        match.apply(0, {"action": "set_auto_train", "args": [theirs.id, "peasant", True]})
    with pytest.raises(CommandError, match="switched on or off"):
        match.apply(0, {"action": "set_auto_train", "args": [hall.id, "peasant", "yes"]})
    with pytest.raises(CommandError, match="plan_if_short"):
        match.apply(0, {"action": "build", "args": [world.player_units(0)[0].id, "farm", [9, 9]], "kwargs": {"plan_if_short": 1}})
    assert theirs.auto == []
