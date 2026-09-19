"""The postures the balance league is played between.

Each archetype is a :class:`~warband.brains.pro_ai.ProProfile` that commits to one
way of playing — knights, siege, a rush, towers — so that a round-robin
between them prices the ingredients of the game: a posture that beats every
other names something too cheap or a counter that is missing, and one that
loses to every other names something not worth its price.  They are meant to
be *distinct*, not strong; the shipped Master (``pro``) plays among them as
the baseline that follows its race's own plan.

    uv run python tools/balance_report.py --seeds 8

Every knob used here is measured by ``tools/arena.py`` like any other; the
archetypes are registered as agents under their names.
"""

from __future__ import annotations

from dataclasses import replace

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, UnitType

F, A, S, K, C, L = (UnitType.FOOTMAN, UnitType.ARCHER, UnitType.SCOUT, UnitType.KNIGHT, UnitType.CATAPULT,
                    UnitType.CLERIC)

ARCHETYPES: tuple[ProProfile, ...] = (
    PRO,
    # Timing: when the army walks out, and how big it is when it does.
    replace(PRO, name="rush", min_army=3, attack_ratio=0.6, symmetry_prior=0.2, regroup_seconds=20.0,
            workers_per_mine=8, expand=False, soldiers_before_workers=8, barracks_per_hall=4,
            army_plan={F: 0.7, A: 0.3}, siege=False, clerics=False),
    replace(PRO, name="boom", expand_early=True, workers_per_mine=12, max_workers=40, max_halls=4,
            min_army=12, attack_ratio=1.2),
    replace(PRO, name="mass", barracks_per_hall=5, min_army=15, attack_ratio=1.0, regroup_seconds=60.0),
    replace(PRO, name="turtle", tower_count=5, min_army=12, attack_ratio=1.4, symmetry_prior=1.0, guards=3),
    # Composition: one branch of the tree, held to strictly, with enough producers of it to field the plan.
    replace(PRO, name="footmen", army_plan={F: 1.0}, strict_plan=True, early_tech=(BuildingType.BLACKSMITH,)),
    replace(PRO, name="archers", army_plan={F: 0.2, A: 0.8}, strict_plan=True, counter_from=1.1),
    replace(PRO, name="knights", army_plan={F: 0.25, S: 0.1, K: 0.65}, strict_plan=True, barracks_per_hall=1,
            early_tech=(BuildingType.STABLES,) * 3),
    replace(PRO, name="raiders", army_plan={F: 0.3, A: 0.2, S: 0.5}, strict_plan=True, raiders=4, scout_from=30.0,
            early_tech=(BuildingType.STABLES,) * 2),
    # Siege dies at six minutes if it walks out at eight: it holds behind towers until the stones are ready.
    replace(PRO, name="siege", army_plan={F: 0.4, A: 0.25, C: 0.35}, strict_plan=True, min_army=12, attack_ratio=1.2,
            tower_count=3, early_tech=(BuildingType.BLACKSMITH, BuildingType.WORKSHOP, BuildingType.WORKSHOP)),
    replace(PRO, name="clerics", army_plan={F: 0.45, A: 0.3, L: 0.25}, strict_plan=True,
            early_tech=(BuildingType.CHURCH,) * 2),
    # Upgrades: the same brain that never buys one, to price the research path.
    replace(PRO, name="noresearch", research=False),
)

NAMES: tuple[str, ...] = tuple(p.name for p in ARCHETYPES)
BY_NAME: dict[str, ProProfile] = {p.name: p for p in ARCHETYPES}
