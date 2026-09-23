"""Measure which plans each map layout rewards, with the same opponents on each layout.

    uv run python tools/map_strategy_report.py --seeds 12 --first-seed 2000 --workers 4 --out DIR/matches.jsonl
    uv run python tools/map_strategy_report.py --from DIR/matches.jsonl

Five deliberately different balance archetypes play every pair from both seats on each of the five
layouts. A seed uses the same size, races and opponents on every layout. Scores are therefore a
comparison of the layouts, not of different draws of the league. Keep the saved match records so
the report can be reread without replaying the games (pass the same --plans if it was customized).
Use fresh seeds to check a proposed change.
"""

from __future__ import annotations

import argparse
import itertools
import random
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()

from arena import load, playable, run  # noqa: E402
from warband.league import arena  # noqa: E402
from warband.league.archetypes import NAMES  # noqa: E402
from warband.league.arena import MatchResult, MatchSpec  # noqa: E402
from warband.sim.rules import Layout, Race  # noqa: E402

PLANS = ("rush", "boom", "turtle", "knights", "siege")


def matchup_specs(seeds: range, plans: tuple[str, ...] = PLANS, minutes: float = arena.DEFAULT_MINUTES) -> list[MatchSpec]:
    """The same race pair, board size and both seats for each pairing on every layout."""
    specs: list[MatchSpec] = []
    for seed in seeds:
        width, height = arena.LADDER_SIZES[seed % len(arena.LADDER_SIZES)]
        for a, b in itertools.combinations(plans, 2):
            rng = random.Random(f"{seed}:{a}:{b}")
            races = tuple(rng.choice(tuple(Race)).value for _ in range(2))
            for layout in Layout:
                game = MatchSpec(seed=seed, agents=(a, b), width=width, height=height, minutes=minutes,
                                 races=races, layout=layout.value)
                specs.append(game)
                specs.append(replace(game, agents=(b, a)))
    return specs


def complete_seeds(specs: list[MatchSpec]) -> list[MatchSpec]:
    """Discard a seed everywhere if even one layout cannot make a fair map at its size."""
    if not specs:
        raise ValueError("at least one seed is required")
    usable = {(spec.seed, spec.layout): playable(spec)
              for spec in specs if spec.agents == specs[0].agents}
    refused = {seed for (seed, _layout), good in usable.items() if not good}
    if refused:
        print(f"  {len(refused)} seed(s) omitted on all layouts because one layout has no fair map: {sorted(refused)}")
    paired = [spec for spec in specs if spec.seed not in refused]
    if not paired:
        raise RuntimeError("no seeds have fair maps on all five layouts")
    return paired


def validate_pairs(specs: list[MatchSpec], plans: tuple[str, ...]) -> None:
    """Reject an interrupted file or one-sided refusal before reporting strategy scores."""
    if not specs:
        raise ValueError("no matches to report")
    expected = {(layout.value, agents)
                for layout in Layout
                for a, b in itertools.combinations(plans, 2)
                for agents in ((a, b), (b, a))}
    for seed in {spec.seed for spec in specs}:
        sample = [spec for spec in specs if spec.seed == seed]
        actual = {(spec.layout, spec.agents) for spec in sample}
        if len(sample) != len(expected) or actual != expected:
            raise ValueError(f"seed {seed} lacks a complete layout, opponent and seat pairing")
        for a, b in itertools.combinations(plans, 2):
            boards = {(spec.width, spec.height, spec.races)
                      for spec in sample if set(spec.agents) == {a, b}}
            if len(boards) != 1:
                raise ValueError(f"seed {seed} changes size or races for {a} against {b}")


def scores(results: list[MatchResult], plans: tuple[str, ...] = PLANS) -> dict[str, dict[str, float]]:
    """A plan's share of all its games on each layout; tied placements earn half."""
    earned = {layout.value: {plan: 0.0 for plan in plans} for layout in Layout}
    played = {layout.value: {plan: 0 for plan in plans} for layout in Layout}
    for result in results:
        layout = result.spec.layout
        assert layout is not None
        a, b = result.spec.agents
        earned[layout][a] += result.score(0, 1)
        earned[layout][b] += result.score(1, 0)
        played[layout][a] += 1
        played[layout][b] += 1
    return {layout: {plan: earned[layout][plan] / played[layout][plan] for plan in plans}
            for layout in earned}


def report(results: list[MatchResult], plans: tuple[str, ...] = PLANS) -> None:
    table = scores(results, plans)
    print(f"{len(results)} matches; {sum(result.decided for result in results)} decided")
    print(f"score against the other {len(plans) - 1} plans (both seats, same seeds/races per layout):")
    print(f"  {'layout':<10}" + "".join(f"{plan:>10}" for plan in plans))
    for layout in Layout:
        row = table[layout.value]
        print(f"  {layout.value:<10}" + "".join(f"{100 * row[plan]:9.1f}%" for plan in plans))
    print("\nrelative advantage: points above or below that plan's mean across layouts:")
    mean = {plan: sum(table[layout.value][plan] for layout in Layout) / len(Layout) for plan in plans}
    print(f"  {'layout':<10}" + "".join(f"{plan:>10}" for plan in plans))
    for layout in Layout:
        row = table[layout.value]
        print(f"  {layout.value:<10}" + "".join(f"{100 * (row[plan] - mean[plan]):+9.1f}" for plan in plans))


def separation(results: list[MatchResult], plans: tuple[str, ...] = PLANS) -> float:
    """Mean point difference between profiles of the four layouts that started alike."""
    table = scores(results, plans)
    layouts = (Layout.PLAINS, Layout.FOREST, Layout.CROSSINGS, Layout.BASTION)
    return sum(abs(table[a.value][plan] - table[b.value][plan])
               for a, b in itertools.combinations(layouts, 2) for plan in plans) / (6 * len(plans))


def compare(baseline: list[MatchResult], current: list[MatchResult], plans: tuple[str, ...] = PLANS) -> None:
    """Paired seed bootstrap: opponents, seats, races and sizes stay fixed across builds."""
    def key(result: MatchResult) -> tuple:
        return tuple(getattr(result.spec, field) for field in arena.SPEC_FIELDS)

    if Counter(map(key, baseline)) != Counter(map(key, current)):
        raise ValueError("baseline and current files must contain the same match specifications")
    seeds = sorted({result.spec.seed for result in current})
    old_by_seed = {seed: [result for result in baseline if result.spec.seed == seed] for seed in seeds}
    new_by_seed = {seed: [result for result in current if result.spec.seed == seed] for seed in seeds}
    old, new = separation(baseline, plans), separation(current, plans)
    rng = random.Random(0x5A6A)
    changes = []
    for _ in range(2000):
        draw = [rng.choice(seeds) for _ in seeds]
        before = [result for seed in draw for result in old_by_seed[seed]]
        after = [result for seed in draw for result in new_by_seed[seed]]
        changes.append(separation(after, plans) - separation(before, plans))
    changes.sort()
    print(f"\nprofile separation, excluding Klondike: {old * 100:.1f} → {new * 100:.1f} points "
          f"(change {(new - old) * 100:+.1f}; paired-seed 95% interval "
          f"{changes[50] * 100:+.1f} to {changes[1950] * 100:+.1f})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--first-seed", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--plans", default=",".join(PLANS), help="comma-separated plans to compare")
    parser.add_argument("--minutes", type=float, default=arena.DEFAULT_MINUTES)
    parser.add_argument("--out", type=Path, help="write every match as JSON lines; pass an explicit temporary path")
    parser.add_argument("--from", dest="source", type=Path, help="read a saved match file instead of playing")
    parser.add_argument("--baseline", type=Path, help="compare --from against an earlier file with identical match specifications")
    args = parser.parse_args()
    plans = tuple(args.plans.split(","))
    if len(plans) < 2 or len(set(plans)) != len(plans) or any(plan not in NAMES for plan in plans):
        parser.error(f"choose at least two distinct plans from {', '.join(NAMES)}")
    if args.source is None and (args.seeds < 1 or args.workers < 1 or args.minutes <= 0):
        parser.error("--seeds, --workers and --minutes must be positive")
    if args.baseline is not None and args.source is None:
        parser.error("--baseline requires --from")
    if args.source is not None:
        results = load([str(args.source)])
    else:
        specs = complete_seeds(matchup_specs(range(args.first_seed, args.first_seed + args.seeds), plans, args.minutes))
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.unlink(missing_ok=True)
        results = run(specs, args.workers, "map plans", save=args.out)
    validate_pairs([result.spec for result in results], plans)
    report(results, plans)
    if args.baseline is not None:
        baseline = load([str(args.baseline)])
        validate_pairs([result.spec for result in baseline], plans)
        compare(baseline, results, plans)


if __name__ == "__main__":
    main()
