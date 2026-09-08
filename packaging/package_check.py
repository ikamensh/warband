"""Diagnostics executed inside the frozen application, without a source checkout."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def online_smoke(endpoint: str) -> dict:
    """Two real WebSocket clients move a server-owned unit and reclaim a seat."""
    if not endpoint:
        raise ValueError("The package smoke check requires an explicit --endpoint")
    from saga2d.online import OnlineClient
    from warband.model import World
    from warband.rules import BuildingType

    clients = []

    def wait(condition):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for client in clients:
                client.poll()
            if condition():
                return
            time.sleep(.02)
        raise AssertionError([(client.ready, client.closed, client.error) for client in clients])

    try:
        creator = OnlineClient("warband-v1", endpoint=endpoint, options={"seed": 3, "width": 40, "height": 32})
        clients.append(creator)
        wait(lambda: bool(creator.room) and creator.state is not None)
        assert creator.resume_token and not creator.ready
        guest = OnlineClient("warband-v1", endpoint=endpoint, room=creator.room)
        clients.append(guest)
        wait(lambda: creator.ready and guest.ready)
        assert (creator.player, guest.player) == (0, 1)
        world = World.from_dict(creator.state["world"])
        unit = world.player_units(0)[0]
        target = next((unit.x + dx, unit.y + dy) for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2))
                      if world.passable(int(unit.x + dx), int(unit.y + dy)))
        command = {"action": "move", "args": [[unit.id], list(target)]}
        guest.submit(command)
        wait(lambda: bool(guest.error))
        assert "own" in guest.error.lower(), guest.error
        guest.error = ""
        creator.submit(command)

        def moved(client):
            current = next(item for item in client.state["world"]["units"] if item["id"] == unit.id)
            return abs(current["x"] - unit.x) + abs(current["y"] - unit.y) > .1

        wait(lambda: moved(creator) and moved(guest))
        room, token = creator.room, creator.resume_token
        creator.close()
        wait(lambda: not guest.ready)
        resumed = OnlineClient("warband-v1", endpoint=endpoint, room=room, resume_token=token)
        clients.append(resumed)
        wait(lambda: resumed.ready and guest.ready)
        assert resumed.player == 0 and moved(resumed)
        # Exercise the settlement interface from inside the frozen client too.
        # No worker or producer selection is supplied by either peer.
        resumed.submit({"action": "order_unit", "args": [0, "footman"]})
        resumed.submit({"action": "order_upgrade", "args": [0, "blades_1"]})
        resumed.submit({"action": "set_assembly", "args": [0, list(target)]})

        def plans():
            return World.from_dict(resumed.state["world"]).player_plans(0)

        wait(lambda: {plan.kind for plan in plans()} == {"unit", "upgrade"})
        wait(lambda: World.from_dict(resumed.state["world"]).players[0].assembly == target)
        world = World.from_dict(resumed.state["world"])
        pos = next((x, y) for y in range(world.height) for x in range(world.width)
                   if world.can_plan_building(BuildingType.FARM, (x, y), 0) is None)
        resumed.submit({"action": "plan_building", "args": [0, "farm", pos]})
        wait(lambda: any(plan.kind == "building" and plan.worker is not None for plan in plans()))
        for plan in plans():
            resumed.submit({"action": "cancel_plan", "args": [0, plan.id]})
        wait(lambda: not plans())
        return {"create_join": True, "foreign_order_rejected": True, "authoritative_movement": True,
                "private_seat_rejoin": True, "global_production": True, "automatic_plan_builder": True,
                "assembly_point": True, "cancel_plans": True}
    finally:
        for client in clients:
            client.close()


def build_info() -> dict:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Package acceptance must run the frozen executable")
    info = json.loads((Path(sys._MEIPASS) / "release" / "build-info.json").read_text(encoding="utf-8"))
    with Path(sys.executable).open("rb") as stream:
        info["executable_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    info["executable"] = str(Path(sys.executable).resolve())
    return info


def smoke(endpoint: str) -> dict:
    from saga2d import fonts
    info = build_info()
    for filename in (*fonts.FILES.values(), "OFL.txt"):
        assert (fonts.FONT_DIR / filename).is_file(), filename
    return {"passed": True, "source_commit": info["source_commit"], "version": info["version"], "frozen": True,
            "executable": info["executable"], "executable_sha256": info["executable_sha256"],
            "bundled_fonts": True, "online": online_smoke(endpoint)}


def native_smoke(output: Path, endpoint: str) -> dict:
    """Use native clipboard/buttons to create and join a real online match in the package."""
    if not endpoint:
        raise ValueError("Native multiplayer acceptance requires an explicit --endpoint")
    os.environ["SAGA2D_SILENT"] = "1"
    os.environ["SAGA2D_HEADLESS"] = "1"
    os.environ["SAGA2D_SERVER_URL"] = endpoint
    from PIL import ImageStat
    from pyglet import gl
    from pyglet.window import key
    from saga2d import Game, MatchMenu, fonts
    from saga2d.multiplayer_ui import MatchLobby
    from saga2d.online import OnlineClient
    from warband import sound
    from warband.scene import DEFAULT_SETTINGS, SettlementPlansScene, new_game
    from warband.style import build_theme
    from warband.title import TitleScene
    from warband.multiplayer import NetworkGameScene, NetworkMenuScene

    info = build_info()
    images = []
    with tempfile.TemporaryDirectory(prefix="warband-native-") as profile:
        game = Game("Warband", resolution=(1280, 800), visible=False, save_dir=Path(profile) / "saves", theme=build_theme())
        creator = None
        clipboard = game.backend.get_clipboard_text()
        try:
            fonts.load(game)
            bank = sound.install(game)
            settings = game.settings(DEFAULT_SETTINGS)

            def frames(count=3):
                for _ in range(count):
                    started = time.monotonic()
                    game.tick(1 / 30)
                    if creator is not None:
                        creator.poll()
                    time.sleep(max(0, 1 / 30 - (time.monotonic() - started)))

            def wait(condition):
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    frames(1)
                    if condition():
                        return
                raise AssertionError(f"Native online flow stopped at {type(game.scene).__name__}")

            def press(symbol, modifiers=0):
                game.backend.window.dispatch_event("on_key_press", symbol, modifiers)
                game.backend.window.dispatch_event("on_key_release", symbol, modifiers)
                frames()

            def click(text):
                from pyglet.window import mouse
                button = next(b for b in game.scene.ui.walk() if getattr(b, "text", "") == text)
                x, y, w, h = button.bounds
                px = int((x + w / 2) * game.backend.scale_factor + game.backend.offset_x)
                py = int((game.height - y - h / 2) * game.backend.scale_factor + game.backend.offset_y)
                game.backend.window.dispatch_event("on_mouse_motion", px, py, 0, 0)
                game.backend.window.dispatch_event("on_mouse_press", px, py, mouse.LEFT, 0)
                game.backend.window.dispatch_event("on_mouse_release", px, py, mouse.LEFT, 0)
                frames()

            def capture(suffix):
                frames()
                image = game.backend.capture_frame()
                assert sum(ImageStat.Stat(image.convert("RGB")).stddev) > 10, "The native frame is blank"
                path = output.with_name(output.stem + suffix + output.suffix)
                image.save(path)
                images.append(path.name)

            game.push(TitleScene(settings=settings))
            capture("-title")
            press(key.M)
            assert isinstance(game.scene, MatchMenu)
            capture("-multiplayer")
            click("Create room")
            wait(lambda: isinstance(game.scene, MatchLobby) and game.scene.session.state is not None)
            session = game.scene.session
            room, token = session.room, session.resume_token
            click("Copy room code")
            assert game.backend.get_clipboard_text() == room
            capture("-room-code")
            click("Cancel")
            creator = OnlineClient("warband-v1", endpoint=endpoint, room=room, resume_token=token)
            wait(lambda: creator.state is not None)
            click("Paste code")
            assert game.scene.fields[2] == room.upper()
            # Exercise the native platform shortcut as well as the visible button.
            press(key.V, key.MOD_COMMAND if sys.platform == "darwin" else key.MOD_CTRL)
            assert game.scene.fields[2] == room.upper()
            capture("-paste-code")
            press(key.ENTER)
            wait(lambda: isinstance(game.scene, NetworkGameScene) and game.scene.session.ready)
            live = game.scene
            wait(lambda: live.world.time >= 2)
            capture("-online-match")
            assert live.selection == []
            click("Train")
            capture("-settlement-train")
            click("Footman")
            wait(lambda: any(plan.kind == "unit" for plan in live.world.player_plans(live.human)))
            camera_before = (*live.camera.offset, live.camera.zoom)
            click(f"Plans ({live._plan_count()})")
            assert isinstance(game.scene, SettlementPlansScene)
            capture("-settlement-plans")
            assert (*live.camera.offset, live.camera.zoom) == camera_before
            click("Cancel")
            wait(lambda: not live.world.player_plans(live.human))
            click("Back")
            press(key.F10)
            assert isinstance(game.scene, NetworkMenuScene)
            before = live.world.time
            wait(lambda: live.world.time > before)
            capture("-match-menu")
            click("Leave match")
            assert isinstance(game.scene, TitleScene)
            game.clear_and_push(new_game(3, width=40, height=32, settings=settings))
            capture("")
            assert game.scene.world.units and game.scene.world.buildings
            return {"passed": True, "source_commit": info["source_commit"], "version": info["version"],
                    "executable": info["executable"], "executable_sha256": info["executable_sha256"],
                    "renderer": gl.gl_info.get_renderer(), "opengl_version": gl.gl_info.get_version_string(), "vendor": gl.gl_info.get_vendor(),
                    "backend": "pyglet", "native_multiplayer_input": True, "native_clipboard_join": True,
                    "live_match_menu": True, "native_settlement_planning": True,
                    "sound_catalogue": len(bank.names), "images": images}
        finally:
            game.backend.set_clipboard_text(clipboard)
            game.close()
            if creator is not None:
                creator.close()
