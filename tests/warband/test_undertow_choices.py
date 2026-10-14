"""Scouting is not a permanent commitment to a campaign's physical choice."""

import pytest

from tools import play_undertow as solver
from warband.sim.model import Harvest, Hold, dist
from warband.sim.rules import BuildingType as B, Terrain, UnitType as U, Upgrade
from warband.story.landmarks import occupied
from warband.story.mission_scene import build_world
from warband.story.new_campaign import CAMPAIGN, STRIP, STRIP_NEEDED


@pytest.mark.slow
def test_grove_scout_can_choose_cut_while_the_starting_garrison_stays_home() -> None:
    """Slow: a gatherer's real walk to parley and harvesting the authored strip must not count
    soldiers already at home as a new order to choose the whole-grove bloom.
    """
    run = build_world(CAMPAIGN.mission("undertow_grove"), flags={})
    world = run.world
    gatherers = run.units(0, U.PEASANT)
    world.hold([unit.id for unit in gatherers])
    world.move([gatherers[0].id], (29.5, 29.5))
    solver.play_until(run, lambda r: "parley" in r.fired, seconds=120)
    solver.play_until(run, lambda r: "grove_plan" in r.fired, seconds=2)
    solver.answer(run, "grove_intent", "cut")
    world.stop([unit.id for unit in gatherers])

    def fell(r) -> None:
        remaining = [tile for tile in STRIP if world.terrain_at(tile) is Terrain.TREES]
        for index, gatherer in enumerate(r.units(0, U.PEASANT)):
            current = next((order.target for order in gatherer.orders if isinstance(order, Harvest)), None)
            if gatherer.carrying is None and current not in remaining and remaining:
                world.harvest([gatherer.id], remaining[index % len(remaining)])

    fell(run)
    solver.play_until(run, lambda r: bool(r.get("bloom_started")), seconds=240, act=fell)
    assert sum(world.terrain_at(tile) is not Terrain.TREES for tile in STRIP) >= STRIP_NEEDED
    assert run.get("undertow_grove_cut") is True


@pytest.mark.slow
def test_seam_scouting_and_withdrawing_does_not_close_the_face_after_the_siege() -> None:
    """Slow: a real scout round trip and siege counterattack leave the seam unguarded. A historical
    objective tick cannot close its face until soldiers actually return and hold the landmark.
    """
    run = build_world(CAMPAIGN.mission("undertow_weight"), flags={})
    world = run.world
    world.hold([unit.id for unit in run.units(0, U.PEASANT)])
    archer = run.units(0, U.ARCHER)[0]
    world.move([archer.id], (51.5, 6.5))
    solver.play_until(run, lambda r: occupied(r, "seam"), seconds=120,
                      act=lambda r: solver.train(r, B.BARRACKS, U.FOOTMAN, 12))
    assert run.state["seam"] == "open", "a scout has not closed the face"
    world.move([archer.id], (9.5, 9.5))
    solver.play_until(run, lambda r: archer.x < 15, seconds=120,
                      act=lambda r: solver.train(r, B.BARRACKS, U.FOOTMAN, 12))
    assert not occupied(run, "seam")
    catapult = run.units(0, U.CATAPULT)[0]
    world.move([catapult.id], (44.5, 38.5))
    world.move([catapult.id], (29.5, 47.5), queue=True)
    world.attack([catapult.id], run.get("enemy_hall"), queue=True)

    def counterattack(r) -> None:
        solver.answer(r, "seam_intent", "guard")
        dagna = r.unit("dagna")
        if dagna is not None and not dagna.orders:
            world.move([dagna.id], (8.5, 22.5))
        solver.train(r, B.BARRACKS, U.FOOTMAN, 12)
        automatic = [worker.id for worker in r.units(0, U.PEASANT)
                     if not worker.orders or isinstance(worker.order, Harvest) and worker.order.auto]
        if automatic:
            world.hold(automatic)
        damaged = [building for building in r.buildings(0, B.VAULT) + r.buildings(0, B.TOWN_HALL)
                   if building.hp < building.max_hp]
        free = [worker for worker in r.units(0, U.PEASANT)
                if not worker.hidden and all(isinstance(order, Hold) for order in worker.orders)]
        if damaged and free:
            world.repair([free[0].id], damaged[0].id)
        visible = [unit for unit in r.units(1) if world.is_visible(0, unit.tile)]
        if visible:
            target = min(visible, key=lambda unit: dist(unit.pos, tuple(r.get("weight_target"))))
            solver.cast_at(r, Upgrade.FLAME_STRIKE, target.pos)
        solver.fight(r, tuple(r.get("weight_target")), exclude=(r.get("dagna"), catapult.id))

    solver.play_until(run, lambda r: bool(r.get("siege_broken")) and r.state["siege"] == "done",
                      seconds=900, act=counterattack)
    world.step()
    run.tick()
    assert not occupied(run, "seam")
    assert not run.won and not run.get("seam_settled"), "a departed scout cannot close the seam"
    world.move([unit.id for unit in run.soldiers(0)], (54.5, 6.5))
    solver.play_until(run, lambda r: r.won, seconds=180)
    assert occupied(run, "seam") and run.get("seam_settled") == "guard"
    assert run.get("undertow_seam_guarded") is True and run.state["seam"] == "done"
