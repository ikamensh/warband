"""The contenders for the rung above Grandmaster play under their names and seed the search."""

import random

from warband.brains.contenders import BY_NAME, CONTENDERS
from warband.brains.policy import FEATURE_NAMES, LEARNED, STANCES, PolicyBrain
from warband.league import evolve
from warband.league.arena import AGENTS, make_agent
from warband.sim import mapgen
from warband.sim.model import World


def test_the_policy_brain_with_zero_weights_plays_as_bred_and_reads_its_features():
    """Zero weights preserve the bred opening through real stance decisions and world orders."""
    brain = make_agent("policy", 0, seed=1)
    baseline = make_agent("apex3", 0, seed=1)
    assert isinstance(brain, PolicyBrain)
    assert len(LEARNED) == len(STANCES) and all(len(row) == len(FEATURE_NAMES) for row in LEARNED)
    world = mapgen.generate(seed=7, human=None)
    reference = World.from_dict(world.to_dict())
    rng, reference_rng = random.Random(1), random.Random(1)
    for _ in range(120):
        brain.think(world, rng)
        baseline.think(reference, reference_rng)
        world.step()
        reference.step()
    assert brain.stance == 0
    assert world.to_dict() == reference.to_dict()


def test_every_contender_is_a_registered_agent_with_a_unique_name():
    names = [p.name for p in CONTENDERS]
    assert len(names) == len(set(names)) == len(BY_NAME)
    for name in names:
        assert name in AGENTS
        assert make_agent(name, 0, seed=1).profile.name == name


def test_the_search_can_seed_itself_from_contenders_and_bred_postures():
    for name in ("apex-rush", "apex-scout", "bred-elf-1", "bred-human-klondike-1"):
        genes = evolve.genes_of(evolve._known_profile(name))
        assert evolve.profile_of(genes, name).name == name


def test_champions_is_a_difficulty_that_draws_from_the_pooled_rosters():
    from warband.brains.ai import DIFFICULTY_ELO, DIFFICULTY_NOTES, make_brain
    from warband.brains.champions import CHAMPIONS
    from warband.brains.pro_ai import RaceBrain
    from warband.sim.rules import Difficulty, Race

    assert set(DIFFICULTY_ELO) == set(Difficulty) and set(DIFFICULTY_NOTES) == set(Difficulty)
    assert DIFFICULTY_ELO[Difficulty.CHAMPIONS] > DIFFICULTY_ELO[Difficulty.GRANDMASTER]
    assert all(len(CHAMPIONS[race]) == 6 for race in Race)
    assert isinstance(make_brain(0, Difficulty.CHAMPIONS, seed=7), RaceBrain)


def test_the_apex_rosters_have_postures_for_every_race_and_play_as_agents():
    from warband.brains.apex import APEX
    from warband.brains.apex2 import APEX2
    from warband.brains.apex3 import APEX3
    from warband.brains.apex4 import APEX4
    from warband.brains.apex5 import APEX5
    from warband.brains.pro_ai import RaceBrain
    from warband.sim.rules import Race

    for roster, agent in ((APEX, "apex"), (APEX2, "apex2"), (APEX3, "apex3"), (APEX4, "apex4"), (APEX5, "apex5")):
        assert set(roster) == set(Race)
        assert all(len(postures) >= 2 for postures in roster.values())
        names = [p.name for postures in roster.values() for p in postures]
        assert len(names) == len(set(names))
        assert isinstance(make_agent(agent, 0, seed=1), RaceBrain)
