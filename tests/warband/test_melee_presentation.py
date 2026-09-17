"""Combat presentation must survive the complete scene update without changing rules."""
import math

import pytest

from warband import textures
from warband.model import World
from warband.rules import BuildingType, Race, Resource, SIM_DT, Terrain, UnitType
from warband.scene import GameScene
from warband.textures import TILE
from warband.visual_lint import ImageStore, alpha


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("resource", [Resource.GOLD, Resource.LUMBER])
def test_worker_puts_cargo_away_for_combat_then_delivers_the_same_load(game, race, resource):
    """A harvested load must survive drawing the axe, stopping and returning to work."""
    terrain = [[Terrain.GRASS] * 24 for _ in range(18)]
    terrain[8][5] = Terrain.TREES
    world = World(24, 18, terrain, 2)
    for player in world.players:
        player.human, player.race = True, race
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (19, 13))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (7, 3))
    worker = world.spawn_unit(0, UnitType.PEASANT, (5.5, 6.5))
    world.update_vision()
    world.harvest([worker.id], mine.id if resource is Resource.GOLD else (5, 8))
    for _ in range(600):
        world.step()
        if worker.carrying is not None and not worker.hidden:
            break
    payload = worker.carry
    assert worker.carrying is resource and payload > 0, "Exercise a real harvested load"
    world.move([worker.id], (12.5, 10.5))
    for _ in range(200):
        world.step()
        if math.dist(worker.pos, (12.5, 10.5)) < .1:
            break
    assert math.dist(worker.pos, (12.5, 10.5)) < .1
    world.hold([worker.id])
    victim = world.spawn_unit(1, UnitType.PEASANT, (13.5, 10.5))
    world.hold([victim.id])
    scene = GameScene(world, 0, ranked=False, settings={"tutorial": False, "music": 0, "sfx": 0})
    game.clear_and_push(scene)
    scene.view.set_reveal(True)

    def assert_cargo_pose(carrying, frame):
        sprite = scene.view.unit_sprite(worker.id)
        expected = textures.unit_image(game, worker.type, worker.player, textures.facing_index(worker.facing),
                                       frame, carrying, race=race)
        assert sprite.image == expected

    game.tick(SIM_DT)
    assert_cargo_pose(resource, "stand")
    world.attack([worker.id], victim.id)
    for _ in range(20):
        game.tick(SIM_DT)
        if worker.windup > 0:
            break
    assert worker.windup > 0
    assert_cargo_pose(None, "wind")
    first_hit(game, victim)
    assert (worker.carrying, worker.carry) == (resource, payload)
    world.stop([worker.id])
    game.tick(SIM_DT)
    assert_cargo_pose(resource, "stand")
    balance = getattr(world.players[0], resource.value)
    world.harvest([worker.id], mine.id)  # A laden worker delivers before gathering again.
    for _ in range(600):
        game.tick(SIM_DT)
        if worker.carrying is None:
            break
    assert worker.carrying is None and worker.carry == 0
    assert getattr(world.players[0], resource.value) == balance + payload


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_melee_trail_keeps_its_whole_arc_inside_the_image_in_every_facing(game, race, unit_type):
    """Rear-facing cuts rise farther than the original fixed square allowed."""
    store = ImageStore(game)
    for facing in range(8):
        pixels = alpha(store.image(textures.melee_trail_image(game, unit_type, facing, race)))
        assert pixels.max() > 100, f"The trail vanished in facing {facing}"
        for edge in (pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]):
            assert edge.max() < 8, f"The trail is clipped in facing {facing}"


def world_marks(game):
    """Immediate world drawings in this bare duel, independent of their primitive."""
    return [(kind, mark) for kind in ("images", "polygons", "lines")
            for mark in getattr(game.backend, kind) if mark["space"] == "world"]


def duel(game, *, damaging=True, race=Race.HUMAN, unit_type=UnitType.FOOTMAN):
    """Reproduce the stationary melee fight captured for WB-004."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    for player in world.players:
        player.human = True
        player.race = race
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    attacker = world.spawn_unit(0, unit_type, (17.5, 13.5))
    victim = world.spawn_unit(1, unit_type, (18.5, 13.5))
    attacker.facing, victim.facing = 0.0, math.pi
    if not damaging:
        attacker.cooldown = attacker.info.cooldown  # Same target poses; no incoming blow in this window.
    scene = GameScene(world, 0, ranked=False, settings={"tutorial": False, "music": 0, "sfx": 0})
    game.clear_and_push(scene)
    scene.view.set_reveal(True)
    world.attack([attacker.id], victim.id)
    world.hold([victim.id])
    return scene, attacker, victim


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_actual_melee_contact_displaces_the_drawn_victim(game, race, unit_type):
    """Compare the same target motion with/without damage, after the entire frame.

    Reading the sprite after game.tick catches a view overwriting the effect;
    matching the target's own poses prevents its attack animation masking a
    missing hit reaction.
    """
    journeys = []
    for damaging in (False, True):
        scene, attacker, victim = duel(game, damaging=damaging, race=race, unit_type=unit_type)
        frames = []
        for _ in range(30):
            game.tick(1 / 60)
            sprite = scene.view.unit_sprite(victim.id)
            frames.append((victim.hp, victim.pos, sprite.position))
        journeys.append(frames)
    control, hit = journeys
    assert hit[-1][0] < control[-1][0], "The fixture must deliver actual damage"
    assert all(a[1] == b[1] == (18.5, 13.5) for a, b in zip(control, hit))
    assert max(math.dist(a[2], b[2]) for a, b in zip(control, hit)) > 0.5, "Damaging hits have no drawn recoil"


def first_hit(game, victim):
    initial_hp = victim.hp
    for _ in range(90):
        game.tick(1 / 60)
        if victim.hp < initial_hp:
            return
    raise AssertionError("The duel did not produce a damaging hit")


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_melee_loads_back_then_drives_forward_without_moving_its_ground_point(game, race, unit_type):
    """Anticipation and follow-through must carry visible weight at gameplay size.

    Stop before the opponent's counter-hit: incoming recoil cannot satisfy this
    property. The drawn weight shift must not move the authoritative unit.
    """
    scene, attacker, victim = duel(game, race=race, unit_type=unit_type)
    initial_hp = attacker.hp
    wind, contact = [], []
    for _ in range(28):
        game.tick(1 / 60)
        assert attacker.pos == (17.5, 13.5)
        assert attacker.hp == initial_hp
        offset = scene.view.unit_sprite(attacker.id).x - attacker.x * TILE
        if attacker.windup > 0:
            wind.append(offset)
        elif victim.hp < victim.max_hp:
            contact.append(offset)
    assert min(wind) < -1.0, "The body never loads back for the swing"
    assert max(contact) > 1.0, "The body never drives through contact"
    assert all(abs(offset) < attacker.radius * TILE for offset in wind + contact)


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_pause_freezes_the_visible_hit_reaction(game, race, unit_type):
    """F3 must freeze the combat body as well as the authoritative clock."""
    scene, attacker, victim = duel(game, race=race, unit_type=unit_type)
    first_hit(game, victim)
    for _ in range(3):
        game.tick(1 / 60)
    game.backend.inject_key("f3")
    game.tick(1 / 60)
    assert scene.paused
    sprite = scene.view.unit_sprite(victim.id)
    held = (scene.world.tick, sprite.position, sprite.rotation, sprite.image)
    trails = world_marks(game)
    assert trails, "Exercise a released weapon cut as well as the body's recoil"
    for _ in range(20):
        game.tick(1 / 60)
        assert (scene.world.tick, sprite.position, sprite.rotation, sprite.image) == held
        assert world_marks(game) == trails


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_cancelled_windup_does_not_leave_a_cut_or_impact(game, race, unit_type):
    """Moving away cancels the load-up; no predicted contact may leak into a frame."""
    scene, attacker, victim = duel(game, race=race, unit_type=unit_type)
    for _ in range(9):
        game.tick(1 / 60)
    assert attacker.windup > 0
    initial_hp = victim.hp
    scene.world.move([attacker.id], (5.5, attacker.y))
    scene.world.move([victim.id], (30.5, victim.y))
    for _ in range(45):
        game.tick(1 / 60)
        assert victim.hp == initial_hp
        assert not world_marks(game)
        sprite = scene.view.unit_sprite(attacker.id)
        assert sprite.rotation == 0
        assert sprite.x == scene.view.unit_position(attacker)[0] * TILE


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_a_released_miss_draws_the_cut_but_does_not_shove_the_target(game, race, unit_type):
    """A target outside reach can escape a committed swing; a trail is not a hit."""
    scene, attacker, victim = duel(game, race=race, unit_type=unit_type)
    for _ in range(6):
        game.tick(1 / 60)
    assert attacker.windup > 0
    # Reproduce the model's missed-windup regression through the actual scene.
    victim.x += 4.0
    scene.world.move([victim.id], (30.5, victim.y))
    cut_seen = False
    for _ in range(30):
        game.tick(1 / 60)
        assert victim.hp == victim.max_hp
        sprite = scene.view.unit_sprite(victim.id)
        assert sprite.x == scene.view.unit_position(victim)[0] * TILE
        assert sprite.rotation == 0
        cut_seen |= bool(world_marks(game))
    assert cut_seen, "The committed miss must still release its swing"


@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("unit_type", [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT])
def test_recoil_follows_a_new_move_and_finishes_at_the_current_ground_point(game, race, unit_type):
    """A hit cannot pin a new move to its old position or snap back on expiry."""
    scene, attacker, victim = duel(game, race=race, unit_type=unit_type)
    first_hit(game, victim)
    start = victim.pos
    scene.world.move([victim.id], (30.5, victim.y))
    for _ in range(30):
        game.tick(1 / 60)
        sprite = scene.view.unit_sprite(victim.id)
        ground = scene.view.unit_position(victim)
        assert abs(sprite.x - ground[0] * TILE) < victim.radius * TILE, "Reaction left the moving body behind"
    assert victim.x > start[0] + 0.5, "Exercise actual travel during recovery"
    assert sprite.x == ground[0] * TILE, "Expired recoil must leave no displacement"
    assert sprite.rotation == 0.0
