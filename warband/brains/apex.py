"""The apex roster: postures bred per race against Master's postures, Medium, Grandmaster and the best
hand-built contender together (written by ``tools/evolve.py export``; bred again rather than edited by
hand).  :class:`warband.brains.pro_ai.RaceBrain` plays them as the arena agent ``apex``; whether they
replace Grandmaster's table is settled by the confirming ladder in ``docs/ai-ladder.md``
("Reading a match").  The searches and trials behind them are kept in
``~/saga/evidence/warband/ai-apex/``."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from warband.brains.pro_ai import PRO, ProProfile
from warband.sim.rules import BuildingType, Layout, Race, UnitType, Upgrade

APEX: Final[dict[Race, tuple[ProProfile, ...]]] = {
    Race.HUMAN: (
        # human-1-best1: 0.667 over 216 games of its search
        replace(PRO, name='apex-human-1', combat_every=0.209, workers_per_mine=9, lumber_floor_panic=313, panic_gold=1000,
                supply_slack=3, max_sites=7, surplus_gold=962, lumber_floor=188, mine_floor=2553, barracks_per_hall=6,
                gold_per_barracks=1714, attack_ratio=1.0, regroup_seconds=75.254, min_army=10, soldiers_before_workers=8,
                tower_count=1, retreat_hp=0.232, rejoin_hp=0.719, raiders=0, ignore_raid_ratio=0.319, scout=False,
                scout_from=32.365, expand_early=True, creep_from=195.47, siege=False, counter_from=0.2,
                counter_strength=2.0, save_for_wanted=False, early_tech=(BuildingType.WORKSHOP,), push_after=84.511,
                opening=(BuildingType.TOWN_HALL,), prospect_floor=18747, abort_ratio=1.5, wood_release=946,
                vault_from=60.252, spell_1=Upgrade.HASTE, spell_3=Upgrade.METEOR, cast_worth=2.816),
        # human-1-best2: 0.659 over 264 games of its search
        replace(PRO, name='apex-human-2', combat_every=0.122, workers_per_mine=8, lumber_share=0.362, panic_gold=1714,
                lumber_stock=2125, supply_per_producer=2.116, max_sites=7, lumber_floor=188, mine_floor=2553,
                barracks_per_hall=6, gold_per_barracks=1714, attack_ratio=1.0, regroup_seconds=75.254, min_army=10,
                raiders=0, ignore_raid_ratio=0.319, scout=False, scout_from=39.19, expand_early=True, creep=False,
                clerics=False, counter_from=0.239, army_plan={UnitType.FOOTMAN: 0.168, UnitType.ARCHER: 0.162,
                UnitType.KNIGHT: 0.396, UnitType.CATAPULT: 0.168, UnitType.CLERIC: 0.106},
                early_tech=(BuildingType.WORKSHOP,), research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1,
                Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_after=84.511, wood_from=7, opening_hold=True,
                prospect_floor=15244, abort_ratio=1.5, wood_per_hand=100, wood_release=803, vault_from=251.403),
    ),
    Race.ORC: (
        # orc-1-best1: 0.750 over 216 games of its search
        replace(PRO, name='apex-orc-1', think_every=0.479, combat_every=0.179, workers_per_mine=12, lumber_share=0.244,
                lumber_stock=2593, supply_slack=5, supply_per_producer=2.396, max_sites=6, surplus_gold=200,
                barracks_first=True, max_producers=9, attack_ratio=0.652, regroup_seconds=53.884, min_army=12,
                soldiers_before_workers=4, tower_count=3, retreat_hp=0.222, rejoin_hp=0.95, raiders=3,
                ignore_raid_ratio=0.363, scout=False, stale_seconds=18.893, symmetry_prior=0.188, expand_early=True,
                creep=False, creep_ratio=1.752, clerics=False, counter_from=0.103, counter_strength=0.98,
                army_plan={UnitType.FOOTMAN: 0.179, UnitType.ARCHER: 0.179, UnitType.KNIGHT: 0.179, UnitType.CATAPULT:
                0.179, UnitType.CLERIC: 0.282}, save_for_wanted=False, early_tech=(BuildingType.STABLES,),
                research_order=(Upgrade.BLADES_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                Upgrade.ARMOR_1, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER,
                Upgrade.MARKSMANSHIP, Upgrade.ARROWS_1, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_after=199.074, push_by=577.527, wood_crew=1, opening=(BuildingType.BARRACKS,
                BuildingType.WORKSHOP, BuildingType.TOWN_HALL, BuildingType.STABLES,), prospect_floor=24000,
                abort_ratio=1.5, wood_per_hand=373, magic=False, second_vault=False, spell_2=Upgrade.STONESKIN,
                spell_3=Upgrade.SUMMON, cast_worth=3.162, far_worth=1.597),
        # orc-1-best2: 0.680 over 264 games of its search
        replace(PRO, name='apex-orc-2', combat_every=0.193, workers_per_mine=9, lumber_floor_panic=0, panic_gold=1724,
                max_halls=4, mine_floor=5655, barracks_first=True, attack_ratio=0.7, retreat_ratio=0.405,
                regroup_seconds=30.0, min_army=6, soldiers_before_workers=9, retreat_hp=0.247, scout=False,
                scout_from=58.554, symmetry_prior=0.25, expand=False, creep_army=10, siege=False, wood_crew=1,
                opening_hold=True, defend_ratio=1.5, prospect_floor=24000, abort_ratio=1.5, wood_per_hand=400,
                spell_3=Upgrade.BATTLE_FURY, cast_worth=3.696),
    ),
    Race.ELF: (
        # elf-1-best1: 0.702 over 272 games of its search
        replace(PRO, name='apex-elf-1', lumber_floor_panic=300, panic_gold=1000, lumber_stock=1523, max_workers=31,
                barracks_first=True, towers_early=2, attack_ratio=0.7, regroup_seconds=30.0, min_army=6,
                soldiers_before_workers=10, tower_count=1, retreat_hp=0.186, symmetry_prior=0.25, expand=False,
                research_order=(Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.MARKSMANSHIP, Upgrade.BLESSING, Upgrade.BLOODLUST,
                Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2,
                Upgrade.SIEGE,), push_upgrades=1, opening=(BuildingType.LUMBER_MILL,), defend_ratio=1.788,
                prospect_floor=24000, abort_ratio=1.5, wood_release=915, second_vault=False, magic_hold=True),
        # elf-1-best2: 0.685 over 200 games of its search
        replace(PRO, name='apex-elf-2', lumber_floor_panic=300, panic_gold=1000, barracks_first=True, attack_ratio=0.7,
                regroup_seconds=30.0, min_army=6, soldiers_before_workers=8, symmetry_prior=0.25, expand=False,
                prospect_floor=24000, abort_ratio=1.5),
    ),
    Race.DWARF: (
        # dwarf-1-best1: 0.727 over 216 games of its search
        replace(PRO, name='apex-dwarf-1', combat_every=0.241, workers_per_mine=12, lumber_floor_panic=132, panic_gold=1147,
                max_workers=41, supply_slack=3, surplus_gold=638, max_halls=2, mine_floor=6847, barracks_per_hall=5,
                max_producers=11, attack_ratio=0.8, regroup_seconds=30.0, min_army=7, soldiers_before_workers=8,
                tower_count=1, retreat_wounded=False, retreat_hp=0.241, rejoin_hp=0.567, stale_seconds=40.0,
                symmetry_prior=0.25, expand=False, creep=False, creep_from=60.0, creep_reach=34.774, siege=False,
                counter_from=0.657, research=False, research_order=(Upgrade.BLADES_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.ARMOR_1, Upgrade.MARKSMANSHIP, Upgrade.ARROWS_1,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.BLADES_2,
                Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE,), push_by=542.381, opening=(BuildingType.CHURCH,
                BuildingType.BARRACKS,), prospect_floor=24000, wood_per_hand=229, second_vault=False,
                spell_1=Upgrade.FLAME_STRIKE, spell_2=Upgrade.STONESKIN, far_worth=2.055),
        # dwarf-1-best2: 0.645 over 960 games of its search
        replace(PRO, name='apex-dwarf-2', combat_every=0.241, lumber_share=0.457, lumber_floor_panic=300, panic_gold=1160,
                lumber_stock=2639, surplus_gold=638, mine_floor=6847, barracks_per_hall=5, barracks_first=True,
                attack_ratio=0.8, regroup_seconds=30.0, min_army=7, soldiers_before_workers=9, retreat_hp=0.241,
                stale_seconds=40.0, symmetry_prior=0.25, creep=False, creep_reach=37.878, counter_from=0.458,
                save_for_wanted=False, early_tech=(BuildingType.BARRACKS, BuildingType.BLACKSMITH, BuildingType.WORKSHOP,
                BuildingType.CHURCH,), research_order=(Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER,
                Upgrade.DEEP_MINING, Upgrade.LONGBOWS, Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.MARKSMANSHIP,
                Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER, Upgrade.ARROWS_2,
                Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.SIEGE,), push_by=542.381, opening=(BuildingType.CHURCH,
                BuildingType.TOWER, BuildingType.TOWN_HALL, BuildingType.TOWER,), prospect_floor=24000, wood_release=2101,
                magic=False, vault_from=268.929, second_vault=False, cast_worth=3.024),
    ),
}

#: A race's postures for one kind of map, where a search on that map alone bred better ones than the race's own.
APEX_FOR_LAYOUT: Final[dict[tuple[Race, Layout], tuple[ProProfile, ...]]] = {

}
