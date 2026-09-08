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
        return {"create_join": True, "foreign_order_rejected": True, "authoritative_movement": True, "private_seat_rejoin": True}
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


def native_smoke(output: Path) -> dict:
    """Exercise title, native multiplayer input and a rendered match in the package."""
    os.environ["SAGA2D_SILENT"] = "1"
    os.environ["SAGA2D_HEADLESS"] = "1"
    from PIL import ImageStat
    from pyglet import gl
    from pyglet.window import key
    from saga2d import Game, MatchMenu, fonts
    from warband import sound
    from warband.scene import DEFAULT_SETTINGS, new_game
    from warband.style import build_theme
    from warband.title import TitleScene

    info = build_info()
    images = []
    with tempfile.TemporaryDirectory(prefix="warband-native-") as profile:
        game = Game("Warband", resolution=(1280, 800), visible=False, save_dir=Path(profile) / "saves", theme=build_theme())
        try:
            fonts.load(game)
            bank = sound.install(game)
            settings = game.settings(DEFAULT_SETTINGS)

            def frames(count=3):
                for _ in range(count):
                    started = time.monotonic()
                    game.tick(1 / 30)
                    time.sleep(max(0, 1 / 30 - (time.monotonic() - started)))

            def capture(suffix):
                frames()
                image = game.backend.capture_frame()
                assert sum(ImageStat.Stat(image.convert("RGB")).stddev) > 10, "The native frame is blank"
                path = output.with_name(output.stem + suffix + output.suffix)
                image.save(path)
                images.append(path.name)

            game.push(TitleScene(settings=settings))
            capture("-title")
            game.backend.window.dispatch_event("on_key_press", key.M, 0)
            game.backend.window.dispatch_event("on_key_release", key.M, 0)
            frames()
            assert isinstance(game.scene, MatchMenu)
            capture("-multiplayer")
            game.clear_and_push(new_game(3, width=40, height=32, settings=settings))
            capture("")
            assert game.scene.world.units and game.scene.world.buildings
            return {"passed": True, "source_commit": info["source_commit"], "version": info["version"],
                    "executable": info["executable"], "executable_sha256": info["executable_sha256"],
                    "renderer": gl.gl_info.get_renderer(), "opengl_version": gl.gl_info.get_version_string(), "vendor": gl.gl_info.get_vendor(),
                    "backend": "pyglet", "native_multiplayer_input": True, "sound_catalogue": len(bank.names), "images": images}
        finally:
            game.close()
