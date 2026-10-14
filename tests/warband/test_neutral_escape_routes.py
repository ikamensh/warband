"""An escape must reach the safety tile from the unit's actual side of the terrain."""

import json
from pathlib import Path

from tools.fuzz import check_progress
from warband.sim.model import World, dist
from warband.sim.rules import CAMP_WATCH, SIM_DT, Race, Terrain, UnitType


def test_an_escape_from_camp_padding_uses_a_reachable_safety_tile():
    """Windows seed83: knight88 cannot start its route across an intervening tree wall.

    Retain the seed's original64x64 terrain, the CI knight position/order and
    its remembered den. Other actors and AI are unnecessary: the original
    rolling20s oracle fails at(54.5,33.5) with path53,30/52,29/51,29.
    """
    capture = json.loads((Path(__file__).with_name('fixtures') / 'windows_seed83_neutral_escape.json').read_text())
    kinds = {terrain.value[0]: terrain for terrain in Terrain}
    terrain = [[kinds[cell] for cell in row] for row in capture['terrain']]
    saved = World(64, 64, terrain, 2, races=[Race(race) for race in capture['races']], scripted=True).to_dict()
    saved['next_id'] = capture['unit']['id']
    saved['time'], saved['tick'] = capture['time'], capture['tick']
    world = World.from_dict(saved)
    unit = world.spawn_unit(capture['unit']['player'], UnitType(capture['unit']['type']), tuple(capture['unit']['pos']))
    saved = world.to_dict()
    saved['units'][0]['orders'] = [capture['unit']['order']]
    saved['worker_knowledge'][unit.player]['encounters'] = [capture['camp']]
    world = World.from_dict(saved)
    unit = world.units[unit.id]
    origin = unit.pos
    den = tuple(capture['camp'][1])
    stalled = {}
    for tick in range(round(25 / SIM_DT)):
        world.step()
        world.take_events()
        assert dist(unit.pos, den) >= CAMP_WATCH, 'the escape must retain the real camp watch'
        if tick % 20 == 0:
            check_progress(world, stalled)
    assert dist(unit.pos, origin) > 3.0
