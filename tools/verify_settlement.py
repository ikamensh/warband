"""Exercise settlement planning with real native mouse events and inspectable frames.

    SAGA2D_SILENT=1 uv run python tools/verify_warband_settlement.py /tmp/warband-settlement

The fixture starts with empty coffers, then grants resources to demonstrate that
waiting plans become real construction and production. Rendering is capped at
30 FPS; this is a UI integration check, not a simulation benchmark.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyglet.window import mouse  # noqa: E402

from saga2d import Button, Game, Label, Row, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband.rules import BUILDINGS, BuildingType, UnitType, Upgrade  # noqa: E402
from warband.scene import SettlementPlansScene, new_game  # noqa: E402
from warband.style import build_theme  # noqa: E402
from warband.textures import TILE  # noqa: E402


def verify(out: Path, save_dir: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    game = Game("Warband settlement verification", resolution=(1280, 800),
                backend="pyglet", visible=False, theme=build_theme(), save_dir=save_dir)
    backend = game.backend
    window = backend.window
    fonts.load(game)
    scene = new_game(seed=3)
    scene.brains = []
    scene.paused = True
    world, player = scene.world, scene.player
    player.gold = player.lumber = 0
    game.push(scene)
    captures = []

    def frames(count: int, dt: float = 1 / 30) -> None:
        for _ in range(count):
            tick(game, dt)

    def shot(name: str) -> None:
        frames(2)
        filename = f"{name}.png"
        backend.capture_frame().save(out / filename)
        captures.append(filename)
        print(filename, flush=True)

    def physical(x: float, y: float) -> tuple[int, int]:
        scale = backend.scale_factor
        return int(x * scale + backend.offset_x), int((game.height - y) * scale + backend.offset_y)

    def click_screen(x: float, y: float) -> None:
        px, py = physical(x, y)
        window.dispatch_event("on_mouse_motion", px, py, 0, 0)
        window.dispatch_event("on_mouse_press", px, py, mouse.LEFT, 0)
        window.dispatch_event("on_mouse_release", px, py, mouse.LEFT, 0)
        frames(2)

    def click_button(button: Button) -> None:
        assert button.enabled, button.text
        x, y, width, height = button.bounds
        click_screen(x + width / 2, y + height / 2)

    def click(text: str) -> None:
        button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == text)
        click_button(button)

    def screen_point(point) -> tuple[float, float]:
        return scene.camera.world_to_screen(point[0] * TILE, point[1] * TILE)

    def cancel_named(name: str) -> None:
        row = next(r for r in game.scene.ui.walk() if isinstance(r, Row)
                   and any(isinstance(label, Label) and label.text == name for label in r.walk()))
        click_button(next(b for b in row.walk() if isinstance(b, Button) and b.text == "Cancel"))

    def plans_snapshot():
        return [{"id": p.id, "kind": p.kind, "type": p.type.value, "status": p.status,
                 "position": p.pos, "worker": p.worker, "building": p.building}
                for p in world.player_plans(scene.human)]

    try:
        frames(25, dt=0.2)  # let the opening banner leave while the simulation stays paused
        assert scene.selection == []
        shot("01-settlement-unselected")
        click("Build")
        shot("02-build-catalogue-costs")
        click("Farm")
        hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
        sites = sorted(((x, y) for y in range(world.height) for x in range(world.width)),
                       key=lambda p: math.dist(p, hall.center))
        for site in sites:
            if world.can_plan_building(BuildingType.FARM, site, scene.human) is not None:
                continue
            size = BUILDINGS[BuildingType.FARM].size
            point = site[0] + size / 2, site[1] + size / 2
            sx, sy = screen_point(point)
            if (20 < sx < game.width - 20 and 180 < sy < game.height - 180
                    and not any(c.visible and c.hit_test(sx, sy) for c in scene.ui.children)):
                break
        else:
            raise AssertionError("No explored legal blueprint site outside the HUD")
        px, py = physical(sx, sy)
        window.dispatch_event("on_mouse_motion", px, py, 0, 0)
        shot("03-blueprint-placement")
        click_screen(sx, sy)
        assert world.player_plans(scene.human)[0].pos == site
        click("Train")
        click("Footman")
        click("Peasant")
        click("Upgrade")
        shot("04-upgrade-catalogue-costs")
        click("Blades I")
        assert {p.type for p in world.player_plans(scene.human)} == {
            BuildingType.FARM, UnitType.FOOTMAN, UnitType.PEASANT, Upgrade.BLADES_1,
        }
        assert player.gold == player.lumber == 0 and scene.selection == []
        scene.paused = False
        frames(33)
        scene.paused = True
        click("Plans (4)")
        assert isinstance(game.scene, SettlementPlansScene)
        waiting = plans_snapshot()
        assert any(p["status"].startswith("Not enough gold") for p in waiting), waiting
        assert any(p["status"] == "Requires a Barracks" for p in waiting), waiting
        shot("05-waiting-plans")
        cancel_named("Sharpened Blades")
        assert len(world.player_plans(scene.human)) == 3
        shot("06-plan-cancelled")
        click("Back")
        click("Assembly")
        target = world.player_units(scene.human)[0].pos
        click_screen(*screen_point(target))
        assert player.assembly is not None and math.dist(player.assembly, target) < 0.1
        shot("07-blueprint-and-assembly")

        # Fixture resource grant: the UI has already submitted ordinary unpaid
        # orders; the real fixed-step model now assigns the worker and producer.
        player.gold = player.lumber = 5000
        scene.paused = False
        for _ in range(240):
            frames(1)
            foundations = [b for b in world.player_buildings(scene.human, BuildingType.FARM) if not b.done]
            linked = any(p.kind == "building" and p.building in {b.id for b in foundations}
                         for p in world.player_plans(scene.human))
            if linked and hall.queue == [UnitType.PEASANT]:
                break
        else:
            raise AssertionError(f"Construction and training did not start: {plans_snapshot()}, {hall.queue}")
        scene.paused = True
        assert scene.selection == []
        shot("08-automatic-construction")
        click(f"Plans ({scene._plan_count()})")
        shot("09-active-production")
        report = {"seed": 3, "resolution": [1280, 800], "fixture_resource_grant": {"gold": 5000, "lumber": 5000},
                  "selection": scene.selection, "farm_site": site, "assembly": player.assembly,
                  "waiting_plans": waiting, "active_plans": plans_snapshot(),
                  "town_hall_queue": [kind.value for kind in hall.queue],
                  "farm_foundation_ids": [b.id for b in foundations], "world_time": world.time,
                  "captures": captures, "result": "passed"}
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print("verify_warband_settlement: all steps passed", flush=True)
    finally:
        game.close()


def main(out: Path) -> None:
    with TemporaryDirectory(prefix="warband-settlement-profile-") as profile:
        verify(out, Path(profile))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband-settlement"))
