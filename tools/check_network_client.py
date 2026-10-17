"""Play, watch and resume a current server using a historical client's actual decoder.

    uv run python tools/check_network_client.py --client-source /path/to/old/warband

The server imports this checkout; a separate process imports ``World`` and
``Event`` from the supplied source checkout. ``--client-python`` can select a
historical client's Python environment with its pinned Saga2D transport. This
probes game payload and transport compatibility, not the graphical client. A
decoding or protocol failure exits nonzero; success prints one JSON record
naming the decoder actually exercised.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from importlib.metadata import version
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = "warband.online.authority:ONLINE"


def catalog() -> dict[str, list[str]]:
    """Every enumerated wire value, including content a short match may never encounter."""
    from warband.sim import model, rules

    names = ("UnitType", "BuildingType", "Race", "Upgrade", "Terrain", "AttackType", "Resource", "MapTheme", "Layout")
    values = {name: sorted(member.value for member in getattr(rules, name)) for name in names}
    # This closed decoder registry is the authoritative spelling of queued orders on the wire.
    return {**values, "Buff": sorted(rules.BUFFS), "CampEncounter": sorted(rules.CAMP_ENCOUNTERS),
            "Order": sorted(model._ORDER_TYPES)}


def play(endpoint: str, client_source: Path, game_id: str) -> dict:
    """Exercise the live wire with the selected client's world and event constructors."""
    from saga2d.online import OnlineClient, PROTOCOL
    from warband.sim import model

    model_path = Path(model.__file__).resolve()
    if not model_path.is_relative_to(client_source / "warband"):
        raise RuntimeError(f"client decoder came from {model_path}, not {client_source}")

    event_kinds = set()
    supports_observer = "observer" in inspect.signature(OnlineClient).parameters
    checks = ["create", "join", "move"]

    def decode(state):
        world = model.World.from_dict(state["world"])
        for _index, fields in state["events"]:
            event = model.Event(**{**fields, "pos": tuple(fields["pos"])})
            event_kinds.add(event.kind)
        return world

    def wait(client, predicate=lambda world: True):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            client.poll()
            if client.error:
                raise RuntimeError(client.error)
            if client.state is not None:
                world = decode(client.state)
                if predicate(world):
                    return world
            time.sleep(.01)
        raise TimeoutError("historical client did not receive the expected authoritative state")

    with ExitStack() as clients:
        def connect(**options):
            client = OnlineClient(game_id, endpoint=endpoint, **options)
            clients.callback(client.close)
            return client

        host = connect(options={"seed": 3, "width": 48, "height": 40})
        host_world = wait(host)
        assert host_world.player_units(host.player), "creating seat has no own units"

        guest = connect(room=host.room)
        guest_world = wait(guest, lambda world: guest.ready)
        wait(host, lambda world: host.ready)
        own = guest_world.player_units(guest.player)[0]
        position = own.pos
        guest.submit({"action": "move", "args": [[own.id], [own.x - 2, own.y]]})
        moved_world = wait(guest, lambda world: world.units[own.id].pos != position
                           and type(world.units[own.id].order).__name__ == "Move")

        observer = None
        if supports_observer:
            observer = connect(room=host.room, observer=True)
            observed_world = wait(observer)
            assert observer.observer and observer.player is None
            for seat in (host.player, guest.player):
                assert observed_world.player_units(seat), f"observer cannot see seat {seat}"
            checks.append("observe")

        guest.close()
        paused_world = wait(host, lambda world: not host.ready)
        returned = connect(room=host.room, resume_token=guest.resume_token)
        resumed_world = wait(returned, lambda world: returned.ready)
        assert returned.player == guest.player, "resume changed the reserved seat"
        assert resumed_world.tick >= paused_world.tick >= moved_world.tick
        checks.append("resume")

        # A real public event reaches every role the historical transport supports.
        returned.submit({"action": "resign", "args": [returned.player]})
        wait(returned, lambda world: world.winner is not None)
        if observer is not None:
            wait(observer, lambda world: world.winner is not None)
        for client in (returned, observer) if observer is not None else (returned,):
            assert any(fields["kind"] == "resigned" for _index, fields in client.state["events"])

    assert "resigned" in event_kinds, "no real event reached the historical decoder"
    checks.append("events")
    return {"game_id": game_id, "client_model": str(model_path),
            "saga2d_version": version("saga2d"), "transport_protocol": PROTOCOL,
            "checks": checks, "unsupported_capabilities": [] if supports_observer else ["observe"],
            "moved_tick": moved_world.tick, "resumed_tick": resumed_world.tick}


def check(client_source: Path, game_id: str, client_python: str, client_saga2d: str | None) -> None:
    """Keep the current authority and historical decoder in independent import environments."""
    from saga2d.testing.online import running_server

    sys.path.insert(0, str(ROOT))
    server_catalog = catalog()
    with running_server(SPEC, cwd=ROOT) as (endpoint, _process):
        result = subprocess.run(
            [client_python, str(Path(__file__).resolve()), "--client-source", str(client_source),
             "--game-id", game_id, "--endpoint", endpoint,
             *(["--client-saga2d", client_saga2d] if client_saga2d else [])],
            cwd=client_source, env={**os.environ, "PYTHONPATH": str(client_source)},
            input=json.dumps(server_catalog), capture_output=True, text=True, timeout=30,
        )
        if result.returncode:
            sys.stderr.write(result.stderr)
            raise SystemExit(result.returncode)
        print(result.stdout, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client-source", type=Path, required=True,
                        help="historical source root containing warband/sim/model.py and its bundled constants")
    parser.add_argument("--game-id", help="the compatible server game id to exercise (default: current protocol)")
    parser.add_argument("--client-python", default=sys.executable,
                        help="Python executable with the historical client's pinned Saga2D (default: current Python)")
    parser.add_argument("--client-saga2d", help="require this exact Saga2D version in the historical client process")
    parser.add_argument("--endpoint", help=argparse.SUPPRESS)  # child process: imports only client_source's game
    args = parser.parse_args()
    source = args.client_source.resolve()
    if not (source / "warband/sim/model.py").is_file():
        parser.error(f"{source} does not contain warband/sim/model.py")
    if args.game_id is None:
        sys.path.insert(0, str(ROOT))
        from warband.online.protocol import GAME_ID

        args.game_id = GAME_ID
    if args.endpoint:
        if args.client_saga2d and version("saga2d") != args.client_saga2d:
            raise ValueError(f"historical client requires Saga2D {args.client_saga2d}, found {version('saga2d')}")
        known = catalog()
        for name, values in json.loads(sys.stdin.read()).items():
            unknown = sorted(set(values) - set(known[name]))
            if unknown:
                raise ValueError(f"historical client has unknown {name} values: {', '.join(unknown)}")
            removed = sorted(set(known[name]) - set(values))
            if removed:
                raise ValueError(f"server removed {name} values: {', '.join(removed)}")
        print(json.dumps(play(args.endpoint, source, args.game_id), sort_keys=True))
    else:
        executable = shutil.which(args.client_python)
        if executable is None:
            parser.error(f"cannot find client Python executable {args.client_python}")
        # Keep the venv's executable symlink: resolving it would select the base interpreter.
        check(source, args.game_id, str(Path(executable).absolute()), args.client_saga2d)


if __name__ == "__main__":
    main()
