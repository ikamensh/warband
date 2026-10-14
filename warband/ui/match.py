"""Execution of a displayed match, independent of its input, HUD and drawing.

Local matches own their decision stream and fixed-step clock. Watching changes
which seat's elimination stops that clock; it never changes the rules. Replays
execute their recorded orders, and remote matches only accept server snapshots.
The narrow rendering hook receives the world about to step, so interpolation
can retain positions even when a replay replaces its world after a reload.
"""

from __future__ import annotations

import random
import time
from contextlib import AbstractContextManager, nullcontext
from typing import Any, Callable, Protocol

from warband.brains.ai import make_brain
from warband.records.replay import Playback, Replay
from warband.sim.model import World
from warband.sim.rules import SIM_DT, Difficulty

MAX_STEPS_PER_FRAME = 6
BeforeStep = Callable[[World], None]
Phase = Callable[[str], AbstractContextManager[Any]]


class Controller(Protocol):
    """The existing local brains share one decision interface."""

    def think(self, world: World, rng: random.Random) -> None: ...


class MatchExecution:
    """The displayed world and its playback controls; concrete kinds supply advancement."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.paused = False
        self.speed = 1.0
        self.stopped = False
        self._acc = 0.0
        self.behind = 0.0  # match seconds dropped to keep a slow display responsive

    @property
    def done(self) -> bool:
        return self.stopped or self.world.winner is not None

    @property
    def fraction(self) -> float:
        """How far the display may interpolate between the latest two fixed steps."""
        return 1.0 if self.done else self._acc / SIM_DT

    def advance(self, dt: float, *, before_step: BeforeStep | None = None, phase: Phase = nullcontext) -> None:
        raise NotImplementedError


class LocalMatch(MatchExecution):
    """One decision stream and fixed-step clock for all local computer players.

    A playing seat stops on its own elimination. With ``player=None`` the
    observer keeps watching until a winner, even if the inspected seat fell.
    Optional brains let missions supply their own difficulties and tools take
    over a human seat without involving presentation.
    """

    def __init__(self, world: World, seed: int, *, difficulty: Difficulty, player: int | None,
                 brains: list[Controller] | None = None) -> None:
        super().__init__(world)
        self.player = player
        self.brains = ([make_brain(p.id, difficulty, seed) for p in world.players[:world.seats] if not p.human]
                       if brains is None else brains)
        self._rng = random.Random(seed)

    @property
    def done(self) -> bool:
        return super().done or (self.player is not None and not self.world.players[self.player].alive)

    def advance(self, dt: float, *, before_step: BeforeStep | None = None, phase: Phase = nullcontext) -> None:
        if self.paused or self.done:
            return
        self._acc += min(dt, 0.25) * self.speed
        self.behind += max(0.0, dt - 0.25) * self.speed
        steps = 0
        while self._acc >= SIM_DT and steps < MAX_STEPS_PER_FRAME:
            with phase("ai"):
                for brain in self.brains:
                    brain.think(self.world, self._rng)
            if before_step is not None:
                before_step(self.world)
            with phase("sim"):
                self.world.step()
            self._acc -= SIM_DT
            steps += 1
        if steps == MAX_STEPS_PER_FRAME:
            self.behind += self._acc
            self._acc = 0.0


class RemoteMatch(MatchExecution):
    """A snapshot world: the room owns time and decisions, including under menus."""

    def advance(self, dt: float, *, before_step: BeforeStep | None = None, phase: Phase = nullcontext) -> None:
        pass


class ReplayMatch(MatchExecution):
    """Recorded orders at the viewer's pace, including reloads and bounded skipping."""

    SPEEDS = (1, 2, 4, 8, 16)
    SKIP_BUDGET = 0.4  # seconds per display frame; the window keeps answering while skipping

    def __init__(self, replay: Replay) -> None:
        self.playback = Playback(replay)
        super().__init__(self.playback.world)
        self._speed_index = 0
        self.skipping = False

    @property
    def done(self) -> bool:
        return self.stopped or self.playback.done

    def change_speed(self, delta: int) -> None:
        self._speed_index = min(max(0, self._speed_index + delta), len(self.SPEEDS) - 1)
        self.speed = self.SPEEDS[self._speed_index]

    def skip_to_end(self) -> None:
        self.skipping = True
        self.paused = False

    def advance(self, dt: float, *, before_step: BeforeStep | None = None, phase: Phase = nullcontext) -> None:
        if self.paused or self.done:
            return
        if self.skipping:
            deadline = time.monotonic() + self.SKIP_BUDGET
            while not self.done and time.monotonic() < deadline:
                self._step(before_step, phase)
            self._acc = 0.0
            if self.done:
                self.skipping = False
            return
        self._acc += min(dt, 0.25) * self.speed
        steps = 0
        while self._acc >= SIM_DT and steps < MAX_STEPS_PER_FRAME and not self.done:
            self._step(before_step, phase)
            self._acc -= SIM_DT
            steps += 1
        if steps == MAX_STEPS_PER_FRAME:
            self._acc = 0.0

    def _step(self, before_step: BeforeStep | None, phase: Phase) -> None:
        if before_step is not None:
            before_step(self.world)
        with phase("sim"):
            self.playback.step()
        self.world = self.playback.world
