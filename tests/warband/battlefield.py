"""An open field for presentation tests: nothing on it but what a test puts there."""

from warband.model import World
from warband.rules import BuildingType, Terrain

SETTINGS = {"tutorial": False, "music": 0, "sfx": 0, "edge_scroll": False}


def field(players: int = 2) -> World:
    """Open grass, human seats far apart in the corners, so a fight depends on nothing but the blow."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], players)
    for player in world.players:
        player.human = True
    corners = ((1, 1), (34, 25), (34, 1), (1, 25))
    for index in range(players):
        world.place_building(index, BuildingType.TOWN_HALL, corners[index])
    return world
