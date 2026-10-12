"""Neutral camps are a match option: on by default, off with --no-wilds, preserved everywhere."""

import pytest

from saga2d import Button, Game
from warband.sim.model import World
from warband.sim.rules import Layout
from warband.ui.scene import DEFAULT_SETTINGS, new_game, next_game
from warband.ui.style import build_theme
from warband.ui.title import TitleScene


def click(game, label):
    """Click the button of the top scene that reads *label*."""
    button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == label)
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.tick(0.1)


def test_cli_leaves_the_wilds_on_unless_no_wilds_is_given():
    """The flag reads like the league's: --no-wilds stores False into wilds."""
    from warband.__main__ import cli_parser

    assert cli_parser().parse_args([]).wilds is True
    assert cli_parser().parse_args(["--no-wilds"]).wilds is False


def test_camps_off_is_the_same_map_without_occupants():
    """Disabling means no camps and no neutral units, while terrain and resources match."""
    wild = new_game(seed=7, width=64, height=48, layout=Layout.PLAINS).world
    bare = new_game(seed=7, width=64, height=48, layout=Layout.PLAINS, wilds=False).world
    assert wild.wilds and not bare.wilds
    assert wild.camps and not bare.camps
    assert any(unit.player == wild.neutral for unit in wild.units.values())
    assert all(unit.player != bare.neutral for unit in bare.units.values())
    assert bare.terrain == wild.terrain
    assert [(m.type, m.pos, m.gold) for m in bare.mines()] == [(m.type, m.pos, m.gold) for m in wild.mines()]
    assert bare.rifts == wild.rifts


@pytest.mark.parametrize("enabled", [False, True])
def test_player_can_choose_wilds_before_starting(tmp_path, enabled):
    """The setup toggle changes the preview and the match actually started by Enter."""
    game = Game("Wilds option", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene(settings=dict(DEFAULT_SETTINGS, tutorial=False, music=0, sfx=0)))
        game.scene.new_game()
        game.tick(0.1)  # lays the panel out, so its buttons can be clicked
        setup = game.scene
        assert setup.wilds is True
        assert setup.preview_world.camps
        for _ in range(0 if enabled else 1):
            click(game, f"Monsters: {'On' if setup.wilds else 'Off'}")
        assert setup.wilds is enabled
        assert bool(setup.preview_world.camps) is enabled
        game.backend.inject_key("return")
        game.tick(0.1)
        assert game.scene.world.wilds is enabled
        assert bool(game.scene.world.camps) is enabled
    finally:
        game.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_multiplayer_wilds_choice_survives_snapshots_and_checkpoint(enabled):
    """The host's option reaches every seat and survives an authority restart."""
    from warband.online.authority import ONLINE

    spec = ONLINE["warband-v2"]
    match = spec.create({"wilds": enabled})
    assert bool(match.world.camps) is enabled
    for seat in range(2):
        world = World.from_dict(match.snapshot(seat)["world"])
        assert world.wilds is enabled
    assert spec.restore(spec.checkpoint(match)).world.wilds is enabled


@pytest.mark.parametrize("invalid", ["false", 0, 1, None])
def test_multiplayer_refuses_non_boolean_wilds_options(invalid):
    """Room options cannot accidentally drop the camps with a truthy string or integer."""
    from saga2d import CommandError
    from warband.online.authority import ONLINE

    with pytest.raises(CommandError, match="wilds must be a boolean"):
        ONLINE["warband-v2"].create({"wilds": invalid})


def test_changing_race_before_start_keeps_a_camps_off_room_camps_off():
    """The waiting-room race rebuild replays the same map, not a camps-on one."""
    from warband.online.authority import ONLINE, _configure_player

    spec = ONLINE["warband-v2"]
    match = spec.create({"seed": 7, "wilds": False})
    assert match.world.camps == []
    _configure_player(match, 0, {"race": "orc"})
    assert match.world.wilds is False
    assert match.world.camps == []
    assert match.world.players[0].race.value == "orc"


@pytest.mark.parametrize("enabled", [False, True])
def test_wilds_option_survives_save_load_and_next_match(enabled):
    """Loading and playing again preserve the chosen match rules."""
    scene = new_game(seed=7, width=64, height=48, layout=Layout.PLAINS, wilds=enabled)
    saved = scene.world.to_dict()
    loaded = World.from_dict(saved)
    assert loaded.wilds is enabled and loaded.to_dict() == saved
    assert next_game(scene).world.wilds is enabled


def test_old_saves_keep_the_wilds_they_were_played_with():
    """A save from before the option loads with camps on, as every old map was."""
    saved = new_game(seed=7, width=64, height=48, layout=Layout.PLAINS).world.to_dict()
    del saved["wilds"]
    assert World.from_dict(saved).wilds is True


def test_every_encounter_has_a_lair_card_tip():
    """The lair card indexes CAMP_TIPS strictly: a catalogue key without one crashes the HUD."""
    from warband.sim.rules import CAMP_ENCOUNTERS
    from warband.ui.scene import CAMP_TIPS

    assert set(CAMP_TIPS) == set(CAMP_ENCOUNTERS)


def test_multiplayer_host_can_switch_wilds_in_room_setup(tmp_path):
    """The visible toggle controls both hosted LAN matches and online creation options."""
    game = Game("Wilds room setup", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene(settings=dict(DEFAULT_SETTINGS, music=0, sfx=0)))
        game.scene.multiplayer()
        menu = game.scene
        game.tick(0.1)
        assert menu.create_options()["wilds"] is True
        assert menu.create_match().world.camps
        x, y, w, h = menu.wilds_button.bounds
        game.backend.inject_click(int(x + w / 2), int(y + h / 2))
        game.backend.inject_release(int(x + w / 2), int(y + h / 2))
        game.tick(0.1)
        assert menu.create_options()["wilds"] is False
        assert menu.create_match().world.camps == []
        menu.set_mode("lan")
        game.tick(0.1)
        assert menu.wilds_button.text == "Monsters: Off"
    finally:
        game.close()
