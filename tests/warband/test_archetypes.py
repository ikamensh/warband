"""The postures the balance league is played between.

An archetype is a ProProfile that plays one way on purpose — knights, siege,
a rush — so that the payoff matrix between them says which ingredients of
the game are worth their price.  These tests pin that each knob really
changes what the brain buys, which is the whole point of having it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from warband.league import arena
from warband.league.arena import MatchSpec, play
from warband.brains.pro_ai import PRO
from warband.sim.rules import Layout, UnitType


def _play(name: str, profile, seed: int = 7, minutes: float = 6, opponent: str = "pro",
          layout: Layout | None = None):
    arena.register_profiles([(name, profile)])
    return play(MatchSpec(seed=seed, agents=(name, opponent), minutes=minutes,
                          layout=layout.value if layout is not None else None)).tallies[0]


@pytest.mark.slow
def test_an_army_plan_decides_what_the_barracks_trains():
    """A plan of archers only turns out archers and no footmen, whatever the race would have done.

    A plan shows only once the barracks turn out soldiers, minutes into a match: the slow tier."""
    tally = _play("test-archers-only", replace(PRO, name="test-archers-only", army_plan={UnitType.ARCHER: 1.0}))
    assert tally.trained["archer"] >= 3
    assert tally.trained["footman"] == 0


@pytest.mark.slow
def test_early_tech_goes_up_before_the_bank_overflows():
    """A knights posture lays its stables inside six minutes; the plain brain waits for saturation.

    Six minutes of play: the slow tier."""
    from warband.sim.rules import BuildingType

    tally = _play("test-stables-early", replace(PRO, name="test-stables-early", early_tech=(BuildingType.STABLES,)))
    assert tally.started["stables"] >= 1


def test_a_brain_raises_the_keep_to_reach_the_tier_behind_it():
    """A funded research order reaches its requested tier through every unnamed prerequisite.

    A completed hall and smith, with no recruiting workers or rival attack,
    isolate prerequisite scheduling from spending and match survival. A battle
    can end before its nominal time cap, so winning it proves no research path.
    """
    import random

    from warband.brains.pro_ai import ProBrain
    from warband.sim.model import World
    from warband.sim.rules import UPGRADES, BuildingType, Race, SIM_DT, Terrain, Upgrade

    profile = replace(PRO, name="test-keep", max_workers=0,
                      early_tech=(BuildingType.BLACKSMITH,), research_order=(Upgrade.BLADES_2,))
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2,
                  scripted=True, races=[Race.DWARF, Race.ORC])
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(0, BuildingType.BLACKSMITH, (8, 4))
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))  # A live army keeps the brain out of worker recovery.
    required = (Upgrade.BLADES_1, Upgrade.KEEP, Upgrade.BLADES_2)
    player = world.players[0]
    player.gold = sum(UPGRADES[upgrade].cost.gold for upgrade in required)
    player.lumber = sum(UPGRADES[upgrade].cost.lumber for upgrade in required)
    deadline = sum(UPGRADES[upgrade].time for upgrade in required) + len(required) * (profile.think_every + SIM_DT)
    brain, rng = ProBrain(0, profile), random.Random(3)
    completed = []
    while world.time < deadline and Upgrade.BLADES_2 not in player.upgrades:
        brain.think(world, rng)
        world.step()
        completed.extend(event.target_type for event in world.take_events() if event.kind == "researched")
    # Neither prerequisite is named by the posture. The requested tier must
    # finish too: buying its gate alone would still leave the upper tree closed.
    assert player.upgrades == set(required)
    assert set(completed) == {upgrade.value for upgrade in required}
    assert completed[-1] == Upgrade.BLADES_2.value
    assert player.gold == player.lumber == 0


@pytest.mark.slow
def test_research_can_be_switched_off_to_price_the_upgrades():
    """With a smith standing, the brain researches; with research off it never does, smith or not.

    Two eight-minute matches: the slow tier."""
    from warband.sim.rules import BuildingType

    smith = replace(PRO, name="test-smith", early_tech=(BuildingType.BLACKSMITH,))
    assert _play("test-smith", smith, minutes=8).researched
    silent = replace(smith, name="test-smith-silent", research=False)
    assert not _play("test-smith-silent", silent, minutes=8).researched


@pytest.mark.slow
def test_early_tech_names_how_many_and_a_strict_plan_stops_the_barracks():
    """Two stables in the list means two stables; a strict plan of knights trains no footman past its share.

    A nine-minute match: the slow tier."""
    from warband.sim.rules import BuildingType

    # Against Easy, so the posture lives long enough to field its plan: against Master it can be
    # dead at five minutes, and then the count says who won rather than what the knobs did. Bastion
    # keeps the main-mine economy fixed while this test prices the plan's two-stables knob. Seed 12
    # banks its knights with margin on either platform's timeline.
    tally = _play("test-two-stables", replace(PRO, name="test-two-stables", barracks_per_hall=1, strict_plan=True,
                                              early_tech=(BuildingType.STABLES, BuildingType.STABLES),
                                              army_plan={UnitType.FOOTMAN: 0.2, UnitType.KNIGHT: 0.8}),
                  minutes=9, opponent="easy", seed=12, layout=Layout.BASTION)
    assert tally.started["stables"] >= 2
    soldiers = tally.trained["footman"] + tally.trained["knight"]
    assert tally.trained["knight"] >= 4
    assert tally.trained["footman"] <= 0.35 * soldiers + 2, dict(tally.trained)
