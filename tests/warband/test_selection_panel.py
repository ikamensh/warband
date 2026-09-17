"""Large selections stay inside the selection panel (WB-018): a two-row grid, paging beyond it, every unit reachable by a click."""

import pytest

from saga2d import Game
from warband.rules import UnitType
from warband.scene import PORTRAITS_PER_PAGE, GameScene
from warband.style import build_theme

from tests.warband.battlefield import SETTINGS, field


def start(tmp_path, resolution: tuple[int, int], count: int, kinds=(UnitType.FOOTMAN,)) -> tuple[Game, GameScene, list[int]]:
    game = Game("Warband selection", backend="mock", resolution=resolution, theme=build_theme(), save_dir=tmp_path / "saves")
    scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    ids = [scene.world.spawn_unit(0, kinds[i % len(kinds)], (8.5 + i % 12, 6.5 + i // 12)).id for i in range(count)]
    scene.select(ids)
    for _ in range(3):  # the panel is laid out on the first frame, the portraits drawn into it from the second
        game.tick(1 / 60)
    return game, scene, ids


def inside(rect, bounds) -> bool:
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    return bx <= x and by <= y and x + w <= bx + bw and y + h <= by + bh


def overlaps(rect, bounds) -> bool:
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    return x < bx + bw and bx < x + w and y < by + bh and by < y + h


def headings(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts if "units" in t["text"]]


@pytest.mark.parametrize("resolution", [(1280, 800), (1280, 720), (1200, 680)], ids=lambda r: f"{r[0]}x{r[1]}")
@pytest.mark.parametrize("count", [1, 12, 18, 26, 60])
def test_selections_fit_inside_the_panel_at_every_size(tmp_path, resolution, count) -> None:
    game, scene, ids = start(tmp_path, resolution, count)
    try:
        panel, card, minimap = scene.selection_panel.bounds, scene.card_panel.bounds, (0, 0, 0, 0)
        rects = [rect for _, rect in scene._portraits] + ([scene._page_tile] if scene._page_tile else [])
        strips = [(x, y + h + 2, w, 4) for x, y, w, h in rects]
        assert len(scene._portraits) == (1 if count == 1 else min(count, PORTRAITS_PER_PAGE if count <= PORTRAITS_PER_PAGE else PORTRAITS_PER_PAGE - 1)) or count == 1
        for rect in rects + strips:
            assert inside(rect, panel), (count, resolution, rect, panel)
            assert not overlaps(rect, card), (count, resolution, rect, card)
        assert (scene._page_tile is not None) == (count > PORTRAITS_PER_PAGE)
    finally:
        game._teardown()


def test_a_large_selection_pages_and_every_unit_can_be_picked(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1280, 800), 60)
    try:
        assert headings(game) == ["60 units · page 1 of 3"]
        seen = []
        for page in range(3):
            seen.extend(entity_id for entity_id, _ in scene._portraits)
            px, py, pw, ph = scene._page_tile
            game.backend.inject_click(int(px + pw / 2), int(py + ph / 2))
            game.tick(1 / 60)
        assert sorted(seen) == sorted(ids) and headings(game) == ["60 units · page 1 of 3"], "three pages wrap around"
        game.backend.inject_click(int(scene._page_tile[0] + 5), int(scene._page_tile[1] + 5))
        game.tick(1 / 60)
        assert headings(game) == ["60 units · page 2 of 3"]
        wanted, (x, y, w, h) = scene._portraits[7]
        game.backend.inject_click(int(x + w / 2), int(y + h / 2))
        game.tick(1 / 60)
        assert scene.selection == [wanted] and scene._page_tile is None
    finally:
        game._teardown()


def test_the_page_clamps_when_the_selection_shrinks_and_resets_when_it_changes(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1280, 800), 60)
    try:
        for _ in range(2):
            game.backend.inject_click(int(scene._page_tile[0] + 5), int(scene._page_tile[1] + 5))
            game.tick(1 / 60)
        assert headings(game) == ["60 units · page 3 of 3"]
        for entity_id in ids[30:]:  # thirty fall in battle
            del scene.world.units[entity_id]
        game.tick(1 / 60)
        assert scene.selection == ids[:30] and headings(game) == ["30 units · page 2 of 2"]
        scene.select(ids[:18])
        game.tick(1 / 60)
        assert headings(game) == ["18 units"] and scene._page_tile is None and len(scene._portraits) == 18
    finally:
        game._teardown()


def test_a_mixed_selection_shows_every_kind(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1200, 680), 20, kinds=(UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT, UnitType.CATAPULT))
    try:
        assert [entity_id for entity_id, _ in scene._portraits] == ids
        assert all(inside(rect, scene.selection_panel.bounds) for _, rect in scene._portraits)
    finally:
        game._teardown()
