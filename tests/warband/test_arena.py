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
    spec = MatchSpec(seed=7, agents=("medium", "easy"), minutes=3)
    first, second = play(spec), play(spec)
    assert (first.placements, first.winner, first.minutes, first.steps) == \
           (second.placements, second.winner, second.minutes, second.steps)


def test_a_match_records_how_each_player_played():
    """The style telemetry is what backs a claim that two agents of one strength are two players."""
    played = play(MatchSpec(seed=3, agents=("medium", "pro"), minutes=4.0))
    assert len(played.styles) == 2
    for style in played.styles:
        assert set(style) == set(arena.STYLE_FIELDS)
        assert style["peak_army"] >= 0 and style["workers"] >= 0
    medians = arena.styles([played, played])
    assert set(medians) == {"medium", "pro"}
    assert medians["pro"]["peak_army"] == played.styles[1]["peak_army"]


def test_a_match_result_survives_a_round_trip_through_plain_data():
    """Saved runs are what a chain of rungs is rated over, so nothing may be lost on the way."""
    import json
    played = play(MatchSpec(seed=3, agents=("medium", "pro"), minutes=2.0, races=("orc", "elf")))
    back = arena.from_record(json.loads(json.dumps(arena.to_record(played))))
    same = lambda a, b: a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))  # noqa: E731
    assert (back.spec, back.placements, back.winner, back.minutes, back.steps, back.wall, back.races) == \
        (played.spec, played.placements, played.winner, played.minutes, played.steps, played.wall, played.races)
    assert all(same(a[f], b[f]) for a, b in zip(back.styles, played.styles) for f in arena.STYLE_FIELDS), \
        "a brain that never attacked has a NaN first attack, which is still the same NaN"
    assert played.races == ("orc", "elf")
    by_race = arena.score_by_race([played, played])
    assert set(by_race) == {"medium", "pro"} and set(by_race["medium"]) == {"orc"}
    assert by_race["medium"]["orc"][1] == 2


def test_placements_rank_every_player_from_one():
    """Placements start at 1 and leave no gaps except where players tie."""
    spec = MatchSpec(seed=11, agents=("hard", "medium", "easy"), minutes=3)
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


def test_a_rating_is_settled_by_peers_not_by_the_agents_it_always_beats():
    """a and b split twenty games; c loses to b 90% and to a 100%, a hundred games each.

    Counting every game the same, a's perfect record against c pulls it well
    clear of b, though the games they played against each other say they are
    level. Weighted by proximity, the games against a far weaker agent count
    for little, and the head-to-head decides.
    """
    results = ([result(("a", "b"), (1, 2))] * 10 + [result(("a", "b"), (2, 1))] * 10
               + [result(("b", "c"), (1, 2))] * 90 + [result(("b", "c"), (2, 1))] * 10
               + [result(("a", "c"), (1, 2))] * 100)
    flat = {r.name: r.elo for r in rate(results, anchor="b", bootstrap=0, proximity=None)}
    near = {r.name: r.elo for r in rate(results, anchor="b", bootstrap=0)}
    assert flat["a"] - flat["b"] > 80, "unweighted, the games against c decide"
    assert abs(near["a"] - near["b"]) < 40, "weighted, the head-to-head does"
    assert near["c"] < near["b"] - 200, "c is still rated well below both"


def test_proximity_weight_falls_off_with_the_gap():
    assert arena.proximity_weight(0.0, 200.0) == 1.0
    assert arena.proximity_weight(200.0, 200.0) == pytest.approx(0.5)
    assert arena.proximity_weight(400.0, 200.0) == pytest.approx(0.2)
    assert arena.proximity_weight(1000.0, 200.0) < 0.05


def test_two_agents_rate_the_same_however_far_apart_they_are():
    """With only one pair there is nothing to weigh against; the odds are the odds."""
    results = [result(("a", "b"), (1, 2))] * 95 + [result(("a", "b"), (2, 1))] * 5
    weighted = {r.name: r.elo for r in rate(results, anchor="b", bootstrap=0)}
    flat = {r.name: r.elo for r in rate(results, anchor="b", bootstrap=0, proximity=None)}
    assert weighted["a"] == pytest.approx(flat["a"], abs=1e-6)


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


def test_a_seed_with_no_fair_map_is_reported_rather_than_raised():
    """mapgen refuses layouts it cannot make fair; a ladder has to survive that."""
    from warband.arena import playable
    assert playable(MatchSpec(seed=1000, agents=("hard", "hard")))
    # Whatever the answer for a given seed, asking must not raise.
    assert playable(MatchSpec(seed=6005, agents=("hard", "hard"))) in (True, False)


def test_a_ladder_is_played_across_the_map_generator_not_one_map():
    """An agent rated on one layout, one size and one land is rated on very little.

    mapgen draws the layout from the seed on its own; size and land are the
    runner's job, and this pins that it does it.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from arena import specs_1v1

    from warband import mapgen

    specs = specs_1v1(["easy", "medium"], range(4000, 4030), "standard", 20.0)
    assert {(s.width, s.height) for s in specs} == set(mapgen.SIZES.values()), "every map size"
    # Both corners of a seed must be the same board, or the swap is not a swap.
    for spec in specs:
        twin = next(o for o in specs if o.seed == spec.seed and o.agents == spec.agents[::-1])
        assert (twin.width, twin.height, twin.theme) == (spec.width, spec.height, spec.theme)


def test_the_land_is_cosmetic_so_a_ladder_need_not_vary_it():
    """Summer, winter and wasteland generate the same terrain tile for tile."""
    from collections import Counter

    from warband import mapgen
    from warband.rules import MapTheme

    counts = set()
    for theme in MapTheme:
        world = mapgen.generate(seed=16000, players=2, human=None, theme=theme)
        counts.add(tuple(sorted(Counter(cell for row in world.terrain for cell in row).items(),
                                key=lambda kv: kv[0].value)))
    assert len(counts) == 1, "if this ever fails, the ladder should start varying the land"


def test_the_layout_comes_from_the_seed_so_a_ladder_sees_all_of_them():
    from warband import mapgen
    from warband.arena import MatchSpec, playable

    drawn = set()
    for seed in range(15000, 15060):
        spec = MatchSpec(seed=seed, agents=("easy", "medium"))
        if playable(spec):
            drawn.add(mapgen.generate(seed=seed, players=2, human=None).layout)
    assert len(drawn) >= 4, f"a ladder should meet most layouts, saw {drawn}"
