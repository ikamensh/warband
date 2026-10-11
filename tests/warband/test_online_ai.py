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
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import pytest
from websockets.sync.client import connect

from saga2d import CommandError

from saga2d.testing.online import command, first_stdout_line, handshake, receive, server_fixture
from warband.brains.ai import make_brain
from warband.online.authority import ORDERS, WarbandMatch
from warband.online.online_ai import _identity_engine, _load_identity, _PlanningWorld, _store_identity, main, run_bot

_NEEDS_LEGACY_ENGINE = pytest.mark.skipif(
    _identity_engine(), reason="an identity-capable engine constructs these instead of refusing")
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


def test_identity_file_roundtrip_is_private_per_endpoint(tmp_path):
    """A stored token loads back for its endpoint only, from a mode 0600 file (fast: no server)."""
    path = str(tmp_path / "identity.json")
    _store_identity(path, "ws://one:1", "token-one")
    _store_identity(path, "ws://two:2", "token-two")
    assert _load_identity(path, "ws://one:1") == "token-one"
    assert _load_identity(path, "ws://two:2") == "token-two"
    assert _load_identity(path, "ws://missing:9") == ""
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_identity_store_narrows_wide_permissions(tmp_path):
    """A pre-existing world-readable store comes back mode 0600 on write (fast: no server)."""
    path = tmp_path / "identity.json"
    path.write_text('{"version": 1, "endpoints": {}}')
    path.chmod(0o644)
    _store_identity(str(path), "ws://one:1", "token-one")
    assert _load_identity(str(path), "ws://one:1") == "token-one"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_missing_identity_file_means_no_identity_yet(tmp_path):
    """A bot with no stored identity simply starts without one (fast: no server)."""
    assert _load_identity(str(tmp_path / "absent.json"), "ws://one:1") == ""


@pytest.mark.parametrize("content", [
    "not json", "[1, 2]",
    '{"version": 2, "endpoints": {}}', '{"version": "1", "endpoints": {}}', '{"version": true, "endpoints": {}}',
    '{"version": 1}', '{"endpoints": {}}', '{"endpoints": 7}',
    '{"version": 1, "endpoints": {"ws://one:1": 7}}',
    '{"version": 1, "endpoints": {"ws://one:1": {}}}',
    '{"version": 1, "endpoints": {"ws://one:1": {"player_token": null}}}',
])
def test_misshapen_identity_file_fails_clearly(tmp_path, content):
    """A store outside the strict schema names its path on read and write alike (fast: no server)."""
    path = tmp_path / "identity.json"
    path.write_bytes(content.encode())
    with pytest.raises(ValueError, match="identity"):
        _load_identity(str(path), "ws://one:1")
    with pytest.raises(ValueError, match="identity"):
        _store_identity(str(path), "ws://one:1", "token-new")
    assert path.read_bytes() == content.encode(), "a refused store is never overwritten"


def test_bad_entry_blocks_every_endpoint_and_preserves_the_file(tmp_path):
    """One malformed entry refuses the whole store; the failed write leaves every byte (fast: no server)."""
    content = b'{"version": 1, "endpoints": {"ws://one:1": 7, "ws://two:2": {"player_token": "token-two"}}}'
    path = tmp_path / "identity.json"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="identity"):
        _load_identity(str(path), "ws://one:1")
    with pytest.raises(ValueError, match="identity"):
        _load_identity(str(path), "ws://two:2")
    with pytest.raises(ValueError, match="identity"):
        _store_identity(str(path), "ws://one:1", "token-new")
    assert path.read_bytes() == content


@_NEEDS_LEGACY_ENGINE
@pytest.mark.parametrize("kwargs", [
    {"rated": True}, {"player_name": "Commander"}, {"identity_file": "ident.json"}, {"race": "orc"},
])
def test_identity_flags_demand_an_identity_capable_engine(kwargs):
    """Ranked rooms, names, identity files and race choices fail clearly on an engine without them.

    The installed engine predates identity support, so the demand fails before connecting
    (fast: no server); on an identity-capable engine these flags construct the new client.
    """
    with pytest.raises(CommandError, match="identity"):
        run_bot(endpoint="ws://127.0.0.1:1/", room="never", duration=0.5,
                emit=lambda event: None, **kwargs)


@pytest.mark.parametrize("kwargs, error", [
    ({"rated": "yes"}, "rated must be true or false"),
    ({"player_name": "  "}, "player_name must be non-empty text"),
    ({"race": "gnome"}, "race must be one of"),
])
def test_identity_arguments_are_validated_before_connecting(kwargs, error):
    """Malformed ranked/identity arguments are refused before any connection (fast: no server)."""
    with pytest.raises(ValueError, match=error):
        run_bot(endpoint="ws://127.0.0.1:1/", room="never", emit=lambda event: None, **kwargs)


def test_rated_with_room_is_a_usage_error(capsys):
    """--rated creates a ranked room, so joining one with it fails before connecting (fast: no server)."""
    with pytest.raises(SystemExit) as exc:
        main(["--room", "code", "--rated"])
    assert exc.value.code == 2
    assert "--rated creates a ranked room" in capsys.readouterr().err


def _handshake_seats(socket, kind, seats, *, game, **fields):
    """Shake hands declaring room-size support: the shared helper speaks for 2-seat clients only."""
    socket.send(json.dumps({"type": kind, "protocol": 1, "game": game, "seats": seats, **fields}))
    return receive(socket, "welcome")


def test_seats_with_room_is_a_usage_error(capsys):
    """--seats sizes a created room, so joining one with it fails before connecting (fast: no server)."""
    with pytest.raises(SystemExit) as exc:
        main(["--room", "code", "--seats", "4"])
    assert exc.value.code == 2
    assert "--seats sets the size of a created room" in capsys.readouterr().err


@pytest.mark.slow
def test_bot_takes_the_last_seat_of_a_four_seat_room(server_url):
    """A bot joining three wire peers becomes seat three and develops it.

    Three wire peers hold seats zero to two while a real bot subprocess plays seat three
    for seconds: the slow tier."""
    with connect(server_url, proxy=None) as first, connect(server_url, proxy=None) as second, \
            connect(server_url, proxy=None) as third:
        welcome = _handshake_seats(first, "create", 4, game="warband-v2",
                                     options={"seed": 3, "width": 64, "height": 48, "players": 4})
        second_welcome = _handshake_seats(second, "join", 4, game="warband-v2", room=welcome["room"])
        third_welcome = _handshake_seats(third, "join", 4, game="warband-v2", room=welcome["room"])
        assert (welcome["player"], second_welcome["player"], third_welcome["player"]) == (0, 1, 2)
        result = subprocess.run(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--difficulty", "hard", "--duration", "4",
             "--report-every", "0.25"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        assert result.returncode == 0, result.stderr + result.stdout
        evidence = [json.loads(line) for line in result.stdout.splitlines()]
        assert evidence[0]["event"] == "joined" and evidence[0]["player"] == 3
        tokens = (welcome["resume_token"], second_welcome["resume_token"], third_welcome["resume_token"])
        assert "resume_token" not in result.stdout and all(token not in result.stdout for token in tokens)
        assert any(row["event"] == "order_submitted" for row in evidence)
        observed = [row for row in evidence if row["event"] == "authoritative_state"]
        assert observed[-1]["tick"] > observed[0]["tick"]
        assert all(row["player"] == 3 for row in observed)
        assert any(row["order_counts"].get("Harvest", 0) for row in observed)
        assert any(row["training_queue"] > 0 for row in observed)
        assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "duration"


@pytest.mark.slow
def test_creator_seats_option_sizes_the_room(server_url):
    """A --create --seats 3 room fills with two wire joiners and goes ready.

    A real creator subprocess plus two wire peers against a real server: the slow tier."""
    process = subprocess.Popen(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, "--create",
         "--seats", "3", "--difficulty", "hard", "--width", "64", "--height", "48",
         "--duration", "4", "--report-every", "0.25"],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
    )
    try:
        announced = json.loads(first_stdout_line(process, timeout=10))
        assert announced["event"] == "created" and announced["player"] == 0
        with connect(server_url, proxy=None) as first, connect(server_url, proxy=None) as second:
            assert _handshake_seats(first, "join", 4, game="warband-v2", room=announced["room"])["player"] == 1
            assert _handshake_seats(second, "join", 4, game="warband-v2", room=announced["room"])["player"] == 2
            ready = receive(first, predicate=lambda message: message["ready"])
            assert ready["state"]["world"]["tick"] >= 0
            assert process.wait(timeout=10) == 0, process.stderr.read()
        evidence = [json.loads(line) for line in process.stdout.read().splitlines()]
        assert evidence[-1]["event"] == "finished" and evidence[-1]["player"] == 0
        assert any(row["event"] == "match_ready" for row in evidence)
        assert "resume_token" not in json.dumps(evidence)
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)


@pytest.mark.slow
def test_bot_survives_a_transient_link_drop(server_url):
    """A severed link mid-match is a wait, not a death: the client retries and play continues.

    A raw TCP proxy carries the bot's traffic and severs it once shortly after the join; a real
    bot subprocess must report connection_wait, resume the same seat through its automatic
    retry and play to the duration end: the slow tier."""
    target = urlparse(server_url)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    listener.settimeout(0.5)
    proxy_url = f"ws://127.0.0.1:{listener.getsockname()[1]}"
    stop = threading.Event()
    pairs = []
    pairs_lock = threading.Lock()

    def pump(source, dest):
        try:
            while not stop.is_set():
                chunk = source.recv(65536)
                if not chunk:
                    break
                dest.sendall(chunk)
        except OSError:
            pass

    def serve():
        while not stop.is_set():
            try:
                downstream, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                upstream = socket.create_connection((target.hostname, target.port))
            except OSError:
                downstream.close()
                continue
            with pairs_lock:
                pairs.append((downstream, upstream))
            threading.Thread(target=pump, args=(downstream, upstream), daemon=True).start()
            threading.Thread(target=pump, args=(upstream, downstream), daemon=True).start()

    def sever():
        with pairs_lock:
            dropped, pairs[:] = list(pairs), []
        for downstream, upstream in dropped:
            for sock in (downstream, upstream):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

    def drain(human, stop, errors):
        try:
            while not stop.is_set():
                try:
                    human.recv(timeout=2)
                except TimeoutError:
                    continue
        except Exception as exc:  # anything else is a real failure, reported below, never swallowed
            errors.append(exc)

    serve_thread = threading.Thread(target=serve, daemon=True)
    serve_thread.start()
    try:
        with connect(server_url, proxy=None) as human:
            welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
            stop_human = threading.Event()
            errors = []
            reader = threading.Thread(target=drain, args=(human, stop_human, errors), daemon=True)
            reader.start()
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "warband.online.online_ai", "--server", proxy_url,
                     "--room", welcome["room"], "--difficulty", "hard",
                     "--duration", "24", "--report-every", "0.25"],
                    cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
                )
                try:
                    joined = json.loads(first_stdout_line(process, timeout=10))
                    assert joined["event"] == "joined" and joined["player"] == 1
                    time.sleep(1.5)
                    sever()
                    assert process.wait(timeout=45) == 0, process.stderr.read()
                    out = process.stdout.read()
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=5)
            finally:
                stop_human.set()
                reader.join(timeout=5)
            if errors:
                raise errors[0]
    finally:
        stop.set()
        listener.close()
    evidence = [joined] + [json.loads(line) for line in out.splitlines()]
    waits = [row for row in evidence if row["event"] == "connection_wait"]
    assert len(waits) == 1 and waits[0]["player"] == 1, "the drop was reported once, never fatal"
    wait_at = evidence.index(waits[0])
    assert any(row["event"] == "match_ready" for row in evidence[wait_at + 1:]), "the seat recovered"
    assert any(row["event"] == "order_submitted" for row in evidence[wait_at + 1:]), \
        "the bot kept giving brain orders after the recovery"
    states = [row for row in evidence if row["event"] == "authoritative_state"]
    assert states[-1]["tick"] > waits[0]["tick"], "authoritative state advanced after the recovery"
    assert all(row.get("player", 1) == 1 for row in evidence), "the retry kept the same seat"
    assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "duration"
    assert "resume_token" not in out and welcome["resume_token"] not in out


@pytest.mark.slow
def test_deliberate_disconnect_is_bounded_by_duration(server_url):
    """A disconnect longer than the remaining duration ends on time with no rejoin.

    The run has no time left to play a rejoined seat, so it holds the absence to the
    duration and ends there instead of opening a connection it cannot use. A real bot
    subprocess schedules its drop near the duration end with a far longer absence:
    the slow tier."""
    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--difficulty", "hard", "--duration", "6",
             "--report-every", "0.25", "--reconnect-after", "4", "--disconnect-for", "30"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=60,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        elapsed = time.monotonic() - start
        assert result.returncode == 0, result.stderr + result.stdout
        evidence = [json.loads(line) for line in result.stdout.splitlines()]
        assert any(row["event"] == "disconnected" for row in evidence)
        assert not any(row["event"] == "rejoined" for row in evidence)
        assert evidence[-1]["event"] == "finished" and evidence[-1]["reason"] == "duration"
        assert evidence[-1]["reconnected"] is False
        assert elapsed < 20, f"the absence slipped past the duration: {elapsed:.1f}s"
        assert "resume_token" not in result.stdout and welcome["resume_token"] not in result.stdout


_NEEDS_IDENTITY_ENGINE = pytest.mark.skipif(
    not _identity_engine(), reason="rated rooms need an identity-capable engine and server")


def _create_and_concede(server_url, bot_args):
    """Launch a creator bot, join over the wire, wait for ready, resign, return evidence.

    Returns (evidence, out, ready_state): the bot's full JSON lines, its raw stdout, and the
    wire peer's first ready state. The surrender ends the match at once, deciding it.
    """
    process = subprocess.Popen(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, *bot_args],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
    )
    try:
        announced = json.loads(first_stdout_line(process, timeout=10))
        assert announced["event"] == "created" and announced["player"] == 0
        with connect(server_url, proxy=None) as peer:
            assert handshake(peer, "join", game="warband-v2", room=announced["room"])["player"] == 1
            for _ in range(20):
                if json.loads(first_stdout_line(process, timeout=10))["event"] == "match_ready":
                    break
            else:
                pytest.fail("the match never went ready")
            ready_state = receive(peer, predicate=lambda message: message["ready"])
            command(peer, {"action": "resign", "args": [1], "kwargs": {}})
            assert process.wait(timeout=25) == 0, process.stderr.read()
            out = process.stdout.read()
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)
    return [json.loads(line) for line in out.splitlines()], out, ready_state


@_NEEDS_IDENTITY_ENGINE
@pytest.mark.slow
def test_rated_create_settles_receipt_and_reuses_identity(server_url, tmp_path):
    """A rated bot mints a private identity, takes the server's receipt, and returns as itself.

    A real --rated creator subprocess plays a real rated room to a wire surrender, then a
    second run with the same identity file proves the same player returns, casually: the
    slow tier."""
    identity = str(tmp_path / "identity.json")
    base = ["--create", "--difficulty", "hard", "--duration", "30", "--report-every", "0.25",
            "--width", "48", "--height", "40"]
    evidence, out, ready_state = _create_and_concede(
        server_url, [*base, "--rated", "--race", "orc", "--player-name", "BotOne",
                     "--identity-file", identity])
    assert ready_state["state"]["world"]["players"][0]["race"] == "orc", "the seat plays its chosen race"
    finished = evidence[-1]
    assert finished["event"] == "finished" and finished["reason"] == "winner" and finished["winner"] == 0
    token = _load_identity(identity, server_url)
    assert token, "the bot minted and kept its own identity"
    assert stat.S_IMODE(os.stat(identity).st_mode) == 0o600
    for secret in ("resume_token", "player_token", token):
        assert secret not in out, "no credential ever reaches the JSON lines"
    assert finished["player_id"] and finished["match_id"]
    profile = finished["profile"]
    assert (profile["player_id"], profile["name"], profile["games"], profile["wins"]) == \
        (finished["player_id"], "BotOne", 1, 1)
    receipt = finished["result"]
    assert receipt["match_id"] == finished["match_id"] and receipt["winner"] == 0
    ratings = {entry["player_id"]: entry for entry in receipt["ratings"]}
    assert len(ratings) == 2
    for entry in ratings.values():
        assert {key for key in ("player_id", "name", "before", "after", "delta", "games", "wins", "losses")} \
            <= set(entry)
    assert ratings[finished["player_id"]]["delta"] > 0
    assert sum(entry["delta"] for entry in ratings.values()) == 0, "exchanged points sum to zero"

    casual, casual_out, reunion_state = _create_and_concede(server_url, [*base, "--identity-file", identity])
    reunion = casual[-1]
    assert reunion["event"] == "finished" and reunion["reason"] == "winner"
    assert "player_id" not in reunion and "result" not in reunion and "profile" not in reunion, \
        "a casual run carries no rated receipt"
    seats = {entry["seat"]: entry["player_id"] for entry in reunion_state["players"] if entry}
    assert seats[0] == finished["player_id"], "the same account returns, not a new one"
    assert _load_identity(identity, server_url) == token
    assert token not in casual_out and "player_token" not in casual_out


@_NEEDS_IDENTITY_ENGINE
@pytest.mark.slow
def test_join_rated_room_with_own_race(server_url, tmp_path):
    """Joining a rated room without --rated still rates the seat, with its own race.

    A wire peer creates the rated room; a real bot subprocess joins it casually with a race
    choice, and the wire surrender settles a receipt for the joiner: the slow tier."""
    identity = str(tmp_path / "identity.json")
    with connect(server_url, proxy=None) as peer:
        welcome = _handshake_seats(peer, "create", 2, game="warband-v2", rated=True,
                                   options={"seed": 3, "width": 48, "height": 40})
        assert welcome["rated"] and welcome["player"] == 0
        process = subprocess.Popen(
            [sys.executable, "-m", "warband.online.online_ai", "--server", server_url,
             "--room", welcome["room"], "--race", "dwarf", "--player-name", "BotTwo",
             "--identity-file", identity, "--difficulty", "hard",
             "--duration", "30", "--report-every", "0.25"],
            cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
        )
        try:
            joined = json.loads(first_stdout_line(process, timeout=10))
            assert joined["event"] == "joined" and joined["player"] == 1
            ready_state = receive(peer, predicate=lambda message: message["ready"])
            assert ready_state["state"]["world"]["players"][1]["race"] == "dwarf"
            command(peer, {"action": "resign", "args": [0], "kwargs": {}})
            assert process.wait(timeout=25) == 0, process.stderr.read()
            out = process.stdout.read()
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)
    evidence = [joined] + [json.loads(line) for line in out.splitlines()]
    finished = evidence[-1]
    assert finished["event"] == "finished" and finished["reason"] == "winner" and finished["winner"] == 1
    assert finished["player_id"] and finished["result"]["winner"] == 1
    assert finished["profile"]["name"] == "BotTwo"
    token = _load_identity(identity, server_url)
    assert token and stat.S_IMODE(os.stat(identity).st_mode) == 0o600
    for secret in ("resume_token", "player_token", token):
        assert secret not in out, "no credential ever reaches the JSON lines"


@_NEEDS_IDENTITY_ENGINE
@pytest.mark.slow
def test_rated_rejoin_keeps_identity_and_seat(server_url, tmp_path):
    """A deliberate rejoin in a rated room carries the same identity and seat.

    A real --rated creator subprocess with an identity file drops and rejoins mid-room
    against a real server; the token file is stable and the undecided finish still names
    the rated seat without any receipt: the slow tier."""
    identity = str(tmp_path / "identity.json")
    process = subprocess.Popen(
        [sys.executable, "-m", "warband.online.online_ai", "--server", server_url, "--create",
         "--rated", "--player-name", "BotZero", "--identity-file", identity,
         "--difficulty", "hard", "--width", "48", "--height", "40",
         "--duration", "9", "--report-every", "0.25", "--reconnect-after", "1", "--disconnect-for", "1"],
        cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "DISPLAY": "", "PYTHONUNBUFFERED": "1"},
    )
    def drain(peer, stop, errors):
        try:
            while not stop.is_set():
                try:
                    peer.recv(timeout=2)
                except TimeoutError:
                    continue
        except Exception as exc:  # anything else is a real failure, reported below, never swallowed
            errors.append(exc)

    try:
        announced = json.loads(first_stdout_line(process, timeout=10))
        assert announced["event"] == "created" and announced["player"] == 0
        with connect(server_url, proxy=None) as peer:
            assert handshake(peer, "join", game="warband-v2", room=announced["room"])["player"] == 1
            stop_peer = threading.Event()
            errors = []
            reader = threading.Thread(target=drain, args=(peer, stop_peer, errors), daemon=True)
            reader.start()
            try:
                assert process.wait(timeout=30) == 0, process.stderr.read()
                out = process.stdout.read()
            finally:
                stop_peer.set()
                reader.join(timeout=5)
            if errors:
                raise errors[0]
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)
    evidence = [json.loads(line) for line in out.splitlines()]
    dropped = [row for row in evidence if row["event"] == "disconnected"]
    rejoined = [row for row in evidence if row["event"] == "rejoined"]
    assert len(dropped) == len(rejoined) == 1
    assert dropped[0]["player"] == rejoined[0]["player"] == 0
    token = _load_identity(identity, server_url)
    assert token and stat.S_IMODE(os.stat(identity).st_mode) == 0o600
    for secret in ("resume_token", "player_token", token):
        assert secret not in out, "no credential ever reaches the JSON lines"
    finished = evidence[-1]
    assert finished["event"] == "finished" and finished["reason"] == "duration"
    assert finished["player_id"] and finished["match_id"] and finished["result"] is None, \
        "an undecided rated finish names the seat but invents no receipt"


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
