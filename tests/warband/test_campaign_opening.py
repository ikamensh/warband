"""The player's first campaign minutes: briefing, command, pressure and resume."""

import json

import pytest

from saga2d import Button, Game
from warband.sim.model import World
from warband.sim.rules import Upgrade
from warband.story.campaign import Run
from warband.story.campaign_scene import CampaignScene
from warband.story.dialog import DialogScene
from warband.story.mission_scene import MissionScene, build_world
from warband.story.new_campaign import CAMPAIGN
from warband.ui.style import build_theme


@pytest.fixture
def game(tmp_path):
    game = Game("Campaign opening", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    yield game
    game.close()


@pytest.mark.slow
def test_begin_briefs_on_the_battlefield_without_advancing_the_battle(game) -> None:
    """Slow: launch through the real menu and build its full map view; reading the briefing costs no lives."""
    game.push(CampaignScene(campaign=CAMPAIGN))
    game.tick(.1)
    game.backend.inject_key("return")
    game.tick(.1)
    assert isinstance(game.scene, DialogScene)
    battlefield = game.scenes[-2]
    assert isinstance(battlefield, MissionScene)
    for _ in range(20):
        game.tick(.1)
    assert battlefield.world.time == 0
    game.backend.inject_key("escape")
    game.tick(.1)
    assert game.scene is battlefield
    assert set(battlefield.selection) == {unit.id for unit in battlefield.run.soldiers(0)}


def test_first_orders_can_heal_and_fight_without_another_conversation() -> None:
    """The opening has usable spell-light, a wounded ally and a visible threat before its decision beat."""
    run = build_world(CAMPAIGN.missions[0], flags={})
    wounded = next(unit for unit in run.soldiers(0) if unit.hp < unit.info.hp)
    before = wounded.hp
    run.world.cast(0, Upgrade.MEND, wounded.pos)
    for _ in range(20):
        run.world.step()
        run.tick()
    assert wounded.hp > before
    for _ in range(80):
        run.world.step()
        run.tick()
    assert run.units(1) and not run.pending
    wolf = next(unit for unit in run.units(1) if run.world.is_visible(0, unit.tile))
    run.world.attack([unit.id for unit in run.soldiers(0)], wolf.id)
    for _ in range(100):
        run.world.step()
        run.tick()
    assert wolf.id not in run.world.units or wolf.hp < wolf.info.hp
    assert not run.pending


def test_saved_opening_reaches_the_same_crisis_without_repeating_the_first_wave() -> None:
    """A save after the first command preserves the wave and the one-time crisis, including its journal text."""
    run = build_world(CAMPAIGN.missions[0], flags={})
    for _ in range(100):
        run.world.step()
        run.tick()
    saved = json.loads(json.dumps({"world": run.world.to_dict(), "mission": run.to_dict()}))
    again = Run.from_dict(run.mission, World.from_dict(saved["world"]), saved["mission"])
    for current in (run, again):
        current.world.attack_move([unit.id for unit in current.soldiers(0)], tuple(current.get("mill_farm_center")))
        for _ in range(700):
            current.world.step()
            current.tick()
    assert run.fired == again.fired and "wave_2" in run.fired
    assert run.get("wave_1_band") == again.get("wave_1_band")
    assert run.state == again.state
    assert run.pending == again.pending and len(run.pending) == 1


@pytest.mark.slow
def test_reading_the_briefing_ends_with_take_command_and_the_selected_company(game) -> None:
    """Slow: the normal Space journey through the actual briefing gives a clear handoff to the battlefield."""
    game.push(CampaignScene(campaign=CAMPAIGN))
    game.tick(.1)
    game.backend.inject_key("return")
    game.tick(.1)
    for _ in range(len(CAMPAIGN.missions[0].briefing)-1):
        game.backend.inject_key("space")
        game.tick(.1)
    buttons = [component.text for component in game.scene.ui.walk() if isinstance(component, Button)]
    assert "Take command" in buttons
    game.backend.inject_key("space")
    game.tick(.1)
    assert isinstance(game.scene, MissionScene) and game.scene.selection


@pytest.mark.slow
def test_a_campaign_spell_returns_to_the_selected_company(game) -> None:
    """Slow: the real mission HUD must let the next right-click command soldiers after a successful Mend."""
    from warband.sim.rules import Difficulty

    scene = MissionScene(CAMPAIGN, build_world(CAMPAIGN.missions[0], flags={}), difficulty=Difficulty.MEDIUM)
    game.push(scene)
    game.tick(.1)
    company = list(scene.selection)
    wounded = next(unit for unit in scene.run.soldiers(0) if unit.hp < unit.info.hp)
    scene.aim_level(1)
    assert scene.aiming is Upgrade.MEND
    scene.cast_at(wounded.pos)
    assert scene.world.cooldown_left(0, Upgrade.MEND) > 0
    assert scene.catalogue is None and scene.selection == company
