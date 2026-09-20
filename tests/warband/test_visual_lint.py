"""The visual lint sees what a person would, and the game's screens pass it."""

import sys
from pathlib import Path

import pytest

from saga2d import Game, RenderLayer, Scene, Sprite, SpriteAnchor
from saga2d.ui import Label
from sagaforge import render3d as r3
from warband.art import textures, visual_lint
from warband.sim.rules import Cost, Race, Resource, UnitType
from warband.ui.icons import Price, price_pairs
from warband.ui.scene import CodexScene, codex_world
from warband.ui.style import build_theme
from warband.ui.title import TitleScene

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


class Priced(Scene):
    """A price in a box too narrow for its symbols and numbers."""

    def __init__(self, width: int) -> None:
        self.width = width

    def on_enter(self) -> None:
        self.ui.add(Price(price_pairs(Cost(1200, 800)), size=14, width=self.width))


@pytest.mark.parametrize("width, flagged", [(40, True), (200, False)])
def test_the_lint_sees_a_price_wider_than_its_column(tmp_path, width, flagged) -> None:
    """A price is drawn as symbols and numbers, not laid out as a label, so nothing about it is wider than its
    box unless the lint measures what it needs: the codex once ran a building's lumber into the next column."""
    game = Game("Lint", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        visual_lint.use_real_text_metrics(game)
        game.push(Priced(width))
        game.tick(1 / 60)
        checks = {f.check for f in visual_lint.lint_frame(game)}
    finally:
        game.close()
    assert ("overflow" in checks) is flagged
class Orphaned(Scene):
    """A wrapped label whose own line break lands after a line the box already wraps."""

    def on_enter(self) -> None:
        self.ui.add(Label("No rated matches yet. Beat the computer to earn a rating;\nleaving a match early counts against it.",
                          text_style="sub", width=376, wrap=True))
        self.ui.add(Label("Two short lines,\nneither of which wraps.", text_style="sub", width=376, wrap=True))


def test_the_lint_sees_a_line_break_that_orphans_what_the_wrapper_left(tmp_path) -> None:
    """The title card read "...to earn / a rating; / leaving a match...": the wrapper broke the sentence and the
    hard break then started a new line, leaving two words alone.  A break after a line that fits is fine."""
    game = Game("Lint", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        visual_lint.use_real_text_metrics(game)
        game.push(Orphaned())
        game.tick(1 / 60)
        orphans = [f for f in visual_lint.lint_frame(game) if f.check == "orphan"]
    finally:
        game.close()
    assert len(orphans) == 1 and "No rated matches yet" in orphans[0].detail


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


@pytest.mark.parametrize("page", [0, 1, 2], ids=["units", "buildings", "upgrades"])
@pytest.mark.parametrize("race", list(Race), ids=lambda r: r.value)
def test_every_race_s_codex_tables_fit_the_smallest_window(page: int, race: Race, tmp_path) -> None:
    """The codex's tables are the tallest thing the game draws and each race writes its own: the unit page stands
    672 px of 680, so one word added to a wrapped column costs a line and pushes the page off the screen for
    whichever race's summaries are longest.  The screens above walk one race's codex; this walks all four, with the
    same font metrics — the mock backend's own measurements are too coarse to see the wrap."""
    game = Game("Lint", backend="mock", resolution=SMALLEST, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        visual_lint.use_real_text_metrics(game)
        game.push(CodexScene(codex_world(race), 0, page, in_match=False))
        game.tick(1 / 60)
        findings = [f for f in visual_lint.lint_layout(game, game.scene) if f.check in VISIBLE]
        assert not findings, "\n".join(str(f) for f in findings)
    finally:
        game.close()


@pytest.mark.slow
def test_every_unit_pose_fits_the_unit_canvas() -> None:
    """A pose reaching below the padding would raise while rendering the low-poly art.

    Every race's every pose in all eight facings takes about two seconds: the slow tier, which a change to the
    art runs before it is pushed."""
    for race in Race:
        for unit_type in UnitType:
            carries = (None, Resource.GOLD, Resource.LUMBER) if unit_type is UnitType.PEASANT else (None,)
            for carrying in carries:
                frames = textures.FRAMES + textures.CHOP_FRAMES if unit_type is UnitType.PEASANT and carrying is None else textures.FRAMES
                for frame in frames:
                    mesh = textures._unit(unit_type, 0, frame, carrying, race)  # the mesh itself: the drop is sized for its reach
                    reach = max(r3.bounds(r3.rotate_z(mesh, facing * 45 - 90), textures.PROJECTION)[3] for facing in range(textures.FACINGS))
                    assert reach + textures.PAD <= textures.DROP_UNIT, (race, unit_type, carrying, frame, reach)


SCREENS = ("title", "new_game_elf", "new_game_master", "select_peasant", "pending_salvage", "select_town_hall", "select_army", "select_60_units", "select_60_archers", "town_at_work", "menu_build_hover", "menu_train_hover",
           "menu_build_at_start", "menu_train_at_start", "menu_upgrade_researched", "menu_upgrade_all_done", "plans", "alerts", "battle_wood",
           "help", "codex_0", "codex_2", "codex_3", "codex_4", "save_browser", "game_over_won", "high_scores",
           "campaign_fresh", "campaign_under_way", "mission_raid", "mission_choice", "mission_result")


#: Screens whose every label must hold its text: the overlays' tables, and the catalogues' captions of what an item needs.
OVERFLOW_CHECKED = ("help", "codex_0", "codex_2", "codex_3", "codex_4", "save_browser", "menu_build_at_start", "menu_train_at_start")
SMALLEST = min(screens.RESOLUTIONS)
FAST_SCREENS = {"title", "select_army", "town_at_work", "battle_wood", "menu_build_hover", "help", "mission_raid"}


@pytest.mark.parametrize("name, resolution", [pytest.param(name, r, id=f"{name}-{r[0]}x{r[1]}",
                                                           marks=() if name in FAST_SCREENS and r == SMALLEST else pytest.mark.slow)
                                              for name in SCREENS for r in screens.RESOLUTIONS])
def test_the_screens_draw_nothing_over_anything(name: str, resolution: tuple[int, int]) -> None:
    """Texts and panels keep off each other and on the screen; overlays fit even a 1200×680 window;
    sprites draw in front only of what they stand in front of. A screen takes a fifth of a second or more
    to play and lint, so the fast tier lints seven, a match's, a mission's and an overlay's, in that
    smallest window, and the slow tier every screen in every window. The layout tests keep text off text
    on every screen in the fast tier."""
    findings = screens.run_screen(name, resolution, None)
    visible = [f for f in findings if f.check in VISIBLE or (f.check == "overflow" and name in OVERFLOW_CHECKED)]
    assert not visible, "\n".join(str(f) for f in visible)
