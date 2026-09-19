"""No text drawn over other text on any screen, at the window sizes players actually have."""

import pytest

from saga2d import Game
from saga2d.testing import assert_no_text_overlap, assert_text_fits, text_boxes
from warband.story.campaign import FORMAT, Progress, ProgressStore
from warband.story.campaign_scene import CampaignScene
from warband.story.dialog import DialogScene
from warband.story.mission_scene import MissionResultScene, MissionScene, build_world
from warband.story.missions import CAMPAIGN
from warband.sim.rules import BuildingType, Difficulty, Race, UnitType
from warband.sim.model import tile_center
from warband.records.profile import EARLY_EXIT_WEIGHT, MatchResult, Profile, standing
from warband.ui.profile_scene import NameScene, ProfileScene
from warband.records.replay import Replay, ReplayStore
from warband.ui.replay_scene import ReplayEndScene, ReplayScene
from warband.ui.controls import SCHEMES
from warband.ui.scene import DEFAULT_SETTINGS, CodexScene, GameOverScene, HelpScene, LeaveScene, PauseScene, SaveBrowserScene, SettingsScene, new_game
from warband.ui.score_scene import HighScoreScene
from warband.ui.style import build_theme
from warband.ui.title import NewGameScene, TitleScene

SIZES = [(1280, 800), (1280, 720), (1440, 900), (1728, 922), (1920, 1080)]  # the HUD is laid out for 1280 wide and up
SHORTEST = (1280, 720)  # where text runs into text first: the fast tier's size, the others are the slow tier's


def sizes(fast=SHORTEST) -> list:
    return [pytest.param(size, id=f"{size[0]}x{size[1]}", marks=() if size == fast else pytest.mark.slow) for size in SIZES]


def settle(game: Game, frames: int = 6) -> None:
    for _ in range(frames):
        game.tick(1 / 60)


def match(game: Game, races=None, controls: str = "classic"):
    scene = new_game(seed=5, races=races, settings=dict(DEFAULT_SETTINGS, controls=controls, tutorial=True))
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


def crowd(game: Game, count: int, page: int = 0):
    """A selection of *count* footmen and peasants, on the given portrait page."""
    scene = match(game)
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    units = [world.spawn_unit(scene.human, UnitType.PEASANT if i % 5 == 0 else UnitType.FOOTMAN, tile_center((hall.x - 6 + i % 12, hall.y + 5 + i // 12)))
             for i in range(count)]
    scene.select([u.id for u in units])
    scene.portrait_page = page
    settle(game)
    return scene


def rated(game: Game) -> Profile:
    """A profile with a few results and a replay of the last one, so the card and the profile screen have rows to lay out."""
    profile = Profile.load(game.data_dir)
    profile.rename("Ilya the Bold, o")
    for i, (outcome, difficulty, weight) in enumerate([("victory", "medium", 1.0), ("defeat", "hard", 1.0), ("left", "master", EARLY_EXIT_WEIGHT),
                                                        ("victory", "master", 1.0), ("resigned", "easy", 1.0)]):
        profile.record(MatchResult(f"match-{i}", f"2026-09-1{i}T10:00:00+00:00", outcome, weight,
                                   "left with no enemy at the gates and no material disadvantage: 0.2 of a loss" if outcome == "left" else "",
                                   difficulty, 1000, 1 + i % 3, "orc", 64, 48, "winter", "forest", 100 + i, 600 + 90 * i, i == 4))
    scene = new_game(seed=5)
    replay = Replay.begin(scene.world, seed=5, difficulty=scene.difficulty, human=scene.human)
    for _ in range(20):
        scene.world.step()
    replay.finish(scene.world, "resigned")
    ReplayStore(game.data_dir).save("match-4", replay, {})
    return profile


def replay(game: Game) -> ReplayScene:
    rated(game)
    scene = ReplayScene(ReplayStore(game.data_dir).load("match-4"))
    game.push(scene)
    settle(game)
    return scene


SCREENS = {
    "title": lambda game: game.push(TitleScene()),
    "title with a record": lambda game: (rated(game), game.push(TitleScene())),
    "profile": lambda game: (rated(game), game.push(TitleScene()), settle(game), game.push(ProfileScene())),
    "empty profile": lambda game: (game.push(TitleScene()), settle(game), game.push(ProfileScene())),
    "rename": lambda game: (p := rated(game), game.push(TitleScene()), settle(game), game.push(NameScene(p))),
    "leave": lambda game: (s := match(game), game.push(LeaveScene(s, standing(s.world, s.human), "Back to title", lambda: None))),
    "replay": replay,
    "replay over": lambda game: (s := replay(game), setattr(s, "skipping", True), settle(game, 12)),
    "new game": lambda game: (game.push(TitleScene()), settle(game), game.push(NewGameScene(game.scene))),
    "match, twelve units selected, a warning, the tutorial": match,
    "eighteen selected": lambda game: crowd(game, 18),
    "sixty selected, page two": lambda game: crowd(game, 60, page=1),
    "build menu": lambda game: (match(game), game.scene.select([next(u.id for u in game.scene.world.player_units(game.scene.human) if u.is_worker)]), game.scene.open_catalogue("build")),
    "pause": lambda game: game.push(PauseScene(match(game))),
    "settings": lambda game: game.push(SettingsScene(match(game))),
    "help": lambda game: (match(game), game.push(HelpScene(game.scene.scheme))),
    "help, grid": lambda game: game.push(HelpScene(SCHEMES["grid"])),
    "help, modal": lambda game: game.push(HelpScene(SCHEMES["modal"])),
    "grid, twelve units selected": lambda game: match(game, controls="grid"),
    "modal, nothing selected: the Train catalogue": lambda game: (match(game, controls="modal"), game.scene.select([]), settle(game)),
    "codex units": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 0))),
    "codex buildings": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 1))),
    "codex upgrades": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 2))),
    "codex races": lambda game: (s := match(game), game.push(CodexScene(s.world, s.human, 3))),
    "orc match, build menu": lambda game: (match(game, races=[Race.ORC, None]), game.scene.select([next(u.id for u in game.scene.world.player_units(game.scene.human) if u.is_worker)]), game.scene.open_catalogue("build")),
    "dwarf codex": lambda game: (s := match(game, races=[Race.DWARF, None]), game.push(CodexScene(s.world, s.human, 0))),
    "save browser": lambda game: (match(game), game.push(SaveBrowserScene(game, "save", on_pick=lambda slot: None))),
    "victory": lambda game: (s := match(game), setattr(s.world, "winner", s.human), game.push(GameOverScene(s))),
    "defeat": lambda game: (s := match(game), setattr(s.world.players[s.human], "alive", False), game.push(GameOverScene(s))),
    "high scores": lambda game: (s := match(game), game.push(HighScoreScene(size=(s.world.width, s.world.height)))),
    "campaign, fresh": lambda game: game.push(CampaignScene()),
    "campaign, under way": lambda game: (ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.HARD, completed=["hollowmere", "greywater"], flags={"truce": True})),
                                        game.push(CampaignScene())),
    "campaign, unreadable": lambda game: (ProgressStore(game.data_dir).saves.save(1, {"format": FORMAT + 1, "campaign": CAMPAIGN.id}, "WarbandCampaign"),
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
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM)
    game.push(scene)
    for _ in range(30):  # three seconds in tenths: past the title banner, which the objectives panel waits for
        game.tick(0.1)
    return scene


@pytest.mark.parametrize("size", sizes())
@pytest.mark.parametrize("screen", list(SCREENS), ids=list(SCREENS))
def test_no_text_is_drawn_over_other_text(screen: str, size: tuple[int, int], tmp_path) -> None:
    """Every screen at the shortest window in the fast tier; the other four sizes build the same scenes again,
    so they are the slow tier's."""
    game = Game("Warband layout", backend="mock", resolution=size, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        SCREENS[screen](game)
        settle(game)
        assert_no_text_overlap(game, top_scene_only=True)
    finally:
        game.close()


@pytest.mark.parametrize("size", sizes())
@pytest.mark.parametrize("screen", ["help", "help, grid", "help, modal"])
def test_help_fits_the_window(screen: str, size: tuple[int, int], tmp_path) -> None:
    """Every line of the help screen lies inside the window, in every control scheme: a row that runs off the edge
    teaches nothing.  The shortest window is the fast tier's, the other sizes the slow tier's."""
    game = Game("Warband layout", backend="mock", resolution=size, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        SCREENS[screen](game)
        settle(game)
        width, height = size
        outside = [box.text for box in text_boxes(game.backend) if box.space == "screen"
                   and not (0 <= box.left and box.left + box.width <= width and 0 <= box.top and box.top + box.height <= height)]
        assert not outside, outside
    finally:
        game.close()


@pytest.mark.parametrize("size, players", [pytest.param(size, players, id=f"{players}p-{size[0]}x{size[1]}",
                                                        marks=() if (size, players) == (SHORTEST, 4) else pytest.mark.slow)
                                           for size in SIZES for players in (2, 4)])
def test_the_match_intro_banner_stays_in_the_window(players: int, size: tuple[int, int], tmp_path) -> None:
    """The title and the roll of rivals, from the first frame of the slide to the last.

    The banner used to enter from 60 % of the window width to the left, so the
    opening frames drew both strings outside the window — a wipe nobody could read.
    Every frame of the two seconds is checked, so the fast tier takes the longest roll, four players in the
    shortest window, and the slow tier the rest.
    """
    game = Game("Warband intro", backend="mock", resolution=size, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(new_game(seed=3, players=players))
        for _ in range(2 * 60):  # the banner holds 1.2 s between two 0.35 s slides
            game.tick(1 / 60)
            assert_text_fits(game)
    finally:
        game.close()


def test_long_tutorial_objective_fits_its_panel(tmp_path) -> None:
    """The lumber instruction remains fully readable when the tutorial advances."""
    game = Game("Warband tutorial", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3)
        game.push(scene)
        worker = next(unit for unit in scene.world.player_units(scene.human) if unit.is_worker)
        scene.select([worker.id])
        scene.world.harvest([worker.id], scene.world.mines()[0].id)
        settle(game)
        assert scene.tutorial.current.text == "Right-click a tree with another peasant for lumber"
        x, y, width, height = scene.objectives.bounds
        instruction = [box for box in text_boxes(game.backend) if box.space == "screen"
                       and box.left >= x and y <= box.top < y + height]
        assert instruction
        assert all(box.right <= x + width for box in instruction), instruction
        assert_no_text_overlap(game, top_scene_only=True)
    finally:
        game.close()
