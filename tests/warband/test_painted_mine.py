"""The gold mine is painted like the buildings (WB-038): four of its stand-ins, nobody's colour, and a worked mine
wears its active look only while the player sees it; out of sight it shows the look last seen."""

import pytest
from PIL import Image
from sagaforge import restyle

from saga2d import Game
from warband import textures
from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.scene import GameScene
from warband.style import build_theme
from warband.textures import TILE
from warband.view import building_look


def registered(game, monkeypatch) -> dict[str, Image.Image]:
    """Every PIL image the game registers from now on, by key."""
    images: dict[str, Image.Image] = {}
    original = game.assets.image_from_pil

    def spy(key, image):
        images[key] = image
        return original(key, image)

    monkeypatch.setattr(game.assets, "image_from_pil", spy)
    return images


def test_the_installed_sheet_paints_the_mines_the_map_draws_unrecoloured(game, monkeypatch) -> None:
    """Every painted variant is drawn as painted, standing on the line a three-tile footprint stands on."""
    images = registered(game, monkeypatch)
    sheet, frames = textures.restyled_mines()
    assert textures.mine_variants() == len(textures.PAINTED_MINES)
    for variant, stand_in in enumerate(textures.PAINTED_MINES):
        key = textures.mine_image(game, variant)
        assert key == textures.mine_key(stand_in)
        assert images[key].tobytes() == frames[key].tobytes(), "a mine is nobody's: no recolouring"
        placement = textures.placements[key]
        assert (placement.size, placement.drop, placement.front) == (sheet.logical_size, sheet.drop, 1.5 * TILE)


def test_the_mine_portrait_is_the_painting(game, monkeypatch) -> None:
    images = registered(game, monkeypatch)
    key = textures.portrait_image(game, BuildingType.GOLD_MINE, None)
    painted = textures.restyled_mines()[1][textures.mine_key(textures.PAINTED_MINES[0])]
    figure = painted.crop(painted.split()[3].getbbox())
    assert images[key].size[0] / images[key].size[1] == pytest.approx(figure.width / figure.height, rel=0.02)


def test_a_mine_is_active_only_while_worked() -> None:
    world = World(24, 18, [[Terrain.GRASS] * 24 for _ in range(18)], 2)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (7, 3))
    assert building_look(mine) == "intact" and building_look(mine, {mine.id}) == "active"
    assert building_look(mine, {mine.id + 1}) == "intact"


@pytest.fixture
def lit(tmp_path, monkeypatch):
    """The installed sheets, with a worked look beside the mine's: its intact frames brightened, so the two tell apart."""
    for sheet in textures.RESTYLED.iterdir():
        (tmp_path / sheet.name).symlink_to(sheet)
    sheet, frames = textures.restyled_mines()
    keys = [(textures.mine_key(variant, "active"), {"variant": variant}) for variant in textures.PAINTED_MINES]
    active = restyle.Sheet.layout(keys, cols=sheet.cols, cell=sheet.cell, origin=sheet.origin, scale=sheet.scale)
    brighter = {key: Image.merge("RGBA", [band.point(lambda c: min(255, c + 60)) for band in frames[textures.mine_key(tags["variant"])].split()[:3]]
                                 + [frames[textures.mine_key(tags["variant"])].split()[3]]) for key, tags in keys}
    restyle.save_frames(restyle.Cut(brighter, restyle.Registration(1.0, 0.0, 0.0), ()), active, tmp_path / "mine.active")
    monkeypatch.setattr(textures, "RESTYLED", tmp_path)
    textures.restyled_mines.cache_clear()
    yield
    textures.restyled_mines.cache_clear()


def test_a_worked_mine_is_lit_while_seen_and_out_of_sight_keeps_the_look_last_seen(tmp_path, lit) -> None:
    game = Game("Warband mine", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
        world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
        world.place_building(1, BuildingType.TOWN_HALL, (26, 18))
        mine = world.place_building(None, BuildingType.GOLD_MINE, (24, 12))
        scene = GameScene(world, seed=1, settings={"tutorial": False})
        scene.brains = []
        game.push(scene)
        world.reveal_all(scene.human)  # the player has seen the mine once; now only its own forces see
        for _ in range(3):
            game.tick(0.1)

        def look() -> str:
            return scene.view.building_sprite(mine.id).image.rsplit(".", 1)[-1]

        assert look() == "intact"
        miner = world.spawn_unit(1, UnitType.PEASANT, (24.5, 15.5))  # a rival's peasant, out of the player's sight
        world.harvest([miner.id], mine.id)
        for _ in range(60):
            game.tick(0.1)
            if miner.inside is not None:
                break
        assert miner.inside == mine.id
        assert look() == "intact", "a mine worked out of sight is lit on the player's map"
        scout = world.spawn_unit(scene.human, UnitType.SCOUT, (22.5, 11.5))
        for _ in range(3):
            game.tick(0.1)
        assert miner.inside == mine.id and look() == "active", "a worked mine in sight is not lit"
        world.stop([scout.id])
        world.move([scout.id], (3.5, 6.5))
        last_seen = look()
        for _ in range(60):
            game.tick(0.1)
            if not world.is_visible(scene.human, (25, 13)):
                break
            last_seen = look()
        shown = set()
        for _ in range(100):  # ten seconds of the miner going in and out, out of sight
            game.tick(0.1)
            shown.add(look())
        assert shown == {last_seen}, "out of sight the mine did not keep the look last seen"
    finally:
        game.close()
