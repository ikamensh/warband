"""Rated rooms and own-race joining through the production server process.

Each test proves one public behaviour over real WebSockets against
``running_server('warband.online.authority:ONLINE')``: a ranked duel settles
ratings exactly once, larger rooms conserve points, casual rooms never rate,
reconnect grace never invents a result, and a joining seat's race choice
reaches only its own seat.  The server tests assert on hellos and states
only, never the database.  Two fast checks drive the public GameSpec
callbacks (create, configure, checkpoint, result, rated, forfeit) directly
for guards the wire cannot reach on its own — bad seats and shapes, late
choices, eligibility, checkpoint shape — with no private methods and no
sockets.  Account tokens are never printed.

Every server test here is slow: it starts a real server subprocess, speaks the
real WebSocket protocol, and waits out the server's real 50 ms clock.  The two
contract checks at the end are fast: small local maps through the public
GameSpec callbacks, no process, no sockets.
"""
import json
import time

import pytest
from websockets.sync.client import connect

from saga2d.testing.online import command, handshake, receive, running_server

GAME = 'warband-v2'
SPEC = 'warband.online.authority:ONLINE'


def duel_options(**extra):
    """A small two-seat map; resigned at once, decided at once."""
    return {'seed': 3, 'width': 48, 'height': 40, **extra}


def ffa_options(seats, **extra):
    """A small valid map for three or four seats (seed 5 deals one)."""
    return {'seed': 5, 'width': 64, 'height': 48, 'players': seats, **extra}


def fresh_profile(welcome):
    """A hello for a brand-new account: 1500, no games, and its own identity."""
    assert welcome['rating'] == {'player_id': welcome['player_id'], 'name': 'Commander',
                                 'rating': 1500.0, 'games': 0, 'wins': 0, 'losses': 0}
    return welcome


def settled_state(socket):
    """The first state carrying the server's settled result receipt."""
    return receive(socket, predicate=lambda message: message['result'] is not None)


def states_for(socket, seconds):
    """The states arriving within *seconds*; raw frames, so nothing aborts the wait."""
    states = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            raw = socket.recv(timeout=max(0.1, deadline - time.monotonic()))
        except TimeoutError:
            break
        message = json.loads(raw)
        if message['type'] == 'state':
            states.append(message)
    return states


def world_of(state, seat):
    return state['state']['world']


@pytest.mark.slow
def test_rated_duel_resign_settles_winner_and_rating_receipt():
    """A real ranked duel: the loser resigns through the validated order, the authority names the
    winner, and both seats get the same receipt with conserved ratings.  Needs the server process,
    two sockets and the settle publish, so the slow tier."""
    with running_server(SPEC) as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            welcome = fresh_profile(handshake(host, game=GAME, options=duel_options(), rated=True))
            assert welcome['rated'] and welcome['match_id']
            guest_welcome = fresh_profile(handshake(guest, 'join', game=GAME, room=welcome['room']))
            assert guest_welcome['player_id'] != welcome['player_id']
            receive(host, predicate=lambda message: message['ready'])
            receive(guest, predicate=lambda message: message['ready'])
            command(guest, {'action': 'resign', 'args': [1]})
            decided = settled_state(host)
            assert settled_state(guest)['result'] == decided['result']
            result = decided['result']
            assert result['match_id'] == welcome['match_id'] and result['winner'] == 0
            ratings = {entry['player_id']: entry for entry in result['ratings']}
            host_entry, guest_entry = ratings[welcome['player_id']], ratings[guest_welcome['player_id']]
            assert (host_entry['before'], guest_entry['before']) == (1500.0, 1500.0)
            assert (host_entry['after'], guest_entry['after']) == (1516.0, 1484.0)
            assert host_entry['delta'] + guest_entry['delta'] == pytest.approx(0.0)
            assert (host_entry['games'], host_entry['wins'], host_entry['losses']) == (1, 1, 0)
            assert (guest_entry['games'], guest_entry['wins'], guest_entry['losses']) == (1, 0, 1)


@pytest.mark.slow
@pytest.mark.parametrize('seats', [3, 4])
def test_rated_ffa_points_conserved_and_dead_seats_may_leave(seats):
    """Every other seat resigns down to one: exchanged points sum to zero and each dead seat's
    socket may go while the survivors finish.  Every handshake declares the four-seat client
    capability the room needs, or the server refuses the larger room.  Up to four sockets on a
    64x48 map through the server clock: slow tier."""
    with running_server(SPEC) as (url, _process):
        with connect(url, proxy=None) as first:
            welcome = handshake(first, game=GAME, seats=4, options=ffa_options(seats), rated=True)
            rest = [connect(url, proxy=None) for _ in range(seats - 1)]
            try:
                for seat, socket in enumerate(rest, start=1):
                    handshake(socket, 'join', game=GAME, seats=4, room=welcome['room'])
                receive(first, predicate=lambda message: message['ready'])
                for seat, socket in enumerate(rest, start=1):
                    if seat < seats - 1:
                        with socket:
                            command(socket, {'action': 'resign', 'args': [seat]})
                            receive(first, predicate=lambda message:
                                    not world_of(message, 0)['players'][seat]['alive'])
                        # The dead seat left; the survivors play on.
                    else:
                        command(socket, {'action': 'resign', 'args': [seat]})
                result = settled_state(first)['result']
                assert settled_state(rest[-1])['result'] == result
            finally:
                for socket in rest:
                    socket.close()
            assert result['winner'] == 0
            deltas = [entry['delta'] for entry in result['ratings']]
            assert sum(deltas) == pytest.approx(0.0)
            assert all((entry['games'], entry['wins'] + entry['losses']) == (1, 1)
                       for entry in result['ratings'])


@pytest.mark.slow
def test_rated_result_exactly_once_across_resume_and_restart(tmp_path):
    """The receipt is identical after both seats resume and after the server restarts on the same
    state directory, and both accounts show exactly one game.  Two server processes plus resumes:
    the slow tier."""
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            guest_welcome = handshake(guest, 'join', game=GAME, room=welcome['room'])
            receive(host, predicate=lambda message: message['ready'])
            command(guest, {'action': 'resign', 'args': [1]})
            result = settled_state(host)['result']
            host_token, guest_token = welcome['resume_token'], guest_welcome['resume_token']
            room = welcome['room']
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            resumed = handshake(host, 'resume', game=GAME, room=room, resume_token=host_token)
            handshake(guest, 'resume', game=GAME, room=room, resume_token=guest_token)
            assert settled_state(host)['result'] == result
            assert settled_state(guest)['result'] == result
            assert resumed['rating']['games'] == 1
            assert settled_state(host)['rated'] and settled_state(host)['match_id'] == result['match_id']


@pytest.mark.slow
def test_casual_match_names_winner_but_rates_nothing():
    """Without rated on create the loser still loses, but no receipt is issued and both accounts
    stay unplayed.  A full duel plus a resume round-trip on the server clock: the slow tier."""
    with running_server(SPEC) as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            welcome = fresh_profile(handshake(host, game=GAME, options=duel_options()))
            assert not welcome['rated']
            guest_welcome = handshake(guest, 'join', game=GAME, room=welcome['room'])
            receive(host, predicate=lambda message: message['ready'])
            command(guest, {'action': 'resign', 'args': [1]})
            decided = receive(host, predicate=lambda message:
                              world_of(message, 0)['winner'] == 0)
            assert decided['result'] is None
            resume = handshake(host, 'resume', game=GAME, room=welcome['room'],
                               resume_token=welcome['resume_token'])
            assert resume['rating']['games'] == 0
            assert guest_welcome['player_id'] != welcome['player_id']


@pytest.mark.slow
def test_grace_reconnect_before_deadline_preserves_match_without_result():
    """An abruptly dropped loser who returns inside a short configured grace finds no invented
    result and the match plays on to a real one.  Live sockets with clock waits: the slow tier."""
    with running_server(SPEC, arguments=('--rated-grace', '8')) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            with connect(url, proxy=None) as guest:
                guest_welcome = handshake(guest, 'join', game=GAME, room=welcome['room'])
                receive(host, predicate=lambda message: message['ready'])
                guest_token = guest_welcome['resume_token']
            # The socket is gone without a goodbye; the host watches states well inside grace.
            watched = states_for(host, 3)
            assert watched, "the server kept the room's clock running for the connected seat"
            assert all(state['result'] is None for state in watched)
            with connect(url, proxy=None) as back:
                handshake(back, 'resume', game=GAME, room=welcome['room'], resume_token=guest_token)
                resumed = receive(host, predicate=lambda message: message['ready'])
                assert resumed['result'] is None
                command(back, {'action': 'resign', 'args': [1]})
                assert settled_state(host)['result']['winner'] == 0


@pytest.mark.slow
def test_grace_expiry_forfeits_absent_loser():
    """A loser who stays gone past a short configured grace forfeits through the authority's own
    resign order: the winner is named and rated with nobody issuing orders.  A dropped socket
    plus a clock wait past grace: the slow tier."""
    with running_server(SPEC, arguments=('--rated-grace', '2')) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            with connect(url, proxy=None) as guest:
                handshake(guest, 'join', game=GAME, room=welcome['room'])
                receive(host, predicate=lambda message: message['ready'])
            result = settled_state(host)['result']
            assert result['match_id'] == welcome['match_id'] and result['winner'] == 0
            ratings = {entry['player_id']: entry for entry in result['ratings']}
            assert ratings[welcome['player_id']]['after'] == 1516.0
            assert all((entry['games'], entry['losses']) == (1, 1)
                       for entry in result['ratings'] if entry['player_id'] != welcome['player_id'])


@pytest.mark.slow
def test_both_offline_pauses_without_false_rating():
    """With nobody connected the rated clock stays paused past even a short grace: no forfeit, no
    result, and the match resumes to a real decision.  Two drops, a wait past grace, two resumes:
    the slow tier."""
    with running_server(SPEC, arguments=('--rated-grace', '2')) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            with connect(url, proxy=None) as guest:
                guest_welcome = handshake(guest, 'join', game=GAME, room=welcome['room'])
                receive(host, predicate=lambda message: message['ready'])
                host_token, guest_token = welcome['resume_token'], guest_welcome['resume_token']
                room = welcome['room']
        time.sleep(4)
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            handshake(host, 'resume', game=GAME, room=room, resume_token=host_token)
            handshake(guest, 'resume', game=GAME, room=room, resume_token=guest_token)
            resumed = receive(host, predicate=lambda message: message['ready'])
            assert resumed['result'] is None
            command(guest, {'action': 'resign', 'args': [1]})
            assert settled_state(host)['result']['winner'] == 0


@pytest.mark.slow
def test_invalid_guest_race_leaves_room_joinable():
    """A bad race choice rejects the join without claiming the seat; a clean join then plays.
    A rejected socket plus a real join round-trip: the slow tier."""
    with running_server(SPEC) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            receive(host)
            with connect(url, proxy=None) as bad:
                bad.send(json.dumps({'type': 'join', 'protocol': 1, 'game': GAME,
                                     'room': welcome['room'], 'player_options': {'race': 'gnome'}}))
                rejection = receive(bad, 'reject')
                assert 'race' in rejection['error'].lower()
            with connect(url, proxy=None) as guest:
                joined = handshake(guest, 'join', game=GAME, room=welcome['room'])
                assert joined['player'] == 1
                assert receive(host, predicate=lambda message: message['ready'])['ready']


@pytest.mark.slow
def test_guest_race_applies_alone_and_survives_restart(tmp_path):
    """The guest owns its chosen race, the creator keeps the drawn one, the ground is untouched,
    and the choice persists across a restart.  Two server processes on one state directory: slow."""
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            before = receive(host)
            creator_race = world_of(before, 0)['players'][0]['race']
            ground = world_of(before, 0)['terrain']
            with connect(url, proxy=None) as guest:
                joined = handshake(guest, 'join', game=GAME, room=welcome['room'],
                                   player_options={'race': 'orc'})
                assert joined['player'] == 1
                ready = receive(host, predicate=lambda message: message['ready'])
                players = world_of(ready, 0)['players']
                assert players[1]['race'] == 'orc'
                assert players[0]['race'] == creator_race
                assert world_of(ready, 0)['terrain'] == ground
                guest_token, room = joined['resume_token'], welcome['room']
                host_token = welcome['resume_token']
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            handshake(host, 'resume', game=GAME, room=room, resume_token=host_token)
            handshake(guest, 'resume', game=GAME, room=room, resume_token=guest_token)
            back = receive(host, predicate=lambda message: message['ready'])
            players = world_of(back, 0)['players']
            assert (players[0]['race'], players[1]['race']) == (creator_race, 'orc')


@pytest.mark.slow
def test_resume_ignores_race_options_once_underway():
    """Player options ride joins, never resumes: reconnecting mid-match with a race choice keeps
    the seat's race.  Needs ticks on the server clock plus a resume round-trip: the slow tier."""
    with running_server(SPEC) as (url, _process):
        with connect(url, proxy=None) as host:
            welcome = handshake(host, game=GAME, options=duel_options(), rated=True)
            with connect(url, proxy=None) as guest:
                joined = handshake(guest, 'join', game=GAME, room=welcome['room'],
                                   player_options={'race': 'orc'})
                assert world_of(receive(guest, predicate=lambda message: message['ready']),
                                1)['players'][1]['race'] == 'orc'
                running = receive(guest, predicate=lambda message:
                                  world_of(message, 1)['tick'] > 0)
                assert world_of(running, 1)['players'][1]['race'] == 'orc'
                guest_token = joined['resume_token']
            with connect(url, proxy=None) as back:
                handshake(back, 'resume', game=GAME, room=welcome['room'],
                          resume_token=guest_token, player_options={'race': 'human'})
                kept = receive(back, predicate=lambda message: message['ready'])
                assert world_of(kept, 1)['players'][1]['race'] == 'orc'


def test_configure_player_contract_without_sockets():
    """The option contract the wire cannot reach on its own: bad seats, shapes and late choices
    are refused before anything changes, and empty choices keep the drawn race.  Fast: one local
    map, no process, no sockets."""
    from saga2d import CommandError

    from warband.online.authority import ONLINE
    spec = ONLINE[GAME]
    match = spec.create(duel_options())
    drawn = [match.world.players[seat].race for seat in range(2)]
    spec.configure_player(match, 1, {})
    spec.configure_player(match, 0, {'race': None})
    assert [match.world.players[seat].race for seat in range(2)] == drawn
    for options in (['race'], 'orc', {'colour': 'red'}, {'race': 'gnome'}, {'race': 5}):
        with pytest.raises(CommandError):
            spec.configure_player(match, 1, options)
    with pytest.raises(CommandError):
        spec.configure_player(match, 9, {})
    assert [match.world.players[seat].race for seat in range(2)] == drawn
    match.world.tick = 1
    with pytest.raises(CommandError):
        spec.configure_player(match, 1, {'race': 'orc'})
    assert [match.world.players[seat].race for seat in range(2)] == drawn


def test_rated_eligibility_and_checkpoint_shape_without_sockets():
    """Rated means a fresh two-to-four duel, never a scripted mission, and race choices add no
    checkpoint fields.  Fast: local matches only, no process, no sockets."""
    from warband.online.authority import ONLINE
    spec = ONLINE[GAME]
    assert spec.result(spec.create(duel_options())) is None
    assert spec.rated(spec.create(duel_options())) is True
    assert spec.rated(spec.create(ffa_options(4))) is True
    scripted = spec.create(duel_options())
    scripted.world.scripted = True
    assert spec.rated(scripted) is False
    match = spec.create(duel_options())
    assert set(spec.checkpoint(match)) == {'seed', 'world', 'events', 'event_id', 'event_seen', 'begun'}
    spec.configure_player(match, 1, {'race': 'orc'})
    assert set(spec.checkpoint(match)) == {'seed', 'world', 'events', 'event_id', 'event_seen', 'begun'}
    spec.forfeit(match, 1)
    assert spec.result(match) == 0
