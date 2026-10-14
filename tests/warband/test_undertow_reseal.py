"""The resealed Chain needs its Keystone standing when the battle ends."""

import pytest

from warband.sim.rules import BuildingType, SIM_DT, UnitType
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN


def advance_until(run, condition, seconds: float) -> None:
    """Advance the real rules and script until a public mission condition holds."""
    for _ in range(round(seconds / SIM_DT)):
        if condition():
            return
        assert run.lost is None, run.lost
        run.world.step()
        run.tick()
    assert condition(), f"condition unmet at mission time {run.time:g}"


@pytest.mark.slow
def test_reseal_requires_the_keystone_to_stand_and_a_rebuilt_one_can_finish() -> None:
    """Slow: real repairs, the final assault destroying the Keystone, a counterattack and rebuilding
    play through the authored Maw. Historical completion of repairs cannot reseal an empty crater;
    an ordinary new Mage Tower on the same footprint restores the player's route to victory.
    """
    run = build_world(CAMPAIGN.mission("undertow_maw"), flags={})
    world = run.world
    position = tuple(run.get("keystone_pos"))
    keystone = world.building_at(position)
    workers = run.units(0, UnitType.PEASANT)
    world.repair([worker.id for worker in workers[:3]], keystone.id)
    advance_until(run, lambda: "keystone_full" in run.fired, 90)
    assert run.get("ending_path") == "sealed"

    world.move([worker.id for worker in workers], (37.5, 11.5))
    world.hold([unit.id for unit in run.soldiers(0)])
    advance_until(run, lambda: keystone.id not in world.buildings, 120)
    # Issa remains at the camp while the other soldiers answer the final assault.
    army = [unit.id for unit in run.soldiers(0) if unit.id != run.get("issa")]
    world.attack_move(army, (39.5, 29.5))
    advance_until(run, lambda: all(unit_id not in world.units for unit_id in run.get("final_band")), 180)
    assert world.building_at(position) is None
    assert not run.won and not run.get("maw_resolved"), "an absent Keystone cannot reseal the Chain"

    surviving_workers = run.units(0, UnitType.PEASANT)
    world.move(army, (33.5, 31.5))
    advance_until(run, lambda: world.can_place(BuildingType.MAGE_TOWER, position, 0,
                                               builder=surviving_workers[0].id) is None, 60)
    world.build(surviving_workers[0].id, BuildingType.MAGE_TOWER, position)
    advance_until(run, lambda: world.building_at(position) is not None, 90)
    rebuilt = world.building_at(position)
    assert rebuilt.id != keystone.id
    world.repair([worker.id for worker in surviving_workers[1:3]], rebuilt.id)
    advance_until(run, lambda: run.won, 120)
    assert rebuilt.done and rebuilt.hp == rebuilt.max_hp
    assert run.get("maw_resolved") == "sealed"
    assert run.remembered() == {
        "undertow_ending_sealed": True,
        "undertow_ending_open": False,
        "undertow_ending_ground": False,
    }
