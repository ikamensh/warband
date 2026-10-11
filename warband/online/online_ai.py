"""A headless opponent connected through the normal online player protocol.

Create a room and print its shareable code immediately::

    python -m warband.online.online_ai --create --difficulty hard --duration 1800

Or join a human-created room::

    python -m warband.online.online_ai --server wss://games.tachyon-ai.eu/play --room CODE

``--reconnect-after`` seconds after the match first goes ready, the bot
deliberately drops its connection once, sleeps ``--disconnect-for`` seconds,
then rejoins its reserved seat with the in-memory room code and resume token
(a public ``OnlineClient`` construction, never worker manipulation). It emits
``disconnected`` before the drop and ``rejoined`` after, with the assigned
player, the tick before and after, and its own entity ids as continuity
evidence. ``--require-completion`` turns a duration end with no declared
winner into a failure. The final ``finished`` event carries the winner the
server declared.

Output is JSON Lines. ``order_submitted`` means queued for the server;
``authoritative_state`` reports what the server actually accepted and simulated.
The protocol has no per-command acknowledgement. Private seat tokens are never
included in output. This client creates no window and never steps the world.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from enum import Enum
import json
import math
import random
import time
from typing import Callable

from saga2d import CommandError
from saga2d.online import OnlineClient, server_endpoint
from warband.brains.ai import make_brain
from warband.online.authority import GROUP_ORDERS, ORDERS
from warband.sim.model import World, tile_center
from warband.sim.rules import Difficulty, MapTheme

POLL_INTERVAL = 0.05
ORDER_INTERVAL = 0.08  # At most 12.5 orders/s, below the public server's 20/s allowance.


def _wire(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    return value


class _PlanningWorld:
    """Let Brain plan on a snapshot copy, recording the equivalent player orders.

    Applying each proposed order locally lets later decisions see spent resources
    and assigned workers. These speculative changes are never published as state.
    Every order the authority takes (``authority.ORDERS``) is sent, a harvest as
    the right-click it is online, and assigning idle workers stays on the copy,
    for the server does that for every seat each second. Any other order the world
    takes from a player is refused here: one that changed the copy alone was a
    decision the server never heard of (the brain hunted an intruder nobody attacked).
    """

    def __init__(self, data):
        self.world = World.from_dict(data)
        self.commands = []

    def __getattr__(self, name):
        if name in ORDERS:
            return lambda *args, **kwargs: self._order(name, *args, **kwargs)
        if getattr(getattr(World, name, None), "is_order", False):
            raise AttributeError(f"The online authority takes no {name} order, so a brain may not give it online")
        return getattr(self.world, name)

    def _order(self, action, *args, **kwargs):
        # World accepts an empty selection as a no-op; the network requires one.
        if action in GROUP_ORDERS and not args[0]:
            return None
        result = getattr(self.world, action)(*args, **kwargs)
        self.commands.append({"action": action, "args": _wire(args), "kwargs": _wire(kwargs)})
        return result

    def harvest(self, unit_ids, target, *, queue=False):
        # Harvest is a model command, while online players right-click resources.
        point = self.world.buildings[target].center if isinstance(target, int) else tile_center(target)
        return self._order("smart", unit_ids, point, queue=queue)

    def assign_workers(self, player):
        # The copy does it now for the decisions later in the same pass, which look at who is on gold and who on lumber.
        self.world.assign_workers(player)


def _state_evidence(client):
    world = client.state["world"]
    units = [unit for unit in world["units"] if unit["player"] == client.player]
    buildings = [building for building in world["buildings"] if building["player"] == client.player]
    player = world["players"][client.player]
    return {
        "event": "authoritative_state", "revision": client.revision, "tick": world["tick"],
        "world_time": world["time"], "ready": client.ready, "player": client.player,
        "gold": player["gold"], "lumber": player["lumber"], "units": len(units),
        "buildings": len(buildings), "winner": world["winner"],
        "order_counts": dict(Counter(unit["orders"][0]["kind"] for unit in units if unit["orders"])),
        "unit_orders": [{"unit": unit["id"], "order": unit["orders"][0]} for unit in units if unit["orders"]],
        "training_queue": sum(len(building["queue"]) for building in buildings),
        "researching": sum(building["research"] is not None for building in buildings),
    }


def _print_event(event):
    print(json.dumps(event, separators=(",", ":"), allow_nan=False), flush=True)


def _own_ids(client):
    """The bot seat's own unit and building ids in its latest authoritative state (public, own fields only)."""
    if client.state is None:
        return [], []
    world = client.state["world"]
    units = sorted(unit["id"] for unit in world["units"] if unit["player"] == client.player)
    buildings = sorted(building["id"] for building in world["buildings"] if building["player"] == client.player)
    return units, buildings


def run_bot(*, endpoint=None, room=None, difficulty=Difficulty.MEDIUM, options=None,
            duration=None, wait_timeout=900.0, report_every=5.0,
            reconnect_after=None, disconnect_for=2.0, require_completion=False,
            emit: Callable[[dict], None] = _print_event) -> dict:
    """Play the assigned online seat until victory or the wall-clock duration ends.

    With no room, create one using ``options``. ``duration`` includes lobby time;
    ``wait_timeout`` bounds each wait for a partner. Network/protocol failures
    raise; normal server order rejections are reported and discard pending plans.
    ``reconnect_after`` seconds after the match first goes ready, the bot drops
    its connection once and rejoins its reserved seat after ``disconnect_for``
    seconds; the rejoin is a public ``OnlineClient`` construction from the
    in-memory room code and resume token, with pending plans discarded. The
    brain itself is kept: it plans afresh on every authoritative snapshot, so
    the post-rejoin snapshot simply drives its next pass. ``require_completion``
    turns a duration end with no server-declared winner into a failure.
    """
    for name, value in (("duration", duration), ("wait_timeout", wait_timeout), ("report_every", report_every),
                        ("reconnect_after", reconnect_after), ("disconnect_for", disconnect_for)):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite.")
    started = waiting_since = time.monotonic()
    deadline = math.inf if duration is None else started + duration
    client = OnlineClient("warband-v2", endpoint=endpoint, room=room, options=options)
    brain = rng = None
    announced = ever_ready = last_ready = False
    first_ready_at = reconnected = awaiting_rejoin = False
    reconnected_player = -1
    before_tick = 0
    before_units: list = []
    before_buildings: list = []
    revision = -1
    pending = deque()
    next_order = next_report = 0.0
    submitted = states = 0
    last_tick = 0
    winner = None
    try:
        while True:
            client.poll()
            now = time.monotonic()
            if client.closed or (client.error and not client.ready):
                raise ConnectionError(client.error or "The online connection closed.")
            if client.error:
                emit({"event": "order_rejected", "error": client.error, "revision": client.revision})
                client.error = ""
                pending.clear()
            if client.resume_token and not announced:
                emit({"event": "joined" if room else "created", "room": client.room,
                      "player": client.player, "difficulty": difficulty.value})
                announced = True
            if client.ready != last_ready:
                emit({"event": "match_ready" if client.ready else "match_paused", "revision": client.revision})
                if client.ready:
                    ever_ready = True
                    if not first_ready_at:
                        first_ready_at = now
                else:
                    waiting_since = now
                    pending.clear()
                last_ready = client.ready
            if client.state is not None and client.revision != revision:
                revision = client.revision
                states += 1
                world = client.state["world"]
                last_tick = world["tick"]
                if awaiting_rejoin:
                    awaiting_rejoin = False
                    after_units, after_buildings = _own_ids(client)
                    if client.player != reconnected_player:
                        raise ConnectionError(
                            f"Rejoined as player {client.player} instead of the reserved seat {reconnected_player}.")
                    emit({"event": "rejoined", "player": client.player, "revision": client.revision,
                          "before_tick": before_tick, "tick": last_tick,
                          "before_units": before_units, "units": after_units,
                          "before_buildings": before_buildings, "buildings": after_buildings})
                if now >= next_report:
                    emit(_state_evidence(client))
                    next_report = now + report_every
                if world["winner"] is not None:
                    winner = world["winner"]
                    reason = "winner"
                    break
            if now >= deadline:
                if not ever_ready:
                    raise TimeoutError("Bot duration expired before both players connected.")
                if require_completion:
                    raise TimeoutError("Bot duration expired before the server declared a winner.")
                reason = "duration"
                break
            if (reconnect_after is not None and not reconnected and ever_ready and client.ready
                    and client.state is not None and now - first_ready_at >= reconnect_after):
                if not client.resume_token:
                    raise ConnectionError("Cannot rejoin the reserved seat without a resume token.")
                reconnected_player = client.player
                before_tick = last_tick
                before_units, before_buildings = _own_ids(client)
                emit({"event": "disconnected", "player": client.player, "revision": client.revision,
                      "tick": last_tick, "units": before_units, "buildings": before_buildings})
                resume_room, resume_token = client.room, client.resume_token
                pending.clear()
                client.close()
                time.sleep(disconnect_for)
                # The seat stays reserved on the server; rejoin it as any player client would.
                # (Ordinary construction only: rated/identity arguments arrive with the new engine.)
                client = OnlineClient("warband-v2", endpoint=endpoint, room=resume_room, resume_token=resume_token)
                pending.clear()
                reconnected = True
                awaiting_rejoin = True
                revision = -1
                continue
            if not client.ready:
                if now - waiting_since >= wait_timeout:
                    raise TimeoutError("Timed out waiting for the other player to connect.")
            elif not pending and (brain is None or client.state["world"]["time"] >= brain.next_think):
                if brain is None:
                    # The map's seed draws Master's posture, and a joiner learns it with the state.
                    brain = make_brain(client.player, difficulty, client.state["seed"])
                    rng = random.Random(client.state["seed"] * 2 + client.player)
                planning = _PlanningWorld(client.state["world"])
                brain.think(planning, rng)
                pending.extend(planning.commands)
            if client.ready and pending and now >= next_order:
                command = pending.popleft()
                client.submit(command)
                submitted += 1
                emit({"event": "order_submitted", "sequence": submitted,
                      "revision": client.revision, "tick": last_tick, "command": command})
                next_order = now + ORDER_INTERVAL
            time.sleep(min(POLL_INTERVAL, max(0.0, deadline - time.monotonic())))
        emit(_state_evidence(client))
        result = {"event": "finished", "reason": reason, "room": client.room, "player": client.player,
                  "elapsed": round(time.monotonic() - started, 3), "tick": last_tick, "winner": winner,
                  "states_received": states, "orders_submitted": submitted,
                  "reconnected": bool(reconnected)}
        emit(result)
        return result
    finally:
        client.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Play an online Warband seat with a headless AI; emit JSON Lines.")
    parser.add_argument("--server", default=server_endpoint(), help="public wss:// endpoint (loopback ws:// accepted)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--room", help="join this human-created room as the second seat")
    mode.add_argument("--create", action="store_true", help="create a room, play seat zero and immediately print its code")
    parser.add_argument("--difficulty", choices=[item.value for item in Difficulty], default="medium")
    parser.add_argument("--duration", type=float, help="maximum wall-clock seconds including the lobby; default runs until victory")
    parser.add_argument("--wait-timeout", type=float, default=900, help="maximum seconds waiting for a partner (default: 900)")
    parser.add_argument("--report-every", type=float, default=5, help="seconds between authoritative evidence rows (default: 5)")
    parser.add_argument("--reconnect-after", type=float, default=None,
                        help="deliberately disconnect once this many seconds after first ready, then rejoin the reserved seat")
    parser.add_argument("--disconnect-for", type=float, default=2.0,
                        help="seconds to stay disconnected before rejoining (default: 2)")
    parser.add_argument("--require-completion", action="store_true",
                        help="fail a duration end unless the server actually declared a winner")
    parser.add_argument("--seed", type=int, default=3, help="map seed for --create")
    parser.add_argument("--width", type=int, default=48, help="map width for --create (48–80)")
    parser.add_argument("--height", type=int, default=40, help="map height for --create (40–64)")
    parser.add_argument("--theme", choices=[item.value for item in MapTheme], default="summer", help="map theme for --create")
    args = parser.parse_args(argv)
    try:
        run_bot(endpoint=args.server, room=args.room, difficulty=Difficulty(args.difficulty),
                options={"seed": args.seed, "width": args.width, "height": args.height, "theme": args.theme},
                duration=args.duration, wait_timeout=args.wait_timeout, report_every=args.report_every,
                reconnect_after=args.reconnect_after, disconnect_for=args.disconnect_for,
                require_completion=args.require_completion)
    except (CommandError, ConnectionError, TimeoutError, ValueError) as exc:
        _print_event({"event": "error", "error": str(exc)})
        return 1
    except KeyboardInterrupt:
        _print_event({"event": "interrupted"})
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
