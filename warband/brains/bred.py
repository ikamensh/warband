"""The postures the genetic search bred, a race's own for each race (written by ``tools/evolve.py export``; bred again
rather than edited by hand).  :class:`warband.brains.pro_ai.RaceBrain` plays them: the Grandmaster setting.  How they were
bred and what they measured is in ``docs/ai-ladder.md``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

BRED: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # human-1-best1: 0.831 over 512 games of its search
        replace(PRO, name='bred-human-1', combat_every=0.122, workers_per_mine=9, lumber_share=0.362, panic_gold=2104,
                lumber_stock=2125, max_sites=7, lumber_floor=188, mine_floor=2553, barracks_per_hall=6,
                gold_per_barracks=1714, attack_ratio=1.0, regroup_seconds=75.254, min_army=10, raiders=0,
                ignore_raid_ratio=0.319, scout=False, scout_from=39.19, expand_early=True, clerics=False,
                counter_from=0.239, army_plan={UnitType.FOOTMAN: 0.167, UnitType.ARCHER: 0.167, UnitType.SCOUT: 0.167,
                UnitType.KNIGHT: 0.228, UnitType.CATAPULT: 0.167, UnitType.CLERIC: 0.106},
                early_tech=(BuildingType.WORKSHOP,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=84.511, wood_from=7, opening_hold=True,
                abort_ratio=1.5, wood_per_hand=125),
        # human-2-best1: 0.773 over 440 games of its search
        replace(PRO, name='bred-human-2', think_every=0.348, combat_every=0.198, workers_per_mine=9, lumber_share=0.362,
                panic_gold=2104, lumber_stock=2125, max_workers=31, supply_slack=3, supply_per_producer=1.754,
                surplus_gold=920, mine_floor=2000, barracks_first=True, max_producers=11, attack_ratio=1.0,
                regroup_seconds=75.254, min_army=13, soldiers_before_workers=5, raid=False, raiders=0,
                ignore_raid_ratio=0.319, scout=False, scout_from=39.19, symmetry_prior=0.593, expand_early=True,
                clerics=False, counter_from=0.239, army_plan={UnitType.FOOTMAN: 0.173, UnitType.ARCHER: 0.173,
                UnitType.SCOUT: 0.173, UnitType.KNIGHT: 0.238, UnitType.CATAPULT: 0.133, UnitType.CLERIC: 0.11},
                early_tech=(BuildingType.BLACKSMITH, BuildingType.WORKSHOP,), research_order=(Upgrade.BLADES_1,
                Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=84.511, wood_from=7,
                opening_hold=True, prospect_floor=24583, abort_ratio=1.5, wood_per_hand=125),
    ),
    Race.ORC: (
        # orc-2-best1: 0.840 over 200 games of its search
        replace(PRO, name='bred-orc-1', think_every=0.479, combat_every=0.179, workers_per_mine=12, lumber_share=0.244,
                lumber_stock=2593, max_workers=33, supply_slack=5, supply_per_producer=2.682, max_sites=4,
                surplus_gold=1408, lumber_floor=114, max_halls=4, mine_floor=2553, barracks_first=True,
                gold_per_barracks=1702, max_producers=11, attack_ratio=0.652, min_army=12, soldiers_before_workers=3,
                tower_count=3, retreat_hp=0.222, rejoin_hp=0.95, raid=False, ignore_raid_ratio=0.363, scout=False,
                symmetry_prior=0.188, clerics=False, counter_strength=0.98, army_plan={UnitType.FOOTMAN: 0.176,
                UnitType.ARCHER: 0.176, UnitType.KNIGHT: 0.176, UnitType.CATAPULT: 0.176, UnitType.CLERIC: 0.277},
                save_for_wanted=False, early_tech=(BuildingType.STABLES,), research_order=(Upgrade.BLADES_1, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.ARMOR_1, Upgrade.MARKSMANSHIP,
                Upgrade.ARROWS_1, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=264.764, push_by=577.527,
                opening=(BuildingType.BARRACKS, BuildingType.WORKSHOP, BuildingType.TOWN_HALL, BuildingType.STABLES,),
                prospect_floor=24000, abort_ratio=1.5, wood_per_hand=373),
        # orc-2-best2: 0.829 over 280 games of its search
        replace(PRO, name='bred-orc-2', think_every=0.479, workers_per_mine=12, lumber_share=0.244, lumber_stock=2593,
                max_workers=33, supply_slack=6, supply_per_producer=2.682, max_sites=4, surplus_gold=1043, lumber_floor=114,
                max_halls=4, mine_floor=2553, barracks_per_hall=4, barracks_first=True, gold_per_barracks=1952,
                max_producers=12, attack_ratio=1.2, min_army=11, soldiers_before_workers=3, retreat_hp=0.222,
                rejoin_hp=0.661, scout=False, symmetry_prior=0.188, expand_early=True, siege=False, clerics=False,
                counter_from=0.463, counter_strength=0.98, army_plan={UnitType.FOOTMAN: 0.214, UnitType.ARCHER: 0.214,
                UnitType.KNIGHT: 0.214, UnitType.CLERIC: 0.336}, save_for_wanted=False, early_tech=(BuildingType.STABLES,),
                research_order=(Upgrade.BLADES_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.ARROWS_1, Upgrade.ARMOR_1, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARROWS_2,
                Upgrade.ARMOR_2, Upgrade.SIEGE,), push_upgrades=1, push_after=178.069, push_by=504.097, wood_from=7,
                opening=(BuildingType.BARRACKS, BuildingType.WORKSHOP, BuildingType.TOWN_HALL, BuildingType.STABLES,),
                defend_ratio=1.328, prospect_floor=29267, abort_ratio=1.5, wood_lead=True, wood_per_hand=267),
    ),
    Race.ELF: (
        # elf-2-best1: 0.824 over 1630 games of its search
        replace(PRO, name='bred-elf-1', think_every=0.387, combat_every=0.215, workers_per_mine=12, lumber_share=0.228,
                lumber_stock=2593, supply_slack=2, max_sites=7, surplus_gold=307, lumber_floor=239, max_halls=2,
                mine_floor=9646, barracks_per_hall=6, towers_early=1, gold_per_barracks=600, max_producers=11,
                attack_ratio=0.774, retreat_ratio=0.457, regroup_seconds=58.213, min_army=17, soldiers_before_workers=3,
                retreat_wounded=False, retreat_hp=0.116, rejoin_hp=0.69, raid=False, raiders=6, reinforce_group=2,
                scout=False, scout_from=41.011, symmetry_prior=0.276, clerics=False, counter_from=0.493,
                counter_strength=0.609, army_plan={UnitType.FOOTMAN: 0.162, UnitType.KNIGHT: 0.264, UnitType.CATAPULT:
                0.275, UnitType.CLERIC: 0.3}, push_upgrades=1, push_after=133.275, push_by=478.686, wood_crew=1,
                wood_from=9, opening=(BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.BLACKSMITH,),
                prospect_floor=24000, abort_ratio=1.5, wood_per_hand=409, wood_release=400),
        # elf-2-best2: 0.779 over 280 games of its search
        replace(PRO, name='bred-elf-2', think_every=0.387, combat_every=0.215, workers_per_mine=11, lumber_share=0.228,
                lumber_floor_panic=256, lumber_stock=1632, supply_slack=3, max_sites=7, surplus_gold=307, lumber_floor=239,
                max_halls=2, mine_floor=9646, barracks_per_hall=6, towers_early=1, gold_per_barracks=600, max_producers=11,
                attack_ratio=0.774, retreat_ratio=0.457, regroup_seconds=58.213, min_army=17, soldiers_before_workers=3,
                retreat_wounded=False, retreat_hp=0.116, rejoin_hp=0.69, raid=False, raiders=6, reinforce_group=2,
                scout=False, scout_from=41.011, stale_seconds=35.022, symmetry_prior=0.276, clerics=False,
                counter_from=0.493, counter_strength=0.609, army_plan={UnitType.FOOTMAN: 0.162, UnitType.KNIGHT: 0.264,
                UnitType.CATAPULT: 0.275, UnitType.CLERIC: 0.3}, push_upgrades=1, push_after=133.275, push_by=478.686,
                wood_crew=1, wood_from=9, opening=(BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.BLACKSMITH,),
                prospect_floor=16000, abort_ratio=1.5, wood_per_hand=409, wood_release=400),
    ),
    Race.DWARF: (
        # dwarf-2-best2: 0.819 over 670 games of its search
        replace(PRO, name='bred-dwarf-1', think_every=0.279, combat_every=0.1, workers_per_mine=11, lumber_share=0.156,
                panic_gold=3000, lumber_stock=2593, supply_slack=2, max_sites=7, surplus_gold=307, lumber_floor=239,
                max_halls=2, mine_floor=9646, barracks_per_hall=6, towers_early=3, gold_per_barracks=600,
                attack_ratio=0.774, retreat_ratio=0.457, regroup_seconds=50.784, min_army=19, soldiers_before_workers=2,
                tower_count=3, retreat_wounded=False, retreat_hp=0.153, raiders=6, reinforce_group=2, scout=False,
                scout_from=50.945, stale_seconds=32.147, symmetry_prior=0.208, expand=False, counter_from=0.671,
                counter_strength=1.523, army_plan={UnitType.FOOTMAN: 0.196, UnitType.ARCHER: 0.112, UnitType.KNIGHT: 0.148,
                UnitType.CATAPULT: 0.266, UnitType.CLERIC: 0.278}, research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP,
                Upgrade.ARROWS_1, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=133.275, push_by=555.159,
                wood_crew=2, wood_from=9, opening=(BuildingType.STABLES, BuildingType.BLACKSMITH,), abort_ratio=1.314),
        # dwarf-2-best1: 0.727 over 1630 games of its search
        replace(PRO, name='bred-dwarf-2', combat_every=0.121, workers_per_mine=12, lumber_share=0.285,
                lumber_floor_panic=476, panic_gold=2714, lumber_stock=2593, supply_slack=2, supply_per_producer=0.434,
                max_sites=6, surplus_gold=307, lumber_floor=239, max_halls=1, mine_floor=9646, barracks_per_hall=6,
                towers_early=1, gold_per_barracks=600, attack_ratio=0.774, retreat_ratio=0.585, regroup_seconds=53.112,
                min_army=17, soldiers_before_workers=3, retreat_wounded=False, retreat_hp=0.228, rejoin_hp=0.61, raid=False,
                raiders=6, reinforce_group=2, scout=False, scout_from=49.302, symmetry_prior=0.276, counter_from=0.671,
                counter_strength=0.5, army_plan={UnitType.FOOTMAN: 0.172, UnitType.KNIGHT: 0.193, UnitType.CATAPULT: 0.303,
                UnitType.CLERIC: 0.332}, research_order=(Upgrade.MARKSMANSHIP, Upgrade.ARMOR_1, Upgrade.BLADES_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.ARROWS_1, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.ARMOR_2, Upgrade.BLADES_2,
                Upgrade.ARROWS_2, Upgrade.SIEGE,), push_upgrades=1, push_after=133.275, push_by=478.686, wood_crew=1,
                wood_from=9, opening=(BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.BLACKSMITH,
                BuildingType.STABLES,), defend_ratio=1.304, abort_ratio=1.5),
    ),
}

#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.
BRED_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {
    (Race.HUMAN, Layout.KLONDIKE): (
        # human-klondike-best1: 0.767 over 1390 games of its search
        replace(PRO, name='bred-human-klondike-1', combat_every=0.1, workers_per_mine=9, lumber_share=0.322,
                lumber_floor_panic=307, lumber_stock=2131, supply_per_producer=1.686, max_sites=4, surplus_gold=920,
                lumber_floor=146, max_halls=2, mine_floor=2000, barracks_per_hall=4, barracks_first=True,
                gold_per_barracks=1390, max_producers=9, attack_ratio=0.935, regroup_seconds=70.548, min_army=8,
                soldiers_before_workers=3, tower_count=1, raid=False, raiders=3, reinforce_group=2, ignore_raid_ratio=0.48,
                scout=False, scout_from=32.942, stale_seconds=39.958, clerics=False, counter_from=0.239,
                counter_strength=0.808, army_plan={UnitType.FOOTMAN: 0.067, UnitType.ARCHER: 0.126, UnitType.SCOUT: 0.17,
                UnitType.KNIGHT: 0.173, UnitType.CATAPULT: 0.263, UnitType.CLERIC: 0.201}, push_after=141.554,
                push_by=682.126, wood_from=7, opening=(BuildingType.STABLES,), opening_hold=True, abort_ratio=1.5,
                wood_lead=True, wood_per_hand=314),
    ),
}
