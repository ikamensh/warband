"""The packaged campaign gate walks real UI/load paths across all races, so it is slow."""

import importlib.util

import pytest

from saga2d import Game
from tools.package import PACKAGE
from warband.story.catalog import UNDERTOW
from warband.story.mission_scene import MissionScene
from warband.ui.scene import DEFAULT_SETTINGS
from warband.ui.style import build_theme
from warband.ui.title import TitleScene


@pytest.mark.slow
def test_package_gate_reaches_every_mission_and_loads_its_automatic_slot(tmp_path):
    """Slow: actual UI input renders five race views and round-trips each campaign save through Load."""
    spec = importlib.util.spec_from_file_location("package_campaign_check", PACKAGE.check)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    game = Game("Package campaign gate", backend="mock", resolution=(1280, 800),
                theme=build_theme(), save_dir=tmp_path / "saves")
    captures = []
    try:
        settings = game.settings(DEFAULT_SETTINGS)

        def frames(count=3):
            for _ in range(count):
                game.tick(1 / 30)

        def press(symbol):
            game.backend.inject_key({"ENTER": "return"}.get(symbol, symbol.lower()))
            frames()

        def capture(suffix):
            frames()
            captures.append((suffix, game.scene))

        game.push(TitleScene(settings=settings))
        frames()
        result = checker.campaign_journey(game, frames, press, capture)
        assert result["missions"] == [mission.id for mission in UNDERTOW.missions]
        assert result["portraits"] == ["Brakk", "Dagna", "Issa", "Sella", "Wrenna"]
        assert result["cover"] and result["objectives"] and result["landmarks"] and result["autosave_load"]
        assert isinstance(game.scene, TitleScene)
        for mission in UNDERTOW.missions:
            for suffix in (f"-campaign-{mission.id}", f"-campaign-{mission.id}-resumed"):
                scene = next(scene for name, scene in captures if name == suffix)
                assert isinstance(scene, MissionScene) and scene.mission is mission
                assert not scene.run.won and scene.run.lost is None
        assert any(name == "-campaign-cover" for name, _ in captures)
    finally:
        game.close()
