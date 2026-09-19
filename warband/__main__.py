"""Run Warband: ``python -m warband [--seed N] [--size Small|Medium|Large] [--players N] [--layout NAME] [--fullscreen]``.

Without ``--seed`` the game opens on the title screen (``--size`` and
``--players`` pre-fill the new-game options).  With ``--seed`` it skips the
title and starts that map directly, so a seed reproduces a match in one step.
``--campaign`` opens the campaign screen; ``--mission ID`` starts that
mission straight away, with the saved progress's choices, skipping the
briefing (for looking at one mission; ``--mission list`` names them).
"""

from __future__ import annotations

import argparse
from typing import Any

from saga2d import add_match_arguments, match_from_arguments
from saga2d import Game, fonts
from warband import mapgen, sound
from warband.rules import Difficulty, Layout, MapTheme, Race
from warband.scene import DEFAULT_SETTINGS, fair_map, new_game
from warband.style import build_theme
from warband.title import TitleScene


def main() -> None:
    parser = argparse.ArgumentParser(description="Warband — a small Warcraft 2-style real-time strategy game")
    parser.add_argument("--seed", type=int, default=None, help="start this map directly, skipping the title screen")
    parser.add_argument("--size", choices=list(mapgen.SIZES), default="Medium")
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--difficulty", choices=[d.value for d in Difficulty], default="medium")
    parser.add_argument("--theme", choices=[t.value for t in MapTheme], default="summer")
    parser.add_argument("--race", choices=[r.value for r in Race], default="human", help="your race; the computer players' are drawn from the seed")
    parser.add_argument("--layout", choices=[each.value for each in Layout] + ["any"], default="any", help="the map's shape; any draws one from the seed")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--campaign", action="store_true", help="open the campaign screen")
    parser.add_argument("--mission", metavar="ID", help="start this campaign mission directly (or 'list')")
    parser.add_argument("--selftest", metavar="PNG", help="start a match in a hidden window, save one frame to PNG and exit (for packaged builds)")
    add_match_arguments(parser)
    args = parser.parse_args()
    if args.mission == "list":
        from warband.missions import CAMPAIGN

        for mission in CAMPAIGN.missions:
            print(f"{mission.id:16} {CAMPAIGN.index(mission)}. {mission.title} · {mission.act}")
        return
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
    from warband.authority import WarbandMatch
    from warband.multiplayer import NetworkGameScene
    layout = None if args.layout == "any" else Layout(args.layout)
    lobby = match_from_arguments(args, parser, title="Warband", game_id="warband-v2",
                                 create_match=lambda: WarbandMatch(**{**lobby_options(args), 'theme': MapTheme(args.theme),
                                                                      'races': (Race(args.race), None), 'layout': layout}),
                                 create_scene=lambda session, match: NetworkGameScene(session, match, settings=settings),
                                 create_options=lambda: lobby_options(args), game=game)
    if lobby is not None:
        game.run(lobby)
        return
    if args.campaign or args.mission is not None:
        from warband.campaign_scene import CampaignScene
        from warband.mission_scene import MissionScene, build_world, current_progress
        from warband.missions import CAMPAIGN

        if args.mission is None:
            game.run(CampaignScene(settings))
            return
        progress = current_progress(game, CAMPAIGN, Difficulty(args.difficulty))
        run = build_world(CAMPAIGN.mission(args.mission), flags=progress.flags)
        game.run(MissionScene(CAMPAIGN, run, difficulty=progress.difficulty, settings=settings))
        return
    if args.seed is not None:
        width, height = mapgen.SIZES[args.size]
        game.run(new_game(args.seed, width=width, height=height, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme),
                          settings=settings, races=[Race(args.race)] + [None] * (args.players - 1), layout=layout))
    else:
        game.run(TitleScene(size=args.size, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme), race=Race(args.race),
                            layout=layout, settings=settings))


def lobby_options(args: argparse.Namespace) -> dict[str, Any]:
    """The two-seat room a command line hosts or creates: on its ``--seed`` as given, or on a fresh seed that makes a
    fair map of its settings (WB-046)."""
    width, height = mapgen.SIZES[args.size]
    layout = None if args.layout == "any" else Layout(args.layout)
    seed = args.seed if args.seed is not None else fair_map(mapgen.fresh_seed(), width, height, 2, theme=MapTheme(args.theme),
                                                            races=[Race(args.race), None], layout=layout)[0]
    return {'seed': seed, 'width': width, 'height': height, 'theme': args.theme, 'races': [args.race, None], 'layout': args.layout}


def selftest(png: str) -> None:
    """Prove a build works without a screen: fonts, art, sound files, and a match started from the title on a window the OS resized."""
    import os

    os.environ["SAGA2D_SILENT"] = "1"
    game = Game("Warband", resolution=(1280, 800), visible=False, theme=build_theme())
    fonts.load(game)
    bank = sound.install(game)
    game.push(TitleScene(settings=game.settings(DEFAULT_SETTINGS)))
    game.tick(1 / 60)
    game.set_window_size((1271, 791))  # the OS has the last word on the window; the match starts on what it gives
    game.tick(1 / 60)
    game.scene.new_game()
    game.tick(1 / 60)
    game.scene.start()
    for _ in range(5):
        game.tick(1 / 60)
    game.backend.capture_frame().save(png)
    bank.wait()
    print(f"warband selftest: {len(bank.names)} sounds, {len(bank.ready)} tracks, frame written to {png}")
    game._teardown()
    game.backend.quit()


if __name__ == "__main__":
    main()
