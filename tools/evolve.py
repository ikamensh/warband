"""Breed brains with a genetic search, judged by ladder matches (the engine is warband/league/evolve.py).

    uv run python tools/evolve.py run --race orc --out docs/evidence/ga/orc-1 --generations 40
    uv run python tools/evolve.py run --out docs/evidence/ga/orc-1 --generations 20      # carry a run on
    uv run python tools/evolve.py show docs/evidence/ga/orc-1                            # its history and its best
    uv run python tools/evolve.py profile docs/evidence/ga/orc-1 --name orc-1-417        # one individual as a ProProfile

A run is kept a generation at a time under ``--out`` (``latest.json`` and one file per generation), so a run
that is stopped, or whose machine slept, carries on from where it was.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its worker processes, not as a library
    fastsim.activate()  # the compiled simulation, unless WARBAND_INTERPRETED is set

from warband.brains.pro_ai import PRO  # noqa: E402
from warband.league import evolve  # noqa: E402


def _show(state: evolve.State, top: int) -> None:
    for row in state.history[-12:]:
        print(f"  gen {row['generation']:3d}: population {row['mean_fitness']:.3f}, best {row['best']} "
              f"{row['best_fitness']:.3f} ({row['best_score']:.3f} over {row['best_games']}); panel {', '.join(row['panel'])}")
    panel = evolve.panel_of(state)
    prior = {o: evolve._population_rate(state.population, o) for o in panel}
    ranked = sorted((i for i in state.population if i.games), key=lambda i: -evolve.fitness(i, panel, prior))
    print(f"\n  generation {state.generation}; panel {', '.join(panel)}")
    print(f"  {'name':<16} {'fitness':>8} {'score':>7} {'games':>6}  first  peak  towers  halls  " + "  ".join(f"{o[:10]:>10}" for o in panel))
    for i in ranked[:top]:
        cells = "  ".join(f"{evolve._rate(i, o):10.2f}" for o in panel)
        print(f"  {i.name:<16} {evolve.fitness(i, panel, prior):8.3f} {i.score:7.3f} {i.games:6d}  "
              f"{i.mean_style('first_attack'):5.0f} {i.mean_style('peak_army'):5.1f} {i.mean_style('towers'):7.1f} "
              f"{i.mean_style('halls'):6.1f}  {cells}")
    print("\n  the hall: " + (", ".join(f"{c.name} ({c.score:.3f} over {c.games})" for c in state.hall) or "empty"))


def _profile(state: evolve.State, name: str | None) -> None:
    pool = {i.name: i for i in [*state.hall, *state.population]}
    if name is None:
        panel = evolve.panel_of(state)
        prior = {o: evolve._population_rate(state.population, o) for o in panel}
        name = max((i for i in state.population if i.games), key=lambda i: evolve.fitness(i, panel, prior)).name
    individual = pool[name]
    profile = evolve.profile_of(individual.genes, name)
    print(f"# {name}: {individual.score:.3f} over {individual.games} games; parents {individual.parents}")
    print("replace(PRO, " + ", ".join(f"{f.name}={getattr(profile, f.name)!r}" for f in fields(profile)
                                     if getattr(profile, f.name) != getattr(PRO, f.name)) + ")")


def _trial(args: argparse.Namespace) -> None:
    """Known profiles with some genes set by hand, against the panel: what one behaviour is worth before it is bred."""
    panel = args.panel.split(",")
    population = []
    for k, text in enumerate(args.set or [""]):
        genes = evolve.genes_of(evolve._known_profile(args.base))
        for term in filter(None, text.split(",")):
            name, _, value = term.partition("=")
            genes[name] = evolve.GENE[name].clip(float(value))
        population.append(evolve.Individual(f"trial-{k}" + (f"[{text}]" if text else f"[{args.base}]"), genes))
    evaluator = evolve.Evaluator(args.workers)
    try:
        seeds = range(args.first_seed, args.first_seed + args.seeds)
        games = evolve.judge(evaluator, population, panel, {}, args.race, seeds, evolve.arena.DEFAULT_MINUTES)
    finally:
        evaluator.close()
    print(f"{games} games; race {args.race or 'drawn'}; base {args.base}; seeds from {args.first_seed}")
    for i in population:
        print(f"  {i.score:6.3f} over {i.games:4d}  " + "  ".join(f"{o} {evolve._rate(i, o):.2f}" for o in panel)
              + f"  first {i.mean_style('first_attack'):4.0f} peak {i.mean_style('peak_army'):4.1f}  {i.name}")


def _macro(args: argparse.Namespace) -> None:
    """Breed an opening for military worth at the checkpoints, undisturbed, and say what it changed."""
    import json
    import random

    base = evolve.genes_of(evolve._known_profile(args.base))
    evaluator = evolve.Evaluator(args.workers)
    seeds = range(args.first_seed, args.first_seed + args.seeds)
    try:
        before = evolve.macro_judge(evaluator, [base], args.race, seeds)[0]
        print(f"{args.base} as {args.race}: {before:.0f} over {args.seeds} boards", flush=True)
        best, score = evolve.macro_search(evaluator, args.race, base, generations=args.generations, population=args.population,
                                          seeds=seeds, rng=random.Random(args.seed), log=lambda text: print(text, flush=True))
        fresh = range(args.first_seed + 1000, args.first_seed + 1000 + 2 * args.seeds)
        check = evolve.macro_judge(evaluator, [base, best], args.race, fresh)
    finally:
        evaluator.close()
    print(f"best {score:.0f} (from {before:.0f}); on {len(fresh)} boards it never saw: {check[1]:.0f} against {check[0]:.0f}")
    print("changed: " + ", ".join(f"{k}={v:g}" for k, v in best.items() if v != base[k]))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"race": args.race, "base": args.base, "score": score, "fresh": check, "genes": best}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("run", "show", "profile", "trial", "macro"))
    parser.add_argument("--base", default="pro-vanguard", help="trial: the known profile the genes are set on")
    parser.add_argument("--set", action="append", help="trial: genes set by hand, e.g. research_first=2,tech.blacksmith=1 (repeatable)")
    parser.add_argument("path", nargs="?", type=Path, help="show, profile: the run's folder")
    parser.add_argument("--out", type=Path, help="run: the run's folder; an existing run is carried on")
    parser.add_argument("--race", default=None, choices=evolve.RACE_VALUES, help="breed for this race (default: whatever the seed draws)")
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--elite", type=int, default=8)
    parser.add_argument("--seeds", type=int, default=6, help="boards per opponent per generation, each from both corners")
    parser.add_argument("--panel", default="pro-vanguard,pro-warden,pro-rush")
    parser.add_argument("--start", default=None, help="comma separated known profiles the first generation is seeded with")
    parser.add_argument("--first-seed", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 4))
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--name", default=None, help="profile: the individual (default: the best of the population)")
    args = parser.parse_args()

    if args.mode == "trial":
        _trial(args)
        return
    if args.mode == "macro":
        _macro(args)
        return
    if args.mode in ("show", "profile"):
        state = evolve.load(args.path)
        _show(state, args.top) if args.mode == "show" else _profile(state, args.name)
        return
    out: Path = args.out
    tag = out.name
    if (out / "latest.json").exists():
        state = evolve.load(out)
        print(f"carrying on {out} from generation {state.generation}")
    else:
        settings = evolve.Settings(race=args.race, population=args.population, elite=args.elite, seeds=args.seeds,
                                   panel=tuple(args.panel.split(",")), first_seed=args.first_seed, seed=args.seed)
        if args.start is not None:
            settings.start = tuple(name for name in args.start.split(",") if name)
        state = evolve.found(settings, tag)
    evaluator = evolve.Evaluator(args.workers)
    try:
        for _ in range(args.generations):
            evolve.step(state, evaluator, tag, log=lambda text: print(text, flush=True))
            evolve.save(state, out)
    finally:
        evaluator.close()
    _show(state, args.top)


if __name__ == "__main__":
    main()
