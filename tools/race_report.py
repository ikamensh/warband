"""Race balance evidence: every pair of races head to head under the same AI, sides swapped per seed.

    uv run python tools/race_report.py                    # 6 pairs × 2 seeds on Medium, Hard against Hard
    uv run python tools/race_report.py --seeds 42 --difficulty master   # about 500 matches, a minute on the Mac

A race that wins far more than it loses across the pairs is out of line; a
mixed table with most matches decided is the aim.  The AI plays every race
the same way (it researches its own arts in order), so the report measures
the rules, not any race-specific strategy.  Matches are independent and fully
determined by their seed, so they run in a process pool of ``--workers``.
"""

from __future__ import annotations

import argparse
import itertools
import multiprocessing as mp
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):  # run as a program or as one of its worker processes, not as a library
    fastsim.activate()  # the compiled simulation, unless WARBAND_INTERPRETED is set

from warband.sim import mapgen  # noqa: E402
from warband.brains.ai import make_brain  # noqa: E402
from warband.sim.rules import OWN_UNITS, SIM_DT, Difficulty, Race  # noqa: E402

OWN = frozenset(unit.value for unit in OWN_UNITS.values())

MINUTES = 20


def match(seed: int, races: tuple[Race, Race], difficulty: Difficulty, *, minutes: int,
          bought: Counter[Race] | None = None, own_units: bool = True, magic: bool = True,
          cast: Counter[Race] | None = None) -> tuple[Race | None, float]:
    """``(winning race or None, minutes played)`` for one AI-versus-AI match; each race's own units trained are counted
    into *bought*, and its spells cast into *cast*."""
    world = mapgen.generate(seed=seed, players=2, human=None, races=races)
    # Hard and Master are a ProBrain, not a Brain; the wilds are nobody's seat and have no brain at all.
    brains = [make_brain(p.id, difficulty, seed, own_units=own_units, magic=magic) for p in world.players[:world.seats]]
    rng = random.Random(seed)
    for _ in range(int(minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for brain in brains:
            brain.think(world, rng)
        world.step()
        for event in world.take_events():
            if bought is not None and event.kind == "trained" and event.target_type in OWN:
                bought[world.players[event.player].race] += 1
            if cast is not None and event.kind == "cast":
                cast[world.players[event.player].race] += 1
    return (world.players[world.winner].race if world.winner is not None else None), world.time / 60


def play(task: tuple[int, tuple[Race, Race], Difficulty, int, bool, bool]
         ) -> tuple[int, tuple[Race, Race], Race | None, float, Counter[Race], Counter[Race]]:
    """One match of the table in a worker process: its seed and races, the winner, the minutes, the own units bought
    and the spells cast."""
    seed, races, difficulty, minutes, own_units, magic = task
    bought: Counter[Race] = Counter()
    cast: Counter[Race] = Counter()
    winner, played = match(seed, races, difficulty, minutes=minutes, bought=bought, own_units=own_units, magic=magic, cast=cast)
    return seed, races, winner, played, bought, cast


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=2, help="seeds per pair; each seed is played from both sides")
    parser.add_argument("--first-seed", type=int, default=1, help="the first of the seeds: another block of seeds is another sample")
    parser.add_argument("--difficulty", choices=[d.value for d in Difficulty], default="hard")
    parser.add_argument("--minutes", type=int, default=MINUTES)
    parser.add_argument("--workers", type=int, default=max(1, mp.cpu_count() // 2),
                        help="matches played at once; half the machine by default, as the stack's slot runs two heavy jobs")
    parser.add_argument("--without-own-units", dest="own_units", action="store_false",
                        help="brains that never buy their race's own unit (WB-068): the same matches as before it existed")
    parser.add_argument("--without-magic", dest="magic", action="store_false",
                        help="brains that never build a vault (WB-067): Hard, Master and Grandmaster as before they cast")
    args = parser.parse_args()
    difficulty = Difficulty(args.difficulty)
    wins: Counter[Race] = Counter()
    losses: Counter[Race] = Counter()
    pairs: Counter[tuple[Race, Race]] = Counter()  # (winner, loser)
    undecided = 0
    bought: Counter[Race] = Counter()  # each race's own unit (WB-068), trained
    cast: Counter[Race] = Counter()  # each race's spells (WB-067), cast
    seeds = [seed for seed in range(args.first_seed, args.first_seed + args.seeds) if fair(seed)]
    if len(seeds) < args.seeds:
        print(f"  ({args.seeds - len(seeds)} of {args.seeds} seeds have no fair map and were left out)", flush=True)
    tasks = [(seed, races, difficulty, args.minutes, args.own_units, args.magic)
             for first, second in itertools.combinations(Race, 2) for seed in seeds for races in ((first, second), (second, first))]
    with mp.get_context("spawn").Pool(args.workers) as pool:
        for seed, races, winner, played, own, spells in pool.imap_unordered(play, tasks, chunksize=1):
            bought.update(own)
            cast.update(spells)
            if winner is None:
                undecided += 1
            else:
                loser = races[0] if winner is races[1] else races[1]
                wins[winner] += 1
                losses[loser] += 1
                pairs[winner, loser] += 1
            print(f"  seed {seed}: {races[0].value} vs {races[1].value} → {winner.value if winner else 'undecided'} after {played:.1f} min", flush=True)
    print(f"{args.difficulty} against {args.difficulty}, {len(seeds)} seeds per pair, sides swapped:")
    for race in Race:
        decided = wins[race] + losses[race]
        print(f"  {race.value:6} won {wins[race]:3}  lost {losses[race]:3}  {100 * wins[race] / max(1, decided):5.1f}%")
    for first, second in itertools.combinations(Race, 2):
        print(f"  {first.value} {pairs[first, second]}–{pairs[second, first]} {second.value}")
    print(f"  undecided within {args.minutes} min: {undecided}")
    played = 3 * len(seeds) * 2  # each race plays three pairings, both sides, every seed
    print("  own units trained: " + ", ".join(f"{race.value} {OWN_UNITS[race].value} {bought[race]} in {played} matches" for race in Race))
    print("  spells cast: " + ", ".join(f"{race.value} {cast[race]} in {played} matches" for race in Race))


def fair(seed: int) -> bool:
    """Whether mapgen can make a fair two-player map from *seed*: a seed it cannot is left out, as the arena does."""
    try:
        mapgen.generate(seed=seed, players=2, human=None)
    except mapgen.NoFairMap:
        return False
    return True


if __name__ == "__main__":
    main()
