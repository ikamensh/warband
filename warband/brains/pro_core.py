"""Match memory and shared map knowledge for the stronger brain."""

from __future__ import annotations

import math
from warband.brains.pro_profiles import PRO, ProProfile
from warband.brains.ai import Hunt, fighters, known_enemy_buildings, known_mines
from warband.sim import mapgen
from warband.sim.model import Build, Building, Point, Repair, Salvage, Unit, World, dist, tile_center
from warband.sim.rules import BuildingType, UnitType
from warband.sim.worker_knowledge import KnownMine

class _ProBrainCore:
    """State and facts shared by the economy and combat decisions."""

    def __init__(self, player: int, profile: ProProfile = PRO) -> None:
        self.player = player
        self.profile = profile
        self.next_think = 0.0
        self.next_combat = 0.0
        self.attacking = False
        self.target: Point | None = None      # where the current push is aimed
        self.commit_strength = 0.0            # what the army was worth when it set out
        self.regroup_until = 0.0              # no new push before this, so a beaten army rebuilds
        self.scouts: list[int] = []  # our eyes on the enemy: the flying machine, or a peasant marked for it (_send_scout)
        self.prospector: int | None = None  # the peasant out looking for the next mine
        self._prospect_leg = 0              # how many places it has been sent to look
        self.raiders: list[int] = []
        self.hunt = Hunt()  # the search for rivals it has lost track of
        self.rushers: list[int] = []  # peasants walking to the enemy's mine to raise a tower there
        self.rush_drafted = 0
        self.rush_over = False
        self._hurt: set[int] = set()  # soldiers pulled out to heal
        self.hunters: dict[int, int] = {}  # our peasants sent at an enemy peasant inside our base: hunter -> its prey
        self.strikers: set[int] = set()    # our peasants sent at an enemy tower standing on our ground
        self.lumber_short = 0  # the wood the purchases it has the gold for are waiting on; see _shortfall
        self._opening_next: BuildingType | None = None  # the building of the opening that goes up next, while one is left
        self.log: list[tuple[float, str]] = []
        self._seen: dict[int, dict[UnitType, float]] = {}  # per opponent: most of each kind ever seen at once
        self._seen_at: dict[int, float] = {}               # …and when that opponent was last looked at
        self.creeping: int | None = None   # the lair the army is clearing
        self.creep_strength = 0.0          # what the army was worth when it set out to clear it
        self.creep_until = 0.0             # …and when it gives that camp up whatever it has left
        self.camp_seen: dict[int, float] = {}   # per lair: the most its guards were ever seen to be worth
        self.camp_retry: dict[int, float] = {}  # …and when a camp that beat the army off is worth trying again
        self.errands: dict[int, Point] = {}  # soldiers sent at a raider or a camp: soldier -> where (_send_on_errand)
        self.threatened = -math.inf  # when a threat to the base was last in sight (_recall waits for CALM after it)

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    def _recover(self, world: World) -> None:
        """Nothing left but buildings: buy the cheapest body that can still work."""
        buildings = world.player_buildings(self.player)
        if any(b.done and b.queue for b in buildings):
            return
        recruit = world.recovery_recruit(self.player)
        if recruit is None:
            return
        building, unit_type = recruit
        if world.can_train(building, unit_type) is not None:
            for b in buildings:
                if not b.done:
                    world.cancel_building(b.id)
                elif b.research is not None:
                    world.cancel_research(b.id)
        world.train(building.id, unit_type)

    def _units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def _peasants(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if u.is_worker]

    def _army(self, world: World) -> list[Unit]:
        return fighters(self._units(world))

    def _halls(self, world: World) -> list[Building]:
        return world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)

    def _hall(self, world: World) -> Building | None:
        halls = self._halls(world)
        return halls[0] if halls else None

    def _knowledge(self, world: World):
        """What this player has actually seen: the model's own per-player memory."""
        return world.worker_knowledge[self.player]

    def _known_enemy_buildings(self, world: World) -> list:
        return known_enemy_buildings(world, self.player)

    def _unexplored_corner(self, world: World) -> Point:
        """Somewhere worth looking when nothing of theirs has been found yet.

        In a duel the opposite corner is the only likely rival. With more
        seats, try the nearest unexplored rival cell first; crossing the
        whole board before looking next door delays every first encounter.
        """
        hall = self._hall(world)
        here = hall.center if hall is not None else (world.width / 2, world.height / 2)
        corners = mapgen.start_guesses(world.width, world.height, world.seats)
        if world.seats > 4:
            own_cell = min(corners, key=lambda point: dist(point, here))
            unknown = [point for point in corners if point != own_cell
                       and not world.is_explored(self.player, (int(point[0]), int(point[1])))]
            if unknown:
                return min(unknown, key=lambda point: dist(point, here))
        return max(corners, key=lambda c: dist(c, here))

    def _known_mines(self, world: World) -> list[KnownMine]:
        return known_mines(world, self.player)

    def _enemies(self, world: World) -> list[Unit]:
        """Visible enemy units of players still in the game."""
        return [u for u in world.units.values()
                if u.player != self.player and u.hp > 0 and not u.hidden
                and world.players[u.player].alive and world.is_visible(self.player, u.tile)]

    def _observe(self, world: World) -> None:
        """Remember the most of each kind the enemy was ever seen with, fading as the sighting ages.

        The memory holds a *count*, so it has to be the high-water mark rather
        than a running total: adding every sighting to a decaying tally reports
        roughly ten times the army that is actually there, and a brain that
        believes it is always outnumbered never attacks at all.
        """
        current: dict[int, dict[UnitType, float]] = {}
        for unit in self._enemies(world):
            if not unit.is_worker:
                seen = current.setdefault(unit.player, {})
                seen[unit.type] = seen.get(unit.type, 0.0) + 1.0
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

    def _front_point(self, world: World, hall: Building) -> Point:
        """Where the army waits: between the hall and whoever is coming."""
        enemy_halls = [record.center for record in self._known_enemy_buildings(world)]
        towards = min(enemy_halls, key=lambda c: dist(c, hall.center)) if enemy_halls else (world.width / 2, world.height / 2)
        hx, hy = hall.center
        away = dist((hx, hy), towards) or 1.0
        return self._standable(world, (hx + (towards[0] - hx) / away * 6, hy + (towards[1] - hy) / away * 6))

    @staticmethod
    def _standable(world: World, point: Point) -> Point:
        """The nearest ground a unit can be told to walk to.

        Six tiles towards the enemy is a fine place for an army to wait until a
        farm is standing on it, at which point a Move there is an order the unit
        can never finish: it paths as close as it can and stops, for good. Fuzz
        catches that as a stalled unit.
        """
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

    def _answering(self, peasant: Unit) -> bool:
        """Whether *peasant* is out answering a rush, so no other job takes it."""
        return peasant.id in self.hunters or peasant.id in self.strikers

    def _free_peasants(self, world: World, *, miners: bool = False) -> list[Unit]:
        """Peasants a rush's answer may draft: not building and on no other errand; with *miners*, the ones
        inside a mine too, who obey as they come out with their load."""
        return [p for p in self._peasants(world) if p.constructing is None and (miners or p.inside is None)
                and not isinstance(p.order, (Build, Repair, Salvage)) and p.id not in self.scouts and p.id not in self.rushers
                and p.id != self.prospector and not self._answering(p)]
