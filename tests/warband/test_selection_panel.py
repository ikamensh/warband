"""Large selections stay inside the selection panel (WB-018): a two-row grid, paging beyond it, every unit reachable by a click."""

import pytest

from saga2d import Game
from saga2d.testing import text_boxes
from warband.art.visual_lint import use_real_text_metrics
from warband.sim.rules import BLADES_BONUS, FORMATION_ARMOR, PLAYABLE_UNITS, UNITS, BuildingType, Race, UnitType, Upgrade
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


def test_the_card_shows_each_condition_with_the_seconds_it_has_left(tmp_path) -> None:
    """Rage and a bleeding wound (WB-062) stand beside the hit points as icons with their seconds left, a rival's
    archer's wound as much as anything: hovering one says what it does, and the speed the wound takes is marked in red
    beside the number it lowers.  Every kind of condition has its look."""
    from warband.sim.rules import BLEEDING, BUFFS
    from warband.ui.style import BAD
    from warband.ui.view import CONDITION_LOOKS

    assert set(CONDITION_LOOKS) == set(BUFFS)
    game = Game("Warband conditions", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        world = field()
        world.players[0].race = Race.ORC  # staged: an orc seat on the open field
        scene = GameScene(world, 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        grunt = world.spawn_unit(0, UnitType.ARCHER, (8.5, 6.5))  # an axethrower: light armour, so it can bleed
        world.hold([grunt.id])
        grunt.hp = grunt.max_hp // 3  # staged: hurt below half
        archer = world.spawn_unit(1, UnitType.ARCHER, (12.5, 6.5))
        world.attack([archer.id], grunt.id)
        while not grunt.conditions or len(grunt.conditions) < 2:
            game.tick(0.1)
        archer.hp = 0  # staged: the archer falls, so nothing strikes again
        scene.select([grunt.id])
        for _ in range(2):
            game.tick(1 / 60)
        texts = list(game.backend.texts)
        assert {"10s", f"{BLEEDING.duration:g}s"} <= {str(t["text"]) for t in texts}
        assert any(str(t["text"]).startswith("-") and tuple(t["color"]) == BAD for t in texts)  # the speed a wound takes
        game.backend.inject_mouse_move(*symbol_at(game, COLORS["bleeding"]))
        game.tick(1 / 60)
        assert scene.tooltip.startswith("Bleeding")
        game.backend.inject_mouse_move(*symbol_at(game, COLORS["rage"]))
        game.tick(1 / 60)
        assert scene.tooltip.startswith("Rage")
    finally:
        game.close()


def test_a_heavy_units_card_shows_the_wound_its_armour_turns(tmp_path) -> None:
    """Heavy armour is never bled (buffs.toml's ``spares``): its card shows the wound's icon struck out, and says so on
    hover; a light unit's card shows nothing of the kind."""
    from warband.ui.scene import SPARED_INK

    game = Game("Warband armour", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        footman, archer = (scene.world.spawn_unit(0, kind, (8.5 + 3 * i, 6.5)) for i, kind in enumerate((UnitType.FOOTMAN, UnitType.ARCHER)))
        scene.select([archer.id])
        for _ in range(2):
            game.tick(1 / 60)
        assert not any(tuple(p["color"]) == SPARED_INK for p in game.backend.polygons)
        scene.select([footman.id])
        for _ in range(2):
            game.tick(1 / 60)
        game.backend.inject_mouse_move(*symbol_at(game, SPARED_INK))
        game.tick(1 / 60)
        assert scene.tooltip == "Heavy armour: never bleeding"
    finally:
        game.close()


#: What the card says a unit wears and how it strikes: both sides of the damage table, in the words a player reads.
#: A new kind of unit — a neutral creature guarding a camp among them — states its own row here: the card is where
#: a player learns which of their units to send at it.
ARMOUR_NOTES = {
    UnitType.PEASANT: "Unarmoured · normal blows",
    UnitType.FOOTMAN: "Heavy armour · normal blows",
    UnitType.ARCHER: "Light armour · piercing blows",
    UnitType.KNIGHT: "Heavy armour · normal blows",
    UnitType.CATAPULT: "Unarmoured · siege blows",
    UnitType.FLYING_MACHINE: "Unarmoured · unarmed · flies",
    UnitType.CLERIC: "Unarmoured · normal blows",
    # Each race's own unit (WB-068), whose mechanic the card says as it says a flyer's.
    UnitType.GRYPHON: "Light armour · normal blows · flies",
    UnitType.SAPPER: "Unarmoured · siege blows",
    UnitType.TREANT: "Unarmoured · crush blows · through forest",
    UnitType.RUNE_GOLEM: "Heavy armour · normal blows",
}


def drawn(game: Game) -> set[str]:
    return {str(t["text"]) for t in game.backend.texts}


@pytest.mark.parametrize("unit_type", list(PLAYABLE_UNITS), ids=lambda u: u.value)
def test_the_card_names_what_a_selected_unit_wears_and_how_it_strikes(tmp_path, unit_type) -> None:
    """Armour class and attack type were reachable only by hovering the armour stat.  The pair is what a player
    acts on — armour alone is half of DAMAGE_FACTORS' two-sided table — so the card states both under the numbers."""
    game, scene, _ids = start(tmp_path, (1200, 680), 1, kinds=(unit_type,))
    try:
        assert scene.armour_notes == (ARMOUR_NOTES[unit_type],)
        assert ARMOUR_NOTES[unit_type] in drawn(game)
    finally:
        game.close()


def test_a_rival_s_unit_states_its_armour_as_readily_as_your_own(tmp_path) -> None:
    """The note is read off the unit's own kind, not off a seat: what a player must read to pick whom to send at a
    creature guarding a camp, which belongs to no player at all."""
    game, scene, _ids = start(tmp_path, (1280, 800), 1, kinds=(UnitType.PEASANT,))
    try:
        rival = scene.world.spawn_unit(1, UnitType.ARCHER, (9.5, 6.5))  # under the peasant's nose: a selection in fog is dropped
        scene.world.update_vision()
        scene.select([rival.id])
        for _ in range(2):
            game.tick(1 / 60)
        assert scene.armour_notes == (ARMOUR_NOTES[UnitType.ARCHER],)
    finally:
        game.close()


def test_a_building_s_card_says_it_is_fortified_whatever_it_is_doing(tmp_path) -> None:
    """A building's card fills up with what it is making, so its class goes in the corner beside the hit points,
    the one spot free in every state."""
    from warband.sim.rules import BuildingType

    game = Game("Warband armour", backend="mock", resolution=(1200, 680), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        hall = scene.world.player_buildings(0, BuildingType.TOWN_HALL)[0]
        scene.select([hall.id])
        for _ in range(3):
            game.tick(1 / 60)
        assert scene.armour_notes == ("Fortified",) and "Fortified" in drawn(game)
        scene.world.players[0].gold = 5000
        scene.train(UnitType.PEASANT)
        scene.world.set_auto_train(hall.id, UnitType.PEASANT, True)
        game.tick(1 / 60)
        assert scene.armour_notes == ("Fortified",), "a hall training endlessly still says what it wears"
    finally:
        game.close()


def test_a_selection_of_one_kind_names_the_armour_it_shares_and_a_mixed_one_does_not(tmp_path) -> None:
    """A blob shows portraits, not stats; the one stat a blob can honestly share is its armour class.  The pair
    does not fit that row: "60 units · page 1 of 3" and "· light armour · piercing blows" want 485 px of 442."""
    game, scene, _ids = start(tmp_path, (1200, 680), 18, kinds=(UnitType.FOOTMAN,))
    try:
        assert scene.armour_notes == ("heavy armour",)
        assert "18 units · heavy armour" == " · ".join(["18 units", *scene.armour_notes])
    finally:
        game.close()
    game, scene, _ids = start(tmp_path, (1200, 680), 18, kinds=(UnitType.FOOTMAN, UnitType.PEASANT))
    try:
        assert scene.armour_notes == ()
    finally:
        game.close()


def test_the_armour_stat_explains_what_lands_harder_on_it(tmp_path) -> None:
    """The card carries the fact; the hover carries the reading of the table from the wearer's side, which the
    tooltip never gave: an unarmoured unit says that piercing blows land half again as hard."""
    game, scene, ids = start(tmp_path, (1280, 800), 1, kinds=(UnitType.PEASANT,))
    try:
        game.backend.inject_mouse_move(*symbol_at(game, COLORS["armor"]))
        game.tick(1 / 60)
        assert "piercing blows land ×1.5" in scene.tooltip
        assert "armour is subtracted from every blow" in scene.tooltip
    finally:
        game.close()


def test_the_card_that_trains_a_unit_says_what_it_will_wear_and_strike(tmp_path) -> None:
    """A player choosing what to build decides before the unit exists: the train catalogue's tooltip carries the
    same pair the unit's own card will."""
    game, scene, ids = start(tmp_path, (1280, 800), 1, kinds=(UnitType.PEASANT,))
    try:
        scene.open_catalogue("train")
        game.tick(1 / 60)
        tips = {c.label: c.tooltip for c in scene.card}
        assert "light armour · piercing blows" in tips["Archer"]
        assert "heavy armour · normal blows" in tips["Footman"]
        assert "unarmoured · siege blows" in tips["Catapult"]
    finally:
        game.close()


def panel_texts(game: Game, scene: GameScene) -> list:
    """The boxes of the texts the panel drew into itself.

    The card and the production readout are drawn straight to the screen, not laid out, so nothing but their own
    width holds them to the panel: a text that starts inside it is the panel's.
    """
    x, y, w, h = scene.selection_panel.bounds
    return [b for b in text_boxes(game.backend)
            if b.space == "screen" and x <= b.left < x + w and y <= (b.top + b.bottom) / 2 < y + h]


def panel_scene(tmp_path, race, resolution=(1280, 800)) -> tuple[Game, GameScene]:
    """A match of *race* with one of every building standing, each far enough from the next to be its own.

    The mock backend measures text by the character; the card wraps and the assertions measure by the game's own
    faces, so the panel is checked against the widths a player sees."""
    game = Game("Warband panel", backend="mock", resolution=resolution, theme=build_theme(), save_dir=tmp_path / "saves")
    use_real_text_metrics(game)
    world = field()
    world.players[0].race = race
    for i, kind in enumerate(k for k in BuildingType if k is not BuildingType.GOLD_MINE):
        world.place_building(0, kind, (4 + i % 5 * 6, 6 + i // 5 * 6))
    scene = GameScene(world, 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    return game, scene


#: One race in the smallest window is the fast tier's share; every race in both windows takes a second each.
CARD_MATRIX = [pytest.param(race, resolution, id=f"{race.value}-{resolution[0]}x{resolution[1]}",
                            marks=() if (race, resolution) == (Race.HUMAN, (1200, 680)) else pytest.mark.slow)
               for race in Race for resolution in ((1280, 800), (1200, 680))]


@pytest.mark.parametrize("race, resolution", CARD_MATRIX)
def test_every_building_card_stays_inside_the_selection_panel(tmp_path, race, resolution) -> None:
    """A card line is written straight to the screen at a fixed column, so a long one used to run out of the panel
    and over the command card beside it: a site with no builder said so on the same line as its percentage, and the
    elves' Grove Mill and the humans' Blacksmith have summaries wider than the column.  Every race's every
    building, whole and going up, with and without a builder, is ten cards in three states, which is a second of
    drawing: the other races and the larger window are the slow tier's."""
    game, scene = panel_scene(tmp_path, race, resolution)
    try:
        peasant = scene.world.spawn_unit(0, UnitType.PEASANT, (2.5, 2.5))
        game.tick(1 / 60)  # the panel is laid out on the first frame and drawn into from the second
        for building in list(scene.world.buildings.values()):
            for progress, builder in ((1.0, None), (0.3, peasant.id), (0.3, None)):  # staged: whole, going up with a builder, and abandoned
                building.progress = building.info.build_time * progress
                building.builder = builder
                scene.select([building.id])
                game.tick(1 / 60)
                panel = scene.selection_panel.bounds
                for box in panel_texts(game, scene):
                    assert inside((box.left, box.top, box.width, box.height), panel), (building.type, progress, builder, str(box), panel)
    finally:
        game.close()


def test_an_empty_catalogue_says_why_inside_the_panel(tmp_path) -> None:
    """The build menu with nothing planned: its note was one line wider than the panel."""
    game, scene = panel_scene(tmp_path, Race.HUMAN, (1200, 680))
    try:
        scene.toggle_catalogue("build")
        for _ in range(2):
            game.tick(1 / 60)
        panel = scene.selection_panel.bounds
        boxes = panel_texts(game, scene)
        assert any("Nothing planned" in b.text for b in boxes)
        for box in boxes:
            assert inside((box.left, box.top, box.width, box.height), panel), (str(box), panel)
    finally:
        game.close()
