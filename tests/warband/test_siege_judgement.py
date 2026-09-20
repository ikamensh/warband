"""A catapult left to its own judgement finds something useful to throw at (WB-052): when the lines meet, the enemy in
front is locked with its own soldiers, so the crew looks for ground where a stone falls on the enemy alone (the
ranks behind, archers, healers, other engines, buildings) and moves up to reach it.

A crew used to refuse outright any stone that could touch its own side, which behind a line locked with the enemy
is every stone there is.  It weighs the trade instead: one of ours under the stone costs ``FRIENDLY_WORTH`` against
one of theirs, and the crew throws what comes down ahead.  So it still keeps its stones off its own line —
the trade rarely pays — but it no longer holds fire all clash to save a graze."""

import math
import random

from warband.sim.model import SIM_DT, Hold, World
from warband.sim.rules import FRIENDLY_WORTH, SIEGE_WORTH, Terrain, UnitType


def clash(seed: int = 1) -> tuple[World, int, set[int]]:
    """Eight footmen a side meet mid-field; the enemy's four archers stand two tiles behind their line, and our
    catapult rolls up six tiles behind ours.  Everyone was given an attack-move, as a player sends an army."""
    world = World(40, 20, [[Terrain.GRASS] * 40 for _ in range(20)], 2, rng=random.Random(seed))
    ours = [world.spawn_unit(0, UnitType.FOOTMAN, (14.5, 6.5 + i)) for i in range(8)]
    theirs = [world.spawn_unit(1, UnitType.FOOTMAN, (21.5, 6.5 + i)) for i in range(8)]
    archers = [world.spawn_unit(1, UnitType.ARCHER, (23.5, 7.5 + 2 * i)) for i in range(4)]
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (8.5, 10.0))
    world.attack_move([u.id for u in ours] + [catapult.id], (30.5, 10.0))
    world.attack_move([u.id for u in theirs], (5.5, 10.0))
    world.hold([u.id for u in archers])
    return world, catapult.id, {u.id for u in ours}


def fight(world: World, catapult: int, ours: set[int], seconds: float) -> tuple[list[float], int, int]:
    """Times the catapult let a stone go, and what its stones cost the enemy and our own side."""
    launches: list[float] = []
    friendly = hostile = 0
    seen: set[int] = set()
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()
        for p in world.projectiles.values():
            if p.source == catapult and p.id not in seen:
                seen.add(p.id)
                launches.append(world.time)
        for e in world.take_events():
            if e.kind == "hit" and e.entity == catapult:
                if e.other in ours | {catapult}:
                    friendly += e.amount
                else:
                    hostile += e.amount
        if catapult not in world.units or not any(u.player == 1 for u in world.units.values()):
            break
    return launches, friendly, hostile


def test_in_a_clash_the_catapult_keeps_throwing_and_its_own_line_stands_through_it() -> None:
    """From the moment the lines meet until the fight is decided or half a minute has passed, the crew lets a stone go
    at least every other reload, and what its stones cost our own side stays a fraction of what they cost the enemy:
    the crew takes the occasional graze for a good trade, never a stone on the line.  It used to hold fire instead,
    for the whole clash."""
    ours_lost = theirs_lost = 0
    for seed in range(1, 13):
        world, catapult, ours = clash(seed)
        while not any(e.kind == "hit" and e.other in ours for e in world.take_events()):  # the first blow between the lines
            world.step()
        contact = world.time
        launches, friendly, hostile = fight(world, catapult, ours, 30.0)
        ours_lost, theirs_lost = ours_lost + friendly, theirs_lost + hostile
        assert friendly * 3 < hostile, f"seed {seed}: the stones cost us {friendly} against {hostile} on the enemy"
        end = min(world.time, contact + 30.0)
        cycle = 2 * (world.units[catapult].info.windup + world.units[catapult].info.cooldown) if catapult in world.units else 7.6
        assert len(launches) >= int((end - contact) / cycle), f"seed {seed}: {len(launches)} stones in {end - contact:.1f} s"
    assert ours_lost * 10 < theirs_lost, f"over the twelve clashes the stones cost us {ours_lost} against {theirs_lost}"


def test_a_catapult_on_hold_looks_again_when_its_target_has_no_clear_stone() -> None:
    """A held crew chose a peasant; then a friend stepped up beside it, so no stone can fall there clear of our own side.
    The crew chooses again and throws at the archer shooting it, never at the peasant while the friend stands there.  It
    used to wait on the peasant for good while the archer shot it to pieces."""
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], 2, rng=random.Random(1))
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (10.5, 8.5))
    catapult.facing = math.pi
    peasant = world.spawn_unit(1, UnitType.PEASANT, (4.5, 8.5))
    world.hold([catapult.id, peasant.id])
    world.update_vision()
    for _ in range(5):
        world.step()
    assert isinstance(catapult.order, Hold) and catapult.order.target == peasant.id
    friend = world.spawn_unit(0, UnitType.PEASANT, (5.3, 8.5))
    archer = world.spawn_unit(1, UnitType.ARCHER, (10.5, 13.2))
    world.hold([friend.id, archer.id])
    world.update_vision()
    struck: set[int] = set()
    for _ in range(int(round(5.0 / SIM_DT))):
        world.step()
        struck |= {e.other for e in world.take_events() if e.kind == "hit" and e.entity == catapult.id}
        if archer.id in struck:
            break
    assert struck == {archer.id}
    assert isinstance(catapult.order, Hold) and catapult.pos == (10.5, 8.5)


def test_a_catapult_on_hold_throws_at_what_it_can_reach_past_an_archer_inside_its_minimum_range() -> None:
    """A held crew with an archer shooting it from inside its minimum range, where it cannot throw, throws at the footman
    in its reach instead.  It used to settle on the archer, worth more, because a stone dropped a tile beyond it would
    land outside the minimum range, then find it too close and throw at nothing."""
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], 2, rng=random.Random(1))
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (10.5, 8.5))
    catapult.facing = math.pi
    archer = world.spawn_unit(1, UnitType.ARCHER, (8.3, 8.5))
    footman = world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 14.2))
    world.hold([catapult.id, archer.id, footman.id])
    world.update_vision()
    assert world.range_of(catapult) >= 5.0 and catapult.info.min_range > 1.5  # the footman's gap, and the archer's
    struck: set[int] = set()
    for _ in range(int(round(4.0 / SIM_DT))):
        world.step()
        struck |= {e.other for e in world.take_events() if e.kind == "hit" and e.entity == catapult.id}
        if footman.id in struck:
            break
    assert struck == {footman.id}


RING = ((0.95, 0.0), (0.0, 0.95), (0.0, -0.95), (-0.95, 0.0), (0.67, 0.67))  # tight enough that one stone reaches several


def throws_at_a_ring(foes: int, friends: int) -> bool:
    """Whether a held crew throws at a ring of *foes* enemy footmen four tiles off with *friends* of our knights
    locked in the middle of it.  In the middle, so that every stone the crew could throw is over our own: it is the
    trade that decides, not a corner of the huddle the crew could pick off instead."""
    world = World(30, 20, [[Terrain.GRASS] * 30 for _ in range(20)], 2, rng=random.Random(1))
    crew = world.spawn_unit(0, UnitType.CATAPULT, (8.5, 8.5))
    crew.facing = 0.0
    held = [world.spawn_unit(1, UnitType.FOOTMAN, (13.0 + dx, 8.5 + dy)) for dx, dy in RING[:foes]]
    held += [world.spawn_unit(0, UnitType.KNIGHT, (13.0, 8.5)) for _ in range(friends)]
    world.hold([crew.id] + [u.id for u in held])
    world.update_vision()
    for _ in range(int(round(2.5 / SIM_DT))):
        world.step()
        if any(p.source == crew.id for p in world.projectiles.values()):
            return True
    return False


def test_a_crew_spends_one_of_its_own_only_for_several_of_theirs() -> None:
    """The trade, stated: one of ours under the stone costs :data:`FRIENDLY_WORTH` against one for one of theirs, and
    the crew throws only what comes down ahead.  With nobody of ours in the way one enemy is stone enough; with one of
    ours in the middle of them it takes several of theirs to pay for it.  Under the old rule the last case never fired."""
    assert FRIENDLY_WORTH >= 2.0 and SIEGE_WORTH.get(UnitType.FOOTMAN, 1.0) == 1.0
    assert throws_at_a_ring(foes=1, friends=0), "a lone enemy with nobody of ours near it is a stone thrown"
    assert not throws_at_a_ring(foes=1, friends=1), "one of ours for one of theirs is not a trade a crew takes"
    assert not throws_at_a_ring(foes=2, friends=1), "nor one of ours for two of theirs"
    assert throws_at_a_ring(foes=5, friends=1), "a huddle of five is worth one of ours, and the crew throws"
