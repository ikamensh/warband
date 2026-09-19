"""The computer players: what a difficulty does with what it has.

Some tests put the brain's own questions to it (whom it counts as the enemy's
soldiers, what it would target or train, which orders it has out): a match
shows them only through outcomes far too noisy to pin, so these call its
private helpers on purpose."""

import random

import pytest

from warband.sim import mapgen
from warband.brains.ai import DEFEND_RADIUS, PROFILES, Brain
from warband.sim.model import AttackMove, Harvest, Repair, World, dist, tile_center
from warband.sim.rules import BuildingType, Difficulty, Layout, Race, SIM_DT, Terrain, UnitType


def test_normal_and_hard_send_a_peasant_to_mend_a_damaged_building_but_easy_does_not() -> None:
    for difficulty, expected in ((Difficulty.MEDIUM, True), (Difficulty.EASY, False)):
        world = mapgen.generate(seed=5, players=2, human=None)
        brain = Brain(0, difficulty)
        hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
        hall.hp = hall.max_hp // 3
        rng = random.Random(1)
        for _ in range(int(8 / SIM_DT)):
            brain.think(world, rng)
            world.step()
        repairing = any(isinstance(u.order, Repair) for u in world.player_units(0)) or hall.hp > hall.max_hp // 3
        assert repairing == expected, difficulty
        if expected:
            assert any("repair town_hall" in what for _, what in brain.log)


def _siege_setup(enemy_type, enemy_count):
    """Eight own footmen marching on the enemy hall, with an enemy raid at an own farm."""
    world = mapgen.generate(seed=5, players=2, human=None)
    brain = Brain(0, Difficulty.MEDIUM)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    farm = None
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            pos = (hall.x + dx, hall.y + dy)
            if world.can_place(BuildingType.FARM, pos, 0) is None:
                farm = world.place_building(0, BuildingType.FARM, pos)
                break
        if farm is not None:
            break
    assert farm is not None
    target = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    footmen = [world.spawn_unit(0, UnitType.FOOTMAN, (hall.center[0] + i, hall.center[1] + 1)) for i in range(8)]
    world.attack_move([u.id for u in footmen], target)
    brain.attacking = True
    fx, fy = farm.center
    enemies = [world.spawn_unit(1, enemy_type, (fx + 2, fy + i * 0.7)) for i in range(enemy_count)]
    world.update_vision()
    return world, brain, footmen, target, enemies


def _defend_lines(brain):
    return [what for _, what in brain.log if "defend with" in what]


def test_a_lone_scout_draws_only_a_couple_of_defenders_and_the_attack_goes_on() -> None:
    world, brain, footmen, target, enemies = _siege_setup(UnitType.SCOUT, 1)
    scout = enemies[0].pos
    brain.think(world, random.Random(1))
    defending = [u for u in footmen if Brain._aimed_at(world, u, scout)]
    holding = [u for u in footmen
               if isinstance(u.order, AttackMove) and dist(u.order.target, target) < 1.0]
    assert len(defending) <= 3
    assert len(holding) >= 5
    assert brain.attacking is True
    assert len(_defend_lines(brain)) == 1
    world.time += brain.profile.think_every + 0.1
    brain.think(world, random.Random(2))
    assert len(_defend_lines(brain)) == 1


def test_a_serious_raid_recalls_the_whole_army_and_cancels_the_attack() -> None:
    world, brain, footmen, _target, _enemies = _siege_setup(UnitType.FOOTMAN, 6)
    brain.think(world, random.Random(1))
    threat = brain._threat(world)
    assert threat is not None
    assert all(Brain._aimed_at(world, u, threat) for u in footmen)
    assert brain.attacking is False


def _farm_headroom(world, count=3) -> None:
    """Completed farms near player 0's first hall so the supply cap does not mask the workforce target."""
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    placed = 0
    for radius in range(4, 13):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius or placed >= count:
                    continue
                pos = (hall.x + dx, hall.y + dy)
                if world.can_place(BuildingType.FARM, pos, 0) is None:
                    world.place_building(0, BuildingType.FARM, pos)
                    placed += 1
        if placed >= count:
            break
    assert placed == count
    world.update_vision()


def _expansion_world():
    """Player 0 with a completed hall beside a far neutral mine, plus farm headroom and gold to spare."""
    world = mapgen.generate(seed=5, players=2, human=None)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    home = [b.center for b in world.buildings.values() if b.type is BuildingType.TOWN_HALL]
    candidates = [m for m in world.mines() if all(dist(m.center, h) > 10 for h in home)]
    far = max(candidates or world.mines(), key=lambda m: dist(m.center, hall.center))
    pos = None
    for dx, dy in ((-5, 0), (4, 0), (0, -5), (0, 4)):
        candidate = (far.x + dx, far.y + dy)
        if 0 <= candidate[0] <= world.width - 3 and 0 <= candidate[1] <= world.height - 3:
            pos = candidate
            break
    assert pos is not None
    world.place_building(0, BuildingType.TOWN_HALL, pos)
    _farm_headroom(world)
    world.update_vision()
    world.players[0].gold = 20000
    world.players[0].lumber = 5000
    return world, far


def _run_brain(world, seconds=120):
    brain = Brain(0, Difficulty.MEDIUM)
    rng = random.Random(1)
    for _ in range(int(seconds / SIM_DT)):
        brain.think(world, rng)
        world.step()
    return brain


def _harvests_far(unit, far) -> bool:
    if unit.inside == far.id:
        return True
    return any(isinstance(order, Harvest) and order.target == far.id for order in unit.orders)


def test_a_second_hall_grows_the_workforce_onto_its_own_mine() -> None:
    world, far = _expansion_world()
    brain = _run_brain(world)
    peasants = [u for u in world.player_units(0) if u.is_worker]
    assert len(peasants) > PROFILES[Difficulty.MEDIUM].peasants
    assert any(_harvests_far(unit, far) for unit in peasants)
    assert any("workforce target" in what for _, what in brain.log)


@pytest.mark.slow
def test_one_hall_holds_the_workforce_at_the_profile_value() -> None:
    """Medium needs over four minutes to hire its fourteen peasants one at a time: the slow tier."""
    world = mapgen.generate(seed=5, players=2, human=None)
    _farm_headroom(world)
    world.players[0].gold = 20000
    world.players[0].lumber = 5000
    for mine in world.mines():
        mine.gold = 10 ** 6  # never running low: a second hall would raise the target by five
    _run_brain(world, seconds=260)  # Medium wants fourteen peasants, and a hall makes one at a time
    peasants = [u for u in world.player_units(0) if u.is_worker]
    assert len(peasants) == PROFILES[Difficulty.MEDIUM].peasants


def _military_building(world, player, building_type):
    """A completed production building near the player's first hall."""
    hall = world.player_buildings(player, BuildingType.TOWN_HALL)[0]
    for radius in range(4, 13):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                pos = (hall.x + dx, hall.y + dy)
                if world.can_place(building_type, pos, player) is None:
                    return world.place_building(player, building_type, pos)
    raise AssertionError(f"no room for {building_type}")


def _rich(world, player=0):
    world.players[player].gold = 20000
    world.players[player].lumber = 5000


def test_orc_barracks_trains_grunts_and_elf_barracks_trains_rangers() -> None:
    for race, expected in ((Race.ORC, UnitType.FOOTMAN), (Race.ELF, UnitType.ARCHER)):
        world = mapgen.generate(seed=5, players=2, human=None, races=[race, None])
        _rich(world)
        barracks = _military_building(world, 0, BuildingType.BARRACKS)
        world.update_vision()
        brain = Brain(0, Difficulty.MEDIUM)
        assert brain._choose_unit(world, barracks, {t: 2 for t in UnitType}) is expected, race


def test_human_answers_a_visible_archer_mass_with_cavalry() -> None:
    world = mapgen.generate(seed=5, players=2, human=None, races=[Race.HUMAN, None])
    _rich(world)
    _military_building(world, 0, BuildingType.BARRACKS)
    stables = _military_building(world, 0, BuildingType.STABLES)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for i in range(6):
        world.spawn_unit(1, UnitType.ARCHER, (hall.center[0] + 2, hall.center[1] + i * 0.7))
    world.update_vision()
    brain = Brain(0, Difficulty.MEDIUM)
    assert brain._choose_unit(world, stables, {t: 2 for t in UnitType}) in (UnitType.SCOUT, UnitType.KNIGHT)


def test_dwarf_workshop_starts_siege_with_four_soldiers() -> None:
    for race, soldiers, expected in ((Race.DWARF, 4, UnitType.CATAPULT), (Race.HUMAN, 4, None), (Race.HUMAN, 6, UnitType.CATAPULT)):
        world = mapgen.generate(seed=5, players=2, human=None, races=[race, None])
        _rich(world)
        _military_building(world, 0, BuildingType.BARRACKS)
        _military_building(world, 0, BuildingType.BLACKSMITH)
        workshop = _military_building(world, 0, BuildingType.WORKSHOP)
        world.update_vision()
        brain = Brain(0, Difficulty.MEDIUM)
        counts = {t: 0 for t in UnitType}
        counts[UnitType.FOOTMAN] = soldiers
        assert brain._choose_unit(world, workshop, counts) is expected, (race, soldiers)


def _archer_share(world, player) -> float:
    army = [u for u in world.player_units(player) if not u.is_worker]
    if not army:
        return 0.0
    return sum(1 for u in army if u.type is UnitType.ARCHER) / len(army)


def _trained_archer_share(brain: Brain) -> float:
    """Share of archers among the soldiers the brain trained: what its race plan asked for,
    whatever the fighting since did to the survivors."""
    trained = [what.split("train ", 1)[1] for _, what in brain.log if what.startswith("train ")]
    if not trained:
        return 0.0
    return sum(1 for name in trained if name == UnitType.ARCHER.value) / len(trained)


@pytest.mark.slow
def test_elf_and_orc_armies_grow_towards_their_race_plans() -> None:
    """Each race's brain on the same open ground against a base that trains nothing: what it asks of
    its buildings then follows its plan alone, with no enemy soldiers in sight to counter and no
    losses (a two-brain match once decided this on the survivors of one seeded fight).
    Six minutes of play for each of two races: the slow tier.
    """
    shares = {}
    for race in (Race.ELF, Race.ORC):
        world = mapgen.generate(seed=5, players=2, human=None, races=[race, Race.HUMAN], layout=Layout.PLAINS)
        brain = Brain(0, Difficulty.MEDIUM)
        rng = random.Random(1)
        for _ in range(int(360 / SIM_DT)):
            brain.think(world, rng)
            world.step()
        assert any(f"army plan {race.value}" in what for _, what in brain.log)
        shares[race] = _trained_archer_share(brain)
    assert shares[Race.ELF] > shares[Race.ORC], shares


def _open_world() -> World:
    terrain = [[Terrain.GRASS] * 40 for _ in range(40)]
    return World(40, 40, terrain, 2, human=None, rng=random.Random(3))


def _place_near(world: World, player: int, building_type: BuildingType, anchor) -> None:
    ax, ay = int(anchor[0]), int(anchor[1])
    for radius in range(4, 30):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                pos = (ax + dx, ay + dy)
                if world.can_place(building_type, pos, player) is None:
                    world.place_building(player, building_type, pos)
                    return
    raise AssertionError(f"no room for {building_type}")


def test_a_hard_brain_caps_its_wave_at_what_the_farms_feed() -> None:
    world = _open_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (33, 33))
    world.reveal_all(0)
    for _ in range(3):
        _place_near(world, 0, BuildingType.TOWN_HALL, hall.center)
    for _ in range(5):
        _place_near(world, 0, BuildingType.FARM, hall.center)
    _used, cap = world.supply(0)
    assert cap == 40
    for i in range(14):
        world.spawn_unit(0, UnitType.PEASANT, (hall.center[0] + 0.5 * (i % 4), hall.center[1] + 4 + 0.5 * (i // 4)))
    for i in range(12):
        world.spawn_unit(0, UnitType.FOOTMAN, (hall.center[0] + 0.5 * (i % 4), hall.center[1] + 6 + 0.5 * (i // 4)))
    for i in range(3):
        world.spawn_unit(1, UnitType.PEASANT, (34.5 + 0.5 * i, 37.5))
    world.update_vision()
    brain = Brain(0, Difficulty.MEDIUM)
    brain.wave = 60
    brain.waves_sent = 1
    rng = random.Random(1)
    for _ in range(3):
        brain.think(world, rng)
        world.time += brain.profile.think_every + 0.1
        if brain.attacking:
            break
    assert brain.attacking
    assert any("wave capped at 24" in what for _, what in brain.log)


def test_a_normal_brain_presses_the_attack_against_a_hall_less_enemy() -> None:
    world = _open_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    enemy_hall = world.place_building(1, BuildingType.TOWN_HALL, (33, 33))
    world.reveal_all(0)
    world.reveal_all(1)
    _place_near(world, 1, BuildingType.FARM, enemy_hall.center)
    _place_near(world, 1, BuildingType.FARM, enemy_hall.center)
    world._remove_building(enemy_hall, reason="destroyed")  # staged: a razed hall, without the siege
    for i in range(2):
        world.spawn_unit(1, UnitType.PEASANT, (34.5 + 0.5 * i, 37.5))
    for i in range(5):
        world.spawn_unit(0, UnitType.FOOTMAN, (hall.center[0] + 0.5 * i, hall.center[1] + 4))
    world.update_vision()
    brain = Brain(0, Difficulty.MEDIUM)
    brain.wave = 10
    brain.waves_sent = 1
    rng = random.Random(1)
    for _ in range(3):
        brain.think(world, rng)
        world.time += brain.profile.think_every + 0.1
        if brain.attacking:
            break
    assert brain.attacking  # five soldiers beat the wave of ten while the enemy has no army


def _press_world(difficulty: Difficulty):
    """Five own footmen against an enemy with buildings but no soldiers."""
    world = _open_world()
    hall = world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    enemy_hall = world.place_building(1, BuildingType.TOWN_HALL, (33, 33))
    world.reveal_all(0)
    world.reveal_all(1)
    _place_near(world, 1, BuildingType.FARM, enemy_hall.center)
    _place_near(world, 1, BuildingType.FARM, enemy_hall.center)
    world._remove_building(enemy_hall, reason="destroyed")  # staged: a razed hall, without the siege
    for i in range(2):
        world.spawn_unit(1, UnitType.PEASANT, (34.5 + 0.5 * i, 37.5))
    for i in range(5):
        world.spawn_unit(0, UnitType.FOOTMAN, (hall.center[0] + 0.5 * i, hall.center[1] + 4))
    world.update_vision()
    brain = Brain(0, difficulty)
    brain.wave = 10
    return world, brain


def _attacks(brain: Brain) -> list[str]:
    return [what for _, what in brain.log if "attack with" in what]


def test_an_easy_brain_holds_its_first_wave_until_it_is_full() -> None:
    """Easy is the setting that waits for a full wave; Medium harasses before one."""
    world, brain = _press_world(Difficulty.EASY)
    world.time = brain.profile.first_attack
    rng = random.Random(1)
    for _ in range(3):
        brain.think(world, rng)
        world.time += brain.profile.think_every + 0.1
    assert not brain.attacking
    assert _attacks(brain) == []
    brain.waves_sent = 1
    for _ in range(3):
        brain.think(world, rng)
        world.time += brain.profile.think_every + 0.1
        if brain.attacking:
            break
    assert brain.attacking
    assert _attacks(brain) != []


def test_easy_sends_no_wave_before_minute_eight_however_big_its_army() -> None:
    """WB-014: a plain opening has no soldiers to speak of before minute four; Easy's wave of ten came at four and
    a half and took its peasants too, so the scripted opening in tools/ai_report.py stopped beating Easy."""
    world, brain = _press_world(Difficulty.EASY)
    brain.wave, brain.waves_sent = 3, 1
    rng = random.Random(1)
    while world.time < brain.profile.first_attack - brain.profile.think_every:
        brain.think(world, rng)
        world.time += brain.profile.think_every
    assert not brain.attacking and _attacks(brain) == []
    world.time = brain.profile.first_attack
    brain.think(world, rng)
    assert brain.attacking


def test_a_medium_brain_presses_even_before_its_first_wave() -> None:
    world, brain = _press_world(Difficulty.MEDIUM)
    assert brain.waves_sent == 0
    rng = random.Random(1)
    for _ in range(3):
        brain.think(world, rng)
        world.time += brain.profile.think_every + 0.1
        if brain.attacking:
            break
    assert brain.attacking
    assert _attacks(brain) != []


def test_every_difficulty_has_a_rating_and_a_note_and_they_go_up() -> None:
    """The New game screen shows these numbers, so a setting without one is a bug.

    They are measured by ``tools/arena.py`` and recorded in docs/ai-ladder.md;
    what is pinned here is that each setting is rated, described, and stronger
    than the one before it.
    """
    from warband.brains.ai import DIFFICULTY_ELO, DIFFICULTY_NOTES

    assert set(DIFFICULTY_ELO) == set(Difficulty)
    assert set(DIFFICULTY_NOTES) == set(Difficulty)
    ratings = [DIFFICULTY_ELO[d] for d in Difficulty]
    assert ratings == sorted(ratings) and len(set(ratings)) == len(ratings), ratings
    assert DIFFICULTY_ELO[Difficulty.MEDIUM] == 1000, "Medium is the anchor the ladder is measured against"
    for note in DIFFICULTY_NOTES.values():
        assert 10 < len(note) <= 70, note  # long enough to say something, short enough to fit the panel


def test_every_difficulty_builds_a_brain_that_plays() -> None:
    """Easy and Medium are a Brain, Hard and Master a ProBrain; all four must think."""
    from warband.brains.ai import make_brain

    for difficulty in Difficulty:
        world = mapgen.generate(seed=7, players=2, human=None)
        brain = make_brain(0, difficulty)
        rng = random.Random(1)
        for _ in range(int(60 / SIM_DT)):
            brain.think(world, rng)
            world.step()
        assert len(world.player_units(0)) > 3, difficulty


def test_master_draws_its_posture_from_the_seed_and_the_seat_a_third_each() -> None:
    """WB-036: the tower rush is Master's third posture. Every client of an online match and every replay of a
    seed must agree on who plays which, so the draw depends on the seed and the seat alone; Hard never rushes."""
    from collections import Counter

    from warband.brains.ai import make_brain

    drawn = Counter(make_brain(seat, Difficulty.MASTER, seed).profile.name for seed in range(300) for seat in range(2))
    assert drawn == {"pro-vanguard": 200, "pro-warden": 200, "pro-rush": 200}, drawn
    assert make_brain(1, Difficulty.MASTER, 41).profile is make_brain(1, Difficulty.MASTER, 41).profile
    assert make_brain(0, Difficulty.MASTER, 41).profile is not make_brain(1, Difficulty.MASTER, 41).profile, \
        "two Masters in one game differ"
    assert {make_brain(seat, Difficulty.HARD, seed).profile.name for seed in range(30) for seat in range(4)} == {"pro-hard"}


def test_the_shipped_brain_is_bound_by_the_same_fog_the_player_plays_under() -> None:
    """It may not target, expand towards, or count what it has never seen."""
    from warband.brains.ai import known_enemy_buildings, known_mines

    world = mapgen.generate(seed=31, players=2, human=None)
    world.update_vision()
    brain = Brain(0, Difficulty.MEDIUM)
    enemy_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    world.spawn_unit(1, UnitType.FOOTMAN, (enemy_hall.center[0] + 1, enemy_hall.center[1] + 1))
    world.update_vision()

    assert known_enemy_buildings(world, 0) == []
    assert all(dist(t, enemy_hall.center) > 3.0 for t in brain._enemy_targets(world)), "an unseen hall is not a target"
    assert brain._enemy_soldiers(world) == 0, "an unseen soldier is not counted"
    assert all(dist(m.center, enemy_hall.center) > 12.0 for m in known_mines(world, 0)), \
        "their gold has not been found"

    # Genuine sight, not a revealed map: a scout of ours standing in their base.
    world.spawn_unit(0, UnitType.SCOUT, (enemy_hall.center[0] + 1, enemy_hall.center[1]))
    world.update_vision()
    assert known_enemy_buildings(world, 0), "once looked at, it is known"
    assert brain._enemy_soldiers(world) == 1
    assert any(dist(t, enemy_hall.center) <= 3.0 for t in brain._enemy_targets(world))
