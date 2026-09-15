"""Remembered terrain and resource facts for decisions made under fog of war.

Seeing a structure reveals its footprint. Its remembered position and contents
remain unchanged while hidden; owned buildings are always known to their owner.
Unknown terrain stays blocked for automatic worker routes.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from warband.rules import BuildingType, Terrain

if TYPE_CHECKING:
    from warband.model import World

BLOCKING = (Terrain.WATER, Terrain.TREES, Terrain.ROCK)


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
        self.blocked = bytearray([1]) * (width * height)
        self.mines: dict[int, KnownMine] = {}
        self.threats: tuple[_Building, ...] = ()  # last-observed armed structures; callers filter out their own
        self._buildings: dict[int, _Building] = {}
        self._terrain_blocked = bytearray([1]) * (width * height)  # the grid without any footprint stamped on it
        self._spans: dict[tuple[int, int, int], tuple[tuple[int, int], ...]] = {}

    def spans(self, x: int, y: int, size: int) -> tuple[tuple[int, int], ...]:
        """One flat-index range per row of a footprint, clipped to the map. Footprints never move, so these are cached."""
        key = (x, y, size)
        found = self._spans.get(key)
        if found is None:
            left, right = max(0, x), min(self.width, x + size)
            found = tuple((row * self.width + left, row * self.width + right)
                          for row in range(max(0, y), min(self.height, y + size))) if left < right else ()
            self._spans[key] = found
        return found

    def sees(self, visible: bytearray, x: int, y: int, size: int) -> bool:
        """Whether any tile of a footprint lies in *visible*, a fog grid of this map's shape."""
        for start, stop in self.spans(x, y, size):
            if any(visible[start:stop]):
                return True
        return False

    def _stamp_buildings(self) -> None:
        """Rebuild the public grid from the terrain layer with every remembered footprint blocked."""
        blocked = self.blocked
        blocked[:] = self._terrain_blocked
        for building in self._buildings.values():
            for start, stop in self.spans(building.x, building.y, building.size):
                blocked[start:stop] = b"\x01" * (stop - start)
        self.threats = tuple(building for building in self._buildings.values() if building.threat_range > 0)

    def _rebuild_grid(self) -> None:
        """Recompute the terrain layer from scratch; refresh() then keeps it current tile by tile."""
        terrain_blocked = self._terrain_blocked
        for index, terrain in enumerate(self.terrain):
            terrain_blocked[index] = terrain is None or terrain in BLOCKING
        self._stamp_buildings()

    def refresh(self, world: World, player: int) -> None:
        if (world.width, world.height) != (self.width, self.height):
            raise ValueError("Worker knowledge dimensions must match the world")
        visible = world.visible[player]
        width = self.width
        remembered, terrain_blocked = self.terrain, self._terrain_blocked
        for y, row in enumerate(world.terrain):
            base = y * width
            seen = visible[base:base + width]
            if not any(seen):
                continue
            for x in itertools.compress(range(width), seen):
                index = base + x
                terrain = row[x]
                if remembered[index] is not terrain:
                    remembered[index] = terrain
                    terrain_blocked[index] = terrain in BLOCKING
        observed = {building.id: building for building in world.buildings.values()
                    if building.player == player or self.sees(visible, building.x, building.y, building.size)}
        for bid, remembered_building in list(self._buildings.items()):
            if bid not in observed and (remembered_building.player == player
                                        or self.sees(visible, remembered_building.x, remembered_building.y,
                                                     remembered_building.size)):
                del self._buildings[bid]
                self.mines.pop(bid, None)
        for building in observed.values():
            threat_range = building.info.range + 1.5 if building.done and building.info.damage else 0.0
            self._buildings[building.id] = _Building(building.id, building.x, building.y, building.size, building.player, threat_range)
            if building.type is BuildingType.GOLD_MINE:
                self.mines[building.id] = KnownMine(building.id, building.x, building.y, building.size, building.gold)
            else:
                self.mines.pop(building.id, None)
        self._stamp_buildings()

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
