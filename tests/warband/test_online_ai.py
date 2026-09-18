"""The headless opponent uses the same public room protocol as a human player."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from websockets.sync.client import connect

from saga2d.testing.online import first_stdout_line, handshake, receive, server_fixture

server_url = server_fixture('warband.authority:ONLINE')


@pytest.mark.slow
def test_headless_opponent_joins_and_its_orders_reach_the_authoritative_world(server_url):
    """A separate CLI process joins seat one, develops it, and exits with useful evidence.

    The headless client plays against a real server for seconds: the slow tier."""
    with connect(server_url, proxy=None) as human:
        welcome = handshake(human, game="warband-v2", options={"seed": 3, "width": 48, "height": 40})
        initial = receive(human)["state"]["world"]
        result = subprocess.run(
            [sys.executable, "-m", "warband.online_ai", "--server", server_url,
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
        [sys.executable, "-m", "warband.online_ai", "--server", server_url, "--create",
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
        [sys.executable, "-m", "warband.online_ai", "--server", server_url, *arguments],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 1, result.stderr + result.stdout
    evidence = [json.loads(line) for line in result.stdout.splitlines()]
    assert evidence[-1]["event"] == "error" and error in evidence[-1]["error"]
    assert "resume_token" not in result.stdout
