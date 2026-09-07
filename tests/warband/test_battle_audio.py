"""Audio feedback exercised through real simulation steps and the game scene."""

import random

import pytest

from saga2d import Game
from warband import sound
from warband.model import Deposit, World
from warband.rules import BuildingType, Resource, Terrain, UnitType, Upgrade
from warband.scene import GameScene


@pytest.fixture(scope="module")
def audio_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("battle-audio")
    sound.generate(root, sound.SOUND_VERSION, sound.SOUNDS, {"march": sound.march, "vigil": sound.vigil})
    return root


@pytest.fixture
def battle(tmp_path, audio_files, monkeypatch):
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    game = Game("Battle audio", backend="mock", save_dir=tmp_path)
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


@pytest.mark.parametrize("attacker_type, weapon, target_type, material", [
    (attacker, weapon, target, material)
    for attacker, weapon in (
        (UnitType.FOOTMAN, "sword"), (UnitType.PEASANT, "axe"),
        (UnitType.SCOUT, "spear"), (UnitType.KNIGHT, "lance"),
        (UnitType.ARCHER, "arrow"), (UnitType.CATAPULT, "stone"), (BuildingType.TOWER, "arrow"),
    )
    for target, material in (
        (UnitType.PEASANT, "flesh"), (UnitType.FOOTMAN, "armor"), (UnitType.CATAPULT, "wood"),
        (BuildingType.FARM, "wood"), (BuildingType.TOWER, "stone"),
    )
    if isinstance(attacker, UnitType) or isinstance(target, UnitType)  # towers only shoot units
])
def test_killing_blow_keeps_the_targets_material(battle, target_type, material, attacker_type, weapon):
    """A victim removed by the simulation must still produce its own impact sound."""
    game, scene, world = battle
    if isinstance(attacker_type, UnitType):
        attacker = world.spawn_unit(0, attacker_type, (10.5, 10.5))
    else:
        attacker = world.place_building(0, attacker_type, (8, 10))
    if isinstance(target_type, UnitType):
        target = world.spawn_unit(1, target_type, (11.5, 10.5))
    else:
        target = world.place_building(1, target_type, (11, 10))
    target.hp = 1
    if isinstance(attacker_type, UnitType):
        world.attack([attacker.id], target.id)
    game.tick(0.2)
    assert world.entity(target.id) is None
    assert f"{weapon}_{material}" in scene.recent_sounds


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
    game.tick(0.2)
    assert victim.hp < victim.max_hp
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
    game.tick(0.2)
    assert f"sword_{material}" in scene.recent_sounds


def test_siege_splash_is_one_weighty_impact_not_a_building_collapse(battle):
    """One catapult volley can hit a crowd without replaying the collapse effect."""
    game, scene, world = battle
    attacker = world.spawn_unit(0, UnitType.CATAPULT, (9.5, 10.5))
    victims = [world.spawn_unit(1, UnitType.KNIGHT, (11.5, 10.5 + offset)) for offset in (-0.5, 0, 0.5)]
    world.attack([attacker.id], victims[1].id)
    game.tick(0.2)
    assert all(v.hp < v.max_hp for v in victims)
    for _ in range(6):
        game.tick(0.1)
    assert sum(name.startswith("stone_") for name in scene.recent_sounds) == 1
    assert "destroyed" not in scene.recent_sounds


def test_siege_impact_waits_for_the_visible_stone_to_land(battle):
    """Long-range catapult contact belongs at arrival, after the visible flight."""
    game, scene, world = battle
    attacker = world.spawn_unit(0, UnitType.CATAPULT, (9.5, 10.5))
    victim = world.spawn_unit(1, UnitType.KNIGHT, (15.5, 10.5))
    world.update_vision()
    world.attack([attacker.id], victim.id)
    game.tick(0.05)
    assert victim.hp < victim.max_hp
    for _ in range(3):
        game.tick(0.1)
    assert "stone_armor" not in scene.recent_sounds
    for _ in range(4):
        game.tick(0.1)
    assert "stone_armor" in scene.recent_sounds
