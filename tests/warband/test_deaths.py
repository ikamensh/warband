"""Unit deaths: one cue per sound family and take, from generated pieces; a race's people cry out and their weapon, body
and gear land, the machines and creatures die as their bodies do."""

from pathlib import Path
import random

import numpy as np
import pytest

from saga2d import Game

from sagaforge.synth import SAMPLE_RATE
from warband.audio import deaths, sound
from warband.audio.bodies import RACE_FAMILIES
from warband.sim.model import World
from warband.sim.rules import BuildingType, Race, Terrain, UnitType
from warband.ui.scene import GameScene
from warband.audio.sound import SoundBank


def low_band_peak_time(clip: np.ndarray) -> float:
    """When the energy below 70 Hz peaks: the body hitting the ground; no voice reaches down there."""
    window = int(0.05 * SAMPLE_RATE)
    n = 1 << (len(clip) - 1).bit_length()  # a power of two: a clip's own length can be a prime, and its transform slow
    low = np.fft.irfft(np.where(np.fft.rfftfreq(n, 1 / SAMPLE_RATE) < 70, np.fft.rfft(clip, n), 0), n)[:len(clip)]
    envelope = np.convolve(low ** 2, np.ones(window) / window, mode="same")
    return int(np.argmax(envelope)) / SAMPLE_RATE


def test_every_family_has_death_cues_at_the_level_with_clean_ends() -> None:
    for family, spent in deaths.ENDS:  # its death, and its spent end where it has one (a sapper's keg)
        for take in range(deaths.takes(family, spent=spent)):
            clip = deaths.death(family, take, spent=spent)
            seconds = len(clip) / SAMPLE_RATE
            assert clip.ndim == 1 and 0.6 <= seconds <= 3.5, (family, spent, take, seconds)
            assert abs(np.abs(clip).max() - deaths.PEAK) < 0.01 and abs(clip[0]) < 0.01 and abs(clip[-1]) < 0.02, (family, spent, take)


def test_every_race_has_death_cues_whose_fall_lands_after_the_cry() -> None:
    for race in RACE_FAMILIES:
        assert deaths.takes(race) >= 3, race
        for take in range(deaths.takes(race)):
            clip = deaths.death(race, take)
            assert low_band_peak_time(clip) > 0.45 * len(clip) / SAMPLE_RATE, (race, take)


@pytest.fixture
def bank(tmp_path):
    game = Game("Warband deaths", backend="mock", save_dir=tmp_path / "saves")
    yield game, SoundBank(game, data_dir=tmp_path / "audio")
    game.close()


def test_the_bank_plays_a_races_death_in_varying_takes_under_the_alert_volume(bank) -> None:
    game, bank = bank
    bank.set_volume("sfx", 1.0)
    for _ in range(10):
        bank.play(deaths.cue("orc"))
    played = game.backend.sounds_played[-10:]
    handles = {game.backend.load_sound(str(bank.data_dir / "sounds" / f"orc_death_{take}.wav")): take for take in range(deaths.takes("orc"))}
    takes = [handles[p["handle"]] for p in played]  # KeyError if anything but an orc death was played
    assert len(set(takes)) >= 2 and not any(a == b for a, b in zip(takes, takes[1:]))  # varied, never the same take twice in a row
    assert all(0.4 <= p["volume"] < 1.0 for p in played)


@pytest.fixture
def battle(tmp_path, monkeypatch):
    """Humans (player 0, the human player) against orcs, with the bank routed in."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=[Race.HUMAN, Race.ORC])
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    game = Game("Warband deaths", backend="mock", save_dir=tmp_path / "saves")
    bank = SoundBank(game, tmp_path / "audio")
    monkeypatch.setattr(sound, "sound_hook", bank.play)
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    yield game, scene, world
    game.close()


def test_a_dying_unit_cries_out_in_its_own_race(battle) -> None:
    game, scene, world = battle
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    grunt = world.spawn_unit(1, UnitType.PEASANT, (11.5, 10.5))
    grunt.hp = 1
    world.attack([footman.id], grunt.id)
    for _ in range(15):
        game.tick(0.1)
    assert world.entity(grunt.id) is None and "orc_death" in scene.recent_sounds
    avenger = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 11.5))
    footman.hp = 1
    world.attack([avenger.id], footman.id)
    for _ in range(15):
        game.tick(0.1)
    assert world.entity(footman.id) is None and "human_death" in scene.recent_sounds
    assert "death" not in scene.recent_sounds  # the old raceless thud is gone
