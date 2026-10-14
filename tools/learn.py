"""Learn the stance policy's weights by evolution strategies over match outcomes.

    uv run python tools/learn.py run --out ~/saga/evidence/warband/ai-apex/policy-1 --generations 30
    uv run python tools/learn.py show ~/saga/evidence/warband/ai-apex/policy-1
    uv run python tools/learn.py export ~/saga/evidence/warband/ai-apex/policy-1

The policy is the linear table in :mod:`warband.brains.policy` — a stance
chosen every five seconds from fog-honest features.  This trains it the way
``tools/evolve.py`` breeds postures, by (mu+lambda) evolution strategies on
the weight vector: offspring are a parent plus Gaussian noise, fitness is
the mean score against a small panel on boards the parents never saw,
rotating every generation.  `export` prints the best table as the LEARNED
literal to paste into ``brains/policy.py`` — the distillation is the paste.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()

import numpy as np  # noqa: E402

from warband.brains.apex3 import APEX3, APEX3_FOR_LAYOUT  # noqa: E402
from warband.brains.policy import FEATURE_NAMES, STANCES, PolicyBrain  # noqa: E402
from warband.league import arena  # noqa: E402
from warband.sim import mapgen  # noqa: E402
from warband.sim.rules import SIM_DT, BuildingType, Layout, MapTheme, Race  # noqa: E402

DIM = len(STANCES) * len(FEATURE_NAMES)
DEFAULT_PANEL = ("grandmaster", "apex2", "apex3")


def _rows(vector) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(v) for v in row) for row in np.asarray(vector).reshape(len(STANCES), -1))


def _play(task) -> float:
    """One game for one weight vector against one panellist; returns the policy's score (0..1)."""
    vector, seed, opponent, corner = task
    board = arena.board(seed)
    layout = board.pop("layout")
    world = mapgen.generate(seed=seed, players=2, human=None, layout=Layout(layout), **board)
    weights = _rows(vector)
    if corner == 0:
        brains = [PolicyBrain(0, APEX3, seed, weights, APEX3_FOR_LAYOUT), arena.make_agent(opponent, 1, seed)]
    else:
        brains = [arena.make_agent(opponent, 0, seed), PolicyBrain(1, APEX3, seed, weights, APEX3_FOR_LAYOUT)]
    rngs = [random.Random(seed * 1000003 + player) for player in range(2)]
    eliminated: dict[int, float] = {}
    leader, leader_since, settled, steps = None, 0.0, None, 0
    for _ in range(int(20 * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for brain, rng in zip(brains, rngs):
            brain.think(world, rng)
        world.step()
        world.take_events()
        steps += 1
        for player in world.players[:2]:
            if not player.alive and player.id not in eliminated:
                eliminated[player.id] = world.time
        if steps % arena.SETTLED_EVERY == 0:
            ahead = arena._runaway(world, eliminated, 2)
            if ahead is None or ahead != leader:
                leader, leader_since = ahead, world.time
            elif world.time - leader_since >= arena.SETTLED_SECONDS:
                settled = leader
                break
    winner = world.winner if world.winner is not None else settled
    mine, theirs = (0, 1) if corner == 0 else (1, 0)
    if winner is not None:
        return 1.0 if winner == mine else 0.0
    placements = arena._placements(world, eliminated, 2)
    return 1.0 if placements[mine] < placements[theirs] else 0.5 if placements[mine] == placements[theirs] else 0.0


def _fitness(pool, vectors, panel, seeds, first_seed) -> list[float]:
    tasks = [(vector, seed, opponent, corner)
             for vector in vectors for opponent in panel
             for seed in range(first_seed, first_seed + seeds) for corner in (0, 1)]
    per = len(tasks) // len(vectors)
    scores = pool.map(_play, tasks)
    return [float(np.mean(scores[i * per:(i + 1) * per])) for i in range(len(vectors))]


def _save(out: Path, generation: int, parents, fitness, history, settings) -> None:
    out.mkdir(parents=True, exist_ok=True)
    row = {"generation": generation, "parents": [list(map(float, p)) for p in parents],
           "fitness": fitness, "history": history, "settings": settings}
    (out / "latest.json").write_text(json.dumps(row), encoding="utf-8")


def _run(args) -> None:
    out = Path(args.out).expanduser()
    rng = np.random.default_rng(args.seed)
    settings = {"population": args.population, "parents": args.parents, "seeds": args.seeds,
                "panel": list(args.panel.split(",")), "first_seed": args.first_seed, "seed": args.seed,
                "sigma": args.sigma}
    if (out / "latest.json").exists():
        row = json.loads((out / "latest.json").read_text())
        parents = [np.array(p) for p in row["parents"]]
        history, generation = row["history"], row["generation"]
        print(f"carrying on {out} from generation {generation}", flush=True)
    else:
        parents = [np.zeros(DIM)] + [rng.normal(0, args.sigma, DIM) for _ in range(args.parents - 1)]
        history, generation = [], 0
    panel = settings["panel"]
    with mp.get_context("spawn").Pool(args.workers) as pool:
        for step in range(args.generations):
            sigma = max(0.05, args.sigma * 0.97 ** generation)
            offspring = [p + rng.normal(0, sigma, DIM) for p in parents
                         for _ in range(args.population // len(parents))]
            vectors = [*parents, *offspring]
            started = time.perf_counter()
            fitness = _fitness(pool, vectors, panel, args.seeds, args.first_seed + generation * 977)
            order = np.argsort(fitness)[::-1]
            parents = [vectors[int(i)] for i in order[:args.parents]]
            best = float(fitness[int(order[0])])
            zero = fitness[0] if generation == 0 else history[0]["zero"] if history else best
            history.append({"generation": generation, "best": best,
                            "mean": float(np.mean(fitness)), "zero": zero, "sigma": sigma})
            generation += 1
            print(f"gen {generation - 1}: {len(vectors) * len(panel) * args.seeds * 2} games in "
                  f"{time.perf_counter() - started:.0f}s; best {best:.3f}, mean {history[-1]['mean']:.3f} "
                  f"(zero weights {zero:.3f})", flush=True)
            _save(out, generation, parents, [float(f) for f in np.array(fitness)[order[:args.parents]]],
                  history, settings)


def _show(args) -> None:
    row = json.loads((Path(args.run).expanduser() / "latest.json").read_text())
    for entry in row["history"]:
        print(f"  gen {entry['generation']:>3}: best {entry['best']:.3f}, mean {entry['mean']:.3f}, "
              f"sigma {entry['sigma']:.3f}")
    print(f"  zero-weight baseline in generation 0: {row['history'][0]['zero']:.3f}" if row["history"] else "  no generations yet")


def _export(args) -> None:
    row = json.loads((Path(args.run).expanduser() / "latest.json").read_text())
    best = row["parents"][0]
    print("LEARNED: Final[tuple[tuple[float, ...], ...]] = (")
    for name, weights in zip(STANCES, _rows(best)):
        print(f"    (  # {name}")
        print("        " + ", ".join(f"{w:+.3f}" for w in weights) + ",")
        print("    ),")
    print(")")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="train (or carry on) a weight table")
    run.add_argument("--out", required=True)
    run.add_argument("--generations", type=int, default=20)
    run.add_argument("--population", type=int, default=24, help="offspring per generation (a multiple of --parents)")
    run.add_argument("--parents", type=int, default=6)
    run.add_argument("--seeds", type=int, default=5, help="boards per panellist, both corners")
    run.add_argument("--panel", default=",".join(DEFAULT_PANEL))
    run.add_argument("--first-seed", type=int, default=700000)
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--sigma", type=float, default=0.2)
    run.add_argument("--workers", type=int, default=max(1, mp.cpu_count() // 2))
    run.set_defaults(go=_run)
    show = sub.add_parser("show", help="a run's fitness history")
    show.add_argument("run")
    show.set_defaults(go=_show)
    export = sub.add_parser("export", help="the best table as the LEARNED literal for brains/policy.py")
    export.add_argument("run")
    export.set_defaults(go=_export)
    args = parser.parse_args()
    args.go(args)


if __name__ == "__main__":
    main()
