"""The contenders for the rung above Grandmaster play under their names and seed the search."""


def test_the_policy_brain_with_zero_weights_plays_as_bred_and_reads_its_features():
    from warband.brains.policy import FEATURE_NAMES, LEARNED, STANCES, PolicyBrain

    assert "policy" in AGENTS
    brain = make_agent("policy", 0, seed=1)
    assert isinstance(brain, PolicyBrain)
    assert len(LEARNED) == len(STANCES) and all(len(row) == len(FEATURE_NAMES) for row in LEARNED)

from warband.brains.contenders import BY_NAME, CONTENDERS
from warband.league import evolve
from warband.league.arena import AGENTS, make_agent


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


def test_the_apex_rosters_have_postures_for_every_race_and_play_as_agents():
    from warband.brains.apex import APEX
    from warband.brains.apex2 import APEX2
    from warband.brains.apex3 import APEX3
    from warband.brains.apex4 import APEX4
    from warband.brains.pro_ai import RaceBrain
    from warband.sim.rules import Race

    for roster, agent in ((APEX, "apex"), (APEX2, "apex2"), (APEX3, "apex3"), (APEX4, "apex4")):
        assert set(roster) == set(Race)
        assert all(len(postures) >= 2 for postures in roster.values())
        names = [p.name for postures in roster.values() for p in postures]
        assert len(names) == len(set(names))
        assert isinstance(make_agent(agent, 0, seed=1), RaceBrain)
