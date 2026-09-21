"""Creature camps: a lair, the guards posted round it, and the rule that puts them back.

A camp is a :class:`~warband.sim.rules.BuildingType.LAIR` with its guards placed beside it when the map
is drawn.  Three rules make it a decision rather than a toll:

* **They rouse together.**  Anything of a playing seat that comes within :data:`~warband.sim.rules.CAMP_WATCH`
  of the lair sends every guard at it at once.  Pulling one wolf at a time and whittling the camp down is
  the cheese this exists to stop, and shared aggro -- not a spawn timer -- is what stops it.
* **They leash to the camp.**  A guard chased or kited past :data:`~warband.sim.rules.CAMP_HOLD` of the lair
  breaks off and walks back to its post, so a camp cannot be dragged into somebody else's fight.  The
  camp's own hold is that leash: a roused guard's :attr:`~warband.sim.model.Unit.home` is cleared, because
  the six tiles :data:`~warband.sim.rules.LEASH` gives an idle chase are shorter than the camp is wide.
* **The camp resets.**  Left alone for :data:`~warband.sim.rules.CAMP_CALM` seconds, guards standing at their
  posts knit their wounds back and the lair sends a fallen one out again every
  :data:`~warband.sim.rules.CAMP_RESPAWN` seconds.  Tear the lair down and none of that happens again.

So the decision is crisp: clear the whole camp, lair included, in one committed push and it is yours for
good; break off half way and you paid units for nothing.  The lair holds the payout
(:attr:`~warband.sim.model.Building.gold`, paid whole to whoever brings it down) and wears a building's
fortified armour, which is what hands a catapult a job before the first walls.

Camps do not stream units.  A den that emitted them would either eat an army during the fight, with no
decision in it, or trickle so slowly that clearing it is beating down an undefended building.
"""

from __future__ import annotations

import math
from typing import Final

from warband.sim.model import Attack, Camp, Move, Point, Unit, World, dist, hypot, tile_center
from warband.sim.rules import (CAMP_CALM, CAMP_HOLD, CAMP_POST, CAMP_REGEN, CAMP_RESPAWN, CAMP_WATCH, SIM_DT,
                               BuildingType, UnitType)

EVERY: Final = 5  # ticks between passes: a quarter of a second, which no creature outruns
DT: Final = EVERY * SIM_DT
HOME: Final = 1.2  # tiles from its post a guard counts itself home
CHASE_SLACK: Final = 3.0  # tiles past CAMP_HOLD a guard already locked on may follow before it is called back
ANSWER: Final = 3.0  # seconds since a guard was struck within which the camp goes looking further out for whoever did it


def centre(world: World, camp: Camp) -> Point:
    """The camp's middle: its lair's, or its posts' own once the lair is down."""
    lair = world.buildings.get(camp.lair)
    if lair is not None:
        return lair.center
    return (sum(x for x, _y in camp.posts) / len(camp.posts), sum(y for _x, y in camp.posts) / len(camp.posts))


def guards(world: World, camp: Camp) -> list[Unit]:
    """The guards of *camp* still standing."""
    return [world.units[uid] for uid in camp.guards if uid in world.units]


def posted(world: World, camp: Camp) -> list[tuple[Unit, Point]]:
    """Each guard still standing, with the post it holds when the camp is settled."""
    return [(world.units[uid], post) for uid, post in zip(camp.guards, camp.posts) if uid in world.units]


def _intruder(world: World, point: Point, radius: float) -> Unit | None:
    """The nearest unit of a playing seat within *radius* of *point*.

    A peasant counts: a camp that ignored workers would let a player tunnel a mining route straight
    through it, and keeping gatherers out of one is exactly what the automatic policy's threat grid
    already does (:func:`warband.sim.worker_ai.safe_navigation`).
    """
    best: Unit | None = None
    best_d = radius
    neutral = world.neutral
    px, py = point
    for unit in world.units_near(point, radius):
        if unit.player == neutral or unit.hidden or unit.hp <= 0:
            continue
        d = hypot(unit.x - px, unit.y - py)
        if d < best_d:
            best, best_d = unit, d
    return best


def update(world: World) -> None:
    """One pass over every camp on the map, from :meth:`~warband.sim.model.World._step`."""
    for camp in world.camps:
        middle = centre(world, camp)
        standing = posted(world, camp)
        near = _intruder(world, middle, CAMP_HOLD if camp.roused else CAMP_WATCH)
        if near is None and any(world.time - guard.struck < ANSWER for guard, _post in standing):
            # Something is shooting the camp from beyond its watch -- a catapult outranges every guard --
            # so it looks as far as a guard could be sent, rather than standing there being taken apart.
            near = _intruder(world, middle, CAMP_HOLD + CHASE_SLACK)
        if near is not None:
            _rouse(world, camp, standing, middle, near)
        else:
            _settle(world, camp, standing)


def _rouse(world: World, camp: Camp, standing: list[tuple[Unit, Point]], middle: Point, near: Unit) -> None:
    """Every guard goes at the intruder at once: one wolf at a time is the cheese this stops."""
    camp.roused = True
    camp.quiet_since = -1.0
    camp.rebuild_at = world.time + CAMP_RESPAWN
    for guard, _post in standing:
        order = guard.order
        if isinstance(order, Attack):
            target = world.entity(order.target)
            if target is not None and target.hp > 0 and dist(world._target_point(target), middle) <= CAMP_HOLD + CHASE_SLACK:
                continue  # already fighting something inside the camp's reach
        guard.orders.clear()
        guard.home = None
        guard.orders.append(Attack(near.id, auto=True))


def _settle(world: World, camp: Camp, standing: list[tuple[Unit, Point]]) -> None:
    """Nobody within the camp's hold: the guards walk back, and once they have been quiet long enough the
    wounded mend and the lair sends the fallen out again."""
    camp.roused = False
    if camp.quiet_since < 0.0:
        camp.quiet_since = world.time
        camp.rebuild_at = world.time + CAMP_RESPAWN
    for guard, post in standing:
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
    _mend(standing)
    if world.time >= camp.rebuild_at:
        camp.rebuild_at = world.time + CAMP_RESPAWN
        _refill(world, camp)


def _mend(standing: list[tuple[Unit, Point]]) -> None:
    """A settled guard standing at its post knits its wounds back, a whole hit point at a time."""
    for guard, post in standing:
        if guard.hp >= guard.max_hp or dist(guard.pos, post) > HOME:
            continue
        guard.charge += CAMP_REGEN * DT
        whole = int(guard.charge)
        if whole:
            guard.charge -= whole
            guard.hp = min(guard.max_hp, guard.hp + whole)


def _refill(world: World, camp: Camp) -> None:
    """One fallen guard comes back out of the lair -- while the lair still stands."""
    lair = world.buildings.get(camp.lair)
    if lair is None:
        return  # the den is down: what is dead stays dead, which is what makes clearing a camp permanent
    for index, uid in enumerate(camp.guards):
        if uid in world.units:
            continue
        post = camp.posts[index]
        door = world.free_tile_near(lair.rect, prefer=post)
        if door is None:
            return
        guard = world.spawn_unit(world.neutral, UnitType(camp.kinds[index]), tile_center(door))
        camp.guards[index] = guard.id
        guard.orders.append(Move(post))
        return


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
    camp = Camp(lair=lair.id, kinds=[], posts=[], guards=[])
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
