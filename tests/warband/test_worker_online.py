"""Automatic worker help belongs to the authority, including ordinary human seats."""

from websockets.sync.client import connect

from tests.test_online_server import command, handshake, receive, server_url
from warband.model import Deposit, Harvest, World


def test_server_assigns_both_players_workers_and_respects_manual_parking(server_url):
    """Two passive peers gain jobs; Stop persists and a later move permits work again."""
    with connect(server_url, proxy=None) as host, connect(server_url, proxy=None, max_queue=None) as guest:
        room = handshake(host, game="warband-v1", options={"seed": 3, "width": 40, "height": 32})
        handshake(guest, "join", game="warband-v1", room=room["room"])
        working = receive(host, predicate=lambda message: message["state"]["world"]["tick"] >= 22)
        world = World.from_dict(working["state"]["world"])
        for player in (0, 1):
            workers = [unit for unit in world.player_units(player) if unit.is_worker]
            assert workers
            assert all(isinstance(unit.order, (Harvest, Deposit)) for unit in workers)

        worker = next(unit for unit in world.player_units(0) if unit.is_worker and not unit.hidden)
        command(host, {"action": "stop", "args": [[worker.id]]})
        parked = receive(host, predicate=lambda message: any(
            unit["id"] == worker.id and not unit["auto_work"]
            for unit in message["state"]["world"]["units"]))
        settled = receive(host, predicate=lambda message:
                          message["state"]["world"]["tick"] >= parked["state"]["world"]["tick"] + 24)
        parked_worker = World.from_dict(settled["state"]["world"]).units[worker.id]
        assert not parked_worker.orders
        assert not parked_worker.auto_work

        command(host, {"action": "move", "args": [[worker.id], parked_worker.pos]})
        resumed = receive(host, predicate=lambda message:
                          message["state"]["world"]["tick"] >= settled["state"]["world"]["tick"] + 24)
        resumed_worker = World.from_dict(resumed["state"]["world"]).units[worker.id]
        assert resumed_worker.auto_work
        assert isinstance(resumed_worker.order, (Harvest, Deposit))
