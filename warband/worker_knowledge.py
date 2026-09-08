"""Remembered terrain and resource facts for decisions made under fog of war.

Seeing a structure reveals its footprint. Its remembered position and contents
remain unchanged while hidden; owned buildings are always known to their owner.
Unknown terrain stays blocked for automatic worker routes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from warband.rules import BuildingType, Terrain

if TYPE_CHECKING:
    from warband.model import World


@dataclass(frozen=True)
class KnownMine:
    id: int
    x: int
    y: int
    size: int
    gold: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.size, self.size

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.size / 2, self.y + self.size / 2


@dataclass(frozen=True)
class _Building:
    id: int
    x: int
    y: int
    size: int
    player: int | None
    threat_range: float = 0.0

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.size / 2, self.y + self.size / 2


class WorkerKnowledge:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.terrain: list[Terrain | None] = [None] * (width * height)
        self.known = bytearray(width * height)
        self.blocked = bytearray([1]) * (width * height)
        self.mines: dict[int, KnownMine] = {}
        self._buildings: dict[int, _Building] = {}

    @property
    def threats(self) -> tuple[_Building, ...]:
        """Last-observed armed structures; callers filter out their own buildings."""
        return tuple(building for building in self._buildings.values() if building.threat_range > 0)

    def _cells(self, building):
        for y in range(max(0, building.y), min(self.height, building.y + building.size)):
            for x in range(max(0, building.x), min(self.width, building.x + building.size)):
                yield y * self.width + x

    def _rebuild_grid(self) -> None:
        blocking = (Terrain.WATER, Terrain.TREES, Terrain.ROCK)
        for index, terrain in enumerate(self.terrain):
            self.known[index] = terrain is not None
            self.blocked[index] = terrain is None or terrain in blocking
        for building in self._buildings.values():
            for index in self._cells(building):
                self.known[index] = self.blocked[index] = 1

    def refresh(self, world: World, player: int) -> None:
        if (world.width, world.height) != (self.width, self.height):
            raise ValueError("Worker knowledge dimensions must match the world")
        visible = world.visible[player]
        for index, shown in enumerate(visible):
            if shown:
                self.terrain[index] = world.terrain[index // self.width][index % self.width]
        observed = {building.id: building for building in world.buildings.values()
                    if building.player == player or any(visible[index] for index in self._cells(building))}
        for bid, remembered in list(self._buildings.items()):
            if bid not in observed and (remembered.player == player or any(visible[index] for index in self._cells(remembered))):
                del self._buildings[bid]
                self.mines.pop(bid, None)
        for building in observed.values():
            threat_range = building.info.range + 1.5 if building.done and building.info.damage else 0.0
            self._buildings[building.id] = _Building(building.id, building.x, building.y, building.size, building.player, threat_range)
            if building.type is BuildingType.GOLD_MINE:
                self.mines[building.id] = KnownMine(building.id, building.x, building.y, building.size, building.gold)
            else:
                self.mines.pop(building.id, None)
        self._rebuild_grid()

    def resource_rect(self, target: int | tuple[int, int]) -> tuple[int, int, int, int] | None:
        if isinstance(target, int):
            mine = self.mines.get(target)
            return mine.rect if mine is not None else None
        x, y = target
        if 0 <= x < self.width and 0 <= y < self.height and self.terrain[y * self.width + x] is Terrain.TREES:
            return x, y, 1, 1
        return None

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height,
                "terrain": [terrain.value if terrain is not None else None for terrain in self.terrain],
                "buildings": [asdict(building) for building in self._buildings.values()],
                "mines": [asdict(mine) for mine in self.mines.values()]}

    @classmethod
    def from_dict(cls, data: dict) -> WorkerKnowledge:
        knowledge = cls(data["width"], data["height"])
        knowledge.terrain = [Terrain(value) if value is not None else None for value in data["terrain"]]
        if len(knowledge.terrain) != knowledge.width * knowledge.height:
            raise ValueError("Remembered terrain must match its map dimensions")
        knowledge._buildings = {item["id"]: _Building(**item) for item in data["buildings"]}
        knowledge.mines = {item["id"]: KnownMine(**item) for item in data["mines"]}
        knowledge._rebuild_grid()
        return knowledge
