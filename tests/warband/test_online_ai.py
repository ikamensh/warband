"""The headless opponent uses the same public room protocol as a human player, and what its brain orders reaches the server.

The brain plans on ``online_ai._PlanningWorld``, a copy of its seat's snapshot that turns each order into a command
for the server; ``run_bot`` drives it only against a live room, so the fast tests below hold the copy itself.
"""

import json
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest
from websockets.sync.client import connect

from saga2d.testing.online import first_stdout_line, handshake, receive, server_fixture
from warband.brains.ai import make_brain
from warband.online.authority import WarbandMatch
from warband.online.online_ai import _PlanningWorld
from warband.records import replay
from warband.sim.model import tile_center
from warband.sim.rules import BuildingType, Difficulty, UnitType

server_url = server_fixture('warband.online.authority:ONLINE')


def test_the_online_ai_hunts_an_intruder_on_the_server_and_lets_it_go_there() -> None:
    """The copy sent a list of orders of its own, and the brain's attacks, holds, cancels and releases changed the
    copy alone: the Hard brain logged "hunt peasant 15 with 3" and nobody attacked the intruder on the server.  Had
    the attack alone been sent, the hunters, let go on the copy once the intruder left the base, would have chased
    it across the map to its own."""
    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    world = match.world
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    intruder = world.spawn_unit(0, UnitType.PEASANT, tile_center((hall.x - 2, hall.y + 1)))
    intruder.hp = 10_000  # staged: it lives through the chase, so only the brain can end it
    world.update_vision()
    brain = make_brain(1, Difficulty.HARD, match.seed)
    rng = random.Random(match.seed * 2 + 1)

    def think() -> None:
        """One pass of the bot: the brain plans on its seat's snapshot, and what it queued goes to the server."""
        planning = _PlanningWorld(json.loads(json.dumps(match.snapshot(1)))['world'])
        planning.world.orders = []  # the copy logs every order the brain gives it, as a recorded match does
        brain.think(planning, rng)
        given = [[name, args, kwargs] for _tick, name, args, kwargs in planning.world.orders if name != 'assign_workers']
        assert given == [[c['action'], c['args'], c['kwargs']] for c in planning.commands], "an order stayed on the copy"
        for command in planning.commands:
            match.apply(1, command)

    def hunters() -> list[int]:
        units = json.loads(json.dumps(match.snapshot(1)))['world']['units']
        return [u['id'] for u in units if u['orders'] and u['orders'][0]['kind'] == 'Attack' and u['orders'][0]['target'] == intruder.id]

    think()
    assert hunters(), "the brain hunted the intruder on its copy alone"
    match.apply(0, {'action': 'move', 'args': [[intruder.id], [4.5, 4.5]], 'kwargs': {}})
    for _ in range(200):  # ten seconds: the intruder leaves the base in three
        match.step()
        if world.time >= brain.next_think:
            think()
            if not hunters():
                break
    assert not hunters(), "the hunters were let go on the copy alone and chase the intruder home"


def test_the_online_ai_sends_every_order_a_player_gives_or_handles_it_by_name() -> None:
    """An order the world takes from a player is one the authority takes, which the copy sends as it is, or one it
    handles by name: a harvest is a right-click online, and idle peasants the server sends to work once a second
    anyway.  Any other the copy refuses rather than keep: a new order has to be one or the other before a brain
    gives it online."""
    planning = _PlanningWorld(json.loads(json.dumps(WarbandMatch(seed=3).snapshot(1)))['world'])
    assert all(callable(getattr(planning, name)) for name in replay.ORDERS)


@pytest.mark.slow
def test_headless_opponent_joins_and_its_orders_reach_the_authoritative_world(server_url):
    """A separate CLI process joins seat one, develops it, and exits with useful evidence.

    The headless client plays against a real server for seconds: the slow tier."""
    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        initial = receive(human)["state"]["world"]
        result = subprocess.run(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--difficulty", "hard", "--duration", "2.5",
             "--report-every", "0.25"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        assert result.returncode == 0, result.stderr + result.stdout
        evidence = [json.loads(line) for line in result.stdout.splitlines()]
        assert evidence[0]["event"] == "joined" and evidence[0]["player"] == 1
        assert "resume_token" not in result.stdout and welcome["resume_token"] not in result.stdout
        assert any(row["event"] == "order_submitted" for row in evidence)
        observed = [row for row in evidence if row["event"] == "authoritative_state"]
        assert observed[-1]["tick"] > observed[0]["tick"]
        assert any(row["order_counts"].get("Harvest", 0) for row in observed)
        assert any(row["training_queue"] > 0 for row in observed)
        assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "duration"
        changed = receive(human, predicate=lambda message: message["state"]["world"]["tick"] >= observed[-1]["tick"])
        authoritative = changed["state"]["world"]
        # The bot's orders reached the world (its own snapshots above say so); the human is not told them (WB-011).
        assert not any(unit["player"] == 1 and unit["orders"] for unit in authoritative["units"])
        assert authoritative["players"][0]["gold"] == initial["players"][0]["gold"]


@pytest.mark.slow
def test_headless_creator_announces_a_room_before_a_human_joins(server_url):
    """The remote bot can create seat zero and waits without advancing the lobby world.

    The headless client waits in a real lobby for seconds: the slow tier."""
    process = subprocess.Popen(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, "--create",
         "--difficulty", "hard", "--width", "48", "--height", "40", "--duration", "2"],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        announced = json.loads(first_stdout_line(process, timeout=5))
        assert announced["event"] == "created" and announced["player"] == 0
        with connect(server_url, proxy=None) as human:
            joined = handshake(human, "join", game="warband-v2", room=announced["room"])
            assert joined["player"] == 1
            state = receive(human, predicate=lambda message: message["state"]["world"]["tick"] >= 22)
            assert not any(unit["player"] == 0 and unit["orders"] for unit in state["state"]["world"]["units"])  # WB-011
            assert process.wait(timeout=6) == 0, process.stderr.read()
        evidence = [json.loads(line) for line in process.stdout.read().splitlines()]
        assert evidence[-1]["event"] == "finished" and evidence[-1]["player"] == 0
        assert any(row["order_counts"] for row in evidence if row["event"] == "authoritative_state"), "the bot never gave an order"
        assert "resume_token" not in json.dumps([announced, *evidence])
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)


@pytest.mark.parametrize("arguments, error", [
    (["--room", "missing"], "Room not found"),
    (["--create", "--wait-timeout", "0.15"], "Timed out waiting"),
])
def test_headless_client_reports_failed_join_and_bounded_lobby_wait(server_url, arguments, error):
    """A failed connection or absent partner exits nonzero with machine-readable evidence."""
    result = subprocess.run(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, *arguments],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 1, result.stderr + result.stdout
    evidence = [json.loads(line) for line in result.stdout.splitlines()]
    assert evidence[-1]["event"] == "error" and error in evidence[-1]["error"]
    assert "resume_token" not in result.stdout
