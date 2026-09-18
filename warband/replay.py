"""Replays: the world a match began in and every order given since, which is the match itself.

The simulation is deterministic to the float bit (lockstep online play needs
that), so a recording holds no frames: :class:`Replay` keeps the start
:meth:`World.to_dict` snapshot, the order log :func:`warband.model.recorded`
fills (the human's orders and the computer players' alike, at the tick they
were given), and where the recording stopped.  :class:`Playback` gives the
same orders at the same ticks to a world restored from the snapshot; the
digest recorded at the end tells whether it arrived at the same match.
Recordings are kept as JSON under ``<data_dir>/replays`` by :class:`ReplayStore`.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saga2d import SaveError, SaveManager
from warband.model import RuleError, World
from warband.rules import BuildingType, Difficulty, UnitType, Upgrade

REPLAY_VERSION = 1
#: A log row that is not an order: the match continued from a save taken at that tick.
RELOAD = "reload"
#: The names :func:`warband.model.recorded` marks: the only calls a replay may make on the world.
ORDERS = frozenset(name for name, attr in vars(World).items() if getattr(attr, "is_order", False))
_POINT_FIELDS = ("target", "point", "pos")
_ENUM_FIELDS = {"building_type": BuildingType, "unit_type": UnitType, "upgrade": Upgrade}


def digest(world: World) -> str:
    """A hash of what the match is at this moment, exact to the float bit: units, buildings, purses and upgrades."""
    out = hashlib.sha256()
    out.update(f"t={world.time!r}|tick={world.tick}|winner={world.winner}".encode())
    for unit in sorted(world.units.values(), key=lambda u: u.id):
        order = type(unit.order).__name__ if unit.order is not None else "-"
        out.update(f"U{unit.id},{unit.player},{unit.type.value},{unit.x!r},{unit.y!r},{unit.hp!r},"
                   f"{unit.carrying},{unit.inside},{len(unit.orders)},{order};".encode())
    for b in sorted(world.buildings.values(), key=lambda b: b.id):
        out.update(f"B{b.id},{b.player},{b.type.value},{b.x},{b.y},{b.hp!r},{b.progress!r},{len(b.queue)},{b.research};".encode())
    for p in world.players:
        out.update(f"P{p.id},{p.gold},{p.lumber},{p.alive},{sorted(u.value for u in p.upgrades)};".encode())
    return out.hexdigest()


def apply_order(world: World, name: str, args: list[Any], kwargs: dict[str, Any]) -> None:
    """Give the logged order *name* to *world* as it was given: points as tuples, enums by value.

    A rule error is the same rule error the original order met, so it is not an error of the replay.
    """
    if name not in ORDERS:
        raise ValueError(f"{name!r} is not an order")
    method = getattr(World, name)
    bound = inspect.signature(method).bind(world, *args, **kwargs)
    for parameter, value in bound.arguments.items():
        if parameter in _POINT_FIELDS and isinstance(value, list):
            bound.arguments[parameter] = tuple(value)
        elif parameter in _ENUM_FIELDS:
            bound.arguments[parameter] = _ENUM_FIELDS[parameter](value)
    try:
        method(*bound.args, **bound.kwargs)
    except RuleError:
        pass


@dataclass
class Replay:
    """A recording: where it starts, every order since, and (once finished) where it ends."""

    start: dict[str, Any]
    seed: int
    difficulty: Difficulty
    human: int
    orders: list[list[Any]] = field(default_factory=list)
    end: dict[str, Any] | None = None  # {"tick", "digest", "outcome"} once the recording stopped

    @classmethod
    def begin(cls, world: World, *, seed: int, difficulty: Difficulty, human: int) -> Replay:
        """Start recording *world* from this moment on."""
        replay = cls(world.to_dict(), seed, difficulty, human)
        replay.attach(world)
        return replay

    def attach(self, world: World) -> None:
        """Log *world*'s orders from now on (a loaded save continues the recording)."""
        world.orders = self.orders

    def reloaded(self, world: World) -> None:
        """Note that the match went on from a save of this moment: playback restores its world the same way there."""
        self.orders.append([world.tick, RELOAD, [], {}])
        self.attach(world)

    def finish(self, world: World, outcome: str) -> None:
        """Stop recording: the end tick and the digest a faithful playback must reach."""
        world.orders = None
        self.end = {"tick": world.tick, "digest": digest(world), "outcome": outcome}

    @property
    def finished(self) -> bool:
        return self.end is not None

    @property
    def end_tick(self) -> int:
        """The tick playback stops at: the recorded end, or after the last order of an unfinished recording."""
        return self.end["tick"] if self.end is not None else (self.orders[-1][0] + 1 if self.orders else 0)

    def to_dict(self) -> dict[str, Any]:
        return {"version": REPLAY_VERSION, "start": self.start, "seed": self.seed, "difficulty": self.difficulty.value, "human": self.human,
                "orders": self.orders, "end": self.end}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Replay:
        """The replay a :meth:`to_dict` describes, or a ValueError naming what is wrong with it."""
        if not isinstance(data, dict) or data.get("version") != REPLAY_VERSION:
            raise ValueError(f"replay format {data.get('version') if isinstance(data, dict) else '?'}, expected {REPLAY_VERSION}")
        orders = data["orders"]
        if not isinstance(orders, list) or not all(isinstance(o, list) and len(o) == 4 and type(o[0]) is int and (o[1] in ORDERS or o[1] == RELOAD)
                                                    and isinstance(o[2], list) and isinstance(o[3], dict) for o in orders):
            raise ValueError("the order log must hold [tick, order, args, kwargs] rows")
        if any(a[0] > b[0] for a, b in zip(orders, orders[1:])):
            raise ValueError("the order log must be in tick order")
        end = data["end"]
        if end is not None and (not isinstance(end, dict) or type(end.get("tick")) is not int or not isinstance(end.get("digest"), str)
                                or not isinstance(end.get("outcome"), str)):
            raise ValueError("the end of a replay names its tick, digest and outcome")
        if type(data["seed"]) is not int or type(data["human"]) is not int:
            raise ValueError("seed and human must be integers")
        return cls(data["start"], data["seed"], Difficulty(data["difficulty"]), data["human"], orders, end)


class Playback:
    """A replay being watched: the world it restores and the orders still to give."""

    def __init__(self, replay: Replay) -> None:
        self.replay = replay
        self.world = World.from_dict(replay.start)
        if not 0 <= replay.human < len(self.world.players):
            raise ValueError("the replay's human seat is not on the map")
        self._next = 0

    @property
    def done(self) -> bool:
        return self.world.tick >= self.replay.end_tick and self._next >= len(self.replay.orders)

    @property
    def faithful(self) -> bool | None:
        """Once done: whether playback arrived at the recorded match (None while it plays or for an unfinished recording)."""
        if not self.done or self.replay.end is None:
            return None
        return digest(self.world) == self.replay.end["digest"]

    def step(self) -> None:
        """Give this tick's orders, then advance the world one step (unless the recording ends here)."""
        orders = self.replay.orders
        while self._next < len(orders) and orders[self._next][0] <= self.world.tick:
            _, name, args, kwargs = orders[self._next]
            if name == RELOAD:
                self.world = World.from_dict(self.world.to_dict())
            else:
                apply_order(self.world, name, args, kwargs)
            self._next += 1
        if self.world.tick < self.replay.end_tick:
            self.world.step()

    def run(self) -> World:
        """Play the whole recording through and return the world it ends in."""
        while not self.done:
            self.step()
        return self.world


class ReplayStore:
    """Recordings kept one file per match under ``<data_dir>/replays``, written atomically with a backup."""

    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "replays"
        self.saves = SaveManager(self.directory)

    @staticmethod
    def slot(run_id: str) -> str:
        return "r" + re.sub(r"[^0-9A-Za-z]", "", run_id)

    def path(self, run_id: str) -> Path:
        return self.directory / f"save_{self.slot(run_id)}.json"

    def save(self, run_id: str, replay: Replay, summary: dict[str, Any]) -> None:
        self.saves.save(self.slot(run_id), replay.to_dict(), "WarbandReplay", summary=summary)

    def load(self, run_id: str) -> Replay:
        """The recording of match *run_id*, or a SaveError saying why there is none."""
        saved = self.saves.load(self.slot(run_id))
        if saved is None:
            raise SaveError(f"No replay of match {run_id} at {self.path(run_id)}")
        try:
            return Replay.from_dict(saved["state"])
        except (KeyError, TypeError, ValueError) as error:
            raise SaveError(f"Cannot read the replay at {self.path(run_id)}: {error}") from error

    def exists(self, run_id: str) -> bool:
        return self.path(run_id).exists()

    def delete(self, run_id: str) -> None:
        self.saves.delete(self.slot(run_id))
