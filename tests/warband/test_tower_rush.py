"""The tower rush (WB-036): a peasant walks towards the far side of the enemy's main mine as the first barracks goes
up and raises a tower beside it the moment it stands, as far round from their hall as the ground allows, and the
brain holds the tower's price while the peasant walks."""

import random

import pytest

from warband.sim import mapgen
from warband.sim.model import dist, rect_gap
from warband.brains.pro_ai import PRO_RUSH, ProBrain
from warband.sim.rules import BUILDINGS, BuildingType


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 3, 5])
def test_the_rush_raises_a_tower_behind_the_enemy_mine_and_its_order_is_paid(seed: int) -> None:
    """Against an opponent that does nothing, so the mechanism is what is tested, not the fight. Three minutes of a
    brain's play: the slow tier."""
    world = mapgen.generate(seed=seed, players=2, human=None)
    brain, rng = ProBrain(0, PRO_RUSH), random.Random(seed)
    their_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    their_mine = min(world.mines(), key=lambda m: dist(m.center, their_hall.center))
    price = BUILDINGS[BuildingType.TOWER].cost
    refused, rushers = [], set()
    while world.time < 180:
        bank = world.players[0]
        before = (bank.gold, bank.lumber)
        brain.think(world, rng)
        rushers.update(brain.rushers)
        walking = [world.units[i] for i in brain.rushers if i in world.units and world.units[i].constructing is None]
        if walking and before[0] >= price.gold and before[1] >= price.lumber:
            assert bank.gold >= price.gold and bank.lumber >= price.lumber, "the brain spent a walking rusher's price"
        world.step()
        refused += [event.text for event in world.take_events() if event.kind == "refused" and event.entity in rushers]
    towers = [b for b in world.player_buildings(0, BuildingType.TOWER) if rect_gap(b.center, their_mine.rect) <= 4.5]
    assert towers, f"no rush tower by three minutes: {[w for _, w in brain.log if w.startswith('rush')]}"
    assert not refused, refused
