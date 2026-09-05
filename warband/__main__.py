"""Run Warband: ``python -m warband [--seed N] [--size Small|Medium|Large] [--players N] [--fullscreen]``.

Without ``--seed`` the game opens on the title screen (``--size`` and
``--players`` pre-fill the new-game options).  With ``--seed`` it skips the
title and starts that map directly, so a seed reproduces a match in one step.
"""

from __future__ import annotations

import argparse

from saga2d import Game, fonts
from warband import mapgen, sound
from warband.rules import Difficulty, MapTheme
from warband.scene import DEFAULT_SETTINGS, new_game
from warband.style import build_theme
from warband.title import TitleScene


def main() -> None:
    parser = argparse.ArgumentParser(description="Warband — a small Warcraft 2-style real-time strategy game")
    parser.add_argument("--seed", type=int, default=None, help="start this map directly, skipping the title screen")
    parser.add_argument("--size", choices=list(mapgen.SIZES), default="Medium")
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--difficulty", choices=[d.value for d in Difficulty], default="normal")
    parser.add_argument("--theme", choices=[t.value for t in MapTheme], default="summer")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--selftest", metavar="PNG", help="start a match in a hidden window, save one frame to PNG and exit (for packaged builds)")
    args = parser.parse_args()
    if args.selftest:
        selftest(args.selftest)
        return
    game = Game("Warband", resolution=None, fullscreen=args.fullscreen, theme=build_theme())
    settings = game.settings(DEFAULT_SETTINGS)
    if args.fullscreen:
        settings["fullscreen"] = True
    fonts.load(game)
    sound.install(game)
    sound.apply_volumes(settings["music"], settings["sfx"])
    if args.seed is not None:
        width, height = mapgen.SIZES[args.size]
        game.run(new_game(args.seed, width=width, height=height, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme),
                          settings=settings))
    else:
        game.run(TitleScene(size=args.size, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme), settings=settings))


def selftest(png: str) -> None:
    """Prove a build works without a screen: fonts, art, sound files and a rendered frame."""
    import os

    os.environ["SAGA2D_SILENT"] = "1"
    game = Game("Warband", resolution=(1280, 800), visible=False, theme=build_theme())
    fonts.load(game)
    bank = sound.install(game)
    game.push(new_game(1, settings=game.settings(DEFAULT_SETTINGS)))
    for _ in range(5):
        game.tick(1 / 60)
    game.backend.capture_frame().save(png)
    print(f"warband selftest: {len(bank.names)} sounds, frame written to {png}")
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
