"""What the pro brain does about a tower on its own ground (WB-037): its peasants go for a lone enemy peasant
walking into the base before it can raise a frame there, and a tower that stands anyway is struck down at once by
the soldiers at home and as many peasants as it takes, rather than left to stop the gold."""

import random
from dataclasses import replace

import pytest

from warband.sim import mapgen
from warband.league.arena import make_agent
from warband.sim.model import World, dist, rect_gap
from warband.brains.pro_ai import PRO_VANGUARD, ProBrain
from warband.sim.rules import BUILDINGS, SIM_DT, BuildingType, Resource, Terrain, UnitType


def base(soldiers: int = 0) -> World:
    """Our hall with eight peasants on its mine, and *soldiers* footmen; the enemy's hall and barracks across the map."""
    world = World(40, 24, [[Terrain.GRASS] * 40 for _ in range(24)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (3, 10))
    world.place_building(None, BuildingType.GOLD_MINE, (9, 10))
    for i in range(8):
        world.spawn_unit(0, UnitType.PEASANT, (8.5 + i % 4, 13.5 + i // 4))  # coming out of the mine's lower face
    for i in range(soldiers):
        world.spawn_unit(0, UnitType.FOOTMAN, (5.5 + i, 14.5))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 10))
    world.place_building(1, BuildingType.BARRACKS, (34, 4))
    world.players[1].gold = world.players[1].lumber = 5000
    world.reveal_all(0)
    world.reveal_all(1)  # it has scouted us
    world.update_vision()
    return world


SITE = (10, 15)  # two tiles below our mine, where our miners see it


def play(world: World, brain: ProBrain, seconds: float) -> None:
    rng = random.Random(1)
    while world.time < seconds:
        brain.think(world, rng)
        world.step()


@pytest.mark.parametrize("party", [PRO_VANGUARD.hunt_party, 0])
def test_a_lone_enemy_peasant_waiting_in_the_base_is_killed_before_it_builds(party: int) -> None:
    """The rush's builder waits behind our mine for its barracks to stand; left alone, it raises its tower."""
    world = base()
    builder = world.spawn_unit(1, UnitType.PEASANT, (12.5, 16.5))
    world.hold([builder.id])
    world.update_vision()
    assert world.is_visible(0, builder.tile)
    brain = ProBrain(0, replace(PRO_VANGUARD, hunt_party=party))
    play(world, brain, 10.0)
    if builder.id in world.units:
        world.build(builder.id, BuildingType.TOWER, SITE)
    play(world, brain, 20.0)
    assert (builder.id not in world.units) == bool(party), [w for _, w in brain.log]
    assert bool(world.player_buildings(1, BuildingType.TOWER)) != bool(party)


@pytest.mark.parametrize("strike", [PRO_VANGUARD.strike_seconds, 0.0])
def test_a_young_frame_the_force_at_hand_can_outpace_is_brought_down_before_it_stands(strike: float) -> None:
    """Eight peasants and two footmen take a point a second each and four each off a frame gaining ten: it falls
    well inside its thirty-five seconds, where left alone it would stand by our mine."""
    world = base(soldiers=2)
    builder = world.spawn_unit(1, UnitType.PEASANT, (12.5, 16.5))
    world.build(builder.id, BuildingType.TOWER, SITE)
    assert world.any_visible(0, (*SITE, 2, 2))
    brain = ProBrain(0, replace(PRO_VANGUARD, hunt_party=0, strike_seconds=strike))
    play(world, brain, 40.0)
    towers = world.player_buildings(1, BuildingType.TOWER)
    assert (not towers) == bool(strike), [w for _, w in brain.log]


def behind(world: World, mine, hall) -> tuple[int, int]:
    """Where tower_freeze.py puts its tower: 1.5 to 3 tiles from the mine, as far from the hall as that allows."""
    size = BUILDINGS[BuildingType.TOWER].size
    best = None
    for y in range(mine.y - 6, mine.y + mine.size + 6):
        for x in range(mine.x - 6, mine.x + mine.size + 6):
            tiles = [(x + dx, y + dy) for dx in range(size) for dy in range(size)]
            if not all(world.in_bounds(t) and world.passable(*t) for t in tiles) or any(u.tile in tiles for u in world.units.values()):
                continue
            centre = (x + size / 2, y + size / 2)
            if 1.5 <= rect_gap(centre, mine.rect) - size / 2 <= 3.0 and (best is None or dist(centre, hall.center) > best[0]):
                best = (dist(centre, hall.center), (x, y))
    assert best is not None
    return best[1]


@pytest.mark.slow
@pytest.mark.parametrize(("posture", "seed"), [("pro-vanguard", 5), ("pro-vanguard", 9), ("pro-warden", 5), ("pro-warden", 9)])
def test_a_tower_placed_by_the_mine_is_struck_down_and_the_gold_comes_back(posture: str, seed: int) -> None:
    """The measurement's placed tower (docs/evidence/tower-rush/tower_freeze.py): before WB-037 it stood for
    minutes, the gold stopped and soldiers died at it one by one. Four minutes of a brain's play: the slow tier."""
    world = mapgen.generate(seed=seed, players=2, human=None)
    brain, rng = make_agent(posture, 0, seed), random.Random(seed)
    tower, lost, gold_after, last_hit = None, 0, 0, {}
    while world.time < 240.0:
        if tower is None and world.time >= 150.0:
            hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
            mine = min(world.mines(), key=lambda m: dist(m.center, hall.center))
            tower = world.place_building(1, BuildingType.TOWER, behind(world, mine, hall))
        brain.think(world, rng)
        world.step()
        for event in world.take_events():
            if event.kind == "hit":
                last_hit[event.other] = event.entity
            elif event.kind == "death" and event.player == 0 and event.text == UnitType.PEASANT.value:
                lost += tower is not None and last_hit.get(event.entity) == tower.id
            elif event.kind == "deposit" and event.player == 0 and event.text == Resource.GOLD.value and world.time >= 210.0:
                gold_after += event.amount
        if tower is not None and tower.id in world.buildings:
            assert world.time < 150.0 + 60.0 + SIM_DT, "the tower still stood a minute on"
    assert lost <= 3, f"the tower killed {lost} peasants"
    assert gold_after > 0, "no gold came in during the last half minute"
