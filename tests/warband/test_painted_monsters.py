"""The neutral creatures are painted like the gold mine: a sheet each, and nobody's colour on any of them.

A creature's sheet is the one kind that is neither a unit's (recoloured per player) nor a building's
(one cell per building): it has every facing and frame of a unit sheet and none of the recolouring, so
these tests hold the swap, the staleness fallback and the *absence* of a team recolour.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sagaforge import restyle
from warband.art import monsters, textures
from warband.art.monsters import Monster
from warband.sim.rules import Race, UnitType

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import restyle as tool  # noqa: E402

CELL = (40, 60)
#: A frame of the synthetic sheets: a grey body with a patch of the first player's team colour on it.
#: Nothing may move that patch, because nothing recolours a creature.
BODY = (10, 25, 30, 50)
MARK = (14, 12, 24, 22)


def paint(folder: Path, monster: Monster, frames: tuple[str, ...] = textures.FRAMES) -> restyle.Sheet:
    """A synthetic painted sheet for one creature: every cell a grey body wearing a team-coloured
    patch, its brightness carrying the frame so two frames can be told apart."""
    keys = [(monsters.monster_key(monster, facing, frame), {"frame": frame, "facing": facing})
            for frame in frames for facing in range(textures.FACINGS)]
    sheet = restyle.Sheet.layout(keys, cols=textures.FACINGS, cell=CELL, origin=(20.0, 45.0), scale=2.0)
    images = {}
    for key, tags in keys:
        frame = Image.new("RGBA", CELL, (0, 0, 0, 0))
        grey = 100 + 15 * textures.FRAMES.index(tags["frame"]) + tags["facing"]
        frame.paste((grey, grey, grey, 255), BODY)
        frame.paste((*textures.team_color(0), 255), MARK)
        images[key] = frame
    restyle.save_frames(restyle.Cut(images, restyle.Registration(1.0, 0.0, 0.0), ()), sheet,
                        folder / monsters.monster_sheet(monster))
    return sheet


@pytest.fixture
def painted(tmp_path, monkeypatch):
    """An empty restyled folder the loader reads instead of the committed one."""
    monkeypatch.setattr(textures, "RESTYLED", tmp_path)
    monkeypatch.setattr(textures, "RESTYLED_ART", True)
    caches = (monsters.restyled_monster, monsters.monster_heads)
    for cache in caches:
        cache.cache_clear()
    yield tmp_path
    for cache in caches:
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


def test_a_creature_draws_its_painted_frames(game, painted, monkeypatch) -> None:
    """Every facing and frame comes off the sheet, placed by the sheet's own cell and anchor."""
    sheet = paint(painted, Monster.TROLL)
    images = registered(game, monkeypatch)
    for facing in range(textures.FACINGS):
        for frame in textures.FRAMES:
            key = monsters.monster_image(game, Monster.TROLL, facing, frame)
            assert key == f"monster.troll.{facing}.{frame}"
            assert np.asarray(images[key]).shape[:2] == CELL[::-1]
            placement = textures.placements[key]
            assert (placement.size, placement.drop, placement.front) == (sheet.logical_size, sheet.drop, 0.0)
    # The head is the figure's top over the anchor: the team patch starts 12 px into a cell anchored at 45.
    assert monsters.monster_heads(Monster.TROLL) == pytest.approx((16.5,) * textures.FACINGS)


def test_nothing_recolours_a_creature(game, painted, monkeypatch) -> None:
    """A creature belongs to nobody, so the team-coloured patch of the sheet reaches the game untouched.

    This is what separates a creature's sheet from a unit's: :func:`textures.unit_image` would turn that
    patch crimson for player 1, and a creature has no player to turn it for."""
    paint(painted, Monster.SPIDER)
    images = registered(game, monkeypatch)
    _, frames = monsters.restyled_monster(Monster.SPIDER)
    for facing in (0, 2, 5):
        key = monsters.monster_image(game, Monster.SPIDER, facing, "stand")
        assert images[key].tobytes() == frames[key].tobytes(), "a creature is nobody's: no recolouring"
        mark = np.asarray(images[key])[MARK[1] + 2, MARK[0] + 2, :3]
        assert tuple(mark) == textures.team_color(0), mark


def test_monster_image_takes_no_player() -> None:
    """The signature is the rule: there is no player to paint a creature for."""
    import inspect

    assert list(inspect.signature(monsters.monster_image).parameters) == ["game", "monster", "facing", "frame"]


def test_a_stale_sheet_warns_and_falls_back_to_the_render(game, painted) -> None:
    """A sheet that no longer holds every frame is ignored with a warning, not drawn half right."""
    paint(painted, Monster.GOLEM, frames=textures.FRAMES[:-1])  # no recover frame
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert monsters.restyled_monster(Monster.GOLEM) is None
    assert any("stale" in str(w.message) and "recover" in str(w.message) for w in caught)
    key = monsters.monster_image(game, Monster.GOLEM, 2, "stand")
    assert textures.placements[key].drop == textures.DROP_UNIT, "the low-poly render's own drop, not a sheet's"


def test_a_creature_without_a_sheet_renders_the_low_poly_stand_in(game, painted) -> None:
    for monster in Monster:
        assert monsters.restyled_monster(monster) is None
        key = monsters.monster_image(game, monster, 2, "stand")
        assert textures.placements[key].drop == textures.DROP_UNIT


def test_the_portrait_comes_from_the_painting(game, painted, monkeypatch) -> None:
    paint(painted, Monster.TROLL)
    images = registered(game, monkeypatch)
    image = images[monsters.monster_portrait_image(game, Monster.TROLL)]
    assert max(image.size) == 128 * game.backend.scale_factor
    # Cropped to the body and the patch above it: 20 px wide, 38 tall.
    assert image.width / image.height == pytest.approx(20 / 38, abs=0.05)


@pytest.mark.slow
def test_the_tool_lays_a_creature_out_facings_across_and_frames_down() -> None:
    """The sheet the painter is given: one creature, nine rows of eight, every frame on one anchor.

    Slow: building the sheet renders all seventy-two cells, which is over the fast tier's budget on a runner."""
    subject = tool.Monsters(Monster.TROLL)
    sheet, images = subject.build_sheet()
    assert subject.name == "monster.troll"
    assert (sheet.cols, sheet.rows) == (textures.FACINGS, len(textures.FRAMES)) and len(sheet.cells) == 72
    assert [c.key for c in sheet.cells[:2]] == ["monster.troll.0.stand", "monster.troll.1.stand"]
    for cell in sheet.cells:
        alpha = np.asarray(images[cell.key])[..., 3]
        assert alpha.max() > 0 and alpha[0].max() == 0 and alpha[-1].max() == 0 and alpha[:, 0].max() == 0 and alpha[:, -1].max() == 0
    text = subject.prompt(sheet)
    assert "9 rows x 8 columns" in text and "a wild troll" in text
    assert "no team colour anywhere on it" in text and "rider" in text
    # A unit's prompt names blue as the team colour to keep; a creature's forbids it outright.
    assert "no blue and no team colour anywhere" in text and tool.TEAM not in text
    assert subject.row_names(sheet)[0] == "standing at guard" and subject.cell_name(sheet.cells[3]).endswith("column 3")
    assert "saddle" in subject.judge and "eight legs" in tool.Monsters(Monster.SPIDER).inventory


def test_the_creatures_are_their_own_subjects() -> None:
    parse = tool.argparse.ArgumentParser()
    parse.add_argument("--race", default="human"); parse.add_argument("--units", default=None)
    parse.add_argument("--buildings", action="store_true"); parse.add_argument("--looks", default="intact,active,damaged")
    parse.add_argument("--mines", action="store_true"); parse.add_argument("--monsters", action="store_true")
    parse.add_argument("--creatures", default="all")
    assert [s.name for s in tool.selected(parse.parse_args(["--monsters"]))] == [f"monster.{m.value}" for m in Monster]
    assert [s.name for s in tool.selected(parse.parse_args(["--monsters", "--creatures", "golem"]))] == ["monster.golem"]
    assert all(s.stage == 0 for s in tool.selected(parse.parse_args(["--monsters"]))), "painted from the stand-ins"


@pytest.mark.slow
@pytest.mark.parametrize("monster", list(Monster))
def test_the_committed_sheet_is_free_of_edge_strays(monster: Monster) -> None:
    """Every creature is painted, and its 72 frames carry nothing the cut brought in from beyond the
    figure — the sibling of ``test_painted_sheets`` for the units.  Slow: every frame of every facing
    is examined, and the sheets are the biggest the tool makes."""
    painted = monsters.restyled_monster(monster)
    assert painted is not None, "this creature has no painted sheet, or a stale one"
    _, frames = painted
    assert len(frames) == textures.FACINGS * len(textures.FRAMES)
    stray = {key: restyle.strays(frame) for key, frame in frames.items()}
    assert {key: boxes for key, boxes in stray.items() if boxes} == {}
    field = {key: int(restyle.residue(np.asarray(frame)[..., 3]).sum()) for key, frame in frames.items()}
    assert {key: count for key, count in field.items() if count} == {}, "the key's faint field far from the figure"


@pytest.mark.slow
def test_a_unit_and_a_creature_are_laid_out_by_the_same_helper() -> None:
    """``figure_sheet`` builds both, so a unit's sheet is pinned here beside the creatures'.

    Slow: it builds two whole sheets, which is over the fast tier's budget on a runner.

    The two differ in nothing but which mesh a (frame, facing) is and what it is called: the cell is
    the widest and tallest any frame needs, the anchor is the same point of every cell, and the
    peasant carries four chop rows the others do not.  The committed sheets were cut against these
    layouts, so a change here makes every one of them stale."""
    unit = tool.Unit(Race.HUMAN, UnitType.PEASANT)
    sheet, images = unit.build_sheet()
    assert (sheet.cols, sheet.rows) == (textures.FACINGS, len(textures.FRAMES) + len(textures.CHOP_FRAMES))
    assert sheet.origin[0] == sheet.cell[0] / 2 and sheet.scale == 2.0
    assert sheet.find(frame="chop1", facing=3).key == textures.unit_key(UnitType.PEASANT, 0, 3, "chop1", None, Race.HUMAN)
    assert set(images) == {c.key for c in sheet.cells}
    installed, _ = textures.restyled_frames(Race.HUMAN, UnitType.PEASANT, None)
    assert (installed.cell, installed.origin, installed.scale) == (sheet.cell, sheet.origin, sheet.scale), "the committed sheet is stale"
    creature, _ = tool.Monsters(Monster.WOLF).build_sheet()
    assert creature.scale == sheet.scale and creature.origin[0] == creature.cell[0] / 2
