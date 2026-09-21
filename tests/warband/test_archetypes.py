"""The postures the balance league is played between.

An archetype is a ProProfile that plays one way on purpose — knights, siege,
a rush — so that the payoff matrix between them says which ingredients of
the game are worth their price.  These tests pin that each knob really
changes what the brain buys, which is the whole point of having it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from warband.league import arena
from warband.league.arena import MatchSpec, play
from warband.brains.pro_ai import PRO
from warband.sim.rules import UnitType


def _play(name: str, profile, seed: int = 7, minutes: float = 6, opponent: str = "pro"):
    arena.register_profiles([(name, profile)])
    return play(MatchSpec(seed=seed, agents=(name, opponent), minutes=minutes)).tallies[0]


@pytest.mark.slow
def test_an_army_plan_decides_what_the_barracks_trains():
    """A plan of archers only turns out archers and no footmen, whatever the race would have done.

    A plan shows only once the barracks turn out soldiers, minutes into a match: the slow tier."""
    tally = _play("test-archers-only", replace(PRO, name="test-archers-only", army_plan={UnitType.ARCHER: 1.0}))
    assert tally.trained["archer"] >= 3
    assert tally.trained["footman"] == 0


@pytest.mark.slow
def test_early_tech_goes_up_before_the_bank_overflows():
    """A knights posture lays its stables inside six minutes; the plain brain waits for saturation.

    Six minutes of play: the slow tier."""
    from warband.sim.rules import BuildingType

    tally = _play("test-stables-early", replace(PRO, name="test-stables-early", early_tech=(BuildingType.STABLES,)))
    assert tally.started["stables"] >= 1


@pytest.mark.slow
def test_a_brain_raises_the_keep_to_reach_the_tier_behind_it():
    """A research order that names a second tier but not the Keep in front of it still reaches that tier: every
    posture in bred.py is such an order, bred before the gate existed and never edited by hand, so a brain that
    stopped at the gate would silently lose the whole upper half of the tree.

    Eight minutes of play, long enough to bank the gate and the tier under it: the slow tier."""
    from warband.sim.rules import BuildingType, Upgrade

    profile = replace(PRO, name="test-keep", early_tech=(BuildingType.BLACKSMITH,),
                      research_order=(Upgrade.BLADES_2,))  # the tier alone: the Keep and Blades I are the rules' business
    tally = _play("test-keep", profile, minutes=8)
    # Neither is in the order; each is bought only because Tempered Blades cannot be had without it.
    assert tally.researched["keep"] == 1 and tally.researched["blades_1"] == 1


@pytest.mark.slow
def test_research_can_be_switched_off_to_price_the_upgrades():
    """With a smith standing, the brain researches; with research off it never does, smith or not.

    Two eight-minute matches: the slow tier."""
    from warband.sim.rules import BuildingType

    smith = replace(PRO, name="test-smith", early_tech=(BuildingType.BLACKSMITH,))
    assert _play("test-smith", smith, minutes=8).researched
    silent = replace(smith, name="test-smith-silent", research=False)
    assert not _play("test-smith-silent", silent, minutes=8).researched


@pytest.mark.slow
def test_early_tech_names_how_many_and_a_strict_plan_stops_the_barracks():
    """Two stables in the list means two stables; a strict plan of knights trains no footman past its share.

    A nine-minute match: the slow tier."""
    from warband.sim.rules import BuildingType

    # Against Easy, so the posture lives long enough to field its plan: against Master it can be
    # dead at five minutes, and then the count says who won rather than what the knobs did.
    tally = _play("test-two-stables", replace(PRO, name="test-two-stables", barracks_per_hall=1, strict_plan=True,
                                              early_tech=(BuildingType.STABLES, BuildingType.STABLES),
                                              army_plan={UnitType.FOOTMAN: 0.2, UnitType.KNIGHT: 0.8}),
                  minutes=9, opponent="easy")
    assert tally.started["stables"] >= 2
    soldiers = tally.trained["footman"] + tally.trained["knight"] + tally.trained["scout"]
    assert tally.trained["knight"] >= 4
    assert tally.trained["footman"] <= 0.35 * soldiers + 2, dict(tally.trained)
