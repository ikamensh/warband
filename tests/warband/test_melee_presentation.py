"""Combat presentation must survive the complete scene update without changing rules."""
import math

import pytest

from warband.art import textures
from warband.sim.model import World
from warband.sim.rules import BuildingType, Race, Resource, SIM_DT, Terrain, UnitType
from warband.ui.scene import GameScene
from warband.art.textures import TILE
from warband.art.visual_lint import ImageStore, alpha


def diagonal(first: list, second: list) -> list:
    """Every pairing of *first* with *second*. The fast tier takes one of *first* for each of *second*, a different
    one each time, so each still appears there; the slow tier takes the rest."""
    return [pytest.param(a, b, id=f"{b.value}-{a.value}", marks=() if i == j % len(first) else pytest.mark.slow)
            for j, b in enumerate(second) for i, a in enumerate(first)]


@pytest.mark.parametrize("race, resource", diagonal(list(Race), [Resource.GOLD, Resource.LUMBER]))
def test_worker_puts_cargo_away_for_combat_then_delivers_the_same_load(game, race, resource):
    """A harvested load must survive drawing the axe, stopping and returning to work.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_melee_trail_keeps_its_whole_arc_inside_the_image_in_every_facing(game, race, unit_type):
    """Rear-facing cuts rise farther than the original fixed square allowed.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_actual_melee_contact_displaces_the_drawn_victim(game, race, unit_type):
    """Compare the same target motion with/without damage, after the entire frame.

    Reading the sprite after game.tick catches a view overwriting the effect;
    matching the target's own poses prevents its attack animation masking a
    missing hit reaction.
    Every race's art is the slow tier's; the fast tier draws one race per case.
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_melee_loads_back_then_drives_forward_without_moving_its_ground_point(game, race, unit_type):
    """Anticipation and follow-through must carry visible weight at gameplay size.

    Stop before the opponent's counter-hit: incoming recoil cannot satisfy this
    property. The drawn weight shift must not move the authoritative unit.
    Every race's art is the slow tier's; the fast tier draws one race per case.
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_pause_freezes_the_visible_hit_reaction(game, race, unit_type):
    """F3 must freeze the combat body as well as the authoritative clock.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_cancelled_windup_does_not_leave_a_cut_or_impact(game, race, unit_type):
    """Moving away cancels the load-up; no predicted contact may leak into a frame.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_a_released_miss_draws_the_cut_but_does_not_shove_the_target(game, race, unit_type):
    """A target outside reach can escape a committed swing; a trail is not a hit.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("race, unit_type", diagonal(list(Race), [UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT]))
def test_recoil_follows_a_new_move_and_finishes_at_the_current_ground_point(game, race, unit_type):
    """A hit cannot pin a new move to its old position or snap back on expiry.
    Every race's art is the slow tier's; the fast tier draws one race per case."""
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


@pytest.mark.parametrize("unit_type", [UnitType.PEASANT, UnitType.FOOTMAN, UnitType.SCOUT, UnitType.KNIGHT])
def test_changing_target_during_windup_cannot_hit_the_cancelled_target(game, unit_type):
    """A new focus-fire order must redirect both the attack and its visible contact."""
    scene, attacker, abandoned = duel(game, unit_type=unit_type)
    replacement = scene.world.spawn_unit(1, UnitType.PEASANT, (attacker.x, attacker.y + 1))
    scene.world.hold([replacement.id])
    for _ in range(6):
        game.tick(1 / 60)
    assert attacker.windup > 0 and abandoned.hp == abandoned.max_hp
    scene.world.attack([attacker.id], replacement.id)
    for _ in range(120):
        game.tick(1 / 60)
        assert abandoned.hp == abandoned.max_hp
        assert scene.view.unit_sprite(abandoned.id).rotation == 0
        if replacement.hp < replacement.max_hp:
            break
    assert replacement.hp < replacement.max_hp, "The new target must actually be struck"
    assert abs(scene.view.unit_sprite(replacement.id).rotation) > 0, "Only the new target reacts to contact"


def test_a_target_removed_during_windup_leaves_no_phantom_contact(game):
    """A target killed by something else must disappear without a later melee impact."""
    scene, attacker, victim = duel(game, unit_type=UnitType.KNIGHT)
    for _ in range(6):
        game.tick(1 / 60)
    assert attacker.windup > 0
    victim.hp = 0  # Another attack killed it before this committed swing could land.
    game.tick(SIM_DT)
    assert scene.world.entity(victim.id) is None
    for _ in range(45):
        game.tick(1 / 60)
        assert scene.view.unit_sprite(victim.id) is None
        assert not world_marks(game), "No released cut should survive the vanished target"
    assert not any(sound.startswith("lance_") for sound in scene.recent_sounds)


def test_fog_reveal_does_not_restore_a_hidden_hit_reaction(game):
    """Hiding an enemy discards its visible reaction, even if revealed immediately."""
    scene, attacker, victim = duel(game)
    first_hit(game, victim)
    scene.world.hold([attacker.id, victim.id])
    sprite = scene.view.unit_sprite(victim.id)
    assert sprite.visible and abs(sprite.rotation) > 0
    scene.paused = True  # Keep the same combat instant across both visibility changes.
    scene.view.set_reveal(False)
    scene.world.visible[scene.human][:] = bytes(len(scene.world.visible[scene.human]))
    game.tick(1 / 60)
    assert not sprite.visible
    assert not world_marks(game), "Hidden combat cannot leak a weapon trail"
    scene.view.set_reveal(True)
    game.tick(1 / 60)
    assert sprite.visible and sprite.rotation == 0
    assert sprite.position == (victim.x * TILE, victim.y * TILE + textures.placements[sprite.image].drop)


def test_loading_a_save_during_contact_discards_the_old_drawn_offset(game):
    """Transient recoil must not be serialized or restored onto a replacement world."""
    scene, attacker, victim = duel(game, unit_type=UnitType.KNIGHT)
    first_hit(game, victim)
    scene.world.hold([attacker.id, victim.id])
    assert abs(scene.view.unit_sprite(victim.id).rotation) > 0
    scene.paused = True
    scene.save_to("contact")
    saved = scene.world.to_dict()
    scene.load_from("contact")
    game.tick(1 / 60)
    scene = game.scene  # a load is a new match scene
    assert scene.world.to_dict() == saved
    restored = scene.world.units[victim.id]
    sprite = scene.view.unit_sprite(restored.id)
    assert sprite.rotation == 0
    assert sprite.position == (restored.x * TILE, restored.y * TILE + textures.placements[sprite.image].drop)


@pytest.mark.slow
@pytest.mark.parametrize("faster", [False, True])
def test_recorded_contact_survives_replay_speed_and_pause(game, faster):
    """A rendered replay must reproduce the fight, react to hits and freeze on pause.

    A fight recorded and then watched back frame by frame, about two seconds: the slow tier. The fast tier's
    replay scene tests watch a whole match back."""
    from warband.records.replay import Replay
    from warband.ui.replay_scene import ReplayScene

    scene, attacker, victim = duel(game, unit_type=UnitType.KNIGHT)
    replay = Replay.begin(scene.world, seed=scene.seed, difficulty=scene.difficulty, human=scene.human)
    scene.world.attack([attacker.id], victim.id)
    for _ in range(30):  # the fight is recorded in tenths; the replay is watched frame by frame
        game.tick(0.1)
    replay.finish(scene.world, "left")
    assert victim.hp < victim.max_hp
    watching = ReplayScene(Replay.from_dict(replay.to_dict()), settings={"music": 0, "sfx": 0, "tutorial": False})
    game.clear_and_push(watching)
    if faster:
        watching.faster()
        watching.faster()
    saw_contact = False
    previous_hp = watching.world.units[victim.id].hp
    for _ in range(240):
        game.tick(1 / 60)
        target = watching.world.units[victim.id]
        if target.hp < previous_hp and not saw_contact:
            sprite = watching.view.unit_sprite(target.id)
            assert abs(sprite.rotation) > 0
            game.backend.inject_key("f3")
            game.tick(1 / 60)
            held = watching.world.tick, sprite.position, sprite.rotation, sprite.image
            for _ in range(12):
                game.tick(1 / 60)
                assert (watching.world.tick, sprite.position, sprite.rotation, sprite.image) == held
            game.backend.inject_key("f3")
            game.tick(1 / 60)
            saw_contact = True
        previous_hp = target.hp
        if watching.playback.done:
            break
    assert saw_contact
    assert watching.playback.done and watching.playback.faithful
