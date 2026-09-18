"""The postures the balance league is played between.

An archetype is a ProProfile that plays one way on purpose — knights, siege,
a rush — so that the payoff matrix between them says which ingredients of
the game are worth their price.  These tests pin that each knob really
changes what the brain buys, which is the whole point of having it.
"""

from __future__ import annotations

from dataclasses import replace

from warband import arena
from warband.arena import MatchSpec, play
from warband.pro_ai import PRO
from warband.rules import UnitType


def _play(name: str, profile, seed: int = 7, minutes: float = 6, opponent: str = "pro"):
    arena.register_profiles([(name, profile)])
    return play(MatchSpec(seed=seed, agents=(name, opponent), minutes=minutes)).tallies[0]


def test_an_army_plan_decides_what_the_barracks_trains():
    """A plan of archers only turns out archers and no footmen, whatever the race would have done."""
    tally = _play("test-archers-only", replace(PRO, name="test-archers-only", army_plan={UnitType.ARCHER: 1.0}))
    assert tally.trained["archer"] >= 3
    assert tally.trained["footman"] == 0


def test_early_tech_goes_up_before_the_bank_overflows():
    """A knights posture lays its stables inside six minutes; the plain brain waits for saturation."""
    from warband.rules import BuildingType

    tally = _play("test-stables-early", replace(PRO, name="test-stables-early", early_tech=(BuildingType.STABLES,)))
    assert tally.started["stables"] >= 1


def test_research_can_be_switched_off_to_price_the_upgrades():
    """With a smith standing, the brain researches; with research off it never does, smith or not."""
    from warband.rules import BuildingType

    smith = replace(PRO, name="test-smith", early_tech=(BuildingType.BLACKSMITH,))
    assert _play("test-smith", smith, minutes=8).researched
    silent = replace(smith, name="test-smith-silent", research=False)
    assert not _play("test-smith-silent", silent, minutes=8).researched


def test_early_tech_names_how_many_and_a_strict_plan_stops_the_barracks():
    """Two stables in the list means two stables; a strict plan of knights trains no footman past its share."""
    from warband.rules import BuildingType

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
