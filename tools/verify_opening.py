"""Play The Undertow's opening through native input, save/resume and a real victory.

    uv run python tools/verify_opening.py DIR [--size 1200x680]

Mend and the first attack use Pyglet keyboard/mouse events. Thereafter the existing
public-order driver holds the vault; no world state is edited. Player data is temporary.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyglet.window import key, mouse  # noqa: E402
from saga2d import Game, fonts  # noqa: E402
from tools.play_undertow import fight, mend_wounded, train  # noqa: E402
from warband.sim.model import Attack  # noqa: E402
from warband.sim.rules import BuildingType, UnitType, Upgrade  # noqa: E402
from warband.story.campaign import ProgressStore  # noqa: E402
from warband.story.campaign_scene import CampaignScene  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionResultScene, MissionScene  # noqa: E402
from warband.story.new_campaign import CAMPAIGN  # noqa: E402
from warband.ui.scene import load_game  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from warband.ui.view import to_world  # noqa: E402


def main(out: Path, size: tuple[int, int]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-opening-") as data:
        game = Game("The Undertow opening", resolution=size, backend="pyglet", visible=False,
                    theme=build_theme(), save_dir=Path(data) / "saves")
        fonts.load(game)

        def tick(seconds: float = .1) -> None:
            for _ in range(round(seconds*10)):
                game.tick(.1)

        def press(symbol: int, modifiers: int = 0) -> None:
            game.backend.window.dispatch_event("on_key_press", symbol, modifiers)
            tick()
            game.backend.window.dispatch_event("on_key_release", symbol, modifiers)
            tick()

        def shot(name: str) -> None:
            game.backend.capture_frame().save(out / f"{name}.png")

        def click_unit(scene: MissionScene, unit, button: int) -> None:
            x, y = scene.camera.world_to_screen(*to_world(scene.view.body_point(unit)))
            backend = game.backend
            px = round(backend.offset_x + x*backend.scale_factor)
            py = round(backend.offset_y + (game.height-y)*backend.scale_factor)
            backend.window.dispatch_event("on_mouse_press", px, py, button, 0)
            backend.window.dispatch_event("on_mouse_release", px, py, button, 0)
            tick()

        try:
            game.push(CampaignScene(campaign=CAMPAIGN))
            tick()
            shot("01-campaign")
            press(key.ENTER)
            assert isinstance(game.scene, DialogScene)
            shot("02-briefing")
            for _ in CAMPAIGN.missions[0].briefing[:-1]:
                press(key.SPACE)
            shot("03-take-command")
            press(key.SPACE)
            scene = game.scene
            assert isinstance(scene, MissionScene) and len(scene.selection) == 7
            wounded = next(unit for unit in scene.run.soldiers(0) if unit.hp < unit.info.hp)
            press(key._1, key.MOD_ALT)
            assert scene.aiming is Upgrade.MEND
            click_unit(scene, wounded, mouse.LEFT)
            assert scene.world.cooldown_left(0, Upgrade.MEND) > 0
            first_order = scene.world.time
            assert first_order < 30
            tick(5)
            assert game.scene is scene, "the first wave must leave the player in command"
            wolf = next(unit for unit in scene.run.units(1) if scene.world.is_visible(0, unit.tile))
            click_unit(scene, wolf, mouse.RIGHT)
            assert any(unit.orders and isinstance(unit.orders[0], Attack) and unit.orders[0].target == wolf.id
                       for unit in scene.run.soldiers(0)), "the native right-click must issue an attack"
            shot("04-first-fight")

            game.save("opening_check", scene=scene)
            saved = game.save_manager.load("opening_check")["state"]
            fired = dict(scene.run.fired)
            scene = load_game(saved)
            game.clear_and_push(scene)
            tick()
            assert scene.run.fired == fired
            crisis_seen = False
            for _ in range(600):
                if isinstance(game.scene, MissionResultScene):
                    break
                if isinstance(game.scene, DialogScene):
                    if "wave_2" in scene.run.fired and not crisis_seen:
                        shot("05-vault-crisis")
                        crisis_seen = True
                    press(key.SPACE)
                    continue
                fight(scene.run, tuple(scene.run.get("mill_vault_center")))
                train(scene.run, BuildingType.BARRACKS, UnitType.FOOTMAN, 10)
                mend_wounded(scene.run)
                tick(1)
            assert isinstance(game.scene, MissionResultScene) and game.scene.won
            assert crisis_seen and scene.run.get("undertow_mill_vault")
            shot("06-victory")
            progress = ProgressStore(game.data_dir, CAMPAIGN.id).load()
            assert progress.completed == [scene.mission.id]
            report = {"first_order_seconds": first_order, "victory_seconds": scene.world.time,
                      "native_mend": True, "native_attack": True, "save_resume": True,
                      "vault_held": True, "progress_recorded": True, "size": list(size)}
            (out / "result.json").write_text(json.dumps(report, indent=2)+"\n")
            print(json.dumps(report))
        finally:
            game.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--size", default="1200x680")
    args = parser.parse_args()
    main(args.out, tuple(int(value) for value in args.size.split("x")))
