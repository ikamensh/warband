"""Magic is a match option: absent by default, preserved when explicitly enabled."""

import pytest

from saga2d import Button, Game
from saga2d.testing.online import server_fixture
from warband.sim.model import World
from warband.sim.rules import BuildingType
from warband.ui.scene import DEFAULT_SETTINGS, new_game
from warband.ui.style import build_theme
from warband.ui.title import TitleScene

magic_server = server_fixture("warband.online.authority:ONLINE")


def click(game, label):
    """Click the button of the top scene that reads *label*."""
    button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == label)
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.tick(0.1)


def test_new_matches_have_no_magic_sources_by_default():
    """Starting an ordinary match creates no ley rifts or magical economy."""
    scene = new_game(seed=3)
    assert not scene.world.magic
    assert not scene.world.rifts
    assert list(scene.world.placeable(BuildingType.VAULT, 0, [(10, 10)])) == []


@pytest.mark.parametrize("enabled", [False, True])
def test_player_can_choose_magic_before_starting(tmp_path, enabled):
    """The setup toggle changes the preview and the match actually started by Enter."""
    game = Game("Magic option", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene(settings=dict(DEFAULT_SETTINGS, tutorial=False, music=0, sfx=0)))
        game.scene.new_game()
        game.tick(0.1)  # lays the panel out, so its buttons can be clicked
        setup = game.scene
        assert not setup.preview_world.magic
        assert not setup.preview_world.rifts
        for _ in range(1 if enabled else 2):
            click(game, "Magic: On" if setup.magic else "Magic: Off")
        assert setup.preview_world.magic is enabled
        assert bool(setup.preview_world.rifts) is enabled
        game.backend.inject_key("return")
        game.tick(0.1)
        assert game.scene.world.magic is enabled
        assert bool(game.scene.world.rifts) is enabled
    finally:
        game.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_multiplayer_magic_choice_survives_snapshots_and_checkpoint(enabled):
    """The host's option reaches every seat and survives an authority restart."""
    from warband.online.authority import ONLINE

    spec = ONLINE["warband-v2"]
    match = spec.create({"magic": enabled})
    for seat in range(2):
        world = World.from_dict(match.snapshot(seat)["world"])
        assert world.magic is enabled
        assert bool(world.rifts) is enabled
    assert spec.restore(spec.checkpoint(match)).world.magic is enabled


@pytest.mark.parametrize("invalid", ["false", 0, 1, None])
def test_multiplayer_refuses_non_boolean_magic_options(invalid):
    """Room options cannot accidentally enable magic with a truthy string or integer."""
    from saga2d import CommandError
    from warband.online.authority import ONLINE

    with pytest.raises(CommandError, match="magic must be a boolean"):
        ONLINE["warband-v2"].create({"magic": invalid})


@pytest.mark.parametrize("enabled", [False, True])
def test_magic_option_survives_save_load_and_next_match(enabled):
    """Loading and playing again preserve the chosen match rules."""
    from warband.ui.scene import next_game

    scene = new_game(seed=3, magic=enabled)
    saved = scene.world.to_dict()
    loaded = World.from_dict(saved)
    assert loaded.magic is enabled and loaded.to_dict() == saved
    assert next_game(scene).world.magic is enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_magic_ui_follows_the_match_option(tmp_path, enabled):
    """HUD, build catalogue, modal shortcuts, help and codex expose only enabled match systems."""
    from saga2d import Button
    from warband.ui.icons import Icon
    from warband.ui.scene import CodexScene

    game = Game("Magic UI", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3, magic=enabled, settings=dict(DEFAULT_SETTINGS, controls="modal", tutorial=False, music=0, sfx=0))
        game.push(scene)
        game.tick(0.1)
        assert any(isinstance(c, Icon) and c.name == "aether" for c in scene.ui.walk()) is enabled
        scene.open_catalogue("build")
        offered = set()
        for _ in range(scene.card_pages):
            offered.update(command.target for command in scene.card)
            scene.change_card_page(1)
        assert (BuildingType.VAULT in offered) is enabled
        assert (BuildingType.MAGE_TOWER in offered) is enabled
        scene.open_catalogue(None)
        game.backend.inject_key("v")
        game.tick(0.1)
        assert (scene.catalogue == "spells") is enabled
        scene.open_help()
        game.tick(0.1)
        text = " ".join(t["text"] for t in game.backend.texts).lower()
        assert ("aether" in text) is enabled
        assert ("alt+1-3" in text) is enabled
        game.pop()
        scene.open_codex()
        game.tick(0.1)
        assert isinstance(game.scene, CodexScene)
        assert any(isinstance(c, Button) and c.text == "Spells" for c in game.scene.ui.walk()) is enabled
        game.scene.page_buildings()
        game.tick(0.1)
        text = " ".join(t["text"] for t in game.backend.texts)
        assert ("Arcane Vault" in text) is enabled
        game.scene.page_tree()
        game.tick(0.1)
        text = " ".join(t["text"] for t in game.backend.texts)
        assert ("Mage Tower" in text) is enabled
    finally:
        game.close()


def test_multiplayer_host_can_switch_magic_in_room_setup(tmp_path):
    """The visible toggle controls both hosted LAN matches and online creation options."""
    game = Game("Magic room setup", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene(settings=dict(DEFAULT_SETTINGS, music=0, sfx=0)))
        game.scene.multiplayer()
        menu = game.scene
        game.tick(0.1)
        assert not menu.create_options()["magic"]
        x, y, w, h = menu.magic_button.bounds
        game.backend.inject_click(int(x + w / 2), int(y + h / 2))
        game.backend.inject_release(int(x + w / 2), int(y + h / 2))
        game.tick(0.1)
        assert menu.create_options()["magic"]
        assert menu.create_match().world.magic
        menu.set_mode("lan")
        game.tick(0.1)
        assert menu.magic_button.text == "Magic: On"
        x, y, w, h = menu.magic_button.bounds
        game.backend.inject_click(int(x + w / 2), int(y + h / 2))
        game.backend.inject_release(int(x + w / 2), int(y + h / 2))
        game.tick(0.1)
        assert not menu.create_match().world.magic
    finally:
        game.close()


def test_old_saves_keep_the_magic_rules_they_were_played_with():
    """An existing magic match remains playable when its save predates the option."""
    saved = new_game(seed=3, magic=True).world.to_dict()
    del saved["magic"]
    loaded = World.from_dict(saved)
    assert loaded.magic and loaded.rifts


@pytest.mark.slow
@pytest.mark.parametrize("enabled", [False, True])
def test_online_room_delivers_hosts_magic_choice_to_joining_players(magic_server, enabled):
    """A real server and two socket clients receive the same match option.

    Server startup and the websocket handshake require processes and sockets: the slow tier.
    """
    from websockets.sync.client import connect
    from saga2d.testing.online import handshake, receive

    with connect(magic_server, proxy=None) as host, connect(magic_server, proxy=None) as guest:
        room = handshake(host, game="warband-v2", options={"magic": enabled})
        initial = receive(host)["state"]["world"]
        assert initial["magic"] is enabled and bool(initial["rifts"]) is enabled
        handshake(guest, "join", game="warband-v2", room=room["room"])
        joined = receive(guest)["state"]["world"]
        assert joined["magic"] is enabled and bool(joined["rifts"]) is enabled


def test_fuzz_does_not_stage_spells_in_a_magic_disabled_match():
    """The seed-81 fuzz regression: disabled matches have no spell to choose."""
    import random
    from tools.fuzz import stage_cast

    world = new_game(seed=81).world
    saved = world.to_dict()
    stage_cast(world, random.Random(81))
    assert world.to_dict() == saved
