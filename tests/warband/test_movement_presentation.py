"""Movement is continuous between authoritative steps without changing game rules."""
import math
import pytest

from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.textures import TILE, WALK_FRAMES
from warband.scene import GameScene


def walking_scene(game, kind=UnitType.FOOTMAN):
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    world.players[1].human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    walker = world.spawn_unit(0, kind, (10.5, 10.5))
    walker.facing = 0.0
    scene = GameScene(world, 0, ranked=False, settings={"tutorial": False, "music": 0, "sfx": 0})
    game.push(scene)
    world.move([walker.id], (30.5, 10.5))
    return scene, walker


@pytest.mark.parametrize("fps", (30, 60, pytest.param(144, marks=pytest.mark.slow)))
@pytest.mark.parametrize("kind", (UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT))
def test_straight_travel_advances_on_every_display_frame(game, fps, kind):
    """A steady walk must not alternate two frozen frames with a three-frame jump.

    Drive the real fixed-step scene and read the visible sprite, so a model-only
    movement test cannot accidentally pass while the player still sees judder.
    At 144 frames a second the scene's warm-up paints six unit frames in each of the
    288, over two seconds: the slow tier walks at 144, the fast tier at 30 and 60.
    """
    scene, walker = walking_scene(game, kind)
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


def test_click_and_box_selection_follow_the_presented_unit(game):
    """The back edge and a tight box must hit the drawn unit, not its next tick."""
    scene, walker = walking_scene(game)
    for _ in range(15):
        game.tick(1 / 60)
    x, y = scene.view.unit_position(walker)
    assert walker.x > x + 0.05, "Exercise a visible offset between model and sprite"
    scene.click_select((x - walker.radius - 0.3, y), shift=False)
    assert scene.selection == [walker.id]
    scene.select([])
    scene.box_select((x - 0.02, y - 0.02), (x + 0.02, y + 0.02), shift=False)
    assert scene.selection == [walker.id]


def test_replay_motion_is_smooth_pauses_and_reaches_the_recorded_end(game):
    """A recording uses the same presentation clock while retaining its exact result."""
    from warband.replay import Replay
    from warband.replay_scene import ReplayScene

    scene, walker = walking_scene(game)
    replay = Replay.begin(scene.world, seed=0, difficulty=scene.difficulty, human=0)
    for _ in range(100):
        scene.world.step()
        scene.world.take_events()
    replay.finish(scene.world, "left")
    player = ReplayScene(replay, settings={"music": 0, "sfx": 0})
    game.clear_and_push(player)
    positions = []
    for frame in range(90):
        game.tick(1 / 60)
        if frame >= 30:
            positions.append(player.view.unit_sprite(walker.id).position)
    assert all(a != b for a, b in zip(positions, positions[1:])), "Replay movement still updates only on model ticks"
    game.backend.inject_key("f3")
    game.tick(1 / 60)
    sprite = player.view.unit_sprite(walker.id)
    held = (sprite.position, sprite.image, player.world.tick)
    for _ in range(12):
        game.tick(1 / 60)
        assert (sprite.position, sprite.image, player.world.tick) == held
    game.backend.inject_key("end")
    game.tick(1 / 60)
    assert player.playback.done and player.playback.faithful
    unit = player.world.units[walker.id]
    assert player.view.unit_position(unit) == pytest.approx(unit.pos), "End screen must show the final positions"


@pytest.mark.parametrize("command", ("command_attack", "command_smart"))
def test_attack_orders_target_the_unit_under_the_presented_pointer(game, command):
    """Both attack-click and right-click must keep a moving enemy's identity."""
    from warband.model import Attack

    scene, walker = walking_scene(game)
    target = scene.world.spawn_unit(1, UnitType.KNIGHT, (13.5, 10.5))
    scene.world.move([target.id], (30.5, 10.5))
    for _ in range(15):
        game.tick(1 / 60)
    scene.select([walker.id])
    x, y = scene.view.unit_position(target)
    getattr(scene, command)((x - target.radius - 0.3, y))
    assert isinstance(walker.order, Attack) and walker.order.target == target.id


def test_loading_a_save_restarts_the_same_motion_without_old_frame_time(game):
    """Repeated loads start identically regardless of the previous fractional tick."""
    scene, walker = walking_scene(game)
    state = scene.get_save_state()
    sequences = []
    for leftover in (0.0, 0.013):
        game.tick(leftover)
        game.scene.load_save_state(state)
        sequence = []
        for _ in range(9):
            game.tick(1 / 60)
            sprite = game.scene.view.unit_sprite(walker.id)
            sequence.append((sprite.position, sprite.image))
        sequences.append(sequence)
    assert sequences[0] == sequences[1], "Loaded motion depends on time left over from the previous world"


def test_right_click_ahead_of_a_moving_enemy_orders_empty_ground(game):
    import json
    from warband.model import Move
    from warband.replay import Playback, Replay

    scene, walker = walking_scene(game)
    target = scene.world.spawn_unit(1, UnitType.KNIGHT, (13.5, 10.5))
    scene.world.move([target.id], (30.5, 10.5))
    for _ in range(15):
        game.tick(1 / 60)
    scene.select([walker.id])
    x, y = scene.view.unit_position(target)
    point = (x + target.radius + 0.36, y)
    assert scene.view.entity_at(point) is None
    assert scene.world.entity_at(point, visible_to=0) is target
    replay = Replay.begin(scene.world, seed=0, difficulty=scene.difficulty, human=0)
    scene.command_smart(point)
    assert isinstance(walker.order, Move) and walker.order.target == point
    for _ in range(60):
        game.tick(1 / 60)
    replay.finish(scene.world, "left")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    playback.run()
    assert playback.faithful
