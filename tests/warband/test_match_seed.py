"""New rooms receive new terrain while explicitly chosen map seeds stay reproducible."""

import time

from saga2d import Button, Game, MatchMenu
from saga2d.multiplayer_ui import MatchLobby
from tests.test_online_server import server_url
from warband.style import build_theme
from warband.title import TitleScene


def test_creating_another_online_room_generates_new_terrain(server_url, tmp_path, monkeypatch):
    """Two Create room clicks in the same menu produce distinct server-owned maps."""
    monkeypatch.setenv("SAGA2D_SERVER_URL", server_url)
    game = Game("room seeds", backend="mock", resolution=(1280, 800),
                theme=build_theme(), save_dir=tmp_path / "saves")
    states = []
    try:
        game.push(TitleScene())
        game.backend.inject_key("m")
        game.tick(1 / 30)
        for _ in range(2):
            assert isinstance(game.scene, MatchMenu)
            button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == "Create room")
            x, y, width, height = button.bounds
            game.backend.inject_click(x + width / 2, y + height / 2)
            game.tick(1 / 30)
            assert isinstance(game.scene, MatchLobby)
            deadline = time.monotonic() + 5
            while game.scene.session.state is None and time.monotonic() < deadline:
                game.tick(1 / 30)
                time.sleep(0.01)
            assert game.scene.session.state is not None, game.scene.session.error
            states.append(game.scene.session.state)
            game.backend.inject_key("escape")
            game.tick(1 / 30)
        assert states[0]["seed"] != states[1]["seed"]
        assert states[0]["world"]["terrain"] != states[1]["world"]["terrain"]
    finally:
        game.close()
