"""Linked story keepers are identifiable in the actual match, and their focus follows saved and rescued unit ids."""

import json

import pytest

from saga2d import Game
from warband.sim.rules import Difficulty
from warband.story.mission_scene import MissionScene, build_world
from warband.story.new_campaign import CAMPAIGN
from warband.ui.scene import load_game
from warband.ui.style import build_theme


@pytest.fixture
def game(tmp_path):
    game = Game("Keepers", backend="mock", resolution=(1200, 680), theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


def start(game, mission_id):
    run = build_world(CAMPAIGN.mission(mission_id), flags={})
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM)
    scene.paused = True
    game.push(scene)
    for _ in range(30):
        game.tick(.1)
    return scene


def press(game, key):
    game.backend.inject_key(key)
    game.tick(.1)


def texts(game):
    return [item["text"] for item in game.backend.texts]


@pytest.mark.slow
def test_f3_identifies_issa_among_knights_and_keeps_her_portrait_after_a_save(game) -> None:
    """Slow: render the full final mission before and after a real save load, including its army portrait grid."""
    scene = start(game, "undertow_maw")
    issa = scene.run.unit("issa")
    other = next(unit for unit in scene.run.units(0, issa.type) if unit.id != issa.id)
    press(game, "f3")
    assert scene.selection == [issa.id] and scene.paused
    assert scene.entity_name(issa) == "Issa"
    assert scene.entity_name(other) == other.info.name
    assert "Issa" in texts(game) and "Issa · F3" in texts(game)
    key = "story.portrait." + CAMPAIGN.speakers["Issa"].portrait
    portrait = game.assets.image(key)
    assert any(item["image"] == portrait for item in game.backend.images)
    press(game, "f1")
    assert any("focus keeper" in text for text in texts(game))
    press(game, "escape")
    scene.select([issa.id, other.id])
    game.tick(.1)
    assert any(item["image"] == portrait for item in game.backend.images)
    saved = json.loads(json.dumps(scene.get_save_state()))
    resumed = load_game(saved)
    resumed.paused = True
    game.clear_and_push(resumed)
    for _ in range(30):
        game.tick(.1)
    press(game, "f3")
    assert resumed.selection == [resumed.run.unit("issa").id]
    assert "Issa" in texts(game) and "Issa · F3" in texts(game)
    assert any(item["image"] == portrait for item in game.backend.images)


@pytest.mark.slow
def test_keeper_focus_follows_the_real_rescue_and_no_longer_names_the_dead_unit(game) -> None:
    """Slow: a real Millfield death/rescue event changes the keeper id while its full map view is live."""
    scene = start(game, "undertow_mill")
    first = scene.run.unit("issa")
    first.hp = 0
    scene.paused = False
    game.tick(.1)
    scene.paused = True
    rescued = scene.run.unit("issa")
    assert rescued is not None and rescued.id != first.id
    press(game, "f3")
    assert scene.selection == [rescued.id]
    assert scene.entity_name(rescued) == "Issa"
    assert scene.entity_name(first) == first.info.name
    assert "Issa · F3" in texts(game)
