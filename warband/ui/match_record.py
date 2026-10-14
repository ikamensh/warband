"""The durable identity of one played match, independent of its displayed scene.

A record starts after the data directory is known, adopts the profile name
before recording, resumes a saved recording and closes replay/rating together.
Reloading preserves the run id so an improved or abandoned finish replaces the
same result. Persistence failures return notices for the scene to display.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from saga2d import SaveError
from warband.brains.ai import DIFFICULTY_ELO
from warband.records.profile import MatchResult, Profile, RatingChange, Standing, standing
from warband.records.replay import Replay, ReplayStore
from warband.records.scores import HighScores
from warband.sim.model import World
from warband.sim.rules import Difficulty
from warband.ui.view import check_memory

SAVE_VERSION = 2  # 2: the world records its layout
AUTOSAVE_EVERY = 120.0  # seconds of match time


class MatchRecord:
    """Run identity, replay and profile lifecycle; no input or rendering state."""

    def __init__(self, *, seed: int, difficulty: Difficulty, human: int, run_id: str | None = None,
                 ranked: bool = True, replay: Replay | None = None, autosave: bool = True) -> None:
        self.seed, self.difficulty, self.human = seed, difficulty, human
        self.run_id = run_id if run_id is not None else str(uuid4())
        self.ranked = ranked
        self.replay: Replay | None = None
        self._saved_replay = replay
        self.profile: Profile | None = None
        self.profile_error = ""
        self.rating_change: RatingChange | None = None
        self._data_dir: Path | None = None
        self._resignation: Standing | None = None
        self._autosave = autosave
        self.autosave_at = AUTOSAVE_EVERY if autosave else math.inf
        self.score_error = ""

    def start(self, data_dir: Path, world: World) -> None:
        """Begin or resume recording after the local identity has named the playing seat."""
        self._data_dir = data_dir
        if not self.ranked:
            return
        try:
            self.profile = Profile.load(data_dir)
        except SaveError as error:
            self.profile, self.profile_error = None, str(error)
        else:
            world.players[self.human].name = self.profile.name
        if self._saved_replay is None:
            self.replay = Replay.begin(world, seed=self.seed, difficulty=self.difficulty, human=self.human)
        else:
            self.replay = self._saved_replay
            self.replay.reloaded(world)
            self._saved_replay = None

    def leaving(self, world: World) -> Standing | None:
        """What leaving an undecided rated match costs; unrated and decided matches cost nothing."""
        if self.replay is None or self.profile is None or world.winner is not None or not world.players[self.human].alive:
            return None
        return standing(world, self.human)

    def resign(self, world: World, where: Standing) -> None:
        """Keep the position before concession so its rating uses the situation the player left."""
        self._resignation = where
        world.resign(self.human)

    def autosave_due(self, seconds: float) -> bool:
        """Consume one due interval, so a scene can save its own UI state with this record."""
        if seconds < self.autosave_at:
            return False
        self.autosave_at += AUTOSAVE_EVERY
        return True

    def restore_clock(self, seconds: float) -> None:
        """Resume at the next interval after the saved match, without an immediate catch-up save."""
        if self._autosave:
            self.autosave_at = (seconds // AUTOSAVE_EVERY + 1) * AUTOSAVE_EVERY

    def save_state(self, world: World) -> dict[str, Any]:
        """The durable match; the displayed scene adds only its own controls and remembered view."""
        return {"version": SAVE_VERSION, "seed": self.seed, "difficulty": self.difficulty.value, "world": world.to_dict(),
                "run_id": self.run_id, "ranked": self.ranked, "replay": self.replay.to_dict() if self.replay is not None else None}

    def keep_score(self, world: World) -> int | None:
        """Keep this run's best finish; the result screen supplies wording for rank or a storage failure."""
        self.score_error = ""
        if not self.ranked:
            return None
        assert self._data_dir is not None  # ranked records start before any finish is presented
        try:
            return HighScores(self._data_dir).record(world, player=self.human, seed=self.seed,
                                                    difficulty=self.difficulty, run_id=self.run_id)
        except SaveError as error:
            self.score_error = str(error)
            return None

    def conclude(self, world: World, outcome: str, where: Standing | None = None) -> tuple[str, ...]:
        """Keep replay and result under this run id; return any persistence failures for display."""
        if self.replay is None or self.profile is None:
            return ()
        assert self._data_dir is not None  # a started profile always has its directory
        if self._resignation is not None and outcome in ("victory", "defeat"):
            outcome, where = "resigned", self._resignation
        notices = []
        player = world.players[self.human]
        self.replay.finish(world, outcome)
        try:
            ReplayStore(self._data_dir).save(self.run_id, self.replay, {
                "name": player.name, "outcome": outcome, "race": player.race.value, "difficulty": self.difficulty.value,
                "players": world.seats, "size": f"{world.width}×{world.height}",
                "clock": f"{int(world.time // 60):02d}:{int(world.time % 60):02d}", "seed": self.seed})
            kept = True
        except SaveError as error:
            kept = False
            notices.append(f"Replay not saved: {error}")
        weight, reason = (where.weight, where.reason) if where is not None else (1.0, "")
        result = MatchResult(self.run_id, datetime.now(timezone.utc).isoformat(), outcome, weight, reason, self.difficulty.value,
                             DIFFICULTY_ELO[self.difficulty], world.seats - 1, player.race.value, world.width, world.height,
                             world.theme.value, world.layout.value, self.seed, int(world.time), kept)
        try:
            self.rating_change = self.profile.record(result)
        except SaveError as error:
            self.profile_error = str(error)
            notices.append(f"Result not recorded: {error}")
        return tuple(notices)


def check_save(state: dict[str, Any]) -> World:
    """The world in a save's ``state``, or a SaveError saying what is wrong with it."""
    if not isinstance(state, dict) or state.get("version") != SAVE_VERSION:
        raise SaveError(f"this save is from another version of Warband (format {state.get('version') if isinstance(state, dict) else '?'}, expected {SAVE_VERSION})")
    try:
        world = World.from_dict(state["world"])
        Difficulty(state["difficulty"])
        if "run_id" in state and (not isinstance(state["run_id"], str) or not state["run_id"].strip()):
            raise ValueError("run_id must be nonempty text")
        if "ranked" in state and type(state["ranked"]) is not bool:
            raise ValueError("ranked must be a boolean")
        saved_replay(state)
        if state.get("seen") is not None:  # saves from before the view remembered carry none
            check_memory(state["seen"], world)
        if any(type(value) is not int or value < 0 for player in world.players for value in player.stats.values()):
            raise ValueError("battle statistics must be nonnegative integers")
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise SaveError(f"the save file is damaged ({type(exc).__name__}: {exc})") from exc
    if not any(p.human for p in world.players):
        raise SaveError("the save has no human player")
    return world


def saved_run_id(state: dict[str, Any]) -> str:
    # Saves from before scoring carry no match ID; the same old save reopened still counts once.
    return state["run_id"] if "run_id" in state else str(uuid5(NAMESPACE_URL, "warband:" + json.dumps(state, sort_keys=True)))


def saved_replay(state: dict[str, Any]) -> Replay | None:
    """The recording a save carries, if it has one (saves from before replays record from where they are loaded)."""
    return Replay.from_dict(state["replay"]) if state.get("replay") is not None else None
