"""Hill-climb the numbers a ProProfile plays by, judged by matches rather than taste.

    uv run python tools/tune.py --rounds 12 --games 40
    uv run python tools/tune.py --rounds 20 --games 60 --against hard,pro --workers 6

Each round perturbs a few knobs of the best profile so far, plays the candidate
against a fixed panel on seeds it has never seen, and keeps it only if it scores
better by more than the noise in that many games. Fresh seeds every round are
the whole point: a profile tuned until it beats one set of maps has learnt the
maps.
"""

from __future__ import annotations

import argparse
import itertools
import math
import multiprocessing as mp
import random
import sys
import time
from dataclasses import fields, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its worker processes, not as a library
    fastsim.activate()  # the compiled simulation, unless WARBAND_INTERPRETED is set

from warband.league import arena  # noqa: E402
from warband.league.arena import MatchSpec  # noqa: E402
from warband.brains.pro_ai import PRO, PRO_PROFILES, ProProfile  # noqa: E402

#: knob → (low, high). Only knobs worth a search; booleans are settled by ablation.
KNOBS: dict[str, tuple[float, float]] = {
    "workers_per_mine": (7, 16),
    "lumber_share": (0.2, 0.5),
    "max_workers": (16, 36),
    "supply_slack": (2, 10),
    "supply_per_producer": (0.5, 4.0),
    "max_sites": (1, 4),
    "surplus_gold": (300, 2500),
    "lumber_floor": (0, 600),
    "barracks_per_hall": (1, 5),
    "attack_ratio": (0.8, 2.0),
    "retreat_ratio": (0.2, 0.8),
    "regroup_seconds": (10, 90),
    "min_army": (4, 22),
    "tower_count": (0, 5),
    "max_halls": (1, 4),
    "think_every": (0.2, 1.0),
    "stale_seconds": (10, 60),
    "symmetry_prior": (0.5, 1.6),
}
_INTEGER = {f.name for f in fields(ProProfile) if f.type == "int"}


def jitter(profile: ProProfile, rng: random.Random, knobs: int) -> ProProfile:
    changes = {}
    for name in rng.sample(sorted(KNOBS), knobs):
        low, high = KNOBS[name]
        current = getattr(profile, name)
        step = (high - low) * 0.25
        value = min(high, max(low, current + rng.uniform(-step, step)))
        changes[name] = int(round(value)) if name in _INTEGER else round(value, 3)
    return replace(profile, **changes)


def score(candidate: ProProfile, against: list[str], seeds: range, workers: int, minutes: float) -> float:
    """Share of the score the candidate takes against the panel, both corners of every map."""
    specs = []
    for opponent in against:
        for seed in seeds:
            specs.append(MatchSpec(seed=seed, agents=("candidate", opponent), minutes=minutes))
            specs.append(MatchSpec(seed=seed, agents=(opponent, "candidate"), minutes=minutes))
    packed = [tuple(s.__dict__[f] for f in arena.SPEC_FIELDS) for s in specs]
    context = mp.get_context("spawn")
    with context.Pool(workers, initializer=arena.register_profiles,
                      initargs=([("candidate", candidate)],)) as pool:
        results = list(pool.imap_unordered(arena.play_spec_tuple, packed, chunksize=1))
    total = 0.0
    for result in results:
        i = result.spec.agents.index("candidate")
        total += result.score(i, 1 - i)
    return total / len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--games", type=int, default=40, help="matches per candidate (seeds are half of this)")
    parser.add_argument("--against", default="hard,pro")
    parser.add_argument("--knobs", type=int, default=3, help="knobs perturbed per candidate")
    parser.add_argument("--minutes", type=float, default=arena.DEFAULT_MINUTES)
    parser.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 2))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start", default=PRO.name, help="the registered profile to climb from")
    args = parser.parse_args()

    against = args.against.split(",")
    rng = random.Random(args.seed)
    best = PRO_PROFILES[args.start]
    seeds = range(50_000, 50_000 + args.games // (2 * len(against)) or 1)
    started = time.perf_counter()
    best_score = score(best, against, seeds, args.workers, args.minutes)
    print(f"round  0: baseline scores {best_score:.3f} against {', '.join(against)} "
          f"({len(seeds) * 2 * len(against)} games, {time.perf_counter() - started:.0f}s)")
    for round_number in range(1, args.rounds + 1):
        # New seeds every round, so a profile cannot be tuned into the maps it was judged on.
        seeds = range(50_000 + round_number * 977, 50_000 + round_number * 977 + (args.games // (2 * len(against)) or 1))
        candidate = jitter(best, rng, args.knobs)
        base = score(best, against, seeds, args.workers, args.minutes)
        trial = score(candidate, against, seeds, args.workers, args.minutes)
        games = len(seeds) * 2 * len(against)
        noise = 1.2 * math.sqrt(0.25 / games)  # a little over one standard error of a coin flip
        changed = {f.name: getattr(candidate, f.name) for f in fields(ProProfile)
                   if getattr(candidate, f.name) != getattr(best, f.name)}
        verdict = "keep" if trial > base + noise else "drop"
        print(f"round {round_number:2d}: {trial:.3f} against {base:.3f} (+{noise:.3f} needed) {verdict}  {changed}")
        if verdict == "keep":
            best, best_score = replace(candidate, name=PRO.name), trial
    print("\nbest profile:")
    for f in fields(ProProfile):
        value, baseline = getattr(best, f.name), getattr(PRO_PROFILES[args.start], f.name)
        mark = "  <-- changed" if value != baseline else ""
        print(f"    {f.name}={value!r},{mark}")


if __name__ == "__main__":
    main()
