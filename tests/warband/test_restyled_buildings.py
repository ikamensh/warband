"""Painted building sheets: the runtime swap, its looks and fallbacks, and the tool's sheets."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sagaforge import restyle
from warband.art import textures
from warband.sim.model import Building
from warband.sim.rules import BUILDINGS, BuildingType, Race, UnitType
from warband.sim.rules import BUILT as rules_built
from warband.ui.view import building_look

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import restyle as tool  # noqa: E402

CELL = (40, 60)
BUILT = [bt for bt in rules_built if bt not in textures.UNPAINTED]  # what the committed sheets hold


def paint(folder: Path, race: Race, look: str, types: list[BuildingType] = BUILT) -> None:
    """A synthetic painted sheet: every building a grey block with a blue banner, the look
    written into the block's brightness so frames of different looks can be told apart."""
    keys = [(textures.building_key(bt, 0, race, look), {"building": bt.value}) for bt in types]
    sheet = restyle.Sheet.layout(keys, cols=3, cell=CELL, origin=(20, 45), scale=2.0)
    frames = {}
    for key, _ in keys:
        frame = Image.new("RGBA", CELL, (0, 0, 0, 0))
        grey = {"intact": 160, "active": 200, "damaged": 90}[look]
        frame.paste((grey, grey, grey, 255), (10, 20, 30, 45))
        frame.paste((*textures.team_color(0), 255), (12, 10, 18, 20))
        frames[key] = frame
    restyle.save_frames(restyle.Cut(frames, restyle.Registration(1.0, 0.0, 0.0), ()), sheet, folder / f"{race.value}.buildings.{look}")


@pytest.fixture
def painted(tmp_path, monkeypatch):
    monkeypatch.setattr(textures, "RESTYLED", tmp_path)
    monkeypatch.setattr(textures, "RESTYLED_ART", True)
    for cache in (textures.restyled_buildings, textures.restyled_frames, textures.stride_heads):
        cache.cache_clear()
    yield tmp_path
    for cache in (textures.restyled_buildings, textures.restyled_frames, textures.stride_heads):
        cache.cache_clear()


def registered(game, monkeypatch) -> dict[str, Image.Image]:
    """Every PIL image the game registers from now on, by key."""
    images: dict[str, Image.Image] = {}
    original = game.assets.image_from_pil

    def spy(key, image):
        images[key] = image
        return original(key, image)

    monkeypatch.setattr(game.assets, "image_from_pil", spy)
    return images


def test_building_image_uses_the_painted_frame_recoloured_to_the_player(game, painted, monkeypatch) -> None:
    paint(painted, Race.ORC, "intact")
    images = registered(game, monkeypatch)
    key = textures.building_image(game, BuildingType.FARM, 1, Race.ORC)
    assert key == "building.orc.farm.intact.1"
    # The sheet's cell over its scale, the anchor's drop, the footprint's front, the banner's top over the anchor.
    assert textures.placements[key] == textures.Placement((20.0, 30.0), 7.5, 32.0, head=17.5)
    frame = np.asarray(images[key])
    assert frame.shape[:2] == CELL[::-1]
    banner, wall = frame[15, 15, :3], frame[30, 20, :3]
    assert banner[0] > banner[2] + 80, banner  # blue became crimson
    assert abs(int(wall[0]) - int(wall[2])) < 8, wall  # grey stayed grey


def test_a_look_without_a_painted_sheet_falls_back_to_the_intact_painting(game, painted, monkeypatch) -> None:
    paint(painted, Race.ELF, "intact")
    paint(painted, Race.ELF, "damaged")
    images = registered(game, monkeypatch)
    damaged = textures.building_image(game, BuildingType.TOWER, 0, Race.ELF, "damaged")
    active = textures.building_image(game, BuildingType.TOWER, 0, Race.ELF, "active")
    assert damaged == "building.elf.tower.damaged.0" and active == "building.elf.tower.intact.0"
    assert np.asarray(images[damaged])[30, 20, 0] == 90 and np.asarray(images[active])[30, 20, 0] == 160
    with pytest.raises(ValueError):
        textures.building_image(game, BuildingType.TOWER, 0, Race.ELF, "ruined")


def test_a_race_without_painted_buildings_renders_the_low_poly_building(game, painted) -> None:
    key = textures.building_image(game, BuildingType.CHURCH, 1, Race.DWARF, "damaged")
    assert key == "building.dwarf.church.intact.1"  # the render has one look
    assert textures.placements[key].drop == 50  # a 3x3 building's own drop, not a sheet's


def test_a_stale_sheet_warns_and_is_ignored(game, painted) -> None:
    paint(painted, Race.HUMAN, "intact", [bt for bt in BUILT if bt is not BuildingType.CHURCH])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert textures.restyled_buildings(Race.HUMAN) is None
    assert any("stale" in str(w.message) and "church" in str(w.message) for w in caught)
    assert textures.placements[textures.building_image(game, BuildingType.FARM, 0, Race.HUMAN)].drop == 34


def test_an_exempted_building_is_drawn_low_poly_beside_the_painted_ones(game, painted, monkeypatch) -> None:
    """A building exempted from painting is missing from the sheets without making them stale: they stay in use for
    the others, and it is the low-poly render in every look (the Aether Vault until it was painted in)."""
    monkeypatch.setitem(textures.UNPAINTED, BuildingType.VAULT, ("a test's", "2026-09-25"))
    without = [bt for bt in BUILT if bt is not BuildingType.VAULT]
    paint(painted, Race.HUMAN, "intact", without)
    paint(painted, Race.HUMAN, "active", without)
    sheet = textures.restyled_buildings(Race.HUMAN)
    assert sheet is not None
    assert textures.placements[textures.building_image(game, BuildingType.FARM, 0, Race.HUMAN)].drop == sheet[0].drop  # painted
    vault = textures.building_image(game, BuildingType.VAULT, 0, Race.HUMAN, "damaged")
    assert vault == "building.human.vault.intact.0" and textures.placements[vault].front == textures.TILE  # a 2x2 render's own
    assert textures.has_look(Race.HUMAN, "active") and not textures.has_look(Race.HUMAN, "active", BuildingType.VAULT)


def test_portraits_come_from_the_painted_frame(game, painted, monkeypatch) -> None:
    paint(painted, Race.ORC, "intact")
    images = registered(game, monkeypatch)
    key = textures.portrait_image(game, BuildingType.STABLES, 1, Race.ORC)
    image = images[key]
    assert max(image.size) == 128 * game.backend.scale_factor
    assert image.width / image.height == pytest.approx(20 / 35, abs=0.05)  # cropped to the block and its banner
    unit = textures.portrait_image(game, UnitType.FOOTMAN, 1, Race.ORC)  # no painted footman here: the low-poly render, framed the same way
    assert max(images[unit].size) == 128 * game.backend.scale_factor


def test_building_look_follows_health_and_work() -> None:
    hall = Building(1, BuildingType.TOWN_HALL, 0, 3, 3, 1200, progress=60.0)
    assert building_look(hall) == "intact"
    hall.queue.append(UnitType.PEASANT)
    assert building_look(hall) == "active"
    hall.hp = 500
    assert building_look(hall) == "damaged"
    site = Building(2, BuildingType.FARM, 0, 3, 3, 40, progress=5.0)
    assert building_look(site) == "founded"  # WB-048: the first half of construction
    site.progress = site.info.build_time * 0.6
    assert building_look(site) == "raised"


def test_the_tool_lays_the_painted_buildings_out_three_to_a_row_with_a_shared_anchor() -> None:
    subject = tool.Buildings(Race.DWARF)
    sheet, images = subject.build_sheet()
    assert sheet.cols == 3 and sheet.rows == 4 and len(sheet.cells) == 10
    assert [c.tags["building"] for c in sheet.cells] == [bt.value for bt in BUILT]
    for cell in sheet.cells:
        alpha = np.asarray(images[cell.key])[..., 3]
        assert alpha.max() > 0 and alpha[0].max() == 0 and alpha[-1].max() == 0 and alpha[:, 0].max() == 0 and alpha[:, -1].max() == 0
    hall = np.asarray(images[sheet.find(building="town_hall").key])[..., 3]
    farm = np.asarray(images[sheet.find(building="farm").key])[..., 3]
    # Both stand on the anchor: each yard (inset a tenth of a tile) reaches half its size below it.
    assert np.flatnonzero(hall.any(axis=1)).max() == pytest.approx(sheet.origin[1] + 1.4 * textures.TILE * sheet.scale, abs=4)
    assert np.flatnonzero(farm.any(axis=1)).max() == pytest.approx(sheet.origin[1] + 0.9 * textures.TILE * sheet.scale, abs=4)
    text = subject.prompt(sheet)
    assert "4 rows x 3 columns" in text and "the Deep Hold:" in text and "the Brewhouse:" in text and "the Rune Shrine:" in text
    assert subject.row_names(sheet)[1] == "col 0 Bolt Tower, col 1 Timber Works, col 2 Forge"


def test_the_tool_lays_four_mines_out_on_a_three_by_four_sheet_that_image_models_paint_as_it_is() -> None:
    """The painters keep a layout only on a canvas of their own shapes: the mine sheet is 3:4, and the canvas asked
    for is the one nearest a sheet's shape. No cell is cut off, none is recoloured blue."""
    subject = tool.Mines()
    sheet, images = subject.build_sheet()
    assert (sheet.cols, sheet.rows) == (2, 2) and [c.tags["variant"] for c in sheet.cells] == list(textures.PAINTED_MINES)
    assert sheet.size[0] / sheet.size[1] == pytest.approx(3 / 4, rel=0.01) and tool.aspect_ratio(sheet.size) == "3:4"
    assert tool.aspect_ratio((1000, 1000)) == "1:1" and tool.aspect_ratio((1080, 606)) == "16:9"
    for cell in sheet.cells:
        alpha = np.asarray(images[cell.key])[..., 3]
        assert alpha.max() > 0 and alpha[0].max() == 0 and alpha[-1].max() == 0 and alpha[:, 0].max() == 0 and alpha[:, -1].max() == 0
    text = subject.prompt(sheet)
    assert "2 rows x 2 columns" in text and "no blue" in text

def test_a_look_sheet_is_built_from_the_installed_intact_painting(painted, monkeypatch) -> None:
    monkeypatch.setattr(tool, "RESTYLED", painted)
    with pytest.raises(FileNotFoundError, match="orc.buildings.intact"):
        tool.Buildings(Race.ORC, "damaged").build_sheet()
    paint(painted, Race.ORC, "intact")
    sheet, images = tool.Buildings(Race.ORC, "damaged").build_sheet()
    assert sheet.cell == CELL and sheet.origin == (20, 45)
    assert set(images) == {textures.building_key(bt, 0, Race.ORC, "damaged") for bt in BUILT}
    text = tool.Buildings(Race.ORC, "damaged").prompt(sheet)
    assert "battle-damaged" in text and "the Great Hall: the keep's roof is broken open" in text and "smoke" in text


def test_selection_defaults_to_every_subject_of_the_race() -> None:
    parse = tool.argparse.ArgumentParser()
    parse.add_argument("--race", default="human"); parse.add_argument("--units", default=None)
    parse.add_argument("--buildings", action="store_true"); parse.add_argument("--looks", default="intact,active,damaged")
    parse.add_argument("--mines", action="store_true"); parse.add_argument("--monsters", action="store_true")
    parse.add_argument("--lairs", action="store_true"); parse.add_argument("--workings", action="store_true")
    parse.add_argument("--creatures", default="all"); parse.add_argument("--add", default=None)
    names = [s.name for s in tool.selected(parse.parse_args(["--race", "elf"]))]
    assert names[:3] == ["elf.peasant", "elf.peasant.gold", "elf.peasant.lumber"] and names[-3:] == ["elf.buildings.intact", "elf.buildings.active", "elf.buildings.damaged"]
    assert [s.name for s in tool.selected(parse.parse_args(["--buildings", "--looks", "damaged"]))] == ["human.buildings.damaged"]
    added = tool.selected(parse.parse_args(["--buildings", "--looks", "intact,raised", "--add", "vault"]))
    assert [(s.name, s.sheet, s.stage) for s in added] == [("human.buildings.intact.vault", "human.buildings.intact", 0),
                                                           ("human.buildings.raised.vault", "human.buildings.raised", 1)]
    assert [s.name for s in tool.selected(parse.parse_args(["--units", "knight"]))] == ["human.knight"]
    assert [s.name for s in tool.selected(parse.parse_args(["--mines"]))] == ["mine.intact", "mine.active"], "a mine has no damaged look"
    assert [s.name for s in tool.selected(parse.parse_args(["--lairs"]))] == ["lair.intact", "lair.damaged"], "a den has no active look"
    workings = tool.selected(parse.parse_args(["--workings"]))
    assert [s.name for s in workings] == ["workings.intact", "workings.active"] and [s.stage for s in workings] == [1, 2], \
        "painted over the mine painting, then lit over their own"
    with pytest.raises(SystemExit):
        tool.selected(parse.parse_args(["--buildings", "--looks", "ruined"]))


def installed_without_the_vault(folder: Path, race: Race, look: str) -> dict[str, Image.Image]:
    """*race*'s committed painting in *look* copied into *folder* as it was before the vault was painted in."""
    sheet, frames = restyle.load_frames(textures.RESTYLED / f"{race.value}.buildings.{look}")
    keys = [(c.key, c.tags) for c in sheet.cells if c.tags["building"] != "vault"]
    before = restyle.Sheet.layout(keys, cols=sheet.cols, cell=sheet.cell, origin=sheet.origin, scale=sheet.scale)
    frames = {key: frames[key] for key, _ in keys}
    restyle.save_frames(restyle.Cut(frames, restyle.Registration(1.0, 0.0, 0.0), ()), before, folder / f"{race.value}.buildings.{look}")
    return restyle.load_frames(folder / f"{race.value}.buildings.{look}")[1]


def same_picture(a: Image.Image, b: Image.Image) -> bool:
    """The same pixels where either is seen (a sheet written to disk keeps no colour under a clear pixel)."""
    a, b = np.asarray(a), np.asarray(b)
    seen = (a[..., 3] > 0) | (b[..., 3] > 0)
    return bool(np.array_equal(a[seen], b[seen]))


def test_an_added_building_is_painted_alone_on_the_sheets_cells_and_cut_in_beside_the_others(tmp_path, monkeypatch) -> None:
    """``--add``: a building new to the game is painted into the installed sheets, whose other paintings stay as they
    are. Its stand-in is rendered on the cells of the sheet it joins, alone; the cut appends it to that sheet; its other
    looks are painted from its intact painting, as every building's are."""
    monkeypatch.setattr(tool, "RESTYLED", tmp_path)
    before = installed_without_the_vault(tmp_path, Race.DWARF, "intact")
    subject = tool.Buildings(Race.DWARF, "intact", (BuildingType.VAULT,))
    sheet, images = subject.build_sheet()
    base = restyle.Sheet.load(tmp_path / "dwarf.buildings.intact")
    assert (sheet.cell, sheet.origin, sheet.scale, len(sheet.cells)) == (base.cell, base.origin, base.scale, 1)
    alpha = np.asarray(images["building.dwarf.vault.intact.0"])[..., 3]
    assert alpha.max() > 0 and alpha[0].max() == 0 and alpha[-1].max() == 0 and alpha[:, 0].max() == 0 and alpha[:, -1].max() == 0
    text = subject.prompt(sheet)
    assert "one building of one faction" in text and "the Rune Vault:" in text and "#A868F0" in text

    tool.install(subject, restyle.Cut(images, restyle.Registration(1.0, 0.0, 0.0), ()), sheet)
    whole, frames = restyle.load_frames(tmp_path / "dwarf.buildings.intact")
    assert [c.tags["building"] for c in whole.cells] == [bt.value for bt in BUILT] and whole.cols == base.cols
    assert all(frames[key].tobytes() == frame.tobytes() for key, frame in before.items()), "the others stay as they were"
    assert same_picture(frames["building.dwarf.vault.intact.0"], images["building.dwarf.vault.intact.0"])

    installed_without_the_vault(tmp_path, Race.DWARF, "raised")
    look = tool.Buildings(Race.DWARF, "raised", (BuildingType.VAULT,))
    sheet, images = look.build_sheet()
    assert list(images) == ["building.dwarf.vault.raised.0"]
    assert same_picture(images["building.dwarf.vault.raised.0"], frames["building.dwarf.vault.intact.0"])
    assert "the chains lie slack" in look.prompt(sheet)
    tool.install(look, restyle.Cut(images, restyle.Registration(1.0, 0.0, 0.0), ()), sheet)
    again = tool.Buildings(Race.DWARF, "raised", (BuildingType.VAULT,))  # painting it again replaces its cell
    tool.install(again, restyle.Cut(images, restyle.Registration(1.0, 0.0, 0.0), ()), sheet)
    assert [c.tags["building"] for c in restyle.Sheet.load(tmp_path / "dwarf.buildings.raised").cells] == [bt.value for bt in BUILT]


def test_a_site_is_cut_at_its_painted_scale_added_or_not() -> None:
    """A site's height says nothing of its scale: the cut keeps the painter's, for a building added to the sheets too."""
    for add in ((), (BuildingType.VAULT,)):
        assert not tool.rescales(tool.Buildings(Race.ELF, "founded", add)) and not tool.rescales(tool.Buildings(Race.ELF, "raised", add))
        assert tool.rescales(tool.Buildings(Race.ELF, "damaged", add))
    assert not tool.rescales(tool.Workings()) and tool.rescales(tool.Mines())


def test_an_added_building_that_outgrows_the_sheets_cells_asks_for_a_whole_repaint(painted, monkeypatch) -> None:
    monkeypatch.setattr(tool, "RESTYLED", painted)
    paint(painted, Race.ORC, "intact", [bt for bt in BUILT if bt is not BuildingType.VAULT])  # cells far too small
    with pytest.raises(ValueError, match="outgrows"):
        tool.Buildings(Race.ORC, "intact", (BuildingType.VAULT,)).build_sheet()


def test_the_workings_sheet_is_the_mine_painting_laid_out_a_row_to_a_wealth() -> None:
    """WB-071's worked-out and poor faces are painted over the installed mine painting: the sheet the painter gets is
    that painting in the mine's own cells, the worked row above the poor one, and the prompt names both."""
    subject = tool.Workings()
    sheet, images = subject.build_sheet()
    mines, painted = tool.restyle.load_frames(tool.RESTYLED / "mine.intact")
    assert (sheet.cell, sheet.origin, sheet.scale) == (mines.cell, mines.origin, mines.scale)
    assert [c.key for c in sheet.cells if c.row == 0] == [textures.mine_key(v, "intact", "worked") for v in textures.PAINTED_MINES]
    assert [c.key for c in sheet.cells if c.row == 1] == [textures.mine_key(v, "intact", "poor") for v in textures.PAINTED_MINES]
    assert all(images[textures.mine_key(v, "intact", w)].tobytes() == painted[textures.mine_key(v)].tobytes()
               for v in textures.PAINTED_MINES for w in ("worked", "poor"))
    text = subject.prompt(sheet)
    assert "row 0 is HALF WORKED OUT" in text and "row 1 is A POOR OLD SEAM" in text and "no blue" in text
