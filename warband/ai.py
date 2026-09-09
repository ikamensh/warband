"""The computer opponent: keep the peasants busy, build in a sensible order,
train soldiers without pause, defend the base and attack in growing waves.

One :class:`Brain` per AI player thinks once a second of simulation
time; everything it does goes through :class:`World` commands, checked
with the matching ``can_*`` query first, so the model never raises here.
Each brain plays its race's army plan (see :data:`ARMY_PLANS`), shifted
towards counters of the enemy composition it can see. Strategic expansion
and military decisions retain their previous map knowledge.
Workers share the model's automatic policy, limited to known safe resources.
"""

from __future__ import annotations

import math
import random

from dataclasses import dataclass

from warband.model import Attack, AttackMove, Build, Building, Deposit, Harvest, Point, Pos, Repair, Unit, World, dist
from warband.races import RACES
from warband.rules import BUILDINGS, BuildingType, Difficulty, Race, Resource, UnitType, Upgrade

EXPAND_DISTANCE = 14.0  # a mine farther than this from the hall gets a hall of its own
DEFEND_RADIUS = 9.0
BUILD_MIN_DISTANCE = 2
BUILD_MAX_DISTANCE = 11
#: Shared upgrades first, then whatever arts the brain's race has (see :mod:`warband.races`).
RESEARCH_ORDER = (Upgrade.BLADES_1, Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.HORSES, Upgrade.PLUNDER, Upgrade.DEEP_MINING, Upgrade.LONGBOWS,
                  Upgrade.BLADES_2, Upgrade.ARMOR_2, Upgrade.ARROWS_2, Upgrade.SIEGE, Upgrade.BLESSING, Upgrade.BLOODLUST, Upgrade.REGROWTH,
                  Upgrade.BLASTING_POWDER)

#: Target shares of the army by skeleton type: FOOTMAN line, ARCHER ranged,
#: SCOUT raider, KNIGHT shock, CATAPULT siege, CLERIC healer.  Shares of types
#: the difficulty profile does not use (cavalry without tech, siege without
#: siege, healers without clerics) are dropped and the rest renormalised.
ARMY_PLANS: dict[Race, dict[UnitType, float]] = {
    Race.HUMAN: {UnitType.FOOTMAN: 0.35, UnitType.ARCHER: 0.30, UnitType.SCOUT: 0.05, UnitType.KNIGHT: 0.20,
                 UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.05},
    Race.ORC: {UnitType.FOOTMAN: 0.45, UnitType.ARCHER: 0.15, UnitType.SCOUT: 0.05, UnitType.KNIGHT: 0.30,
               UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.00},
    Race.ELF: {UnitType.FOOTMAN: 0.25, UnitType.ARCHER: 0.45, UnitType.SCOUT: 0.15, UnitType.KNIGHT: 0.10,
               UnitType.CATAPULT: 0.05, UnitType.CLERIC: 0.00},
    Race.DWARF: {UnitType.FOOTMAN: 0.40, UnitType.ARCHER: 0.35, UnitType.SCOUT: 0.00, UnitType.KNIGHT: 0.05,
                 UnitType.CATAPULT: 0.15, UnitType.CLERIC: 0.05},
}

_MELEE_TYPES = (UnitType.FOOTMAN, UnitType.SCOUT, UnitType.KNIGHT)


def _shift(plan: dict[UnitType, float], deltas: dict[UnitType, float]) -> None:
    """Move share between plan entries in place.  A shift whose types are not
    all in the plan is skipped; the survivors are clamped at zero and
    renormalised so the shares still add up to one."""
    if any(t not in plan for t in deltas):
        return
    for unit_type, delta in deltas.items():
        plan[unit_type] += delta
    for unit_type in plan:
        plan[unit_type] = max(0.0, plan[unit_type])
    total = sum(plan.values())
    if total > 0:
        for unit_type in plan:
            plan[unit_type] /= total


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
    repair: bool  # peasants mend damaged buildings once the fighting there is over


PROFILES: dict[Difficulty, Profile] = {
    Difficulty.EASY: Profile(peasants=7, think_every=2.0, first_wave=10, wave_growth=2, barracks=1, towers=0, tech=False, siege=False,
                             clerics=False, harass=False, reserve=1500, repair=False),
    # Normal is the coin flip against a plain, competent opening; it thinks slower, waits for a bigger first wave and skips siege.
    Difficulty.NORMAL: Profile(peasants=9, think_every=1.5, first_wave=10, wave_growth=3, barracks=2, towers=1, tech=True, siege=False,
                               clerics=False, harass=False, reserve=1000, repair=True),
    Difficulty.HARD: Profile(peasants=14, think_every=0.5, first_wave=8, wave_growth=4, barracks=3, towers=3, tech=True, siege=True,
                             clerics=True, harass=True, reserve=500, repair=True),
}


class Brain:
    def __init__(self, player: int, difficulty: Difficulty = Difficulty.NORMAL) -> None:
        self.player = player
        self.difficulty = difficulty
        self.profile = PROFILES[difficulty]
        self.next_think = 0.0
        self.wave = self.profile.first_wave
        self.waves_sent = 0
        self.attacking = False
        self.raiders: list[int] = []
        self.log: list[tuple[float, str]] = []  # (time, what) — the evidence of how it plays
        self._last_defend = 0  # threat size of the last logged "defend with" line
        self._wave_capped = False
        self._last_workforce_target: int | None = None
        self._plan_logged = False

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    def think(self, world: World, rng: random.Random) -> None:
        """Act if a think is due; call this every simulation step."""
        if world.time < self.next_think or not world.players[self.player].alive or world.winner is not None:
            return
        self.next_think = world.time + self.profile.think_every
        if not self._plan_logged:
            self._plan_logged = True
            self.note(world, f"army plan {world.players[self.player].race.value}")
        if not self._units(world):
            self._recover(world)
            return
        self._economy(world)
        self._repairs(world)
        self._construction(world, rng)
        self._training(world)
        self._research(world)
        self._military(world, rng)

    def _recover(self, world: World) -> None:
        """With no units left, spend refundable work on a recruit before resuming the normal plan."""
        buildings = world.player_buildings(self.player)
        if any(b.done and b.queue for b in buildings):
            return
        recruit = world.recovery_recruit(self.player)
        if recruit is None:
            return  # the next simulation step resolves surrender
        building, unit_type = recruit
        if world.can_train(building, unit_type) is not None:
            for b in buildings:
                if not b.done:
                    world.cancel_building(b.id)
                elif b.research is not None:
                    world.cancel_research(b.id)
        world.train(building.id, unit_type)
        self.note(world, f"recover with {unit_type.value}")

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
        from warband.worker_ai import assign_idle_workers

        assign_idle_workers(world, self.player)

    def _repairs(self, world: World) -> None:
        """One peasant mends the most damaged building, once no enemy is near it."""
        if not self.profile.repair or any(isinstance(p.order, Repair) for p in self._peasants(world)):
            return
        damaged = [b for b in world.player_buildings(self.player, done=True) if b.hp < b.max_hp * 0.7 and b.type is not BuildingType.GOLD_MINE]
        if not damaged:
            return
        b = min(damaged, key=lambda b: b.hp / b.max_hp)
        if world._nearest_enemy(self.player, b.center, 8.0) is not None:
            return
        spare = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Build)]
        if not spare:
            return
        peasant = min(spare, key=lambda p: dist(p.pos, b.center))
        world.repair([peasant.id], b.id)
        self.log.append((world.time, f"repair {b.type.value} at {b.hp}/{b.max_hp}"))

    # -- Construction -----------------------------------------------------------------

    def _construction(self, world: World, rng: random.Random) -> None:
        if any(not b.done for b in world.player_buildings(self.player)):
            return  # one site at a time; a builder in trouble would otherwise stall the whole plan
        peasants = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Repair)]
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

    def _workforce_target(self, world: World) -> int:
        """Peasants wanted: the profile plus five per extra hall, capped by supply
        left after reserving the next wave, never below the profile."""
        halls = len(world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True))
        base = self.profile.peasants + 5 * max(0, halls - 1)
        _used, cap = world.supply(self.player)
        return max(self.profile.peasants, min(base, cap - self.wave))

    def _training(self, world: World) -> None:
        player = self.player
        halls = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
        target = self._workforce_target(world)
        if target != self._last_workforce_target:
            self.note(world, f"workforce target {target}")
            self._last_workforce_target = target
        peasants = len(self._peasants(world))
        for hall in halls:
            if peasants >= target:
                break
            if not hall.queue and world.can_train(hall, UnitType.PEASANT) is None:
                world.train(hall.id, UnitType.PEASANT)
        hall = halls[0] if halls else None
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
                counts[choice] = counts.get(choice, 0) + 1
                self.note(world, f"train {choice.value}")

    def _army_targets(self, world: World) -> dict[UnitType, float]:
        """Target army shares for the brain's race, renormalised to what the
        difficulty profile uses and shifted towards counters of the visible
        enemy soldiers: raiders and shock against archer masses, line and
        ranged against knights."""
        plan = dict(ARMY_PLANS[world.players[self.player].race])
        if not self.profile.tech:
            plan.pop(UnitType.SCOUT, None)
            plan.pop(UnitType.KNIGHT, None)
        if not self.profile.siege:
            plan.pop(UnitType.CATAPULT, None)
        if not self.profile.clerics:
            plan.pop(UnitType.CLERIC, None)
        total = sum(plan.values())
        if total > 0:
            plan = {unit_type: share / total for unit_type, share in plan.items()}
        archers = melee = knights = 0
        for unit in world.units.values():
            if unit.player == self.player or unit.is_worker or unit.hidden or unit.hp <= 0:
                continue
            if not world.is_visible(self.player, unit.tile):
                continue
            if unit.type is UnitType.ARCHER:
                archers += 1
            if unit.type in _MELEE_TYPES:
                melee += 1
            if unit.type is UnitType.KNIGHT:
                knights += 1
        if archers > 0 and archers >= 2 * melee:
            _shift(plan, {UnitType.FOOTMAN: -0.15, UnitType.SCOUT: 0.075, UnitType.KNIGHT: 0.075})
        if knights >= 3:
            _shift(plan, {UnitType.SCOUT: -0.075, UnitType.KNIGHT: -0.075, UnitType.FOOTMAN: 0.075, UnitType.ARCHER: 0.075})
        return plan

    def _choose_unit(self, world: World, building: Building, counts: dict[UnitType, int]) -> UnitType | None:
        soldiers = sum(counts.values())
        if building.type is BuildingType.STABLES:
            if self.profile.harass and counts.get(UnitType.SCOUT, 0) < 2:
                return UnitType.SCOUT
        if building.type is BuildingType.WORKSHOP:
            threshold = 4 if world.players[self.player].race is Race.DWARF else 6
            if soldiers < threshold:
                return None
        targets = self._army_targets(world)
        best: UnitType | None = None
        best_gap = -math.inf
        for unit_type in targets:
            if unit_type not in building.info.trains:
                continue
            if world.can_train(building, unit_type) is None:
                share = counts.get(unit_type, 0) / soldiers if soldiers else 0.0
                if targets[unit_type] - share > best_gap:
                    best, best_gap = unit_type, targets[unit_type] - share
        return best

    def _research(self, world: World) -> None:
        if not self.profile.tech:
            return
        player = world.players[self.player]
        if player.gold < self.profile.reserve:
            return
        for upgrade in RESEARCH_ORDER:
            if upgrade in player.upgrades or not RACES[player.race].upgrade_allowed(upgrade):
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

    def _required_wave(self, world: World) -> int:
        """The army the brain waits for: the wave, bounded by what farms and halls can feed."""
        if self.waves_sent == 0:
            return self.profile.first_wave
        _used, cap = world.supply(self.player)
        bound = cap - len(self._peasants(world)) - 2
        floor = self.profile.first_wave // 2
        required = min(self.wave, bound)
        if required < floor:
            required = floor
        elif bound < self.wave and not self._wave_capped:
            self._wave_capped = True
            self.note(world, f"wave capped at {required}")
        return required

    def _enemy_soldiers(self, world: World) -> int:
        """Living enemy soldiers (units that are not workers) of alive players."""
        return sum(1 for u in world.units.values() if u.player != self.player and world.players[u.player].alive
                   and not u.is_worker and u.hp > 0 and not u.hidden)

    # -- Military --------------------------------------------------------------------

    def _military(self, world: World, rng: random.Random) -> None:
        army = self._army(world)
        if self.profile.harass:
            self._raid(world)
            army = [u for u in army if u.id not in self.raiders]
        threats = self._threats(world)
        if threats:
            threat = self._threat_point(world, threats)
            size = len(threats)
            if 2 * size >= len(army):
                self.attacking = False
                for unit in army:
                    if not isinstance(unit.order, Attack):
                        world.attack_move([unit.id], threat)
                if size != self._last_defend:
                    self.note(world, f"defend with {len(army)} against {size}")
                    self._last_defend = size
                return
            want = min(len(army), max(2, math.ceil(1.5 * size)))
            engaged_ids = {u.id for u in army if self._aimed_at(world, u, threat)}
            responders = len(engaged_ids)
            if responders < want:
                rest = [u for u in army if u.id not in engaged_ids]
                rest.sort(key=lambda u: dist(u.pos, threat))
                for unit in rest[: want - responders]:
                    world.attack_move([unit.id], threat)
                    responders += 1
            if size != self._last_defend:
                self.note(world, f"defend with {responders} against {size}")
                self._last_defend = size
            return
        self._last_defend = 0
        targets = self._enemy_targets(world)
        if not targets:
            return
        required = self._required_wave(world)
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
        if len(army) >= 3 and self._enemy_soldiers(world) < 3 and (
            self.profile.harass or (self.profile.tech and self.waves_sent > 0)
        ):
            self.attacking = True
            self.waves_sent += 1
            hall = self._hall(world)
            origin = hall.center if hall is not None else army[0].pos
            target = min(targets, key=lambda t: dist(t, origin))
            world.attack_move([u.id for u in army], target)
            self.note(world, f"attack with {len(army)} towards {tuple(round(c) for c in target)}")
            return
        if len(army) >= required:
            self.attacking = True
            self.waves_sent += 1
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
        """Enemy buildings of alive players; once those are gone, whatever enemy units remain."""
        buildings = [b.center for b in world.buildings.values() if b.player is not None and b.player != self.player
                     and world.players[b.player].alive]
        if buildings:
            return buildings
        return [u.pos for u in world.units.values() if u.player != self.player and world.players[u.player].alive]

    def _threats(self, world: World) -> list[Unit]:
        """Visible enemies within DEFEND_RADIUS of one of our buildings."""
        own = world.player_buildings(self.player)
        out: list[Unit] = []
        for unit in world.units.values():
            if unit.player == self.player or unit.hidden or not world.is_visible(self.player, unit.tile):
                continue
            for b in own:
                if dist(unit.pos, b.center) < DEFEND_RADIUS:
                    out.append(unit)
                    break
        return out

    def _threat_point(self, world: World, threats: list[Unit]) -> Point:
        """Where to answer: the position of the threat nearest to one of our buildings."""
        buildings = world.player_buildings(self.player)
        return min(threats, key=lambda u: min(dist(u.pos, b.center) for b in buildings)).pos

    @staticmethod
    def _aimed_at(world: World, unit: Unit, point: Point) -> bool:
        """Whether the soldier's current order already answers the threat point."""
        order = unit.order
        if isinstance(order, AttackMove):
            return dist(order.target, point) <= DEFEND_RADIUS
        if isinstance(order, Attack):
            target = world.units.get(order.target)
            pos = target.pos if target is not None else None
            if pos is None:
                building = world.buildings.get(order.target)
                pos = building.center if building is not None else None
            return pos is not None and dist(pos, point) <= DEFEND_RADIUS
        return False

    def _threat(self, world: World) -> Point | None:
        """The nearest visible enemy close to one of our buildings."""
        threats = self._threats(world)
        if not threats:
            return None
        return self._threat_point(world, threats)
