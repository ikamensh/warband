"""Sites ordered and not yet begun, the settlement's plans and a builder's next sites, are the ghosts of their buildings
on the map: the picture drained of its colour, seen through, under whoever stands there, and without a caption."""

import sys
from pathlib import Path

import numpy as np
import pytest

from saga2d import Game
from warband.art import textures
from warband.art.textures import TILE
from warband.art.visual_lint import ImageStore
from warband.sim.model import tile_center
from warband.sim.rules import BUILT, BuildingType, Race, UnitType
from warband.ui.style import build_theme

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import visual_lint as screens  # noqa: E402


@pytest.fixture
def game(tmp_path):
    g = Game("Warband plans", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def test_a_row_of_farms_a_tile_apart_is_three_ghosts_under_a_fight_and_not_a_word(game) -> None:
    """Farms planned a tile apart, the row Shift-placing lays out, once captioned themselves "Planned FarmPlanned
    FarmPlanned Farm": each caption was wider than the pitch.  Each is now its farm seen through, with no caption, and
    a soldier fighting on one is drawn over it."""
    scene = screens.town(game)
    world = scene.world
    sites = [(9, 11), (12, 11), (15, 11)]  # where the run-together captions were seen, on 2026-09-24
    for site in sites:
        world.plan_building(scene.human, BuildingType.FARM, site)
    soldier = world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((13, 12)))  # on the middle farm's ground
    game.tick(1 / 60)
    assert [t["text"] for t in game.backend.texts if t["space"] == "world"] == []
    ghost = game.assets.image(textures.building_image(game, BuildingType.FARM, scene.human, scene.player.race, planned=True))
    drawn = sorted((image for image in game.backend.images if image["image"] == ghost), key=lambda image: image["x"])
    assert [image["x"] + image["width"] / 2 for image in drawn] == [(x + 1) * TILE for x, _y in sites]  # a farm is two tiles wide
    assert all(image["opacity"] < 0.5 for image in drawn)  # more of what is under it shows than of the ghost
    over = game.backend.sprites[scene.view.unit_sprite(soldier.id).sprite_id]["order"]
    assert drawn[1]["order"] < over


@pytest.mark.parametrize("race", list(Race), ids=lambda race: race.value)
def test_a_building_s_ghost_is_its_own_picture_without_colour_where_it_will_stand(game, race: Race) -> None:
    """Every building a race raises, as a plan: the building's own silhouette, grey all over, placed as the building
    will be."""
    store = ImageStore(game)
    for kind in BUILT:
        building, ghost = textures.building_image(game, kind, 0, race), textures.building_image(game, kind, 0, race, planned=True)
        own, drained = np.asarray(store.image(building).convert("RGBA")), np.asarray(store.image(ghost).convert("RGBA"))
        assert np.array_equal(drained[..., 3], own[..., 3]), kind
        seen = drained[..., 3] > 0
        assert (drained[..., 0] == drained[..., 1])[seen].all() and (drained[..., 1] == drained[..., 2])[seen].all(), kind
        assert textures.placements[ghost] == textures.placements[building], kind
