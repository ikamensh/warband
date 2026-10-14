"""Match execution owns clocks and decisions independently of the scene and rendering."""

from tests.warband.battlefield import field
from warband.sim.rules import SIM_DT, Difficulty
from warband.ui.match import LocalMatch


def test_local_match_keeps_fractional_time_and_freezes_on_pause_or_defeat() -> None:
    """Frame sizes change interpolation, never fixed-step rules; a defeated playing seat stops."""
    world = field()
    execution = LocalMatch(world, 7, difficulty=Difficulty.MEDIUM, player=0)
    execution.advance(SIM_DT / 2)
    assert world.tick == 0 and execution.fraction == 0.5
    execution.paused = True
    execution.advance(1.0)
    assert world.tick == 0 and execution.fraction == 0.5
    execution.paused = False
    execution.advance(SIM_DT / 2)
    assert world.tick == 1 and execution.fraction == 0
    world.players[0].alive = False
    execution.advance(SIM_DT)
    assert world.tick == 1 and execution.fraction == 1


def test_local_decisions_match_direct_steps_and_do_not_depend_on_display_hooks() -> None:
    """The display can inspect each pre-step world without moving the computer players' random stream."""
    import random

    from warband.brains.ai import make_brain
    from warband.sim import mapgen

    world = mapgen.generate(3)
    reference = world.from_dict(world.to_dict())
    execution = LocalMatch(world, 3, difficulty=Difficulty.MEDIUM, player=0)
    brains = [make_brain(p.id, Difficulty.MEDIUM, 3) for p in reference.players[:reference.seats] if not p.human]
    rng = random.Random(3)
    seen = []
    for _ in range(8):
        execution.advance(0.1, before_step=lambda current: seen.append(current.tick))
        for _ in range(2):
            for brain in brains:
                brain.think(reference, rng)
            reference.step()
    assert seen == list(range(16))
    assert execution.world.to_dict() == reference.to_dict()


def test_observer_keeps_stepping_after_a_seat_falls_and_caps_frame_work() -> None:
    """An inspected seat's loss is presentation context; only the match's winner stops an observer."""
    world = field(3)
    execution = LocalMatch(world, 7, difficulty=Difficulty.MEDIUM, player=None)
    world.players[0].alive = False
    execution.speed = 3
    execution.advance(1.0)
    assert world.tick == 6 and execution.fraction == 0
    assert abs(execution.behind - (3.0 - 6 * SIM_DT)) < 1e-12
    world.winner = 1
    execution.advance(0.1)
    assert world.tick == 6 and execution.fraction == 1


def test_snapshot_match_never_advances_the_server_world() -> None:
    """A room's world stays authoritative when local frames arrive, including under menus."""
    from warband.ui.match import RemoteMatch

    world = field()
    execution = RemoteMatch(world)
    original = world.to_dict()
    execution.advance(1.0)
    execution.speed = 16
    execution.advance(1.0)
    assert world.to_dict() == original


def test_replay_clock_preserves_reloads_and_skips_to_the_recorded_state() -> None:
    """Pacing and reloads are execution's concern; the final full world still matches the recording."""
    from warband.records.replay import Replay
    from warband.sim.rules import UnitType
    from warband.ui.match import ReplayMatch

    world = field()
    walker = world.spawn_unit(0, UnitType.PEASANT, (8.5, 8.5))
    replay = Replay.begin(world, seed=3, difficulty=Difficulty.MEDIUM, human=0)
    world.move([walker.id], (15.5, 8.5))
    for _ in range(3):
        world.step()
    world = world.from_dict(world.to_dict())
    replay.reloaded(world)
    for _ in range(3):
        world.step()
    replay.finish(world, "left")
    execution = ReplayMatch(replay)
    before = execution.world
    execution.change_speed(2)
    assert execution.speed == 4
    execution.paused = True
    execution.advance(0.1)
    assert execution.world.tick == 0
    execution.skip_to_end()
    execution.advance(0.1)
    assert execution.done and execution.playback.faithful and not execution.skipping
    assert execution.world is not before
    assert execution.world.to_dict() == world.to_dict()
