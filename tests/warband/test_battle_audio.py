"""Audio feedback exercised through real simulation steps and the game scene."""

import random

import pytest

from saga2d import Game
from warband.audio import deaths, sound
from warband.sim.model import Deposit, World
from warband.sim.rules import BUILDINGS, SIM_DT, UNITS, BuildingType, Race, Resource, Terrain, UnitType, Upgrade
from warband.ui.scene import GameScene
from warband.ui.view import to_world


def tick_until(game, condition, max_seconds: float = 4.0) -> None:
    """Blows take a turn, a wind-up and a flight now: tick in small steps until *condition* holds."""
    for _ in range(int(max_seconds / 0.1)):
        if condition():
            return
        game.tick(0.1)
    assert condition(), f"not reached within {max_seconds}s"


@pytest.fixture(scope="module")
def audio_files(tmp_path_factory):
    """A battle's sounds as the game writes them, by its bank on first use; the bank composes no track unasked."""
    root = tmp_path_factory.mktemp("battle-audio")
    game = Game("Battle audio", backend="mock")
    try:
        sound.SoundBank(game, root)
    finally:
        game.close()
    return root


@pytest.fixture
def battle(tmp_path, audio_files, monkeypatch):
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    game = Game("Battle audio", backend="mock", save_dir=tmp_path / "saves")
    bank = sound.SoundBank(game, audio_files)
    monkeypatch.setattr(sound, "sound_hook", bank.play)
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    yield game, scene, world
    game.close()


def test_automatic_gold_deliveries_do_not_ring(battle):
    """Repeated harvesting should grow the treasury without notification jingles."""
    game, scene, world = battle
    worker = world.spawn_unit(0, UnitType.PEASANT, (7.5, 5.5))
    before = world.players[0].gold
    for _ in range(4):
        worker.carrying, worker.carry = Resource.GOLD, 100
        worker.orders.append(Deposit())
        game.tick(0.1)
    assert world.players[0].gold == before + 400
    assert not scene.recent_sounds


#: Everything the rules give a blow.  The matrix below walks these, not a list of its own, so whatever gains a blow
#: strikes in a live scene before it ships: WB-051 armed the cleric, and its first blow in view ended the match.
STRIKERS = [kind for kind, info in (*UNITS.items(), *BUILDINGS.items()) if info.damage]
#: What each is heard to strike with in the common Foley (a race's own arms are test_race_sound's).
WEAPONS = {
    UnitType.FOOTMAN: "sword", UnitType.PEASANT: "axe", UnitType.KNIGHT: "lance",
    UnitType.ARCHER: "arrow", UnitType.CATAPULT: "stone", UnitType.CLERIC: "mote", BuildingType.TOWER: "arrow",
    UnitType.WOLF: "axe", UnitType.TROLL: "axe", UnitType.GOLEM: "hammer", UnitType.SPIDER: "arrow",
    UnitType.GRYPHON: "hammer", UnitType.SAPPER: "stone", UnitType.TREANT: "hammer", UnitType.RUNE_GOLEM: "hammer",
}


@pytest.mark.parametrize("attacker_type, target_type, material", [
    (attacker, target, material)
    for attacker in STRIKERS
    for target, material in (
        (UnitType.PEASANT, "flesh"), (UnitType.FOOTMAN, "armor"), (UnitType.CATAPULT, "wood"),
        (BuildingType.FARM, "wood"), (BuildingType.TOWER, "stone"),
    )
    if isinstance(attacker, UnitType) or isinstance(target, UnitType)  # towers only shoot units
])
def test_killing_blow_keeps_the_targets_material(battle, target_type, material, attacker_type):
    """A victim removed by the simulation must still produce its own impact sound, whoever the rules let strike it."""
    game, scene, world = battle
    weapon = WEAPONS[attacker_type]  # a new striker: say above what it is heard to hit with
    if attacker_type is UnitType.CATAPULT:
        attacker = world.spawn_unit(0, attacker_type, (7.5, 10.5))  # beyond its minimum range
    elif isinstance(attacker_type, UnitType):
        attacker = world.spawn_unit(0, attacker_type, (10.5, 10.5))
    else:
        attacker = world.place_building(0, attacker_type, (8, 10))
    if isinstance(target_type, UnitType):
        target = world.spawn_unit(1, target_type, (11.5, 10.5))
        world.hold([target.id])  # a soldier would otherwise close on the catapult, inside where it can throw
    else:
        target = world.place_building(1, target_type, (11, 10))
    target.hp = 1
    world.update_vision()  # a tower shoots only what its owner can see
    if isinstance(attacker_type, UnitType):
        world.attack([attacker.id], target.id)
    tick_until(game, lambda: world.entity(target.id) is None)
    assert f"{weapon}_{material}" in scene.recent_sounds


def test_a_lone_sapper_s_owner_sees_and_hears_its_blast_on_every_tick_of_the_fog(tmp_path, audio_files, monkeypatch):
    """A sapper's eyes go up with its keg, and when the fog is looked at again the same step (every fourth) its spot is
    dark by the time the scene reads the news.  Its owner still sees the blast, the camera shakes, and the boom and
    the blow on the farm are heard: the sapper's death, which is its keg going up.  Started a tick later each time, one
    of four blasts lands on that step."""
    dark = []
    for delay in range(4):
        world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=[Race.ORC, Race.HUMAN])
        farm = world.place_building(1, BuildingType.FARM, (20, 10))
        sapper = world.spawn_unit(0, UnitType.SAPPER, (14.5, 11.0))
        world.place_building(0, BuildingType.TOWN_HALL, (1, 18))  # a side with a hall, out of sight of the farm
        world.place_building(1, BuildingType.TOWN_HALL, (26, 18))
        game = Game("Blast", backend="mock", save_dir=tmp_path / f"saves-{delay}")
        try:
            monkeypatch.setattr(sound, "sound_hook", sound.SoundBank(game, audio_files).play)
            scene = GameScene(world, seed=1, settings={"tutorial": False})
            scene.brains = []
            game.push(scene)
            scene.camera.center_on(*to_world(farm.center))
            shakes = []
            monkeypatch.setattr(scene.camera, "shake", lambda *args, **kwargs: shakes.append(args))
            for _ in range(delay):
                game.tick(SIM_DT)
            world.attack([sapper.id], farm.id)
            spot = sapper.pos
            while sapper.id in world.units:
                spot = sapper.pos
                game.tick(SIM_DT)
                assert world.time < 10.0, "the sapper never reached the farm"
            dark.append(not world.is_visible(0, (int(spot[0]), int(spot[1]))))
            assert deaths.cue("sapper") in scene.recent_sounds and shakes, f"started {delay} ticks late: the blast went unseen"
            assert "stone_wood" in scene.recent_sounds, f"started {delay} ticks late: its blow on the farm went unheard"
        finally:
            game.close()
    assert any(dark), "no blast landed where its owner no longer saw: the case this is for was never played"


def test_mixed_battle_limits_voices_without_suppressing_alerts(battle):
    """Many materials and weapons must share a budget while warnings stay immediate."""
    game, scene, world = battle
    for name in sorted(sound.IMPACTS):
        scene.sfx(name)
    assert 1 <= len(game.backend.sounds_played) <= 4
    for _ in range(3):
        game.tick(0.1)
        for name in sorted(sound.IMPACTS):
            scene.sfx(name)
    assert len(game.backend.sounds_played) <= 8
    scene.sfx("under_attack")
    assert scene.recent_sounds[-1] == "under_attack"
    before = len(game.backend.sounds_played)
    for _ in range(6):
        game.tick(0.1)
    scene.sfx("sword_flesh")
    assert len(game.backend.sounds_played) == before + 1


def test_offscreen_skirmish_is_quiet_but_own_attack_alert_still_plays(battle):
    """Scouted battles outside the camera should not fill the local soundscape."""
    game, scene, world = battle
    attacker = world.spawn_unit(1, UnitType.FOOTMAN, (26.5, 10.5))
    victim = world.spawn_unit(0, UnitType.PEASANT, (27.5, 10.5))
    scene.camera.zoom = 2
    scene.camera.center_on(160, 160)
    world.attack([attacker.id], victim.id)
    tick_until(game, lambda: victim.hp < victim.max_hp)
    assert world.is_visible(scene.human, victim.tile)
    assert "under_attack" in scene.recent_sounds
    assert not sound.IMPACTS.intersection(scene.recent_sounds)


@pytest.mark.parametrize("target_type, complete, material", [
    (UnitType.ARCHER, True, "armor"), (UnitType.CATAPULT, True, "wood"),
    (BuildingType.TOWER, False, "wood"),
])
def test_armor_upgrades_and_construction_change_the_actual_surface(battle, target_type, complete, material):
    """Armor research affects soldiers; siege frames and unfinished walls stay wood."""
    game, scene, world = battle
    world.players[1].upgrades.add(Upgrade.ARMOR_1)
    attacker = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    target = (world.spawn_unit(1, target_type, (11.5, 10.5)) if isinstance(target_type, UnitType)
              else world.place_building(1, target_type, (11, 10), done=complete))
    world.attack([attacker.id], target.id)
    before = target.hp  # a site under construction is already below its finished hit points
    tick_until(game, lambda: target.hp < before)
    assert f"sword_{material}" in scene.recent_sounds


def test_siege_splash_is_one_weighty_impact_not_a_building_collapse(battle):
    """One catapult volley can hit a crowd without replaying the collapse effect."""
    game, scene, world = battle
    attacker = world.spawn_unit(0, UnitType.CATAPULT, (9.5, 10.5))
    victims = [world.spawn_unit(1, UnitType.KNIGHT, (12.5, 10.5 + offset)) for offset in (-0.5, 0, 0.5)]
    world.hold([v.id for v in victims])
    world.attack([attacker.id], victims[1].id)
    tick_until(game, lambda: victims[1].hp < victims[1].max_hp)
    assert all(v.hp < v.max_hp for v in victims)
    for _ in range(6):
        game.tick(0.1)
    assert sum(name.startswith("stone_") for name in scene.recent_sounds) == 1
    assert not any(name.endswith("_collapse") for name in scene.recent_sounds)


def test_siege_impact_waits_for_the_visible_stone_to_land(battle):
    """Long-range catapult contact belongs at arrival: the stone is a projectile, and the blow and its sound land with it."""
    game, scene, world = battle
    attacker = world.spawn_unit(0, UnitType.CATAPULT, (9.5, 10.5))
    victim = world.spawn_unit(1, UnitType.KNIGHT, (15.5, 10.5))
    world.hold([victim.id])
    world.update_vision()
    world.attack([attacker.id], victim.id)
    tick_until(game, lambda: bool(world.projectiles))  # the stone is in the air
    assert victim.hp == victim.max_hp and "stone_armor" not in scene.recent_sounds
    tick_until(game, lambda: not world.projectiles)
    assert victim.hp < victim.max_hp and "stone_armor" in scene.recent_sounds
