"""An open field for presentation tests: nothing on it but what a test puts there."""

from warband.sim.model import World
from warband.sim.rules import BuildingType, Terrain

SETTINGS = {"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False}


def field(players: int = 2) -> World:
    """Open grass, human seats far apart in the corners, so a fight depends on nothing but the blow."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], players)
    for player in world.players[:world.seats]:  # never the wilds: that seat is nobody's
        player.human = True
    corners = ((1, 1), (34, 25), (34, 1), (1, 25))
    for index in range(players):
        world.place_building(index, BuildingType.TOWN_HALL, corners[index])
    return world


def live_effects(scene) -> list:
    """The effects a scene is playing now. Saga2D's ``Effects`` counts them but does not list them (0.3.8), so this
    reads its list: the one place the tests read a private member of the engine's."""
    return list(scene.effects._items)
