"""Combat power estimates used when choosing and defending a push."""

from __future__ import annotations

import math

from warband.sim.model import Point, Unit, World, dist, plain_sum
from warband.sim.rules import CAMP_ENCOUNTERS, UNITS, BuildingType

def _dps(world: World, unit: Unit) -> float:
    if unit.info.blast:
        return 0.0  # one blow that is its end: no fight is worn down by it, whatever the number of it
    if unit.info.heal:
        # A cleric adds to a fight by undoing damage; count its healing as if it were damage (its own blow is a last resort).
        return world.heal_rate(unit) * 0.8
    return world.damage_of(unit) / unit.info.period


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
    damage = plain_sum(_dps(world, u) for u in units)
    body = plain_sum(_effective_hp(world, u) for u in units)
    return math.sqrt(damage * body)


def camp_strength(world: World, player: int, point: Point, army: list[Unit], lair_id: int,
                  seen: float = 0.0) -> float:
    """Price a scouted roster and visible guards, with extra slam risk for a melee-heavy army.

    Both brains ask this before choosing a destination. Hidden casualties and
    health never change the answer: only public roster stats and the player's
    sight do. *seen* is the remembered guard power, before composition risk.
    """
    guards = [u for u in world.units_near(point, 10.0)
              if u.player == world.neutral and u.hp > 0 and world.is_visible(player, u.tile)]
    value = max(seen, strength(world, guards))
    splash = any(u.info.splash for u in guards)
    # A remembered camp's identity/roster is public. Hidden health, casualties
    # and positions are deliberately never read for its conservative prior.
    camp = world.camp_for(lair_id)
    info = CAMP_ENCOUNTERS.get(camp.encounter) if camp is not None else None
    if info is not None:
        damage = plain_sum(UNITS[kind].damage / UNITS[kind].period for kind in info.roster)
        body = plain_sum(UNITS[kind].hp * (1.0 + UNITS[kind].armor / 6.0) for kind in info.roster)
        value = max(value, math.sqrt(damage * body))
        splash = splash or any(UNITS[kind].splash for kind in info.roster)
    if army and splash:
        melee = plain_sum(1.0 for u in army if u.info.range <= 1.5)
        value *= 1.0 + 0.6 * melee / len(army)
    return value


def _tower_strength(world: World, player: int, point: Point, radius: float = 9.0) -> float:
    """What the fortifications around *point* add to the defender.

    Only the ones we have seen: ``worker_knowledge`` remembers every armed
    structure this player has laid eyes on, and nothing else. A tower is priced
    at what it was built as rather than at its current health, because a
    remembered tower is not a tower we are looking at.
    """
    damage = body = 0.0
    for record in world.worker_knowledge[player].threats:
        if record.player in (None, player) or dist(record.center, point) > radius:
            continue
        building = world.buildings.get(record.id)
        if building is None or not building.info.damage:
            continue
        damage += world.damage_of(building) / building.info.cooldown
        body += building.max_hp
    return math.sqrt(damage * body)


def _tower_strength_own(world: World, player: int, point: Point, radius: float = 9.0) -> float:
    """What *player*'s own standing towers around *point* add to its defence, as :func:`_tower_strength` prices an enemy's."""
    damage = body = 0.0
    for building in world.player_buildings(player, BuildingType.TOWER, done=True):
        if dist(building.center, point) <= radius:
            damage += world.damage_of(building) / building.info.cooldown
            body += building.hp
    return math.sqrt(damage * body)
