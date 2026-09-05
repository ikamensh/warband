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

from dataclasses import dataclass

from warband.model import Attack, AttackMove, Building, Deposit, Harvest, Point, Pos, Unit, World, dist
from warband.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, Difficulty, Resource, UnitType, Upgrade

EXPAND_DISTANCE = 14.0  # a mine farther than this from the hall gets a hall of its own
DEFEND_RADIUS = 9.0
BUILD_MIN_DISTANCE = 2
BUILD_MAX_DISTANCE = 11
RESEARCH_ORDER = (Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.BLADES_2, Upgrade.ARMOR_2,
                  Upgrade.ARROWS_2, Upgrade.SIEGE, Upgrade.BLESSING)


@dataclass(frozen=True)
class Profile:
    """How a difficulty plays: economy size, tempo and which parts of the tech tree it uses."""

    peasants: int
    think_every: float
    first_wave: int
    wave_growth: int
    barracks: int
    towers: int
    tech: bool  # mill, blacksmith, stables, upgrades
    siege: bool  # workshop and catapults
    clerics: bool  # church and clerics
    harass: bool  # early scouts sent at the enemy's peasants
    reserve: int  # gold kept back before research


PROFILES: dict[Difficulty, Profile] = {
    Difficulty.EASY: Profile(peasants=7, think_every=2.0, first_wave=10, wave_growth=2, barracks=1, towers=0, tech=False, siege=False,
                             clerics=False, harass=False, reserve=1500),
    Difficulty.NORMAL: Profile(peasants=10, think_every=1.0, first_wave=8, wave_growth=3, barracks=2, towers=2, tech=True, siege=True,
                               clerics=False, harass=False, reserve=800),
    Difficulty.HARD: Profile(peasants=14, think_every=0.5, first_wave=8, wave_growth=4, barracks=3, towers=3, tech=True, siege=True,
                             clerics=True, harass=True, reserve=500),
}


def lumber_rich(lumber: int) -> bool:
    return lumber > 3000


class Brain:
    def __init__(self, player: int, difficulty: Difficulty = Difficulty.NORMAL) -> None:
        self.player = player
        self.difficulty = difficulty
        self.profile = PROFILES[difficulty]
        self.next_think = 0.0
        self.wave = self.profile.first_wave
        self.attacking = False
        self.unit_toggle = 0
        self.raiders: list[int] = []
        self.log: list[tuple[float, str]] = []  # (time, what) — the evidence of how it plays

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    def think(self, world: World, rng: random.Random) -> None:
        """Act if a think is due; call this every simulation step."""
        if world.time < self.next_think or not world.players[self.player].alive or world.winner is not None:
            return
        self.next_think = world.time + self.profile.think_every
        self._economy(world)
        self._construction(world, rng)
        self._training(world)
        self._research(world)
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
        want_choppers = 0 if lumber_rich(player.lumber) or tree is None else 4 if player.gold > 2000 or player.lumber < 400 else 3
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
        self.note(world, f"build {wanted.value} at {site}")

    def _next_building(self, world: World, hall: Building | None, fallback: Point) -> tuple[BuildingType, Point] | None:
        """``(what to build, where near)`` or None."""
        player = self.player
        profile = self.profile
        gold = world.players[player].gold
        mine = world._nearest_mine(hall.center if hall is not None else fallback, math.inf)
        if hall is None:
            wanted, anchor = BuildingType.TOWN_HALL, (mine.center if mine is not None else fallback)
        else:
            used, cap = world.supply(player)
            have = lambda t: len(world.player_buildings(player, t, done=True))  # noqa: E731
            army = len(self._army(world))
            anchor = hall.center
            if used + 2 > cap:
                wanted = BuildingType.FARM
            elif not have(BuildingType.BARRACKS):
                wanted = BuildingType.BARRACKS
            elif profile.tech and not have(BuildingType.LUMBER_MILL):
                wanted = BuildingType.LUMBER_MILL
            elif profile.tech and not have(BuildingType.BLACKSMITH) and gold > 900:
                wanted = BuildingType.BLACKSMITH
            elif mine is not None and dist(mine.center, hall.center) > EXPAND_DISTANCE and not world.player_buildings(player, BuildingType.TOWN_HALL, done=False):
                wanted, anchor = BuildingType.TOWN_HALL, mine.center
            elif profile.tech and not have(BuildingType.STABLES) and gold > 1200:
                wanted = BuildingType.STABLES
            elif have(BuildingType.BARRACKS) < profile.barracks and gold > 1500:
                wanted = BuildingType.BARRACKS
            elif profile.siege and have(BuildingType.BLACKSMITH) and not have(BuildingType.WORKSHOP) and gold > 1400:
                wanted = BuildingType.WORKSHOP
            elif profile.clerics and not have(BuildingType.CHURCH) and gold > 1400:
                wanted = BuildingType.CHURCH
            elif army >= 6 and have(BuildingType.TOWER) < profile.towers and gold > 1200:
                wanted = BuildingType.TOWER
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
        profile = self.profile
        hall = self._hall(world)
        if hall is not None and not hall.queue and len(self._peasants(world)) < profile.peasants:
            if world.can_train(hall, UnitType.PEASANT) is None:
                world.train(hall.id, UnitType.PEASANT)
        army = self._army(world)
        counts = {t: sum(1 for u in army if u.type is t) for t in UnitType}
        for building in world.player_buildings(player, done=True):
            if not building.info.trains or building.type is BuildingType.TOWN_HALL:
                continue
            if building.rally is None and hall is not None:
                world.set_rally(building.id, self._muster_point(world, hall))
            if building.queue or building.research is not None:
                continue
            choice = self._choose_unit(world, building, counts)
            if choice is not None and world.can_train(building, choice) is None:
                world.train(building.id, choice)
                counts[choice] += 1
                self.unit_toggle += 1
                self.note(world, f"train {choice.value}")

    def _choose_unit(self, world: World, building: Building, counts: dict[UnitType, int]) -> UnitType | None:
        gold = world.players[self.player].gold
        soldiers = sum(counts.values())
        if building.type is BuildingType.BARRACKS:
            return UnitType.ARCHER if self.unit_toggle % 2 else UnitType.FOOTMAN
        if building.type is BuildingType.STABLES:
            if self.profile.harass and counts[UnitType.SCOUT] < 2:
                return UnitType.SCOUT
            return UnitType.KNIGHT if gold > 1000 else None
        if building.type is BuildingType.WORKSHOP:
            return UnitType.CATAPULT if soldiers >= 6 and counts[UnitType.CATAPULT] < 2 and gold > 1200 else None
        if building.type is BuildingType.CHURCH:
            return UnitType.CLERIC if soldiers >= 6 and counts[UnitType.CLERIC] * 6 < soldiers and gold > 1000 else None
        return None

    def _research(self, world: World) -> None:
        if not self.profile.tech:
            return
        player = world.players[self.player]
        if player.gold < self.profile.reserve:
            return
        for upgrade in RESEARCH_ORDER:
            if upgrade in player.upgrades:
                continue
            for building in world.player_buildings(self.player, done=True):
                if upgrade in building.info.researches and world.can_research(building, upgrade) is None:
                    world.research(building.id, upgrade)
                    self.note(world, f"research {upgrade.value}")
                    return

    def _muster_point(self, world: World, hall: Building) -> Point:
        """Between the hall and the map centre: the side the enemy comes from."""
        cx, cy = world.width / 2, world.height / 2
        hx, hy = hall.center
        d = dist((hx, hy), (cx, cy)) or 1.0
        return (hx + (cx - hx) / d * 6, hy + (cy - hy) / d * 6)

    # -- Military --------------------------------------------------------------------

    def _military(self, world: World, rng: random.Random) -> None:
        army = self._army(world)
        if self.profile.harass:
            self._raid(world)
            army = [u for u in army if u.id not in self.raiders]
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
            self.wave += self.profile.wave_growth
            hall = self._hall(world)
            origin = hall.center if hall is not None else army[0].pos
            target = min(targets, key=lambda t: dist(t, origin))
            world.attack_move([u.id for u in army], target)
            self.note(world, f"attack with {len(army)} towards {tuple(round(c) for c in target)}")

    def _raid(self, world: World) -> None:
        """The first two scouts go for the enemy's peasants and keep at it."""
        self.raiders = [i for i in self.raiders if i in world.units]
        scouts = [u for u in self._army(world) if u.type is UnitType.SCOUT and u.id not in self.raiders]
        while len(self.raiders) < 2 and scouts:
            self.raiders.append(scouts.pop().id)
        idle = [i for i in self.raiders if not world.units[i].orders]
        if not idle:
            return
        mines = [m.center for m in world.mines() if any(u.player != self.player and dist(u.pos, m.center) < 8 for u in world.units.values() if u.is_worker)]
        prey = mines or [u.pos for u in world.units.values() if u.player != self.player and u.is_worker and not u.hidden]
        if prey:
            target = min(prey, key=lambda p: dist(p, world.units[idle[0]].pos))
            world.attack_move(idle, target)
            self.note(world, f"raid towards {tuple(round(c) for c in target)}")

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
