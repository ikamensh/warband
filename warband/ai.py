"""The computer opponent: keep the peasants busy, build in a sensible order,
train soldiers without pause, defend the base and attack in growing waves.

One :class:`Brain` per AI player thinks once a second of simulation
time; everything it does goes through :class:`World` commands, checked
with the matching ``can_*`` query first, so the model never raises here.
The brain knows where the enemy's buildings are (as Warcraft's AI did);
everything else it does is what a player could do.
"""

from __future__ import annotations

import math
import random

from warband.model import Attack, AttackMove, Building, Deposit, Harvest, Point, Pos, Unit, World, dist
from warband.rules import BUILDINGS, UNITS, BuildingType, Resource, UnitType

THINK_EVERY = 1.0
TARGET_PEASANTS = 10
EXPAND_DISTANCE = 14.0  # a mine farther than this from the hall gets a hall of its own
FIRST_WAVE = 6
WAVE_GROWTH = 2
DEFEND_RADIUS = 9.0
BUILD_MIN_DISTANCE = 2
BUILD_MAX_DISTANCE = 11


def lumber_rich(lumber: int) -> bool:
    return lumber > 3000


class Brain:
    def __init__(self, player: int) -> None:
        self.player = player
        self.next_think = 0.0
        self.wave = FIRST_WAVE
        self.attacking = False
        self.unit_toggle = 0

    def think(self, world: World, rng: random.Random) -> None:
        """Act if a think is due; call this every simulation step."""
        if world.time < self.next_think or not world.players[self.player].alive or world.winner is not None:
            return
        self.next_think = world.time + THINK_EVERY
        self._economy(world)
        self._construction(world, rng)
        self._training(world)
        self._military(world, rng)

    # -- Helpers -----------------------------------------------------------------

    def _units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def _peasants(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if u.is_worker]

    def _army(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if not u.is_worker]

    def _hall(self, world: World) -> Building | None:
        halls = world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)
        return halls[0] if halls else None

    @staticmethod
    def _job(unit: Unit) -> Resource | None:
        """What a peasant is gathering, if anything."""
        if unit.inside is not None or unit.carrying is Resource.GOLD:
            return Resource.GOLD
        if unit.carrying is Resource.LUMBER:
            return Resource.LUMBER
        for order in unit.orders:
            if isinstance(order, Harvest):
                return Resource.GOLD if isinstance(order.target, int) else Resource.LUMBER
            if isinstance(order, Deposit):
                continue
        return None

    # -- Economy -----------------------------------------------------------------

    def _economy(self, world: World) -> None:
        hall = self._hall(world)
        if hall is None:
            return
        player = world.players[self.player]
        peasants = self._peasants(world)
        mine = world._nearest_mine(hall.center, math.inf)
        tree = world.nearest_tree(hall.center, 14)
        # Lumber piles up faster than it is spent: keep the wood crew small, and send it mining when the pile is high.
        want_choppers = 0 if lumber_rich(player.lumber) or tree is None else 3 if player.gold > 2000 or player.lumber < 400 else 2
        choppers = [p for p in peasants if self._job(p) is Resource.LUMBER and not p.hidden]
        if len(choppers) > want_choppers and mine is not None:
            spare = [c for c in choppers if c.carrying is None]
            if spare:
                world.harvest([spare[0].id], mine.id)
                choppers.remove(spare[0])
        for peasant in peasants:
            if peasant.orders or peasant.hidden:
                continue
            if len(choppers) < want_choppers and tree is not None:
                world.harvest([peasant.id], tree)
                choppers.append(peasant)
            elif mine is not None:
                world.harvest([peasant.id], mine.id)
            elif tree is not None:
                world.harvest([peasant.id], tree)

    # -- Construction -----------------------------------------------------------------

    def _construction(self, world: World, rng: random.Random) -> None:
        if any(not b.done for b in world.player_buildings(self.player)):
            return  # one site at a time; a builder in trouble would otherwise stall the whole plan
        peasants = [p for p in self._peasants(world) if not p.hidden and p.carrying is None]
        if not peasants:
            return
        hall = self._hall(world)
        plan = self._next_building(world, hall, peasants[0].pos)
        if plan is None:
            return
        wanted, anchor = plan
        site = self._site(world, wanted, anchor, rng)
        if site is None:
            return
        builder = min(peasants, key=lambda p: (self._job(p) is Resource.GOLD, dist(p.pos, (site[0], site[1]))))
        world.build(builder.id, wanted, site)

    def _next_building(self, world: World, hall: Building | None, fallback: Point) -> tuple[BuildingType, Point] | None:
        """``(what to build, where near)`` or None."""
        player = self.player
        gold = world.players[player].gold
        mine = world._nearest_mine(hall.center if hall is not None else fallback, math.inf)
        if hall is None:
            wanted, anchor = BuildingType.TOWN_HALL, (mine.center if mine is not None else fallback)
        else:
            used, cap = world.supply(player)
            barracks = world.player_buildings(player, BuildingType.BARRACKS, done=True)
            farms = world.player_buildings(player, BuildingType.FARM, done=True)
            towers = world.player_buildings(player, BuildingType.TOWER, done=True)
            anchor = hall.center
            if used + 2 > cap:
                wanted = BuildingType.FARM
            elif not barracks:
                wanted = BuildingType.BARRACKS
            elif mine is not None and dist(mine.center, hall.center) > EXPAND_DISTANCE and not world.player_buildings(player, BuildingType.TOWN_HALL, done=False):
                wanted, anchor = BuildingType.TOWN_HALL, mine.center
            elif len(self._army(world)) >= 6 and len(towers) < 2 and gold > 1200:
                wanted = BuildingType.TOWER
            elif len(farms) >= 3 and len(barracks) < 2 and gold > 1500:
                wanted = BuildingType.BARRACKS
            else:
                return None
        if world.can_afford(player, BUILDINGS[wanted].cost) is not None:
            return None
        return wanted, anchor

    def _site(self, world: World, building_type: BuildingType, anchor: Point, rng: random.Random) -> Pos | None:
        size = BUILDINGS[building_type].size
        ax, ay = int(anchor[0]), int(anchor[1])
        candidates: list[tuple[float, Pos]] = []
        for dy in range(-BUILD_MAX_DISTANCE, BUILD_MAX_DISTANCE + 1):
            for dx in range(-BUILD_MAX_DISTANCE, BUILD_MAX_DISTANCE + 1):
                pos = (ax + dx - size // 2, ay + dy - size // 2)
                if max(abs(dx), abs(dy)) < BUILD_MIN_DISTANCE + size:
                    continue
                candidates.append((math.hypot(dx, dy) + rng.random() * 2, pos))
        candidates.sort()
        for _score, pos in candidates:
            if world.can_place(building_type, pos, self.player) is None and self._keeps_paths_open(world, pos, size):
                return pos
        return None

    def _keeps_paths_open(self, world: World, pos: Pos, size: int) -> bool:
        """Leave a tile of clearance around other buildings so peasants can always get through."""
        for b in world.player_buildings(self.player):
            gap_x = max(b.x - (pos[0] + size), pos[0] - (b.x + b.size), 0)
            gap_y = max(b.y - (pos[1] + size), pos[1] - (b.y + b.size), 0)
            if max(gap_x, gap_y) < 1:
                return False
        return True

    # -- Training ------------------------------------------------------------------

    def _training(self, world: World) -> None:
        player = self.player
        hall = self._hall(world)
        if hall is not None and not hall.queue and len(self._peasants(world)) < TARGET_PEASANTS:
            if world.can_train(hall, UnitType.PEASANT) is None:
                world.train(hall.id, UnitType.PEASANT)
        for barracks in world.player_buildings(player, BuildingType.BARRACKS, done=True):
            if barracks.rally is None and hall is not None:
                world.set_rally(barracks.id, self._muster_point(world, hall))
            if barracks.queue:
                continue
            gold = world.players[player].gold
            choice = UnitType.KNIGHT if gold > 1600 and self.unit_toggle % 3 == 2 else UnitType.ARCHER if self.unit_toggle % 2 else UnitType.FOOTMAN
            if world.can_train(barracks, choice) is None:
                world.train(barracks.id, choice)
                self.unit_toggle += 1
            elif choice is not UnitType.FOOTMAN and world.can_train(barracks, UnitType.FOOTMAN) is None:
                world.train(barracks.id, UnitType.FOOTMAN)
                self.unit_toggle += 1

    def _muster_point(self, world: World, hall: Building) -> Point:
        """Between the hall and the map centre: the side the enemy comes from."""
        cx, cy = world.width / 2, world.height / 2
        hx, hy = hall.center
        d = dist((hx, hy), (cx, cy)) or 1.0
        return (hx + (cx - hx) / d * 6, hy + (cy - hy) / d * 6)

    # -- Military --------------------------------------------------------------------

    def _military(self, world: World, rng: random.Random) -> None:
        army = self._army(world)
        threat = self._threat(world)
        if threat is not None:
            self.attacking = False
            for unit in army:
                if not isinstance(unit.order, Attack):
                    world.attack_move([unit.id], threat)
            return
        targets = self._enemy_targets(world)
        if not targets:
            return
        if self.attacking:
            if len(army) < 3:
                self.attacking = False
                hall = self._hall(world)
                if hall is not None:
                    world.move([u.id for u in army], self._muster_point(world, hall))
                return
            idle = [u for u in army if not u.orders]
            if idle:
                target = min(targets, key=lambda t: dist(t, idle[0].pos))
                world.attack_move([u.id for u in idle], target)
            return
        if len(army) >= self.wave:
            self.attacking = True
            self.wave += WAVE_GROWTH
            hall = self._hall(world)
            origin = hall.center if hall is not None else army[0].pos
            world.attack_move([u.id for u in army], min(targets, key=lambda t: dist(t, origin)))

    def _enemy_targets(self, world: World) -> list[Point]:
        """Enemy buildings; once those are gone, whatever enemy units remain."""
        buildings = [b.center for b in world.buildings.values() if b.player is not None and b.player != self.player]
        if buildings:
            return buildings
        return [u.pos for u in world.units.values() if u.player != self.player and world.players[u.player].alive]

    def _threat(self, world: World) -> Point | None:
        """The nearest visible enemy close to one of our buildings."""
        best, best_d = None, math.inf
        for unit in world.units.values():
            if unit.player == self.player or unit.hidden or not world.is_visible(self.player, unit.tile):
                continue
            for b in world.player_buildings(self.player):
                d = dist(unit.pos, b.center)
                if d < DEFEND_RADIUS and d < best_d:
                    best, best_d = unit.pos, d
        return best
