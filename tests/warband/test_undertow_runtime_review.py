"""Public-order regressions for the Undertow review's ordinary-player deviations.

These walk authored mission boards, fight real units and build real camps. Whole
mission scenarios are slow; the keeper death/rescue combat fits the fast tier.
"""

import pytest

from tools import play_undertow as solver
from warband.sim.model import Hold, dist
from warband.sim.rules import BuildingType as B, SIM_DT, UnitType as U, Upgrade
from warband.story.mission_scene import build_world
from warband.story.landmarks import occupied
from warband.story.new_campaign import CAMPAIGN, MESA
from warband.story import undertow_dialogue as dialogue


def advance(run, seconds, *, until=lambda run: False, act=None):
    """Advance only the actual simulation and mission script, stopping at a public condition."""
    for tick in range(round(seconds / SIM_DT)):
        if act is not None and tick % round(1 / SIM_DT) == 0:
            act(run)
        run.world.step()
        run.tick()
        if until(run):
            return
    assert until(run), f"condition not reached in {seconds}s: t={run.time}, objectives={run.state}"


def on_mesa(unit):
    return MESA[0] <= unit.x <= MESA[2] and MESA[1] <= unit.y <= MESA[3]


def caravan_at_mesa():
    """Pack the ruins, blast the blocked ford, and walk the caravan up to the mesa."""
    run = build_world(CAMPAIGN.mission("undertow_caravan"), flags={})
    world = run.world
    world.hold([unit.id for unit in run.soldiers(0)])
    for ruin in [building for building in world.buildings.values() if building.player == 2]:
        world.salvage([worker.id for worker in run.units(0, U.PEASANT)], ruin.id)
        advance(run, 120, until=lambda run: ruin.id not in world.buildings)
    advance(run, 1, until=lambda run: run.state["strip"] == "done")
    world.move([unit.id for unit in run.units(0)], (28.5, 23.5))
    advance(run, 120, until=lambda run: "sappers" in run.fired)
    rockfall = list(run.get("rockfall"))
    world.attack([unit.id for unit in run.units(0, U.SAPPER)], rockfall[0])
    advance(run, 120, until=lambda run: not any(rock in world.buildings for rock in rockfall))
    world.move([unit.id for unit in run.units(0)], tuple(run.get("mesa_center")))
    advance(run, 120, until=lambda run: sum(on_mesa(worker) for worker in run.units(0, U.PEASANT)) >= 5)
    return run


def caravan_camp_with_departed_drovers():
    """Build the mesa camp with one worker after the other drovers leave it."""
    run = caravan_at_mesa()
    world = run.world
    advance(run, 1, until=lambda run: run.state["drovers"] == "done")
    workers = run.units(0, U.PEASANT)
    builder = min((worker for worker in workers if on_mesa(worker)), key=lambda worker: dist(worker.pos, (47.5, 20.5)))
    departing = [worker for worker in workers if worker.id != builder.id]
    world.move([worker.id for worker in departing], (37.5, 23.5))
    advance(run, 120, until=lambda run: all(not on_mesa(worker) for worker in departing if worker.id in world.units))
    world.hold([worker.id for worker in departing if worker.id in world.units])
    world.move([unit.id for unit in run.soldiers(0)], (40.5, 23.5))
    advance(run, 30, until=lambda run: all(not on_mesa(unit) for unit in run.soldiers(0)))
    plans = [(B.TOWN_HALL, (46, 19)), (B.FARM, (46, 24)), (B.FARM, (50, 24)), (B.FARM, (54, 24))]
    for kind, position in plans:
        world.build(builder.id, kind, position)
        advance(run, 120, until=lambda run: (site := world.building_at(position)) is not None and site.done)
    advance(run, 1, until=lambda run: run.state["camp"] == "done")
    return run, builder


@pytest.mark.slow
def test_caravan_cannot_win_with_drovers_who_already_left_the_mesa():
    """Slow: real salvage/crossing/build orders expose a historical arrival tick at later victory."""
    run, _ = caravan_camp_with_departed_drovers()
    assert sum(on_mesa(worker) for worker in run.units(0, U.PEASANT)) < 5
    assert run.state["drovers"] == "open"
    assert not run.won, "the settlement still needs five living drovers on the mesa"
    run.world.move([worker.id for worker in run.units(0, U.PEASANT)], tuple(run.get("mesa_center")))
    advance(run, 120, until=lambda run: run.won)
    assert sum(on_mesa(worker) for worker in run.units(0, U.PEASANT)) >= 5


@pytest.mark.slow
def test_caravan_cannot_win_with_a_camp_that_was_already_destroyed():
    """Slow: sappers destroy a completed farm before the real drovers return to the mesa."""
    run, _ = caravan_camp_with_departed_drovers()
    world = run.world
    farm = next(farm for farm in run.buildings(0, B.FARM) if farm.pos == (54, 24))
    for _ in range(2):
        if farm.id not in world.buildings:
            break  # the first blast can already finish a farm damaged during settlement
        saboteur = run.spawn(1, [U.SAPPER], farm.center)[0]
        world.attack([saboteur.id], farm.id)
        advance(run, 15, until=lambda run: saboteur.id not in world.units)
    advance(run, 15, until=lambda run: farm.id not in world.buildings)
    world.move([worker.id for worker in run.units(0, U.PEASANT)], tuple(run.get("mesa_center")))
    advance(run, 120, until=lambda run: sum(on_mesa(worker) for worker in run.units(0, U.PEASANT)) >= 5)
    assert run.state["camp"] == "open"
    assert not run.won, "the settlement needs its three farms standing now"


@pytest.mark.slow
def test_caravan_loses_after_the_last_straggler_dies_without_worker_production():
    """Slow: the original drovers and their once-only replacements die in the real north camp."""
    run = build_world(CAMPAIGN.mission("undertow_caravan"), flags={})
    world = run.world
    world.hold([unit.id for unit in run.soldiers(0)])
    sent = set()

    def march_new_workers(run):
        # Keep the deliberate march active: otherwise automatic workers retreat
        # once the hands-off window expires after arrival.
        ids = [worker.id for worker in run.units(0, U.PEASANT)]
        if ids:
            world.move(ids, (38.5, 11.5))
            sent.update(ids)

    advance(run, 300, until=lambda run: "stragglers" in run.fired and not run.units(0, U.PEASANT),
            act=march_new_workers)
    assert len(sent) == 9 and run.unit("brakk") is not None and world.players[0].alive
    assert run.hall(0) is None
    assert run.lost is not None, "no living builder or worker producer can finish the camp"


@pytest.mark.parametrize("mission_id, keeper", [("undertow_mill", "issa"), ("undertow_weight", "dagna")])
def test_a_keeper_returns_from_the_first_death_but_the_second_death_loses(mission_id, keeper):
    """The hall rescues a keeper once; a second real combat death must end their mission."""
    run = build_world(CAMPAIGN.mission(mission_id), flags={})
    world = run.world
    original = run.unit(keeper)
    enemies = run.spawn(1, [U.TROLL] * 2, original.pos)
    world.attack([unit.id for unit in enemies], original.id)
    advance(run, 10, until=lambda run: (rescued := run.unit(keeper)) is not None and rescued.id != original.id)
    rescued = run.unit(keeper)
    assert run.lost is None and rescued.hp == rescued.max_hp // 2
    enemies = run.spawn(1, [U.TROLL] * 2, rescued.pos)
    world.attack([unit.id for unit in enemies], rescued.id)
    advance(run, 10, until=lambda run: run.unit(keeper) is None)
    assert run.hall(0) is not None
    assert run.lost is not None, "a dead keeper cannot keep leading the story"


@pytest.mark.slow
@pytest.mark.parametrize("destroyed", ["pylon", "vault"])
def test_mill_remembers_deliberate_shuttering_separately_from_a_lost_vault(destroyed):
    """Slow: march on the real pylon, or let an attacking band destroy the real village vault."""
    run = build_world(CAMPAIGN.mission("undertow_mill"), flags={})
    world = run.world
    if destroyed == "pylon":
        world.attack([unit.id for unit in run.soldiers(0)], run.get("mill_pylon"))
    else:
        vault = world.buildings[run.get("mill_vault_id")]
        enemies = run.spawn(1, [U.TROLL] * 2, vault.center)
        world.attack([unit.id for unit in enemies], vault.id)
    advance(run, 60, until=lambda run: bool(run.get("mill_decided")))
    flags = run.remembered()
    assert flags["undertow_mill_vault"] is False
    assert flags["undertow_mill_shuttered"] is (destroyed == "pylon")
    assert flags["undertow_mill_lost"] is (destroyed == "vault")


@pytest.mark.slow
def test_grove_attack_move_routes_the_crew_and_queues_issas_warrant_aftermath():
    """Slow: the ordinary army assault follows the authored road and destroys the woodcutters' mill."""
    run = build_world(CAMPAIGN.mission("undertow_grove"), flags={})
    world = run.world
    world.hold([run.get("wrenna")] + [worker.id for worker in run.units(0, U.PEASANT)])
    world.attack_move([unit.id for unit in run.soldiers(0) if unit.id != run.get("wrenna")],
                      tuple(run.get("cutter_camp")))
    advance(run, 180, until=lambda run: run.get("mill_id") not in world.buildings or bool(run.get("parleyed")))
    assert not run.get("parleyed"), "an army ordered to attack must be allowed to fight"
    assert run.get("mill_id") not in world.buildings
    advance(run, 1, until=lambda run: "grove_plan" in run.fired)
    assert dialogue.GROVE_ROUT_AFTERMATH in run.pending, "the violent route still must reveal Issa's own order"


@pytest.mark.slow
def test_razing_tarnlocks_hall_stops_new_bands_but_requires_clearing_existing_attackers():
    """Slow: the starting catapult flanks the hall while soldiers wait at the seam and a worker caps it."""
    run = build_world(CAMPAIGN.mission("undertow_weight"), flags={})
    world = run.world
    catapult = run.units(0, U.CATAPULT)[0]
    world.move([catapult.id], (44.5, 38.5))
    world.move([catapult.id], (29.5, 47.5), queue=True)
    world.attack([catapult.id], run.get("enemy_hall"), queue=True)
    world.move([unit.id for unit in run.soldiers(0) if unit.id != catapult.id], (54.5, 6.5))
    workers = run.units(0, U.PEASANT)
    world.hold([worker.id for worker in workers])
    world.move([workers[0].id], (53.0, 12.0))
    ordered = False

    def cap(run):
        nonlocal ordered
        if not ordered and world.can_place(B.VAULT, tuple(run.get("seam_rift")), 0, builder=workers[0].id) is None:
            world.build(workers[0].id, B.VAULT, tuple(run.get("seam_rift")))
            ordered = True

    advance(run, 240, until=lambda run: bool(run.get("siege_broken")), act=cap)
    assert run.units(1), "the flanking attack leaves live siege attackers in Tarnlock"
    assert not run.won, "destroying the hall does not remove its existing attack bands"
    assert "confession" in run.fired and dialogue.WEIGHT_CONFESSION in run.pending
    assert run.get("seam_settled") == "cap", "waiting soldiers must not overwrite the completed cap"

    def clear(run):
        solver.answer(run, "seam_intent", "cap")
        solver.train(run, B.BARRACKS, U.FOOTMAN, 12)
        visible = [unit for unit in run.units(1) if world.is_visible(0, unit.tile)]
        if visible:
            target = min(visible, key=lambda unit: dist(unit.pos, tuple(run.get("weight_target"))))
            solver.cast_at(run, Upgrade.FLAME_STRIKE, target.pos)
        solver.fight(run, tuple(run.get("weight_target")), exclude=(run.get("dagna"),))

    advance(run, 300, until=lambda run: run.won or run.lost is not None, act=clear)
    assert run.won and run.lost is None
    assert "band_3" not in run.fired, "a razed siege headquarters cannot keep sending reinforcements"


def test_a_seam_scout_does_not_complete_the_settlement_objective():
    """Reaching the face before its siege is broken is scouting, not a closed seam."""
    run = build_world(CAMPAIGN.mission("undertow_weight"), flags={})
    world = run.world
    world.hold([worker.id for worker in run.units(0, U.PEASANT)])
    world.move([run.units(0, U.ARCHER)[0].id], (51.5, 6.5))
    advance(run, 30, until=lambda run: occupied(run, "seam"))
    assert run.state["seam"] == "open"
    assert not run.get("seam_settled") and run.get("undertow_seam_guarded") is False
