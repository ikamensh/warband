"""Contenders for the rung above Grandmaster, and the diverse bench behind them.

Each profile here answers a diagnosed Grandmaster loss (the match stories of
:mod:`warband.league.narrate`, ``tools/replay_report.py compare``): on fresh
seeds Grandmaster took 62% from Medium and 62% from Master, and in the losses
it attacked at a median 262 s (against Medium) or 853 s (against Master),
stayed on one hall while Medium held three, and was out-mined roughly two to
one in every game that ran long.  The contenders therefore keep the bred
behaviours Master lacks (reading the fight at the target, prospecting) and
vary the rest along the axes the losses name — tempo, expansion, early
defence, siege — so a ladder over them attributes whatever strength appears
instead of asserting it.  They are registered as arena agents under their
names; none is shipped as a difficulty until a confirming ladder seats it
(``docs/ai-ladder.md``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_profiles import PRO_VANGUARD, PRO_WARDEN, ProProfile
from warband.sim.rules import BuildingType

# What every contender keeps from the bred postures and Master has not got:
# turn back from a fight that outweighs the push where it stands, and send a
# peasant looking for gold while the worked mines run low.
_BASE: Final = replace(PRO_VANGUARD, abort_ratio=1.5, prospect_floor=24000)

#: Tempo: out at six on modest terms, back quickly, soldiers fed first.
APEX_RUSH: Final = replace(_BASE, name="apex-rush", min_army=6, attack_ratio=0.7, symmetry_prior=0.25,
                           soldiers_before_workers=8, regroup_seconds=30.0, expand=False)
#: Expansion: a second mine before production saturates, hands to work it, and the army to hold it.
APEX_BOOM: Final = replace(_BASE, name="apex-boom", workers_per_mine=13, max_workers=40, max_halls=4,
                           expand_early=True, mine_floor=3000, min_army=8, attack_ratio=0.9,
                           barracks_per_hall=3, vault_from=420.0)
#: Early defence held into expansion: two towers up front for the 170 s wave, then out at eight.
APEX_WALL: Final = replace(PRO_WARDEN, name="apex-wall", abort_ratio=1.5, prospect_floor=24000,
                           towers_early=2, tower_count=3, attack_ratio=0.9, max_halls=3,
                           workers_per_mine=12, max_workers=36, vault_from=420.0)
#: Siege for the games that run long: the workshop after the smith, stones behind the line.
APEX_SIEGE: Final = replace(APEX_BOOM, name="apex-siege", siege_share=0.12,
                            early_tech=(BuildingType.BLACKSMITH, BuildingType.WORKSHOP), min_army=10)
#: Everything at once, moderated: towers for the wave, expansion for the long game, siege to finish.
APEX_ALL: Final = replace(APEX_BOOM, name="apex-all", towers_early=1, tower_count=3, siege_share=0.1,
                          early_tech=(BuildingType.BLACKSMITH, BuildingType.WORKSHOP),
                          counter_from=0.2, counter_strength=2.0)
#: The rush that also scales: the screen's winner given the second mine its failed kills were missing.
APEX_RUSH2: Final = replace(APEX_RUSH, name="apex-rush2", expand=True, max_halls=3, workers_per_mine=12,
                            max_workers=36, mine_floor=6000)
#: The rush behind a tower, answering shooters the Warden's way.
APEX_RUSH3: Final = replace(APEX_RUSH, name="apex-rush3", towers_early=1, counter_from=0.2,
                            counter_strength=2.0)
#: The rush with eyes: a flying scout from 40 s, its sightings trusted longer, attacks on better terms.
APEX_SCOUT: Final = replace(APEX_RUSH2, name="apex-scout", scout=True, scout_from=40.0,
                            stale_seconds=40.0, attack_ratio=0.8)

#: Every new reading behaviour at once, for the narrator to count how often any of them fires.
APEX_EYE: Final = replace(APEX_SCOUT, name="apex-eye", soft_target=True, punish=True, siege_answer=3,
                          base_trade=True, intercept=True)

CONTENDERS: Final[tuple[ProProfile, ...]] = (APEX_RUSH, APEX_BOOM, APEX_WALL, APEX_SIEGE, APEX_ALL,
                                             APEX_RUSH2, APEX_RUSH3, APEX_SCOUT, APEX_EYE)
BY_NAME: Final[dict[str, ProProfile]] = {p.name: p for p in CONTENDERS}
