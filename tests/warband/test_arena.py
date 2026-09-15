"""The ladder has to be trustworthy before anything it measures is.

These are properties rather than recorded numbers: a match is reproducible,
a balance variant leaves no trace once restored, and the rating fit recovers
a win rate it was given.  They should survive any rewrite of how matches are
scheduled or how strengths are solved for.
"""

from __future__ import annotations

import math

import pytest

from warband import arena
from warband.arena import MatchResult, MatchSpec, Variant, play, rate
from warband.races import RACES
from warband.rules import BUILDINGS, UNITS, BuildingType, Race, UnitType


def result(agents: tuple[str, ...], placements: tuple[int, ...]) -> MatchResult:
    """A finished match, without playing one: the rating code only reads placements."""
    return MatchResult(spec=MatchSpec(seed=0, agents=agents), placements=placements, winner=None,
                       minutes=1.0, steps=1, wall=0.0)


# -- Matches -------------------------------------------------------------------

def test_match_is_reproducible():
    """The same spec twice gives the same match, or no measurement means anything."""
    spec = MatchSpec(seed=7, agents=("normal", "easy"), minutes=3)
    first, second = play(spec), play(spec)
    assert (first.placements, first.winner, first.minutes, first.steps) == \
           (second.placements, second.winner, second.minutes, second.steps)


def test_placements_rank_every_player_from_one():
    """Placements start at 1 and leave no gaps except where players tie."""
    spec = MatchSpec(seed=11, agents=("hard", "normal", "easy"), minutes=3)
    placements = play(spec).placements
    assert len(placements) == 3
    assert min(placements) == 1
    for place in placements:
        assert 1 <= place <= 3


def test_the_winner_places_first():
    spec = MatchSpec(seed=101, agents=("hard", "easy"), minutes=20)
    outcome = play(spec)
    assert outcome.winner is not None, "hard against easy should decide inside twenty minutes"
    assert outcome.placements[outcome.winner] == 1
    assert outcome.score(outcome.winner, 1 - outcome.winner) == 1.0


def test_rotating_a_spec_keeps_the_same_agents():
    spec = MatchSpec(seed=3, agents=("a", "b", "c"))
    assert sorted(spec.rotated(1).agents) == sorted(spec.agents)
    assert spec.rotated(0).agents == spec.agents
    assert spec.rotated(3).agents == spec.agents


def test_a_side_swap_really_swaps_sides():
    """Rotating a two player match puts each agent in the other corner."""
    spec = MatchSpec(seed=5, agents=("hard", "easy"))
    assert spec.rotated(1).agents == ("easy", "hard")


# -- Balance variants ----------------------------------------------------------

def test_a_variant_changes_the_numbers_every_lookup_sees():
    """Both the race tables the simulation reads and the tables the AI prices from."""
    arena.use_variant("standard")
    base_hp = RACES[Race.HUMAN].units[UnitType.FOOTMAN].hp
    base_cost = BUILDINGS[BuildingType.FARM].cost.gold
    arena.register_variant(Variant("test-double-footmen", units={UnitType.FOOTMAN: {"hp": 2.0}},
                                   buildings={BuildingType.FARM: {"cost_gold": 0.5}}))
    try:
        arena.use_variant("test-double-footmen")
        assert RACES[Race.HUMAN].units[UnitType.FOOTMAN].hp == 2 * base_hp
        assert UNITS[UnitType.FOOTMAN].hp == 2 * base_hp
        assert BUILDINGS[BuildingType.FARM].cost.gold == base_cost // 2
    finally:
        arena.use_variant("standard")
        arena.VARIANTS.pop("test-double-footmen")
    assert RACES[Race.HUMAN].units[UnitType.FOOTMAN].hp == base_hp
    assert BUILDINGS[BuildingType.FARM].cost.gold == base_cost


def test_restoring_a_variant_leaves_no_trace():
    """Every unit and building of every race is exactly what it was.

    Worth being fussy about: a ladder that runs variants in one process would
    otherwise quietly rate agents against a drifting rulebook.
    """
    arena.use_variant("standard")
    before = {(race, t): (i.hp, i.damage, i.cost.gold, i.cost.lumber, i.speed, i.build_time)
              for race, info in RACES.items() for t, i in info.units.items()}
    before_buildings = {(race, t): (i.hp, i.cost.gold, i.cost.lumber, i.build_time)
                        for race, info in RACES.items() for t, i in info.buildings.items()}
    arena.ensure_variant("shuffle-42")
    arena.ensure_variant("shuffle-7")
    arena.use_variant("standard")
    assert {(race, t): (i.hp, i.damage, i.cost.gold, i.cost.lumber, i.speed, i.build_time)
            for race, info in RACES.items() for t, i in info.units.items()} == before
    assert {(race, t): (i.hp, i.cost.gold, i.cost.lumber, i.build_time)
            for race, info in RACES.items() for t, i in info.buildings.items()} == before_buildings


def test_a_shuffled_variant_is_drawn_from_its_seed():
    a, b = arena.shuffled_variant(9), arena.shuffled_variant(9)
    assert a.units[UnitType.KNIGHT] == b.units[UnitType.KNIGHT]
    assert arena.shuffled_variant(10).units[UnitType.KNIGHT] != a.units[UnitType.KNIGHT]


def test_a_shuffled_variant_stays_inside_its_spread():
    variant = arena.shuffled_variant(3, spread=0.25)
    for factors in variant.units.values():
        for value in factors.values():
            assert math.exp(-0.25) <= value <= math.exp(0.25)


# -- Ratings -------------------------------------------------------------------

def test_the_anchor_keeps_its_rating():
    results = [result(("a", "b"), (1, 2))] * 6 + [result(("a", "b"), (2, 1))] * 4
    ratings = {r.name: r for r in rate(results, anchor="b", anchor_elo=1000, bootstrap=0)}
    assert ratings["b"].elo == pytest.approx(1000.0)
    assert ratings["a"].elo > ratings["b"].elo, "a won six of ten"


def test_the_fit_recovers_the_win_rate_it_was_given():
    """Three quarters of the games is about 191 Elo, whatever the anchor."""
    results = [result(("a", "b"), (1, 2))] * 75 + [result(("a", "b"), (2, 1))] * 25
    ratings = {r.name: r for r in rate(results, anchor="b", smoothing=0.0, bootstrap=0)}
    assert ratings["a"].elo - ratings["b"].elo == pytest.approx(arena.elo_gap(0.75), abs=1.0)


def test_rating_order_does_not_change_the_answer():
    """Unlike sequential Elo: the same games in any order give the same ratings."""
    import random
    results = ([result(("a", "b"), (1, 2))] * 9 + [result(("b", "c"), (1, 2))] * 7
               + [result(("a", "c"), (1, 2))] * 12 + [result(("c", "a"), (1, 2))] * 2)
    first = {r.name: round(r.elo, 6) for r in rate(results, anchor="b", bootstrap=0)}
    shuffled = list(results)
    random.Random(4).shuffle(shuffled)
    assert {r.name: round(r.elo, 6) for r in rate(shuffled, anchor="b", bootstrap=0)} == first


def test_a_perfect_record_stays_finite_and_ahead():
    """Smoothing is what keeps an undefeated agent on the table instead of at infinity."""
    results = [result(("a", "b"), (1, 2))] * 40
    ratings = {r.name: r for r in rate(results, anchor="b", bootstrap=0)}
    assert math.isfinite(ratings["a"].elo)
    assert ratings["a"].elo - ratings["b"].elo > 400


def test_more_games_at_the_same_rate_mean_a_bigger_proven_gap():
    """An unbeaten record is worth more the longer it goes on."""
    short = {r.name: r for r in rate([result(("a", "b"), (1, 2))] * 10, anchor="b", bootstrap=0)}
    long = {r.name: r for r in rate([result(("a", "b"), (1, 2))] * 200, anchor="b", bootstrap=0)}
    assert long["a"].elo > short["a"].elo


def test_free_for_all_placements_score_pairwise():
    """A three way game is three head to head results, so one match informs every pair."""
    table = arena.pairwise([result(("a", "b", "c"), (1, 2, 3))])
    assert table[("a", "b")] == 1.0 and table[("a", "c")] == 1.0 and table[("b", "c")] == 1.0
    assert table[("c", "a")] == 0.0


def test_a_tie_counts_a_half_to_each_side():
    table = arena.pairwise([result(("a", "b"), (1, 1))])
    assert table[("a", "b")] == 0.5 and table[("b", "a")] == 0.5


def test_mirror_pairings_are_not_counted():
    """An agent beating itself says nothing about its strength."""
    assert arena.pairwise([result(("a", "a"), (1, 2))]) == {}


def test_a_four_player_game_scores_out_of_its_three_pairings():
    """Regression: a placement in a four player game is three head-to-head results,
    so a winner scored 300% of its matches until the share counted pairings."""
    ratings = {r.name: r for r in rate([result(("a", "b", "c", "d"), (1, 2, 3, 4))], bootstrap=0)}
    assert ratings["a"].pairings == 3
    assert ratings["a"].score == 1.0
    assert ratings["d"].score == 0.0
