"""Campaign story views keep narration, field charts and the running mission in step."""

from pathlib import Path

import pytest
from saga2d import Game, Scene
from saga2d.testing import assert_no_text_overlap, assert_text_fits
from warband.art.visual_lint import use_real_text_metrics
from warband.sim.rules import Difficulty
from warband.story.briefing import briefing_chart
from warband.story.campaign import Progress
from warband.story.catalog import CAMPAIGNS, UNDERTOW
from warband.story.dialog import DialogScene
from warband.story.mission_scene import MissionScene, build_world, start_mission
from warband.ui.style import build_theme

MISSIONS = [(campaign, mission) for campaign in CAMPAIGNS for mission in campaign.missions]


@pytest.mark.parametrize("campaign,mission", MISSIONS, ids=[mission.id for _, mission in MISSIONS])
def test_each_levels_chart_reads_its_own_ground_without_changing_the_mission(campaign, mission):
    """Every authored beat resolves to real ground; making a chart cannot consume simulation randomness or change orders."""
    run = build_world(mission, flags={})
    before = run.world.to_dict()
    chart = briefing_chart(run)
    assert chart.size == (run.world.width, run.world.height)
    assert len(chart.beats) == len(mission.briefing)
    assert all(0 <= point[0] < chart.size[0] and 0 <= point[1] < chart.size[1]
               for _, point in chart.places.values())
    assert chart.ground.getbbox() is not None
    assert Path(__file__).resolve().parents[2].joinpath("warband/assets", mission.dialogue_art).is_file()
    assert run.world.to_dict() == before


@pytest.mark.slow
@pytest.mark.parametrize("campaign,mission", MISSIONS, ids=[mission.id for _, mission in MISSIONS])
def test_every_briefing_beat_and_its_annotations_fit_the_small_window(tmp_path, campaign, mission):
    """Slow: paint and lay out every line and map annotation of a whole briefing with real font metrics."""
    game = Game("Field charts", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    try:
        run = build_world(mission, flags={})
        game.push(Scene())
        game.push(DialogScene(mission.briefing, campaign.speakers, run.vars, chart=briefing_chart(run),
                              heading=f"CHAPTER {campaign.index(mission):02} / {mission.title}", end_label="Take command"))
        while isinstance(game.scene, DialogScene):
            game.tick(.1)
            assert_text_fits(game)
            assert_no_text_overlap(game, top_scene_only=True)
            game.backend.inject_key("space")
    finally:
        game.close()


@pytest.mark.slow
def test_caravan_chart_follows_the_words_and_hands_back_the_same_company(tmp_path):
    """Slow: enter a real mission, advance the briefing with input, then resume its frozen company and camera."""
    game = Game("Caravan briefing", backend="mock", resolution=(1200, 680),
                theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        mission = UNDERTOW.mission("undertow_caravan")
        start_mission(game, UNDERTOW, mission, Progress(UNDERTOW.id, Difficulty.MEDIUM), None)
        scene = game.scenes[-2]
        assert isinstance(scene, MissionScene)
        before = scene.world.to_dict()
        camera = scene.camera.center
        company = list(scene.selection)
        for _ in range(3):
            game.backend.inject_key("space")
            game.tick(.1)
        drawn = [item["text"] for item in game.backend.texts]
        assert "Choose a crossing on the Sorrow" in drawn
        assert "The causeway ford" in drawn and "Mill-dam pylon" in drawn
        assert scene.world.to_dict() == before
        assert scene.camera.center == camera and list(scene.selection) == company
        game.backend.inject_key("escape")
        game.tick(.1)
        assert game.scene is scene
        assert scene.world.time > before["time"]
        assert list(scene.selection) == company
    finally:
        game.close()
