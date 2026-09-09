"""Online menus retain the live room and never switch a player into a solo game."""
import time

import pytest

from saga2d import Button, Game, MatchMenu
from saga2d.online import OnlineClient
from saga2d.testing.online import server_fixture

server_url = server_fixture('warband.multiplayer:ONLINE')
from warband.multiplayer import NetworkGameScene
from warband.scene import SettingsScene
from warband.style import build_theme
from warband.title import TitleScene


def wait_for(game, partner, predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        game.tick(1 / 30)
        partner.poll()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError(f'Online menu did not converge: {type(game.scene).__name__}')


def press(game, key):
    game.backend.inject_key(key)
    game.tick(1 / 30)


def buttons(game):
    return [button.text for button in game.scene.ui.walk() if isinstance(button, Button)]


@pytest.fixture
def online_game(server_url, tmp_path, monkeypatch):
    monkeypatch.setenv('SAGA2D_SERVER_URL', server_url)
    partner = OnlineClient('warband-v1', endpoint=server_url, options={'seed': 3, 'width': 40, 'height': 32})
    game = Game('online menu', backend='mock', resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        game.push(TitleScene())
        wait_for(game, partner, lambda: bool(partner.room))
        press(game, 'm')
        assert isinstance(game.scene, MatchMenu)
        for character in partner.room:
            press(game, character)
        press(game, 'return')
        wait_for(game, partner, lambda: isinstance(game.scene, NetworkGameScene) and partner.ready)
        yield game, partner
    finally:
        game.close()
        partner.close()


def test_online_menu_keeps_play_live_and_leaving_preserves_rejoin(online_game):
    """Real room state keeps advancing under menus; leaving returns to a recoverable seat."""
    game, partner = online_game
    match = game.scene
    room = match.session.room
    press(game, 'f10')
    menu = game.scene
    assert buttons(game) == ['Return to match', 'Settings', 'How to play', 'Leave match', 'Quit']
    text = '\n'.join(item['text'] for item in game.backend.texts)
    assert 'Match menu' in text and 'Paused' not in text
    assert 'The match continues while this menu is open.' in text
    assert 'Multiplayer → Rejoin last room' in text
    before = match.world.tick
    wait_for(game, partner, lambda: match.world.tick >= before + 4)
    for key in ('n', 'f5', 'f9'):
        press(game, key)
        assert game.scene is menu and match.session.ready
    press(game, 's')
    assert isinstance(game.scene, SettingsScene)
    before = match.world.tick
    wait_for(game, partner, lambda: match.world.tick >= before + 4)
    press(game, 'escape')
    assert game.scene is menu
    press(game, 'escape')
    assert game.scene is match and match.session.ready
    press(game, 'f10')
    press(game, 't')
    assert isinstance(game.scene, TitleScene) and match.session.closed
    wait_for(game, partner, lambda: not partner.ready)
    press(game, 'm')
    rejoin = next(button for button in game.scene.ui.walk()
                  if isinstance(button, Button) and str(button.text).startswith('Rejoin last room'))
    x, y, width, height = rejoin.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    wait_for(game, partner, lambda: isinstance(game.scene, NetworkGameScene) and partner.ready)
    assert game.scene.session.room == room and game.scene.human == match.human


@pytest.mark.parametrize('winner', [0, 1])
def test_network_result_has_no_solo_rematch_and_escape_leaves(tmp_path, winner):
    """An authoritative victory or defeat ends at the title, never a new local match."""
    from saga2d import MatchClient, MatchHost
    from tests.warband.test_multiplayer import converge
    from warband.model import World
    from warband.multiplayer import WarbandMatch
    from warband.rules import Terrain, UnitType

    match = WarbandMatch(3)
    match.world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    for player in match.world.players:
        player.human = True
    attacker = match.world.spawn_unit(winner, UnitType.FOOTMAN, (10.5, 10.5))
    victim = match.world.spawn_unit(1 - winner, UnitType.PEASANT, (11, 10.5))
    victim.hp = 1
    match.world.update_vision()
    host = MatchHost('warband-v1', match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband-v1', host.address, token='test')
    game = Game('network result', backend='mock', resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, client, lambda: client.ready)
        scene = NetworkGameScene(client)
        game.push(scene)
        game.tick(1 / 30)
        command = {'action': 'attack', 'args': [[attacker.id], victim.id]}
        (host if winner == 0 else client).submit(command)
        converge(host, client, lambda: bool(match.world.units[attacker.id].orders))
        match.step()
        assert match.world.winner == winner
        host.publish()
        converge(host, client, lambda: client.state['world']['winner'] == winner)
        game.tick(1 / 30)
        result = game.scene
        assert result is not scene
        assert buttons(game) == ['Back to title', 'Quit']
        text = '\n'.join(item['text'] for item in game.backend.texts)
        assert ('Victory!' if winner == 1 else 'Defeat') in text
        assert 'choose Multiplayer on the title screen' in text
        press(game, 'n')
        assert game.scene is result and not client.closed
        press(game, 'escape')
        assert isinstance(game.scene, TitleScene) and client.closed
    finally:
        game.close()
        client.close()
        host.close()
