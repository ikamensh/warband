"""Render a campaign's real screens and authored battlefields for visual review.

    uv run python tools/verify_story.py DIR --campaign ID --size 1280x800

Captures the campaign menu, every opening briefing, each playable opening,
linked keeper focus through a real F3 event, and an unfogged model atlas. Saves use temporary player data. This is presentation
verification; the campaign playthrough tests establish that objectives are
attainable through actual orders. Keep the display awake with ``caffeinate -u``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from warband.story.campaign import Line  # noqa: E402
from warband.story.campaign_scene import CampaignScene  # noqa: E402
from warband.story.catalog import DEFAULT_CAMPAIGN, get_campaign  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionScene, build_world  # noqa: E402
from warband.sim.rules import Difficulty  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from tools.verify_campaign import mission_map  # noqa: E402


def main(out: Path, campaign_id: str, size: tuple[int, int], flags: dict) -> None:
    campaign = get_campaign(campaign_id)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-story-") as data:
        game = Game("Warband story verification", resolution=size, backend="pyglet", visible=False,
                    theme=build_theme(), save_dir=Path(data) / "saves")
        fonts.load(game)

        def tick(seconds: float = 0.1) -> None:
            for _ in range(round(seconds * 60)):
                game.tick(1 / 60)

        def shot(name: str) -> None:
            tick()
            path = out / f"{name}.png"
            game.backend.capture_frame().save(path)
            print(path)

        def press(symbol: int) -> None:
            game.backend.window.dispatch_event("on_key_press", symbol, 0)
            game.backend.window.dispatch_event("on_key_release", symbol, 0)

        try:
            game.push(CampaignScene(campaign=campaign))
            shot("00-campaign")
            for number, mission in enumerate(campaign.missions, 1):
                run = build_world(mission, flags=flags)
                prefix = f"{number:02}-{mission.id}"
                mission_map(run, out / f"{prefix}-atlas.png")
                game.clear_and_push(MissionScene(campaign, run, difficulty=Difficulty.MEDIUM))
                game.push(DialogScene(mission.briefing, campaign.speakers, run.vars))
                shot(f"{prefix}-briefing")
                dialogue = game.scene
                while isinstance(dialogue.current, Line):
                    speaker = campaign.speakers.get(dialogue.current.speaker)
                    if speaker is not None and speaker.portrait is not None:
                        shot(f"{prefix}-character")
                        break
                    dialogue.advance()
                while isinstance(game.scene, DialogScene):
                    scene = game.scene
                    scene.skip()
                    if scene.current is not None:
                        scene.choose(scene.current.options[0].value)
                tick(3.2)
                shot(f"{prefix}-opening")
                if any(run.unit(name.lower()) is not None for name in campaign.speakers):
                    from pyglet.window import key

                    press(key.F3)
                    shot(f"{prefix}-keeper")
                    if number == len(campaign.missions):
                        press(key.F1)
                        shot(f"{prefix}-help")
        finally:
            game.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN.id)
    parser.add_argument("--size", default="1280x800", help="WIDTHxHEIGHT")
    parser.add_argument("--flags", default="{}", help="campaign flags as a JSON object")
    args = parser.parse_args()
    width, height = (int(n) for n in args.size.split("x"))
    main(args.out, args.campaign, (width, height), json.loads(args.flags))
