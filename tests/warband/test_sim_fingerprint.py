"""The parity fingerprint reliably reaches the race-specific simulation it promises to cover."""

import pytest

from warband.sim.rules import SIM_DT, UnitType


@pytest.mark.parametrize("kind", [UnitType.SAPPER, UnitType.TREANT])
def test_own_unit_fingerprint_scenario_exercises_its_distinct_behavior(kind):
    """A fixed public-order encounter covers actual blasts or forest traversal without depending on AI tech timing."""
    from tools.sim_fingerprint import at_work, own_unit_world
    from warband.sim.model import World
    world = own_unit_world(kind)
    worked = False
    damaged = False
    restored = None
    for _ in range(int(60 / SIM_DT)):
        world.step()
        events = world.take_events()
        if restored is not None:
            restored.step()
            restored.take_events()
        elif world.time >= 1:
            restored = World.from_dict(world.to_dict())
        worked |= at_work(world, events, kind)
        damaged |= any(event.kind == "hit" and event.source_type == kind.value for event in events)
        if worked and damaged:
            break
    assert worked and damaged
    assert restored is not None and world.to_dict() == restored.to_dict()
