#!/usr/bin/env python
"""Neutral economy and accessibility gates, by race and encounter tier.

Map mode plays whole AI matches with seats cycling every race in a fixed
order. Map-wide camps present are labelled per seat; discovery and feasible
expeditions use that seat's own memory. Production readiness, known-ground
access and freedom from PvP/defense define an opportunity. No opportunity
is reported separately; negative camp economics always fail. --encounters fights
every configured camp with an obtainable common-unit squad for each race,
without magic, in early, mid and prepared brackets: the curve across
brackets is the calibration, and only the prepared bracket gates.
Ancient prepared squads ready ordinary tier-II weapons/armour, a Keep and
Siege Engineering; Strongholds ready tier-I weapons and armour. Slam dodging re-aims every combat pass (0.2 s), the
cadence a brain can actually sustain. Losses include failed engagements;
net bounty is gold/lumber minus replacement prices of units killed by the
wilds or by friendly camp-directed siege stones. Clear time begins with the first blow.

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
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from warband.league import fastsim  # noqa: E402
if __name__ in ("__main__", "__mp_main__"):
    fastsim.activate()
from warband.league import arena  # noqa: E402
from warband.brains.ai import Brain, CAMP_READY_HP, CREEP_REACH, camp_worth, dodge_camp_slams, prepared_cohort, push_is_blind, retry_force  # noqa: E402
from warband.brains.pro_ai import ProBrain, RaceBrain  # noqa: E402
from warband.brains.pro_force import camp_strength, strength  # noqa: E402
from warband.sim import camps, mapgen, path as pathing  # noqa: E402
from warband.sim.model import Attack, Event, Hold, Point, Projectile, Unit, World, dist  # noqa: E402
from warband.sim.races import RACES  # noqa: E402
from warband.sim.rules import CAMP_ENCOUNTERS, CREATURES, SIM_DT, UNITS, UPGRADES, BuildingType, Layout, MapTheme, Race, Terrain, UnitType, Upgrade  # noqa: E402

#: Whole-match race coverage cycles seats through every race in a fixed
#: order instead of the map generator's per-seed draw, so each race
#: appears on both sides across a run.
RACE_ORDER = tuple(race.value for race in Race)


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
    bracket: str = ""


@dataclass
class SeatCoverage:
    """Map-wide supply, and the camps this particular seat discovered and could pursue."""

    seat: int
    agent: str
    race: str
    present: dict[str, int] = field(default_factory=dict)
    discovered: dict[str, int] = field(default_factory=dict)
    feasible: dict[str, int] = field(default_factory=dict)


@dataclass
class ReportResult:
    """A worker result carries its own identity; completion order cannot reassign its seats."""

    rows: list[Measurement]
    coverage: list[SeatCoverage] = field(default_factory=list)
    spec: arena.MatchSpec | None = None


class Measurements:
    """Read combat events without changing the match or its random stream."""

    def __init__(self, world: World, agents: tuple[str, ...]):
        self.agents = agents
        self.owners = {u.id: u.player for u in world.units.values()}
        self.targets = {entity: camp.lair for camp in world.camps for entity in [camp.lair, *camp.guards]}
        self.camps = {camp.lair: camp for camp in world.camps}
        self.present: dict[str, int] = {}
        for camp in world.camps:
            info = CAMP_ENCOUNTERS.get(camp.encounter)
            tier = info.tier if info is not None else "Custom"
            self.present[tier] = self.present.get(tier, 0) + 1
        self.last: dict[int, tuple[int, int]] = {}
        self.stones: dict[int, tuple[Projectile, int | None]] = {}
        self.rows: dict[tuple[int, int], Measurement] = {}
        self.discovered: dict[int, dict[str, int]] = {}  # each seat's own scouting, per tier
        self.feasible: dict[int, set[int]] = {seat: set() for seat in range(world.seats)}
        self._known_routes: dict[tuple[int, int, bool], tuple[int, pathing.Regions]] = {}

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
        # Reports observe every step. Capture a stone's actual target while it
        # is airborne: the crew may move on, die, or clear the camp before impact.
        for stone in world.projectiles.values():
            if stone.kind == "stone" and stone.spell is None and stone.id not in self.stones:
                shooter = world.units.get(stone.source)
                order = shooter.order if shooter is not None else None
                lair = self.targets.get(order.target) if isinstance(order, (Attack, Hold)) else None
                self.stones[stone.id] = (stone, lair)
        landed = [self.stones.pop(uid) for uid in list(self.stones) if uid not in world.projectiles]
        impact_source: int | None = None
        impact_player: int | None = None
        impact_camp: int | None = None
        for event_index, event in enumerate(events):
            if event.kind == "impact":
                impact_source, impact_player, impact_camp = event.entity, event.player, None
                for index, (stone, lair) in enumerate(landed):
                    if stone.source == event.entity and stone.aim == event.pos and event.text == "stone":
                        impact_camp = lair
                        del landed[index]
                        break
                if impact_camp is None and event.text == "stone":
                    # A crew can die on its launch step, before observation.
                    # The camp actually struck by this impact is still causal
                    # evidence, even if the friendly hits come first.
                    for hit in events[event_index + 1:]:
                        if hit.kind == "impact" or (hit.kind == "hit" and hit.entity != impact_source):
                            break
                        if hit.kind == "hit" and hit.other in self.targets:
                            impact_camp = self.targets[hit.other]
                            break
            elif event.kind == "hit":
                if event.entity != impact_source:
                    impact_camp = None
                source_camp = self.targets.get(event.entity)
                target_camp = self.targets.get(event.other)
                source_player = self.owners.get(event.entity)
                if source_camp is not None and event.player is not None and event.player < world.seats:
                    self.last[event.other] = (event.player, source_camp)
                    row = self.row(world, event.player, source_camp)
                elif target_camp is not None and source_player is not None and source_player < world.seats:
                    self.last.pop(event.other, None)
                    row = self.row(world, source_player, target_camp)
                elif (impact_camp is not None and impact_player is not None and impact_player < world.seats
                      and impact_player == event.player):
                    # Only this camp-directed stone caused the friendly casualty;
                    # a former participant's later PvP splash is unrelated.
                    self.last[event.other] = (impact_player, impact_camp)
                    row = self.row(world, impact_player, impact_camp)
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
        # Keep each seat's scouting separate. One side seeing a camp is no
        # opportunity for a different side that never discovered it.
        self.discovered = {}
        for seat in range(world.seats):
            knowledge = world.worker_knowledge[seat]
            counts: dict[str, int] = {}
            for lair in set(knowledge.encounters) | knowledge.cleared_encounters:
                if lair not in self.camps:
                    continue
                info = CAMP_ENCOUNTERS.get(self.camps[lair].encounter)
                tier = info.tier if info is not None else "Custom"
                counts[tier] = counts.get(tier, 0) + 1
            self.discovered[seat] = counts
        return list(self.rows.values())

    def coverage(self, world: World) -> list[SeatCoverage]:
        """Supply is map-wide for each seat; discovery and feasibility belong to that seat alone."""
        self.finish(world)
        result = []
        for seat in range(world.seats):
            counts: dict[str, int] = {}
            for lair in self.feasible[seat]:
                info = CAMP_ENCOUNTERS.get(self.camps[lair].encounter)
                tier = info.tier if info is not None else "Custom"
                counts[tier] = counts.get(tier, 0) + 1
            result.append(SeatCoverage(seat, self.agents[seat], world.players[seat].race.value,
                                       dict(self.present), dict(self.discovered[seat]), counts))
        return result

    def sample_opportunities(self, world: World, brains: list[arena.Agent]) -> None:
        """Sample once a second: an honest, ready expedition while its army is free to pursue it.

        Use production wave/health/strength/travel and retry requirements.
        The read-only army/threat selectors intentionally follow production,
        including retained patients and defense, without issuing any orders.
        Reachability is certified on this seat's remembered terrain, never
        a hidden wall or another seat's scouting. A prepared matrix proves
        access for other agent policies; only shipped camp policies qualify here.
        """
        for seat, agent in enumerate(brains):
            brain = agent.brain if isinstance(agent, RaceBrain) else agent
            if not isinstance(brain, (Brain, ProBrain)) or not brain.profile.creep:
                continue
            if not world.players[seat].alive or world.winner is not None:
                continue
            if brain.attacking and not push_is_blind(world, seat):
                continue
            if brain._threats(world):
                continue
            if isinstance(brain, ProBrain) and brain._home_towers(world):
                continue  # breaking a tower's fire on our economy precedes creeping
            busy = set(brain.raiders) | set(brain.hunt.party) | set(brain.commander.errands) | set(brain.camp_escape)
            army = [unit for unit in brain._army(world) if unit.id not in busy]
            if brain.creeping is not None:
                army = [unit for unit in army if unit.id in brain.creep_party]
            if isinstance(brain, ProBrain):
                profile = brain.profile
                if world.time < max(profile.creep_from, brain.regroup_until):
                    continue
                ready_hp = profile.rejoin_hp
                minimum, ratio, reach = profile.creep_army, profile.creep_ratio, profile.creep_reach
            else:
                profile = brain.profile
                ready_hp = CAMP_READY_HP
                if brain.waves_sent == 0:
                    minimum = profile.first_wave
                else:
                    # _required_wave also logs/caches a cap; compute its public
                    # supply bound here so observation cannot change the brain.
                    workers = sum(unit.is_worker for unit in world.player_units(seat))
                    bound = world.supply(seat)[1] - workers - 2
                    minimum = max(profile.first_wave // 2, min(brain.wave, bound))
                ratio, reach = 1.5, CREEP_REACH
            if not army:
                continue
            halls = world.player_buildings(seat, BuildingType.TOWN_HALL, done=True)
            origin = halls[0].center if halls else army[0].pos
            knowledge = world.worker_knowledge[seat]
            for lair, point in knowledge.encounters.items():
                if lair not in self.camps or lair in knowledge.cleared_encounters:
                    continue
                if brain.creeping is not None and brain.creeping != lair:
                    continue  # an expedition already has its job
                if world.time < brain.camp_retry.get(lair, 0.0):
                    continue
                record = SimpleNamespace(id=lair, center=point)
                if dist(origin, point) > reach * camp_worth(world, seat, record):
                    continue
                cohort = prepared_cohort(world, self._known_cohort(world, seat, army, lair, point), ready_hp)
                force = strength(world, cohort)
                threat = camp_strength(world, seat, point, cohort, lair, brain.camp_seen.get(lair, 0.0))
                if len(cohort) < (1 if threat == 0 else minimum):
                    continue
                if force < ratio * threat:
                    continue
                if force < retry_force(brain.camp_failed.get(lair, 0.0),
                                       brain.camp_at_launch.get(lair, 0.0), threat):
                    continue
                self.feasible[seat].add(lair)

    def _known_cohort(self, world: World, seat: int, army: list[Unit], lair: int, point: Point) -> list[Unit]:
        """Own troops with a certified approach on this seat's terrain and remembered camp watches."""
        knowledge = world.worker_knowledge[seat]
        cohort = []
        for forest in {unit.forest for unit in army if not unit.flying}:
            key = (seat, lair, forest)
            cached = self._known_routes.get(key)
            if cached is None or cached[0] != knowledge.version:
                grid = bytearray(knowledge.blocked)
                if forest:
                    for index, terrain in enumerate(knowledge.terrain):
                        if terrain is Terrain.TREES:
                            grid[index] = 0
                    for building in knowledge.buildings.values():
                        for start, stop in knowledge.spans(building.x, building.y, building.size):
                            grid[start:stop] = b"\x01" * (stop - start)
                grid = camps.navigation(world, seat, grid, {lair}, 0.0, tile_edges=False)
                cached = (knowledge.version, pathing.Regions(grid, world.width, world.height))
                self._known_routes[key] = cached
            regions = cached[1]
            grid = regions.grid
            goal = pathing.nearest_passable((int(point[0]), int(point[1])),
                                           lambda x, y: world.in_bounds((x, y)) and not grid[y * world.width + x],
                                           max_radius=max(world.width, world.height))
            if goal is None:
                continue
            region = regions.label(goal)
            cohort.extend(unit for unit in army if not unit.flying and unit.forest == forest
                          and region != 0 and regions.label(unit.tile) == region)
        cohort.extend(unit for unit in army if unit.flying)
        return cohort


SQUADS = {
    "wolf_den": ((UnitType.FOOTMAN, 4), (UnitType.ARCHER, 6), (UnitType.CLERIC, 2)),
    "spider_nest": ((UnitType.KNIGHT, 4), (UnitType.FOOTMAN, 2), (UnitType.ARCHER, 4), (UnitType.CLERIC, 2)),
    "troll_mound": ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 8), (UnitType.CLERIC, 2), (UnitType.CATAPULT, 1)),
    "stone_cairn": ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 8), (UnitType.CLERIC, 2), (UnitType.CATAPULT, 1)),
    "ancient_sanctum": ((UnitType.KNIGHT, 8), (UnitType.ARCHER, 6), (UnitType.CLERIC, 4), (UnitType.CATAPULT, 4)),
}

ANCIENT_RESEARCH = (Upgrade.KEEP, Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARMOR_1,
                    Upgrade.ARMOR_2, Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.SIEGE)

#: Attainable magic-free openings the brackets measure, same for every
#: encounter: what a small early force, a mid-game mixed army and the
#: tuned prepared expedition each achieve. The curve across brackets is
#: the calibration, not any single squad's clear.
BRACKETS = {
    "early": ((UnitType.FOOTMAN, 4), (UnitType.ARCHER, 4)),
    "mid": ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 6), (UnitType.KNIGHT, 2), (UnitType.CLERIC, 2)),
}

MID_RESEARCH = (Upgrade.BLADES_1, Upgrade.ARROWS_1, Upgrade.ARMOR_1)

#: Slam-dodge cadence in steps: a brain re-aims its micro every combat
#: pass (0.2 s), so the staged dodge does too rather than every 50 ms.
DODGE_EVERY = 4


def default_squad(info) -> tuple[tuple[UnitType, int], ...]:
    """An attainable prepared squad for an encounter with no tuned one, from its tier alone.

    New catalogue identities reuse the same five bodies, so tier pricing
    stays valid for them: raids fall to footmen and archers with healing,
    strongholds add siege and more ranged/support bodies, and anything
    else prices like an Ancient until it earns its own tuning.
    """
    if info.tier == "Raid":
        return ((UnitType.FOOTMAN, 4), (UnitType.ARCHER, 6), (UnitType.CLERIC, 2))
    if info.tier == "Stronghold":
        return ((UnitType.FOOTMAN, 6), (UnitType.ARCHER, 8), (UnitType.CLERIC, 2), (UnitType.CATAPULT, 1))
    return ((UnitType.KNIGHT, 8), (UnitType.ARCHER, 6), (UnitType.CLERIC, 4), (UnitType.CATAPULT, 4))


def squad_for(identity: str) -> tuple[tuple[UnitType, int], ...]:
    """The prepared squad for *identity*: its tuned composition, or the tier default for a new one."""
    return SQUADS.get(identity, default_squad(CAMP_ENCOUNTERS[identity]))


def encounter(seed: int, race: str, identity: str, minutes: float = 4.0, dodge: bool = True,
              bracket: str = "prepared", dodge_every: int = DODGE_EVERY) -> Measurement:
    """A squad fights from outside the leash; losses and bounty come only from real orders and steps."""
    world = World(56, 44, [[Terrain.GRASS] * 56 for _ in range(44)], 2,
                  rng=random.Random(seed), races=[Race(race), Race.HUMAN])
    world.scripted = True
    # A benchmark starting position, not a mid-match order: these ordinary
    # upgrades are available to every race and preserve their actual prerequisites.
    if bracket == "prepared" and CAMP_ENCOUNTERS[identity].tier == "Ancient":
        research = ANCIENT_RESEARCH
    elif bracket == "mid" or (bracket == "prepared" and CAMP_ENCOUNTERS[identity].tier == "Stronghold"):
        research = MID_RESEARCH
    else:
        research = ()
    world.players[0].upgrades.update(research)
    camp = camps.place_encounter(world, (31, 20), identity)
    army = []
    squad = squad_for(identity) if bracket == "prepared" else BRACKETS[bracket]
    for kind, count in squad:
        # The shield line approaches first; shooters and support stand behind
        # it rather than accidentally becoming the front row of the march.
        x = 21.5 if kind in (UnitType.FOOTMAN, UnitType.KNIGHT) else 18.5 if kind is UnitType.ARCHER else 14.5
        for index in range(count):
            army.append(world.spawn_unit(0, kind, (x, 21.5 + (index - (count - 1) / 2) * 1.3)))
    world.reveal_all(0)
    measure = Measurements(world, ("squad", "idle"))
    world.attack_move([u.id for u in army], camp.posts[0])
    for step in range(int(minutes * 60 / SIM_DT)):
        if dodge and step % dodge_every == 0:
            dodge_camp_slams(world, 0, world.player_units(0))
        world.step()
        measure.observe(world, world.take_events())
        if camp.cleared or not world.player_units(0):
            break
        idle = [u.id for u in world.player_units(0) if not u.orders]
        if idle:
            world.attack_move(idle, camp.posts[0])
    if camp.cleared:
        # Completion fixes the clear time; settle only the camp stones already
        # airborne before pricing casualties, without issuing another assault.
        airborne = {uid for uid, (_stone, lair) in measure.stones.items() if lair == camp.lair}
        while any(uid in world.projectiles for uid in airborne):
            world.step()
            measure.observe(world, world.take_events())
    rows = measure.finish(world)
    row = rows[0] if rows else measure.row(world, 0, camp.lair)
    row.bracket = bracket
    row.preparation = sum(u.info.cost.gold + u.info.cost.lumber for u in army)
    row.seed = seed
    row.preparation += sum(UPGRADES[u].cost.gold + UPGRADES[u].cost.lumber for u in research)
    return row


def play(spec: arena.MatchSpec) -> ReportResult:
    races = tuple(Race(r) for r in spec.races) if spec.races is not None else None
    world = mapgen.generate(seed=spec.seed, width=spec.width, height=spec.height, players=spec.players,
                            human=None, races=races, theme=MapTheme(spec.theme),
                            layout=Layout(spec.layout) if spec.layout else None, wilds=spec.wilds,
                            prize=BuildingType(spec.prize) if spec.prize else None)
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
        if world.tick % round(1 / SIM_DT) == 0:
            measure.sample_opportunities(world, agents)
    rows = measure.finish(world)
    for row in rows:
        row.seed, row.layout = spec.seed, spec.layout or ""
    return ReportResult(rows, measure.coverage(world), spec)


def encounter_task(task: tuple[int, str, str, str, float, bool]) -> ReportResult:
    seed, race, identity, bracket, minutes, dodge = task
    row = encounter(seed, race, identity, minutes=minutes, dodge=dodge, bracket=bracket)
    return ReportResult([row])


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
    ap.add_argument("--brackets", default="early,mid,prepared",
                    help="encounter preparation brackets to measure, comma-separated")
    ap.add_argument("--attack-move", action="store_true", help="encounter comparison without dodging marked slams")
    ap.add_argument("--gate", action="store_true",
                    help="require profitable prepared clears; whole-match pursuit where feasible, with nonnegative camp economics")
    ap.add_argument("--details", action="store_true", help="print individual encounter results with reproduction seed/layout")
    args = ap.parse_args(argv)
    tables = hashlib.sha256()
    for path in sorted((Path(__file__).resolve().parents[1] / "warband/assets/constants").glob("*.toml")):
        tables.update(path.name.encode())
        tables.update(path.read_bytes())
    print(f"simulation sources={fastsim.source_key()} tables={tables.hexdigest()}")
    if args.encounters:
        brackets = [b for b in args.brackets.split(",") if b in ("early", "mid", "prepared")]
        if not brackets:
            raise SystemExit("--brackets must name at least one of early,mid,prepared")
        pairs = [(bracket, "prepared squad" if bracket == "prepared" else
                  ", ".join(f"{count} {kind.value}" for kind, count in BRACKETS[bracket])) for bracket in brackets]
        tasks = [(1000 + seed, race.value, identity, bracket, args.minutes or 4.0, not args.attack_move)
                 for seed in range(args.seeds) for race in Race
                 for identity in CAMP_ENCOUNTERS for bracket in brackets]
        runner = encounter_task
        print(f"{len(tasks)} encounters; dodge={not args.attack_move} every {DODGE_EVERY} steps")
        for bracket, squad in pairs:
            print(f"{bracket}: {squad}")
        if "prepared" in brackets:
            for identity in CAMP_ENCOUNTERS:
                squad = squad_for(identity)
                default = "tier default " if identity not in SQUADS else ""
                print(f"prepared {identity}: {default}" + ", ".join(f"{count} {kind.value}" for kind, count in squad))
        print("Ancient research: " + ", ".join(u.value for u in ANCIENT_RESEARCH))
        print("Mid research: " + ", ".join(u.value for u in MID_RESEARCH))
        for kind in CREATURES:
            info = UNITS[kind]
            print(f"{kind.value}: hp={info.hp} damage={info.damage} armor={info.armor} "
                  f"windup={info.windup} splash={info.splash}")
    else:
        agents = tuple(args.agents.split(","))
        width, height = mapgen.dimensions(args.size, len(agents))
        layouts = [args.layout] if args.layout else [l.value for l in mapgen.layouts_for(width, height, len(agents))]
        combos = [(seed, layout) for seed in range(args.seeds) for layout in layouts]
        tasks = [arena.MatchSpec(seed=1000 + seed, agents=agents,
                                 races=tuple(RACE_ORDER[(index + seat) % len(RACE_ORDER)]
                                             for seat in range(len(agents))),
                                 width=width, height=height,
                                 minutes=args.minutes or 20.0, layout=layout, theme=args.theme)
                 for index, (seed, layout) in enumerate(combos)]
        runner = play
        print(f"{len(tasks)} matches, {args.size} {width}x{height}, layouts {','.join(layouts)}, theme {args.theme}, "
              f"races cycle {', '.join(RACE_ORDER)}")
    if args.workers <= 1:
        results = list(map(runner, tasks))
    else:
        with mp.get_context("spawn").Pool(args.workers) as workers:
            results = list(workers.imap_unordered(runner, tasks, chunksize=1))
    groups = defaultdict(list)
    for result in results:
        for row in result.rows:
            groups[(row.agent, row.race, row.encounter if args.encounters else row.tier, row.bracket)].append(row)
    if not args.encounters:
        coverage = defaultdict(list)
        for result in results:
            for seat in result.coverage:
                coverage[(seat.agent, seat.race)].append(seat)
        print("camp access per agent/race: present is map-wide per seat; discovery/readiness use that seat's memory")
        for (agent, race), seats in sorted(coverage.items()):
            tiers = {tier for seat in seats for tier in seat.present}
            for tier in sorted(tiers):
                present = sum(seat.present.get(tier, 0) for seat in seats)
                discovered = sum(seat.discovered.get(tier, 0) for seat in seats)
                feasible = sum(seat.feasible.get(tier, 0) for seat in seats)
                print(f"{agent}/{race} {tier}: map camps {present}, discovered {discovered}, feasible {feasible}")
    print(f"{'agent':10} {'race':6} {'encounter/tier':20} {'bracket':>8} {'engaged':>7} {'clears':>6} {'army':>6} "
          f"{'workers':>7} {'loss g':>7} {'loss w':>7} {'net g':>7} {'net w':>7} {'clear s':>8}")
    for key, rows in sorted(groups.items()):
        completed = [row for row in rows if row.cleared]
        seconds = statistics.mean(row.seconds for row in completed) if completed else float('nan')
        print(f"{key[0]:10} {key[1]:6} {key[2]:20} {key[3]:>8} {len(rows):7} {len(completed):6} "
              f"{sum(r.lost - r.lost_workers for r in rows):6} {sum(r.lost_workers for r in rows):7} "
              f"{sum(r.loss_gold for r in rows):7} {sum(r.loss_lumber for r in rows):7} "
              f"{sum(r.gold - r.loss_gold for r in rows):7} "
              f"{sum(r.lumber - r.loss_lumber for r in rows):7} {seconds:8.1f}")
    if args.details:
        for row in sorted((row for result in results for row in result.rows),
                          key=lambda r: (r.seed, r.layout, r.agent, r.race, r.encounter)):
            print(f"case seed={row.seed} layout={row.layout or 'encounter'} agent={row.agent} race={row.race} "
                  f"camp={row.encounter} bracket={row.bracket or '-'} cleared={row.cleared} "
                  f"army_loss={row.lost - row.lost_workers} "
                  f"worker_loss={row.lost_workers} net={row.gold - row.loss_gold}g/{row.lumber - row.loss_lumber}w "
                  f"seconds={row.seconds:.1f}")
    if args.gate:
        if args.encounters:
            return gate_prepared([row for result in results for row in result.rows])
        return gate_matches(results)
    return 0


def gate_prepared(rows: list[Measurement]) -> int:
    """The staged gate: every prepared engagement clears profitably."""
    prepared = [row for row in rows if row.bracket in ("", "prepared")]
    if not prepared:
        print("FAIL: no prepared encounters measured")
        return 1
    failures = [row for row in prepared
                if not row.cleared or row.gold + row.lumber <= row.loss_gold + row.loss_lumber]
    if failures:
        print(f"FAIL: {len(failures)} prepared engagements failed to clear profitably")
        return 1
    return 0


def gate_matches(results: list[ReportResult]) -> int:
    """The whole-match gate holds ordinary bot camp economics to account per side.

    Negative camp economics always fail. A paid clear is required only for
    a side that discovered an attainable expedition while free to pursue it;
    merely seeing an Ancient with an early army is no such opportunity.
    """
    failed = False
    coverage = defaultdict(list)
    fights = defaultdict(list)
    for result in results:
        for seat in result.coverage:
            coverage[(seat.agent, seat.race)].append(seat)
        for row in result.rows:
            fights[(row.agent, row.race)].append(row)
    for agent, race in sorted(set(coverage) | set(fights)):
        seats = coverage[(agent, race)]
        rows = fights[(agent, race)]
        feasible = sum(sum(seat.feasible.values()) for seat in seats)
        discovered = sum(sum(seat.discovered.values()) for seat in seats)
        net = sum(row.gold + row.lumber - row.loss_gold - row.loss_lumber for row in rows)
        if net < 0:
            print(f"FAIL: {agent}/{race} down {-net} net on {len(rows)} fights "
                  f"({discovered} discovered, {feasible} feasible)")
            failed = True
        elif feasible and not any(row.cleared for row in rows):
            print(f"FAIL: {agent}/{race} no paid clear in {len(seats)} matches "
                  f"({discovered} discovered, {feasible} feasible)")
            failed = True
        elif not feasible and not any(row.cleared for row in rows):
            print(f"NO OPPORTUNITY: {agent}/{race} {discovered} discovered, none ready while free to pursue")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
