"""The computer players: what a difficulty does with what it has."""

import random

from warband import mapgen
from warband.ai import Brain
from warband.model import Repair
from warband.rules import SIM_DT, BuildingType, Difficulty


def test_normal_and_hard_send_a_peasant_to_mend_a_damaged_building_but_easy_does_not() -> None:
    for difficulty, expected in ((Difficulty.NORMAL, True), (Difficulty.HARD, True), (Difficulty.EASY, False)):
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
