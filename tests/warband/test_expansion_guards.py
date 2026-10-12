"""Whole fights establish that expansion guards are affordable early opportunities.

Slow because each case plays a real magic-free fight to completion, rather
than inferring accessibility from stat tables.
"""

import pytest

from tools.creep_report import encounter
from warband.sim.rules import Race


@pytest.mark.slow
@pytest.mark.parametrize("identity", ["wolf_outpost", "spider_hollow"])
@pytest.mark.parametrize("race", list(Race))
def test_every_race_can_profitably_clear_an_expansion_with_an_early_army(identity, race):
    """Eight common troops need no research or healer to unlock a weak guarded expansion."""
    result = encounter(42, race.value, identity, bracket="early")
    assert result.cleared
    assert result.gold >= result.loss_gold
    assert result.lumber >= result.loss_lumber
