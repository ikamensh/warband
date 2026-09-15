"""No text drawn over other text on any screen, at the window sizes players actually have."""

import pytest

from saga2d import Game
from saga2d.testing import assert_no_text_overlap, text_boxes
from warband.campaign import Progress, ProgressStore
from warband.campaign_scene import CampaignScene
from warband.dialog import DialogScene
from warband.mission_scene import MissionResultScene, MissionScene, build_world
from warband.missions import CAMPAIGN
from warband.rules import BuildingType, Difficulty, Race, UnitType
from warband.model import tile_center
from warband.scene import CodexScene, GameOverScene, HelpScene, PauseScene, SaveBrowserScene, SettingsScene, new_game
from warband.score_scene import HighScoreScene
from warband.style import build_theme
from warband.title import NewGameScene, TitleScene

SIZES = [(1280, 800), (1280, 720), (1440, 900), (1728, 922), (1920, 1080)]  # the HUD is laid out for 1280 wide and up


def settle(game: Game, frames: int = 6) -> None:
    for _ in range(frames):
        game.tick(1 / 60)


def match(game: Game, races=None):
    scene = new_game(seed=5, races=races)
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
    "codex races": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 3))),
    "orc match, build menu": lambda game: (match(game, races=[Race.ORC, None]), game.scene.select([next(u.id for u in game.scene.world.player_units(game.scene.human) if u.is_worker)]), game.scene.open_build_menu()),
    "dwarf codex": lambda game: (s := match(game, races=[Race.DWARF, None]), game.push(CodexScene(s.world, s.human, 0))),
    "save browser": lambda game: (match(game), game.push(SaveBrowserScene(game, "save", on_pick=lambda slot: None))),
    "victory": lambda game: (s := match(game), setattr(s.world, "winner", s.human), game.push(GameOverScene(s))),
    "defeat": lambda game: (s := match(game), setattr(s.world.players[s.human], "alive", False), game.push(GameOverScene(s))),
    "high scores": lambda game: (s := match(game), game.push(HighScoreScene(size=(s.world.width, s.world.height)))),
    "campaign, fresh": lambda game: game.push(CampaignScene()),
    "campaign, under way": lambda game: (ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.HARD, completed=["hollowmere", "greywater"], flags={"truce": True})),
                                        game.push(CampaignScene())),
    "mission, objectives": lambda game: mission_scene(game, "hollowmere"),
    "dialogue, a line": lambda game: (s := mission_scene(game, "greywater"), game.push(DialogScene(s.mission.briefing, CAMPAIGN.speakers, s.run.vars))),
    "dialogue, a choice": lambda game: (s := mission_scene(game, "karst_hold"), game.push(DialogScene(s.mission.debrief[2:], CAMPAIGN.speakers, s.run.vars))),
    "mission complete": lambda game: (s := mission_scene(game, "court_of_thorns"), s.run.state.update(court="done", orcs="done"), game.push(MissionResultScene(s, won=True))),
    "mission failed": lambda game: (s := mission_scene(game, "silent_hold"), s.run.state.update(maren="failed"),
                                    game.push(MissionResultScene(s, won=False, reason="Sister Maren must survive"))),
    "mission pause": lambda game: (s := mission_scene(game, "retaken"), game.push(s.pause_menu())),
}


def mission_scene(game: Game, mission_id: str):
    run = build_world(CAMPAIGN.mission(mission_id), flags={"truce": True})
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.NORMAL)
    game.push(scene)
    settle(game)
    return scene


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


@pytest.mark.parametrize("size", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
def test_help_fits_the_window(size: tuple[int, int], tmp_path) -> None:
    """Every line of the help screen lies inside the window: a row that runs off the edge teaches nothing."""
    game = Game("Warband layout", backend="mock", resolution=size, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        SCREENS["help"](game)
        settle(game)
        width, height = size
        outside = [box.text for box in text_boxes(game.backend) if box.space == "screen"
                   and not (0 <= box.left and box.left + box.width <= width and 0 <= box.top and box.top + box.height <= height)]
        assert not outside, outside
    finally:
        game._teardown()
