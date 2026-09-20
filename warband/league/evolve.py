"""Breeding brains: a genetic search over what a :class:`~warband.brains.pro_ai.ProProfile` plays by.

    uv run python tools/evolve.py run --race orc --out docs/evidence/ga/orc-1 --generations 40

A brain here is a composition of behaviours (how it gathers, what it builds and
when, what army it fields, when it fights, how it defends, how it harasses),
each behaviour a handful of :data:`GENES`.  An individual is one value per
gene; :func:`profile_of` turns it into the profile a ``ProBrain`` plays.
Crossover moves whole behaviours between parents, so an opening that works
travels with its numbers, and mutation nudges single genes.

Fitness is what the ladder measures: the share of games an individual takes
from a panel of opponents, from both corners of boards every individual of a
generation shares (common random numbers, so two individuals differ by their
play and not by their maps), on seeds no earlier generation saw (so nothing is
bred into the maps it was judged on).  A win rate from sixty games is worth
about six points either way, so an individual's record is kept per opponent
over every generation it survives, and what selection reads is that record
shrunk towards the population's (:func:`fitness`): a newcomer's lucky sixty
games do not outrank a veteran's six hundred.

The panel is the fixed opponents a run is given plus its own hall of fame, the
best of earlier generations, so the population is pulled past whatever beats
the fixed opponents alone.  A race is forced on the individual being judged
(``--race``), while its opponents take every race in turn: brains are bred per
race, and one evolved player is a posture per race (``RacePostures`` in
:mod:`warband.brains.pro_ai`).
"""

from __future__ import annotations

import json
import math
import multiprocessing as mp
import random
import statistics
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from warband.brains.pro_ai import PRO, PRO_PROFILES, ProBrain, ProProfile
from warband.league import arena
from warband.league.arena import MatchResult, MatchSpec
from warband.sim.rules import BuildingType, Race, UnitType, Upgrade

Genes = dict[str, float]  # one value per gene: numbers as they are, booleans as 0 or 1

RACE_VALUES: tuple[str, ...] = tuple(race.value for race in Race)


@dataclass(frozen=True)
class Gene:
    """One number of a behaviour: the profile field it sets (or a special, see :func:`profile_of`) and its range."""

    name: str
    behaviour: str  # crossover moves a behaviour as one piece
    low: float
    high: float
    kind: str = "float"  # "float", "int", "bool" or "choice" (an integer code with no order)

    def clip(self, value: float) -> float:  # a choice is an integer code like any other
        value = min(self.high, max(self.low, value))
        if self.kind == "float":
            return round(value, 3)
        return float(int(round(value)))

    def draw(self, rng: random.Random) -> float:
        return self.clip(rng.uniform(self.low, self.high))

    def nudge(self, value: float, rng: random.Random, scale: float) -> float:
        """*value* moved by a normal step of *scale* of the range; a boolean flips, a small integer moves one."""
        if self.kind == "bool":
            return 1.0 - value
        if self.kind == "choice":
            return self.draw(rng)  # codes are names, not sizes: a step to the next one means nothing
        step = rng.gauss(0.0, scale * (self.high - self.low))
        if self.kind == "int" and abs(step) < 1.0:
            step = math.copysign(1.0, step)
        return self.clip(value + step)


_PLAN_TYPES: tuple[UnitType, ...] = (UnitType.FOOTMAN, UnitType.ARCHER, UnitType.SCOUT, UnitType.KNIGHT,
                                     UnitType.CATAPULT, UnitType.CLERIC)
_TECH_TYPES: tuple[tuple[BuildingType, int], ...] = ((BuildingType.BARRACKS, 4), (BuildingType.BLACKSMITH, 1), (BuildingType.STABLES, 3),
                                                     (BuildingType.WORKSHOP, 2), (BuildingType.CHURCH, 2))
#: What a slot of an opening may hold, by its code; 0 leaves the slot empty.
_OPENING_CODES: tuple[BuildingType | None, ...] = (None, BuildingType.BARRACKS, BuildingType.LUMBER_MILL, BuildingType.TOWER,
                                                   BuildingType.BLACKSMITH, BuildingType.STABLES, BuildingType.TOWN_HALL,
                                                   BuildingType.CHURCH, BuildingType.WORKSHOP)
OPENING_SLOTS = 6
#: The chains a research order is built from, and each race's first and second art, in RESEARCH_ORDER's order.
_CHAINS: dict[str, tuple[Upgrade, Upgrade]] = {"blades": (Upgrade.BLADES_1, Upgrade.BLADES_2), "armor": (Upgrade.ARMOR_1, Upgrade.ARMOR_2),
                                               "arrows": (Upgrade.ARROWS_1, Upgrade.ARROWS_2)}
_FIRST_ARTS: tuple[Upgrade, ...] = (Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS)
_SECOND_ARTS: tuple[Upgrade, ...] = (Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER)


def research_order(genes: Mapping[str, float]) -> tuple[Upgrade, ...]:
    """The order ``res.*`` spells: each chain's first tier by its priority and its second a whole point behind, the
    race's first art by ``res.arts`` and its second half a point behind, siege engineering last but for the seconds."""
    scored: list[tuple[float, Upgrade]] = []
    for chain, (first, second) in _CHAINS.items():
        scored += [(genes[f"res.{chain}"], first), (genes[f"res.{chain}"] - 1.0, second)]
    scored += [(genes["res.arts"], art) for art in _FIRST_ARTS]
    scored += [(genes["res.arts"] - 0.5, art) for art in _SECOND_ARTS]
    scored.append((-0.75, Upgrade.SIEGE))
    scored.append((genes["res.marks"], Upgrade.MARKSMANSHIP))
    return tuple(upgrade for _score, upgrade in sorted(scored, key=lambda row: -row[0]))


def _g(name: str, behaviour: str, low: float, high: float, kind: str = "float") -> Gene:
    return Gene(name, behaviour, low, high, kind)


#: Every gene, by the behaviour it belongs to.  ``plan.*`` and ``tech.*`` are specials: the shares of an army plan
#: (``plan.on`` decides whether the race's own plan is overruled) and how many of each tech building go up early.
GENES: tuple[Gene, ...] = (
    _g("workers_per_mine", "economy", 6, 16, "int"),
    _g("lumber_share", "economy", 0.15, 0.55),
    _g("lumber_floor_panic", "economy", 0, 800, "int"),
    _g("panic_gold", "economy", 300, 3000, "int"),
    _g("lumber_stock", "economy", 800, 4000, "int"),
    _g("max_workers", "economy", 14, 44, "int"),
    _g("soldiers_before_workers", "economy", 0, 10, "int"),
    _g("wood_crew", "economy", 0, 8, "int"),
    _g("wood_from", "economy", 5, 16, "int"),
    _g("wood_lead", "economy", 0, 1, "bool"),
    _g("wood_per_hand", "economy", 100, 600, "int"),
    _g("wood_release", "economy", 400, 2500, "int"),
    _g("supply_slack", "construction", 1, 10, "int"),
    _g("supply_per_producer", "construction", 0.0, 4.0),
    _g("max_sites", "construction", 2, 7, "int"),
    _g("surplus_gold", "construction", 200, 2500, "int"),
    _g("lumber_floor", "construction", 0, 500, "int"),
    _g("barracks_first", "construction", 0, 1, "bool"),
    *(_g(f"open.{k}", "opening", 0, len(_OPENING_CODES) - 1, "choice") for k in range(OPENING_SLOTS)),
    _g("opening_hold", "opening", 0, 1, "bool"),
    _g("barracks_per_hall", "construction", 1, 6, "int"),
    _g("gold_per_barracks", "construction", 600, 3000, "int"),
    _g("max_producers", "construction", 4, 14, "int"),
    _g("expand", "expansion", 0, 1, "bool"),
    _g("expand_early", "expansion", 0, 1, "bool"),
    _g("max_halls", "expansion", 1, 4, "int"),
    _g("mine_floor", "expansion", 2000, 20000, "int"),
    _g("prospect.on", "expansion", 0, 1, "bool"),
    _g("prospect_floor", "expansion", 6000, 30000, "int"),
    _g("attack_ratio", "engagement", 0.5, 2.0),
    _g("retreat_ratio", "engagement", 0.2, 0.8),
    _g("regroup_seconds", "engagement", 10, 90),
    _g("min_army", "engagement", 3, 24, "int"),
    _g("reinforce_group", "engagement", 1, 8, "int"),
    _g("ignore_raid_ratio", "engagement", 0.0, 0.8),
    _g("stale_seconds", "engagement", 10, 60),
    _g("symmetry_prior", "engagement", 0.1, 1.6),
    _g("push_upgrades", "engagement", 0, 4, "int"),
    _g("push_after", "engagement", 0, 420),
    _g("push_by", "engagement", 240, 720),
    _g("abort.on", "engagement", 0, 1, "bool"),
    _g("abort_ratio", "engagement", 0.8, 3.0),
    _g("guards", "defence", 0, 4, "int"),
    _g("defend.on", "defence", 0, 1, "bool"),
    _g("defend_ratio", "defence", 0.5, 3.0),
    _g("towers_early", "defence", 0, 3, "int"),
    _g("tower_count", "defence", 0, 6, "int"),
    _g("raid", "harass", 0, 1, "bool"),
    _g("raiders", "harass", 0, 6, "int"),
    _g("scout", "harass", 0, 1, "bool"),
    _g("scout_from", "harass", 20, 120),
    _g("rush_towers", "harass", 0, 2, "int"),
    _g("plan.on", "army", 0, 1, "bool"),
    *(_g(f"plan.{t.value}", "army", 0.0, 1.0) for t in _PLAN_TYPES),
    _g("strict_plan", "army", 0, 1, "bool"),
    _g("save_for_wanted", "army", 0, 1, "bool"),
    _g("counter_from", "army", 0.1, 1.1),
    _g("counter_strength", "army", 0.5, 3.0),
    _g("siege", "army", 0, 1, "bool"),
    _g("clerics", "army", 0, 1, "bool"),
    _g("research", "tech", 0, 1, "bool"),
    _g("res.on", "tech", 0, 1, "bool"),
    *(_g(f"res.{chain}", "tech", 0.0, 1.0) for chain in (*_CHAINS, "arts", "marks")),
    *(_g(f"tech.{t.value}", "tech", 0, most, "int") for t, most in _TECH_TYPES),
    _g("retreat_wounded", "micro", 0, 1, "bool"),
    _g("retreat_hp", "micro", 0.1, 0.5),
    _g("rejoin_hp", "micro", 0.5, 0.95),
    _g("combat_every", "micro", 0.1, 0.5),
    _g("think_every", "micro", 0.2, 0.8),
)
GENE: dict[str, Gene] = {gene.name: gene for gene in GENES}
BEHAVIOURS: tuple[str, ...] = tuple(dict.fromkeys(gene.behaviour for gene in GENES))
# The compiled ProProfile reports its fields' types as classes, the source as the strings its annotations are.
_FIELD_KIND = {f.name: f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type)) for f in fields(ProProfile)}


def genes_of(profile: ProProfile) -> Genes:
    """The genes that spell *profile*: what a search starts from when it is seeded with a known brain."""
    genes: Genes = {}
    plan = profile.army_plan
    for gene in GENES:
        if gene.name == "plan.on":
            value = float(plan is not None)
        elif gene.name.startswith("plan."):
            value = float(plan.get(UnitType(gene.name[5:]), 0.0)) if plan is not None else 1.0 / len(_PLAN_TYPES)
        elif gene.name.startswith("tech."):
            value = float(profile.early_tech.count(BuildingType(gene.name[5:])))
        elif gene.name.startswith("open."):
            slot = int(gene.name[5:])
            value = float(_OPENING_CODES.index(profile.opening[slot])) if slot < len(profile.opening) else 0.0
        elif gene.name == "prospect.on":
            value = float(profile.prospect_floor > 0)
        elif gene.name == "prospect_floor":
            value = float(profile.prospect_floor or 16000)
        elif gene.name == "abort.on":
            value = float(profile.abort_ratio > 0.0)
        elif gene.name == "abort_ratio":
            value = profile.abort_ratio or 1.5
        elif gene.name == "defend.on":
            value = float(profile.defend_ratio > 0.0)
        elif gene.name == "defend_ratio":
            value = profile.defend_ratio or 1.5
        elif gene.name == "res.on":
            value = float(profile.research_order is not None)
        elif gene.name.startswith("res."):
            order = profile.research_order
            first = {"res.arts": _FIRST_ARTS, "res.marks": (Upgrade.MARKSMANSHIP,)}.get(gene.name) or _CHAINS[gene.name[4:]][:1]
            # Where the chain stands in the profile's own order, as a priority; the default order's where it has none.
            places = [order.index(u) for u in first if u in order] if order is not None else []
            value = 1.0 - min(places) / 10.0 if places else {"res.blades": 1.0, "res.armor": 0.9, "res.arrows": 0.8, "res.arts": 0.7, "res.marks": 0.6}[gene.name]
        else:
            value = float(getattr(profile, gene.name))
        genes[gene.name] = gene.clip(value)
    return genes


def profile_of(genes: Mapping[str, float], name: str, base: ProProfile = PRO) -> ProProfile:
    """The profile *genes* spell, on top of *base* for every field no gene sets."""
    changes: dict[str, object] = {}
    for gene in GENES:
        if "." in gene.name:
            continue
        value = genes[gene.name]
        kind = _FIELD_KIND[gene.name]
        changes[gene.name] = bool(value) if kind == "bool" else int(value) if kind == "int" else float(value)
    if genes["plan.on"]:
        shares = {t: genes[f"plan.{t.value}"] for t in _PLAN_TYPES}
        total = sum(shares.values())
        # A share under a twentieth is a unit the plan does not field: its producer is not worth building for it.
        plan = {t: s / total for t, s in shares.items() if total > 0 and s / total >= 0.05}
        changes["army_plan"] = plan or None
    else:
        changes["army_plan"] = None
    changes["early_tech"] = tuple(t for t, _most in _TECH_TYPES for _ in range(int(genes[f"tech.{t.value}"])))
    changes["research_order"] = research_order(genes) if genes["res.on"] else None
    opening = [_OPENING_CODES[int(genes[f"open.{k}"])] for k in range(OPENING_SLOTS)]
    changes["opening"] = tuple(step for step in opening if step is not None)
    if not genes["defend.on"]:
        changes["defend_ratio"] = 0.0
    if not genes["abort.on"]:
        changes["abort_ratio"] = 0.0
    if not genes["prospect.on"]:
        changes["prospect_floor"] = 0
    return replace(base, name=name, **changes)  # type: ignore[arg-type]


def random_genes(rng: random.Random) -> Genes:
    return {gene.name: gene.draw(rng) for gene in GENES}


def mutate(genes: Mapping[str, float], rng: random.Random, rate: float = 0.12, scale: float = 0.15) -> Genes:
    """A copy with each gene nudged with probability *rate*, and at least one nudged."""
    out = dict(genes)
    chosen = [gene for gene in GENES if rng.random() < rate] or [rng.choice(GENES)]
    for gene in chosen:
        out[gene.name] = gene.nudge(out[gene.name], rng, scale)
    return out


def crossover(a: Mapping[str, float], b: Mapping[str, float], rng: random.Random) -> Genes:
    """A child that takes each behaviour whole from one parent or the other."""
    source = {behaviour: (a if rng.random() < 0.5 else b) for behaviour in BEHAVIOURS}
    return {gene.name: source[gene.behaviour][gene.name] for gene in GENES}


# -- Individuals and their records ----------------------------------------------------


@dataclass
class Individual:
    name: str
    genes: Genes
    born: int = 0
    parents: tuple[str, ...] = ()
    record: dict[str, list[float]] = field(default_factory=dict)  # opponent -> [score taken, games]
    style: dict[str, list[float]] = field(default_factory=dict)   # style field -> [sum, games it was read in]

    @property
    def games(self) -> int:
        return int(sum(games for _won, games in self.record.values()))

    @property
    def score(self) -> float:
        """The plain share of every game it has played."""
        games = self.games
        return sum(won for won, _games in self.record.values()) / games if games else 0.0

    def add(self, opponent: str, result: MatchResult, seat: int) -> None:
        row = self.record.setdefault(opponent, [0.0, 0.0])
        row[0] += result.score(seat, 1 - seat)
        row[1] += 1.0
        for key, value in result.styles[seat].items():
            if not math.isnan(value):
                cell = self.style.setdefault(key, [0.0, 0.0])
                cell[0] += value
                cell[1] += 1.0
        if result.tallies:
            for unit, count in result.tallies[seat].trained.items():
                cell = self.style.setdefault(f"trained.{unit}", [0.0, 0.0])
                cell[0] += count
            self.style.setdefault("trained.games", [0.0, 0.0])[0] += 1.0

    def mean_style(self, key: str) -> float:
        total, games = self.style.get(key, (0.0, 0.0))
        if key.startswith("trained."):
            games = self.style.get("trained.games", [0.0, 0.0])[0]
        return total / games if games else math.nan

    def to_record(self) -> dict:
        return {"name": self.name, "genes": self.genes, "born": self.born, "parents": list(self.parents),
                "record": self.record, "style": self.style}

    @classmethod
    def from_record(cls, row: Mapping) -> "Individual":
        """A gene added since the record was kept takes the value that spells ``pro``: the behaviour as it was."""
        return cls(name=row["name"], genes=genes_of(PRO) | dict(row["genes"]), born=row["born"], parents=tuple(row["parents"]),
                   record={k: list(v) for k, v in row["record"].items()}, style={k: list(v) for k, v in row["style"].items()})


PRIOR_GAMES = 30.0  # how many games of the population's average a record is mixed with before it is believed


def fitness(individual: Individual, panel: Sequence[str], prior: Mapping[str, float]) -> float:
    """The mean over *panel* of the individual's win rate against each, shrunk towards *prior* (the population's).

    Per opponent, so that a record gathered while the panel was easier does not flatter a veteran; shrunk, so
    that thirty lucky games do not outrank three hundred good ones.
    """
    rates = []
    for opponent in panel:
        won, games = individual.record.get(opponent, (0.0, 0.0))
        rates.append((won + PRIOR_GAMES * prior.get(opponent, 0.5)) / (games + PRIOR_GAMES))
    return statistics.fmean(rates)


# -- Playing ---------------------------------------------------------------------------


Task = tuple[tuple, tuple[tuple[str, Genes], ...]]


def play_task(task: Task) -> MatchResult:
    """One match in a worker: the bred agents it needs travel with it as genes, and are registered on first sight."""
    packed, bred = task
    for name, genes in bred:
        if name not in arena.AGENTS:
            profile = profile_of(genes, name)
            arena.register(name, lambda player, seed, p=profile: ProBrain(player, p))
    return arena.play_spec_tuple(packed)


def specs_for(name: str, race: str | None, opponents: Sequence[str], seeds: Sequence[int], minutes: float,
              layout: str | None = None) -> list[MatchSpec]:
    """*name* against each of *opponents* on each of *seeds*, from both corners; with *race*, *name* plays it and
    the opponent takes each race in turn; with *layout*, every board is of that layout (sizes still cycle)."""
    out = []
    for k, opponent in enumerate(opponents):
        for seed in seeds:
            board = arena.board(seed)
            if layout is not None:
                board["layout"] = layout
            races = (race, RACE_VALUES[(seed + k) % len(RACE_VALUES)]) if race is not None else None
            out.append(MatchSpec(seed=seed, agents=(name, opponent), minutes=minutes, races=races, **board))
            out.append(MatchSpec(seed=seed, agents=(opponent, name), minutes=minutes,
                                 races=(races[1], races[0]) if races is not None else None, **board))
    return out


class Evaluator:
    """A pool of workers kept for a whole run, so that a source edited meanwhile does not reach a run in progress."""

    def __init__(self, workers: int) -> None:
        self.pool = mp.get_context("spawn").Pool(workers) if workers > 1 else None

    def close(self) -> None:
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()

    def map(self, function, tasks: Sequence) -> list:
        """*function* over *tasks*, in their order."""
        if self.pool is None:
            return [function(task) for task in tasks]
        return self.pool.map(function, tasks, chunksize=2)

    def play(self, specs: Sequence[MatchSpec], bred: Mapping[str, Genes]) -> list[MatchResult]:
        usable: dict[tuple, bool] = {}
        tasks: list[Task] = []
        for spec in specs:
            key = (spec.seed, spec.width, spec.height, spec.layout)
            if key not in usable:
                usable[key] = arena.playable(spec)
            if usable[key]:
                packed = tuple(getattr(spec, f) for f in arena.SPEC_FIELDS)
                tasks.append((packed, tuple((a, bred[a]) for a in spec.agents if a in bred)))
        if self.pool is None:
            return [play_task(task) for task in tasks]
        return list(self.pool.imap_unordered(play_task, tasks, chunksize=4))


def judge(evaluator: Evaluator, population: Sequence[Individual], panel: Sequence[str], hall: Mapping[str, Genes],
          race: str | None, seeds: Sequence[int], minutes: float, layout: str | None = None) -> int:
    """Play every individual against the panel on *seeds* and add the games to its record; how many were played."""
    bred = {individual.name: individual.genes for individual in population} | dict(hall)
    by_name = {individual.name: individual for individual in population}
    specs = [spec for individual in population for spec in specs_for(individual.name, race, panel, seeds, minutes, layout)]
    results = evaluator.play(specs, bred)
    for result in results:
        for seat, name in enumerate(result.spec.agents):
            if name in by_name:
                by_name[name].add(result.spec.agents[1 - seat], result, seat)
    return len(results)


# -- Macro: an opening judged on its own --------------------------------------------------

MACRO_CHECKPOINTS: tuple[tuple[float, float], ...] = ((210.0, 1.0), (270.0, 1.0), (360.0, 0.5))  # (seconds, weight)
#: The behaviours an opening is made of.  A macro search breeds these alone; the rest stay as the base has them.
MACRO_BEHAVIOURS: frozenset[str] = frozenset({"economy", "construction", "opening", "tech", "army"})


class _Passive:
    """The opponent of a macro trial: it stands where it started, so nothing but the build is being measured."""

    def think(self, world, rng) -> None:
        return None


def military_worth(world, player: int) -> float:
    """How much fight *player*'s soldiers have in them, as the brain itself compares armies (:func:`strength`):
    linear in the number of like soldiers, and the upgrades they carry are in their blows and their armour."""
    from warband.brains.pro_ai import strength

    return strength(world, [unit for unit in world.player_units(player) if not unit.is_worker])


def macro_task(task: tuple[Genes, str, int]) -> float:
    """One opening played out undisturbed on one board: its army's strength at the checkpoints, weighted and added."""
    from warband.sim import mapgen
    from warband.sim.rules import SIM_DT, Layout, MapTheme

    genes, race, seed = task
    board = arena.board(seed)
    other = RACE_VALUES[seed % len(RACE_VALUES)]
    try:
        world = mapgen.generate(seed=seed, width=board["width"], height=board["height"], players=2, human=None,
                                theme=MapTheme.SUMMER, races=(Race(race), Race(other)), layout=Layout(board["layout"]))
    except ValueError:
        return math.nan  # no fair map from this seed at this size
    # Nothing to attack with and nobody to scout: the opening alone.
    profile = replace(profile_of(genes, "macro"), min_army=10_000, scout=False, raid=False, rush_towers=0)
    brain, rng = ProBrain(0, profile), random.Random(seed * 1000003)
    score, checkpoints = 0.0, list(MACRO_CHECKPOINTS)
    while checkpoints:
        brain.think(world, rng)
        world.step()
        world.take_events()
        if world.time >= checkpoints[0][0]:
            score += checkpoints.pop(0)[1] * military_worth(world, 0)
    return score


def macro_judge(evaluator: "Evaluator", population: Sequence[Genes], race: str, seeds: Sequence[int]) -> list[float]:
    """The mean macro score of each of *population* over *seeds* (boards with no fair map left out)."""
    tasks = [(genes, race, seed) for genes in population for seed in seeds]
    scores = evaluator.map(macro_task, tasks)
    out = []
    for k in range(len(population)):
        mine = [v for v in scores[k * len(seeds):(k + 1) * len(seeds)] if not math.isnan(v)]
        out.append(statistics.fmean(mine) if mine else 0.0)
    return out


def macro_search(evaluator: "Evaluator", race: str, base: Genes, *, generations: int, population: int, seeds: Sequence[int],
                 rng: random.Random, log=print) -> tuple[Genes, float]:
    """Breed the opening behaviours of *base* for military worth at the checkpoints; the best genes and their score.

    The boards are the same every generation: an undisturbed opening is deterministic, so a score is exact and the
    survivors need no second look.  What it is bred on is fifteen boards of every size and layout, not one."""
    genes_in_play = [gene for gene in GENES if gene.behaviour in MACRO_BEHAVIOURS]

    def vary(genes: Genes, rate: float) -> Genes:
        out = dict(genes)
        for gene in [g for g in genes_in_play if rng.random() < rate] or [rng.choice(genes_in_play)]:
            out[gene.name] = gene.nudge(out[gene.name], rng, 0.2)
        return out

    pool = [dict(base)] + [vary(base, 0.3) for _ in range(population - 1)]
    scores = macro_judge(evaluator, pool, race, seeds)
    for generation in range(generations):
        ranked = sorted(zip(scores, range(len(pool))), reverse=True)
        keep = [pool[i] for _s, i in ranked[:population // 4]]
        kept_scores = [s for s, _i in ranked[:population // 4]]
        children = []
        while len(keep) + len(children) < population:
            a, b = rng.choice(keep), rng.choice(keep)
            child = {gene.name: (a if rng.random() < 0.5 else b)[gene.name] for gene in GENES}
            children.append(vary(child, 0.1))
        pool = keep + children
        scores = kept_scores + macro_judge(evaluator, children, race, seeds)
        log(f"macro {race} gen {generation:3d}: best {max(scores):8.0f}  median {statistics.median(scores):8.0f}")
    best = max(range(len(pool)), key=lambda i: scores[i])
    return pool[best], scores[best]


# -- The search ------------------------------------------------------------------------


@dataclass
class Settings:
    race: str | None = None            # the race bred for; None breeds a brain for whatever the seed draws
    layout: str | None = None          # the one layout bred for; None walks all five
    population: int = 32
    elite: int = 8                     # the best, kept and judged again on the next generation's seeds
    immigrants: int = 2                # drawn at random each generation, so the search does not close on itself
    seeds: int = 6                     # boards per opponent per generation; each is played from both corners
    panel: tuple[str, ...] = ("pro-vanguard", "pro-warden", "pro-rush")
    hall_size: int = 2                 # how many of its own champions join the panel
    hall_every: int = 4                # generations between a champion joining the hall
    hall_games: int = 150              # a champion has at least this many games behind it
    minutes: float = arena.DEFAULT_MINUTES
    first_seed: int = 200_000
    seed: int = 0
    start: tuple[str, ...] = ("pro", "pro-vanguard", "pro-warden", "pro-rush", "mass", "boom", "turtle")
    mutation_rate: float = 0.12
    mutation_scale: float = 0.15


@dataclass
class State:
    settings: Settings
    generation: int = 0
    population: list[Individual] = field(default_factory=list)
    hall: list[Individual] = field(default_factory=list)  # champions in the order they entered
    counter: int = 0
    history: list[dict] = field(default_factory=list)

    def to_record(self) -> dict:
        return {"settings": vars(self.settings), "generation": self.generation, "counter": self.counter,
                "population": [i.to_record() for i in self.population], "hall": [i.to_record() for i in self.hall],
                "history": self.history}

    @classmethod
    def from_record(cls, row: Mapping) -> "State":
        settings = Settings(**{k: tuple(v) if isinstance(v, list) else v for k, v in row["settings"].items()})
        return cls(settings=settings, generation=row["generation"], counter=row["counter"],
                   population=[Individual.from_record(i) for i in row["population"]],
                   hall=[Individual.from_record(i) for i in row["hall"]], history=list(row["history"]))


def _known_profile(name: str) -> ProProfile:
    from warband.league.archetypes import BY_NAME

    return PRO_PROFILES[name] if name in PRO_PROFILES else BY_NAME[name]


def _name(state: State, tag: str) -> str:
    state.counter += 1
    return f"{tag}-{state.counter}"


def found(settings: Settings, tag: str, bred: Sequence[Genes] = ()) -> State:
    """The first generation: the known brains and *bred* (genes an earlier search found), mutants of them, and the
    rest drawn at random."""
    rng = random.Random(settings.seed)
    state = State(settings=settings)
    starts = [genes_of(_known_profile(name)) for name in settings.start] + [genes_of(PRO) | dict(genes) for genes in bred]
    for genes in starts:
        state.population.append(Individual(_name(state, tag), genes))
    while len(state.population) < settings.population:
        if starts and len(state.population) < settings.population * 3 // 4:
            genes = mutate(rng.choice(starts), rng, rate=0.25, scale=settings.mutation_scale)
        else:
            genes = random_genes(rng)
        state.population.append(Individual(_name(state, tag), genes))
    return state


def panel_of(state: State) -> list[str]:
    return [*state.settings.panel, *(champion.name for champion in state.hall[-state.settings.hall_size:])]


def step(state: State, evaluator: Evaluator, tag: str, log=print) -> None:
    """One generation: judge everyone on fresh seeds, record it, breed the next."""
    settings = state.settings
    rng = random.Random(settings.seed * 7919 + state.generation)
    panel = panel_of(state)
    hall = {champion.name: champion.genes for champion in state.hall}
    first = settings.first_seed + state.generation * settings.seeds
    seeds = range(first, first + settings.seeds)
    started = time.perf_counter()
    games = judge(evaluator, state.population, panel, hall, settings.race, seeds, settings.minutes, settings.layout)
    prior = {opponent: _population_rate(state.population, opponent) for opponent in panel}
    ranked = sorted(state.population, key=lambda i: -fitness(i, panel, prior))
    best = ranked[0]
    row = {"generation": state.generation, "games": games, "seconds": round(time.perf_counter() - started, 1),
           "panel": panel, "prior": {k: round(v, 3) for k, v in prior.items()},
           "best": best.name, "best_fitness": round(fitness(best, panel, prior), 4), "best_score": round(best.score, 4),
           "best_games": best.games,
           "mean_fitness": round(statistics.fmean(fitness(i, panel, prior) for i in state.population), 4)}
    state.history.append(row)
    log(f"gen {state.generation:3d}: {games} games in {row['seconds']:.0f}s; population {row['mean_fitness']:.3f}; "
        f"best {best.name} {row['best_fitness']:.3f} ({best.score:.3f} over {best.games}) "
        f"vs {', '.join(f'{o} {_rate(best, o):.2f}' for o in panel)}")
    # The hall takes a champion every few generations: the best with enough games behind it that is not in it yet.
    if state.generation and state.generation % settings.hall_every == 0:
        in_hall = {champion.name for champion in state.hall}
        proven = [i for i in ranked if i.games >= settings.hall_games and i.name not in in_hall]
        if proven:
            state.hall.append(Individual.from_record(proven[0].to_record()))
            log(f"         {proven[0].name} enters the hall ({proven[0].score:.3f} over {proven[0].games})")
    elite = ranked[:settings.elite]
    children: list[Individual] = []
    while len(elite) + len(children) < settings.population - settings.immigrants:
        a, b = (_tournament(ranked, rng) for _ in range(2))
        genes = crossover(a.genes, b.genes, rng) if a is not b and rng.random() < 0.7 else dict(a.genes)
        genes = mutate(genes, rng, settings.mutation_rate, settings.mutation_scale)
        children.append(Individual(_name(state, tag), genes, born=state.generation + 1, parents=(a.name, b.name)))
    for _ in range(settings.immigrants):
        source = rng.choice(elite).genes
        children.append(Individual(_name(state, tag), mutate(source, rng, rate=0.4, scale=0.3), born=state.generation + 1))
    state.population = elite + children
    state.generation += 1


def _rate(individual: Individual, opponent: str) -> float:
    won, games = individual.record.get(opponent, (0.0, 0.0))
    return won / games if games else math.nan


def _population_rate(population: Sequence[Individual], opponent: str) -> float:
    won = sum(i.record.get(opponent, (0.0, 0.0))[0] for i in population)
    games = sum(i.record.get(opponent, (0.0, 0.0))[1] for i in population)
    return won / games if games else 0.5


def _tournament(ranked: Sequence[Individual], rng: random.Random, size: int = 3) -> Individual:
    """The best of *size* drawn at random; *ranked* is best first, so the lowest index wins."""
    return ranked[min(rng.randrange(len(ranked)) for _ in range(size))]


def save(state: State, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state.to_record())
    (out / f"gen-{state.generation:03d}.json").write_text(text)
    (out / "latest.json").write_text(text)


def load(out: Path) -> State:
    return State.from_record(json.loads((out / "latest.json").read_text()))
