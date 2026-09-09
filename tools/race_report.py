"""Race balance evidence: every pair of races head to head under the same AI, sides swapped per seed.

    uv run python tools/race_report.py                    # 6 pairs × 2 seeds on Medium, Hard against Hard
    uv run python tools/race_report.py --seeds 4 --difficulty normal --cpu-percent 100

A race that wins far more than it loses across the pairs is out of line; a
mixed table with most matches decided is the aim.  The AI plays every race
the same way (it researches its own arts in order), so the report measures
the rules, not any race-specific strategy.
"""

from __future__ import annotations

import argparse
import itertools
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d.testing.cpu_budget import CpuBudget  # noqa: E402
from warband import mapgen  # noqa: E402
from warband.ai import Brain  # noqa: E402
from warband.rules import SIM_DT, Difficulty, Race  # noqa: E402

MINUTES = 20


def match(seed: int, races: tuple[Race, Race], difficulty: Difficulty, *, minutes: int, budget: CpuBudget | None) -> tuple[Race | None, float]:
    """``(winning race or None, minutes played)`` for one AI-versus-AI match."""
    world = mapgen.generate(seed=seed, players=2, human=None, races=races)
    brains = [Brain(p.id, difficulty) for p in world.players]
    rng = random.Random(seed)
    for _ in range(int(minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        if budget is not None:
            budget.checkpoint()
        for brain in brains:
            brain.think(world, rng)
        world.step()
        world.take_events()
    return (world.players[world.winner].race if world.winner is not None else None), world.time / 60


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=2, help="seeds per pair; each seed is played from both sides")
    parser.add_argument("--difficulty", choices=[d.value for d in Difficulty], default="hard")
    parser.add_argument("--minutes", type=int, default=MINUTES)
    parser.add_argument("--cpu-percent", type=float, default=25, help="CPU allowance, percent of one core")
    args = parser.parse_args()
    budget = CpuBudget(args.cpu_percent)
    difficulty = Difficulty(args.difficulty)
    wins: Counter[Race] = Counter()
    losses: Counter[Race] = Counter()
    undecided = 0
    for first, second in itertools.combinations(Race, 2):
        for seed in range(1, args.seeds + 1):
            for races in ((first, second), (second, first)):
                winner, played = match(seed, races, difficulty, minutes=args.minutes, budget=budget)
                if winner is None:
                    undecided += 1
                else:
                    wins[winner] += 1
                    losses[races[0] if winner is races[1] else races[1]] += 1
                print(f"  seed {seed}: {races[0].value} vs {races[1].value} → {winner.value if winner else 'undecided'} after {played:.1f} min", flush=True)
    print(f"{args.difficulty} against {args.difficulty}, {args.seeds} seeds per pair, sides swapped:")
    for race in Race:
        print(f"  {race.value:6} won {wins[race]:2}  lost {losses[race]:2}")
    print(f"  undecided within {args.minutes} min: {undecided}")


if __name__ == "__main__":
    main()
