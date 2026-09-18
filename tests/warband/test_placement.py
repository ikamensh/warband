"""World.placeable answers what can_place answers, for every spot of a match in progress."""

from __future__ import annotations

import random

import pytest

from warband import mapgen
from warband.ai import make_brain
from warband.rules import BuildingType, Difficulty


@pytest.mark.parametrize("seed", [5, 11])
def test_placeable_is_can_place_on_every_spot(seed: int) -> None:
    world = mapgen.generate(seed=seed, players=2, human=None)
    brains = [make_brain(0, Difficulty.HARD), make_brain(1, Difficulty.MEDIUM)]
    rng = random.Random(seed)
    spots = [(x, y) for y in range(-2, world.height + 1) for x in range(-2, world.width + 1)]
    checked = 0
    for step in range(2400):  # two minutes: halls, farms and barracks going up, peasants everywhere
        for brain in brains:
            brain.think(world, rng)
        world.step()
        if step % 600 != 599:
            continue
        for player in (0, 1):
            for building_type in BuildingType:
                allowed = [spot for spot in spots if world.can_place(building_type, spot, player) is None]
                assert list(world.placeable(building_type, player, spots)) == allowed
                checked += len(allowed)
    assert checked  # some ground was open, so the comparison had something to agree on
