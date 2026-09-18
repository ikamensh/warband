"""A match opens with its map filling the window (WB-035): a map narrower than the canvas, or shorter than the room
between the HUD's rows and panels, opens zoomed in instead of lying in dark margins; one that fills it at zoom 1
opens at 1, as it always did."""

import pytest

from saga2d import Game
from warband import mapgen
from warband.mission_scene import MissionScene, build_world
from warband.missions import CAMPAIGN
from warband.rules import Difficulty
from warband.scene import new_game
from warband.style import build_theme
from warband.textures import TILE

CANVASES = [(1280, 800), (1840, 960), (2480, 1320)]  # a laptop window; a 4K desktop at 200 % and at 150 %


def assert_the_map_fills_the_view(scene) -> None:
    """At the camera's starting place and at the four corners it can be scrolled to, the view shows nothing past the
    map's rim beside it, nor between the HUD's top rows and its bottom panels."""
    camera, world = scene.camera, scene.world
    rim = (-TILE, -TILE, (world.width + 1) * TILE, (world.height + 1) * TILE)
    _left, inset_top, _right, inset_bottom = camera.insets
    for place in (None, rim[:2], (rim[2], rim[1]), (rim[0], rim[3]), rim[2:]):
        if place is not None:
            camera.center_on(*place)
        left, top, right, bottom = camera.visible_world_rect()
        top, bottom = top + inset_top / camera.zoom, bottom - inset_bottom / camera.zoom
        assert rim[0] - 1e-6 <= left and right <= rim[2] + 1e-6, f"a margin beside the map at zoom {camera.zoom:.2f}"
        assert rim[1] - 1e-6 <= top and bottom <= rim[3] + 1e-6, f"a margin above or below the map at zoom {camera.zoom:.2f}"


@pytest.mark.parametrize("canvas", CANVASES, ids=[f"{w}x{h}" for w, h in CANVASES])
@pytest.mark.parametrize("size", list(mapgen.SIZES))
def test_a_match_opens_with_its_map_filling_the_window(size: str, canvas: tuple[int, int], tmp_path) -> None:
    width, height = mapgen.SIZES[size]
    game = Game("Warband camera", backend="mock", resolution=canvas, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3, width=width, height=height)
        game.push(scene)
        game.tick(1 / 60)
        _left, inset_top, _right, inset_bottom = scene.camera.insets
        fills_at_one = (width + 2) * TILE >= canvas[0] and (height + 2) * TILE >= canvas[1] - inset_top - inset_bottom
        assert (scene.camera.zoom == 1.0) == fills_at_one, f"{size} on {canvas} opened at zoom {scene.camera.zoom:.2f}"
        assert_the_map_fills_the_view(scene)
    finally:
        game.close()


def test_a_mission_opens_with_its_map_filling_the_window(tmp_path) -> None:
    """The campaign plays on the same camera: its first mission on a 4K desktop at 150 %."""
    game = Game("Warband camera", backend="mock", resolution=(2480, 1320), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = MissionScene(CAMPAIGN, build_world(CAMPAIGN.mission("hollowmere"), flags={}), difficulty=Difficulty.MEDIUM)
        game.push(scene)
        game.tick(1 / 60)
        assert scene.camera.zoom > 1.0
        assert_the_map_fills_the_view(scene)
    finally:
        game.close()
