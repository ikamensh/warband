"""The postures the genetic search bred, a race's own for each race (written by ``tools/evolve.py export``; bred again
rather than edited by hand).  :class:`warband.brains.pro_ai.RaceBrain` plays them: the Grandmaster setting.  How they were
bred and what they measured is in ``docs/ai-ladder.md``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Race, UnitType, Upgrade

BRED: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # macro-human-1: 1366.746 over 0 games of its search
        replace(PRO, name='bred-human-1', workers_per_mine=8, lumber_share=0.265, lumber_floor_panic=15, panic_gold=1217,
                lumber_stock=1099, max_workers=28, supply_slack=6, supply_per_producer=1.642, max_sites=6,
                surplus_gold=1214, lumber_floor=134, gold_per_barracks=2325, soldiers_before_workers=5, clerics=False,
                counter_from=0.174, counter_strength=1.414, army_plan={UnitType.FOOTMAN: 0.36, UnitType.SCOUT: 0.183,
                UnitType.KNIGHT: 0.456}, early_tech=(BuildingType.STABLES, BuildingType.STABLES, BuildingType.STABLES,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.SIEGE,),
                research_first=1, opening=(BuildingType.BARRACKS, BuildingType.BARRACKS, BuildingType.BLACKSMITH,
                BuildingType.BARRACKS,), wood_lead=True, wood_per_hand=372),
    ),
    Race.ORC: (
        # macro-orc-1: 1162.559 over 0 games of its search
        replace(PRO, name='bred-orc-1', workers_per_mine=8, lumber_share=0.338, lumber_floor_panic=168, panic_gold=2475,
                lumber_stock=1884, supply_slack=2, supply_per_producer=2.645, surplus_gold=200, lumber_floor=31,
                barracks_first=True, gold_per_barracks=668, soldiers_before_workers=7, clerics=False, counter_from=0.1,
                counter_strength=1.733, army_plan={UnitType.FOOTMAN: 0.316, UnitType.KNIGHT: 0.107, UnitType.CATAPULT:
                0.132, UnitType.CLERIC: 0.445}, early_tech=(BuildingType.BARRACKS, BuildingType.BARRACKS,
                BuildingType.BARRACKS, BuildingType.STABLES,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1,
                Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING,
                Upgrade.LONGBOWS, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.SIEGE,), research_first=1, wood_from=5,
                opening=(BuildingType.BARRACKS, BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.WORKSHOP,
                BuildingType.BARRACKS, BuildingType.BARRACKS,), wood_release=1511),
    ),
    Race.ELF: (
        # macro-elf-1: 1237.488 over 0 games of its search
        replace(PRO, name='bred-elf-1', lumber_share=0.188, lumber_floor_panic=800, panic_gold=2304, lumber_stock=2391,
                max_workers=40, supply_slack=3, max_sites=6, surplus_gold=200, lumber_floor=81, barracks_per_hall=4,
                gold_per_barracks=1711, soldiers_before_workers=8, siege=False, clerics=False, counter_from=0.314,
                counter_strength=0.5, army_plan={UnitType.FOOTMAN: 0.474, UnitType.CATAPULT: 0.193, UnitType.CLERIC: 0.304},
                early_tech=(BuildingType.WORKSHOP,), wood_crew=1, wood_from=5, opening=(BuildingType.BARRACKS,
                BuildingType.BARRACKS, BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.BARRACKS,
                BuildingType.BARRACKS,), wood_per_hand=283, wood_release=1418),
    ),
    Race.DWARF: (
        # macro-dwarf-1: 1296.961 over 0 games of its search
        replace(PRO, name='bred-dwarf-1', workers_per_mine=8, lumber_share=0.358, lumber_floor_panic=10, panic_gold=1000,
                lumber_stock=2567, max_workers=30, supply_slack=3, supply_per_producer=2.702, max_sites=4, surplus_gold=915,
                lumber_floor=175, barracks_per_hall=1, barracks_first=True, gold_per_barracks=600, max_producers=9,
                soldiers_before_workers=7, siege=False, counter_from=0.337, counter_strength=2.152,
                army_plan={UnitType.FOOTMAN: 0.388, UnitType.KNIGHT: 0.226, UnitType.CATAPULT: 0.249, UnitType.CLERIC:
                0.137}, early_tech=(BuildingType.BARRACKS, BuildingType.BARRACKS, BuildingType.BLACKSMITH,
                BuildingType.STABLES,), research_first=1, wood_crew=1, opening=(BuildingType.BARRACKS,
                BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.BARRACKS, BuildingType.BLACKSMITH,),
                wood_lead=True, wood_per_hand=242, wood_release=2072),
    ),
}
