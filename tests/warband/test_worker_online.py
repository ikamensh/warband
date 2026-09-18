"""Automatic worker help belongs to the authority, including ordinary human seats."""

from websockets.sync.client import connect

import pytest

from saga2d.testing.online import command, handshake, receive, server_fixture

server_url = server_fixture('warband.authority:ONLINE')
from warband.model import Deposit, Harvest, World


@pytest.mark.slow
def test_server_assigns_both_players_workers_and_respects_manual_parking(server_url):
    """Two passive peers gain jobs; Stop persists and a later move permits work again.

    Two clients work a real server's match for seconds: the slow tier."""
    with connect(server_url, proxy=None) as host, connect(server_url, proxy=None, max_queue=None) as guest:
        room = handshake(host, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        handshake(guest, "join", game="warband-v2", room=room["room"])
        working = receive(host, predicate=lambda message: message["state"]["world"]["tick"] >= 22)
        world = World.from_dict(working["state"]["world"])
        for player, peer in ((0, host), (1, guest)):  # each seat is told of its own workers' jobs, and only it
            seen = world if peer is host else World.from_dict(receive(guest, predicate=lambda m: m["state"]["world"]["tick"] >= 22)["state"]["world"])
            workers = [unit for unit in seen.player_units(player) if unit.is_worker]
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
