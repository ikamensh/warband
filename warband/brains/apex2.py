"""The second apex roster: round-2 postures bred from ``brains/apex.py`` against apex itself (written by
``tools/evolve.py export``; bred again rather than edited by hand).  Played by
:class:`warband.brains.pro_ai.RaceBrain` as the arena agent ``apex2``; measured in
``docs/ai-ladder.md`` ("Reading a match"), evidence in ``~/saga/evidence/warband/ai-apex/``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

APEX2: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # human-2-best1: 0.707 over 816 games of its search
        replace(PRO, name='apex2-human-1', combat_every=0.1, workers_per_mine=8, lumber_share=0.363, lumber_floor_panic=313,
                panic_gold=1000, supply_slack=2, max_sites=6, surplus_gold=962, lumber_floor=185, mine_floor=2000,
                barracks_per_hall=6, gold_per_barracks=2005, attack_ratio=0.5, retreat_ratio=0.455, regroup_seconds=41.468,
                min_army=7, soldiers_before_workers=8, tower_count=1, retreat_hp=0.231, rejoin_hp=0.719, scout=False,
                scout_from=34.325, stale_seconds=40.094, symmetry_prior=0.25, expand_early=True, creep_from=195.47,
                creep_ratio=1.401, creep_reach=33.333, counter_from=0.2, counter_strength=2.0, army_plan={UnitType.ARCHER:
                0.439, UnitType.KNIGHT: 0.086, UnitType.CATAPULT: 0.106, UnitType.CLERIC: 0.323},
                early_tech=(BuildingType.STABLES, BuildingType.WORKSHOP, BuildingType.WORKSHOP,),
                research_order=(Upgrade.ARMOR_1, Upgrade.BLADES_1, Upgrade.ARROWS_1, Upgrade.MARKSMANSHIP, Upgrade.HORSES,
                Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.ARMOR_2, Upgrade.BLADES_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_by=612.937, wood_from=11, opening=(BuildingType.STABLES, BuildingType.BARRACKS,),
                abort_ratio=1.5, wood_release=946, vault_from=60.0, second_vault=False, spell_1=Upgrade.HASTE,
                spell_3=Upgrade.METEOR, cast_worth=2.816, far_worth=2.326),
        # human-2-best2: 0.734 over 184 games of its search
        replace(PRO, name='apex2-human-2', combat_every=0.1, workers_per_mine=9, lumber_share=0.363, lumber_floor_panic=313,
                panic_gold=1348, supply_slack=3, supply_per_producer=1.68, max_sites=6, surplus_gold=1018, lumber_floor=135,
                mine_floor=2000, barracks_per_hall=6, barracks_first=True, towers_early=1, gold_per_barracks=1714,
                max_producers=12, attack_ratio=1.0, regroup_seconds=75.254, min_army=10, soldiers_before_workers=7,
                tower_count=1, retreat_hp=0.232, rejoin_hp=0.671, raiders=0, ignore_raid_ratio=0.33, scout=False,
                scout_from=23.815, symmetry_prior=0.279, expand_early=True, creep=False, creep_from=256.189,
                creep_reach=33.333, siege=False, counter_from=0.481, counter_strength=2.0, save_for_wanted=False,
                early_tech=(BuildingType.STABLES,), push_after=27.984, push_by=508.203, wood_from=11,
                opening=(BuildingType.TOWN_HALL, BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.CHURCH,),
                prospect_floor=22600, abort_ratio=1.917, wood_release=946, vault_from=110.492, second_vault=False,
                magic_hold=True, spell_1=Upgrade.FLAME_STRIKE, spell_2=Upgrade.STONESKIN, spell_3=Upgrade.METEOR,
                cast_worth=2.816),
    ),
    Race.ORC: (
        # orc-2-best1: 0.777 over 224 games of its search
        replace(PRO, name='apex2-orc-1', combat_every=0.19, workers_per_mine=8, lumber_share=0.327, lumber_floor_panic=0,
                panic_gold=2099, lumber_stock=1674, max_halls=4, mine_floor=5661, barracks_first=True,
                gold_per_barracks=1425, attack_ratio=0.7, retreat_ratio=0.405, regroup_seconds=30.0,
                soldiers_before_workers=10, retreat_hp=0.235, ignore_raid_ratio=0.37, scout_from=43.452,
                symmetry_prior=0.142, expand=False, expand_early=True, creep=False, creep_army=10, creep_reach=34.497,
                siege=False, counter_strength=1.29, army_plan={UnitType.FOOTMAN: 0.205, UnitType.ARCHER: 0.167,
                UnitType.KNIGHT: 0.167, UnitType.CATAPULT: 0.293, UnitType.CLERIC: 0.167}, save_for_wanted=False,
                early_tech=(BuildingType.STABLES,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_by=600.708, wood_from=7,
                opening=(BuildingType.STABLES, BuildingType.TOWN_HALL,), opening_hold=True, defend_ratio=1.5,
                abort_ratio=1.5, wood_per_hand=523, wood_release=781, magic=False, spell_3=Upgrade.SUMMON, far_worth=2.152),
        # orc-2-best2: 0.731 over 264 games of its search
        replace(PRO, name='apex2-orc-2', combat_every=0.18, workers_per_mine=8, lumber_share=0.327, lumber_floor_panic=0,
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
        # elf-2-best1: 0.869 over 160 games of its search
        replace(PRO, name='apex2-elf-1', workers_per_mine=12, lumber_share=0.312, lumber_floor_panic=300, panic_gold=1000,
                max_workers=29, barracks_per_hall=4, barracks_first=True, towers_early=2, attack_ratio=0.8,
                retreat_ratio=0.507, regroup_seconds=30.0, min_army=3, soldiers_before_workers=9, tower_count=1,
                scout=False, stale_seconds=40.0, symmetry_prior=0.25, expand=False, creep=False, creep_from=142.504,
                creep_ratio=1.353, counter_from=0.1, save_for_wanted=False, research_order=(Upgrade.BLADES_1,
                Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), opening=(BuildingType.LUMBER_MILL,),
                defend_ratio=1.788, prospect_floor=24000, abort_ratio=1.5, wood_release=916, vault_from=199.706,
                spell_2=Upgrade.ENTANGLE, spell_3=Upgrade.BATTLE_FURY, cast_worth=3.442),
        # elf-2-best2: 0.759 over 432 games of its search
        replace(PRO, name='apex2-elf-2', lumber_share=0.275, lumber_floor_panic=300, panic_gold=1000, lumber_stock=1523,
                max_workers=31, barracks_first=True, towers_early=2, attack_ratio=0.7, regroup_seconds=30.0, min_army=6,
                soldiers_before_workers=10, tower_count=1, retreat_hp=0.186, symmetry_prior=0.25, save_for_wanted=False,
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_upgrades=1, opening=(BuildingType.LUMBER_MILL,), defend_ratio=1.788,
                prospect_floor=24000, abort_ratio=1.5, wood_lead=True, wood_per_hand=270, wood_release=915,
                second_vault=False),
    ),
    Race.DWARF: (
        # dwarf-2-best1: 0.626 over 784 games of its search
        replace(PRO, name='apex2-dwarf-1', think_every=0.63, combat_every=0.241, workers_per_mine=11, lumber_floor_panic=128,
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
        # dwarf-2-best2: 0.641 over 304 games of its search
        replace(PRO, name='apex2-dwarf-2', combat_every=0.211, workers_per_mine=12, lumber_floor_panic=132, panic_gold=859,
                max_workers=44, supply_slack=1, supply_per_producer=3.073, surplus_gold=384, lumber_floor=132, max_halls=1,
                mine_floor=6847, barracks_per_hall=6, barracks_first=True, gold_per_barracks=886, max_producers=11,
                attack_ratio=0.8, regroup_seconds=21.887, min_army=7, soldiers_before_workers=8, tower_count=1,
                retreat_hp=0.329, rejoin_hp=0.55, raiders=3, ignore_raid_ratio=0.48, scout=False, scout_from=65.029,
                stale_seconds=40.0, symmetry_prior=0.25, expand=False, creep=False, creep_from=167.96, creep_army=4,
                counter_from=0.651, save_for_wanted=False, push_by=616.467, wood_crew=1, wood_from=7,
                opening=(BuildingType.CHURCH, BuildingType.BARRACKS, BuildingType.TOWER, BuildingType.BARRACKS,
                BuildingType.TOWN_HALL,), prospect_floor=26423, abort_ratio=1.5, wood_per_hand=229, wood_release=1379,
                second_vault=False, spell_3=Upgrade.SUMMON, far_worth=2.212),
    ),
}

#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.
APEX2_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {

}
