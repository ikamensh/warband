"""Painted building sheets: the runtime swap, its looks and fallbacks, and the tool's sheets."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sagaforge import restyle
from warband import textures
from warband.model import Building
from warband.rules import BuildingType, Race, UnitType
from warband.view import building_look

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import restyle as tool  # noqa: E402

CELL = (40, 60)
BUILT = [bt for bt in BuildingType if bt is not BuildingType.GOLD_MINE]


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
    for cache in (textures.restyled_buildings, textures.restyled_frames):
        cache.cache_clear()
    yield tmp_path
    for cache in (textures.restyled_buildings, textures.restyled_frames):
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
    assert textures.placements[key] == textures.Placement((20.0, 30.0), 7.5, 32.0)  # the sheet's cell over its scale, the anchor's drop, the footprint's front
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
    paint(painted, Race.HUMAN, "intact", BUILT[:-1])  # no church
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert textures.restyled_buildings(Race.HUMAN) is None
    assert any("stale" in str(w.message) and "church" in str(w.message) for w in caught)
    assert textures.placements[textures.building_image(game, BuildingType.FARM, 0, Race.HUMAN)].drop == 34


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
    site = Building(2, BuildingType.FARM, 0, 3, 3, 40, progress=20.0)
    assert building_look(site) == "intact"


def test_the_tool_lays_the_nine_buildings_out_on_one_sheet_with_a_shared_anchor() -> None:
    subject = tool.Buildings(Race.DWARF)
    sheet, images = subject.build_sheet()
    assert sheet.cols == 3 and sheet.rows == 3 and len(sheet.cells) == 9
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
    assert "3 rows x 3 columns" in text and "the Deep Hold:" in text and "the Brewhouse:" in text and "the Rune Shrine:" in text
    assert subject.row_names(sheet)[1] == "col 0 Bolt Tower, col 1 Timber Works, col 2 Forge"


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
    names = [s.name for s in tool.selected(parse.parse_args(["--race", "elf"]))]
    assert names[:3] == ["elf.peasant", "elf.peasant.gold", "elf.peasant.lumber"] and names[-3:] == ["elf.buildings.intact", "elf.buildings.active", "elf.buildings.damaged"]
    assert [s.name for s in tool.selected(parse.parse_args(["--buildings", "--looks", "damaged"]))] == ["human.buildings.damaged"]
    assert [s.name for s in tool.selected(parse.parse_args(["--units", "knight"]))] == ["human.knight"]
    with pytest.raises(SystemExit):
        tool.selected(parse.parse_args(["--buildings", "--looks", "ruined"]))
