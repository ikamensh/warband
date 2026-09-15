"""A stronger computer opponent: one that never idles a building, never floats
a fortune, and picks its fights by comparing armies rather than counting them.

:class:`warband.ai.Brain` plays a reasonable game and is what the difficulty
settings ship. It also leaves most of the board on the table: it builds one
thing at a time, stops at fourteen peasants, waits for round gold thresholds,
and attacks whenever it has collected N soldiers no matter what N soldiers are
waiting for it. :class:`ProBrain` is the answer to each of those, and the
arena (:mod:`warband.arena`) is how the answers are checked.

Where the strength comes from, in the order it matters:

*Macro.* Workers are hired against the mines actually being worked, several
building sites run at once, farms go up before the supply block rather than
after it, and every military building keeps a queue. Gold sitting in the bank
is a unit that is not fighting.

*Engagement.* Armies are compared by ``dps × effective hit points`` — Lanchester's
square law, the reason a concentrated army beats a trickle — including the
towers covering whatever is being attacked. The brain attacks when that
comparison says it wins, retreats when it stops saying so, and does not care
how many soldiers it has in absolute terms.

*Focus fire.* Spreading damage over five enemies kills five of them at once
and takes their fire the whole time; concentrating it removes a shooter from
the fight immediately. The combat pass ranks the enemies in reach by threat
against fragility and points melee at the best of them. Archers are left on
their automatic orders while enemy melee is close, because the model's own
automatic handling kites for them (see ``World._ranged_retreat``) and an
explicit order would switch that off.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from warband.ai import ARMY_PLANS, RESEARCH_ORDER, _shift
from warband.model import Attack, Build, Building, Harvest, Point, Pos, Repair, Unit, World, dist
from warband.races import RACES
from warband.rules import BUILDINGS, BuildingType, Race, Resource, UnitType, Upgrade

_MELEE_TYPES = (UnitType.FOOTMAN, UnitType.SCOUT, UnitType.KNIGHT)
BUILD_MIN_DISTANCE = 2
BUILD_MAX_DISTANCE = 12


@dataclass(frozen=True)
class ProProfile:
    """The numbers the brain plays by. Every one of them is a knob the arena can turn."""

    name: str
    think_every: float = 0.4          # seconds of simulation between macro passes
    combat_every: float = 0.2         # …and between combat passes, which are cheaper and matter more
    workers_per_mine: int = 9         # peasants a worked mine supports
    lumber_share: float = 0.35        # workforce hired above the mine slots; who chops is the model's own policy
    max_workers: int = 26
    supply_slack: int = 4             # farms go up to keep this much headroom…
    supply_per_producer: float = 2.0  # …plus this much per military building
    max_sites: int = 2                # building sites at once
    surplus_gold: int = 1200          # money piling up past this unlocks optional buildings…
    surplus_lumber: int = 700         # …and so must lumber, which is what actually runs out
    lumber_floor: int = 150           # never spend the lumber the next few soldiers need
    max_halls: int = 3
    barracks_per_hall: int = 2
    attack_ratio: float = 1.15        # attack when my strength exceeds theirs by this
    retreat_ratio: float = 0.55       # break off once the push has lost this much of itself
    regroup_seconds: float = 45.0     # after a failed push, rebuild before trying again
    min_army: int = 10                # never walk out with less than this, whatever the comparison says
    tower_count: int = 2
    focus_fire: bool = True
    retreat_wounded: bool = False      # pull a soldier out at this much health and let it heal…
    retreat_hp: float = 0.25
    rejoin_hp: float = 0.7             # …and send it back once it is this whole again
    raid: bool = False                 # riders sent at the enemy's peasants
    raiders: int = 2
    reinforce_group: int = 1           # soldiers that must gather before walking to a fight together
    defend_with_workers: bool = True
    worker_defence_ratio: float = 2.0  # pull peasants when the threat outweighs the army this badly
    scout: bool = True
    scout_from: float = 50.0           # send the first pair of eyes out at this many seconds
    stale_seconds: float = 25.0        # a sighting older than this is not worth attacking on
    symmetry_prior: float = 1.0        # an unlooked-at opponent is assumed to be doing as well as we are
    expand: bool = True
    expand_early: bool = False        # a second mine before production has saturated
    reserve: int = 0                   # gold held back from unit production for buildings and research
    siege: bool = True
    clerics: bool = True


PRO = ProProfile("pro")

#: Variants used to find out which knob is actually carrying the strength.
#: Each differs from :data:`PRO` in one thing, so a ladder over all of them
#: attributes the difference rather than guessing at it.
_TRIALS = (
    replace(PRO, name="pro-eco", workers_per_mine=13, max_workers=32),
    replace(PRO, name="pro-prod", barracks_per_hall=4, surplus_gold=800, surplus_lumber=0),
    replace(PRO, name="pro-expand", expand_early=True),
    replace(PRO, name="pro-nofocus", focus_fire=False),
    replace(PRO, name="pro-noscout", scout=False),
    replace(PRO, name="pro-heal", retreat_wounded=True),
    replace(PRO, name="pro-raid", raid=True),
    replace(PRO, name="pro-group", reinforce_group=4),
)
PRO_PROFILES: dict[str, ProProfile] = {"pro": PRO, **{p.name: p for p in _TRIALS}}


# -- Force comparison ---------------------------------------------------------------

def _dps(world: World, unit: Unit) -> float:
    damage = world.damage_of(unit)
    if damage <= 0:
        # A cleric adds to a fight by undoing damage; count its healing as if it were damage.
        return world.heal_rate(unit) * 0.8 if unit.info.heal else 0.0
    return damage / unit.info.cooldown


def _effective_hp(world: World, unit: Unit) -> float:
    """Hit points inflated by armour, which is subtracted from every blow that lands."""
    return unit.hp * (1.0 + world.armor_of(unit) / 6.0)


def strength(world: World, units: list[Unit]) -> float:
    """How much fight a group has in it: ``sqrt(total dps × total effective hit points)``.

    Squaring it gives Lanchester's square-law combat power, ``N² × dps × hp``
    for a group of like units — twice the army is four times the force, which
    is why feeding soldiers in piecemeal loses. Comparing two of these numbers
    therefore ranks armies exactly as comparing the square law would, and the
    root keeps the ratios the brain is tuned against readable.
    """
    damage = sum(_dps(world, u) for u in units)
    body = sum(_effective_hp(world, u) for u in units)
    return math.sqrt(damage * body)


def _tower_strength(world: World, player: int, point: Point, radius: float = 9.0) -> float:
    """What the fortifications around *point* add to the defender."""
    damage = body = 0.0
    for building in world.buildings.values():
        if building.player in (None, player) or not building.done or building.hp <= 0:
            continue
        if not building.info.damage or dist(building.center, point) > radius:
            continue
        damage += world.damage_of(building) / building.info.cooldown
        body += building.hp
    return math.sqrt(damage * body)


class ProBrain:
    """One per AI player; ``think`` every simulation step, as with :class:`warband.ai.Brain`."""

    def __init__(self, player: int, profile: ProProfile = PRO) -> None:
        self.player = player
        self.profile = profile
        self.next_think = 0.0
        self.next_combat = 0.0
        self.attacking = False
        self.target: Point | None = None      # where the current push is aimed
        self.commit_strength = 0.0            # what the army was worth when it set out
        self.regroup_until = 0.0              # no new push before this, so a beaten army rebuilds
        self.scouts: list[int] = []
        self.raiders: list[int] = []
        self._hurt: set[int] = set()  # soldiers pulled out to heal
        self.log: list[tuple[float, str]] = []
        self._focus: dict[int, int] = {}      # unit id → the target it was last pointed at
        self._enemy_seen: dict[UnitType, float] = {}  # decaying memory of what the enemy fields
        self._last_seen_at = 0.0

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    # -- The pass ------------------------------------------------------------------

    def think(self, world: World, rng: random.Random) -> None:
        if not world.players[self.player].alive or world.winner is not None:
            return
        if world.time >= self.next_combat:
            self.next_combat = world.time + self.profile.combat_every
            self._combat(world)
        if world.time < self.next_think:
            return
        self.next_think = world.time + self.profile.think_every
        if not world.player_units(self.player):
            self._recover(world)
            return
        self._observe(world)
        self._economy(world)
        self._training(world)      # soldiers get first call on the bank…
        self._construction(world, rng)  # …and buildings buy what is left
        self._research(world)
        self._repairs(world)
        self._military(world)

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

    # -- Helpers -------------------------------------------------------------------

    def _units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def _peasants(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if u.is_worker]

    def _army(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if not u.is_worker]

    def _halls(self, world: World) -> list[Building]:
        return world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)

    def _hall(self, world: World) -> Building | None:
        halls = self._halls(world)
        return halls[0] if halls else None

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
        current: dict[UnitType, float] = {}
        for unit in self._enemies(world):
            if not unit.is_worker:
                current[unit.type] = current.get(unit.type, 0.0) + 1.0
        if current:
            self._last_seen_at = world.time
        fade = 0.99 ** (self.profile.think_every / 0.4)
        for unit_type in set(self._enemy_seen) | set(current):
            faded = self._enemy_seen.get(unit_type, 0.0) * fade
            self._enemy_seen[unit_type] = max(faded, current.get(unit_type, 0.0))

    # -- Economy -------------------------------------------------------------------

    def _worked_mines(self, world: World) -> list[Building]:
        """Mines with gold left inside reach of one of our halls."""
        halls = self._halls(world)
        if not halls:
            return []
        return [m for m in world.mines() if m.gold > 0 and min(dist(m.center, h.center) for h in halls) < 14.0]

    def _worker_target(self, world: World) -> int:
        """Peasants worth having: what the mines being worked can absorb, plus the woodcutters."""
        mines = max(1, len(self._worked_mines(world)))
        wanted = round(mines * self.profile.workers_per_mine / (1.0 - self.profile.lumber_share))
        return min(self.profile.max_workers, wanted)

    def _economy(self, world: World) -> None:
        from warband.worker_ai import assign_idle_workers

        assign_idle_workers(world, self.player)

    def _repairs(self, world: World) -> None:
        damaged = [b for b in world.player_buildings(self.player, done=True)
                   if b.hp < b.max_hp * 0.6 and b.type is not BuildingType.GOLD_MINE]
        if not damaged or any(isinstance(p.order, Repair) for p in self._peasants(world)):
            return
        target = min(damaged, key=lambda b: b.hp / b.max_hp)
        if world._nearest_enemy(self.player, target.center, 8.0) is not None:
            return
        spare = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Build)]
        if spare:
            world.repair([min(spare, key=lambda p: dist(p.pos, target.center)).id], target.id)

    # -- Construction ---------------------------------------------------------------

    def _wish_list(self, world: World) -> list[tuple[BuildingType, Point]]:
        """What to put up next, best first. Nothing here waits on a round number of gold."""
        player = self.player
        profile = self.profile
        halls = self._halls(world)
        hall = halls[0] if halls else None
        peasants = self._peasants(world)
        fallback = peasants[0].pos if peasants else (world.width / 2, world.height / 2)
        if hall is None:
            mine = world._nearest_mine(fallback, math.inf)
            return [(BuildingType.TOWN_HALL, mine.center if mine is not None else fallback)]

        have = lambda t: len(world.player_buildings(player, t, done=True))  # noqa: E731
        going_up = [b.type for b in world.player_buildings(player) if not b.done]
        count = lambda t: have(t) + going_up.count(t)  # noqa: E731
        anchor = hall.center
        wishes: list[tuple[BuildingType, Point]] = []

        used, cap = world.supply(player)
        producers = sum(count(t) for t in (BuildingType.BARRACKS, BuildingType.STABLES,
                                           BuildingType.WORKSHOP, BuildingType.CHURCH))
        headroom = profile.supply_slack + int(profile.supply_per_producer * producers)
        farms_coming = going_up.count(BuildingType.FARM) + going_up.count(BuildingType.TOWN_HALL)
        if cap - used + 4 * farms_coming < headroom:
            wishes.append((BuildingType.FARM, anchor))
        if count(BuildingType.BARRACKS) < 1:
            wishes.append((BuildingType.BARRACKS, anchor))
        if count(BuildingType.LUMBER_MILL) < 1:
            wishes.append((BuildingType.LUMBER_MILL, anchor))
        # Everything past here is optional, and optional buildings are what lose games:
        # each one is an army that was not trained. They are unlocked only once the
        # production already standing cannot keep up with the money coming in.
        expansion = self._expansion_site(world) if profile.expand else None
        if expansion is not None and profile.expand_early and count(BuildingType.TOWN_HALL) < profile.max_halls:
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if not self._producers_saturated(world):
            return wishes
        if expansion is not None and not profile.expand_early and count(BuildingType.TOWN_HALL) < profile.max_halls:
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if count(BuildingType.BLACKSMITH) < 1:
            wishes.append((BuildingType.BLACKSMITH, anchor))
        barracks_target = profile.barracks_per_hall * max(1, len(halls))
        if count(BuildingType.BARRACKS) < barracks_target:
            wishes.append((BuildingType.BARRACKS, anchor))
        if count(BuildingType.STABLES) < 1:
            wishes.append((BuildingType.STABLES, anchor))
        if profile.siege and have(BuildingType.BLACKSMITH) and count(BuildingType.WORKSHOP) < 1:
            wishes.append((BuildingType.WORKSHOP, anchor))
        if profile.clerics and count(BuildingType.CHURCH) < 1:
            wishes.append((BuildingType.CHURCH, anchor))
        if count(BuildingType.TOWER) < profile.tower_count and len(self._army(world)) >= 4:
            wishes.append((BuildingType.TOWER, self._front_point(world, hall)))
        return wishes

    def _producers_saturated(self, world: World) -> bool:
        """Whether the buildings already standing are the bottleneck rather than the bank.

        A barracks that is always mid-queue is worth another barracks; one that
        idles for want of gold is not, and neither is a stables next to it.
        """
        producers = [b for b in world.player_buildings(self.player, done=True)
                     if b.info.trains and b.type is not BuildingType.TOWN_HALL]
        if not producers:
            return False
        if any(not b.queue and b.research is None for b in producers):
            return False
        player = world.players[self.player]
        return player.gold >= self.profile.surplus_gold and player.lumber >= self.profile.surplus_lumber

    def _expansion_site(self, world: World) -> Point | None:
        """An unclaimed mine with gold in it, nearest to home."""
        halls = self._halls(world)
        if not halls:
            return None
        claimed = [h.center for h in world.player_buildings(self.player, BuildingType.TOWN_HALL)]
        best, best_distance = None, math.inf
        for mine in world.mines():
            if mine.gold <= 0 or min(dist(mine.center, c) for c in claimed) < 12.0:
                continue
            away = min(dist(mine.center, h.center) for h in halls)
            enemy_halls = [b.center for b in world.buildings.values()
                           if b.type is BuildingType.TOWN_HALL and b.player not in (None, self.player)]
            if enemy_halls and min(dist(mine.center, c) for c in enemy_halls) < away:
                continue  # not ours to take yet
            if away < best_distance:
                best, best_distance = mine.center, away
        return best

    def _construction(self, world: World, rng: random.Random) -> None:
        sites = [b for b in world.player_buildings(self.player) if not b.done]
        free = self.profile.max_sites - len(sites)
        if free <= 0:
            return
        builders = [p for p in self._peasants(world)
                    if not p.hidden and not isinstance(p.order, (Build, Repair))]
        if not builders:
            return
        for wanted, anchor in self._wish_list(world):
            if free <= 0 or not builders:
                break
            cost = BUILDINGS[wanted].cost
            if world.can_afford(self.player, cost) is not None:
                continue
            if world.players[self.player].lumber - cost.lumber < self.profile.lumber_floor:
                continue
            site = self._site(world, wanted, anchor, rng)
            if site is None:
                continue
            builder = min(builders, key=lambda p: dist(p.pos, (site[0] + 1.0, site[1] + 1.0)))
            world.build(builder.id, wanted, site)
            builders.remove(builder)
            free -= 1
            self.note(world, f"build {wanted.value} at {site}")

    def _site(self, world: World, building_type: BuildingType, anchor: Point, rng: random.Random) -> Pos | None:
        size = BUILDINGS[building_type].size
        ax, ay = int(anchor[0]), int(anchor[1])
        candidates: list[tuple[float, Pos]] = []
        for dy in range(-BUILD_MAX_DISTANCE, BUILD_MAX_DISTANCE + 1):
            for dx in range(-BUILD_MAX_DISTANCE, BUILD_MAX_DISTANCE + 1):
                if max(abs(dx), abs(dy)) < BUILD_MIN_DISTANCE + size:
                    continue
                candidates.append((math.hypot(dx, dy) + rng.random() * 2, (ax + dx - size // 2, ay + dy - size // 2)))
        candidates.sort()
        for _score, pos in candidates:
            if world.can_place(building_type, pos, self.player) is None and self._keeps_paths_open(world, pos, size):
                return pos
        return None

    def _keeps_paths_open(self, world: World, pos: Pos, size: int) -> bool:
        for b in world.player_buildings(self.player):
            gap_x = max(b.x - (pos[0] + size), pos[0] - (b.x + b.size), 0)
            gap_y = max(b.y - (pos[1] + size), pos[1] - (b.y + b.size), 0)
            if max(gap_x, gap_y) < 1:
                return False
        return True

    # -- Training -------------------------------------------------------------------

    def _training(self, world: World) -> None:
        player = self.player
        target = self._worker_target(world)
        peasants = len(self._peasants(world))
        halls = self._halls(world)
        for hall in halls:
            if peasants + sum(len(h.queue) for h in halls) >= target:
                break
            if len(hall.queue) < 2 and world.can_train(hall, UnitType.PEASANT) is None:
                world.train(hall.id, UnitType.PEASANT)
        army = self._army(world)
        counts = {t: sum(1 for u in army if u.type is t) for t in UnitType}
        for building in world.player_buildings(player, done=True):
            if not building.info.trains or building.type is BuildingType.TOWN_HALL:
                continue
            if building.rally is None and halls:
                world.set_rally(building.id, self._front_point(world, halls[0]))
            if building.research is not None or len(building.queue) >= 2:
                continue
            choice = self._choose_unit(world, building, counts)
            if choice is not None and world.can_train(building, choice) is None:
                world.train(building.id, choice)
                counts[choice] = counts.get(choice, 0) + 1

    def _army_targets(self, world: World) -> dict[UnitType, float]:
        """Shares of the army to aim for, shifted towards counters of what the enemy is remembered fielding."""
        plan = dict(ARMY_PLANS[world.players[self.player].race])
        if not self.profile.siege:
            plan.pop(UnitType.CATAPULT, None)
        if not self.profile.clerics:
            plan.pop(UnitType.CLERIC, None)
        total = sum(plan.values())
        if total > 0:
            plan = {t: share / total for t, share in plan.items()}
        seen = self._enemy_seen
        archers = seen.get(UnitType.ARCHER, 0.0)
        knights = seen.get(UnitType.KNIGHT, 0.0)
        melee = sum(seen.get(t, 0.0) for t in _MELEE_TYPES)
        if archers > 0 and archers >= 2 * melee:
            _shift(plan, {UnitType.FOOTMAN: -0.15, UnitType.SCOUT: 0.075, UnitType.KNIGHT: 0.075})
        if knights >= 3:
            _shift(plan, {UnitType.SCOUT: -0.075, UnitType.KNIGHT: -0.075, UnitType.FOOTMAN: 0.075, UnitType.ARCHER: 0.075})
        return plan

    def _choose_unit(self, world: World, building: Building, counts: dict[UnitType, int]) -> UnitType | None:
        soldiers = sum(counts.values())
        if building.type is BuildingType.STABLES and self.profile.scout and counts.get(UnitType.SCOUT, 0) < 1:
            return UnitType.SCOUT
        targets = self._army_targets(world)
        best: UnitType | None = None
        best_gap = -math.inf
        for unit_type in targets:
            if unit_type not in building.info.trains or world.can_train(building, unit_type) is not None:
                continue
            share = counts.get(unit_type, 0) / soldiers if soldiers else 0.0
            if targets[unit_type] - share > best_gap:
                best, best_gap = unit_type, targets[unit_type] - share
        return best

    def _research(self, world: World) -> None:
        player = world.players[self.player]
        if player.gold < self.profile.reserve:
            return
        for upgrade in RESEARCH_ORDER:
            if upgrade in player.upgrades or not RACES[player.race].upgrade_allowed(upgrade):
                continue
            for building in world.player_buildings(self.player, done=True):
                if upgrade in building.info.researches and world.can_research(building, upgrade) is None:
                    world.research(building.id, upgrade)
                    return

    # -- Military -------------------------------------------------------------------

    def _front_point(self, world: World, hall: Building) -> Point:
        """Where the army waits: between the hall and whoever is coming."""
        enemy_halls = [b.center for b in world.buildings.values()
                       if b.player not in (None, self.player) and world.players[b.player].alive]
        towards = min(enemy_halls, key=lambda c: dist(c, hall.center)) if enemy_halls else (world.width / 2, world.height / 2)
        hx, hy = hall.center
        away = dist((hx, hy), towards) or 1.0
        return (hx + (towards[0] - hx) / away * 6, hy + (towards[1] - hy) / away * 6)

    def _threats(self, world: World) -> list[Unit]:
        own = world.player_buildings(self.player)
        if not own:
            return []
        out = []
        for unit in self._enemies(world):
            if unit.info.damage == 0 and unit.is_worker:
                continue
            if any(dist(unit.pos, b.center) < 9.0 for b in own):
                out.append(unit)
        return out

    def _military(self, world: World) -> None:
        army = self._army(world)
        self._send_scout(world, army)
        busy = set(self.scouts) | set(self._raid(world, army))
        army = [u for u in army if u.id not in busy]
        threats = self._threats(world)
        if threats:
            self._defend(world, army, threats)
            return
        targets = self._attack_targets(world)
        if not targets:
            return
        hall = self._hall(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if origin is None:
            return
        mine = strength(world, army)
        if self.attacking:
            # Judge a push by how it is going, not by how big the enemy looks from
            # where the army happens to be standing. Estimating the defence again
            # each pass walks the army home the moment a tower comes into view, and
            # then straight back out once it is out of view again; an army that
            # oscillates like that never fights at all.
            if len(army) < 3 or mine < self.profile.retreat_ratio * self.commit_strength:
                self.attacking = False
                self.regroup_until = world.time + self.profile.regroup_seconds
                self.note(world, f"withdraw at {mine:.0f} of {self.commit_strength:.0f}")
                if hall is not None:
                    world.move([u.id for u in army], self._front_point(world, hall))
                return
            if self.target is None or not self._still_there(world, self.target):
                self.target = min(targets, key=lambda t: dist(t, origin))
            # Reinforcements walk to the same place, so the push grows instead of
            # trickling. A soldier crossing the map alone arrives alone and dies
            # alone, so the ones still at home wait until there are enough to travel
            # together; the ones already at the front simply rejoin the fight.
            idle = [u for u in army if not u.orders]
            arrived = [u.id for u in idle if dist(u.pos, self.target) <= 12.0]
            if arrived:
                world.attack_move(arrived, self.target)
            waiting = [u for u in idle if dist(u.pos, self.target) > 12.0]
            if len(waiting) >= self.profile.reinforce_group:
                world.attack_move([u.id for u in waiting], self.target)
            elif waiting and hall is not None:
                point = self._front_point(world, hall)
                world.move([u.id for u in waiting if dist(u.pos, point) > 4.0], point)
            return
        if world.time < self.regroup_until or len(army) < self.profile.min_army:
            self._gather(world, army, hall)
            return
        target = min(targets, key=lambda t: dist(t, origin))
        theirs = self._defenders_near(world, target)
        if mine >= self.profile.attack_ratio * theirs:
            self.attacking = True
            self.target = target
            self.commit_strength = mine
            self.note(world, f"attack {len(army)} strong ({mine:.0f} against {theirs:.0f})")
            world.attack_move([u.id for u in army], target)
        else:
            self._gather(world, army, hall)

    def _still_there(self, world: World, point: Point) -> bool:
        """Whether anything of the enemy's is still standing where the push was aimed."""
        return any(b.hp > 0 and b.player not in (None, self.player) and dist(b.center, point) < 3.0
                   for b in world.buildings.values())

    def _army_centre(self, world: World, army: list[Unit]) -> Point | None:
        if not army:
            return None
        return (sum(u.x for u in army) / len(army), sum(u.y for u in army) / len(army))

    def _gather(self, world: World, army: list[Unit], hall: Building | None) -> None:
        """Wait in one place. An army that trickles forward is an army that loses twice."""
        if hall is None:
            return
        point = self._front_point(world, hall)
        stragglers = [u.id for u in army if not u.orders and dist(u.pos, point) > 4.0]
        if stragglers:
            world.move(stragglers, point)

    def _defenders_near(self, world: World, point: Point, radius: float = 12.0) -> float:
        """What is waiting at *point*: the soldiers we can see, the towers covering it,
        and half of whatever the enemy was last seen with but is currently hidden.

        Strength is linear in the number of like units, so an unseen soldier can
        simply be priced at what one of ours is worth.
        """
        near = [u for u in self._enemies(world) if not u.is_worker and dist(u.pos, point) < radius]
        hidden = max(0.0, sum(self._enemy_seen.values()) - len(near))
        seen = (strength(world, near) + _tower_strength(world, self.player, point)
                + 0.5 * hidden * self._typical_soldier(world))
        if world.time - self._last_seen_at > self.profile.stale_seconds:
            # Nobody has looked at them lately. An enemy nobody has looked at is not
            # an enemy of zero strength — assuming so is how an army of ten walks
            # into a defended base and dies. Until a scout says otherwise, credit
            # them with a game as good as ours, which means no attack goes out on
            # no information at all.
            seen = max(seen, self.profile.symmetry_prior * strength(world, self._army(world)))
        return seen

    def _typical_soldier(self, world: World) -> float:
        """What one average soldier of ours is worth, as a yardstick for unseen enemies."""
        army = [u for u in self._army(world) if u.info.damage > 0]
        return strength(world, army) / len(army) if army else 20.0

    def _attack_targets(self, world: World) -> list[Point]:
        """What is worth walking to: production first, then anything of theirs."""
        wanted = (BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,
                  BuildingType.CHURCH, BuildingType.TOWN_HALL)
        buildings = [b for b in world.buildings.values()
                     if b.player is not None and b.player != self.player and world.players[b.player].alive and b.hp > 0]
        production = [b.center for b in buildings if b.type in wanted]
        if production:
            return production
        if buildings:
            return [b.center for b in buildings]
        return [u.pos for u in world.units.values()
                if u.player != self.player and u.hp > 0 and world.players[u.player].alive]

    def _defend(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        point = min(threats, key=lambda u: min(dist(u.pos, b.center)
                                               for b in world.player_buildings(self.player))).pos
        self.attacking = False
        world.attack_move([u.id for u in army if not isinstance(u.order, Attack)], point)
        if not self.profile.defend_with_workers:
            return
        incoming = strength(world, threats)
        ours = strength(world, army) + _tower_strength(world, self.player, point)
        if ours * self.profile.worker_defence_ratio < incoming:
            return  # hopeless: peasants would only feed it
        if ours >= incoming:
            helpers = [p for p in self._peasants(world)
                       if not p.hidden and dist(p.pos, point) < 12.0 and p.carrying is None][:6]
            if helpers:
                world.attack_move([p.id for p in helpers], point)

    def _send_scout(self, world: World, army: list[Unit]) -> None:
        """Keep one pair of eyes on the enemy: a rider if we have one, a peasant if not.

        Everything the brain decides about attacking rests on knowing what is
        over there, so a scout is cheap at almost any price — and one peasant
        is a much smaller loss than the army that would otherwise walk in blind.
        """
        if not self.profile.scout or world.time < self.profile.scout_from:
            return
        self.scouts = [i for i in self.scouts if i in world.units]
        if not self.scouts:
            riders = [u for u in army if u.type is UnitType.SCOUT]
            if riders:
                self.scouts = [riders[0].id]
            else:
                spare = [p for p in self._peasants(world)
                         if not p.hidden and p.carrying is None and not isinstance(p.order, (Build, Repair))]
                if len(spare) > 3:
                    self.scouts = [spare[-1].id]
        targets = [b.center for b in world.buildings.values()
                   if b.type is BuildingType.TOWN_HALL and b.player not in (None, self.player)
                   and world.players[b.player].alive]
        if not targets:
            return
        for scout_id in self.scouts:
            scout = world.units[scout_id]
            if scout.orders:
                continue
            # Circle the enemy base rather than standing in it, so the sighting stays fresh.
            centre = min(targets, key=lambda c: dist(c, scout.pos))
            angle = (world.time / 12.0) % (2 * math.pi)
            ring = (centre[0] + 7.0 * math.cos(angle), centre[1] + 7.0 * math.sin(angle))
            world.move([scout_id], (min(max(ring[0], 1.0), world.width - 1.0),
                                    min(max(ring[1], 1.0), world.height - 1.0)))

    # -- Combat ----------------------------------------------------------------------

    def _withdraw_if_hurt(self, world: World, unit: Unit) -> bool:
        """Walk a nearly-dead soldier out of reach. A body that lives is damage next fight.

        Returns whether the unit is out of the fight, so the caller stops
        giving it targets.
        """
        profile = self.profile
        if unit.id in self._hurt:
            if unit.hp >= profile.rejoin_hp * unit.max_hp:
                self._hurt.discard(unit.id)
                return False
            return True
        if unit.hp >= profile.retreat_hp * unit.max_hp:
            return False
        if not any(e.info.damage and dist(e.pos, unit.pos) < world.range_of(e) + 2.0 for e in self._enemies(world)):
            return False  # nothing is shooting at it; no reason to leave
        hall = self._hall(world)
        if hall is None:
            return False
        self._hurt.add(unit.id)
        self._focus.pop(unit.id, None)
        world.move([unit.id], hall.center)
        return True

    def _raid(self, world: World, army: list[Unit]) -> list[int]:
        """Riders sent at the peasants. Economy damage costs the enemy the whole game,
        not just the units lost, and the army never misses two scouts."""
        if not self.profile.raid:
            return []
        self.raiders = [i for i in self.raiders if i in world.units]
        spare = [u for u in army if u.type is UnitType.SCOUT and u.id not in self.raiders]
        while len(self.raiders) < self.profile.raiders and spare:
            self.raiders.append(spare.pop().id)
        prey = [u.pos for u in world.units.values()
                if u.player != self.player and u.is_worker and not u.hidden and u.hp > 0
                and world.players[u.player].alive]
        if not prey:
            return list(self.raiders)
        for raider_id in self.raiders:
            rider = world.units[raider_id]
            if rider.orders:
                continue
            world.attack_move([raider_id], min(prey, key=lambda p: dist(p, rider.pos)))
        return list(self.raiders)

    def _threat_value(self, world: World, unit: Unit) -> float:
        """What killing this one is worth: what it does to us, against how hard it is to kill."""
        output = _dps(world, unit)
        if unit.is_worker:
            output += 1.5  # a peasant is not dangerous, but it is the enemy's income
        return output / max(1.0, _effective_hp(world, unit))

    def _combat(self, world: World) -> None:
        """Point melee at the enemy worth killing most, and keep it pointed there."""
        army = [u for u in world.player_units(self.player) if not u.is_worker and u.info.damage > 0]
        if not army:
            return
        enemies = self._enemies(world)
        if not enemies:
            self._focus.clear()
            self._hurt.clear()
            return
        if self.profile.retreat_wounded:
            army = [u for u in army if not self._withdraw_if_hurt(world, u)]
        if not self.profile.focus_fire:
            return
        for unit in army:
            reach = world.range_of(unit) + 2.5
            in_reach = [e for e in enemies if dist(e.pos, unit.pos) <= reach]
            if not in_reach:
                continue
            if unit.info.ranged and any(e.info.melee and dist(e.pos, unit.pos) < 2.5 for e in in_reach):
                continue  # leave the model's own kiting alone; an explicit order would switch it off
            best = max(in_reach, key=lambda e: self._threat_value(world, e))
            if self._focus.get(unit.id) == best.id and isinstance(unit.order, Attack) and unit.order.target == best.id:
                continue  # already on it; re-issuing would restart the approach
            world.attack([unit.id], best.id)
            self._focus[unit.id] = best.id


def register_agents(register) -> None:
    """Add every profile here to an arena registry."""
    for name, profile in PRO_PROFILES.items():
        register(name, lambda player, p=profile: ProBrain(player, p))
