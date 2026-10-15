"""The island roster: postures bred on Scaleway training islands on the merged upstream maps, one VM a
race (written by ``tools/evolve.py export``; bred again rather than edited by hand; the second dwarf
posture is local round four's champion, the dwarf island proving only one).  Played by
:class:`warband.brains.pro_ai.RaceBrain` as the arena agent ``apex5``; measured in
``docs/ai-ladder.md`` ("Reading a match"), evidence in ``~/saga/evidence/warband/ai-apex/``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

APEX5: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # human-island1-best1: 0.731 over 3144 games of its search
        replace(PRO, name='apex5-human-1', think_every=0.433, combat_every=0.1, workers_per_mine=9, lumber_share=0.363,
                lumber_floor_panic=313, panic_gold=1000, supply_slack=2, max_sites=7, surplus_gold=962, lumber_floor=185,
                mine_floor=2000, barracks_per_hall=6, gold_per_barracks=2005, attack_ratio=1.089, retreat_ratio=0.455,
                regroup_seconds=52.624, min_army=6, soldiers_before_workers=8, tower_count=1, retreat_hp=0.204,
                rejoin_hp=0.719, scout=False, scout_from=21.127, stale_seconds=40.094, symmetry_prior=0.25,
                creep_from=195.47, creep_ratio=1.311, creep_reach=33.333, counter_from=0.256, counter_strength=2.0,
                army_plan={UnitType.ARCHER: 0.386, UnitType.KNIGHT: 0.237, UnitType.CATAPULT: 0.093, UnitType.CLERIC:
                0.284}, early_tech=(BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.WORKSHOP,),
                research_order=(Upgrade.ARMOR_1, Upgrade.BLADES_1, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.ARMOR_2, Upgrade.BLADES_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=612.937, wood_from=11, opening=(BuildingType.STABLES, BuildingType.BARRACKS,),
                abort_ratio=1.5, wood_release=946, vault_from=60.0, second_vault=False, spell_1=Upgrade.HASTE,
                spell_3=Upgrade.METEOR, cast_worth=2.816, far_worth=2.326, soft_target=True, punish=True, punish_ratio=0.61,
                queue_depth=1),
        # human-island1-best2: 0.601 over 744 games of its search
        replace(PRO, name='apex5-human-2', combat_every=0.1, workers_per_mine=8, lumber_share=0.389, lumber_floor_panic=313,
                panic_gold=1000, supply_slack=2, max_sites=6, surplus_gold=962, lumber_floor=185, mine_floor=2000,
                barracks_per_hall=6, gold_per_barracks=2005, attack_ratio=1.089, retreat_ratio=0.455,
                regroup_seconds=52.624, min_army=6, soldiers_before_workers=8, tower_count=1, retreat_hp=0.231,
                rejoin_hp=0.719, raiders=0, scout=False, scout_from=21.127, stale_seconds=40.094, symmetry_prior=0.25,
                expand_early=True, creep_from=195.47, creep_ratio=1.511, creep_reach=33.333, counter_from=0.2,
                counter_strength=2.0, army_plan={UnitType.ARCHER: 0.409, UnitType.KNIGHT: 0.08, UnitType.CATAPULT: 0.209,
                UnitType.CLERIC: 0.302}, early_tech=(BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.WORKSHOP,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=612.937, wood_from=11, opening=(BuildingType.STABLES, BuildingType.BARRACKS,),
                abort_ratio=1.5, wood_per_hand=236, wood_release=946, vault_from=60.0, second_vault=False,
                spell_1=Upgrade.HASTE, spell_3=Upgrade.METEOR, cast_worth=2.816, far_worth=2.326, soft_target=True,
                punish=True, punish_ratio=0.697),
    ),
    Race.ORC: (
        # orc-island1-best1: 0.680 over 1692 games of its search
        replace(PRO, name='apex5-orc-1', combat_every=0.282, lumber_share=0.338, lumber_floor_panic=0, panic_gold=1135,
                lumber_stock=1674, max_workers=38, max_sites=6, lumber_floor=28, max_halls=4, mine_floor=5661,
                gold_per_barracks=1455, attack_ratio=0.8, regroup_seconds=45.303, min_army=6, soldiers_before_workers=10,
                retreat_wounded=False, retreat_hp=0.212, rejoin_hp=0.612, raiders=1, ignore_raid_ratio=0.6, scout=False,
                scout_from=41.981, stale_seconds=55.455, symmetry_prior=0.25, expand=False, creep=False, creep_army=13,
                creep_reach=34.497, counter_from=0.254, counter_strength=1.29, save_for_wanted=False,
                early_tech=(BuildingType.BARRACKS, BuildingType.STABLES,), push_by=630.587, wood_crew=2, wood_from=6,
                opening=(BuildingType.TOWN_HALL, BuildingType.TOWN_HALL, BuildingType.BLACKSMITH, BuildingType.TOWN_HALL,
                BuildingType.BARRACKS,), defend_ratio=1.5, prospect_floor=22636, abort_ratio=1.487, wood_per_hand=523,
                wood_release=858, magic=False, magic_hold=True, spell_1=Upgrade.MEND, spell_3=Upgrade.SUMMON,
                cast_worth=2.973, far_worth=2.152, punish=True, punish_ratio=0.499, siege_answer=3),
        # orc-island1-best2: 0.659 over 3192 games of its search
        replace(PRO, name='apex5-orc-2', combat_every=0.18, lumber_share=0.424, lumber_floor_panic=0, panic_gold=1135,
                lumber_stock=1674, max_workers=38, lumber_floor=188, max_halls=4, mine_floor=5661, barracks_first=True,
                gold_per_barracks=1455, max_producers=9, attack_ratio=0.7, retreat_ratio=0.405, regroup_seconds=30.0,
                soldiers_before_workers=10, tower_count=3, retreat_wounded=False, retreat_hp=0.212, raiders=1,
                ignore_raid_ratio=0.759, scout=False, scout_from=41.981, symmetry_prior=0.142, expand=False, creep=False,
                creep_army=13, creep_reach=34.497, clerics=False, counter_strength=1.269, save_for_wanted=False,
                early_tech=(BuildingType.STABLES,), push_by=600.708, wood_crew=2, wood_from=6,
                opening=(BuildingType.STABLES, BuildingType.TOWN_HALL, BuildingType.TOWN_HALL,), defend_ratio=0.984,
                prospect_floor=24000, abort_ratio=1.5, wood_per_hand=523, wood_release=781, vault_from=60.0,
                second_vault=False, magic_hold=True, spell_1=Upgrade.MEND, spell_2=Upgrade.STONESKIN, far_worth=2.152,
                soft_target=True),
    ),
    Race.ELF: (
        # elf-island1-best1: 0.876 over 684 games of its search
        replace(PRO, name='apex5-elf-1', think_every=0.564, combat_every=0.226, workers_per_mine=11, lumber_share=0.175,
                lumber_floor_panic=293, panic_gold=2108, lumber_stock=3189, max_workers=34, supply_slack=2,
                supply_per_producer=1.397, barracks_per_hall=4, barracks_first=True, towers_early=2, attack_ratio=1.089,
                retreat_ratio=0.652, regroup_seconds=30.0, min_army=3, soldiers_before_workers=4, tower_count=1,
                retreat_wounded=False, retreat_hp=0.207, rejoin_hp=0.782, raid=True, raiders=3, ignore_raid_ratio=0.528,
                scout=False, stale_seconds=40.0, symmetry_prior=0.106, expand=False, creep_from=103.2, creep_ratio=1.671,
                counter_from=0.1, army_plan={UnitType.ARCHER: 0.161, UnitType.KNIGHT: 0.214, UnitType.CATAPULT: 0.214,
                UnitType.CLERIC: 0.411}, save_for_wanted=False, early_tech=(BuildingType.BARRACKS, BuildingType.BARRACKS,
                BuildingType.BARRACKS, BuildingType.STABLES,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1,
                Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_by=497.918, wood_crew=1,
                opening=(BuildingType.LUMBER_MILL, BuildingType.TOWN_HALL, BuildingType.WORKSHOP, BuildingType.CHURCH,
                BuildingType.WORKSHOP,), defend_ratio=1.5, abort_ratio=1.5, wood_lead=True, wood_per_hand=465,
                wood_release=2500, vault_from=60.0, second_vault=False, spell_1=Upgrade.FLAME_STRIKE,
                spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.BATTLE_FURY, cast_worth=4.626),
        # elf-island1-best2: 0.847 over 624 games of its search
        replace(PRO, name='apex5-elf-2', think_every=0.564, combat_every=0.226, workers_per_mine=13, lumber_share=0.364,
                lumber_floor_panic=300, panic_gold=1000, max_workers=29, supply_slack=3, supply_per_producer=1.397,
                max_halls=4, barracks_per_hall=4, barracks_first=True, towers_early=3, attack_ratio=1.089,
                retreat_ratio=0.652, regroup_seconds=30.0, min_army=3, soldiers_before_workers=9, tower_count=1,
                retreat_wounded=False, retreat_hp=0.1, rejoin_hp=0.782, raid=True, raiders=1, ignore_raid_ratio=0.528,
                scout=False, stale_seconds=37.05, symmetry_prior=0.106, creep_from=103.2, creep_ratio=1.314,
                counter_from=0.1, army_plan={UnitType.ARCHER: 0.161, UnitType.KNIGHT: 0.214, UnitType.CATAPULT: 0.214,
                UnitType.CLERIC: 0.411}, save_for_wanted=False, early_tech=(BuildingType.BLACKSMITH,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=497.918, opening=(BuildingType.LUMBER_MILL, BuildingType.TOWN_HALL,),
                abort_ratio=1.5, wood_lead=True, wood_per_hand=297, wood_release=1445, magic=False, vault_from=60.0,
                magic_hold=True, spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.BATTLE_FURY, cast_worth=4.036,
                punish_ratio=0.619, queue_depth=3),
    ),
    Race.DWARF: (
        # dwarf-island1-best1: 0.753 over 360 games of its search
        replace(PRO, name='apex5-dwarf-1', think_every=0.664, combat_every=0.203, workers_per_mine=11, lumber_share=0.358,
                lumber_floor_panic=128, panic_gold=1535, lumber_stock=972, max_workers=36, supply_slack=2,
                supply_per_producer=1.523, max_sites=7, surplus_gold=638, lumber_floor=152, max_halls=1, mine_floor=5488,
                barracks_per_hall=6, max_producers=12, attack_ratio=0.8, retreat_ratio=0.666, regroup_seconds=10.0,
                min_army=8, soldiers_before_workers=9, tower_count=1, retreat_hp=0.31, rejoin_hp=0.514, raid=True,
                raiders=1, ignore_raid_ratio=0.48, stale_seconds=40.0, symmetry_prior=0.1, expand=False, creep=False,
                creep_from=251.536, creep_ratio=1.399, creep_reach=46.473, counter_from=0.657,
                early_tech=(BuildingType.CHURCH, BuildingType.CHURCH,), research_order=(Upgrade.ARMOR_1, Upgrade.ARROWS_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLADES_1,
                Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.BLADES_2, Upgrade.SIEGE,), push_by=616.467,
                opening=(BuildingType.CHURCH, BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.STABLES,
                BuildingType.BLACKSMITH,), defend_ratio=1.545, abort_ratio=1.81, wood_per_hand=297, wood_release=1461,
                magic=False, vault_from=156.261, spell_1=Upgrade.MEND, far_worth=2.212, soft_target=True, base_trade=True,
                repair_crew=3, repair_from=0.615, repair_under_fire=True, queue_depth=1),
        # dwarf-4-best1: 0.717 over 580 games of its search
        replace(PRO, name='apex5-dwarf-2', combat_every=0.203, workers_per_mine=11, lumber_share=0.358,
                lumber_floor_panic=128, panic_gold=1270, lumber_stock=1328, max_workers=35, supply_slack=3,
                supply_per_producer=1.831, max_sites=7, surplus_gold=638, lumber_floor=152, max_halls=1, mine_floor=6847,
                barracks_per_hall=6, max_producers=12, attack_ratio=0.8, retreat_ratio=0.663, regroup_seconds=30.0,
                min_army=3, soldiers_before_workers=10, tower_count=0, retreat_hp=0.329, rejoin_hp=0.55, raiders=1,
                stale_seconds=40.0, symmetry_prior=0.22, expand=False, creep=False, creep_from=224.232, creep_army=5,
                creep_ratio=1.399, creep_reach=43.946, counter_from=0.657, army_plan={UnitType.FOOTMAN: 0.339,
                UnitType.ARCHER: 0.186, UnitType.KNIGHT: 0.103, UnitType.CATAPULT: 0.186, UnitType.CLERIC: 0.186},
                save_for_wanted=False, early_tech=(BuildingType.WORKSHOP, BuildingType.CHURCH,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH,
                Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.MARKSMANSHIP, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), opening=(BuildingType.CHURCH, BuildingType.BARRACKS, BuildingType.TOWN_HALL,
                BuildingType.STABLES, BuildingType.BLACKSMITH,), wood_per_hand=391, wood_release=1855, magic_hold=True,
                spell_3=Upgrade.SUMMON, cast_worth=3.657, far_worth=2.37, punish=True, siege_answer=1, repair_crew=3,
                repair_from=0.615, repair_under_fire=True, queue_depth=1),
    ),
}

#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.
APEX5_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {

}
