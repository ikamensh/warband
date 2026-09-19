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
        # human-1-best3: 0.720 over 232 games of its search
        replace(PRO, name='bred-human-2', combat_every=0.201, workers_per_mine=9, lumber_floor_panic=307, lumber_stock=2131,
                supply_per_producer=1.686, surplus_gold=920, max_halls=2, mine_floor=2553, barracks_first=True,
                max_producers=11, attack_ratio=1.0, regroup_seconds=79.1, min_army=15, soldiers_before_workers=3,
                tower_count=1, scout=False, scout_from=32.942, expand=False, counter_from=0.2, counter_strength=2.232,
                save_for_wanted=False, research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2,
                Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=84.511, opening=(BuildingType.STABLES,
                BuildingType.TOWN_HALL,), wood_lead=True, wood_per_hand=271),
    ),
    Race.ORC: (
        # orc-1-best1: 0.798 over 1464 games of its search
        replace(PRO, name='bred-orc-1', think_every=0.479, workers_per_mine=12, lumber_share=0.244, lumber_stock=2593,
                max_workers=33, supply_slack=5, supply_per_producer=2.682, max_sites=4, surplus_gold=1408, lumber_floor=114,
                max_halls=4, mine_floor=2553, barracks_first=True, gold_per_barracks=1702, max_producers=11,
                attack_ratio=1.2, min_army=12, soldiers_before_workers=3, retreat_hp=0.222, rejoin_hp=0.717, scout=False,
                symmetry_prior=0.188, expand_early=True, clerics=False, counter_strength=0.98, army_plan={UnitType.FOOTMAN:
                0.176, UnitType.ARCHER: 0.176, UnitType.KNIGHT: 0.176, UnitType.CATAPULT: 0.176, UnitType.CLERIC: 0.277},
                save_for_wanted=False, research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2,
                Upgrade.ARROWS_2, Upgrade.SIEGE,), push_upgrades=1, push_after=178.069, push_by=527.829, wood_from=7,
                opening=(BuildingType.BARRACKS, BuildingType.WORKSHOP, BuildingType.TOWN_HALL, BuildingType.STABLES,),
                defend_ratio=1.328, abort_ratio=1.5, wood_per_hand=267),
        # orc-1-best3: 0.728 over 912 games of its search
        replace(PRO, name='bred-orc-2', think_every=0.479, combat_every=0.171, workers_per_mine=12, lumber_share=0.244,
                lumber_stock=2593, max_workers=33, supply_slack=5, supply_per_producer=2.682, max_sites=4,
                surplus_gold=1408, lumber_floor=114, max_halls=4, mine_floor=2553, barracks_first=True,
                gold_per_barracks=1702, max_producers=11, attack_ratio=0.652, min_army=12, soldiers_before_workers=3,
                retreat_hp=0.222, rejoin_hp=0.775, ignore_raid_ratio=0.363, scout=False, symmetry_prior=0.188,
                clerics=False, counter_strength=0.98, army_plan={UnitType.FOOTMAN: 0.176, UnitType.ARCHER: 0.176,
                UnitType.KNIGHT: 0.176, UnitType.CATAPULT: 0.176, UnitType.CLERIC: 0.277}, save_for_wanted=False,
                early_tech=(BuildingType.STABLES,), push_after=178.069, push_by=577.527, opening=(BuildingType.BARRACKS,
                BuildingType.WORKSHOP, BuildingType.TOWN_HALL, BuildingType.STABLES,), abort_ratio=1.5, wood_per_hand=373),
    ),
    Race.ELF: (
        # elf-1-best1: 0.776 over 552 games of its search
        replace(PRO, name='bred-elf-1', think_every=0.387, combat_every=0.215, workers_per_mine=12, lumber_share=0.228,
                lumber_stock=2593, supply_slack=2, max_sites=7, surplus_gold=307, lumber_floor=239, max_halls=2,
                mine_floor=9646, barracks_per_hall=6, towers_early=1, gold_per_barracks=600, max_producers=11,
                attack_ratio=0.774, retreat_ratio=0.457, regroup_seconds=58.213, min_army=17, soldiers_before_workers=3,
                retreat_wounded=False, retreat_hp=0.116, rejoin_hp=0.69, raid=False, raiders=6, reinforce_group=2,
                scout=False, scout_from=41.011, symmetry_prior=0.276, clerics=False, counter_from=0.493,
                counter_strength=0.609, army_plan={UnitType.FOOTMAN: 0.162, UnitType.KNIGHT: 0.264, UnitType.CATAPULT:
                0.275, UnitType.CLERIC: 0.3}, push_upgrades=1, push_after=133.275, push_by=478.686, wood_crew=1,
                wood_from=9, opening=(BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.BLACKSMITH,),
                abort_ratio=1.5, wood_per_hand=409, wood_release=400),
    ),
    Race.DWARF: (
        # dwarf-1-best1: 0.853 over 272 games of its search
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
        # dwarf-1-best2: 0.786 over 632 games of its search
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

}
