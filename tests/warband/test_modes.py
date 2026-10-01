"""Persistent keyboard modes, exercised through the same events the player gives the game."""

from dataclasses import replace

from saga2d import Game
import pytest

from warband.sim.rules import BuildingType, UnitType
from warband.ui.scene import DEFAULT_SETTINGS, new_game
from warband.ui.style import build_theme
from warband.sim.rules import Race, Upgrade
from warband.ui import scene as scene_module
from warband.ui.tutorial import Tutorial


@pytest.fixture
def match(tmp_path):
    """A real scene on the mock backend, with quiet settings and isolated saves."""
    game = Game("Modes", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3, magic=True, settings=dict(DEFAULT_SETTINGS, controls="modal", tutorial=False, sfx=0, music=0))
    game.push(scene)
    yield game, scene
    game.close()


def press(game, key, **modifiers):
    game.backend.inject_key(key, **modifiers)
    game.tick(0.1)


def test_orders_choose_an_explicit_strength_before_giving_any_order(match):
    """Choosing an order is navigation, and its numbered strength is a deliberate action, never a timed repeat."""
    game, scene = match
    scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, (20.5, 20.5))
    scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, (21.5, 20.5))
    press(game, "o")
    press(game, "q")
    assert scene.order_choice == "scout"
    assert not scene.adjutant.tags
    press(game, "1")
    assert len(scene.adjutant.members("scout")) == 1
    assert scene.catalogue == "orders" and scene.order_choice is None
    press(game, "s", ctrl=True)
    assert len(scene.adjutant.members("scout")) == 1


def test_esc_and_right_click_back_out_one_level_and_mode_key_goes_home(match):
    """The two exits are distinct and the mode/scope/exit remain visible while placement is armed."""
    game, scene = match
    press(game, "b")
    press(game, "q")
    assert "BUILD · Settlement planner" in [t["text"] for t in game.backend.texts]
    assert "B leaves · Esc goes back" in [t["text"] for t in game.backend.texts]
    game.backend.inject_click(700, 320, "right")
    game.tick(0.1)
    assert scene.placing is None and scene.catalogue == "build"
    press(game, "q")
    press(game, "escape")
    assert scene.pending is None and scene.catalogue == "build"
    press(game, "q")
    press(game, "b")
    assert scene.pending is None and scene.catalogue is None
    assert "UNIT CONTROL" in [t["text"] for t in game.backend.texts]


def test_reordering_content_does_not_change_build_pages_or_keys(match, monkeypatch):
    """Content enumeration is not the slot ledger: presentation order changes cannot move learned bindings."""
    game, scene = match
    press(game, "b")
    before = {c.target: (scene.card_page, c.hotkey) for c in scene.card}
    press(game, "pagedown")
    before.update({c.target: (scene.card_page, c.hotkey) for c in scene.card})
    monkeypatch.setattr(scene_module, "BUILD_ORDER", tuple(reversed(scene_module.BUILD_ORDER)))
    scene.open_catalogue("build")
    after = {c.target: (scene.card_page, c.hotkey) for c in scene.card}
    press(game, "pagedown")
    after.update({c.target: (scene.card_page, c.hotkey) for c in scene.card})
    assert after == before


@pytest.mark.parametrize("race", list(Race))
def test_recruitment_roles_keep_their_keys_across_races_and_unavailable_options(match, race):
    """Foreign units never compress the shared recruit slots; disabled items consume their key and explain why."""
    game, scene = match
    scene.player.race = race
    press(game, "t")
    by_type = {c.target: c for c in scene.card}
    assert {kind: by_type[kind].hotkey for kind in (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.KNIGHT)} == {
        UnitType.PEASANT: "Q", UnitType.FOOTMAN: "W", UnitType.ARCHER: "E", UnitType.KNIGHT: "A"}
    assert len({c.hotkey for c in scene.card}) == len(scene.card)
    press(game, "a")
    assert scene.catalogue == "train" and scene.pending is None
    assert not scene.world.player_plans(scene.human)
    assert scene.status


def test_spells_keep_their_level_slots_and_switching_clears_the_target(match):
    """Learning level II first does not make it Q, and leaving Spells cannot leave an invisible cast armed."""
    game, scene = match
    scene.player.upgrades.add(Upgrade.WITHER)
    press(game, "v")
    assert next(c.hotkey for c in scene.card if c.target is Upgrade.WITHER) == "A"
    press(game, "a")
    assert scene.aiming is Upgrade.WITHER
    press(game, "t")
    assert scene.aiming is None and scene.catalogue == "train"


def test_tutorial_names_the_exit_before_a_selection_order(match):
    """A persistent Build mode cannot make the tutorial's recruitment key place another building."""
    game, scene = match
    scene.tutorial = Tutorial()
    scene.tutorial.step = 5
    press(game, "b")
    for _ in range(20):
        game.tick(0.1)
    assert "B to leave Build" in scene.objective_label.text


def test_mode_keys_switch_and_leave_without_losing_selection(tmp_path):
    """Mode navigation owns its keys even during targeting, and returning home preserves the selection."""
    game = Game("Modes", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3, magic=True, settings=dict(DEFAULT_SETTINGS, controls="modal", tutorial=False, sfx=0, music=0))
        game.push(scene)
        scene.select([next(u.id for u in scene.world.player_units(scene.human) if u.is_worker)])
        selected = list(scene.selection)

        def key(name):
            game.backend.inject_key(name)
            game.tick(0.1)

        key("b")
        assert scene.catalogue == "build"
        key("q")
        assert scene.placing is BuildingType.FARM
        key("t")
        assert scene.catalogue == "train" and scene.pending is None
        key("o")
        assert scene.catalogue == "orders"
        key("v")
        assert scene.catalogue == "spells"
        key("v")
        assert scene.catalogue is None and scene.pending is None
        assert scene.selection == selected
    finally:
        game.close()


def test_build_overflow_keeps_reserved_keys_and_selection_changes_keep_the_mode(tmp_path):
    """Later buildings get another page; selecting workers does not silently leave a planning mode."""
    game = Game("Modes", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3, magic=True, settings=dict(DEFAULT_SETTINGS, controls="modal", tutorial=False, sfx=0, music=0))
        game.push(scene)

        def key(name):
            game.backend.inject_key(name)
            game.tick(0.1)

        key("b")
        before = {c.target: c.hotkey for c in scene.card}
        assert before[BuildingType.FARM] == "Q" and before[BuildingType.CHURCH] == "C"
        key("pagedown")
        assert {c.target: c.hotkey for c in scene.card} == {BuildingType.VAULT: "Q", BuildingType.MAGE_TOWER: "W"}
        worker = next(u for u in scene.world.player_units(scene.human) if u.type is UnitType.PEASANT)
        scene.select([worker.id])
        assert scene.catalogue == "build" and scene.card_page == 1
        assert "Selected workers" in scene.mode_title
        key("pageup")
        assert {c.target: c.hotkey for c in scene.card} == before
        key("b")
        assert scene.catalogue is None and scene.selection == [worker.id]
    finally:
        game.close()


def test_racial_upgrade_order_and_completed_chains_do_not_move_options(match, monkeypatch):
    """The global upgrade card uses declared slots too, even if content tables change order."""
    game, scene = match
    press(game, "u")
    before = {c.target: c.hotkey for c in scene.card}
    monkeypatch.setitem(scene_module.RACES, scene.player.race, replace(scene.race, arts=tuple(reversed(scene.race.arts))))
    scene.open_catalogue("upgrade")
    assert {c.target: c.hotkey for c in scene.card} == before
    scene.player.upgrades.add(Upgrade.KEEP)
    scene.open_catalogue("upgrade")
    assert {c.target: c.hotkey for c in scene.card} == {kind: key for kind, key in before.items() if kind is not Upgrade.KEEP}
