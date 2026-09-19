"""The player's rating: estimated from results, kept with the profile, and what leaving a match costs."""

import random
from datetime import datetime, timezone

import pytest

from saga2d import SaveError
from warband.brains.ai import DIFFICULTY_ELO
from warband.sim.model import World
from warband.records.profile import (
    DEVIATION_START, EARLY_EXIT_WEIGHT, RATING_START, MatchResult, Profile, Rating, expected_score, material, rated, standing,
)
from warband.sim.rules import UNDER_ATTACK_COOLDOWN, BuildingType, Difficulty, Terrain, UnitType


def result(run_id: str, outcome: str, difficulty: Difficulty = Difficulty.MEDIUM, *, weight: float = 1.0, seconds: int = 600) -> MatchResult:
    return MatchResult(run_id, datetime.now(timezone.utc).isoformat(), outcome, weight, "", difficulty.value, DIFFICULTY_ELO[difficulty], 1,
                       "human", 48, 40, "summer", "plains", 3, seconds, False)


FRESH = Rating(RATING_START, DEVIATION_START)


def test_a_win_raises_the_rating_and_a_loss_lowers_it_while_both_narrow_the_estimate():
    """Property: results move the rating toward the evidence and every result makes the estimate surer."""
    win = rated(FRESH, 1000, 1.0)
    loss = rated(FRESH, 1000, 0.0)
    assert win.value > FRESH.value > loss.value
    assert win.deviation < FRESH.deviation and loss.deviation < FRESH.deviation
    assert win.value - FRESH.value == pytest.approx(FRESH.value - loss.value), "an even match is symmetric"


def test_beating_a_stronger_opponent_is_worth_more():
    """Property: the same score against a higher rating moves the rating further; expected scores order the same way."""
    assert expected_score(FRESH, DIFFICULTY_ELO[Difficulty.EASY]) > 0.5 > expected_score(FRESH, DIFFICULTY_ELO[Difficulty.MASTER])
    gains = [rated(FRESH, DIFFICULTY_ELO[d], 1.0).value - FRESH.value for d in Difficulty]
    assert gains == sorted(gains) and gains[0] < gains[-1]


def test_a_settled_rating_moves_less_than_a_fresh_one():
    """Property: after many results the deviation is small and one more result barely moves the rating."""
    rating = FRESH
    for _ in range(40):
        rating = rated(rating, 1000, 1.0)
        rating = rated(rating, 1000, 0.0)
    assert rating.deviation < 100 and not rating.provisional
    assert abs(rated(rating, 1000, 1.0).value - rating.value) < abs(rated(FRESH, 1000, 1.0).value - FRESH.value) / 3


def test_an_early_exit_counts_about_a_fifth_of_a_loss():
    """The weighted result moves the rating by roughly the weight's share and narrows the estimate far less."""
    full = rated(FRESH, 1000, 0.0)
    partial = rated(FRESH, 1000, 0.0, EARLY_EXIT_WEIGHT)
    ratio = (FRESH.value - partial.value) / (FRESH.value - full.value)
    assert 0.15 < ratio < 0.35
    assert FRESH.deviation - partial.deviation < (FRESH.deviation - full.deviation) / 3


def test_the_profile_keeps_its_results_and_folds_the_rating_from_them(tmp_path):
    """A recorded result is on disk for the next launch; a second result for the same match replaces the first."""
    profile = Profile.load(tmp_path)
    assert profile.name and profile.rating == FRESH and profile.counts() == {"victories": 0, "defeats": 0, "left": 0}
    change = profile.record(result("m1", "victory", Difficulty.HARD))
    assert change.delta > 0 and not change.replaced and change.before == FRESH
    profile.record(result("m2", "left", weight=EARLY_EXIT_WEIGHT))
    again = Profile.load(tmp_path)
    assert again.rating == profile.rating and [r.run_id for r in again.results] == ["m1", "m2"]
    assert again.counts() == {"victories": 1, "defeats": 0, "left": 1}
    finished = again.record(result("m2", "victory"))
    assert finished.replaced and finished.after.value > again.history()[0].after.value
    assert [c.result.run_id for c in again.history()] == ["m1", "m2"] and again.history()[-1].after == again.rating
    assert Profile.load(tmp_path).counts() == {"victories": 2, "defeats": 0, "left": 0}


def test_renaming_persists_and_an_empty_or_overlong_name_is_refused(tmp_path):
    profile = Profile.load(tmp_path)
    profile.rename("  Ilya the Bold, of a very long name indeed ")
    assert Profile.load(tmp_path).name == "Ilya the Bold, o"
    with pytest.raises(ValueError):
        profile.rename("   ")
    assert Profile.load(tmp_path).name == "Ilya the Bold, o"


def test_a_damaged_profile_is_reported_and_left_alone(tmp_path):
    profile = Profile.load(tmp_path)
    profile.record(result("m1", "defeat"))
    profile.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(SaveError):
        Profile.load(tmp_path)
    assert profile.path.read_text() == "{broken"


def test_a_result_with_impossible_values_is_refused():
    with pytest.raises(ValueError):
        result("m", "draw")
    with pytest.raises(ValueError):
        result("m", "left", weight=0.0)
    with pytest.raises(ValueError):
        result("", "victory")


# -- Standing when leaving --------------------------------------------------------------


def battlefield() -> World:
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 24))
    for i in range(3):
        world.spawn_unit(0, UnitType.PEASANT, (6.5 + i, 6.5))
        world.spawn_unit(1, UnitType.PEASANT, (30.5 + i, 22.5))
    return world


def test_leaving_on_even_terms_with_no_enemy_near_counts_a_fifth_of_a_loss():
    world = battlefield()
    where = standing(world, 0)
    assert where.material == material(world, 1) == where.rival
    assert not where.under_attack and not where.behind
    assert where.weight == EARLY_EXIT_WEIGHT and "no enemy at the gates" in where.reason


def test_leaving_under_attack_or_behind_counts_in_full():
    """An enemy fighter at the gates, a blow landed lately, or less material than the rival: a full loss each."""
    at_the_gates = battlefield()
    at_the_gates.spawn_unit(1, UnitType.FOOTMAN, (8.5, 4.5))
    assert standing(at_the_gates, 0).under_attack and standing(at_the_gates, 0).weight == 1.0
    struck = battlefield()
    struck.time = 100.0
    struck.players[0].last_alert = 100.0 - UNDER_ATTACK_COOLDOWN / 2
    assert standing(struck, 0).under_attack and "under attack" in standing(struck, 0).reason
    struck.time += UNDER_ATTACK_COOLDOWN
    assert not standing(struck, 0).under_attack
    behind = battlefield()
    for _ in range(4):
        behind.spawn_unit(1, UnitType.KNIGHT, (30.5, 20.5))
    where = standing(behind, 0)
    assert where.behind and not where.under_attack and where.weight == 1.0 and "behind in material" in where.reason
    ahead = battlefield()
    for _ in range(4):
        ahead.spawn_unit(0, UnitType.KNIGHT, (6.5, 4.5))
    assert not standing(ahead, 0).behind and standing(ahead, 0).weight == EARLY_EXIT_WEIGHT


def test_material_counts_only_what_stands_finished_and_alive():
    world = battlefield()
    before = material(world, 0)
    world.place_building(0, BuildingType.BARRACKS, (10, 2), done=False)
    assert material(world, 0) == before, "a building site is not material yet"
    barracks = world.place_building(0, BuildingType.BARRACKS, (16, 2))
    world.player_units(0)[0].hp = 0
    peasant = world.unit_info(0, UnitType.PEASANT).cost
    assert material(world, 0) == before + barracks.info.cost.gold + barracks.info.cost.lumber - peasant.gold - peasant.lumber
    assert standing(world, 0).rival == material(world, 1)
    world.players[1].alive = False
    assert standing(world, 0).rival == 0
