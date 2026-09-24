"""A flyer as the player meets it (WB-064): drawn in the air over its shadow, picked and boxed by the body drawn up
there, and given orders that make sense for a machine with no weapon (mock backend)."""

import pytest

from saga2d import Game, RenderLayer
from saga2d.rendering.layers import LAYER_BAND
from warband.sim.model import Attack, Move, tile_center
from warband.sim.rules import BuildingType, Race, UnitType
from warband.art import textures, visual_lint
from warband.art.textures import TILE
from warband.ui.scene import new_game
from warband.ui.style import build_theme
from warband.ui.view import FLIGHT, SHADOW_COLOR


@pytest.fixture
def game(tmp_path):
    g = Game("Warband flyers", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


@pytest.fixture
def play(game):
    scene = new_game(seed=3)
    game.push(scene)
    game.tick(1 / 60)
    return game, scene


def screen_of(scene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * TILE, point[1] * TILE)
    return int(sx), int(sy)


def click(game: Game, scene, point, button: str = "left") -> None:
    x, y = screen_of(scene, point)
    game.backend.inject_click(x, y, button)
    game.backend.inject_release(x, y, button)
    game.tick(1 / 60)


def drag_box(game: Game, scene, a, b) -> None:
    x0, y0 = screen_of(scene, a)
    x1, y1 = screen_of(scene, b)
    game.backend.inject_click(x0, y0)
    game.backend.inject_drag(x1, y1, x1 - x0, y1 - y0)
    game.backend.inject_release(x1, y1)
    game.tick(1 / 60)


def a_flyer_in_view(game: Game, scene, player: int | None = None):
    """A flying machine of *player* (the human's by default) hovering on the human's side of the map, in view."""
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    ground = tile_center((hall.x + 6, hall.y + 5))
    flyer = scene.world.spawn_unit(scene.human if player is None else player, UnitType.FLYING_MACHINE, ground)
    scene.world.hold([flyer.id])
    scene.world.update_vision()
    scene.camera.center_on(ground[0] * TILE, ground[1] * TILE)
    for _ in range(3):
        game.tick(1 / 60)
    return flyer, ground


def test_a_flyer_is_drawn_in_the_air_over_its_shadow(play) -> None:
    game, scene = play
    flyer, (gx, gy) = a_flyer_in_view(game, scene)
    sprite = scene.view.unit_sprite(flyer.id)
    assert sprite.layer is RenderLayer.EFFECTS, "over the roofs and the trees, under the fog"
    body = scene.view.body_point(flyer)
    assert body[0] == pytest.approx(gx) and gy - body[1] > FLIGHT * 0.9, body
    shadows = [p for p in game.backend.polygons if p["color"] == SHADOW_COLOR and p["space"] == "world"]
    assert shadows and all(p["order"] // LAYER_BAND == RenderLayer.EFFECTS for p in shadows)
    xs = [x for x, _ in shadows[0]["points"]]
    ys = [y for _, y in shadows[0]["points"]]
    assert min(xs) < gx * TILE < max(xs) and min(ys) < gy * TILE + 2 < max(ys), "on the ground under it"


def test_the_pointer_and_a_box_take_a_flyer_by_its_body_not_its_shadow(play) -> None:
    game, scene = play
    flyer, ground = a_flyer_in_view(game, scene)
    body = scene.view.body_point(flyer)
    click(game, scene, body)
    assert scene.selection == [flyer.id]
    click(game, scene, (ground[0] + 3.0, ground[1] + 2.5))  # empty ground: nothing
    assert scene.selection == []
    click(game, scene, (ground[0], ground[1] + 0.2))  # the shadow alone is only ground
    assert scene.selection == []
    drag_box(game, scene, (ground[0] - 1.0, ground[1] - 0.5), (ground[0] + 1.0, ground[1] + 0.5))
    assert scene.selection == [], "a box round the shadow alone"
    drag_box(game, scene, (body[0] - 1.0, body[1] - 0.6), (body[0] + 1.0, body[1] + 0.6))
    assert scene.selection == [flyer.id]
    lines = [line for line in game.backend.lines if line["space"] == "world" and line["order"] // LAYER_BAND == RenderLayer.EFFECTS]
    assert lines, "its ring is drawn round its shadow, with the flyers"


def test_a_right_click_sends_the_flyer_to_look_and_an_attack_order_says_it_has_no_weapon(play) -> None:
    game, scene = play
    flyer, ground = a_flyer_in_view(game, scene)
    enemy = scene.world.spawn_unit(1, UnitType.FOOTMAN, (ground[0] + 3.0, ground[1]))
    scene.world.hold([enemy.id])
    scene.world.update_vision()
    game.tick(1 / 60)
    scene.select([flyer.id])
    click(game, scene, enemy.pos, "right")
    assert isinstance(flyer.order, Move) and not scene.status.startswith("The")
    scene.command_attack(enemy.pos)
    assert scene.status == "The Flying Machine has no weapon"


def test_a_right_click_on_an_enemy_flyer_is_refused_to_melee_and_taken_by_a_shooter(play) -> None:
    game, scene = play
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    footman = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, tile_center((hall.x + 4, hall.y + 5)))
    archer = scene.world.spawn_unit(scene.human, UnitType.ARCHER, tile_center((hall.x + 4, hall.y + 6)))
    theirs, _ground = a_flyer_in_view(game, scene, player=1)
    body = scene.view.body_point(theirs)
    scene.select([footman.id])
    click(game, scene, body, "right")
    assert not footman.orders and scene.status.startswith("Only shooters and towers can hit")
    scene.select([archer.id])
    click(game, scene, body, "right")
    assert isinstance(archer.order, Attack) and archer.order.target == theirs.id


@pytest.mark.parametrize("race", list(Race))
def test_every_race_s_flyer_passes_the_art_lint(game, race: Race) -> None:
    """Every facing and frame of the machine through the art lint as a flyer is held to it: nothing empty or cut off by
    its canvas, no two frames of a wing beat or a turn of the rotor one picture, and enough of the team's colour on it
    for a player to tell whose it is.  Its feet and its middle are not asked: nothing of it stands on its anchor, and
    its rotor or wings sweep them (``visual_lint.lint_subject``)."""
    store = visual_lint.ImageStore(game)
    frames = {(facing, frame): (key, store.image(key)) for facing in range(textures.FACINGS) for frame in textures.FRAMES
              for key in [textures.unit_image(game, UnitType.FLYING_MACHINE, 0, facing, frame, None, race=race)]}
    findings = [finding for key, image in frames.values() for finding in visual_lint.lint_image(key, image)]
    findings += visual_lint.lint_subject(race.value, frames, textures.placements[frames[(0, "stand")][0]], flies=True)
    theirs = textures.unit_image(game, UnitType.FLYING_MACHINE, 1, 2, "stand", None, race=race)
    findings += visual_lint.lint_recolour(theirs, store.image(frames[(2, "stand")][0]), store.image(theirs))
    assert not findings, [str(finding) for finding in findings]
