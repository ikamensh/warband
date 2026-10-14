"""Watching AI-only matches: pace, read-only HUD, unrated results (mock backend)."""

import math

import pytest

from saga2d import Button, Game, Label
from warband.sim.model import Event, RuleError
from warband.sim.races import RACES
from warband.sim.rules import BuildingType, Difficulty, Race
from warband.ui.observer import OBSERVER_SPEEDS, WatchScene, next_observer, observe_game
from warband.ui.scene import GameScene, new_game
from warband.ui.style import build_theme
from warband.ui.title import NewGameScene, TitleScene
from warband.ui.view import rgba, to_world


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Test", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


@pytest.fixture
def watch(game):
    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    return game, scene


def press(game: Game, key: str, **mods) -> None:
    game.backend.inject_key(key, **mods)
    game.tick(1 / 60)


def tick(game: Game, seconds: float, dt: float = 1 / 60) -> None:
    """*seconds* of watching in frames of *dt*."""
    for _ in range(int(seconds / dt) + 1):
        game.tick(dt)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


def click_label(game: Game, label: str) -> None:
    """Click the button of the top scene that reads *label*."""
    button = game.scene.ui.find(lambda c: isinstance(c, Button) and c.text == label)
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width // 2, y + height // 2)
    game.backend.inject_release(x + width // 2, y + height // 2)
    game.tick(1 / 60)


def screen_of(scene: GameScene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    return int(sx), int(sy)


def click_map(game: Game, scene: GameScene, point, button: str = "left") -> None:
    x, y = screen_of(scene, point)
    game.backend.inject_click(x, y, button)
    game.backend.inject_release(x, y, button)
    game.tick(1 / 60)


def test_observer_paces_are_exactly_1_1_2_1_5_2_3() -> None:
    """The watched paces, no more and no fewer."""
    assert OBSERVER_SPEEDS == (1.0, 1.2, 1.5, 2.0, 3.0)


def test_played_match_ignores_pace_keys(game) -> None:
    """A human-led match stays at 1x: PgUp/PgDn are not its pace."""
    scene = new_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    press(game, "pageup")
    press(game, "pageup")
    assert scene.execution.speed == 1.0
    start = scene.world.time
    tick(game, 1.0)
    assert abs(scene.world.time - start - 1.0) < 0.15


@pytest.mark.parametrize("steps_up", [0, 1, 2, 3, 4])
def test_observer_pace_keeps_match_time(game, steps_up: int) -> None:
    """Every watched pace advances the match by pace × real time, across frames."""
    scene = observe_game(seed=11, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    for _ in range(steps_up):
        press(game, "pageup")
    pace = OBSERVER_SPEEDS[steps_up]
    assert scene.execution.speed == pace
    start = scene.world.time
    tick(game, 2.0)
    assert abs(scene.world.time - start - 2.0 * pace) < 0.15


def test_observe_gives_every_seat_a_brain_and_no_human() -> None:
    """One real brain per playing seat; the watcher is not a seat."""
    scene = observe_game(seed=3, players=3, width=64, height=64)
    assert isinstance(scene, WatchScene)
    assert len(scene.execution.brains) == 3
    assert sorted(b.player for b in scene.execution.brains) == [0, 1, 2]
    assert not any(p.human for p in scene.world.players[:scene.world.seats])
    # No watcher seat added: the seats, plus the neutral wilds past them.
    assert len([p for p in scene.world.players if not p.neutral]) == scene.world.seats


def test_watching_is_unrated_unrecorded_and_unsaved(watch) -> None:
    """No profile, no replay, no tutorial, no autosave under a watcher."""
    _game, scene = watch
    assert scene.record.ranked is False
    assert scene.record.replay is None
    assert scene.record.profile is None
    assert scene.tutorial is None
    assert scene.record.autosave_at == math.inf
    assert scene.leaving() is None
    assert scene.conclude("left") is None


def test_new_game_observe_flow_keeps_settings(game) -> None:
    """Skirmish → Observe → Watch: clicks, not calls, keep seed, race, difficulty and map."""
    game.push(TitleScene())
    game.tick(1 / 60)
    click_label(game, "Skirmish")
    setup = game.scene
    assert isinstance(setup, NewGameScene)
    setup.set_players(2)
    setup.set_difficulty(Difficulty.HARD)
    setup.set_race(Race.ORC)
    seed = setup.seed
    click_label(game, "Observe")
    assert "you watch" in " ".join(texts(game))
    click_label(game, "Watch")
    scene = game.scene
    assert scene.record.seed == seed
    assert scene.record.difficulty is Difficulty.HARD
    assert scene.world.seats == 2
    assert scene.world.players[0].race is Race.ORC
    press(game, "pageup")
    assert scene.execution.speed == 1.2  # the match that opened is a watched one


def test_new_game_starts_played_by_default(game) -> None:
    """Untouched, the screen starts a played match as before."""
    game.push(TitleScene())
    game.tick(1 / 60)
    click_label(game, "Skirmish")
    click_label(game, "Start")
    scene = game.scene
    assert isinstance(scene, GameScene)
    press(game, "pageup")
    assert scene.execution.speed == 1.0


def test_observer_inspects_every_side_through_clicks(game) -> None:
    """A rival's unit across the map selects: the whole match is shown."""
    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    foe = scene.world.player_units(1)[0]
    scene.camera.center_on(*to_world(foe.pos))
    game.tick(1 / 60)
    click_map(game, scene, foe.pos)
    assert foe.id in scene.selection


def test_observer_orders_never_reach_the_world(watch) -> None:
    """Keys, clicks, chords and the command paths move nothing while paused."""
    game, scene = watch
    scene.toggle_pause()
    game.tick(1 / 60)
    before = scene.world.to_dict()
    assert scene.attempt("smart", [1], (2.0, 2.0)) is False
    scene.command("scout")
    press(game, "m")  # a pending order, refused
    press(game, "f", ctrl=True)  # an adjutant command, refused
    scene.toggle_catalogue("build")
    scene.open_plans()
    scene.toggle_cancel_mode()
    scene.save_to("quick")
    scene.resign(None)
    with pytest.raises(RuleError):
        scene.order("smart", [1], (2.0, 2.0))
    foe = scene.world.player_units(1)[0]
    scene.camera.center_on(*to_world(foe.pos))
    game.tick(1 / 60)
    click_map(game, scene, foe.pos, button="right")  # selects; never orders
    assert scene.world.to_dict() == before
    scene.toggle_pause()


def test_observer_outlives_the_viewed_seat(game) -> None:
    """The watch continues while two seats stand, whatever became of seat 0."""
    scene = observe_game(seed=3, players=3, width=64, height=64, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    scene.world.resign(0)
    assert not scene.world.players[0].alive
    tick_before = scene.world.tick
    tick(game, 1.0)
    assert game.scene is scene  # no result yet: seats 1 and 2 fight on
    assert scene.world.winner is None
    assert scene.world.tick > tick_before  # the match keeps stepping


def test_observer_end_names_the_winner_and_watches_again(game) -> None:
    """The result says who won — never who 'you' are — and Watch again re-deals AI seats."""
    scene = observe_game(seed=3, players=3, width=64, height=64, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    scene.world.resign(0)
    scene.world.resign(1)
    assert scene.world.winner == 2
    tick(game, 0.5)
    shown = " ".join(texts(game))
    winner = scene.world.players[2].name
    assert f"{winner} wins" in shown
    assert "Victory!" not in shown and "Defeat" not in shown
    assert "you won" not in shown.lower() and "you lost" not in shown.lower()
    click_label(game, "Watch again")
    again = game.scene
    assert again is not scene
    assert again.world.seats == 3
    assert not any(p.human for p in again.world.players[:again.world.seats])
    assert len(again.execution.brains) == 3


def test_observer_menu_leaves_profile_replays_scores_untouched(game, tmp_path) -> None:
    """Pause offers no resign or saves; leaving keeps a preexisting profile byte-identical."""
    from warband.records.profile import Profile

    keeper = Profile(tmp_path, name="Keeper", results=[])
    keeper.save()
    before = (tmp_path / "profile" / "save_1.json").read_bytes()
    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    scene.open_menu()
    game.tick(1 / 60)
    assert "Paused — observing" in " ".join(texts(game))
    labels = [c.text for c in game.scene.ui.find_all(lambda c: isinstance(c, Button))]
    assert "Resign" not in labels
    assert not any("Save" in label or "Load" in label for label in labels)
    click_label(game, "Back to title")
    assert isinstance(game.scene, TitleScene)
    assert (tmp_path / "profile" / "save_1.json").read_bytes() == before
    assert not (tmp_path / "replays").exists()
    assert not (tmp_path / "high_scores").exists()


def test_observer_switches_viewed_seats(game) -> None:
    """Keys and strip buttons inspect each side in turn, including a fallen one."""
    scene = observe_game(seed=3, players=3, width=64, height=64, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    press(game, "[")  # steps back, wrapping past seat 0 to seat 2
    assert scene.viewed == 2
    assert f"Watching {scene.world.players[2].name}" in " ".join(texts(game))
    press(game, "]")
    assert scene.viewed == 0
    click_label(game, ">")
    assert scene.viewed == 1
    click_label(game, "<")
    assert scene.viewed == 0
    scene.world.resign(0)
    press(game, "[")  # wraps past the fallen viewed seat
    assert scene.viewed == 2
    scene.watch_seat(0)  # the fallen seat stays inspectable
    assert scene.viewed == 0


def test_observer_hints_advertise_watching_not_orders(watch) -> None:
    """The key bar names inspecting, seats and pace — never orders or rallying."""
    _game, scene = watch
    wording = " ".join(f"{key}: {value}" for key, value in scene.hint())
    assert "select any side" in wording
    assert "watch a seat" in wording
    assert "pace" in wording
    assert "order" not in wording.lower()
    assert "rally" not in wording.lower()
    assert "B / T / U" not in wording


def test_watch_seam_hints_advertise_no_clock() -> None:
    """A snapshot-fed watcher reuses WatchScene.hint: no local pace or pause."""
    scene = WatchScene(observe_game(seed=3).world, 3)  # hint needs no running game
    wording = " ".join(f"{key}: {value}" for key, value in scene.hint())
    assert "select any side" in wording
    assert "pace" not in wording
    assert "pause" not in wording.lower()


def test_observer_panel_instructions_name_inspection(watch) -> None:
    """The selection panel never promises orders or cancellation while watching."""
    _game, scene = watch
    # Reason for the seam calls: draw_text strings never reach the mock backend's
    # text capture, so the seam copy is the observable under test.
    assert "inspect" in scene._empty_selection_note()
    assert "order" not in scene._empty_selection_note().lower()
    assert "cancel" not in scene._queue_footer_note().lower()


def test_observer_shows_other_seat_spells(game) -> None:
    """A rival's distant cast still bursts: the watcher is not fog-bound."""
    from saga2d.effects import Pulse

    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    hidden = next((x, y) for y in range(scene.world.height) for x in range(scene.world.width)
                  if not scene.world.is_visible(0, (x, y)))
    at = (hidden[0] + 0.5, hidden[1] + 0.5)
    # Reason for staging the event: no public path casts a foreign spell on demand;
    # the burst it draws is the observable.
    scene._handle_events([Event("spell", at, player=1, text="mend")])
    assert any(isinstance(fx, Pulse) for fx in scene.effects._items)  # effects expose no public iterator


def test_observer_names_losses_for_their_owner(game) -> None:
    """A fallen hall keeps its owner's race name; nobody's keeps the catalogue's."""
    from saga2d.effects import Toast

    scene = observe_game(seed=3, settings={"controls": "classic"}, races=[Race.HUMAN, Race.ORC])
    game.push(scene)
    game.tick(1 / 60)
    owner = scene.world.players[1]
    hall = scene.world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    # Reason for staging the events: real razings need armies; the toasts are the observable.
    scene._handle_events([Event("destroyed", hall.center, player=1, text=BuildingType.TOWN_HALL.value)])
    toasts = [fx for fx in scene.effects._items if isinstance(fx, Toast)]  # effects expose no public iterator
    assert toasts, "a visible loss shows"
    assert toasts[-1].lines == [f"{owner.name}'s great hall was destroyed"]
    scene._handle_events([Event("destroyed", (5.0, 5.0), player=None, text=BuildingType.GOLD_MINE.value)])
    neutral = [fx for fx in scene.effects._items if isinstance(fx, Toast)][-1].lines
    assert neutral == ["The gold mine was destroyed"]


def test_observer_never_voices_the_viewed_side_private_affairs(game) -> None:
    """A viewed seat's refusals and alarms are not the watcher's: no warning, no toast, no ping.

    Staged through the scene's own event consumption, the way the live world feeds it; a
    public loss on the same call still shows, and the watcher's own input refusal still warns.
    """
    from saga2d.effects import Toast

    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    unit = scene.world.player_units(scene.viewed)[0]
    hall = scene.world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    status, toasts = scene.status, len([fx for fx in scene.effects._items if isinstance(fx, Toast)])
    # Reason for staging the events: real AI refusals need broke peasants; the toasts are the observable.
    scene._handle_events([Event("refused", unit.pos, player=scene.viewed, entity=unit.id,
                                text="Cannot build: Not enough gold"),
                          Event("deferred", unit.pos, player=scene.viewed, entity=unit.id,
                                text="Not enough gold: the Farm waits as a plan"),
                          Event("under_attack", unit.pos, player=scene.viewed, entity=unit.id)])
    assert scene.status == status
    assert len([fx for fx in scene.effects._items if isinstance(fx, Toast)]) == toasts
    assert scene.last_alert is None
    scene._handle_events([Event("destroyed", hall.center, player=1, text=BuildingType.TOWN_HALL.value)])
    assert len([fx for fx in scene.effects._items if isinstance(fx, Toast)]) == toasts + 1
    assert scene.attempt("move", [unit.id], (2.0, 2.0)) is False
    assert "Observers give no orders" in scene.status


def test_observer_queue_right_click_cancels_nothing(game) -> None:
    """Right-clicking a watched hall's queue warns instead of cancelling."""
    from warband.sim.rules import UnitType

    scene = observe_game(seed=3, settings={"controls": "classic"})
    game.push(scene)
    game.tick(1 / 60)
    hall = scene.world.player_buildings(scene.viewed, BuildingType.TOWN_HALL)[0]
    scene.world.train(hall.id, UnitType.PEASANT)  # test setup recruits; the AI would too
    game.tick(1 / 60)  # with nothing selected the panel overviews production
    assert scene._queue_hits, "the hall shows queued work"  # hit coordinates only exist on the scene
    (px, py, pw, ph), _entry = scene._queue_hits[0]
    scene.toggle_pause()  # freeze the live match: only the click may move anything
    before = scene.world.to_dict()
    x, y = int(px + pw / 2), int(py + ph / 2)
    game.backend.inject_click(x, y, "right")
    game.backend.inject_release(x, y, "right")
    game.tick(1 / 60)
    assert scene.world.to_dict() == before
    assert "Observers give no orders" in " ".join(texts(game))
    scene.toggle_pause()


def test_observer_top_bar_follows_the_viewed_seat(game) -> None:
    """The strip button repoints the top bar's name, colour and race — not just Watching."""
    scene = observe_game(seed=3, settings={"controls": "classic"}, races=[Race.HUMAN, Race.ORC])
    game.push(scene)
    game.tick(1 / 60)
    first, second = scene.world.players[0], scene.world.players[1]
    assert first.name != second.name  # else the switch proves nothing
    assert RACES[first.race].name != RACES[second.race].name
    assert scene.side_name.text == first.name
    click_label(game, ">")
    assert scene.viewed == 1
    assert scene.side_name.text == second.name
    assert scene.side_name.style.text_color == rgba(second.color)
    assert scene.side_race.text == RACES[second.race].name
    click_label(game, "<")
    assert scene.side_name.text == first.name
    assert scene.side_race.text == RACES[first.race].name


def pace_button(game: Game) -> Button:
    """The Watching strip's speed button, found by its tooltip through the public tree."""
    button = game.scene.ui.find(
        lambda c: isinstance(c, Button)
        and getattr(c, "tooltip", None) == "Game speed · click to cycle · PageUp/PageDown")
    assert button is not None, "the Watching strip shows one speed button"
    assert isinstance(button, Button)
    return button


def test_observer_hud_watches_without_order_controls(watch) -> None:
    """Watching, pace and seat controls are shown; order rows and the card are gone."""
    _game, scene = watch
    shown = " ".join(texts(watch[0]))
    assert "Watching" in shown
    assert "1×" in shown  # the pace reads even at 1x
    pace = pace_button(watch[0])
    assert pace.text == "1×"
    assert watch[0].scene.ui.find(
        lambda c: isinstance(c, Button) and c.text in ("+", "-")) is None
    assert scene.settlement_row.visible is False
    assert scene.command_row.visible is False
    assert scene.spell_bar.visible is False
    assert scene.card_panel.visible is False


def test_observer_strip_clicks_change_pace(watch) -> None:
    """The speed button cycles every pace and wraps to 1x; PgUp/PgDn step bounded."""
    game, scene = watch
    assert scene.execution.speed == 1.0
    assert pace_button(game).text == "1×"
    for label, speed in (("1×", 1.2), ("1.2×", 1.5), ("1.5×", 2.0), ("2×", 3.0)):
        click_label(game, label)
        assert scene.execution.speed == speed
        assert pace_button(game).text == f"{speed:g}×"
    click_label(game, "3×")  # button wraps; keys never do
    assert scene.execution.speed == 1.0
    assert pace_button(game).text == "1×"
    press(game, "pageup")
    assert scene.execution.speed == 1.2
    assert pace_button(game).text == "1.2×"
    press(game, "pagedown")
    assert scene.execution.speed == 1.0
    assert pace_button(game).text == "1×"
    press(game, "pagedown")  # bounded below
    assert scene.execution.speed == 1.0
    for _ in range(5):
        press(game, "pageup")
    assert scene.execution.speed == 3.0  # bounded above
    assert pace_button(game).text == "3×"


def test_watch_again_stays_computer_led() -> None:
    """Watch again re-deals a match nobody leads, with the same seats and races."""
    scene = observe_game(seed=3, players=3, width=64, height=64)
    again = next_observer(scene)
    assert again.world.seats == 3
    assert not any(p.human for p in again.world.players[:again.world.seats])
    assert [p.race for p in again.world.players[:again.world.seats]] == [
        p.race for p in scene.world.players[:scene.world.seats]]
    assert len(again.execution.brains) == 3


def test_observe_notes_name_watching_not_playing(game) -> None:
    """The New game screen stays honest about who plays in each mode."""
    game.push(TitleScene())
    game.tick(1 / 60)
    click_label(game, "Skirmish")
    assert "you and" in " ".join(texts(game))
    click_label(game, "Observe")
    shown = " ".join(texts(game))
    assert "you watch" in shown
    assert "unrated" in shown
    assert "Seats:" in shown


def test_observe_controls_fit_the_smallest_window(tmp_path) -> None:
    """The Observe choice and its notes fit a 1200×680 window and still start a watch."""
    small = Game("Warband Test", backend="mock", resolution=(1200, 680), theme=build_theme(),
                 save_dir=tmp_path / "saves")
    try:
        small.push(TitleScene())
        small.tick(1 / 60)
        click_label(small, "Skirmish")
        click_label(small, "Observe")
        bounds: list[tuple] = []

        def walk(component) -> None:
            try:
                bounds.append(component.bounds)
            except (AttributeError, TypeError):
                pass
            for child in getattr(component, "children", []) or []:
                walk(child)

        walk(small.scene.ui)
        assert bounds, "the setup panel lays out nothing"
        left = min(b[0] for b in bounds)
        right = max(b[0] + b[2] for b in bounds)
        top = min(b[1] for b in bounds)
        bottom = max(b[1] + b[3] for b in bounds)
        assert left >= 0 and right <= 1200
        assert top >= 0 and bottom <= 680
        click_label(small, "Watch")
        pace = pace_button(small)
        assert pace.text == "1×"
        x, y, w, h = pace.bounds
        assert x >= 0 and x + w <= 1200 and y >= 0 and y + h <= 680
        press(small, "pageup")
        assert small.scene.execution.speed == 1.2
        assert pace.text == "1.2×"
        click_label(small, "1.2×")  # the button answers in the small window too
        assert small.scene.execution.speed == 1.5
        assert pace.text == "1.5×"
        watched = small.scene.viewed
        click_label(small, ">")
        assert small.scene.viewed != watched
        assert small.scene.side_name.text == small.scene.player.name
    finally:
        small.close()
