"""The third apex roster: round-3 postures bred with the enlarged genome (soft targets, punishment,
siege answers, base trades, interceptions, creeping, repair crews) against apex and apex2 (written by
``tools/evolve.py export``; bred again rather than edited by hand; the second dwarf posture is round
two's champion, round three proving only one dwarf).  Played by
:class:`warband.brains.pro_ai.RaceBrain` as the arena agent ``apex3``; measured in
``docs/ai-ladder.md`` ("Reading a match"), evidence in ``~/saga/evidence/warband/ai-apex/``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

APEX3: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # human-3-best1: 0.683 over 580 games of its search
        replace(PRO, name='apex3-human-1', combat_every=0.1, workers_per_mine=8, lumber_share=0.363, lumber_floor_panic=313,
                panic_gold=1000, supply_slack=2, max_sites=6, surplus_gold=962, lumber_floor=185, mine_floor=2000,
                barracks_per_hall=6, gold_per_barracks=2005, attack_ratio=0.5, retreat_ratio=0.455, regroup_seconds=41.468,
                min_army=7, soldiers_before_workers=8, tower_count=1, retreat_hp=0.231, rejoin_hp=0.719, scout=False,
                scout_from=34.325, stale_seconds=40.094, symmetry_prior=0.25, expand_early=True, creep_from=195.47,
                creep_ratio=1.401, creep_reach=33.333, counter_from=0.2, counter_strength=2.0, army_plan={UnitType.ARCHER:
                0.46, UnitType.KNIGHT: 0.09, UnitType.CATAPULT: 0.111, UnitType.CLERIC: 0.339},
                early_tech=(BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.WORKSHOP,),
                research_order=(Upgrade.ARMOR_1, Upgrade.BLADES_1, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.ARMOR_2, Upgrade.BLADES_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=612.937, wood_from=11, opening=(BuildingType.STABLES, BuildingType.BARRACKS,),
                abort_ratio=1.5, wood_release=946, vault_from=60.0, second_vault=False, spell_1=Upgrade.HASTE,
                spell_3=Upgrade.METEOR, cast_worth=2.816, far_worth=2.326),
        # human-3-best2: 0.649 over 1220 games of its search
        replace(PRO, name='apex3-human-2', combat_every=0.1, workers_per_mine=9, lumber_share=0.449, lumber_floor_panic=313,
                panic_gold=660, lumber_stock=2618, max_workers=34, supply_slack=2, max_sites=6, surplus_gold=200,
                lumber_floor=185, mine_floor=2000, barracks_per_hall=6, towers_early=1, gold_per_barracks=2005,
                attack_ratio=1.047, regroup_seconds=75.254, min_army=10, soldiers_before_workers=8, tower_count=1,
                retreat_hp=0.231, rejoin_hp=0.808, raid=True, raiders=3, ignore_raid_ratio=0.33, scout=False,
                scout_from=40.0, symmetry_prior=0.279, creep=False, creep_from=256.189, creep_reach=33.333,
                counter_from=0.481, counter_strength=2.0, save_for_wanted=False, early_tech=(BuildingType.WORKSHOP,
                BuildingType.WORKSHOP,), push_after=27.984, push_by=508.203, wood_from=12, opening=(BuildingType.TOWN_HALL,
                BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.CHURCH,), prospect_floor=22600, wood_lead=True,
                wood_release=946, cast_worth=1.487, far_worth=1.562, base_trade=True),
    ),
    Race.ORC: (
        # orc-3-best1: 0.690 over 1140 games of its search
        replace(PRO, name='apex3-orc-1', combat_every=0.19, workers_per_mine=8, lumber_share=0.327, lumber_floor_panic=0,
                panic_gold=2099, lumber_stock=1674, max_halls=4, mine_floor=10719, barracks_first=True,
                gold_per_barracks=1425, attack_ratio=0.7, retreat_ratio=0.405, regroup_seconds=30.0,
                soldiers_before_workers=10, retreat_hp=0.235, ignore_raid_ratio=0.37, scout_from=43.452, symmetry_prior=0.1,
                expand=False, expand_early=True, creep=False, creep_from=91.479, creep_army=10, creep_reach=30.862,
                counter_strength=1.29, save_for_wanted=False, early_tech=(BuildingType.STABLES,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=600.708, wood_from=7, opening=(BuildingType.STABLES, BuildingType.TOWN_HALL,),
                opening_hold=True, defend_ratio=1.5, abort_ratio=1.5, wood_per_hand=523, wood_release=781, magic=False,
                magic_hold=True, spell_3=Upgrade.SUMMON, cast_worth=2.973, far_worth=2.152, intercept=True, repair_crew=2,
                repair_from=0.716),
        # orc-3-best2: 0.645 over 580 games of its search
        replace(PRO, name='apex3-orc-2', combat_every=0.18, workers_per_mine=8, lumber_share=0.327, lumber_floor_panic=0,
                panic_gold=1724, lumber_stock=1674, lumber_floor=188, max_halls=4, mine_floor=5661, barracks_first=True,
                gold_per_barracks=1425, attack_ratio=0.7, retreat_ratio=0.405, regroup_seconds=30.0,
                soldiers_before_workers=10, retreat_wounded=False, retreat_hp=0.212, ignore_raid_ratio=0.398,
                scout_from=43.452, symmetry_prior=0.142, expand=False, creep=False, creep_army=10, creep_reach=34.497,
                siege=False, clerics=False, counter_strength=1.269, army_plan={UnitType.FOOTMAN: 0.174, UnitType.ARCHER:
                0.174, UnitType.KNIGHT: 0.174, UnitType.CATAPULT: 0.305, UnitType.CLERIC: 0.174}, save_for_wanted=False,
                early_tech=(BuildingType.STABLES,), push_by=600.708, wood_crew=2, opening=(BuildingType.STABLES,
                BuildingType.TOWN_HALL,), opening_hold=True, defend_ratio=1.5, prospect_floor=24000, abort_ratio=1.5,
                wood_per_hand=523, wood_release=781, magic=False, second_vault=False, magic_hold=True, spell_1=Upgrade.MEND,
                spell_3=Upgrade.SUMMON, far_worth=2.152),
    ),
    Race.ELF: (
        # elf-3-best1: 0.770 over 230 games of its search
        replace(PRO, name='apex3-elf-1', think_every=0.564, combat_every=0.226, workers_per_mine=11, lumber_share=0.175,
                lumber_floor_panic=293, panic_gold=2108, lumber_stock=3049, max_workers=34, supply_per_producer=1.596,
                max_halls=2, barracks_per_hall=4, barracks_first=True, towers_early=1, attack_ratio=0.8,
                retreat_ratio=0.507, regroup_seconds=30.0, min_army=3, soldiers_before_workers=4, tower_count=1,
                retreat_hp=0.221, rejoin_hp=0.814, ignore_raid_ratio=0.507, scout=False, scout_from=30.711,
                stale_seconds=40.0, symmetry_prior=0.25, creep=False, creep_from=142.504, creep_ratio=1.371,
                counter_from=0.1, save_for_wanted=False, early_tech=(BuildingType.BARRACKS, BuildingType.BARRACKS,),
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=597.47, wood_crew=1, opening=(BuildingType.TOWN_HALL, BuildingType.STABLES,
                BuildingType.CHURCH, BuildingType.STABLES, BuildingType.BARRACKS,), abort_ratio=1.637, wood_lead=True,
                wood_per_hand=465, wood_release=2406, vault_from=140.678, magic_hold=True, spell_1=Upgrade.MEND,
                spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.BATTLE_FURY, cast_worth=5.157, far_worth=1.784, base_trade=True,
                intercept=True),
        # elf-3-best2: 0.760 over 200 games of its search
        replace(PRO, name='apex3-elf-2', workers_per_mine=12, lumber_share=0.312, lumber_floor_panic=300, panic_gold=1000,
                max_workers=29, barracks_per_hall=4, barracks_first=True, towers_early=2, attack_ratio=0.8,
                retreat_ratio=0.507, regroup_seconds=30.0, min_army=3, soldiers_before_workers=9, tower_count=1,
                scout=False, stale_seconds=40.0, symmetry_prior=0.25, expand=False, creep=False, creep_from=142.504,
                creep_ratio=1.353, counter_from=0.1, save_for_wanted=False, research_order=(Upgrade.BLADES_1,
                Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), opening=(BuildingType.LUMBER_MILL,),
                defend_ratio=1.788, prospect_floor=24000, abort_ratio=1.5, wood_release=916, vault_from=199.706,
                spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.BATTLE_FURY, cast_worth=3.442),
    ),
    Race.DWARF: (
        # dwarf-3-best1: 0.748 over 230 games of its search
        replace(PRO, name='apex3-dwarf-1', combat_every=0.203, workers_per_mine=11, lumber_share=0.358,
                lumber_floor_panic=128, panic_gold=1270, lumber_stock=1328, max_workers=36, supply_slack=3, max_sites=7,
                surplus_gold=638, lumber_floor=152, max_halls=2, mine_floor=6847, barracks_per_hall=6, max_producers=12,
                attack_ratio=0.8, retreat_ratio=0.666, regroup_seconds=21.887, min_army=8, soldiers_before_workers=10,
                tower_count=0, retreat_hp=0.329, rejoin_hp=0.55, raiders=1, ignore_raid_ratio=0.48, stale_seconds=40.0,
                symmetry_prior=0.1, expand=False, creep=False, creep_from=158.985, creep_army=5, creep_ratio=1.399,
                creep_reach=43.946, counter_from=0.657, army_plan={UnitType.FOOTMAN: 0.313, UnitType.ARCHER: 0.172,
                UnitType.KNIGHT: 0.172, UnitType.CATAPULT: 0.172, UnitType.CLERIC: 0.172},
                early_tech=(BuildingType.WORKSHOP, BuildingType.CHURCH,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1,
                Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.MARKSMANSHIP, Upgrade.BLADES_2,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_by=616.467, opening=(BuildingType.CHURCH,
                BuildingType.BARRACKS, BuildingType.TOWN_HALL, BuildingType.STABLES, BuildingType.BLACKSMITH,),
                defend_ratio=1.941, abort_ratio=1.81, wood_per_hand=297, wood_release=1461, vault_from=156.261,
                second_vault=False, spell_1=Upgrade.MEND, spell_3=Upgrade.SUMMON, far_worth=2.212, base_trade=True,
                repair_crew=3, repair_from=0.615, repair_under_fire=True, queue_depth=1),
        # dwarf-2-best1: 0.626 over 784 games of its search
        replace(PRO, name='apex3-dwarf-2', think_every=0.63, combat_every=0.241, workers_per_mine=11, lumber_floor_panic=128,
                panic_gold=1186, lumber_stock=1328, max_workers=36, supply_slack=3, surplus_gold=638, max_halls=2,
                mine_floor=6847, barracks_per_hall=5, barracks_first=True, max_producers=11, attack_ratio=0.8,
                retreat_ratio=0.607, regroup_seconds=30.0, min_army=6, soldiers_before_workers=10, tower_count=0,
                retreat_hp=0.241, rejoin_hp=0.567, scout_from=57.046, stale_seconds=40.0, symmetry_prior=0.25, expand=False,
                creep=False, creep_army=5, creep_ratio=1.288, creep_reach=39.983, siege=False, counter_from=0.657,
                counter_strength=0.608, early_tech=(BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,),
                research=False, research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING,
                Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2,
                Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=65.225, opening=(BuildingType.CHURCH, BuildingType.BARRACKS,
                BuildingType.TOWN_HALL, BuildingType.CHURCH,), prospect_floor=24000, abort_ratio=1.5, wood_release=1461,
                magic_hold=True, spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.SUMMON),
    ),
}

#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.
APEX3_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {

}
