"""Play Warband's music director through the real pyglet backend and report what it did.

    uv run python tools/verify_warband_music.py DIR

Uses pyglet's silent audio driver in a hidden window, so nothing is heard and no
display is needed beyond being awake.  The bank composes the catalogue in the
background exactly as in play (into DIR/bank, so the player's cache is untouched);
the title waits for its piece, a match starts its race's opener, a scripted fight
switches to the battle piece, calm returns to peace, and the match's end plays the
ending once.  Every change is checked on the native players: two during a crossfade,
one after.  A JSON report of the timeline goes to DIR/music-native.json.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SAGA2D_SILENT"] = "1"
os.environ["SAGA2D_HEADLESS"] = "1"

from saga2d import Game, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband import sound  # noqa: E402
from warband.model import World  # noqa: E402
from warband.rules import BuildingType, Race, Terrain, UnitType  # noqa: E402
from warband.scene import GameScene  # noqa: E402
from warband.style import build_theme  # noqa: E402
from warband.title import TitleScene  # noqa: E402


def main(out: Path) -> None:
    import pyglet

    out.mkdir(parents=True, exist_ok=True)
    game = Game("Warband music verification", backend="pyglet", visible=False, resolution=(1280, 800), theme=build_theme(), save_dir=out / "saves")
    backend = game.backend
    timeline: list[dict] = []
    started = time.monotonic()

    def note(event: str, **facts) -> None:
        timeline.append({"t": round(time.monotonic() - started, 2), "event": event, "playing": bank.music_playing,
                         "players": len(backend._players), **facts})
        print(f"{timeline[-1]['t']:7.2f}s  {event:32s} playing={bank.music_playing} players={len(backend._players)} {facts or ''}")

    def until(condition, seconds: float, what: str) -> None:
        """Tick at the native 30 FPS pace (a 1/60 s step each) until *condition* holds."""
        deadline, ticks = time.monotonic() + seconds, 0
        while time.monotonic() < deadline:
            tick(game)
            ticks += 1
            if condition():
                return
        raise AssertionError(f"Timed out after {ticks} ticks waiting for {what}: playing={bank.music_playing} players={len(backend._players)}")

    try:
        fonts.load(game)
        assert "silent" in type(pyglet.media.get_audio_driver()).__module__, "verification must use the silent driver"
        bank = sound.SoundBank(game, data_dir=out / "bank", compose=True)
        sound.sound_hook, sound.volume_hook, sound.music_hook = bank.play, bank.set_volume, bank.music
        game.every(0.25, bank.poll)
        game.push(TitleScene(settings={"tutorial": False, "music": 0.6, "sfx": 0.0}))
        note("title shown", ready=sorted(bank.ready))
        until(lambda: bank.music_playing == "vigil", 60, "the title piece to compose and start")
        note("title piece started", ready=sorted(bank.ready))

        world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=(Race.DWARF, Race.ORC))
        world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
        world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
        scene = GameScene(world, seed=1, settings={"tutorial": False, "music": 0.6, "sfx": 0.0})
        scene.brains = []
        game.clear_and_push(scene)
        match_started = time.monotonic()
        until(lambda: bank.music_playing == "deepforge", 90, "the dwarves' opener")
        note("match opener started", players=len(backend._players), waited=round(time.monotonic() - match_started, 2))
        assert time.monotonic() - match_started < 12, "the match's own suite should jump the composer's queue"
        assert len(backend._players) == 2, "the title should still be fading under the opener"
        until(lambda: len(backend._players) == 1, 20, "the title to finish fading")
        note("title faded out")

        for x in (10.5, 11.5, 12.5):
            world.spawn_unit(0, UnitType.FOOTMAN, (x, 10.5))
        victim = world.spawn_unit(1, UnitType.KNIGHT, (11.5, 11.5))
        world.hold([victim.id])
        world.attack([u.id for u in world.player_units(0)], victim.id)
        until(lambda: bank.music_playing == "ironwall", 60, "the battle piece (it may still be composing)")
        note("battle piece started", mood=scene.mood, blows=len(scene._fights))
        until(lambda: len(backend._players) == 1, 20, "the opener to finish fading")
        world.move([u.id for u in world.player_units(0)], (3.5, 3.5))
        until(lambda: bank.music_playing == "deepforge", 40, "peace to return")
        note("peace resumed", mood=scene.mood)
        until(lambda: len(backend._players) == 1, 20, "the battle piece to finish fading")

        for fallen in (*world.player_units(1), *world.player_buildings(1)):
            fallen.hp = 0  # the rival falls; the next step buries it and declares the winner
        until(lambda: bank.music_playing == "victory", 30, "the victory fanfare")
        note("ending started", game_over=scene._game_over, top=type(game.scene).__name__)
        until(lambda: bank.music_playing is None, 40, "the fanfare to play out")
        note("ending finished")
        assert not backend._players, f"players left after the ending: {list(backend._players)}"
        bank.wait()
        note("catalogue composed", ready=len(bank.ready))
        assert len(bank.ready) == len(sound.MUSIC)
    finally:
        sound.sound_hook = sound.volume_hook = sound.music_hook = None
        game.close()
    (out / "music-native.json").write_text(json.dumps(timeline, indent=1))
    print(f"ok: report in {out / 'music-native.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dir", type=Path)
    main(parser.parse_args().dir)
