"""Large selections stay inside the selection panel (WB-018): a two-row grid, paging beyond it, every unit reachable by a click."""

import pytest

from saga2d import Game
from warband.sim.rules import BLADES_BONUS, FORMATION_ARMOR, UNITS, UnitType, Upgrade
from warband.ui.scene import PORTRAITS_PER_PAGE, GameScene
from warband.ui.icons import COLORS
from warband.ui.style import GOLD, build_theme

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
        rects = [rect for _, rect in scene.portraits] + ([scene.page_tile] if scene.page_tile else [])
        strips = [(x, y + h + 2, w, 4) for x, y, w, h in rects]
        assert len(scene.portraits) == (1 if count == 1 else min(count, PORTRAITS_PER_PAGE if count <= PORTRAITS_PER_PAGE else PORTRAITS_PER_PAGE - 1)) or count == 1
        for rect in rects + strips:
            assert inside(rect, panel), (count, resolution, rect, panel)
            assert not overlaps(rect, card), (count, resolution, rect, card)
        assert (scene.page_tile is not None) == (count > PORTRAITS_PER_PAGE)
    finally:
        game.close()


def test_a_large_selection_pages_and_every_unit_can_be_picked(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1280, 800), 60)
    try:
        assert headings(game) == ["60 units · page 1 of 3"]
        seen = []
        for page in range(3):
            seen.extend(entity_id for entity_id, _ in scene.portraits)
            px, py, pw, ph = scene.page_tile
            game.backend.inject_click(int(px + pw / 2), int(py + ph / 2))
            game.tick(1 / 60)
        assert sorted(seen) == sorted(ids) and headings(game) == ["60 units · page 1 of 3"], "three pages wrap around"
        game.backend.inject_click(int(scene.page_tile[0] + 5), int(scene.page_tile[1] + 5))
        game.tick(1 / 60)
        assert headings(game) == ["60 units · page 2 of 3"]
        wanted, (x, y, w, h) = scene.portraits[7]
        game.backend.inject_click(int(x + w / 2), int(y + h / 2))
        game.tick(1 / 60)
        assert scene.selection == [wanted] and scene.page_tile is None
    finally:
        game.close()


def test_the_page_clamps_when_the_selection_shrinks_and_resets_when_it_changes(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1280, 800), 60)
    try:
        for _ in range(2):
            game.backend.inject_click(int(scene.page_tile[0] + 5), int(scene.page_tile[1] + 5))
            game.tick(1 / 60)
        assert headings(game) == ["60 units · page 3 of 3"]
        for entity_id in ids[30:]:  # thirty fall in battle
            del scene.world.units[entity_id]
        game.tick(1 / 60)
        assert scene.selection == ids[:30] and headings(game) == ["30 units · page 2 of 2"]
        scene.select(ids[:18])
        game.tick(1 / 60)
        assert headings(game) == ["18 units"] and scene.page_tile is None and len(scene.portraits) == 18
    finally:
        game.close()


def test_a_mixed_selection_shows_every_kind(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1200, 680), 20, kinds=(UnitType.PEASANT, UnitType.FOOTMAN, UnitType.KNIGHT, UnitType.CATAPULT))
    try:
        assert [entity_id for entity_id, _ in scene.portraits] == ids
        assert all(inside(rect, scene.selection_panel.bounds) for _, rect in scene.portraits)
    finally:
        game.close()


def test_the_panel_says_in_words_what_a_unit_is_doing(tmp_path) -> None:
    """It spelt out the order's class name: an attack-move read "Attacking-moving" and a repair "Repair"."""
    from warband.sim.rules import BuildingType

    game = Game("Warband selection", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        world = scene.world
        footman = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 6.5))
        world.attack_move([footman.id], (30.5, 6.5))
        farm = world.place_building(0, BuildingType.FARM, (8, 10))
        farm.hp = farm.max_hp // 2  # staged: a raid's work
        peasant = world.spawn_unit(0, UnitType.PEASANT, (12.5, 12.5))
        world.repair([peasant.id], farm.id)
        ruin = world.place_building(1, BuildingType.FARM, (20, 10))
        ruin.abandoned = True  # staged: a rival's resignation, without playing one out
        wrecker = world.spawn_unit(0, UnitType.PEASANT, (18.5, 10.5))
        world.salvage([wrecker.id], ruin.id)
        said = {}
        for unit in (footman, peasant, wrecker):
            scene.select([unit.id])
            for _ in range(2):
                game.tick(1 / 60)
            said[unit.id] = {t["text"] for t in game.backend.texts}
        assert "Attack-moving" in said[footman.id] and "Repairing" in said[peasant.id] and "Salvaging" in said[wrecker.id]
    finally:
        game.close()


def test_shift_and_a_click_on_a_portrait_takes_that_unit_out_of_the_selection(tmp_path) -> None:
    game, scene, ids = start(tmp_path, (1280, 800), 3)
    try:
        chosen, (x, y, w, h) = scene.portraits[1]
        game.backend.inject_click(x + w / 2, y + h / 2, "left", shift=True)
        game.backend.inject_release(x + w / 2, y + h / 2, "left", shift=True)
        game.tick(1 / 60)
        assert sorted(scene.selection) == sorted(i for i in ids if i != chosen)
    finally:
        game.close()


def gold_marks(game: Game) -> list[str]:
    """The gold "+N" marks on the card, left to right: what research or the field added to a listed number."""
    marks = [t for t in game.backend.texts if str(t["text"]).startswith("+") and tuple(t["color"]) == GOLD]
    return [str(t["text"]) for t in sorted(marks, key=lambda t: t["x"])]


def symbol_at(game: Game, color) -> tuple[float, float]:
    """The middle of the symbol drawn in *color*: where a player would put the pointer to ask what it is."""
    facets = [p for p in game.backend.polygons if tuple(p["color"]) == color]
    points = [q for p in facets for q in p["points"]]
    return (min(q[0] for q in points) + max(q[0] for q in points)) / 2, (min(q[1] for q in points) + max(q[1] for q in points)) / 2


def test_research_and_the_shield_wall_are_marked_beside_the_number_they_raise(tmp_path) -> None:
    """A bigger number says nothing about why: what an upgrade or a comrade adds stands beside the listed number
    in gold, the way an RTS marks an upgraded stat, and the armour explains its own on hover."""
    game = Game("Warband upgrades", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        world = scene.world
        listed = UNITS[UnitType.FOOTMAN]
        alone = world.spawn_unit(0, UnitType.FOOTMAN, (8.5, 6.5))
        scene.select([alone.id])
        for _ in range(2):
            game.tick(1 / 60)
        assert gold_marks(game) == [] and str(listed.damage) in [str(t["text"]) for t in game.backend.texts]
        world.players[0].upgrades.add(Upgrade.BLADES_1)  # staged: the blacksmith's research, finished
        for side in (-1, 1):  # a comrade at each elbow, which is the shield wall's own armour
            world.spawn_unit(0, UnitType.FOOTMAN, (8.5 + side, 6.5))
        game.tick(1 / 60)
        assert gold_marks(game) == [f"+{BLADES_BONUS}", f"+{2 * FORMATION_ARMOR}"]
        game.backend.inject_mouse_move(*symbol_at(game, COLORS["armor"]))
        game.tick(1 / 60)
        assert "elbows" in scene.tooltip
    finally:
        game.close()
