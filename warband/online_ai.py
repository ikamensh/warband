"""A headless opponent connected through the normal online player protocol.

Create a room and print its shareable code immediately::

    python -m warband.online_ai --create --difficulty hard --duration 1800

Or join a human-created room::

    python -m warband.online_ai --server wss://games.tachyon-ai.eu/play --room CODE

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
from warband.ai import Brain
from warband.model import World, tile_center
from warband.rules import Difficulty, MapTheme

POLL_INTERVAL = 0.05
ORDER_INTERVAL = 0.08  # At most 12.5 orders/s, below the public server's 20/s allowance.
_BRAIN_ORDERS = frozenset({"move", "attack_move", "repair", "build", "train", "research", "set_rally"})


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
    """

    def __init__(self, data):
        self.world = World.from_dict(data)
        self.commands = []

    def __getattr__(self, name):
        if name in _BRAIN_ORDERS:
            return lambda *args, **kwargs: self._order(name, *args, **kwargs)
        return getattr(self.world, name)

    def _order(self, action, *args, **kwargs):
        # World accepts an empty selection as a no-op; the network requires one.
        if action in {"move", "attack_move", "repair"} and not args[0]:
            return None
        result = getattr(self.world, action)(*args, **kwargs)
        self.commands.append({"action": action, "args": _wire(args), "kwargs": _wire(kwargs)})
        return result

    def harvest(self, unit_ids, target, *, queue=False):
        # Harvest is a model command, while online players right-click resources.
        point = self.world.buildings[target].center if isinstance(target, int) else tile_center(target)
        return self._order("smart", unit_ids, point, queue=queue)


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


def run_bot(*, endpoint=None, room=None, difficulty=Difficulty.NORMAL, options=None,
            duration=None, wait_timeout=900.0, report_every=5.0,
            emit: Callable[[dict], None] = _print_event) -> dict:
    """Play the assigned online seat until victory or the wall-clock duration ends.

    With no room, create one using ``options``. ``duration`` includes lobby time;
    ``wait_timeout`` bounds each wait for a partner. Network/protocol failures
    raise; normal server order rejections are reported and discard pending plans.
    """
    for name, value in (("duration", duration), ("wait_timeout", wait_timeout), ("report_every", report_every)):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite.")
    started = waiting_since = time.monotonic()
    deadline = math.inf if duration is None else started + duration
    client = OnlineClient("warband-v1", endpoint=endpoint, room=room, options=options)
    brain = rng = None
    announced = ever_ready = last_ready = False
    revision = -1
    pending = deque()
    next_order = next_report = 0.0
    submitted = states = 0
    last_tick = 0
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
                brain = Brain(client.player, difficulty)
                announced = True
            if client.ready != last_ready:
                emit({"event": "match_ready" if client.ready else "match_paused", "revision": client.revision})
                if client.ready:
                    ever_ready = True
                else:
                    waiting_since = now
                    pending.clear()
                last_ready = client.ready
            if client.state is not None and client.revision != revision:
                revision = client.revision
                states += 1
                world = client.state["world"]
                last_tick = world["tick"]
                if now >= next_report:
                    emit(_state_evidence(client))
                    next_report = now + report_every
                if world["winner"] is not None:
                    reason = "winner"
                    break
            if now >= deadline:
                if not ever_ready:
                    raise TimeoutError("Bot duration expired before both players connected.")
                reason = "duration"
                break
            if not client.ready:
                if now - waiting_since >= wait_timeout:
                    raise TimeoutError("Timed out waiting for the other player to connect.")
            elif not pending and client.state["world"]["time"] >= brain.next_think:
                if rng is None:
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
                  "elapsed": round(time.monotonic() - started, 3), "tick": last_tick,
                  "states_received": states, "orders_submitted": submitted}
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
    parser.add_argument("--difficulty", choices=[item.value for item in Difficulty], default="normal")
    parser.add_argument("--duration", type=float, help="maximum wall-clock seconds including the lobby; default runs until victory")
    parser.add_argument("--wait-timeout", type=float, default=900, help="maximum seconds waiting for a partner (default: 900)")
    parser.add_argument("--report-every", type=float, default=5, help="seconds between authoritative evidence rows (default: 5)")
    parser.add_argument("--seed", type=int, default=3, help="map seed for --create")
    parser.add_argument("--width", type=int, default=48, help="map width for --create (40–64)")
    parser.add_argument("--height", type=int, default=40, help="map height for --create (32–48)")
    parser.add_argument("--theme", choices=[item.value for item in MapTheme], default="summer", help="map theme for --create")
    args = parser.parse_args(argv)
    try:
        run_bot(endpoint=args.server, room=args.room, difficulty=Difficulty(args.difficulty),
                options={"seed": args.seed, "width": args.width, "height": args.height, "theme": args.theme},
                duration=args.duration, wait_timeout=args.wait_timeout, report_every=args.report_every)
    except (CommandError, ConnectionError, TimeoutError, ValueError) as exc:
        _print_event({"event": "error", "error": str(exc)})
        return 1
    except KeyboardInterrupt:
        _print_event({"event": "interrupted"})
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
