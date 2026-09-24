"""A played match leaves its frame times, and what the match was, in saga2d's frame telemetry (not the league's tallies).

Frame rates on large maps were not knowable from replays (they hold orders, not frames); telemetry
names the run, so a slow stretch can be found again in that run's replay at the tick it gives.
"""

from saga2d import Game
from saga2d.telemetry import read

from tests.warband.battlefield import SETTINGS, field
from warband.ui.scene import GameScene


def test_a_match_played_through_the_loop_records_its_map_run_and_phases(tmp_path) -> None:
    game = Game("warband", backend="mock", save_dir=tmp_path / "saves")
    game.telemetry.enabled = True
    game.telemetry.window = 0.04
    game.backend.inject_focus(True)
    world = field()
    world.players[1].human = False  # a computer player, so the AI's phase has a brain in it
    scene = GameScene(world, 0, ranked=False, settings=dict(SETTINGS))
    game.after(0.2, game.quit)
    game.run(scene)

    [session] = read(tmp_path / "telemetry")
    windows = [w for w in session["windows"] if w["scene"] == "GameScene"]
    assert windows
    last = windows[-1]["context"]
    assert last["run"] == scene.run_id
    assert last["map"] == f"{world.width}x{world.height}" and last["seats"] == world.seats
    assert last["tick"] == world.tick > 0 and last["units"] == len(world.units)
    phases = {name for w in windows for name in w.get("phases", {})}
    assert {"ai", "sim", "view"} <= phases
