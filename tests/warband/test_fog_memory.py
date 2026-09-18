"""The fog of war is honest: ground the player cannot see shows what it held when they last saw it.

A rival's building raised on explored ground stays out of sight until somebody looks, one razed
there stays on the map until somebody looks, and the same goes for the minimap, for picking with
the mouse and for the trees a rival fells.  What a rival is making stays the rival's business
even in plain sight.
"""

import numpy as np
import pytest

from saga2d import Game
from warband.model import tile_center
from warband.rules import BuildingType, Terrain, UnitType
from warband.scene import load_game, new_game
from warband.style import build_theme

FRAME = 1 / 60
VISION_FRAMES = 20  # frames that are sure to hold a fog recomputation: a step every three, vision every four steps


@pytest.fixture
def play(tmp_path):
    game = Game("Warband Fog", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=5)
    game.push(scene)
    scene.brains = []  # the rival only does what the test has it do
    game.tick(FRAME)
    yield game, scene
    game.close()


def frames(game: Game, count: int = VISION_FRAMES) -> None:
    for _ in range(count):
        game.tick(FRAME)


def rival_site(scene, building_type: BuildingType = BuildingType.FARM) -> tuple[int, int]:
    """Open ground beside the rival's hall: far from anything the player owns."""
    world = scene.world
    rival = next(p.id for p in world.players if p.id != scene.human)
    hall = world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
    for reach in range(3, 10):
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                site = (hall.x + dx, hall.y + dy)
                if world.can_place(building_type, site, rival) is None:
                    return site
    raise AssertionError("no open ground beside the rival's hall")


def explore_everything(game: Game, scene) -> None:
    """The player has seen the whole map once and now sees only what their own forces see."""
    scene.world.reveal_all(scene.human)
    frames(game)


def test_a_building_raised_on_explored_ground_stays_unseen_until_somebody_looks(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    rival = next(p.id for p in world.players if p.id != scene.human)
    site = rival_site(scene)
    explore_everything(game, scene)
    assert world.is_explored(scene.human, site) and not world.is_visible(scene.human, site)
    farm = world.place_building(rival, BuildingType.FARM, site)
    frames(game)
    assert view.building_sprite(farm.id) is None, "a farm the player never saw is drawn under the fog"
    assert view.entity_at(farm.center) is None, "a farm the player never saw can be picked with the mouse"
    world.spawn_unit(scene.human, UnitType.SCOUT, (site[0] - 1.5, site[1] + 0.5))
    frames(game)
    assert view.building_sprite(farm.id) is not None
    assert view.entity_at(farm.center) is farm


def test_a_building_razed_out_of_sight_stands_on_the_map_until_somebody_looks(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    rival = next(p.id for p in world.players if p.id != scene.human)
    site = rival_site(scene)
    shell = world.place_building(rival, BuildingType.FARM, site, done=False)
    explore_everything(game, scene)  # the player saw the site once
    assert view.building_sprite(shell.id) is not None and not world.is_visible(scene.human, site)
    world.cancel_building(shell.id)  # the rival tears it down where nobody watches
    frames(game)
    assert view.building_sprite(shell.id) is not None, "the player cannot know it is gone"
    assert view.sighting(shell.id) is not None
    world.spawn_unit(scene.human, UnitType.SCOUT, (site[0] - 1.5, site[1] + 0.5))
    frames(game)
    assert view.building_sprite(shell.id) is None and view.sighting(shell.id) is None, "now they look, and it is gone"


def minimap_pixel(scene, tile: tuple[int, int]) -> tuple[int, int, int]:
    pixels = np.asarray(scene.view._minimap_image())
    return tuple(int(c) for c in pixels[tile[1] * 2, tile[0] * 2, :3])


def test_the_minimap_shows_out_of_sight_ground_as_last_seen(play) -> None:
    game, scene = play
    world = scene.world
    rival = next(p.id for p in world.players if p.id != scene.human)
    site = rival_site(scene)
    explore_everything(game, scene)
    before = minimap_pixel(scene, site)
    farm = world.place_building(rival, BuildingType.FARM, site)
    frames(game)
    assert minimap_pixel(scene, site) == before, "the rival's new farm is on the minimap before anybody saw it"
    world.spawn_unit(scene.human, UnitType.SCOUT, (site[0] - 1.5, site[1] + 0.5))
    frames(game)
    assert minimap_pixel(scene, site) == world.players[rival].color
    assert farm.id in {s.id for s in scene.view._sightings.values()}


def test_a_tree_felled_out_of_sight_stands_until_somebody_looks_and_one_grown_back_waits_too(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    explore_everything(game, scene)
    tree = next(pos for pos in view._trees if not world.is_visible(scene.human, pos)
                and any(world.passable(pos[0] + dx, pos[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    beside = next((tree[0] + dx, tree[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if world.passable(tree[0] + dx, tree[1] + dy))
    wooded = minimap_pixel(scene, tree)
    rival = next(p.id for p in world.players if p.id != scene.human)
    feller = world.spawn_unit(rival, UnitType.PEASANT, tile_center(beside))
    world.harvest([feller.id], tree)
    for _ in range(600):  # a minute at most, in tenths: the chopping is waited out, not looked at
        game.tick(0.1)
        if world.terrain_at(tree).value != "trees":
            break
    assert world.terrain_at(tree).value != "trees", "the rival's worker never felled the tree"
    frames(game)
    assert tree in view._trees and minimap_pixel(scene, tree) == wooded, "a tree felled out of sight vanished from the player's map"
    assert view.terrain_at(tree).value == "trees", "the status line names the ground as it is, not as the player knows it"
    world.spawn_unit(scene.human, UnitType.SCOUT, tile_center(beside))
    frames(game)
    assert tree not in view._trees and minimap_pixel(scene, tree) != wooded and view.terrain_at(tree).value == "grass"


@pytest.mark.parametrize("reopen", ["in the match", "from the title"])
def test_a_save_keeps_what_the_player_had_seen(play, reopen) -> None:
    """Loading must not show the player what the fog hid when they saved."""
    game, scene = play
    world = scene.world
    rival = next(p.id for p in world.players if p.id != scene.human)
    site = rival_site(scene)
    explore_everything(game, scene)
    farm = world.place_building(rival, BuildingType.FARM, site)
    frames(game)
    scene.save_to("quick")
    if reopen == "in the match":
        scene.load_from("quick")
    else:
        game.clear_and_push(load_game(game.save_manager.load("quick")["state"], settings=scene.settings))
    frames(game)
    scene = game.scene
    assert scene.world is not world and farm.id in scene.world.buildings
    assert scene.view.building_sprite(farm.id) is None, "loading the save revealed a farm the player had never seen"
    hall = scene.world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
    assert scene.view.building_sprite(hall.id) is not None, "the rival's hall, seen before the save, is remembered after it"


def panel_text(game: Game) -> str:
    return " | ".join(t["text"] for t in game.backend.texts)


def test_what_a_rival_is_making_stays_private_and_a_fogged_building_reads_as_last_seen(play) -> None:
    game, scene = play
    world = scene.world
    rival = next(p.id for p in world.players if p.id != scene.human)
    hall = world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
    explore_everything(game, scene)
    world.players[rival].gold = 5000
    world.train(hall.id, UnitType.PEASANT)
    seen_hp = hall.hp
    hall.hp -= 300  # struck where the player cannot see
    scene.select([hall.id])
    frames(game, 3)
    text = panel_text(game)
    assert f"{seen_hp}/{hall.max_hp}" in text, f"the panel shows a fogged hall's hit points as they are now: {text}"
    assert "%" not in text, f"the panel shows what the rival is training: {text}"
    world.spawn_unit(scene.human, UnitType.SCOUT, (hall.x - 1.5, hall.y + 0.5))
    frames(game)
    text = panel_text(game)
    assert f"{hall.hp}/{hall.max_hp}" in text and "%" not in text, f"in plain sight the damage shows, the production still does not: {text}"


def test_a_tree_the_player_watches_fall_is_gone_the_frame_it_falls(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    tree, beside = next((pos, (pos[0] + dx, pos[1] + dy)) for pos in view._trees if world.is_visible(scene.human, pos)
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if world.passable(pos[0] + dx, pos[1] + dy))
    worker = world.spawn_unit(scene.human, UnitType.PEASANT, tile_center(beside))
    world.harvest([worker.id], tree)
    for _ in range(600):  # in tenths: whatever frame the tree falls in is the frame it must be gone by
        game.tick(0.1)
        if world.terrain_at(tree) is not Terrain.TREES:
            break
    assert world.terrain_at(tree) is not Terrain.TREES and tree not in view._trees


def test_a_tree_grown_back_out_of_sight_waits_to_be_seen(play) -> None:
    game, scene = play
    world, view = scene.world, scene.view
    explore_everything(game, scene)
    glade = next((x, y) for y in range(world.height) for x in range(world.width)
                 if world.terrain_at((x, y)) is Terrain.GRASS and not world.is_visible(scene.human, (x, y)) and world.building_at((x, y)) is None
                 and world.passable(x + 1, y) and not world.is_visible(scene.human, (x + 1, y)))
    world.terrain[glade[1]][glade[0]] = Terrain.TREES  # the elven art at work where nobody watches
    frames(game)
    assert glade not in view._trees and view.terrain_at(glade) is Terrain.GRASS
    world.spawn_unit(scene.human, UnitType.SCOUT, tile_center((glade[0] + 1, glade[1])))
    frames(game)
    assert glade in view._trees and view.terrain_at(glade) is Terrain.TREES


def test_a_save_from_before_the_view_remembered_starts_from_the_footprints_the_model_remembers(play) -> None:
    game, scene = play
    world = scene.world
    rival = next(p.id for p in world.players if p.id != scene.human)
    site = rival_site(scene)
    explore_everything(game, scene)
    farm = world.place_building(rival, BuildingType.FARM, site)
    frames(game)
    state = scene.get_save_state()
    del state["seen"]
    game.clear_and_push(load_game(state, settings=scene.settings))
    frames(game)
    view = game.scene.view
    hall = game.scene.world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
    assert view.building_sprite(hall.id) is not None and view.building_sprite(farm.id) is None
