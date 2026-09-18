"""The visual lint sees what a person would, and the game's screens pass it."""

import sys
from pathlib import Path

import pytest

from saga2d import Game, RenderLayer, Scene, Sprite, SpriteAnchor
from saga2d.ui import Label
from sagaforge import render3d as r3
from warband import textures, visual_lint
from warband.rules import Race, Resource, UnitType
from warband.style import build_theme
from warband.title import TitleScene

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import visual_lint as screens  # noqa: E402

VISIBLE = {"text-overlap", "panel-overlap", "off-screen", "text-off-screen", "draw-order", "stretched"}


@pytest.mark.parametrize("resolution", screens.RESOLUTIONS)
def test_title_fits_on_the_first_frame(tmp_path, resolution) -> None:
    """The title must not use stale layout bounds and jump down after its first frame."""
    game = Game("Lint", backend="mock", resolution=resolution, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        visual_lint.use_real_text_metrics(game)
        game.push(TitleScene())
        game.tick(1 / 60)
        assert not game.text_overflows
        assert not visual_lint.lint_texts(game)
    finally:
        game.close()


class Crowded(Scene):
    """Two texts on one spot and a label narrower than its text."""

    def on_enter(self) -> None:
        self.ui.add(Label("A long line of text in a short box", width=20))

    def draw(self) -> None:
        self.draw_text("first", 300, 300)
        self.draw_text("second", 304, 302)


def test_the_lint_sees_text_over_text_and_text_wider_than_its_box(tmp_path) -> None:
    game = Game("Lint", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        visual_lint.use_real_text_metrics(game)
        game.push(Crowded())
        game.tick(1 / 60)
        checks = {f.check for f in visual_lint.lint_frame(game)}
    finally:
        game.close()
    assert {"text-overlap", "overflow"} <= checks


def test_text_lint_checks_the_active_overlay_not_its_paused_background(tmp_path) -> None:
    """A covered scene may pause a toast mid-slide; the overlay itself must still fit."""
    class Offscreen(Scene):
        transparent = True

        def draw(self) -> None:
            self.draw_text("Outside", 650, 100)

    class Overlay(Scene):
        transparent = True

    game = Game("Lint", backend="mock", resolution=(640, 480), save_dir=tmp_path / "saves")
    try:
        game.push(Offscreen())
        game.tick(1 / 60)
        assert [f.check for f in visual_lint.lint_texts(game)] == ["text-off-screen"]
        game.push(Overlay())
        game.tick(1 / 60)
        assert not visual_lint.lint_texts(game)
        game.push(Offscreen())
        game.tick(1 / 60)
        assert [f.check for f in visual_lint.lint_texts(game)] == ["text-off-screen"]
    finally:
        game.close()


def test_the_lint_sees_a_sprite_drawn_over_the_one_it_stands_behind(tmp_path) -> None:
    game = Game("Lint", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        store = visual_lint.ImageStore(game)
        textures.register_static(game)
        placement = textures.placements["site.2"]
        scene = Scene()
        game.push(scene)

        def site(y: float, ground: float) -> Sprite:
            return scene.add_sprite(Sprite("site.2", position=(100, y + placement.drop), size=placement.size, anchor=SpriteAnchor.BOTTOM_CENTER,
                                           layer=RenderLayer.UNITS, y_sort=True, ground=ground))

        behind, front = site(100, placement.ground), site(110, placement.ground)
        game.tick(1 / 60)
        assert not visual_lint.lint_sprites(game, store)
        behind.ground = -40  # sorted as if it stood 40 px lower: now drawn over the one in front of it
        game.tick(1 / 60)
        assert [f.check for f in visual_lint.lint_sprites(game, store)] == ["draw-order"]
    finally:
        game.close()


def test_every_unit_pose_fits_the_unit_canvas() -> None:
    """A pose reaching below the padding would raise while rendering the low-poly art."""
    for race in Race:
        for unit_type in UnitType:
            carries = (None, Resource.GOLD, Resource.LUMBER) if unit_type is UnitType.PEASANT else (None,)
            for carrying in carries:
                frames = textures.FRAMES + textures.CHOP_FRAMES if unit_type is UnitType.PEASANT and carrying is None else textures.FRAMES
                for frame in frames:
                    mesh = textures._unit(unit_type, 0, frame, carrying, race)
                    reach = max(r3.bounds(r3.rotate_z(mesh, facing * 45 - 90), textures.PROJECTION)[3] for facing in range(textures.FACINGS))
                    assert reach + textures.PAD <= textures.DROP_UNIT, (race, unit_type, carrying, frame, reach)


SCREENS = ("title", "new_game_elf", "select_peasant", "select_town_hall", "select_army", "select_60_units", "town_at_work", "menu_build_hover", "plans", "alerts", "battle_wood",
           "help", "codex_0", "codex_2", "codex_3", "save_browser", "game_over_won", "high_scores")


@pytest.mark.parametrize("resolution", screens.RESOLUTIONS, ids=lambda r: f"{r[0]}x{r[1]}")
@pytest.mark.parametrize("name", SCREENS)
def test_the_screens_draw_nothing_over_anything(name: str, resolution: tuple[int, int]) -> None:
    """Texts and panels keep off each other and on the screen; overlays fit even a 1200×680 window;
    sprites draw in front only of what they stand in front of."""
    findings = screens.run_screen(name, resolution, None)
    visible = [f for f in findings if f.check in VISIBLE or (f.check == "overflow" and name in ("help", "codex_0", "codex_2", "codex_3", "save_browser"))]
    assert not visible, "\n".join(str(f) for f in visible)
