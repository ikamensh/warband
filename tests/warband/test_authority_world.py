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


def test_a_snapshot_tells_a_seat_neither_the_servers_dice_nor_what_the_other_seat_has_seen() -> None:
    """The save format is the server's; a seat gets the match without the random stream (every damage roll to
    come) and without the other seat's explored ground and remembered map, which also were a third of its bytes."""
    from warband.model import World

    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    world = match.world
    for seat, other in ((0, 1), (1, 0)):
        sent = match.snapshot(seat)['world']
        assert World.from_dict(sent).rng.getstate() != world.rng.getstate(), "the snapshot carries the server's random stream"
        assert sent['explored'][seat] == world.to_dict()['explored'][seat] and not any(bytes.fromhex(sent['explored'][other]))
        theirs = sent['worker_knowledge'][other]
        assert not theirs['buildings'] and not theirs['mines'] and not any(theirs['terrain'])
        assert sent['worker_knowledge'][seat] == world.worker_knowledge[seat].to_dict()
        assert sent['units'] == world.to_dict()['units'] and sent['buildings'] == world.to_dict()['buildings']


def test_a_snapshot_is_the_receivers_to_keep() -> None:
    match = WarbandMatch(seed=3)
    sent = match.snapshot(0)
    sent['world']['units'].clear()
    sent['events'].append('scribble')
    assert match.world.units and 'scribble' not in match.events and match.snapshot(0)['world']['units']


def test_a_checkpoint_keeps_the_whole_match() -> None:
    from warband.authority import ONLINE

    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    spec = ONLINE['warband-v2']
    restored = spec.restore(spec.checkpoint(match))
    assert restored.world.to_dict() == match.world.to_dict() and restored.world.rng.getstate() == match.world.rng.getstate()
