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


_STYLE_SCALES = {"first_attack": 300.0, "peak_army": 30.0, "towers": 3.0, "halls": 2.0, "barracks": 4.0}


def _style_gap(a: evolve.Individual, b: evolve.Individual) -> float:
    """How differently two individuals played: their timing and size on a common scale, and the shares of what they trained."""
    import math

    gap = 0.0
    for key, scale in _STYLE_SCALES.items():
        x, y = a.mean_style(key), b.mean_style(key)
        if not (math.isnan(x) or math.isnan(y)):
            gap += ((x - y) / scale) ** 2
    units = sorted({k for i in (a, b) for k in i.style if k.startswith("trained.") and k not in ("trained.games", "trained.peasant")})
    totals = [sum(i.mean_style(k) for k in units if k in i.style) or 1.0 for i in (a, b)]
    for key in units:
        x = a.mean_style(key) / totals[0] if key in a.style else 0.0
        y = b.mean_style(key) / totals[1] if key in b.style else 0.0
        gap += (x - y) ** 2
    return math.sqrt(gap)


def _best(state: evolve.State, args: argparse.Namespace) -> None:
    """Write the run's best proven individuals out as genes files, best first (``--out`` is the folder)."""
    import json

    panel = evolve.panel_of(state)
    prior = {o: evolve._population_rate(state.population, o) for o in panel}
    pool = {i.name: i for i in [*state.hall, *state.population] if i.games >= args.min_games}
    by_fitness = sorted(pool.values(), key=lambda i: -evolve.fitness(i, panel, prior))
    # The best, then of those within --within of it the ones that play least like the ones already chosen: a roster of
    # one strength and several players, not a champion and its siblings.
    ranked = by_fitness[:1]
    near = [i for i in by_fitness[1:] if evolve.fitness(i, panel, prior) >= evolve.fitness(by_fitness[0], panel, prior) - args.within]
    while near and len(ranked) < args.top:
        chosen = max(near, key=lambda i: min(_style_gap(i, other) for other in ranked))
        ranked.append(chosen)
        near.remove(chosen)
    args.out.mkdir(parents=True, exist_ok=True)
    for place, individual in enumerate(ranked, 1):
        path = args.out / f"{args.path.name}-best{place}.json"
        path.write_text(json.dumps({"name": individual.name, "race": state.settings.race, "score": individual.score,
                                    "games": individual.games, "genes": individual.genes}))
        print(f"{path}: {individual.name} {individual.score:.3f} over {individual.games}")


def _source(value) -> str:
    """*value* as the Python that spells it in warband/brains/bred.py: enums by their member, the rest by repr."""
    from enum import Enum

    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_source(k)}: {_source(round(v, 3) if isinstance(v, float) else v)}" for k, v in value.items()) + "}"
    if isinstance(value, tuple):
        return "(" + "".join(f"{_source(v)}, " for v in value).rstrip(" ") + ")"
    return repr(value)


def _export(args: argparse.Namespace) -> None:
    """Write warband/brains/bred.py from genes files: ``--genes race:file`` once per posture, in the order they are drawn."""
    import json
    import textwrap

    by_key: dict[str, list[tuple[str, dict]]] = {}  # "race" or "race@layout" -> its postures, in the order given
    for term in args.genes or []:
        key, _, path = term.partition(":")
        by_key.setdefault(key, []).append((Path(path).stem, json.loads(Path(path).read_text())))

    def table(key: str, label: str) -> str:
        postures = []
        for k, (stem, row) in enumerate(by_key[key], 1):
            profile = evolve.profile_of(evolve.genes_of(PRO) | row["genes"], f"bred-{key.replace('@', '-')}-{k}")
            changed = ", ".join(f"{f.name}={_source(getattr(profile, f.name))}" for f in fields(profile)
                                if getattr(profile, f.name) != getattr(PRO, f.name))
            body = textwrap.fill(f"replace(PRO, {changed}),", width=124, initial_indent=" " * 8, subsequent_indent=" " * 16)
            postures.append(f"        # {stem}: {row.get('score', 0):.3f} over {row.get('games', 0)} games of its search\n{body}")
        return f"    {label}: (\n" + "\n".join(postures) + "\n    ),"

    races = [table(race, f"Race.{race.upper()}") for race in evolve.RACE_VALUES if race in by_key]
    layouts = [table(key, f"(Race.{key.partition('@')[0].upper()}, Layout.{key.partition('@')[2].upper()})")
               for key in by_key if "@" in key]
    args.out.write_text(BRED_HEADER + "BRED: Final[dict[Race, tuple[ProProfile, ...]]] = {\n" + "\n".join(races) + "\n}\n\n"
                        "#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.\n"
                        "BRED_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {\n" + "\n".join(layouts) + "\n}\n")
    print(f"wrote {args.out}: " + ", ".join(f"{key} {len(rows)}" for key, rows in by_key.items()))


BRED_HEADER = '''"""The postures the genetic search bred, a race's own for each race (written by ``tools/evolve.py export``; bred again
rather than edited by hand).  :class:`warband.brains.pro_ai.RaceBrain` plays them: the Grandmaster setting.  How they were
bred and what they measured is in ``docs/ai-ladder.md``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

'''


def _trial(args: argparse.Namespace) -> None:
    """Known profiles with some genes set by hand, against the panel: what one behaviour is worth before it is bred."""
    panel = args.panel.split(",")
    population = []
    for k, text in enumerate(args.set or ([] if args.genes else [""])):
        genes = evolve.genes_of(evolve._known_profile(args.base))
        for term in filter(None, text.split(",")):
            name, _, value = term.partition("=")
            genes[name] = evolve.GENE[name].clip(float(value))
        population.append(evolve.Individual(f"trial-{k}" + (f"[{text}]" if text else f"[{args.base}]"), genes))
    for path in args.genes or []:
        import json

        population.append(evolve.Individual(f"trial-{Path(path).stem}", evolve.genes_of(PRO) | json.loads(Path(path).read_text())["genes"]))
    evaluator = evolve.Evaluator(args.workers)
    try:
        seeds = range(args.first_seed, args.first_seed + args.seeds * args.seed_step, args.seed_step)
        games = evolve.judge(evaluator, population, panel, {}, args.race, seeds, evolve.arena.DEFAULT_MINUTES, args.layout)
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
    if args.genes:  # carry an earlier search on
        base = base | json.loads(Path(args.genes[0]).read_text())["genes"]
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
    parser.add_argument("mode", choices=("run", "show", "profile", "trial", "macro", "best", "export"))
    parser.add_argument("--min-games", type=int, default=150, help="best: only individuals with this many games behind them")
    parser.add_argument("--within", type=float, default=0.04, help="best: how far below the best's fitness a different player may be")
    parser.add_argument("--base", default="pro-vanguard", help="trial: the known profile the genes are set on")
    parser.add_argument("--set", action="append", help="trial: genes set by hand, e.g. abort.on=1,abort_ratio=1.2 (repeatable)")
    parser.add_argument("--genes", action="append", help="trial: a JSON file whose \"genes\" play as they are (repeatable)")
    parser.add_argument("path", nargs="?", type=Path, help="show, profile: the run's folder")
    parser.add_argument("--out", type=Path, help="run: the run's folder; an existing run is carried on")
    parser.add_argument("--race", default=None, choices=evolve.RACE_VALUES, help="breed for this race (default: whatever the seed draws)")
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--elite", type=int, default=8)
    parser.add_argument("--seeds", type=int, default=6, help="boards per opponent per generation, each from both corners")
    parser.add_argument("--panel", default="pro-vanguard,pro-warden,pro-rush")
    parser.add_argument("--hall-size", type=int, default=2, help="run: how many of its own champions join the panel")
    parser.add_argument("--layout", default=None, help="run, trial: play every board on this layout (default: all five in turn)")
    parser.add_argument("--start", default=None, help="comma separated known profiles the first generation is seeded with")
    parser.add_argument("--seed-genes", default=None, help="run: comma separated JSON files whose \"genes\" join the first generation (a macro search's --out)")
    parser.add_argument("--first-seed", type=int, default=200_000)
    parser.add_argument("--seed-step", type=int, default=1, help="trial: 5 keeps one layout (the first seed's), since layouts cycle by seed")
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
    if args.mode == "export":
        _export(args)
        return
    if args.mode in ("show", "profile", "best"):
        state = evolve.load(args.path)
        {"show": lambda: _show(state, args.top), "profile": lambda: _profile(state, args.name), "best": lambda: _best(state, args)}[args.mode]()
        return
    out: Path = args.out
    tag = out.name
    if (out / "latest.json").exists():
        state = evolve.load(out)
        print(f"carrying on {out} from generation {state.generation}")
    else:
        settings = evolve.Settings(race=args.race, population=args.population, elite=args.elite, seeds=args.seeds,
                                   panel=tuple(args.panel.split(",")), first_seed=args.first_seed, seed=args.seed,
                                   hall_size=args.hall_size, layout=args.layout)
        if args.start is not None:
            settings.start = tuple(name for name in args.start.split(",") if name)
        import json

        bred = [json.loads(Path(path).read_text())["genes"] for path in (args.seed_genes.split(",") if args.seed_genes else [])]
        state = evolve.found(settings, tag, bred)
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
