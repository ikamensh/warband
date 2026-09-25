"""Each race's own unit in a computer player's hands (WB-068): when it is worth buying, and what it is for once it stands.

A brain buys its race's unit only when what the side knows says it is the answer, never as the next soldier of a plan:

| unit | bought when (the side's own sightings and memory) | used for |
|---|---|---|
| Gryphon Rider | the rival fields catapults or flyers and is not shooter-heavy, or its army is shooter-light | hunting flyers, catapults and lone shooters, out of towers' and massed shooters' reach |
| Goblin Sapper | two or more rival towers are known, or a rival hall within :data:`SAPPER_REACH` | a tower or hall the army is pushing at, or one near that nobody guards, run at by the way clear of soldiers; a knot of rivals on top of it |
| Treant | a forest route to the rival is shorter than the walk round (:func:`forest_route_pays`) | a push's flank: the rival building by the most trees, reached through the wood |
| Rune Golem | the rival's army is melee-heavy | the thickest knot of rival melee within reach |

Everything here reads what the seat knows: the rivals in sight (``World.is_visible``), the buildings it remembers as it
last saw them (``World.worker_knowledge``: one razed out of sight still stands to it, and a unit sent at it walks to
where it remembers it until it is seen again) and a brain's own count of what it has seen (*seen*: the most of each
kind seen at once).  So the brain decides the same on a seat's snapshot online as on the whole world.  The ground a
forest route is planned on is the map's grid (:func:`forest_route_pays`), as every brain's site search reads it.
Both kinds of brain use it: Medium (``ai.Brain``) with what it sees now, Hard, Master and the bred postures
(``pro_ai.ProBrain``) with their memory.  A unit it is steering is out of the brain's army for that pass (:meth:`
Commander.step` says which), so a push or a defence never takes it off its errand.
"""

from __future__ import annotations

from typing import Final

from warband.sim import path as pathing
from warband.sim.model import Attack, Build, Building, Move, Point, Unit, World, dist, int_sum, plain_sum, rect_gap, tile_center
from warband.sim.rules import OWN_UNITS, UNITS, BuildingType, Terrain, UnitType, Upgrade
from warband.sim.worker_knowledge import KnownBuilding

#: Tiles from our hall a known rival hall may stand for sappers to be worth buying against it alone.
SAPPER_REACH: Final = 45.0
#: Of the rival soldiers seen, the share that shoots (strikes the air) above which gryphons are not bought, and below
#: which (with :data:`SHOOTER_LIGHT_ARMY` of them seen) the army is shooter-light and gryphons are bought whatever it has.
SHOOTER_HEAVY: Final = 0.35
SHOOTER_LIGHT: Final = 0.15
SHOOTER_LIGHT_ARMY: Final = 5
#: Of the rival soldiers seen, the melee share (with at least :data:`MELEE_ARMY` melee seen) that buys golems.
MELEE_HEAVY: Final = 0.6
MELEE_ARMY: Final = 5
#: A forest route pays when it is this much of the walk round, or less.
FOREST_SHORTCUT: Final = 0.85
#: Tiles round a gryphon's prey within which other rival shooters make it no lone shooter.
LONE: Final = 5.0
#: Tiles a sapper keeps from a rival soldier on its way; nearer, it turns back to our own side.
INTERCEPT: Final = 3.5
#: Tiles a sapper runs at a building no push escorts: a hall across the map is a sapper met on the way.
SAP_RUN: Final = 15.0
#: Rival shooters near a mark that make it no place for a gryphon.
MASSED: Final = 3
#: Rival units round one of them that make a knot worth a golem's slam, or a sapper's keg.
KNOT: Final = 3
#: Tiles a walk to a remembered building may aim off its spot before it is given again (``ai.REDIRECT``'s).
REDIRECT: Final = 2.0
#: A gryphon this hurt hunts no more.
GRYPHON_HOME_HP: Final = 0.4
#: Soldiers a side has before it buys its own unit at all: a centrepiece for an army, never an opening.  With fewer,
#: the unit is soldiers the first clash does not have -- unless the gold is idle anyway: a side with :data:`IDLE_GOLD`
#: in the bank is not short of soldiers for want of money (Medium banks that much for minutes; Master's opening passes
#: 3000 for a moment on its way to its next buildings).  What the unit waits for -- the Keep, the building that trains
#: it -- a side invests in from idle gold alone: Master's orcs, raising the Keep, a smith and a siege yard for sappers
#: from an army's money, lost Master more matches than their sappers won them (docs/balance.md, WB-068).
UNIQUE_ARMY: Final = 8
IDLE_GOLD: Final = 6000


def own_unit(world: World, player: int) -> UnitType | None:
    """The unit only *player*'s race fields."""
    return OWN_UNITS.get(world.race_of(player))


def rival_buildings(world: World, player: int) -> list[KnownBuilding]:
    """The rival buildings *player* remembers, as it last saw them: where each stands, its kind, whether it shot and
    whether it had fallen to a ruin.  One razed while nobody of the side was looking still stands to it."""
    return [record for record in world.worker_knowledge[player].buildings.values()
            if record.player is not None and record.player != player and record.player < world.seats
            and world.players[record.player].alive]


def _shooter(unit_type: UnitType) -> bool:
    info = UNITS[unit_type]
    return info.strikes_air and not info.heal


def wanted(world: World, player: int, seen: dict[UnitType, float], route_pays: bool) -> bool:
    """Whether *player*'s own unit is the answer to what it knows: *seen* the most of each rival kind it has seen at
    once, *route_pays* whether a forest route reaches the rival (:func:`forest_route_pays`, asked for the treant)."""
    unit = own_unit(world, player)
    soldiers = plain_sum(n for t, n in seen.items() if t is not UnitType.PEASANT and UNITS[t].soldier)
    shooters = plain_sum(n for t, n in seen.items() if _shooter(t))
    if unit is UnitType.GRYPHON:
        share = shooters / soldiers if soldiers else 0.0
        prey = seen.get(UnitType.CATAPULT, 0.0) + plain_sum(n for t, n in seen.items() if UNITS[t].flying)
        return (prey >= 1.0 and share <= SHOOTER_HEAVY) or (soldiers >= SHOOTER_LIGHT_ARMY and share <= SHOOTER_LIGHT)
    if unit is UnitType.SAPPER:
        towers = halls = 0
        home = world.player_buildings(player, BuildingType.TOWN_HALL)
        for record in rival_buildings(world, player):
            if record.type is BuildingType.TOWER:
                towers += 1
            elif record.type is BuildingType.TOWN_HALL and any(dist(record.center, hall.center) <= SAPPER_REACH for hall in home):
                halls += 1
        return towers >= 2 or halls >= 1
    if unit is UnitType.TREANT:
        return route_pays
    if unit is UnitType.RUNE_GOLEM:
        melee = plain_sum(n for t, n in seen.items() if UNITS[t].melee and t is not UnitType.PEASANT)
        return melee >= MELEE_ARMY and melee >= MELEE_HEAVY * soldiers
    return False


def forest_route_pays(world: World, start: Point, goal: Point) -> bool:
    """Whether a forest walker's route from *start* to *goal* is :data:`FOREST_SHORTCUT` of a walker's or shorter, or
    reaches where a walker's cannot: the wood is a road to the rival.  Both are planned on the static grids, the
    walker's on the map's and the forest walker's with its trees open."""
    width, height = world.width, world.height
    a, b = (int(start[0]), int(start[1])), (int(goal[0]), int(goal[1]))
    walker = pathing.find_path_grid(a, b, world._blocked, width, height, max_expansions=world.path_budget)
    through = pathing.find_path_grid(a, b, world.forest_ground(), width, height, max_expansions=world.path_budget)
    if not through or through[-1] != b:
        return False
    if not walker or walker[-1] != b:
        return True
    return _length(through) <= FOREST_SHORTCUT * _length(walker)


def _length(route: list[tuple[int, int]]) -> float:
    return plain_sum(dist(tile_center(p), tile_center(q)) for p, q in zip(route, route[1:]))


class Commander:
    """What a brain does with its own units once they stand; one per brain, as it keeps its errands between passes."""

    def __init__(self) -> None:
        self.errands: dict[int, int] = {}  # a unit's id -> the id of what it was sent at
        self.route: dict[tuple[int, int], bool] = {}  # (our hall's id, the rival building's id) -> forest_route_pays

    def route_pays(self, world: World, player: int) -> bool:
        """:func:`forest_route_pays` from our first hall to the nearest rival building we know, worked out once a pair."""
        halls = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
        known = rival_buildings(world, player)
        if not halls or not known:
            return False
        hall = halls[0]
        record = min(known, key=lambda r: (dist(r.center, hall.center), r.id))
        key = (hall.id, record.id)
        pays = self.route.get(key)
        if pays is None:
            start = world.free_tile_near(hall.rect)
            end = world.free_tile_near(record.rect, prefer=hall.center)
            pays = self.route[key] = start is not None and end is not None and forest_route_pays(world, tile_center(start), tile_center(end))
        return pays

    def answer(self, world: World, player: int, seen: dict[UnitType, float], *, invest: bool = False) -> bool:
        """Whether *player*'s own unit is its answer now: what the side knows says so (:func:`wanted`), and it has an
        army of :data:`UNIQUE_ARMY` to be the centrepiece of or :data:`IDLE_GOLD` in the bank; to *invest* in what the
        unit waits for, the idle gold alone."""
        unit = own_unit(world, player)
        if unit is None:
            return False
        idle = world.players[player].gold >= IDLE_GOLD
        if not idle and (invest or int_sum(1 for u in world.units.values() if u.player == player and not u.is_worker
                                           and u.info.soldier and not u.info.blast) < UNIQUE_ARMY):
            return False
        return wanted(world, player, seen, unit is UnitType.TREANT and self.route_pays(world, player))

    def wish(self, world: World, player: int, building: Building, seen: dict[UnitType, float]) -> UnitType | None:
        """The race's own unit, when *building* trains it, the side has room for another under its limit and has what it
        waits for (:meth:`World.lacks_for`), and it is the answer (:meth:`answer`)."""
        unit = own_unit(world, player)
        if (unit is None or unit not in building.info.trains or world.lacks_for(player, unit) is not None
                or world.at_limit(player, unit) is not None):
            return None
        return unit if self.answer(world, player, seen) else None

    def waits_for(self, world: World, player: int, seen: dict[UnitType, float]) -> tuple[Upgrade, ...]:
        """What the race's own unit waits for that *player* has not researched (the Keep), when it is the answer
        (:meth:`answer`): a brain researches it first, from what it can spend, and keeps the hall free of recruits once
        it can pay, or a hall always training peasants would never be raised.  Nothing is held for it: the Keep's price
        held from the soldiers cost the orcs more matches than their sappers won (docs/balance.md, WB-068)."""
        unit = own_unit(world, player)
        if unit is None:
            return ()
        missing = tuple(needed for needed in UNITS[unit].requires if needed not in world.players[player].upgrades)
        return missing if missing and self.answer(world, player, seen, invest=True) else ()

    def building(self, world: World, player: int, seen: dict[UnitType, float]) -> BuildingType | None:
        """The building the race's own unit is trained at, when it is the answer and *player* has none standing, going
        up or ordered: a brain puts it up, or the answer would never come."""
        unit = own_unit(world, player)
        if unit is None:
            return None
        kind = UNITS[unit].trained_at
        if world.player_buildings(player, kind) or any(isinstance(order, Build) and order.type is kind
                                                        for u in world.player_units(player) if u.is_worker for order in u.orders):
            return None
        return kind if self.answer(world, player, seen, invest=True) else None

    @staticmethod
    def kept_free(world: World, player: int, first: tuple[Upgrade, ...]) -> set[int]:
        """The ids of *player*'s buildings that research one of *first* (the Keep: its halls): a brain queues no recruit
        at them while it can pay for it, or a hall always training peasants would never be raised."""
        if not first:
            return set()
        return {b.id for b in world.player_buildings(player, done=True) if any(u in b.info.researches for u in first)}

    def step(self, world: World, player: int, units: list[Unit], push: Point | None) -> set[int]:
        """Steer *player*'s own units among *units* for this pass; the ids of those on an errand, which the brain's army
        leaves alone.  *push* is where the brain's army is attacking, or None while it is not."""
        army = [u for u in units if u.type in _OWN and not u.hidden]
        units_by_id = {u.id: u for u in army}
        self.errands = {uid: target for uid, target in self.errands.items() if uid in units_by_id and _known(world, player, target)}
        busy: set[int] = set()
        for unit in army:
            if unit.type is UnitType.GRYPHON and self._hunt(world, player, unit):
                busy.add(unit.id)
            elif unit.type is UnitType.SAPPER:
                self._sap(world, player, unit, push)
                busy.add(unit.id)  # a sapper is never the army's: its blow is its end
            elif unit.type is UnitType.TREANT and push is not None and self._flank(world, player, unit, push):
                busy.add(unit.id)
            elif unit.type is UnitType.RUNE_GOLEM and self._slam(world, player, unit):
                busy.add(unit.id)
        return busy

    # -- The gryphon ---------------------------------------------------------------------------------------------------

    def _hunt(self, world: World, player: int, gryphon: Unit) -> bool:
        """Hunt a flyer, a catapult or a lone shooter in sight, clear of the towers the side knows and of massed shooters;
        True while it hunts.  Hurt below :data:`GRYPHON_HOME_HP`, it hunts no more and is the brain's to care for, as
        any wounded soldier is (``ProBrain._withdraw_if_hurt``)."""
        if gryphon.hp < GRYPHON_HOME_HP * gryphon.max_hp:
            self.errands.pop(gryphon.id, None)
            return False  # the brain's own care for its wounded takes it from here
        current = self.errands.get(gryphon.id)
        if current is not None and isinstance(gryphon.order, Attack) and gryphon.order.target == current:
            return True
        towers = [record for record in rival_buildings(world, player) if record.threat_range > 0]  # standing, armed, as last seen
        best: Unit | None = None
        best_d = 0.0
        for enemy in world.units.values():
            if (enemy.player == player or enemy.player >= world.seats or enemy.hidden or enemy.hp <= 0
                    or not world.is_visible(player, enemy.tile)):
                continue
            if not (enemy.flying or enemy.type is UnitType.CATAPULT or (_shooter(enemy.type) and self._lone(world, player, enemy))):
                continue
            if self._massed(world, player, enemy) or any(rect_gap(enemy.pos, tower.rect) <= tower.threat_range for tower in towers):
                continue
            d = dist(gryphon.pos, enemy.pos)
            if best is None or d < best_d or (d == best_d and enemy.id < best.id):
                best, best_d = enemy, d
        if best is None:
            self.errands.pop(gryphon.id, None)
            return False
        world.attack([gryphon.id], best.id)
        self.errands[gryphon.id] = best.id
        return True

    @staticmethod
    def _lone(world: World, player: int, shooter: Unit) -> bool:
        """Whether *player* sees no other shooter of *shooter*'s side within :data:`LONE` of it."""
        return not any(other is not shooter and other.player == shooter.player and not other.hidden and other.hp > 0
                       and _shooter(other.type) and dist(other.pos, shooter.pos) <= LONE and world.is_visible(player, other.tile)
                       for other in world.units_near(shooter.pos, LONE))

    @staticmethod
    def _massed(world: World, player: int, mark: Unit) -> bool:
        return int_sum(1 for other in world.units_near(mark.pos, LONE)
                       if other.player != player and other.player < world.seats and not other.hidden and other.hp > 0
                       and _shooter(other.type) and world.is_visible(player, other.tile)) >= MASSED

    # -- The sapper ----------------------------------------------------------------------------------------------------

    def _sap(self, world: World, player: int, sapper: Unit, push: Point | None) -> None:
        """Run at a rival tower or hall: one the army is pushing at, or one within :data:`SAP_RUN` that no rival soldier
        in sight stands by and the way to which passes none; turn back to our side when a rival soldier comes within
        :data:`INTERCEPT` of it short of its mark, away from the push.  A knot of rivals on top of it (:data:`KNOT`,
        with no more than one of our own there) it takes with it: better that than dying for nothing."""
        soldiers = [e for e in world.units.values()
                    if e.player != player and e.player < world.seats and not e.hidden and e.hp > 0 and e.info.soldier
                    and not e.flying and world.is_visible(player, e.tile)]
        reach = sapper.info.blast
        knot = [e for e in soldiers if dist(e.pos, sapper.pos) - e.radius <= reach]
        own = int_sum(1 for u in world.units_near(sapper.pos, reach + 1.0)
                      if u.player == player and u is not sapper and not u.flying and dist(u.pos, sapper.pos) - u.radius <= reach)
        if len(knot) >= KNOT and own <= 1:
            mark = min(knot, key=lambda e: (dist(e.pos, sapper.pos), e.id))
            if not (isinstance(sapper.order, Attack) and sapper.order.target == mark.id):
                world.attack([sapper.id], mark.id)
            self.errands[sapper.id] = mark.id
            return
        current = self.errands.get(sapper.id)
        if current is not None:
            mark_building = world.worker_knowledge[player].buildings.get(current)
            if mark_building is not None and _going_at(sapper, mark_building):
                near = rect_gap(sapper.pos, mark_building.rect)
                caught = any(dist(e.pos, sapper.pos) <= INTERCEPT for e in soldiers)
                if not (caught and near > INTERCEPT and (push is None or dist(sapper.pos, push) > 8.0)):
                    _go_at(world, player, sapper, mark_building)  # at the building itself once the side sees it
                    return  # on its way, or too near its mark to turn back
                self.errands.pop(sapper.id)
                home = world.player_buildings(player, BuildingType.TOWN_HALL, done=True)
                if home:
                    tile = world.free_tile_near(home[0].rect, prefer=sapper.pos)
                    if tile is not None:
                        world.move([sapper.id], tile_center(tile))
                return
            self.errands.pop(sapper.id, None)
        best: KnownBuilding | None = None
        best_rank = (0, 0.0)
        for record in rival_buildings(world, player):
            if record.type not in (BuildingType.TOWER, BuildingType.TOWN_HALL) or record.ruin:
                continue
            center = record.center
            escorted = push is not None and dist(center, push) <= 12.0
            if not escorted and (dist(center, sapper.pos) > SAP_RUN or any(dist(e.pos, center) <= 7.0 for e in soldiers)
                                 or any(_near_line(e.pos, sapper.pos, center, INTERCEPT) for e in soldiers)):
                continue
            if int_sum(1 for u in world.units_near(center, record.size / 2 + reach + 1.0)
                       if u.player == player and u is not sapper and not u.flying and rect_gap(u.pos, record.rect) <= reach + 0.5) > 1:
                continue  # our own at its walls: the keg would take them with it
            rank = (0 if escorted else 1, dist(sapper.pos, center))
            if best is None or rank < best_rank:
                best, best_rank = record, rank
        if best is not None:
            _go_at(world, player, sapper, best)
            self.errands[sapper.id] = best.id

    # -- The treant ----------------------------------------------------------------------------------------------------

    def _flank(self, world: World, player: int, treant: Unit, push: Point) -> bool:
        """While the army pushes at *push*, take the rival building beside the most trees near it, through the wood: the
        trees as the side remembers them."""
        target: KnownBuilding | None = None
        best = (-1, 0.0)
        remembered, width = world.worker_knowledge[player].terrain, world.width
        for record in rival_buildings(world, player):
            center = record.center
            if dist(center, push) > 14.0:
                continue
            x, y, w, h = record.rect
            trees = int_sum(1 for ty in range(max(0, y - 3), min(world.height, y + h + 3))
                            for tx in range(max(0, x - 3), min(width, x + w + 3)) if remembered[ty * width + tx] is Terrain.TREES)
            rank = (trees, -dist(center, push))
            if target is None or rank > best:
                target, best = record, rank
        if target is None:
            return False
        order = treant.order
        if not (isinstance(order, Attack) and order.auto):  # a fight of its own it finishes
            _go_at(world, player, treant, target)
        self.errands[treant.id] = target.id
        return True

    # -- The rune golem ------------------------------------------------------------------------------------------------

    def _slam(self, world: World, player: int, golem: Unit) -> bool:
        """Go for the thickest knot of rival melee within its sight and a little more: at least :data:`KNOT` others round
        one of them, where its slam lands on all of them at once."""
        if golem.windup > 0.0:
            return golem.id in self.errands
        reach = golem.info.splash + 0.5
        best: Unit | None = None
        best_knot = KNOT - 1
        for enemy in world.units_near(golem.pos, golem.info.sight + 2.0):
            if (enemy.player == player or enemy.player >= world.seats or enemy.hidden or enemy.hp <= 0 or enemy.flying
                    or not enemy.info.melee or not world.is_visible(player, enemy.tile)):
                continue
            knot = int_sum(1 for other in world.units_near(enemy.pos, reach + 0.6)
                           if other is not enemy and other.player == enemy.player and not other.hidden and other.hp > 0
                           and not other.flying and dist(other.pos, enemy.pos) - other.radius <= reach
                           and world.is_visible(player, other.tile))
            if knot > best_knot or (best is not None and knot == best_knot and enemy.id < best.id):
                best, best_knot = enemy, knot
        if best is None:
            self.errands.pop(golem.id, None)
            return False
        if not (isinstance(golem.order, Attack) and golem.order.target == best.id):
            world.attack([golem.id], best.id)
        self.errands[golem.id] = best.id
        return True


_OWN: Final = frozenset(OWN_UNITS.values())


def _known(world: World, player: int, target: int) -> bool:
    """Whether *player* still knows of an errand's *target*: a rival unit it sees, or a building it remembers."""
    unit = world.units.get(target)
    if unit is not None:
        return not unit.hidden and world.is_visible(player, unit.tile)
    return target in world.worker_knowledge[player].buildings


def _going_at(unit: Unit, record: KnownBuilding) -> bool:
    """Whether *unit* is already on its way at a remembered building, as :func:`_go_at` sends it."""
    order = unit.order
    return ((isinstance(order, Attack) and order.target == record.id)
            or (isinstance(order, Move) and dist(order.target, record.center) <= REDIRECT))


def _go_at(world: World, player: int, unit: Unit, record: KnownBuilding) -> None:
    """Send *unit* at a remembered rival building: at the building itself while the side sees it, and while it does
    not, on a walk to where it remembers it (what stands there is not the side's to know until it looks; a walk, as a
    keg or a treant sent at a hall is not to be turned aside by what it passes).  An order it is already on is not
    given again, which would restart its walk."""
    if world.any_visible(player, record.rect) and record.id in world.buildings:
        if not (isinstance(unit.order, Attack) and unit.order.target == record.id):
            world.attack([unit.id], record.id)
    elif not (isinstance(unit.order, Move) and dist(unit.order.target, record.center) <= REDIRECT):
        world.move([unit.id], record.center)


def _near_line(point: Point, a: Point, b: Point, within: float) -> bool:
    """Whether *point* is within *within* tiles of the segment from *a* to *b*."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 <= 0.0 else max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / length2))
    return dist(point, (ax + dx * t, ay + dy * t)) <= within
