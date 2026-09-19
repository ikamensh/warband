"""Set-piece battles on open grass: what a unit behaviour is worth, apart from everything else a match is.

    uv run python tools/battle_bench.py                                  # the standard pairings, each side's arts level
    uv run python tools/battle_bench.py --left drill --right ""          # the left side has researched Battle Drill
    uv run python tools/battle_bench.py --army footman:6,archer:6 --races elf,orc --fights 200

Two armies of the same price are stood a screen apart and sent at each other with one attack-move each, which is
all a brain does for its soldiers; the fighting is the model's.  Each pairing is fought ``--fights`` times from
both sides of the field, and the readout is the share won by the left army and what the winner had left.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()

from warband.sim.model import World  # noqa: E402
from warband.sim.rules import SIM_DT, Race, Terrain, UnitType, Upgrade  # noqa: E402

WIDTH, HEIGHT = 44, 30
ARMIES = ("footman:10", "archer:10", "footman:6,archer:6", "footman:5,archer:4,knight:3", "knight:6,archer:6",
          "footman:6,archer:5,cleric:2")


def army_of(text: str) -> list[UnitType]:
    out: list[UnitType] = []
    for term in text.split(","):
        name, _, count = term.partition(":")
        out += [UnitType(name)] * int(count or 1)
    return out


def fight(seed: int, armies: tuple[list[UnitType], list[UnitType]], races: tuple[Race, Race],
          arts: tuple[tuple[Upgrade, ...], tuple[Upgrade, ...]], swap: bool) -> tuple[int | None, float, float]:
    """One battle; ``(winner, what the left army has left, what the right has)`` as shares of their price."""
    rng = random.Random(seed)
    sides = (1, 0) if swap else (0, 1)  # which player fields the left army: the first to act each step must not be one army's luck
    seated = sorted(zip(sides, races))
    world = World(WIDTH, HEIGHT, [[Terrain.GRASS] * WIDTH for _ in range(HEIGHT)], 2, human=None,
                  rng=random.Random(seed + 1), races=[race for _player, race in seated])
    price = [0.0, 0.0]
    for index, player in enumerate(sides):
        world.players[player].upgrades.update(arts[index])
    for index, player in enumerate(sides):
        x0 = 8.0 if (index == 0) != swap else WIDTH - 8.0
        toward = 1.0 if x0 < WIDTH / 2 else -1.0
        for k, unit_type in enumerate(armies[index]):
            # Shooters and healers behind the line, as a rally point leaves them; a little jitter so no two fights are one.
            back = 0.0 if world.unit_info(player, unit_type).melee else 2.0
            y = HEIGHT / 2 + ((k % 8) - 3.5) * 1.1 + rng.uniform(-0.3, 0.3)
            x = x0 - toward * (back + (k // 8) * 1.1) + rng.uniform(-0.3, 0.3)
            unit = world.spawn_unit(player, unit_type, (x, y))
            cost = unit.info.cost
            price[index] += cost.gold + cost.lumber
    world.update_vision()
    for index, player in enumerate(sides):
        x0 = 8.0 if (index == 0) != swap else WIDTH - 8.0
        world.attack_move([u.id for u in world.player_units(player)], (WIDTH - x0, HEIGHT / 2))
    for _ in range(int(240 / SIM_DT)):
        world.step()
        world.take_events()
        alive = [bool(world.player_units(p)) for p in (0, 1)]
        if not all(alive):
            break
    left = [0.0, 0.0]
    for index, player in enumerate(sides):
        for unit in world.player_units(player):
            cost = unit.info.cost
            left[index] += (cost.gold + cost.lumber) * unit.hp / unit.max_hp
    shares = (left[0] / price[0], left[1] / price[1])
    winner = None if (shares[0] > 0) == (shares[1] > 0) else (0 if shares[0] > 0 else 1)
    return winner, shares[0], shares[1]


def arts_of(text: str) -> tuple[Upgrade, ...]:
    return tuple(Upgrade(name) for name in text.split(",") if name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--army", default=None, help="one composition for both sides, e.g. footman:6,archer:6 (default: the standard set)")
    parser.add_argument("--right-army", default=None, help="the right side's composition when it differs")
    parser.add_argument("--races", default="human,human")
    parser.add_argument("--left", default="", help="upgrades the left army has, comma separated")
    parser.add_argument("--right", default="", help="upgrades the right army has")
    parser.add_argument("--fights", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    races = tuple(Race(r) for r in args.races.split(","))
    arts = (arts_of(args.left), arts_of(args.right))
    print(f"{args.races}; left has {args.left or 'nothing'}, right has {args.right or 'nothing'}; {args.fights} fights a pairing, half from each side")
    print(f"  {'army':<34} {'left wins':>9} {'draws':>6} {'left keeps':>10} {'right keeps':>11}")
    for text in ([args.army] if args.army else ARMIES):
        armies = (army_of(text), army_of(args.right_army or text))
        won = drawn = 0
        kept: tuple[list[float], list[float]] = ([], [])
        for k in range(args.fights):
            winner, a, b = fight(args.seed * 100_003 + k, armies, races, arts, swap=bool(k % 2))  # type: ignore[arg-type]
            won += winner == 0
            drawn += winner is None
            kept[0].append(a)
            kept[1].append(b)
        print(f"  {text:<34} {won / args.fights * 100:8.1f}% {drawn:6d} {statistics.fmean(kept[0]) * 100:9.1f}% "
              f"{statistics.fmean(kept[1]) * 100:10.1f}%")


if __name__ == "__main__":
    main()
