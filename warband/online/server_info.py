"""Ask a room server how busy it is, without starting the game.

``warband --server-info`` prints the server's players, rooms and capacity;
:func:`server_info` returns the same validated mapping for in-game callers.
Both speak the server's public ``GET /status`` contract and nothing else: no
room codes, no tokens, no simulation, no window.  :func:`server_info` blocks
on the network, so the game calls it off its UI thread.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any
from urllib import error as urlerror
from urllib import parse, request

#: Seconds :func:`server_info` waits per connection/read step unless asked otherwise.
DEFAULT_TIMEOUT = 10.0
#: The largest status answer read; anything bigger is refused, not truncated.
MAX_PAYLOAD = 256 * 1024
#: Plain ``ws`` endpoints are only this server's own machine (the engine's policy in ``saga2d.online``).
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
#: Counts the contract reports as exact integers: rooms, readiness, players and capacity.
COUNTS = ("protocol", "rooms", "ready_rooms", "players", "max_rooms", "max_connections")
#: Durations the contract reports as numbers: whole seconds or fractions, always finite and positive.
DURATIONS = ("room_retention", "campaign_retention")


class ServerInfoError(Exception):
    """The server's status cannot be reported: unreachable, refusing, or misshapen."""


def default_endpoint() -> str:
    """The room endpoint the game would connect to (``SAGA2D_SERVER_URL`` or the live server)."""
    from saga2d.online import server_endpoint

    return server_endpoint()


def status_url(endpoint: str) -> str:
    """The ``http(s)`` status page at a ``ws(s)`` room endpoint's origin.

    ``wss`` becomes ``https`` and ``ws`` becomes ``http``; the path is always
    ``/status``, whatever the endpoint's own path is.  The endpoint itself is
    held to the engine's policy: ``wss``, or plain ``ws`` only on this
    machine, no user info, no fragment, a real port.
    """
    parts = parse.urlsplit(endpoint)
    if parts.scheme not in ("ws", "wss") or not parts.hostname:
        raise ServerInfoError(f"Use a wss:// server address, not {endpoint!r}.")
    if parts.username or parts.password or parts.fragment:
        raise ServerInfoError(f"Use a plain wss:// server address, not {endpoint!r}.")
    if parts.scheme == "ws" and parts.hostname not in LOCAL_HOSTS:
        raise ServerInfoError("Online connections require TLS (wss://); plain ws is only for a local server.")
    try:
        port = parts.port
    except ValueError:
        raise ServerInfoError(f"Use a server port between 1 and 65535, not {endpoint!r}.") from None
    if port == 0:
        raise ServerInfoError("The server port must be between 1 and 65535.")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return parse.urlunsplit((("https" if parts.scheme == "wss" else "http"),
                             f"{host}:{port}" if port else host, "/status", "", ""))


def _is_number(value: Any) -> bool:
    """Whether *value* is a positive finite number (an int or a float, never a boolean)."""
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate_status(payload: Any, url: str = "server") -> dict[str, Any]:
    """The contract's fields with their types proven, or a :class:`ServerInfoError`.

    Counts are exact integers (never booleans, never strings), durations
    positive finite numbers kept as sent, the games a list of names, the
    ratings a table of per-game ``enabled`` flags with the known optional
    ``seats`` and ``starting_rating`` preserved, and the known optional
    ``rated_grace`` preserved too.  Unknown newer fields pass through
    ignored, so a newer server stays readable.
    """
    if not isinstance(payload, dict):
        raise ServerInfoError(f"The server status at {url} is not a JSON object.")
    for key in COUNTS:
        if type(payload.get(key)) is not int or payload[key] < 0:
            raise ServerInfoError(f"The server status at {url} has no integer {key!r}.")
    for key in DURATIONS:
        if not _is_number(payload.get(key)):
            raise ServerInfoError(f"The server status at {url} has no positive {key!r} duration.")
    if not isinstance(payload.get("games"), list) or not all(isinstance(name, str) for name in payload["games"]):
        raise ServerInfoError(f"The server status at {url} has no games list.")
    ratings = payload.get("ratings")
    if not isinstance(ratings, dict):
        raise ServerInfoError(f"The server status at {url} has no ratings table.")
    kept_ratings = {}
    for game, flags in ratings.items():
        if not isinstance(flags, dict) or type(flags.get("enabled")) is not bool:
            raise ServerInfoError(f"The server status at {url} has no ratings flag for {game!r}.")
        kept = {"enabled": flags["enabled"]}
        if "seats" in flags:
            if (not isinstance(flags["seats"], list)
                    or not all(type(seats) is int and seats > 0 for seats in flags["seats"])):
                raise ServerInfoError(f"The server status at {url} has no seat list for {game!r}.")
            kept["seats"] = list(flags["seats"])
        if "starting_rating" in flags:
            if not _is_number(flags["starting_rating"]):
                raise ServerInfoError(f"The server status at {url} has no positive starting rating for {game!r}.")
            kept["starting_rating"] = flags["starting_rating"]
        kept_ratings[game] = kept
    kept = {"protocol": payload["protocol"], "games": list(payload["games"]),
            "rooms": payload["rooms"], "ready_rooms": payload["ready_rooms"], "players": payload["players"],
            "max_rooms": payload["max_rooms"], "max_connections": payload["max_connections"],
            "room_retention": payload["room_retention"], "campaign_retention": payload["campaign_retention"],
            "ratings": kept_ratings}
    if "rated_grace" in payload:
        if not _is_number(payload["rated_grace"]):
            raise ServerInfoError(f"The server status at {url} has no positive 'rated_grace' duration.")
        kept["rated_grace"] = payload["rated_grace"]
    return kept


def server_info(endpoint: str | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Fetch and validate one server's status: its games, rooms, players, capacity and retention.

    ``endpoint`` defaults to :func:`default_endpoint`; ``timeout`` bounds each
    connection and read step in seconds (socket semantics, not the whole
    request).  Raises :class:`ServerInfoError` with an actionable message
    when the server cannot be reached or its answer is not the contract —
    never a guess.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout < math.inf:
        raise ServerInfoError(f"Wait a positive number of seconds for the server, not {timeout!r}.")
    resolved = endpoint or default_endpoint()
    url = status_url(resolved)
    # Like the game's own client (which connects with no proxy), go direct:
    # a proxy's block page is not a server status, and its address varies by machine.
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            if response.status != 200:
                raise ServerInfoError(f"The server status at {url} answered HTTP {response.status}.")
            body = response.read(MAX_PAYLOAD + 1)
    except urlerror.HTTPError as exc:
        raise ServerInfoError(f"The server status at {url} answered HTTP {exc.code}.") from None
    except (urlerror.URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, urlerror.URLError) else exc
        raise ServerInfoError(f"Cannot reach the server status at {url}: {reason}. "
                              "Check the address and that the server is running.") from None
    if len(body) > MAX_PAYLOAD:
        raise ServerInfoError(f"The server status at {url} is larger than {MAX_PAYLOAD} bytes; refusing it.")
    try:
        payload = json.loads(body)
    except ValueError:
        raise ServerInfoError(f"The server status at {url} is not JSON.") from None
    return {"endpoint": resolved, "status_url": url, **validate_status(payload, url)}


def _duration(seconds: int | float) -> str:
    """A retention in its largest whole unit: 900 as 15m, 86400 as 1d, a fraction as seconds."""
    whole = int(seconds) if isinstance(seconds, float) and seconds.is_integer() else seconds
    if isinstance(whole, int) and whole > 0:
        if whole % 86400 == 0:
            return f"{whole // 86400}d"
        if whole % 3600 == 0:
            return f"{whole // 3600}h"
        if whole % 60 == 0:
            return f"{whole // 60}m"
        return f"{whole}s"
    return f"{seconds}s"


def _ratings_text(ratings: dict[str, dict[str, Any]]) -> str:
    """One game's rating state: its name, its seats when known, whether ratings are on."""
    parts = []
    for game, flags in ratings.items():
        seats = "/".join(str(seats) for seats in flags["seats"]) if "seats" in flags else ""
        parts.append(f"{game}{' (seats ' + seats + ')' if seats else ''} "
                     f"{'enabled' if flags['enabled'] else 'disabled'}")
    return ", ".join(parts) or "none reported"


def format_text(info: dict[str, Any]) -> str:
    """The status as readable lines: the endpoint, whether it is online, players, rooms and limits."""
    ratings = _ratings_text(info["ratings"])
    lines = [
        f"Warband server: {info['endpoint']}",
        f"Status: online (protocol {info['protocol']})",
        f"Players online: {info['players']}",
        f"Rooms: {info['ready_rooms']} ready of {info['rooms']} (up to {info['max_rooms']} rooms, "
        f"{info['max_connections']} connections)",
        f"Room retention: {_duration(info['room_retention'])}; campaign retention: "
        f"{_duration(info['campaign_retention'])}",
        f"Games: {', '.join(info['games']) or 'none reported'}",
        f"Ratings: {ratings}",
    ]
    if "rated_grace" in info:
        lines.append(f"Rated grace: {_duration(info['rated_grace'])}")
    return "\n".join(lines)


def run(argv: list[str]) -> None:
    """Answer ``--server-info`` and exit: print the status, or fail nonzero with an actionable error."""
    parser = argparse.ArgumentParser(prog="warband",
                                     description="Ask the Warband room server how busy it is, without starting the game.")
    parser.add_argument("--server-info", action="store_true", required=True,
                        help="ask the room server for its status and exit")
    parser.add_argument("--server", metavar="URL", default=None,
                        help=f"room server endpoint (default {default_endpoint()})")
    parser.add_argument("--json", action="store_true", help="print the validated status as JSON")
    parser.add_argument("--timeout", metavar="SECONDS", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds to wait per connection/read step (default {DEFAULT_TIMEOUT:g})")
    args = parser.parse_args(argv)
    try:
        info = server_info(args.server, timeout=args.timeout)
    except ServerInfoError as exc:
        parser.exit(1, f"warband: {exc}\n")
    print(json.dumps(info, indent=2) if args.json else format_text(info))
