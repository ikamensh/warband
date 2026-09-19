"""The map view: sprites in step with the model, draw order, fog and minimap images, textures."""

import numpy as np
import pytest
from PIL import Image

from saga2d import Game
from warband.art import textures
from warband.sim.model import tile_center
from warband.sim.rules import BuildingType, Layout, MapTheme, Resource, Terrain, UnitType
from warband.ui.scene import GameScene, new_game
from warband.ui.view import FOG_MARGIN, STAFF_REACH, WATER_PERIOD
from warband.sim import mapgen
from warband.ui.style import build_theme
from warband.art.textures import TILE


@pytest.fixture
def play():
    game = Game("Warband View", backend="mock", resolution=(1280, 800), theme=build_theme())
    scene = new_game(seed=5)
    game.push(scene)
    game.tick(1 / 60)
    yield game, scene
    game.close()


def order_of(game: Game, sprite) -> int:
    return game.backend.sprites[sprite.sprite_id]["order"]


def test_every_tree_and_building_has_a_sprite_and_a_felled_tree_loses_it(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    trees = sum(1 for row in world.terrain for t in row if t is Terrain.TREES)
    assert len(view.tree_sprites) == trees
    in_sight = {b.id for b in world.buildings.values() if b.player == scene.human or world.any_visible(scene.human, b.rect)}
    assert {b.id for b in world.buildings.values() if view.building_sprite(b.id) is not None} == in_sight
    pos = next(p for p in view.tree_sprites if world.is_visible(scene.human, p))  # one felled out of sight stands until somebody looks: test_fog_memory
    tree_sprite_id = view.tree_sprites[pos].sprite_id
    world.terrain[pos[1]][pos[0]] = Terrain.GRASS
    for _ in range(20):  # the player's next look around (a felling they watch is shown at once: test_fog_memory)
        game.tick(1 / 60)
    assert pos not in view.tree_sprites
    assert tree_sprite_id not in game.backend.sprites  # Includes its baked shade and litter.


def test_forest_uses_twenty_stable_variants_across_save_reload(play) -> None:
    """A real map uses the full forest asset bank without reshuffling on load."""
    game, scene = play
    before = {pos: sprite.image for pos, sprite in scene.view.tree_sprites.items()}
    assert len(set(before.values())) >= 20
    scene.view.reset(scene.world.from_dict(scene.world.to_dict()))
    assert {pos: sprite.image for pos, sprite in scene.view.tree_sprites.items()} == before


@pytest.mark.slow
def test_harvesting_worker_swings_axe_then_carries_wood(play) -> None:
    """Harvest orders drive all swing poses, face the tree, then show carried logs.

    It watches a whole chop frame by frame for every swing pose, about three seconds: the slow tier."""
    game, scene = play
    world = scene.world
    tree, approach = next(
        (pos, (pos[0] + dx, pos[1] + dy))
        for pos in scene.view.tree_sprites for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
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
    keys = {textures.mine_image(game, i) for i in range(textures.mine_variants())}
    assert len(keys) == textures.mine_variants()
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
    tree = min(view.tree_sprites, key=lambda p: abs(p[0] - hall.center[0]) + abs(p[1] - hall.center[1]))
    walker = world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((tree[0], tree[1] + 1)))
    game.tick(1 / 60)
    assert order_of(game, view.unit_sprite(walker.id)) > order_of(game, view.tree_sprites[tree])


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
    for _ in range(40):  # the walk to the mine, in tenths
        game.tick(0.1)
        if peasant.inside is not None:
            break
    assert peasant.inside is not None and not view.unit_sprite(peasant.id).visible


def test_fog_image_is_clear_where_seen_dim_where_explored_and_black_elsewhere(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    fog = np.asarray(view.fog_image())[FOG_MARGIN:-FOG_MARGIN, FOG_MARGIN:-FOG_MARGIN]
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    hx, hy = int(hall.center[0]), int(hall.center[1])
    assert fog[hy, hx, 3] == 0
    assert fog[world.height - 2, world.width - 2, 3] == 255
    unit = next(u for u in world.player_units(scene.human))
    unit.x, unit.y = hall.center[0] + 12, hall.center[1]
    world.update_vision()
    unit.x, unit.y = hall.center[0], hall.center[1]
    world.update_vision()
    image = np.asarray(view.fog_image())
    assert np.all(image[:FOG_MARGIN, :, 3] == 255)
    assert np.all(image[-FOG_MARGIN:, :, 3] == 255)
    assert np.all(image[:, :FOG_MARGIN, 3] == 255)
    assert np.all(image[:, -FOG_MARGIN:, 3] == 255)
    fog = image[FOG_MARGIN:-FOG_MARGIN, FOG_MARGIN:-FOG_MARGIN]
    assert fog[hy, hx + 12, 3] not in (0, 255)
    updates_before = game.backend.image_updates.get(game.assets.image(view.fog_key), 0)
    for _ in range(20):
        game.tick(1 / 60)
    assert game.backend.image_updates[game.assets.image(view.fog_key)] > updates_before


def test_minimap_image_marks_terrain_buildings_and_units(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    image = view.minimap_image()
    assert image.size == (world.width * 2, world.height * 2)
    pixels = np.asarray(image)
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    assert tuple(pixels[hall.y * 2, hall.x * 2, :3]) == world.players[scene.human].color
    mine = world.mines()[0]
    assert tuple(pixels[mine.y * 2, mine.x * 2, :3]) == (232, 196, 70)
    assert tuple(pixels[(world.height - 2) * 2, (world.width - 2) * 2, :3]) != (0, 0, 0)  # dark, not black


def test_unit_images_are_rendered_on_demand_per_facing_and_frame(play) -> None:
    game, scene = play
    key = textures.unit_image(game, UnitType.KNIGHT, 1, 6, "strike")
    placement = textures.placements[key]
    assert game.assets.has_image(key) and 0 < placement.drop < placement.size[1]  # the feet lie inside the image
    for unit_type in UnitType:  # every unit, frame and carry variant renders (a missing colour name would raise here)
        for frame in textures.FRAMES:
            textures.unit_image(game, unit_type, 1, 3, frame)
    for carrying in (Resource.GOLD, Resource.LUMBER):
        textures.unit_image(game, UnitType.PEASANT, 0, 2, "walk1", carrying)
    for theme in MapTheme:
        textures.register_theme(game, theme)
    assert textures.facing_index(0.0) == 0 and textures.facing_index(3.1416 / 2) == 2 and textures.facing_index(-3.1416 / 2) == 6
    other = textures.unit_image(game, UnitType.KNIGHT, 1, 6, "strike")
    assert other == key
    for building_type in BuildingType:
        if building_type is not BuildingType.GOLD_MINE:
            assert textures.placements[textures.building_image(game, building_type, 0)].size[0] >= textures.BUILDINGS[building_type].size * TILE * 0.8


def test_ground_chunks_cover_the_map_with_a_margin_and_sand_meets_water() -> None:
    from warband.sim import mapgen

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


@pytest.mark.parametrize("scale", [0.85375, 1.0, 2.0])
def test_chunk_padding_does_not_paint_grass_beyond_the_playable_map(scale) -> None:
    """The renderer's overlapping chunks must not create a bright strip outside fog."""
    world = mapgen.generate(seed=3, width=48, height=40, layout=Layout.PLAINS)
    for cx, cy in ((0, 0), (3, 0), (0, 3), (3, 3)):
        image = textures.ground_chunk(world.terrain_at, world.in_bounds, cx, cy, scale)
        assert image.size == (round(textures.CHUNK_PX * scale),) * 2
        for y in range(textures.CHUNK + 2):
            for x in range(textures.CHUNK + 2):
                tile = (cx * textures.CHUNK - 1 + x, cy * textures.CHUNK - 1 + y)
                alpha = image.getpixel((round((x + 0.5) * TILE * scale), round((y + 0.5) * TILE * scale)))[3]
                assert alpha == (255 if world.in_bounds(tile) else 0)


@pytest.mark.parametrize("scale", [1.0, 1.25, 2.0])
def test_overlapping_ground_chunks_agree_at_horizontal_and_vertical_seams(scale) -> None:
    """Panning must not expose lines where independently painted chunks overlap."""
    world = mapgen.generate(seed=3)
    # Include a shore across both chunk edges, not just uniform meadow.
    for y in range(6, 10):
        for x in range(6, 10):
            world.terrain[y][x] = Terrain.WATER
    for phase in range(textures.WATER_PHASES):
        a, right, below = [np.asarray(textures.ground_chunk(world.terrain_at, world.in_bounds, cx, cy, scale, phase=phase))
                           for cx, cy in ((0, 0), (1, 0), (0, 1))]
        overlap = round(2 * TILE * scale)
        np.testing.assert_array_equal(a[:, -overlap:], right[:, :overlap])
        np.testing.assert_array_equal(a[-overlap:, :], below[:overlap, :])


@pytest.mark.parametrize("theme", list(MapTheme))
@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_forest_and_clearing_share_the_same_ground_across_chunk_edges(theme, scale) -> None:
    """Felling removes the tree sprite, leaving grass rather than a baked dark square."""
    world = mapgen.generate(seed=3, width=48, height=40, theme=theme, layout=Layout.FOREST)
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
    before = len(game.backend._image_sizes)  # the mock backend does not count the images it holds publicly (Saga2D 0.3.8)
    keys = [sprite.image for sprite in scene.view.ground_sprites] + [scene.view.fog_key, scene.view.minimap_key]
    handles = [game.assets.image(key) for key in keys]
    scene.world = scene.world.from_dict(scene.world.to_dict())
    scene.view.reset(scene.world)
    assert len(game.backend._image_sizes) == before  # the mock's count, as above
    game.tick(1 / 60)  # the unit warmer may now add animation frames
    assert [game.assets.image(key) for key in keys] == handles
    assert Image  # the PIL import is what the view feeds update_image


def test_a_site_shows_its_foundation_then_its_walls_raised_and_a_battered_building_smokes_then_burns(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    site = world.place_building(scene.human, BuildingType.FARM, (hall.x + 5, hall.y + 4), done=False)
    game.tick(1 / 60)
    race = world.race_of(scene.human)  # WB-048: a site wears its own painting, whole, not the building faded in
    assert view.building_sprite(site.id).image == textures.building_key(BuildingType.FARM, scene.human, race, "founded")
    assert view.building_sprite(site.id).opacity == 255
    site.progress = site.info.build_time * 0.6
    game.tick(1 / 60)
    assert view.building_sprite(site.id).image == textures.building_key(BuildingType.FARM, scene.human, race, "raised")
    assert view.building_sprite(site.id).opacity == 255
    site.progress = site.info.build_time
    site.hp = site.max_hp
    game.tick(1 / 60)
    assert view.building_sprite(site.id).opacity == 255 and site.id not in view.smoke
    site.hp = site.max_hp // 3
    game.tick(1 / 60)
    assert site.id in view.smoke
    for _ in range(30):
        game.tick(1 / 60)
    assert view.smoke[site.id].particle_count > 0 and site.id not in view.fires
    site.hp = site.max_hp // 5  # under a quarter it blazes as well
    for _ in range(30):
        game.tick(1 / 60)
    assert site.id in view.fires and view.fires[site.id].particle_count > 0
    site.hp = site.max_hp
    game.tick(1 / 60)
    assert site.id not in view.smoke and site.id not in view.fires


def flood(world, x0: int, y0: int, size: int = 3) -> None:
    """Water painted into a generated map where the test needs it, as map generation carves a road: the terrain and
    the grid the model paths on (the World has no public way to change a tile, and nothing a player does can)."""
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
    assert view.chunk_has_water(0) and len(view.ground_keys[0]) == textures.WATER_PHASES
    land = next(i for i, keys in enumerate(view.ground_keys) if len(keys) == 1)
    first = view.ground_sprites[0].image
    while view.water_pending:  # the other phases are painted one per frame; the water waits on phase 0 meanwhile
        assert view.ground_sprites[0].image == first
        game.tick(1 / 60)
    assert all(game.assets.has_image(key) for key in view.ground_keys[0])
    for _ in range(int(WATER_PERIOD * 60) + 2):
        game.tick(1 / 60)
    assert view.ground_sprites[0].image != first and view.ground_sprites[0].image in view.ground_keys[0]
    assert view.ground_sprites[land].image == view.ground_keys[land][0]
    # A loaded map of the same size may have its water elsewhere: the chunks are classified again.
    other = mapgen.generate(seed=6, width=48, height=40, players=2)
    flood(other, 20, 20)
    view.reset(other)
    for index, keys in enumerate(view.ground_keys):
        assert (len(keys) > 1) == view.chunk_has_water(index)
    assert len(view.ground_keys[view.ground_keys.index(view.chunk_keys(2 * 6 + 2))]) == textures.WATER_PHASES  # chunk (2, 2) holds (20, 20)
    game.close()


def test_walk_frames_follow_the_distance_walked_not_the_clock(play) -> None:
    """Feet stay planted: a unit's walk frame advances with the ground it covers, so a fast unit
    steps faster and a unit held in place keeps its frame."""
    from warband.ui.view import STRIDE, unit_frame

    game, scene = play
    u = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, (10.5, 10.5))
    u.state = "move"
    seen = [unit_frame(u, travel, 0.0) for travel in (0.0, STRIDE, 2 * STRIDE, 3 * STRIDE, 4 * STRIDE)]
    assert seen == list(textures.WALK_FRAMES) + [textures.WALK_FRAMES[0]]
    assert unit_frame(u, 0.5 * STRIDE, 0.0) == unit_frame(u, 0.5 * STRIDE, 9.0)  # the clock does not move the feet


def test_a_blow_winds_up_before_it_lands_and_follows_through_after(play) -> None:
    """Phases of one attack, read off the model's own clocks: wind-up while the model has the weapon
    drawn back, then strike, follow-through and recovery right after the blow, guard otherwise."""
    from warband.ui.view import FOLLOW, RECOVER, STRIKE, unit_frame

    game, scene = play
    u = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, (10.5, 10.5))
    u.state = "attack"
    full = u.info.cooldown

    def at(cooldown: float, windup: float = 0.0) -> str:
        u.cooldown, u.windup = cooldown, windup
        return unit_frame(u, 0.0, 0.0)

    assert at(0.0, u.info.windup) == "wind"  # drawn back, about to land
    assert at(0.0, 0.01) == "wind"
    assert at(full) == "strike"  # the model has just landed the blow and reset the cooldown
    assert at(full - STRIKE - FOLLOW / 2) == "follow"
    assert at(full - STRIKE - FOLLOW - RECOVER / 2) == "recover"
    assert at(full / 2) == "stand"
    assert at(0.0) == "stand"  # ready, facing a target it cannot yet strike: guard


def test_shots_in_the_air_have_sprites_that_fly_and_go_when_they_land(play) -> None:
    """An arrow's sprite appears when it is loosed, moves toward its mark and leaves when the shot lands;
    a stone lobs above the ground on its way to the point it was aimed at."""
    game, scene = play
    world = scene.world
    archer = world.spawn_unit(scene.human, UnitType.ARCHER, (6.5, 6.5))
    catapult = world.spawn_unit(scene.human, UnitType.CATAPULT, (6.5, 9.5))
    for u in (archer, catapult):
        u.facing = 0.0
    victim = world.spawn_unit(1, UnitType.KNIGHT, (10.4, 6.5))
    wall = world.place_building(1, BuildingType.FARM, (12, 9))
    world.hold([victim.id])
    world.attack([archer.id], victim.id)
    world.attack([catapult.id], wall.id)
    seen: dict[str, list[tuple[float, float]]] = {"arrow": [], "stone": []}
    for _ in range(90):
        game.tick(1 / 30)
        for p in world.projectiles.values():
            sprite = scene.view.shot_sprites[p.id]
            assert sprite.visible and sprite.image == p.kind
            seen[p.kind].append(sprite.position)
    assert len(seen["arrow"]) >= 2 and len(seen["stone"]) >= 5
    assert seen["arrow"][-1][0] > seen["arrow"][0][0]  # flew toward the knight
    stone_x = [x for x, _ in seen["stone"]]
    assert stone_x == sorted(stone_x) and stone_x[-1] > stone_x[0] + 3 * 32
    apex = min(y for _, y in seen["stone"])
    assert apex < seen["stone"][0][1] - 32 and apex < seen["stone"][-1][1] - 32  # up, over and down again
    assert not world.projectiles and not scene.view.shot_sprites  # all landed, all sprites gone


def test_an_arrow_points_along_its_flight_from_its_first_frame(play) -> None:
    """An arrow took its heading from the trail behind it, so on its first frame, with no trail yet, it pointed east
    whatever it was loosed at.  Loosed to the north-west it points up and to the left at once."""
    game, scene = play
    world = scene.world
    archer = world.spawn_unit(scene.human, UnitType.ARCHER, (9.5, 9.5))
    victim = world.spawn_unit(1, UnitType.KNIGHT, (7.0, 7.0))
    world.hold([victim.id])
    world.attack([archer.id], victim.id)
    for _ in range(240):
        game.tick(1 / 60)
        if world.projectiles:
            break
    (arrow,) = world.projectiles.values()
    assert -170 < scene.view.shot_sprites[arrow.id].rotation < -100  # about -135° on a screen whose y grows downward


def test_a_healers_shot_is_a_mote_of_light_that_flies_straight_from_before_it(play) -> None:
    """The model flies a cleric's weak blow as an arrow (it follows its mark); what is seen is the striker's own: a
    mote of light, first seen before the healer where it holds its staff, straight to its mark.  An archer's arrow
    beside it keeps its image and rises on its way."""
    game, scene = play
    world = scene.world
    shooters = {"mote": world.spawn_unit(scene.human, UnitType.CLERIC, (6.5, 6.5)), "arrow": world.spawn_unit(scene.human, UnitType.ARCHER, (6.5, 10.5))}
    seen: dict[str, list[tuple[float, float]]] = {"mote": [], "arrow": []}
    for shooter in shooters.values():
        shooter.facing = 0.0
        victim = world.spawn_unit(1, UnitType.KNIGHT, (shooter.x + 2.9, shooter.y))
        world.hold([victim.id])
        world.attack([shooter.id], victim.id)
    for _ in range(120):
        game.tick(1 / 60)
        for p in world.projectiles.values():
            look = next(name for name, shooter in shooters.items() if shooter.id == p.source)
            sprite = scene.view.shot_sprites[p.id]
            assert p.kind == "arrow" and sprite.image == look
            seen[look].append(sprite.position)

    def rise(path: list[tuple[float, float]]) -> float:
        """How far above the straight line from its first to its last point the path climbs, in pixels."""
        (x0, y0), (x1, y1) = path[0], path[-1]
        return max(y0 + (y1 - y0) * (x - x0) / (x1 - x0) - y for x, y in path)

    assert len(seen["mote"]) >= 5 and len(seen["arrow"]) >= 5
    assert seen["mote"][0][0] - shooters["mote"].x * TILE >= STAFF_REACH * TILE - 0.01  # never inside the healer's hood
    assert rise(seen["mote"]) < 0.5 < 3 < rise(seen["arrow"])
