"""Match stories: unit-steps read as logical actions, battles and a verdict (warband.league.narrate)."""

import json
import math
import random

import pytest

from warband.league.arena import MatchSpec
from warband.league.narrate import FACTOR_FIELDS, Narrator, autopsy, factor_gaps, lead_holds, narrate, render
from warband.sim.model import World
from warband.sim.rules import SIM_DT, BuildingType, Terrain, UnitType


def _fight(seconds: float = 45.0):
    """Two footman groups sent at each other on open grass, narrated: one battle, priced losses."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2, rng=random.Random(3))
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    left = [world.spawn_unit(0, UnitType.FOOTMAN, (14.5, 14.5 + i)).id for i in range(6)]
    right = [world.spawn_unit(1, UnitType.FOOTMAN, (24.5, 14.5 + i)).id for i in range(4)]
    narrator = Narrator(world)
    world.attack_move(left, (24.5, 16.0))
    world.attack_move(right, (14.5, 16.0))
    for _ in range(int(seconds / SIM_DT)):
        world.step()
        narrator.observe(world, world.take_events())
    return world, narrator


def test_a_fight_clusters_into_a_battle_with_priced_losses():
    world, narrator = _fight()
    story = narrator.finish(world, agent_names=("a", "b"))
    assert story.battles, "six footmen against four is a battle"
    battle = max(story.battles, key=lambda b: b.damage)
    assert battle.place == "open ground"
    assert battle.losses_value.get(1, 0) > 0, "the smaller side lost priced soldiers"
    assert sum(battle.deaths.values()) >= 4
    assert battle.net_for(0) > 0, "the bigger group came out ahead on value"
    assert [e.kind for e in story.episodes].count("battle") == len(story.battles)


def test_factors_cover_every_field_and_agree_with_the_tallies():
    world, narrator = _fight()
    story = narrator.finish(world, agent_names=("a", "b"))
    for seat in range(2):
        assert tuple(story.factors[seat]) == FACTOR_FIELDS
        assert story.factors[seat]["losses_value"] >= story.battles[0].losses_value.get(seat, 0)
        assert story.factors[seat]["damage_taken"] > 0
    assert story.factors[0]["net_trade"] > story.factors[1]["net_trade"]
    assert all(len(row) == 2 for row in story.samples)
    assert story.samples[0][0].time == 0.0 <= story.samples[-1][0].time


def test_a_story_renders_and_survives_json():
    world, narrator = _fight(20.0)
    story = narrator.finish(world, agent_names=("a", "b"))
    page = render(story)
    assert "factors:" in page and "battle" in page
    record = json.loads(json.dumps(story.to_record()))
    assert record["agents"] == ["a", "b"] and record["battles"] and record["factors"]


def test_a_short_match_narrates_openings_and_a_verdict():
    story = narrate(MatchSpec(seed=7, agents=("master", "medium"), minutes=3))
    assert {e.kind for e in story.episodes} >= {"opening"}
    assert all(not math.isnan(story.factors[s]["gathered"]) for s in range(2))
    assert story.verdict and story.verdict[0].text
    assert factor_gaps([story])  # undecided: every median is NaN, but the table stands
    assert lead_holds([story], 60.0)[1] == 0
    assert autopsy([story], "master") == ["master lost no decided duel in these stories"]


@pytest.mark.slow
def test_a_decided_match_verdict_names_priced_reasons():
    """A whole settled match: the slow tier (it plays minutes of simulation to a result)."""
    story = narrate(MatchSpec(seed=101, agents=("grandmaster", "easy"), minutes=15))
    assert story.winner is not None, "grandmaster against easy settles"
    assert story.agents[story.winner] == "grandmaster"
    assert story.verdict[0].kind in {"mining", "trade", "supply", "float", "camps", "raid", "tech",
                                     "expansion", "first_clash", "tempo"}
    gaps = factor_gaps([story])
    assert gaps["net_trade"][0] > gaps["net_trade"][1]
    held, n = lead_holds([story], 300.0)
    assert n == 1 and held in (0.0, 1.0)
    assert "lost 1 decided" in autopsy([story], "easy")[0]
