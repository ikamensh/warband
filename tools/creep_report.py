#!/usr/bin/env python
"""Neutral economy and accessibility gates, by race and encounter tier.

Map mode plays whole AI matches. --encounters fights every configured camp with
an obtainable common-unit squad for each race, without magic. Ancient squads
prepare ordinary tier-II weapons/armour, a Keep and Siege Engineering.
Losses include failed engagements; net bounty is gold/lumber minus replacement
prices of units killed by the wilds. Clear time begins with the first blow.

    uv run python tools/creep_report.py --agents pro,pro --seeds 12
    uv run python tools/creep_report.py --encounters --seeds 3 --gate
"""
from __future__ import annotations

import argparse
import hashlib
import multiprocessing as mp
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from warband.league import fastsim  # noqa: E402
if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()
from warband.league import arena  # noqa: E402
from warband.brains.ai import dodge_camp_slams  # noqa: E402
from warband.sim import camps, mapgen  # noqa: E402
from warband.sim.model import Event, World  # noqa: E402
from warband.sim.races import RACES  # noqa: E402
from warband.sim.rules import CAMP_ENCOUNTERS, CREATURES, SIM_DT, UNITS, UPGRADES, Layout, MapTheme, Race, Terrain, UnitType, Upgrade  # noqa: E402


@dataclass
class Measurement:
    agent: str
    race: str
    encounter: str
    tier: str
    started: float = -1.0
    cleared: bool = False
    seconds: float = 0.0
    lost: int = 0
    lost_workers: int = 0
    loss_gold: int = 0
    loss_lumber: int = 0
    gold: int = 0
    lumber: int = 0
    preparation: int = 0  # army + research price, paid once rather than charged as a casualty
    seed: int = 0
    layout: str = ""


class Measurements:
    """Read combat events without changing the match or its random stream."""

    def __init__(self, world: World, agents: tuple[str, ...]):
        self.agents = agents
        self.owners = {u.id: u.player for u in world.units.values()}
        self.targets = {entity: camp.lair for camp in world.camps for entity in [camp.lair, *camp.guards]}
        self.camps = {camp.lair: camp for camp in world.camps}
        self.last: dict[int, tuple[int, int]] = {}
        self.involvement: dict[int, int] = {}
        self.rows: dict[tuple[int, int], Measurement] = {}

    def row(self, world: World, player: int, lair: int) -> Measurement:
        key = (player, lair)
        if key not in self.rows:
            identity = self.camps[lair].encounter
            info = CAMP_ENCOUNTERS.get(identity)
            self.rows[key] = Measurement(self.agents[player], world.players[player].race.value, identity,
                                         info.tier if info else "Custom")
        return self.rows[key]

    def observe(self, world: World, events: list[Event]) -> None:
        self.owners.update((u.id, u.player) for u in world.units.values())
        for event in events:
            if event.kind == "hit":
                source_camp = self.targets.get(event.entity)
                target_camp = self.targets.get(event.other)
                source_player = self.owners.get(event.entity)
                if source_camp is not None and event.player is not None and event.player < world.seats:
                    self.last[event.other] = (event.player, source_camp)
                    self.involvement[event.other] = source_camp
                    row = self.row(world, event.player, source_camp)
                elif target_camp is not None and source_player is not None and source_player < world.seats:
                    self.last.pop(event.other, None)
                    self.involvement[event.entity] = target_camp
                    row = self.row(world, source_player, target_camp)
                elif source_player == event.player and event.other in self.involvement:
                    # A siege stone on the clearing army is a real replacement
                    # cost of that encounter, even though the wilds did not kill it.
                    lair = self.involvement[event.other]
                    self.last[event.other] = (event.player, lair)
                    row = self.row(world, event.player, lair)
                else:
                    self.last.pop(event.other, None)
                    continue
                if row.started < 0:
                    row.started = world.time
            elif event.kind == "death" and event.entity in self.last:
                player, lair = self.last.pop(event.entity)
                row = self.row(world, player, lair)
                cost = RACES[world.players[player].race].units[UnitType(event.text)].cost
                row.lost += 1
                row.lost_workers += int(event.text == UnitType.PEASANT.value)
                row.loss_gold += cost.gold
                row.loss_lumber += cost.lumber
            elif event.kind == "hoard" and event.player is not None:
                if event.other not in self.camps:
                    continue
                row = self.row(world, event.player, event.other)
                row.gold += event.amount
                row.lumber += event.amount2
        for (player, lair), row in self.rows.items():
            if self.camps[lair].cleared and row.seconds == 0.0:
                # A passer-by killed by the camp did not clear it when another
                # seat finishes the guards. Completion belongs to contributors.
                row.cleared = row.gold + row.lumber > 0
                row.seconds = world.time - row.started

    def finish(self, world: World) -> list[Measurement]:
        for row in self.rows.values():
            if row.seconds == 0.0 and row.started >= 0:
                row.seconds = world.time - row.started
        return list(self.rows.values())


SQUADS = {
    "wolf_den": ((UnitType.FOOTMAN, 4), (UnitType.ARCHER, 6), (UnitType.CLERIC, 2)),
    "spider_nest": ((UnitType.KNIGHT, 4), (UnitType.FOOTMAN, 2), (UnitType.ARCHER, 4), (UnitType.CLERIC, 2)),
    "troll_mound": ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 8), (UnitType.CLERIC, 2), (UnitType.CATAPULT, 1)),
    "stone_cairn": ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 8), (UnitType.CLERIC, 2), (UnitType.CATAPULT, 1)),
    "ancient_sanctum": ((UnitType.KNIGHT, 8), (UnitType.ARCHER, 6), (UnitType.CLERIC, 4), (UnitType.CATAPULT, 4)),
}

ANCIENT_RESEARCH = (Upgrade.KEEP, Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARMOR_1,
                    Upgrade.ARMOR_2, Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.SIEGE)


def encounter(seed: int, race: str, identity: str, minutes: float = 4.0, dodge: bool = True) -> Measurement:
    """A squad fights from outside the leash; losses and bounty come only from real orders and steps."""
    world = World(56, 44, [[Terrain.GRASS] * 56 for _ in range(44)], 2,
                  rng=random.Random(seed), races=[Race(race), Race.HUMAN])
    world.scripted = True
    # A benchmark starting position, not a mid-match order: these ordinary
    # upgrades are available to every race and preserve their actual prerequisites.
    if CAMP_ENCOUNTERS[identity].tier == "Ancient":
        world.players[0].upgrades.update(ANCIENT_RESEARCH)
    camp = camps.place_encounter(world, (31, 20), identity)
    army = []
    for kind, count in SQUADS[identity]:
        # The shield line approaches first; shooters and support stand behind
        # it rather than accidentally becoming the front row of the march.
        x = 21.5 if kind in (UnitType.FOOTMAN, UnitType.KNIGHT) else 18.5 if kind is UnitType.ARCHER else 14.5
        for index in range(count):
            army.append(world.spawn_unit(0, kind, (x, 21.5 + (index - (count - 1) / 2) * 1.3)))
    world.reveal_all(0)
    measure = Measurements(world, ("squad", "idle"))
    world.attack_move([u.id for u in army], camp.posts[0])
    for _ in range(int(minutes * 60 / SIM_DT)):
        if dodge:
            dodge_camp_slams(world, 0, world.player_units(0))
        world.step()
        measure.observe(world, world.take_events())
        if camp.cleared or not world.player_units(0):
            break
        idle = [u.id for u in world.player_units(0) if not u.orders]
        if idle:
            world.attack_move(idle, camp.posts[0])
    rows = measure.finish(world)
    row = rows[0] if rows else measure.row(world, 0, camp.lair)
    row.preparation = sum(u.info.cost.gold + u.info.cost.lumber for u in army)
    row.seed = seed
    if CAMP_ENCOUNTERS[identity].tier == "Ancient":
        row.preparation += sum(UPGRADES[u].cost.gold + UPGRADES[u].cost.lumber for u in ANCIENT_RESEARCH)
    return row


def play(spec: arena.MatchSpec) -> list[Measurement]:
    races = tuple(Race(r) for r in spec.races) if spec.races is not None else None
    world = mapgen.generate(seed=spec.seed, width=spec.width, height=spec.height, players=spec.players,
                            human=None, races=races, theme=MapTheme(spec.theme),
                            layout=Layout(spec.layout) if spec.layout else None)
    agents = [arena.make_agent(name, seat, spec.seed) for seat, name in enumerate(spec.agents)]
    rngs = [random.Random(spec.seed * 1000003 + seat) for seat in range(spec.players)]
    measure = Measurements(world, spec.agents)
    for _ in range(int(spec.minutes * 60 / SIM_DT)):
        if world.winner is not None:
            break
        for brain, rng in zip(agents, rngs):
            brain.think(world, rng)
        world.step()
        measure.observe(world, world.take_events())
    rows = measure.finish(world)
    for row in rows:
        row.seed, row.layout = spec.seed, spec.layout or ""
    return rows


def encounter_task(task: tuple[int, str, str, float, bool]) -> list[Measurement]:
    return [encounter(*task)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agents", default="pro,pro")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--size", default="Medium", choices=list(mapgen.SIZES))
    ap.add_argument("--layout", default=None)
    ap.add_argument("--theme", default=MapTheme.SUMMER.value, choices=[t.value for t in MapTheme])
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() // 2))
    ap.add_argument("--encounters", action="store_true", help="every race against every encounter, common-unit squads")
    ap.add_argument("--attack-move", action="store_true", help="encounter comparison without dodging marked slams")
    ap.add_argument("--gate", action="store_true", help="require profitable prepared clears or nonnegative whole-match camp economics")
    ap.add_argument("--details", action="store_true", help="print individual encounter results with reproduction seed/layout")
    args = ap.parse_args(argv)
    tables = hashlib.sha256()
    for path in sorted((Path(__file__).resolve().parents[1] / "warband/assets/constants").glob("*.toml")):
        tables.update(path.name.encode())
        tables.update(path.read_bytes())
    print(f"simulation sources={fastsim.source_key()} tables={tables.hexdigest()}")
    if args.encounters:
        tasks = [(1000 + seed, race.value, identity, args.minutes or 4.0, not args.attack_move)
                 for seed in range(args.seeds) for race in Race for identity in CAMP_ENCOUNTERS]
        runner = encounter_task
        print(f"{len(tasks)} encounters; dodge={not args.attack_move}")
        for identity, squad in SQUADS.items():
            print(f"{identity}: " + ", ".join(f"{count} {kind.value}" for kind, count in squad))
        print("Ancient research: " + ", ".join(u.value for u in ANCIENT_RESEARCH))
        for kind in CREATURES:
            info = UNITS[kind]
            print(f"{kind.value}: hp={info.hp} damage={info.damage} armor={info.armor} "
                  f"windup={info.windup} splash={info.splash}")
    else:
        agents = tuple(args.agents.split(","))
        width, height = mapgen.dimensions(args.size, len(agents))
        layouts = [args.layout] if args.layout else [l.value for l in mapgen.layouts_for(width, height, len(agents))]
        tasks = [arena.MatchSpec(seed=1000 + seed, agents=agents, width=width, height=height,
                                 minutes=args.minutes or 20.0, layout=layout, theme=args.theme)
                 for seed in range(args.seeds) for layout in layouts]
        runner = play
        print(f"{len(tasks)} matches, {args.size} {width}x{height}, layouts {','.join(layouts)}, theme {args.theme}")
    if args.workers <= 1:
        results = list(map(runner, tasks))
    else:
        with mp.get_context("spawn").Pool(args.workers) as workers:
            results = list(workers.imap_unordered(runner, tasks, chunksize=1))
    groups = defaultdict(list)
    for rows in results:
        for row in rows:
            groups[(row.agent, row.race, row.encounter if args.encounters else row.tier)].append(row)
    print(f"{'agent':10} {'race':6} {'encounter/tier':20} {'engaged':>7} {'clears':>6} {'army':>6} {'workers':>7} "
          f"{'loss g':>7} {'loss w':>7} {'net g':>7} {'net w':>7} {'clear s':>8}")
    for key, rows in sorted(groups.items()):
        completed = [row for row in rows if row.cleared]
        seconds = statistics.mean(row.seconds for row in completed) if completed else float('nan')
        print(f"{key[0]:10} {key[1]:6} {key[2]:20} {len(rows):7} {len(completed):6} "
              f"{sum(r.lost - r.lost_workers for r in rows):6} {sum(r.lost_workers for r in rows):7} "
              f"{sum(r.loss_gold for r in rows):7} {sum(r.loss_lumber for r in rows):7} "
              f"{sum(r.gold - r.loss_gold for r in rows):7} "
              f"{sum(r.lumber - r.loss_lumber for r in rows):7} {seconds:8.1f}")
    if args.details:
        for row in sorted((row for batch in results for row in batch),
                          key=lambda r: (r.seed, r.layout, r.agent, r.race, r.encounter)):
            print(f"case seed={row.seed} layout={row.layout or 'encounter'} agent={row.agent} race={row.race} "
                  f"camp={row.encounter} cleared={row.cleared} army_loss={row.lost - row.lost_workers} "
                  f"worker_loss={row.lost_workers} net={row.gold - row.loss_gold}g/{row.lumber - row.loss_lumber}w "
                  f"seconds={row.seconds:.1f}")
    failures = [row for rows in results for row in rows
                if not row.cleared or row.gold + row.lumber <= row.loss_gold + row.loss_lumber]
    if args.gate:
        if args.encounters and failures:
            print(f"FAIL: {len(failures)} engagements failed to clear profitably")
            return 1
        if not args.encounters:
            failed = False
            for agent in set(args.agents.split(",")):
                for race in Race:
                    rows = [row for batch in results for row in batch if row.agent == agent and row.race == race.value]
                    if sum(row.gold + row.lumber - row.loss_gold - row.loss_lumber for row in rows) < 0:
                        print(f"FAIL: {agent}/{race.value} lost more replacing camp casualties than its earned bounty")
                        failed = True
                    elif not any(row.cleared for row in rows):
                        print(f"{agent}/{race.value}: no paid clear; no net camp loss (prepared matrix proves accessibility)")
            if failed:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
