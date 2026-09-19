"""Building wreckage: a crack, the mass coming down, the debris settling, per material and take."""

import random

import numpy as np
import pytest

from saga2d import Game
from sagaforge.synth import SAMPLE_RATE
from warband.audio import sound, wreckage
from warband.sim.model import World
from warband.sim.rules import BuildingType, Race, Terrain, UnitType
from warband.ui.scene import GameScene
from warband.audio.sound import SoundBank


def test_every_material_has_collapse_cues_longer_than_any_one_stage() -> None:
    for material in wreckage.MATERIALS:
        assert wreckage.takes(material) >= 2, material
        for take in range(wreckage.takes(material)):
            clip = wreckage.collapse(material, take)
            seconds = len(clip) / SAMPLE_RATE
            assert clip.ndim == 1 and 1.5 <= seconds <= 5.0, (material, take, seconds)
            assert abs(np.abs(clip).max() - wreckage.PEAK) < 0.01 and abs(clip[0]) < 0.01 and abs(clip[-1]) < 0.02, (material, take)
            falling = len(wreckage.piece(material, "collapse", take)) / SAMPLE_RATE
            assert seconds >= wreckage.CRACK_TO_COLLAPSE + falling, (material, take)  # the crack first, the mass after it


def test_materials_follow_the_building_and_a_site_is_scaffolding() -> None:
    assert wreckage.material(BuildingType.TOWER) == "stone" and wreckage.material(BuildingType.FARM) == "wood"
    assert wreckage.material(BuildingType.TOWER, complete=False) == "wood"
    assert set(wreckage.CUES) == {"wood_collapse", "stone_collapse"}


@pytest.fixture
def battle(tmp_path, monkeypatch):
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=[Race.HUMAN, Race.ORC])
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    game = Game("Warband wreckage", backend="mock", save_dir=tmp_path / "saves")
    bank = SoundBank(game, tmp_path / "audio")
    monkeypatch.setattr(sound, "sound_hook", bank.play)
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    yield game, scene, world
    game.close()


def test_a_razed_building_collapses_in_its_material(battle) -> None:
    game, scene, world = battle
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    farm = world.place_building(1, BuildingType.FARM, (11, 10))
    farm.hp = 1
    world.attack([footman.id], farm.id)
    for _ in range(15):
        game.tick(0.1)
    assert world.entity(farm.id) is None and "wood_collapse" in scene.recent_sounds
    tower = world.place_building(1, BuildingType.TOWER, (13, 10))
    tower.hp = 1
    world.attack([footman.id], tower.id)
    for _ in range(40):  # the footman walks over, waits out his swing, strikes
        game.tick(0.1)
        if world.entity(tower.id) is None:
            break
    assert world.entity(tower.id) is None and "stone_collapse" in scene.recent_sounds
    assert "destroyed" not in scene.recent_sounds
