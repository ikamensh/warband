"""Set-piece battles on open grass: what a unit behaviour is worth, apart from everything else a match is.

    uv run python tools/battle_bench.py                                  # the standard pairings, each side's arts level
    uv run python tools/battle_bench.py --left drill --right ""          # the left side has researched Battle Drill
    uv run python tools/battle_bench.py --army footman:6,archer:6 --races elf,orc --fights 200
    uv run python tools/battle_bench.py --army footman:7,catapult:2 --right-army footman:10 --aimed left
    uv run python tools/battle_bench.py --army footman:2,archer:3,knight:1 --cast all --fights 120   # one cast of each spell
    uv run python tools/battle_bench.py --army footman:2,archer:3,knight:1 --right-army footman:2,archer:3,knight:2 --cast all   # a knight short

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

``--cast`` gives the left side one spell (WB-067), cast once by a scripted caster at the spell's natural moment, where
the brains' judge for it (``brains.magic``) finds the best point, and with the aether to pay for it: a buff, a blow, a
hold on the rival army or a summoning at contact (the first step a unit of either side has a rival within its reach
and a step), Mend once the caster's army has taken :data:`MEND_WOUNDS` of its life or :data:`MEND_WAIT` seconds after
contact.  ``--cast all`` fights every pairing with no spell and then with each of the nine: what one well-timed cast
is worth in an even fight is its row against the first.  ``--moment brain`` hands the spell to a Master's caster
instead (``brains.magic.Magus``: its judges, its bar and its moment), for one cast from a store short of full, each
side with a vault by the middle of the field (:class:`BrainCaster`): whether, when and where a Master casts it; its
``no spell`` row is the same field without a cast.
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

from dataclasses import replace  # noqa: E402

from warband.brains import magic  # noqa: E402
from warband.brains.pro_profiles import PRO_VANGUARD  # noqa: E402
from warband.league.arena import ensure_variant  # noqa: E402
from warband.sim.model import Attack, Point, Unit, World, dist  # noqa: E402
from warband.sim.rules import (AETHER_STORE, DIRECT_HIT, SIEGE_WORTH, SIM_DT, SPELLS, SPLASH_FRACTION, BuildingType, Race, Terrain,  # noqa: E402
                                Touch, UnitType, Upgrade)

WIDTH, HEIGHT = 44, 30
CAST_EVERY: Final = 4  # --cast: steps between the scripted caster's looks, a combat pass as Master's
MEND_WOUNDS: Final = 0.25  # --cast mend: the share of its army's life taken before Mend is cast…
MEND_WAIT: Final = 10.0  # …or this many seconds after contact, whichever comes first
APPROACH: Final = 4.0  # --cast: a delayed blow is cast on the approach, this many tiles further out than contact
VAULT_AT: Final = (17, 7)  # --moment brain: a vault above the near side of the middle (the far side's mirrored), whose reach covers the middle
BRAIN_STORE: Final = AETHER_STORE - 10  # --moment brain: a store short of full (a full one halves the caster's bar)
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
          aimed: tuple[bool, bool] = (False, False), cast: Upgrade | None = None,
          moment: str = "natural", store: int = BRAIN_STORE) -> tuple[int | None, float, float, bool]:
    """One battle; ``(winner, what the left army has left, what the right has, whether the spell was cast)``, the
    armies' remains as shares of their price.

    A side whose *aimed* is set has its siege crews driven by :func:`aim_crews` instead of by their own judgement; with
    *cast* the left side casts that spell once, as its :class:`Caster` (or with *moment* "brain" its :class:`BrainCaster`,
    *store* aether in hand) says."""
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
        if moment == "brain":
            # Both sides have one, the caster's alone holding aether: a vault in sight draws blows and gives sight, and
            # the caster's alone won the mirror 75 % without a cast.
            world.place_building(player, BuildingType.VAULT, VAULT_AT if x0 < WIDTH / 2 else (WIDTH - VAULT_AT[0] - 2, VAULT_AT[1]))
    caster: Caster | BrainCaster | None = None
    if cast is not None:
        caster = BrainCaster(sides[0], cast, world, store) if moment == "brain" else Caster(sides[0], cast, world, moment)
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
        if caster is not None and step % CAST_EVERY == 0:
            caster.look(world)
        world.step()
        world.take_events()
        alive = [any(not u.expires for u in world.player_units(p)) for p in (0, 1)]
        if not all(alive):
            break
    left = [0.0, 0.0]
    for index, player in enumerate(sides):
        for unit in world.player_units(player):
            if unit.expires:
                continue  # a summoned elemental is the spell's, not the army's price
            cost = unit.info.cost
            left[index] += (cost.gold + cost.lumber) * unit.hp / unit.max_hp
    shares = (left[0] / price[0], left[1] / price[1])
    winner = None if (shares[0] > 0) == (shares[1] > 0) else (0 if shares[0] > 0 else 1)
    return winner, shares[0], shares[1], caster is not None and caster.done


class Caster:
    """The scripted caster of ``--cast``: one cast of its spell, at its natural moment, where the brains' judge for it
    finds the most to do.  It has the aether (a store no vault holds, so the far price is paid) and nothing else of a
    brain: no bar, no reserve, no second cast."""

    def __init__(self, player: int, spell: Upgrade, world: World, moment: str = "natural") -> None:
        self.player, self.spell, self.info = player, spell, SPELLS[spell]
        self.margin = APPROACH if moment == "approach" or moment == "natural" and self.info.delay else 1.0
        world.players[player].upgrades.add(spell)
        world.players[player].aether = 100_000
        self.life = 0.0
        self.contact: float | None = None
        self.done = False

    def _in_contact(self, world: World) -> bool:
        for u in world.units.values():
            if u.hp <= 0 or u.is_worker:
                continue
            reach = world.range_of(u) + self.margin
            for foe in world.units_near(u.pos, reach + 1.0):
                if foe.player != u.player and foe.hp > 0 and dist(u.pos, foe.pos) - u.radius - foe.radius <= reach:
                    return True
        return False

    def point(self, world: World) -> Point | None:
        """Where the judge puts it now: over the most of ours, on the most of theirs, or between the two fronts."""
        info, sides = self.info, magic.Sides(world, self.player)
        if info.summons is not None:
            ours, theirs = [u for u in sides.army if not u.expires], sides.armed
            if not ours or not theirs:
                return None
            ours = sorted(ours, key=lambda u: min(dist(u.pos, foe.pos) for foe in theirs))[:4]
            theirs = sorted(theirs, key=lambda foe: min(dist(u.pos, foe.pos) for u in ours))[:4]
            a, b = magic._centre(ours), magic._centre(theirs)
            return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if info.touches is Touch.OWN:
            sides.engaged = sides.army  # the whole army is in the fight the cast is for
            options = magic._buff(world, self.player, info, sides)
        elif info.damage:
            options = magic._blow(world, self.player, info, sides)
        else:
            options = magic._cover_rivals(info, sides.armed)
        return max(options, key=lambda option: option[1])[0] if options else None

    def look(self, world: World) -> None:
        if self.done:
            return
        army = [u for u in world.player_units(self.player) if not u.expires]
        hp = plain = 0.0
        for u in army:
            hp += u.hp
            plain += u.max_hp
        if not self.life:
            self.life = plain
        if self.contact is None:
            if not self._in_contact(world):
                return
            self.contact = world.time
        if self.info.lays and any(kind.hp_per_second > 0.0 for kind in self.info.lays):
            if hp > (1.0 - MEND_WOUNDS) * self.life and world.time - self.contact < MEND_WAIT:
                return
        point = self.point(world)
        if point is None or world.can_cast(self.player, self.spell, point) is not None:
            return
        world.cast(self.player, self.spell, point)
        self.done = True


class BrainCaster:
    """``--moment brain``: the spell in a Master's hands, cast once, when and where its caster (``brains.magic.Magus``)
    finds it worth its price and its bar: :func:`fight` gives each side a vault by :data:`VAULT_AT` (off any rift: they
    draw nothing), whose reach covers the middle of the field, and the caster's store holds *store* (``--store``;
    :data:`BRAIN_STORE` pays a near cast of any level short of a full store, which would halve the bar)."""

    def __init__(self, player: int, spell: Upgrade, world: World, store: int) -> None:
        self.player = player
        level = SPELLS[spell].level
        self.magus = magic.Magus(replace(PRO_VANGUARD, **{f"spell_{level}": spell}))  # type: ignore[arg-type]
        world.players[player].upgrades.add(spell)
        world.players[player].aether = store
        self.done = False

    def look(self, world: World) -> None:
        if not self.done:
            self.done = bool(self.magus.cast(world, self.player))


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
    parser.add_argument("--cast", default="", help="a spell the left side casts once at its natural moment, or all: none and each of the nine (WB-067)")
    parser.add_argument("--moment", default="natural", choices=("natural", "contact", "approach", "brain"),
                        help="when --cast casts: at contact, on the approach, its natural moment (a delayed blow on the approach, "
                             "Mend on wounds), or when and where a Master's caster would")
    parser.add_argument("--store", type=int, default=BRAIN_STORE,
                        help="--moment brain: the aether in the caster's store; its one vault holds AETHER_STORE")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    casts: list[Upgrade | None] = [None, *SPELLS] if args.cast == "all" else [Upgrade(args.cast) if args.cast else None]
    if args.variant:
        ensure_variant(args.variant)
    races = tuple(Race(r) for r in args.races.split(","))
    arts = (arts_of(args.left), arts_of(args.right))
    aimed = (args.aimed in ("left", "both"), args.aimed in ("right", "both"))
    print(f"{args.races}; left has {args.left or 'nothing'}, right has {args.right or 'nothing'}; {args.fights} fights a pairing, half from each side")
    print(f"  siege crews aimed by hand: {args.aimed}; rulebook {args.variant or 'standard'}")
    print(f"  {'army':<34} {'left wins':>9} {'draws':>6} {'left keeps':>10} {'right keeps':>11} {'cast in':>8}")
    for text in ([args.army] if args.army else ARMIES):
        armies = (army_of(text), army_of(args.right_army or text))
        for cast in casts:
            won = drawn = casts_made = 0
            kept: tuple[list[float], list[float]] = ([], [])
            for k in range(args.fights):
                winner, a, b, made = fight(args.seed * 100_003 + k, armies, races, arts, swap=bool(k % 2), aimed=aimed,  # type: ignore[arg-type]
                                           cast=cast, moment=args.moment, store=args.store)
                won += winner == 0
                drawn += winner is None
                casts_made += made
                kept[0].append(a)
                kept[1].append(b)
            label = text if cast is None and len(casts) == 1 else f"{text} {cast.value if cast else 'no spell'}"
            print(f"  {label:<34} {won / args.fights * 100:8.1f}% {drawn:6d} {statistics.fmean(kept[0]) * 100:9.1f}% "
                  f"{statistics.fmean(kept[1]) * 100:10.1f}% {casts_made / args.fights * 100:7.1f}%", flush=True)

if __name__ == "__main__":
    main()
