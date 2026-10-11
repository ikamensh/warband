"""Ask the room server how busy it is, from the command line.

``warband --server-info`` prints the server's players, rooms and capacity
without starting the game, compiling the simulation or opening a window.

The fast tests below cover the public helpers (endpoint mapping, payload
validation, text formatting, argument routing).  Everything that starts a
whole interpreter or serves local HTTP is marked slow: a subprocess start
takes about a second, and a socket server cannot run in the fast tier.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from warband.__main__ import answered_by_the_parser, main, server_info_requested
from warband.online.server_info import ServerInfoError, format_text, status_url, validate_status

ROOT = Path(__file__).resolve().parents[2]

CONTRACT = {"protocol": 1, "games": ["warband-v2"], "rooms": 2, "ready_rooms": 1, "players": 3,
            "max_rooms": 32, "max_connections": 96, "room_retention": 900, "campaign_retention": 604800,
            "rated_grace": 300, "ratings": {"warband-v2": {"enabled": True, "seats": [2], "starting_rating": 1500.0}}}


def test_a_play_endpoint_maps_to_its_status_page() -> None:
    assert status_url("wss://games.tachyon-ai.eu/play") == "https://games.tachyon-ai.eu/status"


def test_a_plain_ws_endpoint_maps_to_http_for_a_local_server() -> None:
    assert status_url("ws://127.0.0.1:8765/play") == "http://127.0.0.1:8765/status"


def test_a_status_mapping_keeps_the_origin_and_drops_the_path() -> None:
    """Every endpoint answers at its origin's /status; there is no per-path status page."""
    assert status_url("wss://example.com:445/sub/play") == "https://example.com:445/status"
    assert status_url("wss://example.com/rooms") == "https://example.com/status"


@pytest.mark.parametrize("endpoint", ["http://example.com/play", "https://example.com/play",
                                      "wss://example.com:0/play", "ws://example.com/play",
                                      "wss://user@example.com/play", "wss://example.com/play#frag",
                                      "not-a-url", ""])
def test_endpoints_outside_the_engine_policy_are_refused(endpoint: str) -> None:
    """The same policy the game client enforces: wss, or plain ws only at home (saga2d.online)."""
    with pytest.raises(ServerInfoError):
        status_url(endpoint)


def test_a_valid_payload_validates_with_its_optional_fields() -> None:
    info = validate_status(dict(CONTRACT), "http://127.0.0.1:1/status")
    assert (info["players"], info["rooms"], info["ready_rooms"]) == (3, 2, 1)
    assert info["games"] == ["warband-v2"]
    assert info["rated_grace"] == 300
    assert info["ratings"] == {"warband-v2": {"enabled": True, "seats": [2], "starting_rating": 1500.0}}


def test_optional_fields_may_be_absent() -> None:
    plain = {key: value for key, value in CONTRACT.items() if key != "rated_grace"}
    plain["ratings"] = {"warband-v2": {"enabled": True}}
    info = validate_status(plain, "http://127.0.0.1:1/status")
    assert "rated_grace" not in info
    assert info["ratings"] == {"warband-v2": {"enabled": True}}


def test_unknown_newer_fields_are_ignored() -> None:
    info = validate_status({**CONTRACT, "motd": "hello"}, "http://127.0.0.1:1/status")
    assert "motd" not in info


def test_fractional_retentions_validate_and_survive() -> None:
    """The server speaks floats too: a fractional retention is kept, never truncated to a silent zero."""
    info = validate_status({**CONTRACT, "room_retention": 1.5}, "http://127.0.0.1:1/status")
    assert info["room_retention"] == 1.5


def test_a_float_starting_rating_validates_and_survives() -> None:
    """The engine reports its starting rating as a float: kept as sent, while booleans stay refused."""
    info = validate_status(CONTRACT, "http://127.0.0.1:1/status")
    assert type(info["ratings"]["warband-v2"]["starting_rating"]) is float
    assert info["ratings"]["warband-v2"]["starting_rating"] == 1500.0
    bad = {"warband-v2": {"enabled": True, "starting_rating": True}}
    with pytest.raises(ServerInfoError):
        validate_status({**CONTRACT, "ratings": bad}, "http://127.0.0.1:1/status")


@pytest.mark.parametrize("key", ["protocol", "rooms", "ready_rooms", "players",
                                 "max_rooms", "max_connections"])
@pytest.mark.parametrize("value", ["2", True, 2.0, None])
def test_a_mistyped_count_is_refused(key: str, value: object) -> None:
    """A count that is not an exact integer fails loudly, never prints as an invented number."""
    with pytest.raises(ServerInfoError):
        validate_status({**CONTRACT, key: value}, "http://127.0.0.1:1/status")


@pytest.mark.parametrize("value", [0, -5, True, "900", float("inf"), float("nan")])
def test_a_non_positive_duration_is_refused(value: object) -> None:
    with pytest.raises(ServerInfoError):
        validate_status({**CONTRACT, "room_retention": value}, "http://127.0.0.1:1/status")


@pytest.mark.parametrize("payload", [{**CONTRACT, "ratings": {"warband-v2": {"enabled": "yes"}}},
                                     {**CONTRACT, "ratings": ["warband-v2"]},
                                     {**CONTRACT, "ratings": {"warband-v2": {"enabled": True, "seats": ["many"]}}},
                                     {**CONTRACT, "ratings": {"warband-v2": {"enabled": True, "starting_rating": "high"}}},
                                     {**CONTRACT, "rated_grace": -1},
                                     {k: v for k, v in CONTRACT.items() if k != "players"},
                                     [1, 2], "status"])
def test_a_misshapen_payload_is_refused(payload: object) -> None:
    with pytest.raises(ServerInfoError):
        validate_status(payload, "http://127.0.0.1:1/status")


def test_text_names_the_endpoint_players_and_rooms() -> None:
    text = format_text({"endpoint": "wss://games.tachyon-ai.eu/play",
                        "status_url": "https://games.tachyon-ai.eu/status", **CONTRACT})
    assert "wss://games.tachyon-ai.eu/play" in text
    assert "3" in text and "warband-v2" in text
    assert "online" in text


def test_text_formats_fractional_retentions() -> None:
    text = format_text({"endpoint": "wss://x/play", "status_url": "https://x/status",
                        **{**CONTRACT, "room_retention": 1.5}})
    assert "1.5s" in text


def test_a_server_info_request_skips_the_simulation_choice() -> None:
    """Like --help and --version, --server-info must never wait for the compile."""
    assert answered_by_the_parser(["--server-info"])
    assert answered_by_the_parser(["--server-info", "--server", "wss://example.com/play"])
    assert answered_by_the_parser(["--server-infoo"])
    assert answered_by_the_parser(["--server-info=wrong"])
    assert answered_by_the_parser(["--json"])
    assert answered_by_the_parser(["--timeout", "3"])
    assert not answered_by_the_parser(["--server", "wss://example.com/play"])


def test_only_info_flags_route_to_the_info_parser() -> None:
    assert server_info_requested(["--server-info"])
    assert server_info_requested(["--server-info", "--seed", "3"])
    assert server_info_requested(["--json"])
    assert server_info_requested(["--timeout", "3"])
    assert server_info_requested(["--server-infoo"])
    assert server_info_requested(["--server-inf"])
    assert server_info_requested(["--server-i"])
    assert not server_info_requested(["--server", "wss://example.com/play", "--online-host"])
    assert not server_info_requested(["--serv"])
    assert not server_info_requested(["--seed", "3"])
    assert not server_info_requested([])


def test_a_server_info_prefix_answers_without_the_simulation(monkeypatch) -> None:
    """The game parser expands --server-inf to --server-info, so the early dispatch must too:
    a refused connection on the discard port still proves the answer path never chose the simulation."""
    from warband.league import fastsim

    monkeypatch.setattr(fastsim, "activate_for_game",
                        lambda: pytest.fail("chose the simulation to answer a prefix"))
    monkeypatch.setattr(sys, "argv", ["warband", "--server-inf", "--server", "ws://127.0.0.1:9/play"])
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code != 0


def test_help_names_server_info(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["warband", "--help"])
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code == 0
    assert "--server-info" in capsys.readouterr().out


def test_a_game_launch_alongside_server_info_is_refused(monkeypatch, capsys) -> None:
    """--server-info answers instead of playing; a seed alongside it is a mistake, not a match."""
    monkeypatch.setattr(sys, "argv", ["warband", "--server-info", "--seed", "3"])
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code != 0


@pytest.mark.parametrize("argv", [["warband", "--json"], ["warband", "--timeout", "3"],
                                  ["warband", "--server-infoo"], ["warband", "--server-info=wrong"]])
def test_info_flag_mistakes_are_refused_without_the_simulation(monkeypatch, argv) -> None:
    """--json/--timeout shape a server-info answer and malformed flags are mistakes: all refuse
    through the info parser, before anything chooses (let alone compiles) the simulation."""
    from warband.league import fastsim

    monkeypatch.setattr(fastsim, "activate_for_game",
                        lambda: pytest.fail("chose the simulation to refuse a flag"))
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code != 0


class _StatusHandler(BaseHTTPRequestHandler):
    """Serve one canned answer on /status; the test server sets body/status/delay."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/status":
            self.send_response(404)
            self.end_headers()
            return
        if self.server.delay:  # type: ignore[attr-defined]
            import time

            time.sleep(self.server.delay)  # type: ignore[attr-defined]
        body = self.server.body  # type: ignore[attr-defined]
        self.send_response(self.server.status)  # type: ignore[attr-defined]
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def status_server():
    """A real local HTTP server speaking the /status contract; closed after the test."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StatusHandler)
    server.body = json.dumps(CONTRACT).encode()
    server.status = 200
    server.delay = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()


def _endpoint(server) -> str:
    port = server.server_address[1]
    return f"ws://127.0.0.1:{port}/play"


def _cli_env():
    """The game environment without the interpreted-simulation opt-out: the CLI must not need it."""
    env = dict(os.environ)
    env.pop("WARBAND_INTERPRETED", None)
    return env


@pytest.mark.slow
def test_the_command_line_reports_a_live_server(status_server) -> None:
    """A whole interpreter start against real local HTTP: text names the endpoint and its numbers."""
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server)],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode == 0, done.stderr
    assert _endpoint(status_server) in done.stdout
    assert "3" in done.stdout and "warband-v2" in done.stdout


@pytest.mark.slow
def test_the_command_line_reports_a_live_server_as_json(status_server) -> None:
    """A whole interpreter start against real local HTTP: stdout parses as the validated mapping."""
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server),
                           "--json"], capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert (payload["players"], payload["rooms"], payload["ready_rooms"]) == (3, 2, 1)
    assert payload["games"] == ["warband-v2"]
    assert payload["rated_grace"] == 300
    assert payload["ratings"]["warband-v2"]["starting_rating"] == 1500.0


@pytest.mark.slow
def test_the_command_line_needs_no_simulation_or_art(status_server) -> None:
    """A guarded interpreter proves the headless path: simulation, UI, art, audio and even the
    simulation compiler's own module fail the run on import."""
    guard = "\n".join(["import sys, runpy",
                         "forbid = ('warband.sim', 'warband.ui', 'warband.art', 'warband.audio', 'warband.story', "
                         "'warband.brains', 'warband.records', 'warband.league', "
                         "'warband.online.authority', 'warband.online.online_ai')",
                         "import importlib.abc",
                         "class Guard(importlib.abc.MetaPathFinder):",
                         "    def find_spec(self, name, path=None, target=None):",
                         "        if name in forbid or name.startswith(tuple(f + '.' for f in forbid)):",
                         "            raise ImportError('headless violation: ' + name)",
                         "sys.meta_path.insert(0, Guard())",
                         "sys.argv = ['warband', '--server-info', '--server', %r]"
                         % _endpoint(status_server),
                         "runpy.run_module('warband', run_name='__main__')"])
    done = subprocess.run([sys.executable, "-c", guard], capture_output=True, text=True,
                          cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode == 0, done.stderr
    assert "warband-v2" in done.stdout


@pytest.mark.slow
def test_an_unreachable_server_fails_without_invented_numbers(status_server) -> None:
    """A whole interpreter start at a closed port: nonzero, actionable stderr, no zeros on stdout."""
    port = status_server.server_address[1]
    status_server.shutdown()
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", f"ws://127.0.0.1:{port}/play"],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""
    assert "0" not in done.stdout.split()


@pytest.mark.slow
def test_a_malformed_answer_fails(status_server) -> None:
    """A whole interpreter start against real local HTTP serving garbage: nonzero with a clear error."""
    status_server.body = b"not json{"
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server)],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""


@pytest.mark.slow
def test_a_mistyped_answer_fails(status_server) -> None:
    """A whole interpreter start against real local HTTP serving wrong types: nonzero, no zeros printed."""
    bad = dict(CONTRACT)
    bad["players"] = "three"
    status_server.body = json.dumps(bad).encode()
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server)],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""


@pytest.mark.slow
def test_a_failing_server_fails(status_server) -> None:
    """A whole interpreter start against real local HTTP answering 500: nonzero with a clear error."""
    status_server.status = 500
    status_server.body = b"boom"
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server)],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""


@pytest.mark.slow
def test_an_oversized_answer_is_refused(status_server) -> None:
    """A whole interpreter start against real local HTTP serving past the payload bound: nonzero, nothing read."""
    from warband.online.server_info import MAX_PAYLOAD

    status_server.body = b'{"protocol": 1, "pad": "' + b"x" * (MAX_PAYLOAD + 1) + b'"}'
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server)],
                          capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""


@pytest.mark.slow
def test_a_slow_server_times_out(status_server) -> None:
    """A whole interpreter start against real local HTTP slower than --timeout: nonzero, quickly."""
    status_server.delay = 5
    done = subprocess.run([sys.executable, "-m", "warband", "--server-info", "--server", _endpoint(status_server),
                           "--timeout", "0.5"], capture_output=True, text=True, cwd=ROOT, env=_cli_env(), timeout=120)
    assert done.returncode != 0
    assert done.stderr.strip() != ""
