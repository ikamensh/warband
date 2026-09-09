"""Choosing a race on the title and seeing it everywhere: HUD, cards, codex, saves, rooms and the map."""

import pytest

from saga2d import CommandError, Game
from online_server.games import create_match
from warband.model import tile_center
from warband.multiplayer import WarbandMatch
from warband.races import RACES
from warband.rules import BUILDINGS, BuildingType, Race, Terrain, UnitType, Upgrade
from warband.scene import CodexScene, GameScene, new_game
from warband.style import build_theme
from warband.title import RACE_KEYS, TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Races", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g._teardown()


def press(game: Game, key: str) -> None:
    game.backend.inject_key(key)
    game.tick(1 / 60)


def texts(game: Game) -> list[str]:
    return [t["text"] for t in game.backend.texts]


def click_tile(game: Game, scene: GameScene, point) -> None:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    game.backend.inject_click(int(sx), int(sy))
    game.backend.inject_release(int(sx), int(sy))
    game.tick(1 / 60)


def test_the_title_offers_every_race_with_a_hotkey_and_the_match_uses_it(game) -> None:
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "n")
    shown = texts(game)
    for race in Race:
        assert RACES[race].name in shown
    assert any(RACES[Race.HUMAN].passive in t for t in shown)
    press(game, RACE_KEYS[Race.ORC].lower())
    assert game.scene.race is Race.ORC and any(RACES[Race.ORC].passive in t for t in texts(game))
    press(game, "return")
    scene = game.scene
    assert isinstance(scene, GameScene) and scene.player.race is Race.ORC and scene.world.players[1].race is not Race.ORC
    game.tick(1 / 60)
    shown = texts(game)
    assert "Orcs" in shown and any("The Orcs of Azure against the" in t for t in shown)
    peon = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    click_tile(game, scene, peon.pos)
    assert "Peon" in texts(game)
    press(game, "b")
    labels = {c.label: c.hotkey for c in scene._card}
    assert labels["Hall"] == "H" and labels["War Camp"] == "B" and labels["Kennels"] == "S" and "Barracks" not in labels
    press(game, "f5")
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    press(game, "c")
    assert isinstance(game.scene, GameScene) and game.scene.player.race is Race.ORC and game.scene.race.name == "Orcs"


def test_buildings_offer_the_race_units_and_only_its_own_arts(game) -> None:
    scene = new_game(seed=3, races=[Race.ORC, None])
    game.push(scene)
    game.tick(1 / 60)
    world = scene.world
    world.reveal_all(scene.human)
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    world.place_building(scene.human, BuildingType.BARRACKS, (hall.x + 5, hall.y))
    kennels = world.place_building(scene.human, BuildingType.STABLES, (hall.x + 5, hall.y + 4))
    scene.player.gold, scene.player.lumber = 5000, 5000
    game.tick(1 / 60)
    scene.select([kennels.id])
    labels = [c.label for c in scene._card]
    assert labels == ["Wolf Rider", "Ogre", "Plunder", "Cancel"]  # Horse Breeding is a Human art
    press(game, "h")
    assert kennels.research is Upgrade.PLUNDER
    game.tick(1 / 60)
    scene.mouse = (scene.selection_panel.bounds[0] + 120, scene.selection_panel.bounds[1] + 70)  # over the readout
    game.tick(1 / 60)
    assert scene.tooltip.startswith("Researching Plunder")
    scene.select([])
    scene.open_settlement("upgrade")
    labels = [c.label for c in scene._card]
    assert "Bloodlust" in labels and "Plunder" in labels and "Horses" not in labels and "Blessing" not in labels
    scene.open_settlement("train")
    assert [c.label for c in scene._card][:3] == ["Peon", "Grunt", "Axethrower"]
    scene.open_settlement(None)
    press(game, "f2")
    assert isinstance(game.scene, CodexScene)
    shown = texts(game)
    assert "Codex — the Orcs" in shown and "Grunt" in shown and "Great Hall" in shown and "Footman" not in shown
    press(game, "4")
    shown = texts(game)
    assert "Codex — the four races" in shown and "Orcs ✓" in shown
    for race in Race:
        assert any(RACES[race].passive in t for t in shown), race
    press(game, "escape")


def test_a_regrown_tree_gets_a_sprite_and_a_felled_one_loses_it(game) -> None:
    scene = new_game(seed=5, races=[Race.ELF, None])
    game.push(scene)
    game.tick(1 / 60)
    world, view = scene.world, scene.view
    scene.player.upgrades.add(Upgrade.REGROWTH)
    tree, approach = next(
        (pos, (pos[0] + dx, pos[1] + dy))
        for pos in view._trees for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if world.passable(pos[0] + dx, pos[1] + dy) and world.is_visible(scene.human, pos)
    )
    gatherer = world.spawn_unit(scene.human, UnitType.PEASANT, tile_center(approach))
    world.harvest([gatherer.id], tree)
    for _ in range(600):
        game.tick(1 / 60)
        if tree not in view._trees:
            break
    assert tree not in view._trees and world.terrain_at(tree) is Terrain.GRASS and world.regrowth
    world.stop([gatherer.id])
    world.move([gatherer.id], hall_center := world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0].center)
    scene.speed = 8.0
    for _ in range(60 * 12):
        game.tick(1 / 60)
        if tree in view._trees:
            break
    assert world.terrain_at(tree) is Terrain.TREES and tree in view._trees and view._trees[tree].image.startswith("tree.")
    assert hall_center


def test_rooms_carry_the_creator_race_and_reject_nonsense(tmp_path) -> None:
    match = WarbandMatch(3, 40, 32, races=(Race.DWARF, None))
    assert match.world.players[0].race is Race.DWARF and match.world.players[1].race is not Race.DWARF
    assert match.snapshot(0)["world"]["players"][0]["race"] == "dwarf"
    served = create_match("warband-v1", {"seed": 3, "width": 40, "height": 32, "races": ["elf", None]})
    assert served.world.players[0].race is Race.ELF
    for bad in ("elf", ["elf"], ["elf", "hobbit"], [1, None]):
        with pytest.raises(CommandError, match="races"):
            create_match("warband-v1", {"seed": 3, "races": bad})
    assert BUILDINGS[BuildingType.TOWN_HALL].name == "Town Hall"  # the shared table is untouched by the race tables
