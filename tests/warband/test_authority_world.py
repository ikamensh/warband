"""The authoritative match gives orders to the world it is running, not to a copy rebuilt from its save.

Every accepted order once replaced the world with ``World.from_dict(world.to_dict())``.  A save keeps no
paths, plan throttles or stuck clocks, so each order, from either seat, made every unit on the map forget
its route and plan again, and the match a seat got depended on how often the other one clicked.
"""
import pytest

from saga2d import CommandError
from warband.online.authority import WarbandMatch
from warband.sim.rules import BuildingType, UnitType


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
    from warband.sim.model import World

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
        whole = world.to_dict()
        for key in ('units', 'buildings'):
            own = [entity for entity in whole[key] if entity['player'] == seat]
            assert own and [entity for entity in sent[key] if entity['player'] == seat] == own, f"a seat's own {key} travel whole"


def test_a_snapshot_is_the_receivers_to_keep() -> None:
    match = WarbandMatch(seed=3)
    sent = match.snapshot(0)
    sent['world']['units'].clear()
    sent['events'].append('scribble')
    assert match.world.units and 'scribble' not in match.events and match.snapshot(0)['world']['units']


def test_a_checkpoint_keeps_the_whole_match() -> None:
    from warband.online.authority import ONLINE

    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    spec = ONLINE['warband-v2']
    restored = spec.restore(spec.checkpoint(match))
    assert restored.world.to_dict() == match.world.to_dict() and restored.world.rng.getstate() == match.world.rng.getstate()


def test_old_news_leaves_the_snapshot_and_fresh_news_stays_long_enough_to_be_read() -> None:
    """Every snapshot once carried the last 128 events for ever: a quarter of its bytes, ten times a second, minutes after the fight."""
    from warband.online.authority import EVENT_TICKS
    from tests.warband.battlefield import field

    match = WarbandMatch(seed=3)
    match.world = field()
    victim = match.world.spawn_unit(0, UnitType.PEASANT, (12.5, 12.5))
    victim.hp = 1
    raider = match.world.spawn_unit(1, UnitType.FOOTMAN, (13.4, 12.5))
    match.world.update_vision()
    match.apply(1, {'action': 'attack', 'args': [[raider.id], victim.id], 'kwargs': {}})
    for _ in range(200):
        match.step()
        if victim.id not in match.world.units:
            break
    news = match.snapshot(0)['events']
    assert {fields['kind'] for _, fields in news} >= {'hit', 'death'}
    for _ in range(EVENT_TICKS // 2):
        match.step()
    assert match.snapshot(0)['events'] == news, "a client a second or two behind must still find the news"
    for _ in range(EVENT_TICKS):
        match.step()
    assert match.snapshot(0)['events'] == [], "old news still rides every snapshot"
    match.world.reveal_all(1)  # seat 1 has scouted the hall across the field: a seat names only what it knows
    match.apply(1, {'action': 'attack', 'args': [[raider.id], match.world.player_buildings(0)[0].id], 'kwargs': {}})
    for _ in range(600):
        match.step()
        if match.snapshot(0)['events']:
            break
    later = match.snapshot(0)['events']
    assert later and later[0][0] > news[-1][0], "event numbers go on counting, so a client never takes new news for old"


def test_event_numbers_go_on_counting_after_a_restart_in_a_quiet_moment() -> None:
    from warband.online.authority import EVENT_TICKS, ONLINE
    from tests.warband.battlefield import field

    match = WarbandMatch(seed=3)
    match.world = field()
    victim = match.world.spawn_unit(0, UnitType.PEASANT, (12.5, 12.5))
    victim.hp = 1
    raider = match.world.spawn_unit(1, UnitType.FOOTMAN, (13.4, 12.5))
    match.world.update_vision()
    match.apply(1, {'action': 'attack', 'args': [[raider.id], victim.id], 'kwargs': {}})
    for _ in range(200 + EVENT_TICKS):
        match.step()
    assert match.event_id > 0 and match.events == [], "the fight is old news by now"
    spec = ONLINE['warband-v2']
    restored = spec.restore(spec.checkpoint(match))
    assert restored.event_id == match.event_id, "a client would take the news after the restart for news it has had"
