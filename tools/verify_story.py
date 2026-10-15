"""Render a campaign's real screens and authored battlefields for visual review.

    uv run python tools/verify_story.py DIR --campaign ID --size 1280x800

Captures the campaign menu, every opening briefing, each playable opening,
linked keeper focus through a real F3 event, choices, the journal, minimap hover,
and the Undertow finale's commitment/result/epilogue. The later presentation
fixtures queue the actual authored choices; the finale uses public World orders.
Saves use temporary player data. This is presentation
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
from warband.story.campaign import Choice, Line, Progress, ProgressStore  # noqa: E402
from warband.story.campaign_scene import CampaignScene  # noqa: E402
from warband.story.catalog import DEFAULT_CAMPAIGN, get_campaign  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionScene, build_world, start_mission  # noqa: E402
from warband.sim.rules import Difficulty, UnitType  # noqa: E402
from warband.art.textures import TILE  # noqa: E402
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

        def dismiss() -> None:
            while isinstance(game.scene, DialogScene):
                scene = game.scene
                scene.skip()
                if isinstance(scene.current, Choice):
                    scene.choose(scene.current.options[0].value)

        def paused_mission(run) -> MissionScene:
            scene = MissionScene(campaign, run, difficulty=Difficulty.MEDIUM)
            scene.paused = True
            game.clear_and_push(scene)
            tick()
            dismiss()
            tick(3.2)
            return scene

        try:
            game.push(CampaignScene(campaign=campaign))
            shot("00-campaign")
            for number, mission in enumerate(campaign.missions, 1):
                run = build_world(mission, flags=flags)
                prefix = f"{number:02}-{mission.id}"
                mission_map(run, out / f"{prefix}-atlas.png")
                start_mission(game, campaign, mission, Progress(campaign.id, Difficulty.MEDIUM, flags=flags), None)
                run = game.scenes[-2].run
                shot(f"{prefix}-briefing")
                dialogue = game.scene
                while isinstance(dialogue.current, Line):
                    speaker = campaign.speakers.get(dialogue.current.speaker)
                    if speaker is not None and speaker.portrait is not None:
                        shot(f"{prefix}-character")
                        break
                    dialogue.advance()
                dismiss()
                tick(3.2)
                shot(f"{prefix}-opening")
                if any(run.unit(name.lower()) is not None for name in campaign.speakers):
                    from pyglet.window import key

                    press(key.F3)
                    shot(f"{prefix}-keeper")
                    if number == len(campaign.missions):
                        tick(10)  # the consequence notice must give the objectives back to the selected keeper
                        shot(f"{prefix}-keeper-objectives")
                        assert game.scene.objectives_body.visible, "keeper focus must keep the mission objectives readable"
                        press(key.F1)
                        shot(f"{prefix}-help")
            if campaign.id == "undertow":
                from pyglet.window import key
                from tools.play_undertow import solve_maw

                for mission_id, trigger_id in (("undertow_weight", "confession"),):
                    mission = campaign.mission(mission_id)
                    run = build_world(mission, flags=flags)
                    paused_mission(run)
                    # A presentation fixture queues the authored phase, without claiming to play to it.
                    next(trigger for trigger in mission.triggers if trigger.id == trigger_id).do(run)
                    game.push(DialogScene(run.pending.pop(), campaign.speakers, run.vars, record=True))
                    while not isinstance(game.scene.current, Choice):
                        game.scene.advance()
                    shot(f"phase-{mission_id}-choice")
                    press(key._3)
                    dismiss()
                    press(key.J)
                    press(key.LEFT)  # the selected answer, before the following instruction
                    shot(f"phase-{mission_id}-journal")

                mission = campaign.mission("undertow_maw")
                run = build_world(mission, flags=flags)
                keystone = run.world.building_at(tuple(run.get("keystone_pos")))
                run.world.repair([unit.id for unit in run.units(0, UnitType.PEASANT)[:1]], keystone.id)
                for _ in range(1200):
                    run.world.step()
                    run.tick()
                    if run.get("ending_path"):
                        break
                assert run.get("ending_path") == "sealed", "the public repair order must commit RESEAL"
                scene = paused_mission(run)
                tick(10)  # let the muster and commitment notices finish so the chosen objective stays visible
                shot("phase-maw-committed")
                point = run.vars["landmarks"]["keystone"]["point"]
                x, y = scene.minimap.to_screen(*(value * TILE for value in point))
                backend = game.backend
                px = backend.offset_x + x * backend.scale_factor
                py = backend.offset_y + (game.height - y) * backend.scale_factor
                backend.window.dispatch_event("on_mouse_motion", round(px), round(py), 0, 0)
                shot("phase-maw-minimap-hover")
                press(key.J)
                shot("phase-maw-journal")

                # Seed only earlier completion for this presentation journey; the Maw itself wins through orders.
                progress = Progress(campaign.id, Difficulty.MEDIUM, completed=[m.id for m in campaign.missions[:-1]], flags=dict(flags))
                ProgressStore(game.data_dir, campaign.id).save(progress)
                run = build_world(mission, flags=progress.flags)
                solve_maw(run, ending="sealed")
                run.pending.clear()
                run.notes.clear()
                game.clear_and_push(MissionScene(campaign, run, difficulty=Difficulty.MEDIUM))
                tick()
                shot("phase-maw-result")
                press(key.ENTER)
                shot("phase-maw-debrief")
                game.scene.skip()
                shot("phase-maw-epilogue")
                game.scene.skip()
                shot("phase-campaign-complete")
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
