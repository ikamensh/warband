"""Drive Warband through the real pyglet backend and save frames to look at.

    uv run python tools/verify.py /tmp/warband_shots

Real window events are dispatched (mouse presses, drags, key presses and a
wheel scroll), so this exercises the pyglet event handlers and the GPU
rendering path that the mock tests cannot.  Each step asserts on the model
before saving its PNG.  The display must be awake (``caffeinate -u -t 3``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyglet.window import key, mouse  # noqa: E402

from saga2d import Game, fonts  # noqa: E402
from warband.sim.model import Build, Harvest, tile_center  # noqa: E402
from warband.sim.rules import BuildingType, UnitType  # noqa: E402
from warband.ui.scene import GameScene, PauseScene, new_game  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    game = Game("Warband verify", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme())
    backend = game.backend
    window = backend.window
    fonts.load(game)
    scene = new_game(seed=3)
    game.push(scene)

    def frames(n: int) -> None:
        for _ in range(n):
            game.tick(1 / 60)

    def shot(name: str) -> None:
        frames(2)
        backend.capture_frame().save(out / f"{name}.png")
        print(f"  {name}.png")

    def physical(point) -> tuple[int, int]:
        sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
        s = backend.scale_factor
        return int(sx * s + backend.offset_x), int((800 - sy) * s + backend.offset_y)

    def press(symbol: int, mods: int = 0) -> None:
        window.dispatch_event("on_key_press", symbol, mods)
        window.dispatch_event("on_key_release", symbol, mods)
        frames(2)

    def click(point, button: int = mouse.LEFT, mods: int = 0) -> None:
        px, py = physical(point)
        window.dispatch_event("on_mouse_press", px, py, button, mods)
        window.dispatch_event("on_mouse_release", px, py, button, mods)
        frames(2)

    frames(3)
    world = scene.world
    hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
    peasants = [u for u in world.player_units(scene.human) if u.is_worker]
    shot("01_start")

    # Drag a box around the peasants with real mouse events.
    xs, ys = [p.x for p in peasants], [p.y for p in peasants]
    x0, y0 = physical((min(xs) - 1, min(ys) - 1))
    x1, y1 = physical((max(xs) + 1, max(ys) + 1))
    window.dispatch_event("on_mouse_press", x0, y0, mouse.LEFT, 0)
    window.dispatch_event("on_mouse_drag", x1, y1, x1 - x0, y1 - y0, mouse.LEFT, 0)
    frames(1)
    shot("02_drag_box")
    window.dispatch_event("on_mouse_release", x1, y1, mouse.LEFT, 0)
    frames(2)
    assert sorted(scene.selection) == sorted(p.id for p in peasants), scene.selection

    # Right-click the mine: the peasants go mining.
    mine = world.mines()[0]
    click(mine.center, mouse.RIGHT)
    assert all(isinstance(p.order, Harvest) for p in peasants), [p.order for p in peasants]
    frames(90)
    shot("03_mining")

    # Shift-click removes one peasant from the selection (mouse modifiers).
    click(peasants[0].pos, mouse.LEFT, key.MOD_SHIFT)
    assert peasants[0].id not in scene.selection and len(scene.selection) == 2, scene.selection

    # Build a farm with B, F and a click; the ghost shows while placing.
    click(peasants[1].pos)
    press(key.B)
    press(key.F)
    assert scene.placing is BuildingType.FARM
    site = (hall.x + 5, hall.y + 4)
    px, py = physical((site[0] + 1, site[1] + 1))
    window.dispatch_event("on_mouse_motion", px, py, 0, 0)
    frames(2)
    shot("04_build_ghost")
    click((site[0] + 1, site[1] + 1))
    assert isinstance(peasants[1].order, Build), peasants[1].order
    frames(400)  # the builder walks over from the mine first
    assert any(b.type is BuildingType.FARM for b in world.player_buildings(scene.human))
    shot("05_farm_site")

    # Train a peasant from the hall with P.
    click(hall.center)
    press(key.P)
    assert hall.queue == [UnitType.PEASANT]

    # Wheel zoom, control group, an enemy raid with the alert, and the pause menu.
    px, py = physical(hall.center)
    window.dispatch_event("on_mouse_scroll", px, py, 0, 2)
    frames(20)
    assert scene.camera.zoom > 1.0
    knight = world.spawn_unit(1, UnitType.KNIGHT, tile_center((hall.x + 5, hall.y - 2)))
    world.attack([knight.id], hall.id)
    frames(150)
    assert scene.last_alert is not None
    shot("06_raid")

    # Endless training: Shift with the recruit's letter, and a right-click on a portrait as autocast had it.
    barracks = world.place_building(scene.human, BuildingType.BARRACKS, (hall.x - 4, hall.y + 4))
    frames(2)
    click(barracks.center)
    assert scene.selection == [barracks.id], scene.selection
    press(key.F, key.MOD_SHIFT)
    archer = scene.card_buttons[1]
    x, y, w, h = archer.bounds
    s = backend.scale_factor
    ax, ay = int((x + w / 2) * s + backend.offset_x), int((800 - (y + h / 2)) * s + backend.offset_y)
    window.dispatch_event("on_mouse_press", ax, ay, mouse.RIGHT, 0)
    window.dispatch_event("on_mouse_release", ax, ay, mouse.RIGHT, 0)
    frames(30)
    assert barracks.auto[0] in (UnitType.FOOTMAN, UnitType.ARCHER) and set(barracks.auto) == {UnitType.FOOTMAN, UnitType.ARCHER}, barracks.auto
    shot("07_endless")

    # The planner's spot: B, F, and F again with nothing selected plans a farm by the hall.
    press(key.ESCAPE)
    press(key.B)
    press(key.F)
    press(key.F)
    assert any(p.type is BuildingType.FARM for p in world.player_plans(scene.human)), world.player_plans(scene.human)
    shot("08_planner_farm")
    press(key.ESCAPE)

    # The Grid scheme: keys by the card's place, D builds and Q is the farm.
    scene.settings["controls"] = "grid"
    scene.apply_settings()
    scene.select([world.spawn_unit(scene.human, UnitType.PEASANT, tile_center((hall.x + 4, hall.y + 5))).id])  # those at work are in the mine
    frames(2)
    press(key.D)
    press(key.Q)
    assert scene.catalogue == "build" and scene.placing is BuildingType.FARM, (scene.catalogue, scene.pending)
    shot("09_grid")
    press(key.ESCAPE)
    press(key.ESCAPE)
    press(key.ESCAPE)
    press(key.F10)
    assert isinstance(game.scene, PauseScene)
    shot("10_pause")
    press(key.ESCAPE)
    assert isinstance(game.scene, GameScene)
    game._teardown()
    backend.quit()
    print("verify: all steps passed")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/warband_shots"))
