"""The tutorial: a strip of objectives that ticks itself off from the world state.

Each objective is a sentence and a predicate on the scene; the strip shows
the first unfinished one plus what is done.  It is on for a player's first
match and can be hidden or switched off in the settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from warband.model import AttackMove, Harvest, Patrol
from warband.rules import BuildingType, UnitType

if TYPE_CHECKING:
    from warband.scene import GameScene


@dataclass(frozen=True)
class Objective:
    text: str
    done: Callable[[GameScene], bool]


def _units(scene: GameScene):
    return scene.world.player_units(scene.human)


def _buildings(scene: GameScene, building_type: BuildingType, *, done: bool | None = None):
    return scene.world.player_buildings(scene.human, building_type, done=done)


def _harvesting(scene: GameScene, gold: bool) -> bool:
    for u in _units(scene):
        if not u.is_worker:
            continue
        if gold and u.inside is not None:
            return True
        for order in u.orders:
            if isinstance(order, Harvest) and isinstance(order.target, int) == gold:
                return True
    return False


OBJECTIVES: tuple[Objective, ...] = (
    Objective("Select a peasant: click one, or drag a box around them", lambda s: any(isinstance(s.world.units.get(i), object) and s.world.units[i].is_worker for i in s.selection if i in s.world.units)),
    Objective("Send peasants to the gold mine: right-click the mine", lambda s: _harvesting(s, gold=True)),
    Objective("Put a peasant on lumber: right-click a tree", lambda s: _harvesting(s, gold=False)),
    Objective("Build a farm for supply: select a peasant, press B then F, click open ground", lambda s: bool(_buildings(s, BuildingType.FARM))),
    Objective("Build a barracks: B then B", lambda s: bool(_buildings(s, BuildingType.BARRACKS))),
    Objective("Train a footman: select the barracks, press F", lambda s: any(u.type is UnitType.FOOTMAN for u in _units(s)) or any(b.queue for b in _buildings(s, BuildingType.BARRACKS, done=True))),
    Objective("Gather your army (Ctrl+A) and attack-move (A) towards the enemy", lambda s: any(isinstance(o, (AttackMove, Patrol)) for u in _units(s) for o in u.orders) or s.stats["buildings_razed"] > 0),
    Objective("Raze every enemy building to win — F2 opens the codex, F1 the controls", lambda s: False),
)


class Tutorial:
    def __init__(self) -> None:
        self.step = 0
        self.visible = True

    @property
    def current(self) -> Objective | None:
        return OBJECTIVES[self.step] if self.step < len(OBJECTIVES) else None

    @property
    def finished(self) -> bool:
        return self.step >= len(OBJECTIVES) - 1

    def update(self, scene: GameScene) -> bool:
        """Advance past completed objectives; True when one was just completed."""
        advanced = False
        while self.step < len(OBJECTIVES) - 1 and OBJECTIVES[self.step].done(scene):
            self.step += 1
            advanced = True
        return advanced
