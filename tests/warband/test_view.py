"""The map view: sprites in step with the model, draw order, fog and minimap images, textures."""

import numpy as np
import pytest
from PIL import Image

from saga2d import Game
from warband import textures
from warband.model import tile_center
from warband.rules import BuildingType, MapTheme, Terrain, UnitType
from warband.scene import new_game
from warband.style import build_theme
from warband.textures import TILE


@pytest.fixture
def play():
    game = Game("Warband View", backend="mock", resolution=(1280, 800), theme=build_theme())
    scene = new_game(seed=5)
    game.push(scene)
    game.tick(1 / 60)
    yield game, scene
    game._teardown()


def order_of(game: Game, sprite) -> int:
    return game.backend.sprites[sprite.sprite_id]["order"]


def test_every_tree_and_building_has_a_sprite_and_a_felled_tree_loses_it(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    trees = sum(1 for row in world.terrain for t in row if t is Terrain.TREES)
    assert len(view._trees) == trees
    assert set(view._buildings) == {b.id for b in world.buildings.values() if view._known(b)}
    pos = next(p for p in view._trees)
    world.terrain[pos[1]][pos[0]] = Terrain.GRASS
    game.tick(1 / 60)
    assert pos not in view._trees


def test_units_draw_in_front_of_what_stands_behind_them(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    front = world.spawn_unit(scene.human, UnitType.FOOTMAN, (hall.center[0], hall.y + hall.size + 0.6))
    behind = world.spawn_unit(scene.human, UnitType.FOOTMAN, (hall.center[0], hall.y - 0.6))
    game.tick(1 / 60)
    hall_order = order_of(game, view.building_sprite(hall.id))
    assert order_of(game, view.unit_sprite(front.id)) > hall_order > order_of(game, view.unit_sprite(behind.id))
    tree = min(view._trees, key=lambda p: abs(p[0] - hall.center[0]) + abs(p[1] - hall.center[1]))
    walker = world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((tree[0], tree[1] + 1)))
    game.tick(1 / 60)
    assert order_of(game, view.unit_sprite(walker.id)) > order_of(game, view._trees[tree])


def test_enemies_are_shown_only_where_the_player_can_see(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    far = world.spawn_unit(1, UnitType.FOOTMAN, (world.width - 5.5, world.height - 5.5))
    near = world.spawn_unit(1, UnitType.FOOTMAN, (hall.center[0] + 3, hall.center[1] + 3))
    world.update_vision()
    game.tick(1 / 60)
    assert view.unit_sprite(far.id) is None
    assert view.unit_sprite(near.id) is not None and view.unit_sprite(near.id).visible
    peasant = next(u for u in world.player_units(scene.human))
    world.harvest([peasant.id], world.mines()[0].id)
    for _ in range(200):
        game.tick(1 / 60)
        if peasant.inside is not None:
            break
    assert peasant.inside is not None and not view.unit_sprite(peasant.id).visible


def test_fog_image_is_clear_where_seen_dim_where_explored_and_black_elsewhere(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    fog = np.asarray(view._fog_image())
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    hx, hy = int(hall.center[0]), int(hall.center[1])
    assert fog[hy, hx, 3] == 0
    assert fog[world.height - 2, world.width - 2, 3] == 255
    unit = next(u for u in world.player_units(scene.human))
    unit.x, unit.y = hall.center[0] + 12, hall.center[1]
    world.update_vision()
    unit.x, unit.y = hall.center[0], hall.center[1]
    world.update_vision()
    fog = np.asarray(view._fog_image())
    assert fog[hy, hx + 12, 3] not in (0, 255)
    updates_before = game.backend.image_updates.get(game.assets.image(view.fog_key), 0)
    for _ in range(20):
        game.tick(1 / 60)
    assert game.backend.image_updates[game.assets.image(view.fog_key)] > updates_before


def test_minimap_image_marks_terrain_buildings_and_units(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    image = view._minimap_image()
    assert image.size == (world.width * 2, world.height * 2)
    pixels = np.asarray(image)
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert tuple(pixels[hall.y * 2, hall.x * 2, :3]) == world.players[scene.human].color
    mine = world.mines()[0]
    assert tuple(pixels[mine.y * 2, mine.x * 2, :3]) == (232, 196, 70)
    assert tuple(pixels[(world.height - 2) * 2, (world.width - 2) * 2, :3]) != (0, 0, 0)  # dark, not black


def test_unit_images_are_rendered_on_demand_per_facing_and_frame(play) -> None:
    game, scene = play
    key = textures.unit_image(game, UnitType.KNIGHT, 1, 6, "attack")
    assert game.assets.has_image(key) and textures.placements[key].drop == textures.DROP_UNIT
    assert textures.facing_index(0.0) == 0 and textures.facing_index(3.1416 / 2) == 2 and textures.facing_index(-3.1416 / 2) == 6
    other = textures.unit_image(game, UnitType.KNIGHT, 1, 6, "attack")
    assert other == key
    for building_type in BuildingType:
        if building_type is not BuildingType.GOLD_MINE:
            assert textures.placements[textures.building_image(game, building_type, 0)].size[0] >= textures.BUILDINGS[building_type].size * TILE * 0.8


def test_ground_chunks_cover_the_map_with_a_margin_and_sand_meets_water() -> None:
    from warband import mapgen

    world = mapgen.generate(seed=3)
    chunk = textures.ground_chunk(world.terrain_at, world.in_bounds, 0, 0, 1.0)
    assert chunk.size == (textures.CHUNK_PX, textures.CHUNK_PX)
    water = [(x, y) for y in range(world.height) for x in range(world.width) if world.terrain[y][x] is Terrain.WATER
             and any(world.in_bounds((x + dx, y)) and world.terrain[y][x + dx] is Terrain.GRASS for dx in (-1, 1))]
    assert water
    x, y = water[0]
    cx, cy = x // textures.CHUNK, y // textures.CHUNK
    img = textures.ground_chunk(world.terrain_at, world.in_bounds, cx, cy, 1.0)
    colours = {img.getpixel((px, py))[:3] for px in range((x - cx * textures.CHUNK) * TILE, (x - cx * textures.CHUNK + 3) * TILE)
               for py in range((y - cy * textures.CHUNK + 1) * TILE, (y - cy * textures.CHUNK + 2) * TILE)}
    palette = textures.PALETTES[MapTheme.SUMMER]
    assert palette.sand in colours and palette.water in colours


def test_portraits_are_tightly_framed_pictures(play) -> None:
    game, scene = play
    key = textures.portrait_image(game, UnitType.FOOTMAN, 0)
    w, h = game.backend.get_image_size(game.assets.image(key))
    assert max(w, h) == pytest.approx(128, abs=2)
    assert textures.portrait_image(game, BuildingType.GOLD_MINE, None) != key


def test_a_new_map_of_the_same_size_reuses_the_ground_fog_and_minimap_images(play) -> None:
    game, scene = play
    before = len(game.backend._image_sizes)
    scene.world = scene.world.from_dict(scene.world.to_dict())
    scene.view.reset(scene.world)
    game.tick(1 / 60)
    assert len(game.backend._image_sizes) == before
    assert Image  # the PIL import is what the view feeds update_image
