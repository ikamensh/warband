"""Combat presentation must survive the complete scene update without changing rules."""
import math

from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.scene import GameScene
from warband.textures import TILE


def duel(game, *, damaging=True):
    """Reproduce the stationary footman fight captured for WB-004."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    attacker = world.spawn_unit(0, UnitType.FOOTMAN, (17.5, 13.5))
    victim = world.spawn_unit(1, UnitType.FOOTMAN, (18.5, 13.5))
    attacker.facing, victim.facing = 0.0, math.pi
    if not damaging:
        attacker.cooldown = 3.0  # Same opponent/target poses; no incoming blow in this window.
    scene = GameScene(world, 0, ranked=False, settings={"tutorial": False, "music": 0, "sfx": 0})
    game.clear_and_push(scene)
    scene.view.set_reveal(True)
    world.attack([attacker.id], victim.id)
    world.hold([victim.id])
    return scene, attacker, victim


def test_actual_melee_contact_displaces_the_drawn_victim(game):
    """Compare the same target motion with/without damage, after the entire frame.

    Reading the sprite after game.tick catches a view overwriting the effect;
    matching the target's own poses prevents its attack animation masking a
    missing hit reaction.
    """
    journeys = []
    for damaging in (False, True):
        scene, attacker, victim = duel(game, damaging=damaging)
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


def test_pause_freezes_the_visible_hit_reaction(game):
    """F3 must freeze the combat body as well as the authoritative clock."""
    scene, attacker, victim = duel(game)
    first_hit(game, victim)
    for _ in range(3):
        game.tick(1 / 60)
    game.backend.inject_key("f3")
    game.tick(1 / 60)
    assert scene.paused
    sprite = scene.view.unit_sprite(victim.id)
    held = (scene.world.tick, sprite.position, sprite.rotation, sprite.image)
    for _ in range(20):
        game.tick(1 / 60)
        assert (scene.world.tick, sprite.position, sprite.rotation, sprite.image) == held


def test_recoil_follows_a_new_move_and_finishes_at_the_current_ground_point(game):
    """A hit cannot pin a new move to its old position or snap back on expiry."""
    scene, attacker, victim = duel(game)
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
