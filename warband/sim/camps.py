"""Optional neutral encounters: collective defense, finite guards and earned completion rewards.

Guards rouse together and remain leashed to their home. Fallen guards stay dead, so scouting,
trying a fight and withdrawing can make permanent progress. Survivors mend after disengagement.
An encounter pays once both its guards and lair fall; actual contributed damage shares the payout,
so a final hit cannot steal an expedition. Healing erases the credit for the wounds it restores.
"""

from __future__ import annotations

import math
from typing import Final

from warband.sim.model import Attack, Camp, Event, Move, Point, Unit, World, dist, hypot, int_sum, plain_sum, tile_center
from warband.sim.rules import (CAMP_CALM, CAMP_HOLD, CAMP_POST, CAMP_REGEN, CAMP_WATCH, SIM_DT,
                               CAMP_ENCOUNTERS, BuildingType, UnitType)

EVERY: Final = 5  # ticks between passes: a quarter of a second, which no creature outruns
DT: Final = EVERY * SIM_DT
HOME: Final = 1.2  # tiles from its post a guard counts itself home
CHASE_SLACK: Final = 3.0  # tiles past CAMP_HOLD a guard already locked on may follow before it is called back
ANSWER: Final = 3.0  # seconds since a guard was struck within which the camp goes looking further out for whoever did it


def centre(world: World, camp: Camp) -> Point:
    """The camp's static anchor, including a remembered encounter with no currently visible entities."""
    if camp.origin is not None:
        return camp.origin
    lair = world.buildings.get(camp.lair)
    if lair is not None:
        return lair.center
    return (plain_sum(x for x, _y in camp.posts) / len(camp.posts), plain_sum(y for _x, y in camp.posts) / len(camp.posts))


def guards(world: World, camp: Camp) -> list[Unit]:
    """The guards of *camp* still standing."""
    return [world.units[uid] for uid in camp.guards if uid in world.units and world.units[uid].hp > 0]


def posted(world: World, camp: Camp) -> list[tuple[Unit, Point]]:
    """Each guard still standing, with the post it holds when the camp is settled."""
    return [(world.units[uid], post) for uid, post in zip(camp.guards, camp.posts) if uid in world.units and world.units[uid].hp > 0]


def _intruder(world: World, point: Point, radius: float, standing: list[tuple[Unit, Point]]) -> Unit | None:
    """The nearest unit of a playing seat within *radius* of *point*.

    A peasant counts: a camp that ignored workers would let a player tunnel a mining route straight
    through it, and keeping gatherers out of one is exactly what the automatic policy's threat grid
    already does (:func:`warband.sim.worker_ai.safe_navigation`). Unarmed flying scouts do not
    rouse it. An armed flyer counts only if a surviving guard can answer it, so an unreachable
    flyer cannot distract every ground guard or keep an otherwise settled camp awake.
    """
    best: Unit | None = None
    best_d = radius
    neutral = world.neutral
    px, py = point
    for unit in world.units_near(point, radius):
        if unit.player == neutral or unit.hidden or unit.hp <= 0:
            continue
        if unit.flying and (not unit.info.damage or not any(world.can_strike(guard, unit) for guard, _post in standing)):
            continue
        d = hypot(unit.x - px, unit.y - py)
        if d < best_d:
            best, best_d = unit, d
    return best


def update(world: World) -> None:
    """One pass over every camp on the map, from :meth:`~warband.sim.model.World._step`."""
    for camp in world.camps:
        if camp.cleared:
            continue
        if _complete(world, camp):
            continue
        middle = centre(world, camp)
        standing = posted(world, camp)
        near = _intruder(world, middle, CAMP_HOLD if camp.roused else CAMP_WATCH, standing)
        if near is None and (world.time - camp.struck < ANSWER or any(world.time - guard.struck < ANSWER for guard, _post in standing)):
            # Something is shooting the camp from beyond its watch -- a catapult outranges every guard --
            # so it looks as far as a guard could be sent, rather than standing there being taken apart.
            near = _intruder(world, middle, CAMP_HOLD + CHASE_SLACK, standing)
        if near is not None:
            _rouse(world, camp, standing, middle, near)
        else:
            _settle(world, camp, standing)


def _rouse(world: World, camp: Camp, standing: list[tuple[Unit, Point]], middle: Point, near: Unit) -> None:
    """Every guard goes at the intruder at once: one wolf at a time is the cheese this stops."""
    camp.roused = True
    camp.quiet_since = -1.0
    candidates = [unit for unit in world.units_near(middle, CAMP_HOLD + CHASE_SLACK)
                  if unit.player != world.neutral and not unit.hidden and unit.hp > 0
                  and (not unit.flying or unit.info.damage)]
    for guard, _post in standing:
        if guard.windup > 0.0:
            continue  # an attack once committed has a fixed tell and outcome
        target = near
        hittable = [unit for unit in candidates if world.can_strike(guard, unit)]
        if not world.can_strike(guard, target):
            if not hittable:
                continue
            target = min(hittable, key=lambda unit: (dist(unit.pos, guard.pos), unit.id))
        if guard.type is UnitType.WOLF:
            exposed = [unit for unit in hittable if unit.info.ranged and not unit.is_worker and unit.info.damage]
            if exposed:
                target = min(exposed, key=lambda unit: (dist(unit.pos, guard.pos), unit.id))
        elif guard.type is UnitType.SPIDER:
            melee = [unit for unit in candidates if unit.info.melee and unit.info.damage]
            close = min(melee, key=lambda unit: (dist(unit.pos, guard.pos), unit.id)) if melee else None
            if close is not None and dist(close.pos, guard.pos) < 3.0 and guard.cooldown > 0.0:
                dx, dy = guard.x - close.x, guard.y - close.y
                length = hypot(dx, dy)
                if length > 0.01:
                    spot = world._clamp((guard.x + dx / length * 2.0, guard.y + dy / length * 2.0))
                    if (dist(spot, middle) <= CAMP_HOLD and world.passable(int(spot[0]), int(spot[1]))
                            and world._line_clear(guard.pos, spot)):
                        guard.orders.clear()
                        guard.orders.append(Move(spot))
                        continue
        order = guard.order
        if isinstance(order, Attack):
            current = world.entity(order.target)
            if (current is not None and current.hp > 0 and dist(world._target_point(current), middle) <= CAMP_HOLD + CHASE_SLACK
                    and (guard.type is not UnitType.WOLF or current is target)):
                continue
        guard.orders.clear()
        guard.home = None
        guard.orders.append(Attack(target.id, auto=True))


def _settle(world: World, camp: Camp, standing: list[tuple[Unit, Point]]) -> None:
    """Nobody within the hold: survivors return home and mend; defeated guards stay defeated."""
    camp.roused = False
    if camp.quiet_since < 0.0:
        camp.quiet_since = world.time
    for guard, post in standing:
        if guard.slam_point is not None and guard.windup > 0.0:
            continue  # a committed ground slam finishes even when its target leaves the hold
        if dist(guard.pos, post) <= HOME:
            if isinstance(guard.order, Move):
                guard.orders.clear()
            continue
        order = guard.order
        if isinstance(order, Move) and dist(order.target, post) <= HOME:
            continue  # already walking back
        guard.orders.clear()
        guard.home = None
        guard.orders.append(Move(post))
    if world.time - camp.quiet_since < CAMP_CALM:
        return
    _mend(world, standing)


def _mend(world: World, standing: list[tuple[Unit, Point]]) -> None:
    """A settled guard standing at its post knits its wounds back, a whole hit point at a time."""
    for guard, post in standing:
        if guard.hp >= guard.max_hp or dist(guard.pos, post) > HOME or world.time - guard.struck < CAMP_CALM:
            continue
        guard.charge += CAMP_REGEN * DT
        whole = int(guard.charge)
        if whole:
            guard.charge -= whole
            amount = min(whole, guard.max_hp - guard.hp)
            guard.hp += amount
            healed(world, guard.id, amount)


def place(world: World, lair_pos: tuple[int, int], roster: list[UnitType], hoard: int) -> Camp:
    """Raise a lair at *lair_pos* with *roster* posted around it, and record the camp.

    The posts are spread evenly round the lair at :data:`~warband.sim.rules.CAMP_POST` tiles from the
    same starting angle every time, so a camp and each of its mirror images on a symmetric map are
    placed by the same arithmetic and come out congruent.
    """
    if not roster:
        raise ValueError("a camp needs at least one guard: an empty one has no middle once its lair is down")
    lair = world.place_building(world.neutral, BuildingType.LAIR, lair_pos)
    lair.gold = hoard
    cx, cy = lair.center
    camp = Camp(lair=lair.id, kinds=[], posts=[], guards=[], gold=hoard, origin=lair.center)
    for i, kind in enumerate(roster):
        angle = 2.0 * math.pi * i / len(roster) + math.pi / 4.0
        spot = world._clamp((cx + math.cos(angle) * CAMP_POST, cy + math.sin(angle) * CAMP_POST))
        tile = (int(spot[0]), int(spot[1]))
        if not world.passable(tile[0], tile[1]) or world.building_at(tile) is not None:
            free = world.free_tile_near(lair.rect, prefer=spot)
            spot = tile_center(free) if free is not None else lair.center
        guard = world.spawn_unit(world.neutral, kind, spot)
        guard.facing = angle
        camp.kinds.append(kind.value)
        camp.posts.append(spot)
        camp.guards.append(guard.id)
    world.camps.append(camp)
    return camp


def place_encounter(world: World, lair_pos: tuple[int, int], encounter: str) -> Camp:
    """Raise a configured encounter: one identity supplies its roster, difficulty and payout."""
    info = CAMP_ENCOUNTERS[encounter]
    camp = place(world, lair_pos, list(info.roster), info.gold)
    camp.encounter, camp.lumber = encounter, info.lumber
    lair = world.buildings[camp.lair]
    lair.max_hp = lair.hp = info.lair_hp
    return camp


def record_damage(world: World, entity: int, player: int, amount: int) -> None:
    """Credit only actual damage on encounter entities, never overkill or hidden purse mutations."""
    camp = world.camp_for(entity)
    if camp is None or camp.cleared or amount <= 0:
        return
    camp.struck = world.time
    shares = camp.credit.setdefault(entity, {})
    shares[player] = shares.get(player, 0.0) + float(amount)


def healed(world: World, entity: int, amount: int) -> None:
    """Restored wounds erase their proportional credit; repeated harassment cannot reserve a hoard."""
    camp = world.camp_for(entity)
    if camp is None or amount <= 0:
        return
    shares = camp.credit.get(entity)
    if not shares:
        return
    total = plain_sum(shares.values())
    factor = max(0.0, total - amount) / total if total > 0.0 else 0.0
    for seat in shares:
        shares[seat] *= factor


def _shares(amount: int, contribution: dict[int, float]) -> dict[int, int]:
    """Largest-remainder allocation conserves integer resources, with deterministic seat-id ties."""
    total = plain_sum(contribution.values())
    quotas = {seat: amount * weight / total for seat, weight in contribution.items()}
    result = {seat: int(quota) for seat, quota in quotas.items()}
    remaining = amount - int_sum(result.values())
    order = sorted(quotas, key=lambda seat: (-(quotas[seat] - result[seat]), seat))
    for seat in order[:remaining]:
        result[seat] += 1
    return result


def _complete(world: World, camp: Camp) -> bool:
    lair = world.buildings.get(camp.lair)
    if lair is not None and lair.hp > 0 or guards(world, camp):
        return False
    camp.cleared = True
    contribution: dict[int, float] = {}
    for shares in camp.credit.values():
        for seat, amount in shares.items():
            if 0 <= seat < world.seats and amount > 0.0:
                contribution[seat] = contribution.get(seat, 0.0) + amount
    if not contribution:
        return True  # scripted removal had no participating seat, hence no earned bounty
    gold, lumber = _shares(camp.gold, contribution), _shares(camp.lumber, contribution)
    point = centre(world, camp)
    for seat in sorted(contribution):
        player = world.players[seat]
        player.gold += gold[seat]
        player.lumber += lumber[seat]
        player.stats["bounty_gold"] += gold[seat]
        player.stats["bounty_lumber"] += lumber[seat]
        world.events.append(Event("hoard", point, player=seat, other=camp.lair,
                                  amount=gold[seat], amount2=lumber[seat], text=camp.encounter))
    owner = min(contribution, key=lambda seat: (-contribution[seat], seat))
    world.players[owner].stats["camps_cleared"] += 1
    world.events.append(Event("camp_cleared", point, player=owner, other=camp.lair, text=camp.encounter))
    for seat in range(world.seats):
        if seat in contribution or world.is_visible(seat, (int(point[0]), int(point[1]))):
            knowledge = world.worker_knowledge[seat]
            knowledge.encounters.setdefault(camp.lair, point)  # witnessed completion news includes its location
            knowledge.cleared_encounters.add(camp.lair)
            knowledge.version += 1
    if lair is not None:
        lair.gold = 0
    return True


def known_guards(world: World, player: int) -> set[int]:
    """Guard identities of discovered encounters, including one whose lair has already fallen."""
    known: set[int] = set()
    for lair in world.worker_knowledge[player].encounters:
        camp = world.camp_for(lair)
        if camp is not None:
            known.update(camp.guards)
    return known


def navigation(world: World, player: int, base: bytearray, excluded_ids: set[int], margin: float,
               warnings: tuple[tuple[float, float, float], ...] = (), *, tile_edges: bool = True) -> bytearray:
    """Remembered camp watches are avoided ground, except an explicitly chosen encounter.

    This changes routing, never physical terrain. A discovered encounter stays
    a remembered danger after its lair falls, until this seat hears completion news.
    By default the tile's nearest edge is stamped. Centre-only stamping permits
    precise escape/fallback routing; its accepted movement must check the actual circle.
    """
    knowledge = world.worker_knowledge[player]
    lairs = [point for lair, point in knowledge.encounters.items()
             if lair not in knowledge.cleared_encounters and lair not in excluded_ids]
    if not lairs and not warnings:
        return base
    grid = bytearray(base)
    circles = [(point[0], point[1], CAMP_WATCH + margin) for point in lairs]
    circles.extend(warnings)
    edge = .5 if tile_edges else 0.0
    for cx, cy, radius in circles:
        for y in range(max(0, int(cy - radius - 1)), min(world.height, int(cy + radius + 1))):
            for x in range(max(0, int(cx - radius - 1)), min(world.width, int(cx + radius + 1))):
                dx = max(0.0, abs(x + .5 - cx) - edge)
                dy = max(0.0, abs(y + .5 - cy) - edge)
                distance2 = dx * dx + dy * dy
                if distance2 < radius * radius or (not tile_edges and distance2 == radius * radius):
                    grid[y * world.width + x] = 1
    return grid
