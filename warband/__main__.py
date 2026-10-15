"""Run Warband: ``python -m warband [--seed N] [--size Small|Medium|Large] [--players N] [--layout NAME] [--fullscreen]``.

Without ``--seed`` the game opens on the title screen (``--size`` and
``--players`` pre-fill the new-game options).  With ``--seed`` it skips the
title and starts that map directly, so a seed reproduces a match in one step.
``--campaign`` opens the campaign screen; ``--mission ID`` starts that
mission straight away, with the saved progress's choices, skipping the
briefing (for looking at one mission; ``--mission list`` names them).
``--server-info`` asks the room server how busy it is and exits, without
choosing the simulation or opening a window.

Online rooms from the command line mirror the Multiplayer screen: ``--online-host``
creates a room (``--players`` seats, ``--rated`` for a rated room, ``--race`` for
your own seat), ``--online-join CODE`` joins one with your own race choice, and
``--online-resume`` rejoins the saved seat.  Joins follow the host's rated room;
``--rated`` with anything but ``--online-host`` is refused.

The simulation runs compiled (:func:`warband.league.fastsim.activate_for_game`),
about ten times faster: a checkout compiles it on the first launch after its
sources change, a minute or so, and ``WARBAND_INTERPRETED=1`` runs the source.
So nothing here imports the simulation before :func:`main` has chosen it.
``--help`` and ``--version`` print a line and exit, so they never wait for that compile.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

ICON = Path(__file__).parent / "assets" / "icon.png"  # what the Dock, the taskbar and the built app draw Warband under

#: This game's rooms on the server, shared by the screen and the command line.
GAME_ID = "warband-v2"
#: Seats an online room holds; LAN stays a two-seat game.
ROOM_SEATS = (2, 3, 4)
#: The saved-seat record's shape, exactly the framework's: the base lobby lifecycle writes it.
LAST_ROOM_DEFAULTS = {"game_id": "", "endpoint": "", "room": "", "resume_token": ""}
LAST_ROOM_FILE = "online-room.json"


def main() -> None:
    if server_info_requested(sys.argv[1:]):
        from warband.online import server_info  # headless: no simulation, window, fonts, art, audio or UI

        server_info.run(sys.argv[1:])
        return
    from warband.league import fastsim  # after the headless branch: choosing the simulation imports it
    if not answered_by_the_parser(sys.argv[1:]):
        fastsim.activate_for_game()  # before anything imports the simulation: whatever does from here on gets the compiled one
    parser = cli_parser()
    args = parser.parse_args()
    _run_with_args(args, parser)


def cli_parser() -> argparse.ArgumentParser:
    """The full game command line, testable without opening a window: local play plus LAN and online rooms."""
    from saga2d import add_match_arguments

    from warband.sim import mapgen
    from warband.sim.rules import Difficulty, Layout, MapTheme, Race
    from warband.ui.version import running_build

    parser = argparse.ArgumentParser(description="Warband — a small Warcraft 2-style real-time strategy game")
    parser.add_argument("--seed", type=int, default=None, help="start this map directly, skipping the title screen")
    parser.add_argument("--size", choices=list(mapgen.SIZES), default="Medium")
    parser.add_argument("--players", type=int, default=2, choices=range(2, mapgen.MAX_PLAYERS + 1), metavar="N",
                        help=f"seats, 2 to {mapgen.MAX_PLAYERS}; a size that cannot seat them is refused")
    parser.add_argument("--difficulty", choices=[d.value for d in Difficulty], default="medium")
    parser.add_argument("--theme", choices=[t.value for t in MapTheme], default="summer")
    parser.add_argument("--race", choices=[r.value for r in Race], default="human", help="your race; the computer players' are drawn from the seed")
    parser.add_argument("--layout", choices=[each.value for each in Layout] + ["any"], default="any", help="the map's shape; any draws one from the seed")
    parser.add_argument("--magic", action="store_true", help="enable ley rifts, magical buildings and spells (off by default)")
    parser.add_argument("--no-wilds", dest="wilds", action="store_false", help="leave neutral creature camps off the map (same terrain and deposits)")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--rated", action="store_true", help="host a rated online room (with --online-host only; joins follow the host)")
    parser.add_argument("--version", action="version", version="Warband " + running_build(), help="name this build and exit")
    parser.add_argument("--campaign", action="store_true", help="open the campaign screen")
    parser.add_argument("--mission", metavar="ID", help="start this campaign mission directly (or 'list')")
    parser.add_argument("--selftest", metavar="PNG", help="start a match in a hidden window, save one frame to PNG and exit (for packaged builds)")
    parser.add_argument("--server-info", action="store_true", help="ask the room server how busy it is and exit (answered before the game starts)")
    parser.add_argument("--json", action="store_true", help="print --server-info as JSON")
    parser.add_argument("--timeout", metavar="SECONDS", type=float, default=None, help="seconds to wait for --server-info")
    add_match_arguments(parser)
    return parser


def _run_with_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from saga2d import Game, fonts
    from warband.audio import sound
    from warband.sim import mapgen
    from warband.sim.rules import Difficulty, Layout, MapTheme, Race
    from warband.ui.scene import DEFAULT_SETTINGS, new_game
    from warband.ui.style import build_theme
    from warband.ui.title import TitleScene

    if args.mission == "list":
        from warband.story.catalog import CAMPAIGNS

        for campaign in CAMPAIGNS:
            print(campaign.title)
            for mission in campaign.missions:
                print(f"{mission.id:24} {campaign.index(mission)}. {mission.title} · {mission.act}")
        return
    if args.selftest:
        selftest(args.selftest)
        return
    game = Game("Warband", resolution=None, fullscreen=args.fullscreen, theme=build_theme(), icon=ICON)
    settings = game.settings(DEFAULT_SETTINGS)
    if args.fullscreen:
        settings["fullscreen"] = True
    fonts.load(game)
    sound.install(game)
    sound.apply_volumes(settings["music"], settings["sfx"])
    lobby = multiplayer_lobby(args, parser, game, settings)
    if lobby is not None:
        game.run(lobby)
        return
    if args.campaign or args.mission is not None:
        from warband.story.campaign_scene import CampaignScene
        from warband.story.mission_scene import MissionScene, build_world, current_progress
        from warband.story.catalog import find_mission

        if args.mission is None:
            game.run(CampaignScene(settings))
            return
        try:
            campaign, mission = find_mission(args.mission)
        except KeyError as error:
            parser.error(str(error))
        progress = current_progress(game, campaign, Difficulty(args.difficulty))
        run = build_world(mission, flags=progress.flags)
        game.run(MissionScene(campaign, run, difficulty=progress.difficulty, settings=settings))
        return
    layout = None if args.layout == "any" else Layout(args.layout)
    refused = mapgen.refusal(*mapgen.dimensions(args.size, args.players), args.players, layout)
    if refused is not None:
        parser.error(f"{refused}. Sizes for {args.players}: {', '.join(mapgen.sizes_for(args.players, layout)) or 'none'}.")
    if args.seed is not None:
        width, height = mapgen.dimensions(args.size, args.players)
        game.run(new_game(args.seed, width=width, height=height, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme),
                          settings=settings, races=[Race(args.race)] + [None] * (args.players - 1), layout=layout, magic=args.magic,
                          wilds=args.wilds))
    else:
        game.run(TitleScene(size=args.size, players=args.players, difficulty=Difficulty(args.difficulty), theme=MapTheme(args.theme), race=Race(args.race),
                            layout=layout, settings=settings, magic=args.magic, wilds=args.wilds))


def multiplayer_lobby(args: argparse.Namespace, parser: argparse.ArgumentParser, game, settings):
    """A Warband lobby for an explicit CLI multiplayer request, otherwise ``None``.

    Online rooms go through :class:`OnlineClient` with the durable per-endpoint
    identity (:func:`online_identity`) and the command line's own race as
    ``player_options`` on create and join only; resume reuses the saved seat and
    endpoint with the identity for that endpoint and no race override.  The host's
    ``--players`` count reaches the room faithfully; anything but ``--online-host``
    with ``--rated`` is refused, since joins follow the host and rejoin keeps its
    room.  LAN reuses the shared transport and is wrapped in the same Warband lobby,
    so the command line and the screen wait in the same room; its lifecycle saving
    stays the base's.
    """
    online = bool(args.online_host or args.online_join or args.online_resume)
    lan = bool(args.host or args.join)
    if args.rated and not args.online_host:
        parser.error("--rated needs --online-host: joins follow the host's room, rejoin keeps its room.")
    if online:
        from saga2d.online import OnlineClient

        from warband.ui.multiplayer import NetworkGameScene, WarbandLobby, online_identity

        endpoint = args.server or None
        make_scene = lambda connection: NetworkGameScene(connection, None, settings=settings)  # noqa: E731
        if args.online_host:
            try:
                options = lobby_options(args, players=args.players)
            except ValueError as exc:
                parser.error(str(exc))
            session = OnlineClient(GAME_ID, endpoint=endpoint, options=options,
                                   **online_identity(game, endpoint),
                                   rated=args.rated,
                                   player_options={"race": args.race})
            return WarbandLobby(session, make_scene, title="Warband multiplayer")
        if args.online_join:
            session = OnlineClient(GAME_ID, endpoint=endpoint, room=args.online_join,
                                   **online_identity(game, endpoint),
                                   player_options={"race": args.race})
            return WarbandLobby(session, make_scene, title="Warband multiplayer")
        from saga2d import Settings

        record = Settings(game.data_dir / LAST_ROOM_FILE, dict(LAST_ROOM_DEFAULTS))
        if (record.error or record["game_id"] != GAME_ID
                or not record["room"] or not record["resume_token"]
                or not (args.server or record["endpoint"])):
            parser.error("No saved online room for this game. Create or join a room first.")
        saved_endpoint = args.server or record["endpoint"] or None
        session = OnlineClient(GAME_ID, endpoint=saved_endpoint, room=record["room"],
                               resume_token=record["resume_token"],
                               **online_identity(game, saved_endpoint))
        return WarbandLobby(session, make_scene, title="Warband multiplayer")
    if lan:
        from saga2d import match_from_arguments

        from warband.online.authority import WarbandMatch
        from warband.sim.rules import Layout, MapTheme, Race
        from warband.ui.multiplayer import NetworkGameScene, WarbandLobby

        layout = None if args.layout == "any" else Layout(args.layout)
        base = match_from_arguments(args, parser, title="Warband multiplayer", game_id=GAME_ID,
                                    create_match=lambda: WarbandMatch(**{**lobby_options(args), "theme": MapTheme(args.theme),
                                                                         "races": (Race(args.race), None), "layout": layout}),
                                    create_scene=lambda session, match: NetworkGameScene(session, match, settings=settings),
                                    create_options=lambda: lobby_options(args), game=game)
        return WarbandLobby(base.session, base.make_scene, title="Warband multiplayer")
    return None


#: Flags answered by the info parser, without the simulation or a window.
INFO_FLAGS = ("--server-info", "--json", "--timeout")
#: Game options an info abbreviation must not steal (--serv and --j stay ambiguous, as in the game parser).
INFO_RIVALS = ("--server", "--join", "--theme")


def server_info_requested(argv: list[str]) -> bool:
    """Whether *argv* carries a server-info flag, answered without the simulation or a window.

    ``--server-info`` (and its malformed extensions, refused clearly), ``--json``
    and ``--timeout`` all route to the info parser before anything compiles: alone
    the latter two are mistakes to refuse, not a match to play.  A unique
    prefix the game parser would expand (``--server-inf``, like ``--vers`` for
    ``--version``) routes the same way; anything a game option could also
    claim stays on the game's path."""
    for token in argv:
        word = token.split("=", 1)[0]
        if not word.startswith("--"):
            continue
        if any(word == flag or word.startswith(flag) for flag in INFO_FLAGS):
            return True
        if (sum(flag.startswith(word) for flag in INFO_FLAGS) == 1
                and not any(rival.startswith(word) for rival in INFO_RIVALS)):
            return True
    return False


def answered_by_the_parser(argv: list[str]) -> bool:
    """Whether *argv* asks for ``--help`` or ``--version``, which the parser answers and exits on (or refuses with the
    usage line): nothing then runs the simulation, which only builds the parser from the source.

    A checkout compiles the simulation on its first launch after its sources change, a minute on a Mac and eight on a
    busy CI runner, which ``--version`` once waited for.  A prefix the parser would expand (``--vers``) counts too.
    ``--server-info`` answers its own way, but likewise never chooses the simulation."""
    asks = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    asks.add_argument("-h", "--help", action="store_true")
    asks.add_argument("--version", action="store_true")
    try:
        known = asks.parse_known_args(argv)[0]
    except argparse.ArgumentError:  # --help=x: the parser refuses it with the whole usage line
        return True
    return known.help or known.version or server_info_requested(argv)


def lobby_options(args: argparse.Namespace, players: int = 2) -> dict[str, Any]:
    """The online room a command line hosts: on its ``--seed`` as given, or on a fresh seed that makes a
    fair map of its settings (WB-046).

    *players* is the room's seat count: the online host passes its ``--players`` so a
    2/3/4-seat request reaches the server faithfully, while older callers keep the
    two-seat default.  Sizes, dimensions and layouts that cannot hold the seats are
    refused clearly instead of silently falling back to another map.
    """
    from warband.online.authority import ONLINE_SIZE
    from warband.sim import mapgen
    from warband.sim.rules import Layout, MapTheme, Race
    from warband.ui.scene import fair_map

    seats = players
    if seats not in ROOM_SEATS:
        raise ValueError(f"Online rooms seat 2 to 4 players, not {seats}.")
    layout = None if args.layout == "any" else Layout(args.layout)
    sizes = mapgen.sizes_for(seats, layout)
    if args.size not in sizes:
        raise ValueError(f"Size {args.size} cannot seat {seats}: {', '.join(sizes) or 'none'}.")
    width, height = mapgen.dimensions(args.size, seats)
    if width > ONLINE_SIZE[0] or height > ONLINE_SIZE[1]:
        raise ValueError(f"Size {args.size} ({width}x{height}) is larger than online rooms hold "
                         f"({ONLINE_SIZE[0]}x{ONLINE_SIZE[1]}): {', '.join(sizes) or 'none'}.")
    if layout is not None and layout not in mapgen.layouts_for(width, height, seats):
        raise ValueError(f"Layout {args.layout} cannot seat {seats} on {args.size}.")
    seed = args.seed if args.seed is not None else fair_map(mapgen.fresh_seed(), width, height, seats, theme=MapTheme(args.theme),
                                                            races=[Race(args.race)] + [None] * (seats - 1),
                                                            layout=layout, magic=args.magic, wilds=args.wilds)[0]
    return {"seed": seed, "width": width, "height": height, "theme": args.theme,
            "players": seats, "races": [args.race] + [None] * (seats - 1),
            "layout": args.layout, "magic": args.magic, "wilds": args.wilds}


def selftest(png: str) -> None:
    """Prove a build works without a screen: fonts, art, sound files, and a match started from the title on a window the OS resized."""
    import os

    from saga2d import Game, fonts
    from warband.audio import sound
    from warband.ui.scene import DEFAULT_SETTINGS
    from warband.ui.style import build_theme
    from warband.ui.title import TitleScene

    os.environ["SAGA2D_SILENT"] = "1"
    game = Game("Warband", resolution=(1280, 800), visible=False, theme=build_theme(), icon=ICON)
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
