"""A hash of whole simulated matches: the guard that a change was only a speed change.

    uv run python tools/sim_fingerprint.py              # print the fingerprint of the standard set
    uv run python tools/sim_fingerprint.py --check FILE # compare against a recorded one, exit 1 on drift

The fingerprint walks AI-vs-AI matches on fixed seeds and digests the exact
state every ten simulated seconds: unit positions as ``repr`` (so the float
bits themselves have to match, which is what lockstep online play needs),
hit points, orders, buildings, resources and upgrades.  Any optimisation of
the model, the pathfinder or the worker policy must leave this unchanged;
a deliberate rules or AI change is expected to move it, and the recorded
file is then refreshed in the same commit.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.sim import mapgen  # noqa: E402
from warband.brains.ai import make_brain  # noqa: E402
from warband.sim.model import World  # noqa: E402
from warband.sim.rules import SIM_DT, Difficulty  # noqa: E402

SEEDS = (101, 102, 103, 104)
MINUTES = 6
SAMPLE_EVERY = 200  # steps, i.e. ten simulated seconds


def digest_world(world: World, out: hashlib._Hash) -> None:
    out.update(f"t={world.time!r}|winner={world.winner}".encode())
    for unit in sorted(world.units.values(), key=lambda u: u.id):
        order = type(unit.order).__name__ if unit.order is not None else "-"
        out.update(f"U{unit.id},{unit.player},{unit.type.value},{unit.x!r},{unit.y!r},{unit.hp!r},"
                   f"{unit.carrying},{unit.inside},{len(unit.orders)},{order};".encode())
    for b in sorted(world.buildings.values(), key=lambda b: b.id):
        out.update(f"B{b.id},{b.player},{b.type.value},{b.x},{b.y},{b.hp!r},{b.progress!r},"
                   f"{len(b.queue)},{b.research};".encode())
    for p in world.players:
        out.update(f"P{p.id},{p.gold},{p.lumber},{p.alive},{sorted(u.value for u in p.upgrades)};".encode())


def fingerprint(seeds=SEEDS, minutes: int = MINUTES) -> str:
    out = hashlib.sha256()
    for seed in seeds:
        rng = random.Random(seed)
        world = mapgen.generate(seed=seed, players=2, human=None)
        brains = [make_brain(0, Difficulty.HARD), make_brain(1, Difficulty.MEDIUM)]
        out.update(f"seed={seed};".encode())
        for step in range(int(minutes * 60 / SIM_DT)):
            if world.winner is not None:
                break
            for b in brains:
                b.think(world, rng)
            world.step()
            world.take_events()
            if step % SAMPLE_EVERY == 0:
                digest_world(world, out)
        digest_world(world, out)
    return out.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", type=Path, help="a file holding a recorded fingerprint")
    parser.add_argument("--write", type=Path, help="record the fingerprint into this file")
    args = parser.parse_args()
    got = fingerprint()
    print(got)
    if args.write:
        args.write.write_text(got + "\n")
    if args.check:
        want = args.check.read_text().strip()
        if want != got:
            print(f"DRIFT: recorded {want}, got {got}", file=sys.stderr)
            raise SystemExit(1)
        print("matches the recorded fingerprint")


if __name__ == "__main__":
    main()
