"""Remembered terrain and resource facts for decisions made under fog of war.

Seeing a structure reveals its footprint. Its remembered position and contents
remain unchanged while hidden; owned buildings are always known to their owner.
Unknown terrain stays blocked for automatic worker routes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final, TYPE_CHECKING

from warband.rules import BuildingType, Terrain

try:
    from warband import _native  # the footprint test in C, built only with the compiled simulation (warband/fastsim.py)
except ImportError:  # the source runs, as it does in the game
    _native = None  # type: ignore[assignment]
_any_lit: Final = None if _native is None else _native.any_lit  # looked up once: sees is asked dozens of times a step

if TYPE_CHECKING:
    from warband.model import World

BLOCKING: Final = (Terrain.WATER, Terrain.TREES, Terrain.ROCK)


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
        self.buildings: dict[int, _Building] = {}  # last-observed footprint of every structure ever seen
        self.threats: tuple[_Building, ...] = ()  # the armed ones among them; callers filter out their own
        self._terrain_blocked = bytearray([1]) * (width * height)  # the grid without any footprint stamped on it
        self._spans: dict[tuple[int, int, int], tuple[tuple[int, int], ...]] = {}
        self._trees: set[int] = set()
        self._tree_order: tuple[int, ...] | None = None
        self.version = 0  # counts the times blocked and threats were stamped anew, the only times they change

    @property
    def trees(self) -> tuple[int, ...]:
        """Remembered tree tiles as flat indices in map order, so route plans consider them in a fixed order."""
        if self._tree_order is None:
            self._tree_order = tuple(sorted(self._trees))
        return self._tree_order

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
        if _any_lit is not None:
            return _any_lit(visible, x, y, size, size, self.width, self.height)
        for start, stop in self.spans(x, y, size):
            if visible.count(0, start, stop) < stop - start:  # a C scan, no slice copied
                return True
        return False

    def _stamp_buildings(self) -> None:
        """Rebuild the public grid from the terrain layer with every remembered footprint blocked."""
        self.version += 1
        blocked = self.blocked
        blocked[:] = self._terrain_blocked
        for building in self.buildings.values():
            for start, stop in self.spans(building.x, building.y, building.size):
                blocked[start:stop] = b"\x01" * (stop - start)
        self.threats = tuple(building for building in self.buildings.values() if building.threat_range > 0)

    def _rebuild_grid(self) -> None:
        """Recompute the terrain layer from scratch; refresh() then keeps it current tile by tile."""
        terrain_blocked, trees = self._terrain_blocked, set()
        for index, terrain in enumerate(self.terrain):
            terrain_blocked[index] = terrain is None or terrain in BLOCKING
            if terrain is Terrain.TREES:
                trees.add(index)
        self._trees, self._tree_order = trees, None
        self._stamp_buildings()

    def refresh(self, world: World, player: int) -> None:
        if (world.width, world.height) != (self.width, self.height):
            raise ValueError("Worker knowledge dimensions must match the world")
        visible = world.visible[player]
        width = self.width
        remembered, terrain_blocked, trees = self.terrain, self._terrain_blocked, self._trees
        changed = False
        for index in self._stale(world.terrain, visible):
            terrain = world.terrain[index // width][index % width]
            changed = True
            remembered[index] = terrain
            terrain_blocked[index] = terrain in BLOCKING
            if terrain is Terrain.TREES:
                trees.add(index)
            else:
                trees.discard(index)
            self._tree_order = None
        # Owners are narrowed before they are compared, as World.player_buildings explains.
        observed = {building.id: building for building in world.buildings.values()
                    if building.player is not None and building.player == player
                    or self.sees(visible, building.x, building.y, building.size)}
        for bid, remembered_building in list(self.buildings.items()):
            if bid not in observed and (remembered_building.player is not None and remembered_building.player == player
                                        or self.sees(visible, remembered_building.x, remembered_building.y,
                                                     remembered_building.size)):
                del self.buildings[bid]
                self.mines.pop(bid, None)
                changed = True
        for building in observed.values():
            info = building.info
            threat_range = info.range + 1.5 if building.done and info.damage else 0.0
            known = self.buildings.get(building.id)
            # Nothing but a structure's threat can change under a fixed id: it is built once and never moves.
            if known is None or known.threat_range != threat_range:
                self.buildings[building.id] = _Building(building.id, building.x, building.y, building.size,
                                                        building.player, threat_range)
                changed = True
            if building.type is BuildingType.GOLD_MINE:
                mine = self.mines.get(building.id)
                if mine is None or mine.gold != building.gold:
                    self.mines[building.id] = KnownMine(building.id, building.x, building.y, building.size, building.gold)
            else:
                self.mines.pop(building.id, None)
        if changed:  # the grid still stands as it was unless remembered terrain or a footprint changed
            self._stamp_buildings()

    def _stale(self, rows: list[list[Terrain]], visible: bytearray) -> list[int]:
        """The flat indices, in map order, of the lit tiles whose remembered terrain is not what is there now."""
        width, remembered = self.width, self.terrain
        if _native is not None:
            return _native.stale_tiles(visible, rows, remembered, width, self.height)
        stale: list[int] = []
        for y, row in enumerate(rows):
            base = y * width
            seen = visible[base:base + width]
            lo = seen.find(1)
            while lo >= 0:  # each run of lit tiles in the row, compared whole first: usually nothing changed
                hi = seen.find(0, lo)
                if hi < 0:
                    hi = width
                if remembered[base + lo:base + hi] != row[lo:hi]:
                    stale.extend(base + x for x in range(lo, hi) if remembered[base + x] is not row[x])
                lo = seen.find(1, hi)
        return stale

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
                "buildings": [asdict(building) for building in self.buildings.values()],
                "mines": [asdict(mine) for mine in self.mines.values()]}

    @classmethod
    def from_dict(cls, data: dict) -> WorkerKnowledge:
        knowledge = cls(data["width"], data["height"])
        knowledge.terrain = [Terrain(value) if value is not None else None for value in data["terrain"]]
        if len(knowledge.terrain) != knowledge.width * knowledge.height:
            raise ValueError("Remembered terrain must match its map dimensions")
        knowledge.buildings = {item["id"]: _Building(**item) for item in data["buildings"]}
        knowledge.mines = {item["id"]: KnownMine(**item) for item in data["mines"]}
        knowledge._rebuild_grid()
        return knowledge
