"""A seed the game chooses makes a fair map (WB-046). A few seeds in a thousand make none at some settings, and
where the game chose the seed it plays the next one instead; a seed the player gives is played as given, or
refused with the clear NoFairMap."""

import argparse
import json

import pytest

from saga2d import Game, MatchMenu
from warband.sim import mapgen
from warband.__main__ import lobby_options
from warband.sim.rules import Layout, Race
from warband.ui.scene import GameOverScene, GameScene, fair_map, new_game
from warband.ui.style import build_theme
from warband.ui.title import NewGameScene, TitleScene

UNFAIR = 67  # Small, two seats: every try at the forest this seed draws leaves its roads too straight


def unfair(**settings) -> int:
    """UNFAIR, checked for these settings: what the game does with an unfair seed needs one."""
    with pytest.raises(mapgen.NoFairMap):
        mapgen.generate(UNFAIR, 48, 40, 2, **settings)
    return UNFAIR


def same(a, b) -> bool:
    return json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def mock_game(tmp_path) -> Game:
    return Game("t", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")


def press(game, key) -> None:
    game.backend.inject_key(key)
    game.tick(1 / 60)


def test_fair_map_goes_on_to_the_next_seed_only_where_one_makes_no_fair_map() -> None:
    seed, world = fair_map(unfair(), 48, 40, 2)
    assert seed == UNFAIR + 1 and same(world, mapgen.generate(UNFAIR + 1, 48, 40, 2))
    assert fair_map(UNFAIR + 1, 48, 40, 2)[0] == UNFAIR + 1


def test_a_seed_the_player_gives_is_refused_clearly() -> None:
    with pytest.raises(mapgen.NoFairMap):
        new_game(unfair(), 48, 40, 2)


def open_new_game(game, title: TitleScene) -> NewGameScene:
    """New game over *title*'s settings; the title itself, and its backdrop, are not needed."""
    game.push(NewGameScene(title))
    game.tick(1 / 60)
    return game.scene


def test_new_game_goes_on_to_the_next_fair_seed_on_a_resize_or_a_reroll(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mapgen, "fresh_seed", lambda: UNFAIR)
    unfair(races=[Race.HUMAN, None])
    game = mock_game(tmp_path)
    try:
        scene = open_new_game(game, TitleScene())  # Medium, two seats, Humans, any layout: the seed is fair there
        assert scene.seed == UNFAIR
        press(game, "s")  # Small, where it is not
        assert scene.seed == UNFAIR + 1 and f"Seed {UNFAIR + 1}" in [t["text"] for t in game.backend.texts]
        assert same(scene.preview_world, mapgen.generate(UNFAIR + 1, 48, 40, 2, races=[Race.HUMAN, None]))
        press(game, "r")  # a reroll onto it
        assert scene.seed == UNFAIR + 1
    finally:
        game.close()


def test_new_game_starts_the_seed_and_map_it_shows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mapgen, "fresh_seed", lambda: UNFAIR)
    game = mock_game(tmp_path)
    try:
        scene = open_new_game(game, TitleScene(size="Small"))  # drawn onto the unfair seed
        assert scene.seed == UNFAIR + 1
        preview = scene.preview_world
        press(game, "return")
        assert isinstance(game.scene, GameScene) and game.scene.seed == UNFAIR + 1 and game.scene.world.terrain == preview.terrain
    finally:
        game.close()


def test_new_game_after_a_match_plays_the_next_fair_seed(tmp_path) -> None:
    game = mock_game(tmp_path)
    try:
        match = new_game(UNFAIR - 1, 48, 40, 2, layout=Layout.FOREST)
        races = [p.race for p in match.world.players]
        unfair(races=races, layout=Layout.FOREST)
        game.push(match)
        game.tick(1 / 60)
        match.world.winner = match.human
        game.push(GameOverScene(match))
        game.tick(1 / 60)
        press(game, "n")
        assert isinstance(game.scene, GameScene) and game.scene is not match and game.scene.seed == UNFAIR + 1
        assert game.scene.world.layout is Layout.FOREST and [p.race for p in game.scene.world.players] == races
    finally:
        game.close()


def test_rooms_from_the_multiplayer_menu_are_made_on_fair_seeds(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mapgen, "fresh_seed", lambda: UNFAIR)
    unfair(races=[Race.HUMAN, None])
    game = mock_game(tmp_path)
    try:
        game.push(TitleScene(size="Small"))
        game.tick(1 / 60)
        press(game, "m")
        menu = game.scene
        assert isinstance(menu, MatchMenu)
        assert menu.create_match().seed == UNFAIR + 1, "a LAN host"
        assert menu.create_options()["seed"] == UNFAIR + 1, "an online room"
    finally:
        game.close()


def test_the_command_lines_room_is_on_a_fair_seed_unless_it_gives_one(monkeypatch) -> None:
    monkeypatch.setattr(mapgen, "fresh_seed", lambda: UNFAIR)
    unfair(races=[Race.HUMAN, None])
    args = argparse.Namespace(seed=None, size="Small", theme="summer", race="human", layout="any")
    assert lobby_options(args)["seed"] == UNFAIR + 1
    assert lobby_options(argparse.Namespace(**{**vars(args), "seed": UNFAIR}))["seed"] == UNFAIR
