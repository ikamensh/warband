"""Evidence for the AI gates: difficulties against a scripted human opening, and how often matches end.

    uv run python tools/ai_report.py                 # 3 difficulties × 4 seeds against the script, 8 Normal-vs-Normal matches
    uv run python tools/ai_report.py --seeds 8 --decide 20
    uv run python tools/ai_report.py --seeds 0 --decide 0 --ladder 4   # every pair of difficulties head to head, sides swapped per seed

The script plays a plain human opening through World commands: peasants
mine and chop, farms keep supply ahead, a barracks then a second one, a
blacksmith for Sharpened Blades, footmen and archers trained without pause,
and an attack-move with the whole army every time it reaches twelve.
Easy should lose to it, Hard should beat it, Normal is the coin flip.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband import mapgen  # noqa: E402
from warband.ai import Brain  # noqa: E402
from warband.model import Harvest, World, dist  # noqa: E402
from warband.rules import BUILDINGS, SIM_DT, BuildingType, Difficulty, UnitType, Upgrade  # noqa: E402

MINUTES = 20


class Script:
    """A fixed, unadaptive human plan for player 0."""

    def __init__(self, player: int = 0) -> None:
        self.player = player
        self.next = 0.0
        self.attacked = 0

    def act(self, world: World, rng: random.Random) -> None:
        if world.time < self.next:
            return
        self.next = world.time + 1.0
        p = self.player
        hall = next((b for b in world.player_buildings(p, BuildingType.TOWN_HALL, done=True)), None)
        if hall is None:
            return
        mine = world._nearest_mine(hall.center, 99)
        peasants = [u for u in world.player_units(p) if u.is_worker]
        for u in peasants:
            if not u.orders and not u.hidden:
                choppers = sum(1 for q in peasants if any(isinstance(o, Harvest) and not isinstance(o.target, int) for o in q.orders))
                tree = world.nearest_tree(hall.center, 14)
                if choppers < 3 and tree is not None:
                    world.harvest([u.id], tree)
                elif mine is not None:
                    world.harvest([u.id], mine.id)
        if not hall.queue and len(peasants) < 9 and world.can_train(hall, UnitType.PEASANT) is None:
            world.train(hall.id, UnitType.PEASANT)
        used, cap = world.supply(p)
        builders = [u for u in peasants if not u.hidden and u.carrying is None]
        under_way = any(not b.done for b in world.player_buildings(p))
        barracks = world.player_buildings(p, BuildingType.BARRACKS, done=True)
        smith = world.player_buildings(p, BuildingType.BLACKSMITH, done=True)
        want = None
        if used + 2 > cap:
            want = BuildingType.FARM
        elif not barracks:
            want = BuildingType.BARRACKS
        elif not smith:
            want = BuildingType.BLACKSMITH
        elif len(barracks) < 2:
            want = BuildingType.BARRACKS
        if want is not None and not under_way and builders and world.can_afford(p, BUILDINGS[want].cost) is None:
            for r in range(3, 12):
                spots = [(hall.x + dx, hall.y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
                rng.shuffle(spots)
                site = next((s for s in spots if world.can_place(want, s, p) is None), None)
                if site is not None:
                    world.build(builders[0].id, want, site)
                    break
        for b in barracks:
            if not b.queue:
                choice = UnitType.ARCHER if len(b.queue) % 2 else UnitType.FOOTMAN
                if world.can_train(b, choice) is None:
                    world.train(b.id, choice)
        for s in smith:
            if world.can_research(s, Upgrade.BLADES_1) is None:
                world.research(s.id, Upgrade.BLADES_1)
        army = [u for u in world.player_units(p) if not u.is_worker]
        idle = [u for u in army if not u.orders]
        if len(army) >= 12 and len(idle) >= 8:
            targets = [b.center for b in world.buildings.values() if b.player not in (None, p)]
            if targets:
                target = min(targets, key=lambda t: dist(t, hall.center))
                world.attack_move([u.id for u in army], target)
                self.attacked += 1


def match(seed: int, difficulty: Difficulty, *, minutes: int = MINUTES) -> tuple[int | None, float, dict]:
    rng = random.Random(seed)
    world = mapgen.generate(seed=seed, players=2, human=0)
    script, brain = Script(0), Brain(1, difficulty)
    for _ in range(int(minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        script.act(world, rng)
        brain.think(world, rng)
        world.step()
        world.take_events()
    armies = {p.id: len([u for u in world.player_units(p.id) if not u.is_worker]) for p in world.players}
    return world.winner, world.time, {"armies": armies, "buildings": {p.id: len(world.player_buildings(p.id)) for p in world.players}, "attacks": script.attacked}


def ai_vs_ai(seed: int, difficulty: Difficulty, other: Difficulty | None = None, *, minutes: int) -> tuple[int | None, float]:
    """Player 0 plays *difficulty*, player 1 plays *other* (the same difficulty by default)."""
    rng = random.Random(seed)
    world = mapgen.generate(seed=seed, players=2, human=None)
    brains = [Brain(0, difficulty), Brain(1, other or difficulty)]
    for _ in range(int(minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for b in brains:
            b.think(world, rng)
        world.step()
        world.take_events()
    return world.winner, world.time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--decide", type=int, default=8, help="Normal-vs-Normal matches on Medium for the decided-within-20-minutes rate")
    parser.add_argument("--ladder", type=int, default=0, help="seeds per pair of difficulties, each played from both sides")
    args = parser.parse_args()
    print("Scripted opening against each difficulty (winner 0 = the script):")
    for difficulty in Difficulty:
        wins = 0
        for seed in range(1, args.seeds + 1):
            winner, t, info = match(seed, difficulty)
            wins += winner == 0
            print(f"  {difficulty.value:6s} seed {seed}: winner {winner} at {t / 60:.1f} min, armies {info['armies']}, buildings {info['buildings']}, script attacks {info['attacks']}")
        print(f"  → script won {wins}/{args.seeds} against {difficulty.value}")
    decided = 0
    times = []
    for seed in range(101, 101 + args.decide):
        winner, t = ai_vs_ai(seed, Difficulty.NORMAL, minutes=MINUTES)
        decided += winner is not None
        times.append(t / 60)
        print(f"  normal vs normal seed {seed}: winner {winner} at {t / 60:.1f} min")
    if args.decide:
        print(f"Normal vs Normal on Medium: {decided}/{args.decide} decided within {MINUTES} minutes; mean {sum(times) / len(times):.1f} min")
    levels = list(Difficulty)
    for i, weaker in enumerate(levels):
        for stronger in levels[i + 1:]:
            wins = 0
            for seed in range(201, 201 + args.ladder):
                for side in (0, 1):  # the stronger brain plays each seed from both sides
                    pair = (stronger, weaker) if side == 0 else (weaker, stronger)
                    winner, t = ai_vs_ai(seed, pair[0], pair[1], minutes=MINUTES)
                    wins += winner == side
                    print(f"  {stronger.value} (player {side}) vs {weaker.value} seed {seed}: winner {winner} at {t / 60:.1f} min")
            if args.ladder:
                print(f"  → {stronger.value} won {wins}/{2 * args.ladder} against {weaker.value}")


if __name__ == "__main__":
    main()
