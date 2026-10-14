"""Network observers watch real rooms read-only: whole map, no seat, no writes.

LAN tests run on localhost sockets like the other multiplayer tests.  Online
tests ride a real room server, so they are slow: a hosted round trip takes
whole seconds, and there is no faster honest way to watch one.
"""
import json
import time

import pytest

from saga2d import CommandError, Game, MatchClient, MatchHost
from saga2d.testing.online import server_fixture

server_url = server_fixture('warband.online.authority:ONLINE')


def converge(*peers, until):
    """Poll every peer until *until* holds: asserting a state means waiting for its owner too."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        for peer in peers:
            peer.poll()
        if until():
            return
        time.sleep(.001)
    raise AssertionError('network observers did not converge')


def lan_host(match):
    """A LAN host of *match* with watching registered."""
    return MatchHost('warband-v2', match.apply, match.snapshot, address=('127.0.0.1', 0),
                     token='watch', observer_snapshot=match.observer_snapshot)


def test_observer_sees_the_whole_map_the_guest_is_filtered():
    """An observer holds no seat and sees every unit; the guest sees only its own."""
    from warband.online.authority import WarbandMatch
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    try:
        assert watcher.observer and watcher.player is None
        converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
        guest_ids = {u['id'] for u in guest.state['world']['units']}
        watch_ids = {u['id'] for u in watcher.state['world']['units']}
        assert watch_ids == {u.id for u in match.world.units.values()}
        assert guest_ids < watch_ids, "the guest's fog must hide something the watcher sees"
        from warband.online.authority import NO_DICE
        assert watcher.state['world']['rng'] == json.loads(json.dumps(NO_DICE))
    finally:
        watcher.close()
        guest.close()
        host.close()


def test_observe_is_refused_where_the_host_has_no_hook():
    """A host from before observing answers the handshake with an explicit refusal."""
    from warband.online.authority import WarbandMatch
    match = WarbandMatch(seed=3)
    host = MatchHost('warband-v2', match.apply, match.snapshot, address=('127.0.0.1', 0), token='plain')
    watcher = MatchClient('warband-v2', host.address, token='plain', observer=True)
    try:
        converge(host, watcher, until=lambda: watcher.error)
        assert watcher.error == 'This match does not support observing.'
        assert not watcher.ready and watcher.state is None
    finally:
        watcher.close()
        host.close()


def test_observer_orders_are_refused_on_the_wire_and_off_it():
    """Submitting raises locally; a forged raw command frame earns a server error, never orders."""
    import socket
    import struct

    from warband.online.authority import WarbandMatch
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    try:
        converge(host, watcher, until=lambda: host.observer_count == 1)
        with pytest.raises(CommandError):
            watcher.submit({'action': 'move', 'args': [[1], [2., 2.]], 'kwargs': {}})
        raw = socket.create_connection(host.address, timeout=5)
        try:
            hello = json.dumps({'type': 'observe', 'protocol': 1, 'game': 'warband-v2',
                                'token': 'watch'}).encode()
            raw.sendall(struct.pack('!I', len(hello)) + hello)
            converge(host, until=lambda: host.observer_count == 2)
            unit = match.world.player_units(0)[0]
            forged = json.dumps({'type': 'command',
                                 'command': {'action': 'move', 'args': [[unit.id], [2., 2.]], 'kwargs': {}}}).encode()
            raw.sendall(struct.pack('!I', len(forged)) + forged)
            answer = b''
            raw.settimeout(.2)
            deadline = time.monotonic() + 5
            while b'Observers cannot submit orders.' not in answer and time.monotonic() < deadline:
                host.poll()
                try:
                    while True:
                        chunk = raw.recv(4096)
                        if not chunk:
                            break
                        answer += chunk
                except (OSError, TimeoutError):
                    pass
            assert b'Observers cannot submit orders.' in answer
            assert not match.world.units[unit.id].orders
        finally:
            raw.close()
    finally:
        watcher.close()
        host.close()


def buttons(game):
    from saga2d import Button
    return [button.text for button in game.scene.ui.walk() if isinstance(button, Button)]


def labels(game):
    from saga2d import Label
    return [label.text() if callable(getattr(label, 'text', None)) else label.text
            for label in game.scene.ui.walk() if isinstance(label, Label)]


def watched_scene(game, watcher):
    """A live observer scene on *game*: the session holds the seat, never the scene."""
    from warband.ui.multiplayer import NetworkObserverScene
    scene = NetworkObserverScene(watcher)
    assert scene.session.player is None
    game.push(scene)
    return scene


def test_observer_scene_watches_without_authority(tmp_path):
    """The scene inspects every side, refuses orders, and keeps no saves or brains."""
    from warband.online.authority import WarbandMatch
    from warband.sim.model import RuleError
    from warband.ui.multiplayer import NetworkObserverEndScene, NetworkObserverMenuScene
    from warband.ui.style import build_theme
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    game = Game('observer scene', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
        scene = watched_scene(game, watcher)
        game.tick(1 / 30)
        assert scene.viewed == 0 and scene.human == 0
        scene.watch_next()
        assert (scene.viewed, scene.human) == (1, 1)
        unit = next(u for u in scene.world.units.values() if u.player == 0)
        scene.select([unit.id])
        assert scene.selection == [unit.id]
        with pytest.raises(RuleError):
            scene.order('move', [unit.id], (2., 2.))
        assert scene.attempt('move', [unit.id], (2., 2.)) is False
        assert scene.tutorial is None and scene.record.replay is None
        game.backend.inject_key('f10')
        game.tick(1 / 30)
        assert isinstance(game.scene, NetworkObserverMenuScene)
        assert 'Stop watching' in [b.text for b in game.scene.ui.walk() if hasattr(b, 'text')]
        game.backend.inject_key('escape')
        game.tick(1 / 30)
        assert game.scene is scene
        match.world.resign(1)
        for _ in range(4):
            match.step()
        host.publish()
        converge(host, guest, watcher,
                 until=lambda: watcher.state['world']['winner'] == 0)
        deadline = time.monotonic() + 5
        while not isinstance(game.scene, NetworkObserverEndScene) and time.monotonic() < deadline:
            host.poll()
            guest.poll()
            game.tick(1 / 30)
            time.sleep(.01)
        end = game.scene
        assert isinstance(end, NetworkObserverEndScene)
        titles = [getattr(w, 'text', '') for w in end.ui.walk()]
        assert any(f"{match.world.players[0].name} wins" in t for t in titles), titles
        assert not any('Victory!' in t or 'Defeat' in t or ' AI ' in t for t in titles)
    finally:
        game.close()
        watcher.close()
        guest.close()
        host.close()


def test_observer_disconnect_leaves_the_match_running():
    """Closing a watcher changes neither readiness nor the host's clock."""
    from warband.online.authority import WarbandMatch
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    try:
        converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
        watcher.close()
        converge(host, guest, until=lambda: host.observer_count == 0)
        assert host.ready
        for _ in range(4):
            match.step()
        host.publish()
        converge(host, guest, until=lambda: guest.state['world']['tick'] == match.world.tick)
    finally:
        watcher.close()
        guest.close()
        host.close()


def test_background_never_pauses_the_watched_room(tmp_path):
    """Backgrounding leaves the watcher live: snapshots keep landing, nothing says Paused."""
    from warband.online.authority import WarbandMatch
    from warband.ui.style import build_theme
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    game = Game('observer background', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
        scene = watched_scene(game, watcher)
        game.tick(1 / 30)
        scene.on_background()
        game.tick(1 / 30)
        assert not scene.execution.paused
        for _ in range(4):
            match.step()
        host.publish()
        converge(host, guest, watcher,
                 until=lambda: watcher.state['world']['tick'] == match.world.tick)
        game.tick(1 / 30)
        assert not scene.execution.paused and scene.world.tick == match.world.tick
        scene.on_foreground()
        game.tick(1 / 30)
        assert not scene.execution.paused
    finally:
        game.close()
        watcher.close()
        guest.close()
        host.close()


def test_snapshot_watcher_names_observed_activity_not_idleness(tmp_path):
    """Stripped orders show no Idle counts: the button hides, Tab says why, the card shows state."""
    import re

    from warband.online.authority import WarbandMatch
    from warband.ui.style import build_theme
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    game = Game('observer activity', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
        from warband.sim.rules import UnitType
        world = match.world
        marcher = world.spawn_unit(0, UnitType.FOOTMAN, world.player_units(0)[0].pos)
        world.move([marcher.id], (world.width - 3.5, world.height - 3.5))
        hand = next(u for u in world.player_units(0) if u.is_worker and not u.hidden)
        world.harvest([hand.id], world.mines()[0].id)
        for _ in range(4):
            match.step()
        host.publish()
        scene = watched_scene(game, watcher)
        converge(host, guest, watcher,
                 until=lambda: watcher.state['world']['tick'] == match.world.tick)
        game.tick(1 / 30)
        game.tick(1 / 30)
        assert not scene.idle_button.visible
        game.backend.inject_key('tab')
        game.tick(1 / 30)
        assert 'unavailable while observing' in scene.status
        scene.select([marcher.id])
        game.tick(1 / 30)
        drawn = [t['text'] for t in game.backend.texts]
        assert 'Move' in drawn, [t for t in drawn if len(t) < 24]
        assert not any(re.fullmatch(r'Idle \d+', t) for t in drawn)
    finally:
        game.close()
        watcher.close()
        guest.close()
        host.close()


def test_observer_lobby_tracks_refusal_and_disconnect(tmp_path):
    """A refused or dropped watch stays in the lobby saying so — and writes nothing anywhere."""
    from types import SimpleNamespace

    from warband.ui.multiplayer import WarbandLobby
    from warband.ui.style import build_theme

    def stub(**kwargs):
        session = SimpleNamespace(observer=True, online=True, player=None, state=None, revision=0,
                                  ready=False, error='', closed=False, observer_count=0, incompatible=False,
                                  endpoint='wss://lint.invalid/play', room='AB12', seats=2, present=0,
                                  players=[], resume_token='', player_token='')
        session.poll = lambda: None
        session.close = lambda: setattr(session, 'closed', True)
        for key, value in kwargs.items():
            setattr(session, key, value)
        return session

    game = Game('observer lobby', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        game.push(WarbandLobby(stub(incompatible=True), lambda connection: None))
        game.tick(1 / 30)
        assert 'Open download page' in buttons(game)
        game.pop()
        refused = stub(closed=True, error='This match does not support observing.')
        game.push(WarbandLobby(refused, lambda connection: None))
        game.tick(1 / 30)
        shown = labels(game)
        assert any('Could not connect' in t for t in shown if isinstance(t, str))
        assert any('does not support observing' in t for t in shown if isinstance(t, str))
        assert isinstance(game.scene, WarbandLobby), "a refused watch transfers nowhere"
        gone = stub(closed=True, error='Connection timed out.')
        game.push(WarbandLobby(gone, lambda connection: None))
        game.tick(1 / 30)
        assert any('Could not connect' in t for t in labels(game) if isinstance(t, str))
        assert not (tmp_path / 'saves' / 'online-room.json').exists()
        assert not (tmp_path / 'saves' / 'online-identity.json').exists()
    finally:
        game.close()


def test_guest_joins_while_an_observer_waits():
    """An early watcher sees the lobby clear when the guest arrives, all on the same states."""
    from warband.online.authority import WarbandMatch
    from warband.sim.model import World
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    watcher = MatchClient('warband-v2', host.address, token='watch', observer=True)
    try:
        converge(host, watcher, until=lambda: host.observer_count == 1)
        assert not watcher.ready
        guest = MatchClient('warband-v2', host.address, token='watch')
        try:
            converge(host, guest, watcher, until=lambda: guest.ready and watcher.ready)
            seen = World.from_dict(watcher.state['world'])
            assert {u.id for u in seen.units.values()} == {u.id for u in match.world.units.values()}
        finally:
            guest.close()
    finally:
        watcher.close()
        host.close()


def test_observe_needs_no_identity_and_writes_none(tmp_path):
    """A corrupted identity record neither blocks nor changes watching; files stay byte-identical."""
    from saga2d import Game
    from warband.online.authority import WarbandMatch
    from warband.ui.multiplayer import MatchSetupMenu, NetworkObserverScene, WarbandLobby
    from warband.ui.style import build_theme
    match = WarbandMatch(seed=3)
    host = lan_host(match)
    guest = MatchClient('warband-v2', host.address, token='watch')
    game = Game('observe identity', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, guest, until=lambda: guest.ready)
        data = tmp_path / 'saves'
        data.mkdir(parents=True, exist_ok=True)
        (data / 'online-identity.json').write_text('{"tokens": {"sentinel": "keep"}}')
        (data / 'online-room.json').write_text('{"game_id": "sentinel", "room": "S1", "resume_token": "T1"}')
        (data / 'online-memory.json').write_text('{"sentinel": []}')
        before = {name: (data / name).read_bytes() for name in
                  ('online-identity.json', 'online-room.json', 'online-memory.json')}
        menu = MatchSetupMenu()
        game.push(menu)
        game.tick(1 / 30)
        menu.set_mode('lan')
        game.tick(1 / 30)
        menu.fields = ['127.0.0.1', str(host.address[1]), 'watch']
        observe = next(b for b in menu.ui.walk() if getattr(b, 'text', '') == 'Observe room')
        x, y, w, h = observe.bounds
        game.backend.inject_click(x + w / 2, y + h / 2)
        game.tick(1 / 30)
        assert isinstance(game.scene, WarbandLobby)
        deadline = time.monotonic() + 5
        while not isinstance(game.scene, NetworkObserverScene) and time.monotonic() < deadline:
            game.tick(1 / 30)
            host.poll()
            guest.poll()
            time.sleep(.01)
        assert isinstance(game.scene, NetworkObserverScene)
        for _ in range(30):
            game.tick(1 / 30)
            host.poll()
            guest.poll()
        assert {name: (data / name).read_bytes() for name in before} == before
        (data / 'online-identity.json').write_text('corrupted{{{')
        menu2 = MatchSetupMenu()
        game.push(menu2)
        game.tick(1 / 30)
        menu2.set_mode('lan')
        menu2.fields = ['127.0.0.1', str(host.address[1]), 'watch']
        menu2.observe()
        game.tick(1 / 30)
        assert isinstance(game.scene, WarbandLobby), "a damaged record must not refuse watching"
    finally:
        game.close()
        guest.close()
        host.close()


def drive(game, *peers, until, timeout=30):
    """Tick the scene while every peer polls: a watched state belongs to whoever reports it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        game.tick(1 / 30)
        for peer in peers:
            peer.poll()
        if until():
            return
        time.sleep(.01)
    raise AssertionError(f'online observers did not converge: '
                         f'{[(peer.player, peer.ready, peer.closed, peer.error) for peer in peers]}')


def observe_room(game, code):
    """Press the menu's own Observe room button for *code*: the public watching path."""
    from warband.ui.multiplayer import MatchSetupMenu, WarbandLobby
    menu = MatchSetupMenu()
    game.push(menu)
    game.tick(1 / 30)
    menu.fields[2] = code
    game.tick(1 / 30)
    observe = next(b for b in menu.ui.walk() if getattr(b, 'text', '') == 'Observe room')
    x, y, w, h = observe.bounds
    game.backend.inject_click(x + w / 2, y + h / 2)
    game.tick(1 / 30)
    assert isinstance(game.scene, WarbandLobby)
    return menu


@pytest.mark.slow
def test_online_observe_follows_a_full_room_to_its_winner(server_url, tmp_path, monkeypatch):
    """Watching joins a full room from the menu, outlives the followed seat, and names the winner."""
    from saga2d.online import OnlineClient
    from warband.ui.multiplayer import NetworkObserverEndScene, NetworkObserverScene
    from warband.ui.style import build_theme
    monkeypatch.setenv('SAGA2D_SERVER_URL', server_url)
    host = OnlineClient('warband-v2', endpoint=server_url,
                        options={'seed': 3, 'width': 48, 'height': 40, 'players': 3})
    converge(host, until=lambda: bool(host.room))
    guests = [OnlineClient('warband-v2', endpoint=server_url, room=host.room) for _ in range(2)]
    game = Game('online observe', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, *guests, until=lambda: all(p.ready for p in (host, *guests)))
        # Connections may arrive in either order: test the seats the server assigned.
        guests.sort(key=lambda peer: peer.player)
        observe_room(game, host.room)
        drive(game, host, *guests, until=lambda: isinstance(game.scene, NetworkObserverScene))
        scene = game.scene
        assert scene.session.player is None and scene.session.observer
        guest_ids = {u['id'] for u in guests[0].state['world']['units']}
        watch_ids = {u['id'] for u in scene.session.state['world']['units']}
        assert guest_ids < watch_ids, "the watcher sees what no seat's fog may show"
        token, room = guests[1].resume_token, guests[1].room
        guests[1].close()
        drive(game, host, guests[0], until=lambda: not scene.session.ready)
        game.tick(1 / 30)
        assert 'waiting' in scene.status, "a missing seat pauses the room the watcher sees"
        guests[1] = OnlineClient('warband-v2', endpoint=server_url, room=room, resume_token=token)
        drive(game, host, *guests, until=lambda: all(p.ready for p in (host, *guests)))
        host.submit({'action': 'resign', 'args': [0]})
        drive(game, host, *guests, until=lambda: not scene.world.players[0].alive)
        assert scene.world.winner is None and game.scene is scene, "the watched fall ends no watching"
        scene.watch_next()
        assert scene.viewed == 1
        guests[0].submit({'action': 'resign', 'args': [1]})
        drive(game, host, *guests, until=lambda: isinstance(game.scene, NetworkObserverEndScene))
        titles = [getattr(w, 'text', '') for w in game.scene.ui.walk()]
        assert any(f"{scene.world.players[2].name} wins" in t for t in titles), titles
        assert not any('Victory!' in t or 'Defeat' in t or ' AI ' in t for t in titles)
        observe_room(game, host.room)
        drive(game, host, *guests, until=lambda: isinstance(game.scene, NetworkObserverEndScene),
              timeout=30)
    finally:
        game.close()
        for peer in guests:
            peer.close()
        host.close()


@pytest.mark.slow
def test_online_observe_leaves_the_players_files_alone(server_url, tmp_path, monkeypatch):
    """Watching another room changes neither identity, last room, nor fog memory: byte for byte."""
    from saga2d.online import OnlineClient
    from warband.ui.multiplayer import NetworkObserverScene
    from warband.ui.style import build_theme
    monkeypatch.setenv('SAGA2D_SERVER_URL', server_url)
    host = OnlineClient('warband-v2', endpoint=server_url, options={'seed': 3, 'width': 48, 'height': 40})
    converge(host, until=lambda: bool(host.room))
    guest = OnlineClient('warband-v2', endpoint=server_url, room=host.room)
    game = Game('online observe files', backend='mock', theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, guest, until=lambda: guest.ready)
        data = tmp_path / 'saves'
        data.mkdir(parents=True, exist_ok=True)
        (data / 'online-identity.json').write_text(
            '{"tokens": {"https://elsewhere.example": "SECRET"}, "profiles": {}}')
        (data / 'online-room.json').write_text(
            '{"game_id": "warband-v2", "endpoint": "https://elsewhere.example", '
            '"room": "ELSEWHERE", "resume_token": "PRIVATE"}')
        (data / 'online-memory.json').write_text('{"room": "ELSEWHERE", "seen": {}}')
        before = {name: (data / name).read_bytes() for name in
                  ('online-identity.json', 'online-room.json', 'online-memory.json')}
        observe_room(game, host.room)
        drive(game, host, guest, until=lambda: isinstance(game.scene, NetworkObserverScene))
        for _ in range(60):
            game.tick(1 / 30)
            host.poll()
            guest.poll()
        assert {name: (data / name).read_bytes() for name in before} == before
    finally:
        game.close()
        guest.close()
        host.close()
