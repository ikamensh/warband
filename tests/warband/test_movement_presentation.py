"""Movement is continuous between authoritative steps without changing game rules."""
import math
import pytest

from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.textures import TILE, WALK_FRAMES
from warband.scene import GameScene


@pytest.mark.parametrize("fps", (30, 60, 144))
@pytest.mark.parametrize("kind", (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT))
def test_straight_travel_advances_on_every_display_frame(game, fps, kind):
    """A steady walk must not alternate two frozen frames with a three-frame jump.

    Drive the real fixed-step scene and read the visible sprite, so a model-only
    movement test cannot accidentally pass while the player still sees judder.
    """
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    world.players[1].human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    walker = world.spawn_unit(0, kind, (10.5, 10.5))
    walker.facing = 0.0
    scene = GameScene(world, 0, ranked=False, settings={"tutorial": False, "music": 0, "sfx": 0})
    game.push(scene)
    world.move([walker.id], (30.5, 10.5))
    positions = []
    poses = set()
    for frame in range(fps * 2):
        game.tick(1 / fps)
        if frame >= fps // 2:
            sprite = scene.view.unit_sprite(walker.id)
            positions.append(sprite.position)
            poses.add(sprite.image.rsplit(".", 1)[-1])
    distances = [math.dist(a, b) for a, b in zip(positions, positions[1:])]
    assert min(distances) > 0, f"Steady travel froze on {sum(d == 0 for d in distances)} of {len(distances)} intervals"
    assert max(distances) <= walker.info.speed * TILE / fps + 1e-6, "Presentation must not collect several frames into a jump"
    assert walker.x > 13.0, "The fixture must actually travel, not walk against an obstruction"
    assert poses == set(WALK_FRAMES), "Actual travel must exercise the complete walk cycle"
