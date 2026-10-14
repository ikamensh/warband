"""Exclusive soldier duties and worker errands for a stronger brain.

A soldier has exactly one duty. Tactical target/route memories may outlive an
errand, but only this roster grants permission to issue that errand's orders.
The roster also ends escapes and drops dead units before decisions run.
"""
from __future__ import annotations

from enum import Enum

from warband.brains.ai import fighters
from warband.sim.model import Build, Move, Repair, Salvage, Unit, World


class Duty(Enum):
    MAIN = "main"
    GUARD = "guard"
    RAID = "raid"
    HUNT = "hunt"
    COMMANDER = "commander"
    CREEP = "creep"
    ESCAPE = "escape"
    HEAL = "heal"


class Assignment:
    def __init__(self, duty: Duty, sequence: int, until: float = 0.0) -> None:
        self.duty = duty
        self.sequence = sequence
        self.until = until


class Assignments:
    """Own exclusive tasking; membership queries return copies, never writable state."""

    def __init__(self) -> None:
        self._by_unit: dict[int, Assignment] = {}
        self._sequence = 0

    def sync(self, world: World, player: int) -> None:
        current = {u.id: u for u in world.player_units(player) if not u.is_worker and u.hp > 0}
        for uid in list(self._by_unit):
            if uid not in current:
                del self._by_unit[uid]
        for uid, unit in current.items():
            if uid not in self._by_unit:
                self.assign([uid], Duty.MAIN)
            assignment = self._by_unit[uid]
            if assignment.duty is Duty.ESCAPE and (world.time >= assignment.until
                    or not any(isinstance(order, Move) for order in unit.orders)):
                self.assign([uid], Duty.MAIN)

    def duty(self, uid: int) -> Duty | None:
        assignment = self._by_unit.get(uid)
        return assignment.duty if assignment is not None else None

    def members(self, duty: Duty) -> list[int]:
        return sorted((uid for uid, assignment in self._by_unit.items() if assignment.duty is duty),
                      key=lambda uid: self._by_unit[uid].sequence)

    def assign(self, uids: list[int], duty: Duty, *, until: float = 0.0) -> None:
        """Transfer each unit to *duty*, ending its previous duty atomically."""
        for uid in uids:
            current = self._by_unit.get(uid)
            if current is not None and current.duty is duty and current.until == until:
                continue
            self._by_unit[uid] = Assignment(duty, self._sequence, until)
            self._sequence += 1

    def release(self, duty: Duty) -> None:
        self.assign(self.members(duty), Duty.MAIN)

    def replace(self, duty: Duty, uids: list[int]) -> None:
        """Reconcile a decision's continuing errands, releasing those it ended."""
        continuing = set(uids)
        self.assign([uid for uid in self.members(duty) if uid not in continuing], Duty.MAIN)
        self.assign(uids, duty)

    def select(self, units: list[Unit], duties: tuple[Duty, ...]) -> list[Unit]:
        """Keep world order for force estimates and deterministic group commands."""
        # Newly spawned recruits have not met a think pass yet; their first duty is the main force.
        return [u for u in units if (self.duty(u.id) or Duty.MAIN) in duties]

    def fit_units(self, world: World, player: int) -> list[Unit]:
        """The fighting force, including detached soldiers but excluding patients."""
        return [u for u in fighters(world.player_units(player)) if self.duty(u.id) is not Duty.HEAL]


class WorkerErrands:
    """Worker reservations shared by economic and base-defense decisions.

    Workers are not members of the army. Their tasks keep the gatherer and
    building policy from reclaiming a scout or a peasant answering a rush.
    """
    def __init__(self) -> None:
        self.scouts: list[int] = []
        self.prospector: int | None = None
        self.rushers: list[int] = []
        self.hunters: dict[int, int] = {}
        self.strikers: set[int] = set()

    def answering(self, uid: int) -> bool:
        return uid in self.hunters or uid in self.strikers

    def free(self, world: World, player: int, *, miners: bool = False) -> list[Unit]:
        return [p for p in world.player_units(player) if p.is_worker and p.constructing is None
                and (miners or p.inside is None) and not isinstance(p.order, (Build, Repair, Salvage))
                and p.id not in self.scouts and p.id not in self.rushers
                and p.id != self.prospector and not self.answering(p.id)]
