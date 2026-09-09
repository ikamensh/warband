"""Each race sounds like itself: voiced cues, race weapon Foley and a march of its own."""

import random

import pytest

from saga2d import Game
from warband import music, sound
from warband.model import Event, World
from warband.rules import BuildingType, Race, Terrain, UnitType
from warband.scene import GameScene, new_game
from warband.style import build_theme
from warband.title import TitleScene
from warband.voices import CUES, voiced


def test_cues_are_voiced_for_every_race_but_humans_and_impacts_follow_the_striker() -> None:
    for cue in CUES:
        assert voiced(cue, Race.HUMAN) == cue
        for race in (Race.ORC, Race.ELF, Race.DWARF):
            assert voiced(cue, race) == f"{race.value}_{cue}" in sound.SOUNDS
    assert voiced("sword_flesh", Race.ORC) == "sword_flesh" and voiced("button", Race.DWARF) == "button"
    blow = Event("hit", (1.0, 1.0), source_type="knight", target_type="footman", target_armor=2)
    assert sound.impact_sound(blow) == "lance_armor" and sound.impact_sound(blow, Race.ELF) == "lance_armor"
    assert sound.impact_sound(blow, Race.DWARF) == "hammer_armor" and sound.impact_sound(blow, Race.ORC) == "hammer_armor"
    swing = Event("hit", (1.0, 1.0), source_type="footman", target_type="peasant", target_armor=0)
    assert sound.impact_sound(swing, Race.ORC) == "axe_flesh" and sound.impact_sound(swing, Race.DWARF) == "axe_flesh"
    assert sound.impact_sound(swing, Race.HUMAN) == "sword_flesh"
    assert "hammer" in sound.combat_sound.WEAPONS and all(f"hammer_{m}_0" in sound.SOUNDS for m in sound.combat_sound.MATERIALS)
    assert {suite.battle for suite in music.SUITES.values()} | {music.TITLE_TRACK} <= set(music.TRACKS) and len(music.SUITES) == 4


@pytest.fixture
def game(tmp_path):
    g = Game("Race sound", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g._teardown()


def test_a_match_speaks_and_marches_in_the_players_race(game, monkeypatch) -> None:
    played = []
    monkeypatch.setattr(sound, "music_hook", lambda mood, race: played.append((mood, race)))
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=(Race.DWARF, Race.ORC))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    game.tick(1 / 60)
    assert set(played) == {("peace", Race.DWARF)}  # asked on entry and again every frame, so a fight can change it
    scene.sfx("command")
    scene.sfx("sword_flesh")
    assert list(scene.recent_sounds) == ["dwarf_command", "sword_flesh"]
    bear = world.spawn_unit(0, UnitType.KNIGHT, (10.5, 10.5))
    grunt = world.spawn_unit(1, UnitType.FOOTMAN, (11.5, 10.5))
    world.hold([grunt.id])
    world.attack([bear.id], grunt.id)
    for _ in range(12):
        game.tick(0.1)
    assert "hammer_armor" in scene.recent_sounds and "axe_armor" in scene.recent_sounds  # a war hammer on the grunt's hide armour; its axe on the rider's plate
    assert "dwarf_under_attack" in scene.recent_sounds
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    assert played[-1] == ("title", None)
    game.clear_and_push(new_game(seed=2, races=[Race.ELF, None]))
    game.tick(1 / 60)
    assert played[-1] == ("peace", Race.ELF)
