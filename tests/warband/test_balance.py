"""The balance readout: what the league's matches say about the rules.

Properties of the arithmetic, on payoff matrices whose answer is known —
rock-paper-scissors splits three ways, a dominant posture takes everything —
and of the evidence file, which must give back what was written to it.
"""

from __future__ import annotations

import pytest

from warband.balance import equilibrium


def test_rock_paper_scissors_is_played_a_third_each():
    payoff = [[0.5, 0.0, 1.0],
              [1.0, 0.5, 0.0],
              [0.0, 1.0, 0.5]]
    weights = equilibrium(payoff)
    assert sum(weights) == pytest.approx(1.0)
    for w in weights:
        assert w == pytest.approx(1 / 3, abs=0.02)


def test_a_dominant_posture_is_the_whole_meta():
    """Beating everything, even narrowly, leaves the others no share."""
    payoff = [[0.5, 0.6, 0.6],
              [0.4, 0.5, 0.5],
              [0.4, 0.5, 0.5]]
    weights = equilibrium(payoff)
    assert weights[0] == pytest.approx(1.0, abs=0.02)


def _match(agents, winner, tallies, seed=1):
    from warband.arena import MatchResult, MatchSpec
    placements = tuple(1 if i == winner else 2 for i in range(len(agents)))
    return MatchResult(spec=MatchSpec(seed=seed, agents=agents), placements=placements, winner=winner,
                       minutes=10.0, steps=12_000, wall=1.0, tallies=tuple(tallies))


def _tally(race="human", **fields):
    from collections import Counter

    from warband.telemetry import PlayerTally, Sample
    tally = PlayerTally(race=race)
    for name, value in fields.items():
        if name == "timeline":
            tally.timeline = [Sample(**row) for row in value]
        else:
            setattr(tally, name, Counter(value) if isinstance(value, dict) and name != "first" else value)
    return tally


def test_usage_counts_what_was_bought_and_what_it_earned():
    """Two footmen for 1200 that destroyed 800 of value earned 667 per thousand spent, in half the player-games."""
    from warband.balance import usage

    results = [_match(("a", "b"), 0, [
        _tally(trained={"footman": 2}, spent={"footman": 1200}, kill_value={"footman": 800}, lost={"footman": 1},
               first={"footman": 90.0}),
        _tally(),
    ])]
    footman = {row.key: row for row in usage(results)}["footman"]
    assert (footman.player_games, footman.bought_in, footman.bought) == (2, 1, 2)
    assert footman.share == pytest.approx(0.5)
    assert footman.value_per_1000 == pytest.approx(800 / 1200 * 1000)
    assert footman.lost == 1
    assert footman.first == pytest.approx(90.0)


def test_a_posture_is_read_off_its_own_players_only():
    """Unspent bank, supply-blocked time and matches at the cap are averaged over the games a posture played."""
    from warband.balance import postures

    rich = _tally(timeline=[dict(time=0, gold=1000, lumber=500, supply_used=5, supply_cap=9, peasants=5, soldiers=0, army_value=0),
                            dict(time=60, gold=3000, lumber=0, supply_used=9, supply_cap=9, peasants=5, soldiers=4, army_value=2400),
                            dict(time=120, gold=5000, lumber=0, supply_used=9, supply_cap=9, peasants=5, soldiers=2, army_value=1200)])
    poor = _tally(timeline=[dict(time=0, gold=1000, lumber=500, supply_used=5, supply_cap=9, peasants=5, soldiers=0, army_value=0),
                            dict(time=120, gold=100, lumber=50, supply_used=8, supply_cap=13, peasants=5, soldiers=3, army_value=1800)])
    results = [_match(("hoarder", "spender"), 1, [rich, poor]), _match(("spender", "hoarder"), 0, [poor, rich], seed=2)]
    table = {p.name: p for p in postures(results)}
    assert table["hoarder"].games == 2 and table["hoarder"].score == 0.0
    assert table["hoarder"].unspent == pytest.approx(5000)
    assert table["hoarder"].blocked == pytest.approx(2 / 3)
    assert table["hoarder"].peak_army == pytest.approx(2400)
    assert table["spender"].unspent == pytest.approx(150)
    assert table["spender"].blocked == pytest.approx(0.0)


def test_the_evidence_file_gives_back_what_was_written():
    """A played match survives the trip through the JSON lines file unchanged, tallies included."""
    from warband.arena import MatchSpec, play
    from warband.balance import load, save

    played = [play(MatchSpec(seed=7, agents=("pro", "rush"), minutes=2))]
    path = __import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "league.jsonl"
    save(played, path)
    assert load(path) == played
