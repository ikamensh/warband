"""Warband rooms on the dedicated server: the server clock, checkpoints and restarts."""
import json

import pytest
from websockets.sync.client import connect

from saga2d.testing.online import command, handshake, receive, running_server, server_fixture
from warband.multiplayer import ONLINE
from warband.rules import BuildingType, UnitType

GAME = 'warband-v1'
SPEC = 'warband.multiplayer:ONLINE'
server_url = server_fixture(SPEC)


def test_warband_runs_on_the_server_clock_and_pauses_for_a_disconnected_player(server_url):
    """Headless RTS advances without a host scene and both factions' units obey validated orders."""
    from warband.model import World
    with connect(server_url, proxy=None) as host, connect(server_url, proxy=None) as guest:
        room = handshake(host, game='warband-v1', options={'width': 40, 'height': 32})
        assert receive(host)['state']['world']['tick'] == 0
        guest_seat = handshake(guest, 'join', game='warband-v1', room=room['room'])
        receive(host)
        ready = receive(guest)
        world = World.from_dict(ready['state']['world'])
        own, enemy = world.player_units(1)[0], world.player_units(0)[0]
        destination = [own.x - 2, own.y]
        command(guest, {'action': 'move', 'args': [[enemy.id], destination]})
        assert 'own' in receive(guest, 'error')['error']
        command(guest, {'action': 'move', 'args': [[own.id], destination]})
        moved = receive(guest, predicate=lambda message: message['state']['world']['tick'] >= 12)
        assert World.from_dict(moved['state']['world']).units[own.id].pos != own.pos
        guest.close()
        paused = receive(host, predicate=lambda message: not message['ready'])
        with pytest.raises(TimeoutError):
            host.recv(timeout=.15)
        with connect(server_url, proxy=None) as returned:
            handshake(returned, 'resume', game='warband-v1', room=room['room'],
                      resume_token=guest_seat['resume_token'])
            resumed = receive(returned)
            assert resumed['ready']
            assert resumed['state']['world']['tick'] >= paused['state']['world']['tick']



def test_rooms_and_private_seats_survive_server_restart(tmp_path):
    """Trusted checkpoints restore private seats and a running match after process loss."""
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            seat0 = handshake(host, game=GAME)
            receive(host)
            seat1 = handshake(guest, 'join', game=GAME, room=seat0['room'])
            receive(host)
            before = receive(guest, predicate=lambda state: state['state']['world']['tick'] >= 4)
    with running_server(SPEC, arguments=('--state-dir', tmp_path)) as (url, process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            returned = handshake(host, 'resume', game=GAME, room=seat0['room'], resume_token=seat0['resume_token'])
            assert returned['player'] == 0
            assert not receive(host)['ready']
            handshake(guest, 'resume', game=GAME, room=seat0['room'], resume_token=seat1['resume_token'])
            resumed = receive(guest)
            assert resumed['ready']
            assert resumed['state']['world']['tick'] >= before['state']['world']['tick'] >= 4


def test_trusted_checkpoint_keeps_existing_json_and_the_next_real_order():
    """The match resumes exact paid state using its unchanged checkpoint format."""
    spec = ONLINE[GAME]
    match = spec.create({'width': 40, 'height': 32})
    hall = next(building for building in match.world.buildings.values()
                if building.player == 0 and building.type == BuildingType.TOWN_HALL)
    match.apply(0, {'action': 'train', 'args': [hall.id, UnitType.PEASANT.value]})
    before = json.loads(json.dumps(match.snapshot(0)))
    checkpoint = json.loads(json.dumps(spec.checkpoint(match)))
    assert checkpoint == before
    resumed = spec.restore(checkpoint)
    assert resumed.snapshot(0) == match.snapshot(0)
    assert resumed.snapshot(1) == match.snapshot(1)
    following = {'action': 'cancel_train', 'args': [hall.id]}
    match.apply(0, following)
    resumed.apply(0, following)
    assert json.loads(json.dumps(resumed.snapshot(0))) != before
    assert resumed.snapshot(0) == match.snapshot(0)
