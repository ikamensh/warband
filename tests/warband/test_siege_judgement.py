"""A catapult left to its own judgement finds something useful to throw at (WB-052): when the lines meet, the enemy in
front is locked with its own soldiers, so the crew looks for ground where a stone falls on the enemy alone (the
ranks behind, archers, healers, other engines, buildings) and moves up to reach it, never onto its own side."""

import random

from warband.sim.model import SIM_DT, World
from warband.sim.rules import Terrain, UnitType


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


def fight(world: World, catapult: int, ours: set[int], seconds: float) -> tuple[list[float], int]:
    """Times the catapult let a stone go, and how much of our own side its stones hurt."""
    launches: list[float] = []
    friendly = 0
    seen: set[int] = set()
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()
        for p in world.projectiles.values():
            if p.source == catapult and p.id not in seen:
                seen.add(p.id)
                launches.append(world.time)
        for e in world.take_events():
            if e.kind == "hit" and e.entity == catapult and e.other in ours | {catapult}:
                friendly += e.amount
        if catapult not in world.units or not any(u.player == 1 for u in world.units.values()):
            break
    return launches, friendly


def test_in_a_clash_the_catapult_keeps_throwing_and_never_on_its_own_side() -> None:
    """From the moment the lines meet until the fight is decided or half a minute has passed, the crew lets a stone go
    at least every other reload, and not one lands on our soldiers."""
    for seed in range(1, 7):
        world, catapult, ours = clash(seed)
        while not any(e.kind == "hit" and e.other in ours for e in world.take_events()):  # the first blow between the lines
            world.step()
        contact = world.time
        launches, friendly = fight(world, catapult, ours, 30.0)
        assert friendly == 0, f"seed {seed}: the catapult's stones hurt its own side for {friendly}"
        end = min(world.time, contact + 30.0)
        cycle = 2 * (world.units[catapult].info.windup + world.units[catapult].info.cooldown) if catapult in world.units else 7.6
        assert len(launches) >= int((end - contact) / cycle), f"seed {seed}: {len(launches)} stones in {end - contact:.1f} s"
