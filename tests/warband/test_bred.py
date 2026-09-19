"""The behaviours the genetic search composes, and the table Grandmaster plays from.

Each behaviour is off in ``pro``; these pin what switching it on does, through what the world shows of it (what gets
built, what a player comes to know, who holds an axe), so they survive the numbers being bred again."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from warband.brains.ai import known_mines, make_brain
from warband.brains.bred import BRED
from warband.brains.pro_ai import PRO, PRO_VANGUARD, ProBrain
from warband.sim import mapgen
from warband.sim.model import World
from warband.sim.rules import SIM_DT, BuildingType, Difficulty, Layout, Race


def play(world: World, brain, seconds: float, seed: int = 1) -> None:
    rng = random.Random(seed)
    for _ in range(int(seconds / SIM_DT)):
        brain.think(world, rng)
        world.step()
        world.take_events()


def test_every_race_has_a_posture_and_grandmaster_plays_its_race_s_own() -> None:
    assert set(BRED) == set(Race) and all(BRED[race] for race in Race)
    for race in Race:
        world = mapgen.generate(seed=5, players=2, human=None, races=(race, Race.HUMAN))
        brain = make_brain(0, Difficulty.GRANDMASTER, seed=5)
        play(world, brain, 1.0)
        assert brain.brain.profile in BRED[race], race  # the posture it settled on at its first pass: a bred brain's own question


def test_two_grandmasters_of_one_race_draw_different_postures_where_the_race_has_two() -> None:
    """As Master's are: the map's seed and the seat draw it, so a replay and every client agree, and a mirror differs."""
    race = next(race for race in Race if len(BRED[race]) > 1)
    world = mapgen.generate(seed=6, players=2, human=None, races=(race, race))
    brains = [make_brain(seat, Difficulty.GRANDMASTER, seed=6) for seat in (0, 1)]
    for brain in brains:
        play(world, brain, 0.5)
    assert brains[0].brain.profile is not brains[1].brain.profile


@pytest.mark.slow
def test_an_opening_goes_up_in_its_order_before_anything_but_farms() -> None:
    """Two barracks, then a blacksmith: the mill, which the bank would otherwise buy first for being cheaper, waits.
    Three minutes of a match to see four buildings started, a couple of seconds interpreted: the slow tier."""
    world = mapgen.generate(seed=11, players=2, human=None, races=(Race.HUMAN, Race.HUMAN), layout=Layout.PLAINS)
    brain = ProBrain(0, replace(PRO_VANGUARD, name="opening", opening=(BuildingType.BARRACKS, BuildingType.BARRACKS, BuildingType.BLACKSMITH)))
    play(world, brain, 200.0)
    built = [what.split()[1] for _t, what in brain.log if what.startswith("build ") and "farm" not in what]
    assert built[:3] == ["barracks", "barracks", "blacksmith"], built


@pytest.mark.slow
def test_a_prospector_finds_the_pit_a_brain_that_does_not_scout_never_learns_of() -> None:
    """Klondike holds little gold at home and the rest in the middle. Two minutes of a match each way: the slow tier."""
    known = {}
    for floor in (0, 24000):
        world = mapgen.generate(seed=600003, width=48, height=40, players=2, human=None, races=(Race.ELF, Race.HUMAN), layout=Layout.KLONDIKE)
        brain = ProBrain(0, replace(PRO, name="prospect", scout=False, raid=False, prospect_floor=floor))
        play(world, brain, 120.0)
        known[floor] = len(known_mines(world, 0))
    assert known[0] == 1 and known[24000] > 1, known
