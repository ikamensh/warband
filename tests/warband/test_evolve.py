"""The genetic search breeds what the ladder can play: whatever its operators make is a profile a brain accepts, the
brains it starts from are spelled exactly by their genes, and a generation leaves a record a run can carry on from.

Properties of the operators rather than recorded numbers, so they survive new genes and new behaviours.
"""

from __future__ import annotations

import random

import pytest

from warband.brains.pro_ai import PRO_PROFILES, ProBrain
from warband.league import evolve
from warband.sim import mapgen
from warband.sim.rules import Race


@pytest.mark.parametrize("name", ["pro", "pro-vanguard", "pro-warden", "pro-rush"])
def test_a_shipped_posture_is_spelled_exactly_by_its_genes(name: str) -> None:
    """A search seeded with Master's postures starts from Master, not from something near it."""
    profile = PRO_PROFILES[name]
    assert evolve.profile_of(evolve.genes_of(profile), name) == profile


def test_whatever_the_operators_make_stays_in_range_and_is_a_profile_a_brain_plays() -> None:
    """Random genes, mutants and children keep every gene inside its range, and the profile they spell runs a pass."""
    rng = random.Random(5)
    world = mapgen.generate(seed=3, players=2, human=None, races=(Race.ORC, Race.ELF))
    pool = [evolve.random_genes(rng) for _ in range(6)]
    for _ in range(40):
        a, b = rng.sample(pool, 2)
        child = evolve.mutate(evolve.crossover(a, b, rng), rng, rate=0.3, scale=0.5)
        assert set(child) == set(evolve.GENE)
        for name, value in child.items():
            gene = evolve.GENE[name]
            assert gene.low <= value <= gene.high and (gene.kind == "float" or value == int(value)), name
        pool[rng.randrange(len(pool))] = child
    for k, genes in enumerate(pool):
        ProBrain(0, evolve.profile_of(genes, f"bred-{k}")).think(world, rng)


def test_a_child_takes_each_behaviour_whole_from_one_parent() -> None:
    """Crossover moves a behaviour as one piece, so an opening travels with its numbers."""
    rng = random.Random(2)
    a, b = evolve.random_genes(rng), evolve.random_genes(rng)
    child = evolve.crossover(a, b, rng)
    for behaviour in evolve.BEHAVIOURS:
        mine = {gene.name: child[gene.name] for gene in evolve.GENES if gene.behaviour == behaviour}
        assert mine in ({name: a[name] for name in mine}, {name: b[name] for name in mine}), behaviour


def test_fitness_trusts_a_long_record_over_a_lucky_short_one() -> None:
    """Thirty games at 70% do not outrank three hundred at 65%: the record is shrunk towards the population's."""
    lucky = evolve.Individual("lucky", {}, record={"x": [21.0, 30.0]})
    proven = evolve.Individual("proven", {}, record={"x": [195.0, 300.0]})
    prior = {"x": 0.5}
    assert evolve.fitness(proven, ["x"], prior) > evolve.fitness(lucky, ["x"], prior)


@pytest.mark.slow
def test_a_generation_is_judged_recorded_and_carried_on(tmp_path) -> None:
    """One small generation against one opponent, saved and loaded again. It plays eight two-minute matches, several
    seconds interpreted: the slow tier."""
    settings = evolve.Settings(race="orc", population=4, elite=2, immigrants=1, seeds=1, panel=("pro-hard",), minutes=2.0,
                               start=("pro", "pro-vanguard"))
    state = evolve.found(settings, "test")
    evaluator = evolve.Evaluator(workers=1)
    try:
        evolve.step(state, evaluator, "test", log=lambda text: None)
    finally:
        evaluator.close()
    assert state.generation == 1 and len(state.population) == 4
    assert state.history[0]["games"] == 8, "four individuals, one board, both corners"
    kept = [i for i in state.population if i.games]
    assert len(kept) == 2 and all(i.games == 2 and set(i.record) == {"pro-hard"} for i in kept), "the elite keep their records"
    evolve.save(state, tmp_path)
    back = evolve.load(tmp_path)
    assert back.to_record() == state.to_record()
