"""The launched game names the build it is: on the title screen, in the pause panel and from ``--version``.

Every bug report begins with which build it came from, and a screenshot is often all there is.  A published build
knows its number and the commit it was frozen from; a checkout has no number — the run that publishes it decides
that — so it names its commit, with a ``+`` when the working tree holds changes the commit does not.
"""

import subprocess
import sys

import pytest

from saga2d import Game, Label
from warband.__main__ import answered_by_the_parser, main
from warband.league import fastsim
from warband.ui.scene import DEFAULT_SETTINGS, PauseScene, new_game
from warband.ui.style import build_theme
from warband.ui.title import TitleScene
from warband.ui.version import ROOT, checkout_commit, describe, running_build

FROZEN = {"version": "0.2.98", "source_commit": "ebccd1d09f4a1b2c3d4e5f60718293a4b5c6d7e8", "working_tree_dirty": False}


def labels(game: Game) -> list[str]:
    return [str(widget.text) for widget in game.scene.ui.walk() if isinstance(widget, Label)]


def settle(game: Game, frames: int = 6) -> None:
    for _ in range(frames):
        game.tick(1 / 60)


def test_a_published_build_names_its_version_and_the_commit_it_was_frozen_from() -> None:
    assert describe(FROZEN, None) == "v0.2.98 · ebccd1d"


def test_a_build_frozen_from_a_dirty_tree_says_it_is_modified() -> None:
    """The packaging records a dirty tree; a build whose source is not the commit it names must not pass for it."""
    assert describe({**FROZEN, "working_tree_dirty": True}, None) == "v0.2.98 · ebccd1d · modified"


def test_a_checkout_names_its_commit_instead_of_a_version() -> None:
    assert describe(None, "62537f1+") == "checkout · 62537f1+"


def test_a_copy_with_no_commit_to_name_is_still_labelled() -> None:
    """Installed without its repository, or without git: there is nothing to name, and the label stays a label."""
    assert describe(None, None) == "checkout"


def test_this_checkout_is_named_by_the_commit_it_stands_at() -> None:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    commit = checkout_commit()
    assert commit is not None and commit.removesuffix("+") == head


def test_the_title_screen_shows_the_build(tmp_path) -> None:
    game = Game("Warband version", backend="mock", resolution=(1280, 720), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        game.push(TitleScene())
        settle(game)
        assert running_build() in labels(game)
    finally:
        game._teardown()


def test_the_pause_panel_shows_the_build_without_leaving_the_match(tmp_path) -> None:
    """Esc in a match is where a player looks it up mid-game, without losing the match to find out."""
    game = Game("Warband version", backend="mock", resolution=(1280, 720), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=5, settings=dict(DEFAULT_SETTINGS))
        game.push(scene)
        settle(game)
        game.push(PauseScene(scene))
        settle(game)
        assert f"Warband {running_build()}" in labels(game)
    finally:
        game._teardown()


@pytest.mark.parametrize("asks", ["--version", "--vers", "--help", "-h"])
def test_the_command_line_answers_help_and_version_without_the_compiled_simulation(asks: str, monkeypatch, capsys) -> None:
    """A checkout compiles the simulation on its first launch after its sources change: a line printed and an exit
    must not wait for that (``--version`` once waited eight minutes on a CI runner)."""
    monkeypatch.setattr(fastsim, "activate_for_game", lambda: pytest.fail("chose the simulation to print a line"))
    monkeypatch.setattr(sys, "argv", ["warband", asks])
    with pytest.raises(SystemExit) as exited:
        main()
    printed = capsys.readouterr().out
    assert exited.value.code == 0
    assert printed.startswith("usage: warband" if asks in ("-h", "--help") else f"Warband {running_build()}\n")


@pytest.mark.parametrize("argv, answered", [(["--seed", "3"], False), (["--mission", "list"], False), ([], False),
                                            (["--seed=--version"], False), (["--size", "Small", "--version"], True),
                                            (["--mission", "--help"], True), (["--help=x"], True)])
def test_only_a_line_the_parser_prints_skips_the_simulation(argv: list[str], answered: bool) -> None:
    """Whatever goes on to play chooses the simulation first; a command line naming help or version always ends in
    the parser, answered or refused (``--mission --help`` lacks the mission)."""
    assert answered_by_the_parser(argv) is answered


@pytest.mark.slow
def test_the_command_line_names_the_build_and_exits() -> None:
    """A whole interpreter start, a second of it: the slow tier's."""
    done = subprocess.run([sys.executable, "-m", "warband", "--version"], capture_output=True, text=True, check=True, cwd=ROOT)
    assert done.stdout.strip() == f"Warband {running_build()}"
