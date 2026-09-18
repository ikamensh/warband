"""The authoritative match gives orders to the world it is running, not to a copy rebuilt from its save.

Every accepted order once replaced the world with ``World.from_dict(world.to_dict())``.  A save keeps no
paths, plan throttles or stuck clocks, so each order, from either seat, made every unit on the map forget
its route and plan again, and the match a seat got depended on how often the other one clicked.
"""
import pytest

from saga2d import CommandError
from warband.authority import WarbandMatch
from warband.rules import BuildingType, UnitType


def marched(chatter_every: int | None, ticks: int = 300) -> list[tuple[float, float]]:
    """Seat 0 sends a worker across the map; where it is every 50 ticks, with seat 1 re-setting its rally point or not."""
    match = WarbandMatch(seed=3)
    walker = match.world.player_units(0)[0]
    match.apply(0, {'action': 'move', 'args': [[walker.id], [match.world.width - 6.5, match.world.height - 6.5]], 'kwargs': {}})
    hall = match.world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    trail = []
    for tick in range(ticks):
        if chatter_every is not None and tick % chatter_every == 0:
            match.apply(1, {'action': 'set_rally', 'args': [hall.id, [hall.x - 2.5, hall.y + 0.5]], 'kwargs': {}})
        match.step()
        if tick % 50 == 49:
            trail.append(match.world.units[walker.id].pos)
    return trail


@pytest.mark.parametrize("chatter_every", [1, 7, 40])
def test_one_seats_orders_leave_the_other_seats_march_alone(chatter_every) -> None:
    """To the float bit: lockstep-grade determinism is the simulation's rule, and an order about a rally point is not about that worker."""
    assert marched(chatter_every) == marched(None)


def test_an_accepted_order_is_given_to_the_running_world() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    worker = world.player_units(1)[0]
    match.apply(1, {'action': 'move', 'args': [[worker.id], [worker.x + 3, worker.y]], 'kwargs': {}})
    assert match.world is world and worker.orders, "the order went to a copy of the world"

