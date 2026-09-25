"""Choosing a race on the title and seeing it everywhere: HUD, cards, codex, saves, rooms and the map."""

import pytest

from saga2d import CommandError, Game
from warband.online.authority import ONLINE, WarbandMatch
from warband.sim.model import tile_center
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, BuildingType, Race, Terrain, UnitType, Upgrade
from warband.ui.scene import CodexScene, GameScene, new_game
from warband.ui.tech import BRIGHT, TechTree
from warband.ui.style import build_theme
from warband.ui.title import RACE_KEYS, TitleScene


@pytest.fixture
def game(tmp_path):
    g = Game("Warband Races", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


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
    assert "Orcs" in shown and any(f"The Orcs of {scene.player.name} against the" in t for t in shown)
    peon = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    click_tile(game, scene, peon.pos)
    assert "Peon" in texts(game)
    press(game, "b")
    labels = {c.label: c.hotkey for c in scene.card}
    assert labels["Hall"] == "H" and labels["War Camp"] == "B" and labels["Kennels"] == "S" and "Barracks" not in labels
    press(game, "f5")
    game.clear_and_push(TitleScene())
    game.tick(1 / 60)
    press(game, "c")
    assert isinstance(game.scene, GameScene) and game.scene.player.race is Race.ORC and game.scene.race.name == "Orcs"


def test_the_title_opens_the_codex_for_the_race_chosen_under_new_game(game) -> None:
    """The codex is readable before a match is started: F2 on the title, the race New game is set to, nothing owned."""
    game.push(TitleScene())
    game.tick(1 / 60)
    press(game, "f2")
    assert isinstance(game.scene, CodexScene)
    shown = texts(game)
    assert "Codex — the Humans" in shown and "Footman" in shown and "Grunt" not in shown
    press(game, "3")  # upgrades: none is researched outside a match, so none is ticked
    assert not any(t.endswith(" ✓") for t in texts(game))
    press(game, "5")  # the tech tree is the plain reference out of a match: no settlement to light it by
    assert RACES[Race.HUMAN].buildings[BuildingType.BARRACKS].name in texts(game)
    tree = game.scene.ui.find(lambda c: isinstance(c, TechTree))
    assert all(picture.opacity == BRIGHT for picture in tree.pictures)
    assert not any("faint: not yet" in t for t in texts(game))
    press(game, "escape")
    assert isinstance(game.scene, TitleScene)
    press(game, "n")
    press(game, RACE_KEYS[Race.ORC].lower())
    press(game, "escape")
    press(game, "f2")
    shown = texts(game)
    assert "Codex — the Orcs" in shown and "Grunt" in shown and "Footman" not in shown


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
    labels = [c.label for c in scene.card]
    assert labels == ["Ogre", "Plunder", "Cancel"]  # Horse Breeding is a Human art, the Gryphon Rider a Human unit
    press(game, "h")
    assert kennels.research is Upgrade.PLUNDER
    game.tick(1 / 60)
    scene.mouse = (scene.selection_panel.bounds[0] + 120, scene.selection_panel.bounds[1] + 70)  # over the readout
    game.tick(1 / 60)
    assert scene.tooltip.startswith("Researching Plunder")
    scene.select([])
    scene.open_catalogue("upgrade")
    labels = [c.label for c in scene.card]
    assert "Bloodlust" in labels and "Plunder" in labels and "Horses" not in labels and "Blessing" not in labels
    scene.open_catalogue("train")
    trained = [c.label for c in scene.card]
    assert trained[:3] == ["Peon", "Grunt", "Axethrower"] and "Goblin Sapper" in trained and "Gryphon Rider" not in trained
    scene.open_catalogue(None)
    press(game, "f2")
    assert isinstance(game.scene, CodexScene)
    shown = texts(game)
    assert "Codex — the Orcs" in shown and "Grunt" in shown and "Goblin Sapper" in shown and "Footman" not in shown
    assert "Treant" not in shown  # the Elves' own
    press(game, "2")
    assert "Great Hall" in texts(game)
    press(game, "4")
    shown = texts(game)
    assert "Codex — the four races" in shown and "Orcs ✓" in shown
    for race in Race:
        assert any(RACES[race].passive in t for t in shown), race
    press(game, "escape")


@pytest.mark.slow
def test_a_regrown_tree_gets_a_sprite_and_a_felled_one_loses_it(game) -> None:
    """A tree grows back after a minute of the match and its computer players, about three seconds: the slow
    tier."""
    scene = new_game(seed=5, races=[Race.ELF, None])
    game.push(scene)
    game.tick(1 / 60)
    world, view = scene.world, scene.view
    scene.player.upgrades.add(Upgrade.REGROWTH)
    tree, approach = next(
        (pos, (pos[0] + dx, pos[1] + dy))
        for pos in view.tree_sprites for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if world.passable(pos[0] + dx, pos[1] + dy) and world.is_visible(scene.human, pos)
    )
    gatherer = world.spawn_unit(scene.human, UnitType.PEASANT, tile_center(approach))
    world.harvest([gatherer.id], tree)
    for _ in range(100):  # ten seconds at most, in tenths: the felling and the regrowth are waited for
        game.tick(0.1)
        if tree not in view.tree_sprites:
            break
    assert tree not in view.tree_sprites and world.terrain_at(tree) is Terrain.GRASS and world.regrowth
    world.stop([gatherer.id])
    world.move([gatherer.id], hall_center := world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0].center)
    scene.speed = 3.0  # a tenth of a second at three times speed is six steps, the most a frame takes
    for _ in range(220):
        game.tick(0.1)
        if tree in view.tree_sprites:
            break
    assert world.terrain_at(tree) is Terrain.TREES and tree in view.tree_sprites and view.tree_sprites[tree].image.startswith("tree.")
    assert hall_center


def test_rooms_carry_the_creator_race_and_reject_nonsense(tmp_path) -> None:
    match = WarbandMatch(3, 48, 40, races=(Race.DWARF, None))
    assert match.world.players[0].race is Race.DWARF and match.world.players[1].race is not Race.DWARF
    assert match.snapshot(0)["world"]["players"][0]["race"] == "dwarf"
    served = ONLINE["warband-v2"].create({"seed": 3, "width": 48, "height": 40, "races": ["elf", None]})
    assert served.world.players[0].race is Race.ELF
    for bad in ("elf", ["elf"], ["elf", "hobbit"], [1, None]):
        with pytest.raises(CommandError, match="races"):
            ONLINE["warband-v2"].create({"seed": 3, "races": bad})
    assert BUILDINGS[BuildingType.TOWN_HALL].name == "Town Hall"  # the shared table is untouched by the race tables
