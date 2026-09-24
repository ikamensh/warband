"""The aether in the match's HUD (WB-063): the figure beside gold and lumber, a vault's card, its reach, and placing
a vault, which snaps onto a ley rift and says when it would not draw.  Mock backend, through the scene's input."""

import pytest

from saga2d import Game
from warband.sim.model import RIFT, Build, Event
from warband.sim.rules import AETHER_EVERY, AETHER_STORE, BuildingType
from warband.ui.icons import Icon
from warband.ui.scene import new_game
from warband.ui.style import build_theme


@pytest.fixture
def play(tmp_path):
    game = Game("Warband aether", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
    game.push(scene)
    game.tick(1 / 60)
    yield game, scene
    game.close()


def screen_of(scene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    return int(sx), int(sy)


def point_at(game, scene, point) -> None:
    game.backend.inject_mouse_move(*screen_of(scene, point))
    game.tick(1 / 60)


def press(game, key: str) -> None:
    game.backend.inject_key(key)
    game.tick(1 / 60)


def own_rift(scene) -> tuple[int, int]:
    """The rift the map lays by the player's hall."""
    hall = scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    return min(scene.world.rifts, key=lambda r: abs(r[0] - hall.x) + abs(r[1] - hall.y))


def test_the_hud_shows_aether_stored_over_what_the_vaults_hold(play) -> None:
    game, scene = play
    world = scene.world
    icon = next(c for c in scene.ui.walk() if isinstance(c, Icon) and c.name == "aether")
    _icon, label = scene.resource_pair("aether")
    assert label.text == "0/0"
    world.place_building(scene.human, BuildingType.VAULT, own_rift(scene))
    world.players[scene.human].aether = 12
    game.tick(1 / 60)
    assert label.text == f"12/{AETHER_STORE}"
    x, y, w, h = icon.bounds
    scene.mouse = (x + w / 2, y + h / 2)
    game.backend.inject_mouse_move(x + w / 2, y + h / 2)
    game.tick(1 / 60)
    assert scene.tooltip.startswith("Aether") and "1 of 1 vault drawing" in scene.tooltip


def test_placing_a_vault_snaps_onto_the_rift_beside_the_pointer_and_says_it_draws(play) -> None:
    game, scene = play
    rift = own_rift(scene)
    peasant = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    scene.select([peasant.id])
    press(game, "b")
    press(game, "v")
    assert scene.placing is BuildingType.VAULT
    point_at(game, scene, (rift[0] + RIFT + 0.5, rift[1] + 0.5))  # a tile to the right of it: still the rift's
    assert scene.ghost() == (BuildingType.VAULT, rift, True)
    assert ("On a ley rift", "it draws aether") in scene.hint()
    assert scene.reach_shown() == [(rift[0] + RIFT / 2, rift[1] + RIFT / 2)]
    point_at(game, scene, (rift[0] - 4.0, rift[1] + 6.0))
    assert scene.ghost()[1] != rift
    assert ("Off the ley rifts", "it stores and reaches but draws nothing") in scene.hint()
    point_at(game, scene, (rift[0] + 1.0, rift[1] + 1.0))
    x, y = screen_of(scene, (rift[0] + 1.0, rift[1] + 1.0))
    game.backend.inject_click(x, y, "left")
    game.backend.inject_release(x, y, "left")
    game.tick(1 / 60)
    assert isinstance(peasant.order, Build) and (peasant.order.type, peasant.order.pos) == (BuildingType.VAULT, rift)


def test_the_planner_puts_a_vault_on_a_free_rift_the_player_knows(play) -> None:
    game, scene = play
    rift = own_rift(scene)
    scene.select([])
    press(game, "b")
    press(game, "v")
    press(game, "v")  # its key again: the planner picks the spot
    assert [(p.type, p.pos) for p in scene.world.player_plans(scene.human)] == [(BuildingType.VAULT, rift)]


def test_a_farm_placed_on_a_rift_is_refused_with_the_reason(play) -> None:
    game, scene = play
    rift = own_rift(scene)
    scene.select([])
    press(game, "b")
    press(game, "f")
    point_at(game, scene, (rift[0] + 1.0, rift[1] + 1.0))
    assert scene.ghost() == (BuildingType.FARM, rift, False)
    x, y = screen_of(scene, (rift[0] + 1.0, rift[1] + 1.0))
    game.backend.inject_click(x, y, "left")
    game.backend.inject_release(x, y, "left")
    game.tick(1 / 60)
    assert scene.status == "Keep the ley rift for a vault" and not scene.world.player_plans(scene.human)


def test_a_vault_s_card_says_what_it_draws_and_its_reach_shows_while_it_is_selected(play) -> None:
    game, scene = play
    world = scene.world
    vault = world.place_building(scene.human, BuildingType.VAULT, own_rift(scene))
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    stray = world.place_building(scene.human, BuildingType.VAULT, (hall.x - 4, hall.y + 5))
    scene.select([vault.id])
    game.tick(1 / 60)
    assert scene.reach_shown() == [vault.center]
    shown = " ".join(t["text"] for t in game.backend.texts)
    assert f"On a ley rift · draws 1 aether every {AETHER_EVERY:g} s" in shown
    world.players[scene.human].aether = world.aether_cap(scene.human)
    game.tick(1 / 60)
    assert "the store is full, so it draws nothing" in " ".join(t["text"] for t in game.backend.texts)
    scene.select([stray.id])
    game.tick(1 / 60)
    assert "Off the ley rifts: it stores and reaches, but draws nothing" in " ".join(t["text"] for t in game.backend.texts)
    site = world.place_building(scene.human, BuildingType.VAULT, (hall.x - 4, hall.y - 6), done=False)
    scene.select([site.id])
    assert scene.reach_shown() == [], "a site reaches nothing yet"


def test_a_spill_is_told_to_its_owner(play) -> None:
    game, scene = play
    scene.world.events.append(Event("spilled", (10.0, 10.0), player=scene.human, amount=40))
    game.tick(1 / 60)
    assert "40 aether spilled" in scene.status
