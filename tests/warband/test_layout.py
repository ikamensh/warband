"""No text drawn over other text on any screen, at the window sizes players actually have."""

import pytest

from saga2d import Game
from saga2d.testing import assert_no_text_overlap
from warband.rules import BuildingType, UnitType
from warband.model import tile_center
from warband.scene import CodexScene, GameOverScene, HelpScene, PauseScene, SaveBrowserScene, SettingsScene, new_game
from warband.style import build_theme
from warband.title import NewGameScene, TitleScene

SIZES = [(1280, 800), (1280, 720), (1440, 900), (1728, 922), (1920, 1080)]  # the HUD is laid out for 1280 wide and up


def settle(game: Game, frames: int = 6) -> None:
    for _ in range(frames):
        game.tick(1 / 60)


def match(game: Game):
    scene = new_game(seed=5)
    game.push(scene)
    settle(game)
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    for i in range(12):
        world.spawn_unit(scene.human, list(UnitType)[i % len(UnitType)], tile_center((hall.x + 4 + i % 6, hall.y + 4 + i // 6)))
    scene.select([u.id for u in world.player_units(scene.human)])
    scene.warn("Requires a Barracks")
    settle(game)
    return scene


SCREENS = {
    "title": lambda game: game.push(TitleScene()),
    "new game": lambda game: (game.push(TitleScene()), settle(game), game.push(NewGameScene(game.scene))),
    "match, twelve units selected, a warning, the tutorial": match,
    "build menu": lambda game: (match(game), game.scene.select([next(u.id for u in game.scene.world.player_units(game.scene.human) if u.is_worker)]), game.scene.open_build_menu()),
    "pause": lambda game: game.push(PauseScene(match(game))),
    "settings": lambda game: game.push(SettingsScene(match(game))),
    "help": lambda game: (match(game), game.push(HelpScene())),
    "codex units": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 0))),
    "codex buildings": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 1))),
    "codex upgrades": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 2))),
    "save browser": lambda game: (match(game), game.push(SaveBrowserScene(game, "save", on_pick=lambda slot: None))),
    "victory": lambda game: game.push(GameOverScene(match(game), True)),
    "defeat": lambda game: game.push(GameOverScene(match(game), False)),
}


@pytest.mark.parametrize("size", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
@pytest.mark.parametrize("screen", list(SCREENS), ids=list(SCREENS))
def test_no_text_is_drawn_over_other_text(screen: str, size: tuple[int, int], tmp_path) -> None:
    game = Game("Warband layout", backend="mock", resolution=size, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        SCREENS[screen](game)
        settle(game)
        assert_no_text_overlap(game, top_scene_only=True)
    finally:
        game._teardown()
