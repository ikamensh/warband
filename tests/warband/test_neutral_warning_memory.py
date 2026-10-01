"""Observed creature warnings survive fog without revealing hidden units or another seat's memory."""

from warband.online.authority import WarbandMatch
from warband.sim.model import World
from warband.sim.rules import SIM_DT, Terrain, UnitType


def warning_world():
    """Only seat zero can see this armed creature; neither seat knows any encounter anchor."""
    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2, scripted=True)
    guard = world.spawn_unit(world.neutral, UnitType.GOLEM, (24.5, 19.5))
    observer = world.spawn_unit(0, UnitType.PEASANT, (28.5, 19.5))
    world.hold([guard.id])
    world.hold([observer.id])
    world.update_vision()
    assert world.is_visible(0, guard.tile) and not world.is_visible(1, guard.tile)
    return world, guard, observer


def advance(world, seconds):
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_an_unseen_guard_keeps_its_last_observed_warning_in_private_saved_and_online_memory():
    """Fog retains the observed point, while saves and each seat's own snapshot preserve only its knowledge."""
    world, guard, observer = warning_world()
    observed = guard.pos
    assert world.worker_knowledge[0].guard_warnings == {guard.id: observed}
    assert not world.worker_knowledge[1].guard_warnings
    world.move([observer.id], (44.5, 30.5))
    advance(world, 15)
    assert not world.is_visible(0, guard.tile)
    world.move([guard.id], (5.5, 5.5))
    advance(world, 3)
    assert guard.pos != observed and not world.is_visible(0, guard.tile)
    assert world.worker_knowledge[0].guard_warnings == {guard.id: observed}

    restored = World.from_dict(world.to_dict())
    assert restored.worker_knowledge[0].guard_warnings == {guard.id: observed}
    assert not restored.worker_knowledge[1].guard_warnings
    match = WarbandMatch(seed=81)
    match.world = restored
    match.begun = restored.to_dict()["terrain"]
    for seat in range(world.seats):
        client = World.from_dict(match.snapshot(seat)["world"])
        assert guard.id not in client.units, "a remembered warning must not reveal the hidden creature"
        assert client.worker_knowledge[0].guard_warnings == ({guard.id: observed} if seat == 0 else {})
        assert not client.worker_knowledge[1].guard_warnings


def test_revisiting_an_empty_last_seen_guard_tile_clears_its_warning():
    """A scout can dismiss stale danger by seeing the old position empty, without seeing the departed guard."""
    world, guard, observer = warning_world()
    old_tile = guard.tile
    world.move([observer.id], (44.5, 30.5))
    advance(world, 15)
    world.move([guard.id], (5.5, 5.5))
    advance(world, 15)
    assert guard.id in world.worker_knowledge[0].guard_warnings
    world.move([observer.id], (28.5, 19.5))
    advance(world, 15)
    assert world.is_visible(0, old_tile) and not world.is_visible(0, guard.tile)
    assert guard.id not in world.worker_knowledge[0].guard_warnings


def test_discovering_the_visible_guards_lair_replaces_the_broad_warning_with_the_known_encounter():
    """Once its lair is observed, the precise encounter watch replaces the guard's conservative warning."""
    from warband.sim import camps

    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2, scripted=True)
    camp = camps.place(world, (21, 18), [UnitType.GOLEM], 3200)
    guard = world.units[camp.guards[0]]
    observer = world.spawn_unit(0, UnitType.PEASANT, (28.5, 19.5))
    world.hold([observer.id])
    world.update_vision()
    assert world.is_visible(0, guard.tile)
    assert camp.lair not in world.worker_knowledge[0].encounters
    assert guard.id in world.worker_knowledge[0].guard_warnings

    world.reveal_all(0)
    assert camp.lair in world.worker_knowledge[0].encounters
    assert guard.id not in world.worker_knowledge[0].guard_warnings
    assert not world.worker_knowledge[1].encounters
    assert not world.worker_knowledge[1].guard_warnings
