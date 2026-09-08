"""The map view: sprites in step with the model, draw order, fog and minimap images, textures."""

import numpy as np
import pytest
from PIL import Image

from saga2d import Game
from warband import textures
from warband.model import tile_center
from warband.rules import BuildingType, MapTheme, Resource, Terrain, UnitType
from warband.scene import GameScene, new_game
from warband.view import WATER_PERIOD
from warband import mapgen
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
    tree_sprite_id = view._trees[pos].sprite_id
    world.terrain[pos[1]][pos[0]] = Terrain.GRASS
    game.tick(1 / 60)
    assert pos not in view._trees
    assert tree_sprite_id not in game.backend.sprites  # Includes its baked shade and litter.


def test_forest_uses_twenty_stable_variants_across_save_reload(play) -> None:
    """A real map uses the full forest asset bank without reshuffling on load."""
    game, scene = play
    before = {pos: sprite.image for pos, sprite in scene.view._trees.items()}
    assert len(set(before.values())) >= 20
    scene.view.reset(scene.world.from_dict(scene.world.to_dict()))
    assert {pos: sprite.image for pos, sprite in scene.view._trees.items()} == before


def test_harvesting_worker_swings_axe_then_carries_wood(play) -> None:
    """Harvest orders drive all swing poses, face the tree, then show carried logs."""
    game, scene = play
    world = scene.world
    tree, approach = next(
        (pos, (pos[0] + dx, pos[1] + dy))
        for pos in scene.view._trees for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if world.passable(pos[0] + dx, pos[1] + dy)
    )
    worker = world.spawn_unit(scene.human, UnitType.PEASANT, tile_center(approach))
    world.harvest([worker.id], tree)
    poses = set()
    checked_pause = False
    for _ in range(420):
        game.tick(1 / 60)
        sprite = scene.view.unit_sprite(worker.id)
        if worker.state == "chop" and worker.carrying is None:
            poses.add(sprite.image.rsplit(".", 1)[-1])
            if not checked_pause:
                before = sprite.image
                scene.paused = True
                for _ in range(20):
                    game.tick(1 / 60)
                assert sprite.image == before
                scene.paused = False
                checked_pause = True
        if worker.carrying is Resource.LUMBER:
            assert ".lumber." in sprite.image
            assert sprite.image.rsplit(".", 1)[-1] in textures.FRAMES
            break
    assert worker.carrying is Resource.LUMBER
    assert poses == set(textures.CHOP_FRAMES)
    assert world.terrain_at(tree) is Terrain.GRASS


def test_idle_opening_prepares_later_animation_images(play) -> None:
    """The incremental warmer advances beyond its first yielded image."""
    game, scene = play
    key = textures.unit_key(UnitType.PEASANT, 0, 1, "walk2")
    for _ in range(10):
        game.tick(1 / 60)
    assert game.assets.has_image(key)


def test_crystal_mines_render_all_variants_and_keep_their_variant_on_reload(play) -> None:
    """Every mine variant can enter the atlas, with placement stable across saves."""
    game, scene = play
    keys = {textures.mine_image(game, i) for i in range(20)}
    assert len(keys) == 20
    for key in keys:
        width, height = game.backend.get_image_size(game.assets.image(key))
        assert width >= TILE * 2 and height >= TILE * 2
    mines = scene.world.mines()
    before = {mine.id: scene.view.building_sprite(mine.id).image for mine in mines if scene.view.building_sprite(mine.id)}
    scene.view.reset(scene.world.from_dict(scene.world.to_dict()))
    assert {bid: scene.view.building_sprite(bid).image for bid in before} == before


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
    for unit_type in UnitType:  # every unit, frame and carry variant renders (a missing colour name would raise here)
        for frame in textures.FRAMES:
            textures.unit_image(game, unit_type, 1, 3, frame)
    for carrying in (Resource.GOLD, Resource.LUMBER):
        textures.unit_image(game, UnitType.PEASANT, 0, 2, "walk1", carrying)
    for theme in MapTheme:
        textures.register_theme(game, theme)
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


@pytest.mark.parametrize("theme", list(MapTheme))
@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_forest_and_clearing_share_the_same_ground_across_chunk_edges(theme, scale) -> None:
    """Felling removes the tree sprite, leaving grass rather than a baked dark square."""
    world = mapgen.generate(seed=3, width=24, height=24, theme=theme)
    forest = [textures.ground_chunk(world.terrain_at, world.in_bounds, cx, cy, scale, theme)
              for cx, cy in ((0, 0), (1, 0), (1, 1))]
    assert any(terrain is Terrain.TREES for row in world.terrain for terrain in row)
    for row in world.terrain:
        for x, terrain in enumerate(row):
            if terrain is Terrain.TREES:
                row[x] = Terrain.GRASS
    cleared = [textures.ground_chunk(world.terrain_at, world.in_bounds, cx, cy, scale, theme)
               for cx, cy in ((0, 0), (1, 0), (1, 1))]
    for before, after in zip(forest, cleared):
        np.testing.assert_array_equal(np.asarray(before), np.asarray(after))


def test_portraits_are_tightly_framed_pictures(play) -> None:
    game, scene = play
    key = textures.portrait_image(game, UnitType.FOOTMAN, 0)
    w, h = game.backend.get_image_size(game.assets.image(key))
    assert max(w, h) == pytest.approx(128, abs=2)
    assert textures.portrait_image(game, BuildingType.GOLD_MINE, None) != key


def test_a_new_map_of_the_same_size_reuses_the_ground_fog_and_minimap_images(play) -> None:
    game, scene = play
    before = len(game.backend._image_sizes)
    keys = [sprite.image for sprite in scene.view._ground] + [scene.view.fog_key, scene.view.minimap_key]
    handles = [game.assets.image(key) for key in keys]
    scene.world = scene.world.from_dict(scene.world.to_dict())
    scene.view.reset(scene.world)
    assert len(game.backend._image_sizes) == before
    game.tick(1 / 60)  # the unit warmer may now add animation frames
    assert [game.assets.image(key) for key in keys] == handles
    assert Image  # the PIL import is what the view feeds update_image


def test_a_site_shows_the_building_rising_and_a_battered_building_smokes_then_burns(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    site = world.place_building(scene.human, BuildingType.FARM, (hall.x + 5, hall.y + 4), done=False)
    game.tick(1 / 60)
    assert view._building_keys[site.id] == "site.2"
    site.progress = site.info.build_time * 0.6
    game.tick(1 / 60)
    assert view._building_keys[site.id] == textures.building_key(BuildingType.FARM, scene.human) and view.building_sprite(site.id).opacity == 150
    site.progress = site.info.build_time
    site.hp = site.max_hp
    game.tick(1 / 60)
    assert view.building_sprite(site.id).opacity == 255 and site.id not in view._smoke
    site.hp = site.max_hp // 3
    game.tick(1 / 60)
    assert site.id in view._smoke
    for _ in range(30):
        game.tick(1 / 60)
    assert view._smoke[site.id].particle_count > 0 and site.id not in view._fire
    site.hp = site.max_hp // 5  # under a quarter it blazes as well
    for _ in range(30):
        game.tick(1 / 60)
    assert site.id in view._fire and view._fire[site.id].particle_count > 0
    site.hp = site.max_hp
    game.tick(1 / 60)
    assert site.id not in view._smoke and site.id not in view._fire


def flood(world, x0: int, y0: int, size: int = 3) -> None:
    for y in range(y0, y0 + size):
        for x in range(x0, x0 + size):
            world.terrain[y][x] = Terrain.WATER
            world._blocked[y * world.width + x] = 1


def test_water_moves_once_its_phases_are_painted_while_land_stays_still() -> None:
    game = Game("Warband View", backend="mock", resolution=(1280, 800), theme=build_theme())
    world = mapgen.generate(seed=5, width=48, height=40, players=2)
    flood(world, 2, 2)
    scene = GameScene(world, 5)
    game.push(scene)
    game.tick(1 / 60)
    view = scene.view
    assert view._chunk_has_water(0) and len(view._ground_keys[0]) == textures.WATER_PHASES
    land = next(i for i, keys in enumerate(view._ground_keys) if len(keys) == 1)
    first = view._ground[0].image
    while view._water_pending:  # the other phases are painted one per frame; the water waits on phase 0 meanwhile
        assert view._ground[0].image == first
        game.tick(1 / 60)
    assert all(game.assets.has_image(key) for key in view._ground_keys[0])
    for _ in range(int(WATER_PERIOD * 60) + 2):
        game.tick(1 / 60)
    assert view._ground[0].image != first and view._ground[0].image in view._ground_keys[0]
    assert view._ground[land].image == view._ground_keys[land][0]
    # A loaded map of the same size may have its water elsewhere: the chunks are classified again.
    other = mapgen.generate(seed=6, width=48, height=40, players=2)
    flood(other, 20, 20)
    view.reset(other)
    for index, keys in enumerate(view._ground_keys):
        assert (len(keys) > 1) == view._chunk_has_water(index)
    assert len(view._ground_keys[view._ground_keys.index(view._chunk_keys(2 * 6 + 2))]) == textures.WATER_PHASES  # chunk (2, 2) holds (20, 20)
    game._teardown()
