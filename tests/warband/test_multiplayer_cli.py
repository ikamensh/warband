"""Command-line multiplayer rooms behave like the Multiplayer screen's rooms.

Each slow test drives the public CLI helpers in :mod:`warband.__main__` against a
real room-server subprocess on loopback: hosting, joining with the command line's
own race, resuming a saved seat, and settling a rated room.  One mock-backend Game
holds the CLI lobby while raw :class:`OnlineClient` partners fill the other seats
(the engine allows a single Game at a time).  A real server process, real
WebSockets and the server's real clock make these the slow tier; the refusal
checks at the start need no server and stay fast.  No test fakes the server or
the client: every assertion reads public session state, saved records, or the
authoritative receipt.
"""

import json
import time

import pytest

from saga2d import Game
from saga2d.online import OnlineClient
from saga2d.testing.online import server_fixture

server_url = server_fixture("warband.online.authority:ONLINE")

from warband.__main__ import cli_parser, lobby_options, multiplayer_lobby
from warband.ui.multiplayer import NetworkGameScene, WarbandLobby
from warband.ui.scene import DEFAULT_SETTINGS
from warband.ui.style import build_theme


def make_game(tmp_path, tag):
    """A headless game with its own saved records for the CLI seat under test."""
    return Game(f"cli {tag}", backend="mock", resolution=(1280, 800),
                theme=build_theme(), save_dir=tmp_path / f"{tag}-saves")


def drive(game, partners, until, seconds=25):
    """Tick the pushed lobby and poll raw partners until *until* holds."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        game.tick(1 / 30)
        for partner in partners:
            partner.poll()
        if until():
            return
        time.sleep(0.01)
    raise AssertionError("CLI room did not converge")


def test_cli_parser_offers_rated_for_online_hosts():
    """The new flag is spelled out next to the room flags it belongs to."""
    args = cli_parser().parse_args(["--online-host", "--rated"])
    assert args.rated and args.online_host
    assert cli_parser().parse_args([]).rated is False


def test_cli_rated_without_host_is_refused():
    """Joins follow the host's room and rejoin keeps its room, so only hosting takes --rated."""
    parser = cli_parser()
    for argv in (["--online-join", "ABCD", "--rated"], ["--online-resume", "--rated"], ["--rated"]):
        with pytest.raises(SystemExit):
            multiplayer_lobby(parser.parse_args(argv), parser, None, None)


def test_cli_online_host_rejects_sixteen_seats():
    """A flag combination the rooms cannot hold is refused, never silently re-seated."""
    parser = cli_parser()
    with pytest.raises(SystemExit):
        multiplayer_lobby(parser.parse_args(["--online-host", "--players", "16"]), parser, None, None)


def test_cli_lobby_options_rejects_oversize_and_bad_seats():
    """Options the rooms cannot hold are refused clearly instead of hosting another map."""
    parser = cli_parser()
    args = parser.parse_args(["--size", "Huge", "--players", "2"])
    with pytest.raises(ValueError, match="larger than online rooms hold"):
        lobby_options(args, players=2)
    args = parser.parse_args(["--players", "5"])
    with pytest.raises(ValueError, match="2 to 4"):
        lobby_options(args, players=5)


@pytest.mark.slow
def test_cli_host_and_join_choose_own_factions(server_url, tmp_path):
    """The host's and the guest's races each reach their own seat through the CLI.

    A real server subprocess pairs the CLI lobby with a raw joining seat; the welcome
    round-trips and the host's fair map take seconds, so slow.
    """
    game = make_game(tmp_path, "factions")
    partner = None
    try:
        lobby = multiplayer_lobby(
            cli_parser().parse_args(["--online-host", "--seed", "3", "--race", "orc", "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        assert isinstance(lobby, WarbandLobby)
        game.push(lobby)
        drive(game, (), until=lambda: bool(lobby.session.room))
        partner = OnlineClient("warband-v2", endpoint=server_url, room=lobby.session.room,
                               player_name="Guest", player_options={"race": "elf"})
        drive(game, (partner,), until=lambda: lobby.session.ready and partner.ready)
        assert lobby.session.rated is False and partner.rated is False
        assert [player["race"] for player in lobby.session.state["world"]["players"]][:2] == ["orc", "elf"]
    finally:
        if partner is not None:
            partner.close()
        game.close()


@pytest.mark.slow
def test_cli_rated_room_settles_one_receipt(server_url, tmp_path):
    """A rated CLI room settles exactly one authoritative receipt when a seat resigns.

    Resigning through the validated order, waiting out the settle publish and reading
    both receipts off real sessions needs the server process, so slow.
    """
    game = make_game(tmp_path, "rated")
    partner = None
    try:
        lobby = multiplayer_lobby(
            cli_parser().parse_args(["--online-host", "--seed", "3", "--rated", "--race", "dwarf",
                                     "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        game.push(lobby)
        drive(game, (), until=lambda: bool(lobby.session.room))
        partner = OnlineClient("warband-v2", endpoint=server_url, room=lobby.session.room,
                               player_name="Guest", player_options={"race": "human"})
        drive(game, (partner,), until=lambda: lobby.session.ready and partner.ready)
        assert lobby.session.rated and partner.rated
        match_id = lobby.session.match_id
        assert match_id
        partner.submit({"action": "resign", "args": [1]})
        drive(game, (partner,), until=lambda: lobby.session.result is not None and partner.result is not None)
        assert partner.result == lobby.session.result
        result = lobby.session.result
        assert result["match_id"] == match_id and result["winner"] == 0
        ratings = {entry["player_id"]: entry for entry in result["ratings"]}
        host_entry = ratings[lobby.session.player_id]
        guest_entry = ratings[partner.player_id]
        assert host_entry["delta"] + guest_entry["delta"] == pytest.approx(0.0)
        assert (host_entry["games"], host_entry["wins"], host_entry["losses"]) == (1, 1, 0)
        assert (guest_entry["games"], guest_entry["wins"], guest_entry["losses"]) == (1, 0, 1)
    finally:
        if partner is not None:
            partner.close()
        game.close()


@pytest.mark.slow
def test_cli_identity_persists_across_rooms(server_url, tmp_path):
    """The durable account survives a second room on the same computer.

    Two creates on real connections take seconds, so slow.  The token assertions read
    the saved identity file and live sessions only; the account is never printed.
    """
    game = make_game(tmp_path, "keeping")
    try:
        first = multiplayer_lobby(
            cli_parser().parse_args(["--online-host", "--seed", "3", "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        game.push(first)
        drive(game, (), until=lambda: bool(first.session.player_token))
        first_token, first_id = first.session.player_token, first.session.player_id
        stored = json.loads((game.data_dir / "online-identity.json").read_text())
        assert stored["tokens"][server_url] == first_token
        first.session.close()
        game.pop()

        second = multiplayer_lobby(
            cli_parser().parse_args(["--online-host", "--seed", "5", "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        game.push(second)
        drive(game, (), until=lambda: bool(second.session.player_id))
        assert second.session.player_token == first_token
        assert second.session.player_id == first_id
    finally:
        game.close()


@pytest.mark.slow
def test_cli_resume_rejoins_the_saved_seat(server_url, tmp_path):
    """A dropped CLI seat rejoins its room with --online-resume, on the same identity.

    Joining, dropping and resuming over real connections take seconds, so slow.  The
    resume sends the saved endpoint identity with no race override: the seat rejoins
    rather than re-choosing.
    """
    game = make_game(tmp_path, "rejoin")
    partner = None
    try:
        partner = OnlineClient("warband-v2", endpoint=server_url,
                               options={"seed": 3, "width": 48, "height": 40},
                               player_name="Host")
        deadline = time.monotonic() + 25
        while not partner.room and time.monotonic() < deadline:
            partner.poll()
            time.sleep(0.01)
        assert partner.room
        lobby = multiplayer_lobby(
            cli_parser().parse_args(["--online-join", partner.room, "--race", "elf", "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        assert isinstance(lobby, WarbandLobby)
        game.push(lobby)
        drive(game, (partner,), until=lambda: lobby.session.ready and partner.ready)
        guest_id, guest_room = lobby.session.player_id, lobby.session.room
        assert lobby.session.state["world"]["players"][1]["race"] == "elf"
        lobby.session.close()
        game.pop()

        resume = multiplayer_lobby(
            cli_parser().parse_args(["--online-resume", "--server", server_url]),
            cli_parser(), game, game.settings(DEFAULT_SETTINGS))
        assert isinstance(resume, WarbandLobby)
        assert resume.session.room == guest_room
        game.push(resume)
        drive(game, (partner,), until=lambda: resume.session.ready)
        assert resume.session.room == guest_room
        assert resume.session.player_id == guest_id
        assert resume.session.player == 1
        assert isinstance(game.scene, NetworkGameScene)
    finally:
        if partner is not None:
            partner.close()
        game.close()


@pytest.mark.slow
def test_cli_four_seat_host_options_reach_the_server(server_url, tmp_path):
    """A --players 4 host asks for four seats and the server holds that room.

    Creating a four-seat fair map and waiting for the create welcome takes seconds, so slow.
    """
    parser = cli_parser()
    args = parser.parse_args(["--online-host", "--players", "4", "--seed", "5", "--server", server_url])
    options = lobby_options(args, players=4)
    assert options["players"] == 4 and len(options["races"]) == 4
    assert options["races"][0] == "human" and set(options["races"][1:]) == {None}
    game = make_game(tmp_path, "four")
    try:
        lobby = multiplayer_lobby(args, parser, game, game.settings(DEFAULT_SETTINGS))
        assert isinstance(lobby, WarbandLobby)
        game.push(lobby)
        drive(game, (), until=lambda: lobby.session.state is not None)
        assert lobby.session.seats == 4
    finally:
        game.close()
