"""Render every level's narrated field chart, plus live conversation and choice layouts.

    uv run python tools/verify_dialogue.py DIR [--size 1200x680] [--animation]

Uses native key events to advance actual briefings. The field conversation and
seam choice are presentation fixtures, not claims of playing to those events.
Progress and saves live in a temporary directory.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyglet.window import key  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from warband.story.campaign import Choice, Progress  # noqa: E402
from warband.story.catalog import CAMPAIGNS, UNDERTOW  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionScene, start_mission  # noqa: E402
from warband.story.undertow_dialogue import WEIGHT_SELLA_EXCHANGE  # noqa: E402
from warband.sim.rules import Difficulty  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402


def main(out: Path, size: tuple[int, int], *, animation: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-dialogue-") as temp:
        game = Game("Warband / Aether council", resolution=size, backend="pyglet", visible=False,
                    theme=build_theme(), save_dir=Path(temp) / "saves")
        fonts.load(game)
        recording = False
        frames = []

        def tick(seconds: float = 1.4) -> None:
            for _ in range(round(seconds * 10)):
                game.tick(.1)
                if recording:
                    frames.append(game.backend.capture_frame().resize((960, round(960 * size[1] / size[0]))))

        def press(symbol: int) -> None:
            game.backend.window.dispatch_event("on_key_press", symbol, 0)
            game.backend.window.dispatch_event("on_key_release", symbol, 0)
            tick()

        def shot(name: str) -> None:
            game.backend.capture_frame().save(out / f"{name}.png")
            print(out / f"{name}.png", flush=True)

        try:
            for campaign in CAMPAIGNS:
                for mission in campaign.missions:
                    start_mission(game, campaign, mission, Progress(campaign.id, Difficulty.MEDIUM), None)
                    recording = animation and mission.id == "undertow_caravan"
                    tick()
                    if mission.id == "undertow_mill":
                        shot("briefing-arrival")
                    press(key.SPACE)
                    shot(f"chart-{mission.id}")
                    if mission.id == "undertow_caravan":
                        press(key.SPACE)
                        press(key.SPACE)
                        shot("briefing-caravan-route")
                    recording = False
            if frames:
                frames[0].save(out / "briefing.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
            mission = UNDERTOW.mission("undertow_weight")
            start_mission(game, UNDERTOW, mission, Progress(UNDERTOW.id, Difficulty.MEDIUM), None)
            game.scene.skip()
            scene = game.scene
            assert isinstance(scene, MissionScene)
            game.push(scene.conversation(WEIGHT_SELLA_EXCHANGE))
            tick()
            shot("field-conversation")
            game.scene.skip()
            next(trigger for trigger in mission.triggers if trigger.id == "confession").do(scene.run)
            game.push(scene.conversation(scene.run.pending.pop()))
            while not isinstance(game.scene.current, Choice):
                press(key.SPACE)
            tick()
            shot("field-choice")
            press(key._3)
            assert scene.run.vars["seam_intent"] == "guard"
            assert isinstance(game.scene, DialogScene)
            shot("field-answer")
        finally:
            game.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--size", default="1200x680")
    parser.add_argument("--animation", action="store_true", help="also record the caravan's animated briefing")
    args = parser.parse_args()
    main(args.out, tuple(int(n) for n in args.size.split("x")), animation=args.animation)
