"""Alt-tabbing freezes an undecided local match and resumes it on return."""

from tests.warband.battlefield import SETTINGS, field
from warband.ui.multiplayer import NetworkGameScene
from warband.ui.scene import GameScene


def test_background_pauses_and_foreground_resumes(game) -> None:
    scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    assert not scene.paused
    before = scene.world.time
    game.tick(0.1)
    assert scene.world.time > before
    game.backend.inject_focus(False)
    game.tick(0.1)
    assert scene.paused
    frozen = scene.world.time
    for _ in range(5):
        game.tick(0.1)
    assert scene.world.time == frozen
    game.backend.inject_focus(True)
    game.tick(0.1)
    assert not scene.paused
    game.tick(0.1)
    assert scene.world.time > frozen


def test_manual_pause_survives_a_background_cycle(game) -> None:
    scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    scene.toggle_pause()
    assert scene.paused
    game.backend.inject_focus(False)
    game.tick(0.1)
    game.backend.inject_focus(True)
    game.tick(0.1)
    assert scene.paused, "a manual pause is the player's, the return must not undo it"


def test_decided_match_is_left_alone(game) -> None:
    scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    scene._game_over = True  # staged state, as the suite's rules allow
    game.backend.inject_focus(False)
    game.tick(0.1)
    assert not scene.paused


class _StubSession:
    online = False

    def __init__(self, world, seed: int) -> None:
        self.revision = 0
        self.state = {"world": world.to_dict(), "seed": seed, "events": []}
        self.player = 0
        self.ready = True
        self.room = ""
        self.error = ""

    def poll(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_network_match_keeps_playing_elsewhere(game) -> None:
    """Freezing snapshots locally while the authority advances would desync the seat."""
    world = field()
    scene = NetworkGameScene(_StubSession(world, 0), settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    game.backend.inject_focus(False)
    game.tick(0.1)
    assert not scene.paused
