"""What needs what: the tech tree as the rules tables give it, and where a player stands in it.

The rules keep each prerequisite beside what needs it (:mod:`warband.sim.rules`: a building's ``requires``, a
unit's ``trained_at``, an upgrade's lower tier and the building that researches it).  This reads them the other
way round for the HUD: what an item still needs, whether that is on its way, what a building opens.  The world
checks the same rules when an order arrives; nothing here decides what the simulation does, and it lives outside
``warband/sim`` so the online contract, which hashes that folder, does not move for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from warband.sim.model import Build, World
from warband.sim.rules import BUILDINGS, UNITS, UPGRADES, BuildingType, UnitType, Upgrade

Target = UnitType | BuildingType | Upgrade
Prerequisite = BuildingType | Upgrade


def researched_at(upgrade: Upgrade) -> BuildingType:
    return next(kind for kind, info in BUILDINGS.items() if upgrade in info.researches)


def prerequisites(target: Target) -> tuple[Prerequisite, ...]:
    """What *target* needs directly, in the order a player meets it: a unit its building, a building the one it
    requires, an upgrade the building that researches it and then its lower tier.  Every race shares these."""
    if isinstance(target, UnitType):
        return (UNITS[target].trained_at,)
    if isinstance(target, BuildingType):
        requires = BUILDINGS[target].requires
        return () if requires is None else (requires,)
    lower = UPGRADES[target].requires
    return (researched_at(target),) + (() if lower is None else (lower,))


@dataclass(frozen=True)
class Need:
    """The first prerequisite of an item that the player lacks, and whether it is on its way: then an order for the
    item is planned and waits for it, where otherwise it would wait for something nobody is making."""

    target: Prerequisite
    coming: bool


def has(world: World, player: int, item: Prerequisite) -> bool:
    """A building of *item*'s kind stands finished, or the upgrade is researched."""
    if isinstance(item, BuildingType):
        return bool(world.player_buildings(player, item, done=True))
    return item in world.players[player].upgrades


def coming(world: World, player: int, item: Prerequisite) -> bool:
    """*item* is on its way: a building going up, planned or a builder's next site; an upgrade researched or planned."""
    if any(plan.type is item for plan in world.player_plans(player)):
        return True
    if isinstance(item, BuildingType):
        return (bool(world.player_buildings(player, item, done=False))
                or any(isinstance(order, Build) and order.type is item for unit in world.player_units(player) for order in unit.orders))
    return any(building.research is item for building in world.player_buildings(player))


def need(world: World, player: int, target: Target) -> Need | None:
    """What *target* waits for, or None when the player has everything it needs (or, an upgrade, has it already)."""
    if isinstance(target, Upgrade) and target in world.players[player].upgrades:
        return None
    for item in prerequisites(target):
        if not has(world, player, item):
            return Need(item, coming(world, player, item))
    return None
