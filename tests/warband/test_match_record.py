"""A match's recording, rating and save lifecycle through real durable storage."""

from tests.warband.battlefield import field
from warband.records.profile import Profile
from warband.records.replay import Playback, ReplayStore
from warband.sim.rules import Difficulty
from warband.ui.match_record import MatchRecord


def test_a_finished_record_keeps_a_faithful_replay_and_one_rated_result(tmp_path) -> None:
    """Starting adopts the local name before recording; finishing ties replay and result to one run."""
    Profile.load(tmp_path).rename("Commander")
    world = field()
    record = MatchRecord(seed=3, difficulty=Difficulty.MEDIUM, human=0)
    record.start(tmp_path, world)
    assert world.players[0].name == "Commander"
    world.resign(1)
    assert record.conclude(world, "victory") == ()
    assert record.rating_change is not None and record.rating_change.result.outcome == "victory"
    profile = Profile.load(tmp_path)
    assert [row.run_id for row in profile.results] == [record.run_id]
    playback = Playback(ReplayStore(tmp_path).load(record.run_id))
    playback.run()
    assert playback.faithful


def test_saved_record_resumes_the_same_run_and_autosaves_at_the_next_interval(tmp_path) -> None:
    """Save metadata, continued replay and autosave cadence belong to one record across a reload."""
    from warband.ui.match_record import AUTOSAVE_EVERY, check_save, saved_replay, saved_run_id

    world = field()
    record = MatchRecord(seed=7, difficulty=Difficulty.HARD, human=0)
    record.start(tmp_path, world)
    world.time = AUTOSAVE_EVERY + 15
    state = record.save_state(world)
    restored = check_save(state)
    resumed = MatchRecord(seed=state["seed"], difficulty=Difficulty(state["difficulty"]), human=0,
                          run_id=saved_run_id(state), ranked=state["ranked"], replay=saved_replay(state))
    resumed.restore_clock(restored.time)
    resumed.start(tmp_path, restored)
    assert resumed.run_id == record.run_id
    assert resumed.replay.orders[-1][1] == "reload"
    assert resumed.autosave_at == 2 * AUTOSAVE_EVERY
    assert not resumed.autosave_due(restored.time)
    assert resumed.autosave_due(2 * AUTOSAVE_EVERY)
    assert not resumed.autosave_due(2 * AUTOSAVE_EVERY)


def test_a_score_can_be_kept_after_its_storage_failure_is_repaired(tmp_path) -> None:
    """A result reopened after a write failure reports the latest attempt and still counts the run once."""
    from warband.records.scores import HighScores

    world = field()
    record = MatchRecord(seed=3, difficulty=Difficulty.MEDIUM, human=0)
    record.start(tmp_path, world)
    world.resign(1)
    blocked = tmp_path / "high_scores"
    blocked.write_text("in the way")
    assert record.keep_score(world) is None and record.score_error
    blocked.unlink()
    assert record.keep_score(world) == 1 and not record.score_error
    assert [entry.run_id for entry in HighScores(tmp_path).load()] == [record.run_id]
