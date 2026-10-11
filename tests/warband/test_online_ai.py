"""The headless opponent uses the same public room protocol as a human player, and what its brain orders reaches the server.

The brain plans on ``online_ai._PlanningWorld``, a copy of its seat's snapshot that turns each order into a command
for the server; ``run_bot`` drives it only against a live room, so the fast tests below hold the copy itself.
The bot can also drop its connection once and rejoin its reserved seat, and can demand a server-declared
winner before a duration end counts as success; those need a live room, so they live in the slow tier.
"""

import json
import os
from pathlib import Path
import random
import subprocess
import sys
import threading

import pytest
from websockets.sync.client import connect

from saga2d.testing.online import command, first_stdout_line, handshake, receive, server_fixture
from warband.brains.ai import make_brain
from warband.online.authority import ORDERS, WarbandMatch
from warband.online.online_ai import _PlanningWorld, run_bot
from warband.records import replay
from warband.sim.model import tile_center
from warband.sim.rules import BuildingType, Difficulty, UnitType

server_url = server_fixture('warband.online.authority:ONLINE')


@pytest.mark.source_only("brains plan on a stand-in for a World; online_ai runs as a program of its own, on the source")
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


@pytest.mark.parametrize("flag,value", [
    ("reconnect_after", 0), ("reconnect_after", -1.0),
    ("reconnect_after", float("inf")), ("reconnect_after", float("nan")),
    ("disconnect_for", 0), ("disconnect_for", -2.0),
    ("disconnect_for", float("inf")), ("disconnect_for", float("nan")),
])
def test_reconnect_timings_must_be_positive_and_finite(flag, value):
    """A non-positive or unbounded reconnect timing is refused before any connection (fast: no server)."""
    with pytest.raises(ValueError, match="must be positive and finite"):
        run_bot(endpoint="ws://127.0.0.1:1/", room="never", emit=lambda event: None, **{flag: value})


@pytest.mark.slow
def test_bot_disconnects_once_and_rejoins_its_reserved_seat(server_url):
    """A deliberate drop keeps the reserved seat: the same player, advancing ticks, orders resume.

    The run spans a full peasant training cycle (about eleven seconds of world time: the bot
    retrains near world t=17, well after rejoining near t=2), so a macro decision is genuinely
    required post-rejoin and the orders assertion cannot pass on a quiet bot. A real bot
    subprocess drops and rejoins against a real server while a human holds the other seat:
    the slow tier."""

    def drain(human, stop, errors):
        try:
            while not stop.is_set():
                try:
                    human.recv(timeout=2)
                except TimeoutError:
                    continue
        except Exception as exc:  # anything else is a real failure, reported below, never swallowed
            errors.append(exc)

    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        stop = threading.Event()
        errors = []
        reader = threading.Thread(target=drain, args=(human, stop, errors), daemon=True)
        reader.start()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
                 "--room", welcome["room"], "--difficulty", "hard", "--duration", "30",
                 "--report-every", "0.25", "--reconnect-after", "1", "--disconnect-for", "1"],
                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=60,
                env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
            )
        finally:
            stop.set()
            reader.join(timeout=5)
        if errors:
            raise errors[0]
        assert result.returncode == 0, result.stderr + result.stdout
        evidence = [json.loads(line) for line in result.stdout.splitlines()]
        assert evidence[0]["event"] == "joined" and evidence[0]["player"] == 1
        dropped = [row for row in evidence if row["event"] == "disconnected"]
        rejoined = [row for row in evidence if row["event"] == "rejoined"]
        assert len(dropped) == len(rejoined) == 1, "the bot disconnected and rejoined exactly once"
        assert dropped[0]["player"] == rejoined[0]["player"] == 1, "the rejoin kept the reserved seat"
        assert rejoined[0]["before_tick"] == dropped[0]["tick"]
        assert rejoined[0]["tick"] >= dropped[0]["tick"]
        assert "resume_token" not in result.stdout and welcome["resume_token"] not in result.stdout
        states = [row for row in evidence if row["event"] == "authoritative_state"]
        assert states[-1]["tick"] > dropped[0]["tick"], "authoritative state advanced after the rejoin"
        rejoin_at = evidence.index(rejoined[0])
        assert any(row["event"] == "order_submitted" for row in evidence[rejoin_at + 1:]), \
            "the bot kept giving brain orders after rejoining"
        assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "duration"
        assert evidence[-1]["reconnected"] is True


@pytest.mark.slow
def test_require_completion_fails_a_duration_end_with_no_winner(server_url):
    """A bounded run with --require-completion exits nonzero while the match is still undecided.

    A real bot subprocess plays out a short duration against a real server: the slow tier."""
    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        result = subprocess.run(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--difficulty", "hard", "--duration", "2",
             "--report-every", "0.25", "--require-completion"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        assert result.returncode == 1, result.stderr + result.stdout
        evidence = [json.loads(line) for line in result.stdout.splitlines()]
        assert evidence[-1]["event"] == "error" and "winner" in evidence[-1]["error"]
        assert "resume_token" not in result.stdout and welcome["resume_token"] not in result.stdout


@pytest.mark.slow
def test_declared_winner_is_a_success_carrying_the_server_result(server_url):
    """When the opponent surrenders over the wire, a --require-completion bot succeeds with the winner.

    A real bot subprocess plays a real server match ended by a real wire surrender, with a reconnect
    scheduled far past the finish so none happens: the slow tier."""
    assert "resign" in ORDERS, "the surrender below must stay a valid authority order"
    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        process = subprocess.Popen(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--difficulty", "hard",
             "--duration", "30", "--report-every", "0.25",
             "--require-completion", "--reconnect-after", "60"],
            cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        try:
            assert json.loads(first_stdout_line(process, timeout=10))["event"] == "joined"
            for _ in range(20):
                if json.loads(first_stdout_line(process, timeout=10))["event"] == "match_ready":
                    break
            else:
                pytest.fail("the match never went ready")
            command(human, {"action": "resign", "args": [0], "kwargs": {}})
            assert process.wait(timeout=20) == 0, process.stderr.read()
            out = process.stdout.read()
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)
        evidence = [json.loads(line) for line in out.splitlines()]
        assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "winner"
        assert evidence[-1]["winner"] == 1 and evidence[-1]["player"] == 1
        states = [row for row in evidence if row["event"] == "authoritative_state"]
        assert states and states[-1]["winner"] == 1, "the final evidence carries the server-declared winner"
        assert not any(row["event"] in ("disconnected", "rejoined") for row in evidence), \
            "no reconnect happens once the game is finished"
        assert "resume_token" not in out and welcome["resume_token"] not in out


@pytest.mark.slow
def test_no_reconnect_without_a_match(server_url):
    """A lobby that never fills ends on duration with no disconnect or rejoin evidence.

    A real creator subprocess waits alone against a real server: the slow tier."""
    result = subprocess.run(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, "--create",
         "--width", "48", "--height", "40", "--duration", "1.5", "--reconnect-after", "0.5"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10,
        env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
    )
    assert result.returncode == 1, result.stderr + result.stdout
    evidence = [json.loads(line) for line in result.stdout.splitlines()]
    assert evidence[-1]["event"] == "error" and "both players" in evidence[-1]["error"]
    assert not any(row["event"] in ("disconnected", "rejoined") for row in evidence), \
        "no reconnect is attempted before the match goes ready"
    assert "resume_token" not in result.stdout


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
