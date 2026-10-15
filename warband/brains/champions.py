"""The Champions group: the strongest bred rosters pooled, one posture drawn per game.

A difficulty above Grandmaster made of *several* similarly strong brains
rather than one: per race, the two postures each of the apex3, apex4 and
apex5 rosters (measured 1509–1552 as rosters; docs/ai-ladder.md, "Reading a
match").  :class:`warband.brains.pro_ai.RaceBrain` draws among them by the
map seed, so rematches at this setting are not the same opponent twice —
which champion you get is not known until its opening shows.
"""

from __future__ import annotations

from typing import Final

from warband.brains.apex3 import APEX3
from warband.brains.apex4 import APEX4
from warband.brains.apex5 import APEX5
from warband.brains.pro_profiles import ProProfile
from warband.sim.rules import Layout, Race

CHAMPIONS: Final[dict[Race, tuple[ProProfile, ...]]] = {
    race: (*APEX5[race], *APEX4[race], *APEX3[race]) for race in Race
}
CHAMPIONS_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {}
