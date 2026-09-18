"""Starting the game on the windows players actually get.

``python -m warband`` asks for a window that fits the screen; the OS has the last
word.  Windows clips it under the taskbar, a 4K desktop hands back more pixels
than the request named, a player maximises it or toggles fullscreen between
matches.  Every such window gives the backend a different ``scale_factor``, and
everything rasterised at that scale — the title's backdrop, the match's ground —
has to survive the change.  The 2026-09-17 Windows report (BACKLOG.md, WB-022):
the first Start crashed because the title had registered a Medium map's ground
images at one scale and the match redrew them at another.
"""

import pytest

from saga2d import Game
from saga2d.backends.mock_backend import MockBackend
from warband.scene import GameScene, LeaveScene, PauseScene
from warband.style import build_theme
from warband.title import NewGameScene, TitleScene

# What the OS hands back after ``Game(resolution=None)`` asked for a window fitting a 1920×1080 desktop.
WINDOWS = {
    "as requested": (1840, 960),
    "clipped under the taskbar": (1840, 951),  # the reported crash: the ground came back 317 px for a 320 px image
    "maximised": (1920, 1040),
    "a small window": (960, 500),
    "maximised on a 4K monitor it was dragged to": (3840, 2120),
}

# The 3840×2160 Windows desktop of the 2026-09-17 report (WB-021), as measured on a real one at each scaling:
# the screen in desktop units, the desktop's scale, and the canvas and texture scale the engine gives the game.
DESKTOPS = {
    "3840x2160 at 200 %": ((1920, 1080), 2.0, (1840, 960), 2.0),
    "3840x2160 at 150 %": ((2560, 1440), 1.5, (2480, 1320), 1.5),
    "3840x2160 at 100 %": ((3840, 2160), 1.0, (2506, 1360), 1.5),
}


@pytest.fixture
def launch(tmp_path):
    game = Game("Warband", backend="mock", resolution=None, theme=build_theme(), save_dir=tmp_path / "saves")  # as __main__ does: fit the screen
    game.push(TitleScene())
    game.tick(1 / 60)
    yield game
    game.close()


def press(game: Game, *keys: str) -> None:
    for key in keys:
        game.backend.inject_key(key)
        game.tick(1 / 60)


def frames(game: Game, count: int = 3) -> None:
    for _ in range(count):
        game.tick(1 / 60)


def the_os_hands_back(game: Game, change) -> None:
    """Apply a display *change* and let the backend rasterise for the window that came of it.

    The mock backend derives ``scale_factor`` from the window it got, as the pyglet backend does.
    """
    change()
    frames(game)


def start_match(game: Game) -> GameScene:
    assert isinstance(game.scene, TitleScene)
    press(game, "n")
    assert isinstance(game.scene, NewGameScene)
    press(game, "return")
    assert isinstance(game.scene, GameScene)
    drawn = game.backend.frame_count
    frames(game)
    assert game.backend.frame_count == drawn + 3 and game.backend.sprites
    return game.scene


def back_to_title(game: Game) -> None:
    press(game, "escape")
    assert isinstance(game.scene, PauseScene)
    press(game, "t")
    if isinstance(game.scene, LeaveScene):
        press(game, "return")
    frames(game)
    assert isinstance(game.scene, TitleScene)


@pytest.mark.parametrize("window", WINDOWS.values(), ids=list(WINDOWS))
def test_the_first_match_starts_on_the_window_the_os_handed_back(launch, window) -> None:
    game = launch
    assert game.resolution == (1840, 960)
    the_os_hands_back(game, lambda: game.backend.inject_resize(*window))
    start_match(game)


@pytest.mark.slow
@pytest.mark.parametrize("screen, scale, canvas, texture_scale", DESKTOPS.values(), ids=list(DESKTOPS))
def test_a_4k_desktop_gets_a_canvas_made_for_it_and_plays(tmp_path, screen, scale, canvas, texture_scale) -> None:
    """The report's desktop: not a 3760×2040 canvas with the HUD at native pixels, and matches start, end and restart.

    Two matches per desktop with art painted at up to twice the scale, most of a second each: the slow tier."""
    game = Game("Warband", backend=MockBackend(screen=screen, desktop_scale=scale), resolution=None,
                theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene())
        game.tick(1 / 60)
        assert game.resolution == canvas and game.backend.scale_factor == pytest.approx(texture_scale, abs=0.001)
        start_match(game)
        back_to_title(game)
        the_os_hands_back(game, lambda: game.set_fullscreen(True))
        start_match(game)
    finally:
        game.close()


@pytest.mark.slow
def test_matches_start_after_the_window_changed_between_them(launch) -> None:
    """Title, match, title, match: each pair after a display change rasterises for a window the previous pair did not.

    Four matches, one per window, over a second: the slow tier."""
    game = launch
    start_match(game)
    for change in (lambda: game.backend.inject_resize(1840, 951), lambda: game.set_fullscreen(True), lambda: game.set_window_size((1280, 800))):
        back_to_title(game)
        the_os_hands_back(game, change)
        start_match(game)
