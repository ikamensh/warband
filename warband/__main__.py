"""Run Warband: ``python -m warband [--seed N] [--size Small|Medium|Large] [--players N] [--fullscreen]``.

Without ``--seed`` the game opens on the title screen (``--size`` and
``--players`` pre-fill the new-game options).  With ``--seed`` it skips the
title and starts that map directly, so a seed reproduces a match in one step.
"""

from __future__ import annotations

import argparse

from saga2d import Game, fonts
from warband import mapgen, sound
from warband.scene import new_game
from warband.style import build_theme
from warband.title import TitleScene


def main() -> None:
    parser = argparse.ArgumentParser(description="Warband — a small Warcraft 2-style real-time strategy game")
    parser.add_argument("--seed", type=int, default=None, help="start this map directly, skipping the title screen")
    parser.add_argument("--size", choices=list(mapgen.SIZES), default="Medium")
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()
    game = Game("Warband", resolution=None, fullscreen=args.fullscreen, theme=build_theme())
    fonts.load(game)
    sound.install(game)
    if args.seed is not None:
        width, height = mapgen.SIZES[args.size]
        game.run(new_game(args.seed, width=width, height=height, players=args.players))
    else:
        game.run(TitleScene(size=args.size, players=args.players))


if __name__ == "__main__":
    main()
