"""Observed opponent memory and map queries shared by a stronger brain's decisions.

Intelligence has no economic or tactical state: forgetting a sighting, changing
how a known mine is found, or choosing safe staging ground is local to it.
"""
from __future__ import annotations

import math
from warband.brains.pro_profiles import ProProfile
from warband.brains.pro_force import strength
from warband.brains.ai import camp_safe_point, known_enemy_buildings, known_mines
from warband.sim import mapgen
from warband.sim.model import Building, Point, Unit, World, dist, plain_sum, tile_center
from warband.sim.rules import BuildingType, UnitType
from warband.sim.worker_knowledge import KnownMine


class Intelligence:
    def __init__(self, player: int, profile: ProProfile) -> None:
        self.player = player
        self.profile = profile
        self.log: list[tuple[float, str]] = []
        self._seen: dict[int, dict[UnitType, float]] = {}
        self._seen_at: dict[int, float] = {}
        self._army_seen: dict[int, tuple[float, Point, int]] = {}
        self._building_seen: dict[int, tuple[float, float, int]] = {}

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    def units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def peasants(self, world: World) -> list[Unit]:
        return [u for u in self.units(world) if u.is_worker]

    def halls(self, world: World) -> list[Building]:
        return world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)

    def hall(self, world: World) -> Building | None:
        halls = self.halls(world)
        return halls[0] if halls else None

    def known_buildings(self, world: World) -> list:
        return known_enemy_buildings(world, self.player)

    def unexplored_corner(self, world: World) -> Point:
        """Somewhere worth looking when nothing of theirs has been found yet.

        In a duel the opposite corner is the only likely rival. With more
        seats, try the nearest unexplored rival cell first; crossing the
        whole board before looking next door delays every first encounter.
        """
        hall = self.hall(world)
        here = hall.center if hall is not None else (world.width / 2, world.height / 2)
        corners = mapgen.start_guesses(world.width, world.height, world.seats)
        if world.seats > 4:
            own_cell = min(corners, key=lambda point: dist(point, here))
            unknown = [point for point in corners if point != own_cell
                       and not world.is_explored(self.player, (int(point[0]), int(point[1])))]
            if unknown:
                return min(unknown, key=lambda point: dist(point, here))
        return max(corners, key=lambda c: dist(c, here))

    def known_mines(self, world: World) -> list[KnownMine]:
        return known_mines(world, self.player)

    def enemies(self, world: World) -> list[Unit]:
        """Visible enemy units of players still in the game."""
        return [u for u in world.units.values()
                if u.player != self.player and u.hp > 0 and not u.hidden
                and not world.players[u.player].neutral and world.players[u.player].alive
                and world.is_visible(self.player, u.tile)]

    def observe(self, world: World) -> None:
        """Remember the most of each kind the enemy was ever seen with, fading as the sighting ages.

        The memory holds a *count*, so it has to be the high-water mark rather
        than a running total: adding every sighting to a decaying tally reports
        roughly ten times the army that is actually there, and a brain that
        believes it is always outnumbered never attacks at all.
        """
        current: dict[int, dict[UnitType, float]] = {}
        soldiers: dict[int, list[Unit]] = {}
        for unit in self.enemies(world):
            if not unit.is_worker:
                seen = current.setdefault(unit.player, {})
                seen[unit.type] = seen.get(unit.type, 0.0) + 1.0
                soldiers.setdefault(unit.player, []).append(unit)
        for owner, seen_now in soldiers.items():
            middle = (plain_sum(u.x for u in seen_now) / len(seen_now),
                      plain_sum(u.y for u in seen_now) / len(seen_now))
            self._army_seen[owner] = (world.time, middle, len(seen_now))
        if self.profile.soft_target:
            # What stands at each known enemy building while it is in sight, remembered for when it is not:
            # a target choice made from home otherwise prices every unseen expansion at nought.
            for record in self.known_buildings(world):
                if world.is_visible(self.player, (int(record.center[0]), int(record.center[1]))):
                    local = [u for u in soldiers.get(record.player, ()) if dist(u.pos, record.center) <= 14.0]
                    self._building_seen[record.id] = (world.time, strength(world, local), len(local))
        fade = 0.99 ** (self.profile.think_every / 0.4)
        for player in world.players[:world.seats]:  # the wilds are no opponent to keep a memory of
            if player.id == self.player or not player.alive:
                continue
            now = current.get(player.id, {})
            if now:
                self._seen_at[player.id] = world.time
            memory = self._seen.setdefault(player.id, {})
            for unit_type in set(memory) | set(now):
                memory[unit_type] = max(memory.get(unit_type, 0.0) * fade, now.get(unit_type, 0.0))

    def remembered(self, player: int | None = None) -> dict[UnitType, float]:
        """How many of each kind *player* was last seen with; every opponent's, added, if None."""
        if player is not None:
            return dict(self._seen.get(player, {}))
        out: dict[UnitType, float] = {}
        for memory in self._seen.values():
            for unit_type, count in memory.items():
                out[unit_type] = out.get(unit_type, 0.0) + count
        return out

    def last_seen(self, player: int | None = None) -> float:
        """When an opponent was last looked at; the most recent look at anyone if None."""
        if player is not None:
            return self._seen_at.get(player, -math.inf)
        return max(self._seen_at.values(), default=-math.inf)

    def front_point(self, world: World, hall: Building) -> Point:
        """Where the army waits: between the hall and whoever is coming."""
        enemy_halls = [record.center for record in self.known_buildings(world)]
        towards = min(enemy_halls, key=lambda c: dist(c, hall.center)) if enemy_halls else (world.width / 2, world.height / 2)
        hx, hy = hall.center
        away = dist((hx, hy), towards) or 1.0
        return self.standable(world, (hx + (towards[0] - hx) / away * 6, hy + (towards[1] - hy) / away * 6))

    def standable(self, world: World, point: Point, *, expedition: bool = False) -> Point:
        """The nearest ground a unit can be told to walk to.

        Six tiles towards the enemy is a fine place for an army to wait until a
        farm is standing on it, at which point a Move there is an order the unit
        can never finish: it paths as close as it can and stops, for good. Fuzz
        catches that as a stalled unit.
        """
        if not expedition:
            point = camp_safe_point(world, self.player, point)
        x, y = int(point[0]), int(point[1])
        if world.in_bounds((x, y)) and world.passable(x, y):
            return point
        for ring in range(1, 9):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    tile = (x + dx, y + dy)
                    if world.in_bounds(tile) and world.passable(*tile):
                        return tile_center(tile)
        return point

    def army_sighting(self, owner: int) -> tuple[float, Point, int] | None:
        """The last visible army for one opponent, if any."""
        return self._army_seen.get(owner)

    def army_sightings(self) -> list[tuple[int, tuple[float, Point, int]]]:
        """Opponent sightings in observation order, for deterministic target choices."""
        return list(self._army_seen.items())

    def building_sighting(self, building: int) -> tuple[float, float, int] | None:
        return self._building_seen.get(building)
