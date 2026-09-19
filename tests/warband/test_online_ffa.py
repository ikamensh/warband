"""Three and four humans in one online room (WB-012), through the production room server process.

A room has the seats its match has players; each seat is sent its own view of the match (WB-011); a player who
resigns leaves their buildings standing, abandoned, and the others fight on until one is left.  A seat still in
the match pauses the room when it leaves; one that is out may go.
"""
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys

from websockets.sync.client import connect

import pytest

from saga2d.testing.online import command, handshake, receive, server_fixture

GAME = 'warband-v2'
server_url = server_fixture('warband.online.authority:ONLINE')


@contextmanager
def room(url: str, players: int, **options):
    """*players* connections, the first creating a room of that many seats on a Medium map and the rest joining."""
    with ExitStack() as stack:
        sockets = [stack.enter_context(connect(url, proxy=None, max_queue=None)) for _ in range(players)]
        welcome = handshake(sockets[0], game=GAME, seats=4,
                            options={'seed': 5, 'width': 64, 'height': 48, 'players': players, **options})
        seats = [welcome] + [handshake(socket, 'join', game=GAME, room=welcome['room'], seats=4) for socket in sockets[1:]]
        yield sockets, seats


def state(socket, predicate=lambda message: True) -> dict:
    return receive(socket, predicate=predicate)


def world(socket, predicate=lambda message: True) -> dict:
    return state(socket, predicate)['state']['world']


def test_three_humans_play_one_room_each_seeing_its_own(server_url):
    with room(server_url, 3) as (sockets, seats):
        assert [seat['player'] for seat in seats] == [0, 1, 2] and all(seat['seats'] == 3 for seat in seats)
        ready = [state(socket, lambda message: message['ready']) for socket in sockets]
        for seat, message in enumerate(ready):
            seen = message['state']['world']
            assert len(seen['players']) == 3 and message['player'] == seat
            assert {u['player'] for u in seen['units']} == {seat}, "a seat was sent another's workers at home"
        own = next(u for u in ready[2]['state']['world']['units'] if u['player'] == 2)
        command(sockets[2], {'action': 'move', 'args': [[own['id']], [own['x'] + 2, own['y']]]})
        moved = world(sockets[2], lambda message: any(u['id'] == own['id'] and abs(u['x'] - own['x']) > .5
                                                      for u in message['state']['world']['units']))
        assert moved['winner'] is None


@pytest.mark.slow
def test_a_resignation_in_four_leaves_three_fighting_and_the_last_two_decide_it(server_url):
    """Four clients play until three have resigned, most of a second: the slow tier."""
    with room(server_url, 4) as (sockets, seats):
        for socket in sockets:
            state(socket, lambda message: message['ready'])
        command(sockets[3], {'action': 'resign', 'args': [3]})
        out = world(sockets[3], lambda message: not message['state']['world']['players'][3]['alive'])
        assert out['winner'] is None
        assert all(b['abandoned'] for b in out['buildings'] if b['player'] == 3), "the resigned player's buildings fell"
        assert any(b['player'] == 3 for b in out['buildings']), "the resigned player's buildings were removed"
        sockets[3].close()  # out of the match: leaving pauses nobody
        going_on = state(sockets[0], lambda message: message['present'] == 3)
        assert going_on['ready']
        tick = going_on['state']['world']['tick']
        assert state(sockets[0], lambda message: message['state']['world']['tick'] > tick + 10)['ready']
        command(sockets[2], {'action': 'resign', 'args': [2]})
        two_left = world(sockets[0], lambda message: not message['state']['world']['players'][2]['alive'])
        assert two_left['winner'] is None, "the match was decided with two players still in it"
        command(sockets[1], {'action': 'resign', 'args': [1]})
        decided = world(sockets[0], lambda message: message['state']['world']['winner'] is not None)
        assert decided['winner'] == 0


def test_resigning_someone_else_is_refused(server_url):
    with room(server_url, 3) as (sockets, seats):
        for socket in sockets:
            state(socket, lambda message: message['ready'])
        command(sockets[1], {'action': 'resign', 'args': [2]})
        refused = json.loads(sockets[1].recv(timeout=5))
        while refused['type'] != 'error':
            refused = json.loads(sockets[1].recv(timeout=5))
        assert 'only resign yourself' in refused['error']
        assert world(sockets[2])['players'][2]['alive']


def test_a_seat_still_in_the_match_that_leaves_pauses_the_room_until_it_rejoins(server_url):
    with room(server_url, 3) as (sockets, seats):
        for socket in sockets:
            state(socket, lambda message: message['ready'])
        sockets[1].close()
        paused = state(sockets[0], lambda message: not message['ready'])
        assert paused['present'] == 2
        with connect(server_url, proxy=None, max_queue=None) as back:
            returned = handshake(back, 'resume', game=GAME, room=seats[0]['room'], resume_token=seats[1]['resume_token'], seats=4)
            assert returned['player'] == 1
            assert state(sockets[0], lambda message: message['ready'])['present'] == 3


def test_a_client_from_before_larger_rooms_cannot_join_one(server_url):
    with room(server_url, 3) as (sockets, seats), connect(server_url, proxy=None) as old:
        old.send(json.dumps({'type': 'join', 'protocol': 1, 'game': GAME, 'room': seats[0]['room']}))
        refused = json.loads(old.recv(timeout=5))
        assert refused['type'] == 'reject' and refused.get('reason') == 'incompatible'
        assert 'Update your game client' in refused['error']


@pytest.mark.slow
def test_the_online_ai_takes_a_seat_in_a_room_of_three(server_url):
    """The headless client plays for seconds in a room of three: the slow tier."""
    with ExitStack() as stack:
        human = stack.enter_context(connect(server_url, proxy=None, max_queue=None))
        welcome = handshake(human, game=GAME, seats=4, options={'seed': 5, 'width': 64, 'height': 48, 'players': 3})
        bot = subprocess.Popen(
            [sys.executable, '-m', 'warband.online.online_ai', '--server', server_url, '--room', welcome['room'],
             '--difficulty', 'hard', '--duration', '2.5', '--report-every', '0.25'],
            cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, 'DISPLAY': '', 'PYTHONUNBUFFERED': '1'})
        try:
            other = stack.enter_context(connect(server_url, proxy=None, max_queue=None))
            state(human, lambda message: message['present'] >= 2)
            handshake(other, 'join', game=GAME, room=welcome['room'], seats=4)
            state(human, lambda message: message['ready'])
            output, errors = bot.communicate(timeout=30)
        finally:
            if bot.poll() is None:
                bot.kill()
        assert bot.returncode == 0, errors[-2000:]
        evidence = [json.loads(line) for line in output.splitlines()]
        assert evidence[0]['event'] == 'joined' and evidence[0]['player'] == 1
        assert any(row['event'] == 'order_submitted' for row in evidence)


def test_resigning_from_the_match_menu_asks_first_then_the_player_may_watch_the_rest(tmp_path):
    import sys as _sys

    from saga2d import Game
    from warband.online.authority import WarbandMatch
    from warband.ui.multiplayer import NetworkGameScene, NetworkMenuScene, NetworkResultScene, ResignScene
    from warband.ui.style import build_theme

    _sys.path.insert(0, str(Path(__file__).parent))
    from test_online_motion import QUIET, Seat

    match = WarbandMatch(seed=5, width=64, height=48, players=3)
    seat = Seat(match, 0)
    game = Game("Warband FFA", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")

    def press(key: str) -> None:
        game.backend.inject_key(key)
        game.tick(1 / 60)

    def texts() -> str:
        return "\n".join(t["text"] for t in game.backend.texts)

    try:
        scene = NetworkGameScene(seat, settings=QUIET)
        game.push(scene)
        game.tick(1 / 60)
        press("f10")
        assert isinstance(game.scene, NetworkMenuScene) and "Resign" in texts()
        press("r")
        assert isinstance(game.scene, ResignScene) and "the others fight on" in texts()
        press("escape")
        assert isinstance(game.scene, NetworkMenuScene) and match.world.players[0].alive, "Escape resigned anyway"
        press("r")
        press("return")
        assert not match.world.players[0].alive and match.world.winner is None
        match.step()
        seat.publish()
        for _ in range(3):
            game.tick(1 / 60)
        assert isinstance(game.scene, NetworkResultScene) and "You are out — the others fight on" in texts()
        press("w")
        assert game.scene is scene, "Watch did not return to the match"
    finally:
        game.close()
