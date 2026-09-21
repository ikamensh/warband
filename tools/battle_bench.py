"""Set-piece battles on open grass: what a unit behaviour is worth, apart from everything else a match is.

    uv run python tools/battle_bench.py                                  # the standard pairings, each side's arts level
    uv run python tools/battle_bench.py --left drill --right ""          # the left side has researched Battle Drill
    uv run python tools/battle_bench.py --army footman:6,archer:6 --races elf,orc --fights 200
    uv run python tools/battle_bench.py --army footman:7,catapult:2 --right-army footman:10 --aimed left

Two armies of the same price are stood a screen apart and sent at each other with one attack-move each, which is
all a brain does for its soldiers; the fighting is the model's.  Each pairing is fought ``--fights`` times from
both sides of the field, and the readout is the share won by the left army and what the winner had left.

``--aimed`` hands a side's siege engines to a player instead of to their own judgement.  A crew under an
attack-move throws only the stone that trades well against what it would cost its own side
(``model._aim_trade``); a crew a player right-clicked onto a target fires wherever it is pointed and answers
for the splash.  They are two different weapons, and the league only ever plays the first.  The player model here
is the least a human does: every ``AIM_EVERY`` seconds, a crew with no live target in reach is right-clicked onto
the enemy its stone is worth the most on (:func:`best_mark`, the same count of bodies under the splash the crew's
own judgement uses), and left alone while that target lives.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warband.league import fastsim  # noqa: E402

if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()

from warband.league.arena import ensure_variant  # noqa: E402
from warband.sim.model import Attack, Unit, World  # noqa: E402
from warband.sim.rules import DIRECT_HIT, SIEGE_WORTH, SIM_DT, SPLASH_FRACTION, Race, Terrain, UnitType, Upgrade  # noqa: E402

WIDTH, HEIGHT = 44, 30
AIM_EVERY: Final = 0.5  # seconds between a hand-driven player's looks at its siege crews
ARMIES = ("footman:10", "archer:10", "footman:6,archer:6", "footman:5,archer:4,knight:3", "knight:6,archer:6",
          "footman:6,archer:5,cleric:2")


def army_of(text: str) -> list[UnitType]:
    out: list[UnitType] = []
    for term in text.split(","):
        name, _, count = term.partition(":")
        out += [UnitType(name)] * int(count or 1)
    return out


def fight(seed: int, armies: tuple[list[UnitType], list[UnitType]], races: tuple[Race, Race],
          arts: tuple[tuple[Upgrade, ...], tuple[Upgrade, ...]], swap: bool,
          aimed: tuple[bool, bool] = (False, False)) -> tuple[int | None, float, float]:
    """One battle; ``(winner, what the left army has left, what the right has)`` as shares of their price.

    A side whose *aimed* is set has its siege crews driven by :func:`aim_crews` instead of by their own judgement."""
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
    hands = [player for index, player in enumerate(sides) if aimed[index]]
    every = max(1, int(round(AIM_EVERY / SIM_DT)))
    for step in range(int(240 / SIM_DT)):
        if hands and step % every == 0:
            for player in hands:
                aim_crews(world, player)
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


def best_mark(world: World, crew: Unit) -> Unit | None:
    """The enemy a player would drop this crew's stone on: of those it can throw at from where it stands, the one
    with the most under the splash, counted as the crew's own judgement counts it (:data:`SIEGE_WORTH`, in full
    within :data:`DIRECT_HIT` and :data:`SPLASH_FRACTION` out to the splash).  Friendly fire is not counted: that
    is the whole of what a player-ordered stone ignores."""
    splash = world.splash_of(crew)
    reach = world.range_of(crew) + crew.radius
    best: Unit | None = None
    best_worth = 0.0
    for enemy in world.units_near(crew.pos, reach + crew.info.radius):
        if enemy.player == crew.player or enemy.hp <= 0:
            continue
        gap = math.dist(crew.pos, enemy.pos) - enemy.radius - crew.radius
        if not crew.info.min_range <= max(gap, 0.0) <= world.range_of(crew):
            continue
        worth = 0.0
        for other in world.units_near(enemy.pos, splash + 1.0):
            if other.player == crew.player or other.hp <= 0:
                continue
            under = math.dist(enemy.pos, other.pos) - other.radius
            if under <= splash:
                worth += SIEGE_WORTH.get(other.type, 1.0) * (1.0 if under <= DIRECT_HIT else SPLASH_FRACTION)
        if worth > best_worth:
            best, best_worth = enemy, worth
    return best


def aim_crews(world: World, player: int) -> None:
    """One look by a hand-driving player at its siege crews: any crew without a live target in reach is
    right-clicked onto the best mark there is.  A crew already throwing at something is left alone."""
    for crew in world.player_units(player):
        if not crew.info.siege or crew.hp <= 0:
            continue
        order = crew.order
        if isinstance(order, Attack) and not order.auto:
            target = world.entity(order.target)
            if isinstance(target, Unit) and target.hp > 0 and world.range_of(crew) >= math.dist(crew.pos, target.pos) - crew.radius - target.radius:
                continue
        mark = best_mark(world, crew)
        if mark is not None:
            world.attack([crew.id], mark.id)


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
    parser.add_argument("--variant", default=None,
                        help="a rulebook to try, as tools/balance_report.py spells it: scale:catapult.cooldown=1.3")
    parser.add_argument("--aimed", default="none", choices=("none", "left", "right", "both"),
                        help="whose siege crews a player right-clicks onto their targets instead of leaving them to their own judgement")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    if args.variant:
        ensure_variant(args.variant)
    races = tuple(Race(r) for r in args.races.split(","))
    arts = (arts_of(args.left), arts_of(args.right))
    aimed = (args.aimed in ("left", "both"), args.aimed in ("right", "both"))
    print(f"{args.races}; left has {args.left or 'nothing'}, right has {args.right or 'nothing'}; {args.fights} fights a pairing, half from each side")
    print(f"  siege crews aimed by hand: {args.aimed}; rulebook {args.variant or 'standard'}")
    print(f"  {'army':<34} {'left wins':>9} {'draws':>6} {'left keeps':>10} {'right keeps':>11}")
    for text in ([args.army] if args.army else ARMIES):
        armies = (army_of(text), army_of(args.right_army or text))
        won = drawn = 0
        kept: tuple[list[float], list[float]] = ([], [])
        for k in range(args.fights):
            winner, a, b = fight(args.seed * 100_003 + k, armies, races, arts, swap=bool(k % 2), aimed=aimed)  # type: ignore[arg-type]
            won += winner == 0
            drawn += winner is None
            kept[0].append(a)
            kept[1].append(b)
        print(f"  {text:<34} {won / args.fights * 100:8.1f}% {drawn:6d} {statistics.fmean(kept[0]) * 100:9.1f}% "
              f"{statistics.fmean(kept[1]) * 100:10.1f}%")


if __name__ == "__main__":
    main()
