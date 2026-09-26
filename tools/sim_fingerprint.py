"""A hash of whole simulated matches: the guard that a change was only a speed change.

    uv run python tools/sim_fingerprint.py              # print the fingerprint of the standard set
    uv run python tools/sim_fingerprint.py --check FILE # compare against a recorded one, exit 1 on drift

The fingerprint walks AI-vs-AI matches on fixed seeds and digests the exact
state every ten simulated seconds: unit positions as ``repr`` (so the float
bits themselves have to match, which is what lockstep online play needs),
hit points, orders, conditions, buildings, resources and upgrades.  Any optimisation of
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
from warband.sim.model import Event, World  # noqa: E402
from warband.sim.rules import SIM_DT, Difficulty, Race, Terrain, UnitType  # noqa: E402

SEEDS = (101, 102, 103, 104)
MINUTES = 6
#: Matches where a race's own unit goes to work (WB-068), Medium against Medium, orcs and elves, each before its cut
#: in minutes: on seed 89 a sapper goes up, on seed 2 a treant walks into the wood.  The standard set's matches are
#: decided before a side has the Keep, so without them the compiled simulation was never held to the source on that
#: code.  Chosen by playing seeds (the AI's timelines are chaotic), and a rules or AI change moves them: ``--check``
#: and ``--write`` refuse a fingerprint in which one no longer goes to work, so whoever refreshes the record picks again.
OWN_UNITS_MATCHES = ((89, (Race.ORC, Race.ELF), 6, UnitType.SAPPER), (2, (Race.ORC, Race.ELF), 6, UnitType.TREANT))
SAMPLE_EVERY = 200  # steps, i.e. ten simulated seconds


def digest_world(world: World, out: hashlib._Hash) -> None:
    out.update(f"t={world.time!r}|winner={world.winner}".encode())
    for unit in sorted(world.units.values(), key=lambda u: u.id):
        order = type(unit.order).__name__ if unit.order is not None else "-"
        out.update(f"U{unit.id},{unit.player},{unit.type.value},{unit.x!r},{unit.y!r},{unit.hp!r},"
                   f"{unit.carrying},{unit.inside},{len(unit.orders)},{order},"
                   f"{[(c.kind.key, c.until, c.player, c.worn) for c in unit.conditions]};".encode())
    for b in sorted(world.buildings.values(), key=lambda b: b.id):
        out.update(f"B{b.id},{b.player},{b.type.value},{b.x},{b.y},{b.hp!r},{b.progress!r},"
                   f"{len(b.queue)},{b.research};".encode())
    for p in world.players:
        out.update(f"P{p.id},{p.gold},{p.lumber},{p.aether},{p.alive},{sorted(u.value for u in p.upgrades)};".encode())


def at_work(world: World, events: list[Event], own: UnitType) -> bool:
    """Whether *own* is doing what its match is there for this step: a sapper's keg goes up, a treant stands in the wood."""
    if own is UnitType.SAPPER:
        return any(event.kind == "blast" for event in events)
    return any(unit.type is own and world.terrain_at((int(unit.x), int(unit.y))) is Terrain.TREES for unit in world.units.values())


def fingerprint(seeds=SEEDS, minutes: int = MINUTES, worked: dict[int, float] | None = None) -> str:
    """The hash; with *worked*, also when each own-unit match's unit first went to work, by seed."""
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
    for seed, races, own_minutes, own in OWN_UNITS_MATCHES:
        rng = random.Random(seed)
        world = mapgen.generate(seed=seed, players=2, human=None, races=races)
        brains = [make_brain(0, Difficulty.MEDIUM, seed), make_brain(1, Difficulty.MEDIUM, seed)]
        out.update(f"own={seed};".encode())
        for step in range(int(own_minutes * 60 / SIM_DT)):
            if world.winner is not None:
                break
            for b in brains:
                b.think(world, rng)
            world.step()
            events = world.take_events()
            if worked is not None and seed not in worked and at_work(world, events, own):
                worked[seed] = world.time
            if step % SAMPLE_EVERY == 0:
                digest_world(world, out)
        digest_world(world, out)
    return out.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", type=Path, help="a file holding a recorded fingerprint")
    parser.add_argument("--write", type=Path, help="record the fingerprint into this file")
    args = parser.parse_args()
    worked: dict[int, float] = {}
    got = fingerprint(worked=worked)
    print(got)
    for seed, _races, own_minutes, own in OWN_UNITS_MATCHES:
        print(f"own={seed}: {own.value} at work from {worked[seed]:.1f} s" if seed in worked else
              f"own={seed}: no {own.value} at work within {own_minutes} min")
    if (args.check or args.write) and len(worked) < len(OWN_UNITS_MATCHES):
        print("an own-unit match no longer holds its unit's code: pick another seed or cut (OWN_UNITS_MATCHES)", file=sys.stderr)
        raise SystemExit(1)
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
