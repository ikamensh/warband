"""The neutral gate measures real replacement losses and obtainable army clears."""

import random
from dataclasses import replace

import pytest

from tools.creep_report import SQUADS, Measurement, Measurements, ReportResult, SeatCoverage, encounter, gate_matches, gate_prepared
from warband.league import arena
from warband.brains.ai import Brain
from warband.brains.pro_ai import PRO, ProBrain
from warband.sim import camps
from warband.sim.model import World, dist
from warband.sim.rules import CAMP_ENCOUNTERS, SIM_DT, UPGRADES, BuildingType, Cost, Race, Terrain, UnitType, Upgrade


def test_finish_counts_camps_a_seat_laid_eyes_on():
    """Each side's discovery funnel includes only that side's scouting, even with different races."""
    world = World(56, 44, [[Terrain.GRASS] * 56 for _ in range(44)], 2, rng=random.Random(11),
                  races=[Race.HUMAN, Race.ORC])
    world.scripted = True
    den = camps.place_encounter(world, (10, 10), "wolf_den")
    nest = camps.place_encounter(world, (40, 30), "spider_nest")
    mound = camps.place_encounter(world, (24, 22), "troll_mound")
    measure = Measurements(world, ("human", "orc"))
    assert measure.finish(world) == []
    assert measure.discovered == {0: {}, 1: {}}
    # A scout walks up to the den alone: only it counts, while the nest and
    # the mound stand undiscovered.
    scout = world.spawn_unit(0, UnitType.FOOTMAN, (12.5, 10.5))
    world.hold([scout.id])
    for _ in range(int(5 / SIM_DT)):
        world.step()
        if den.lair in world.worker_knowledge[0].encounters:
            break
    assert den.lair in world.worker_knowledge[0].encounters
    assert nest.lair not in world.worker_knowledge[0].encounters
    assert mound.lair not in world.worker_knowledge[0].encounters
    assert measure.finish(world) == []
    assert measure.discovered == {0: {"Raid": 1}, 1: {}}
    # The other seat looks at the rest; its scout does not discover those
    # camps on behalf of seat zero.
    other = world.spawn_unit(1, UnitType.FOOTMAN, (40.5, 30.5))
    world.hold([other.id])
    eye = world.spawn_unit(1, UnitType.FOOTMAN, (24.5, 22.5))
    world.hold([eye.id])
    for _ in range(int(5 / SIM_DT)):
        world.step()
        if (nest.lair in world.worker_knowledge[1].encounters
                and mound.lair in world.worker_knowledge[1].encounters):
            break
    measure.finish(world)
    assert measure.discovered == {0: {"Raid": 1}, 1: {"Raid": 1, "Stronghold": 1}}
    first, second = measure.coverage(world)
    assert (first.race, second.race) == ("human", "orc")
    assert first.present == second.present == {"Raid": 2, "Stronghold": 1}
    assert first.discovered == {"Raid": 1}
    assert second.discovered == {"Raid": 1, "Stronghold": 1}


def test_the_prepared_gate_passes_profitable_clears_and_fails_the_rest():
    """Staged gate: an unprofitable or failed prepared clear fails, whatever else cleared."""
    good = Measurement(agent="pro", race="human", encounter="wolf_den", tier="Raid", bracket="prepared",
                       cleared=True, lost=2, loss_gold=1000, loss_lumber=100, gold=2700, lumber=650)
    assert gate_prepared([good]) == 0
    failed = Measurement(agent="pro", race="human", encounter="wolf_den", tier="Raid", bracket="prepared",
                         cleared=False, lost=2, loss_gold=1000, loss_lumber=100, gold=0, lumber=0)
    assert gate_prepared([good, failed]) == 1
    unprofitable = Measurement(agent="pro", race="human", encounter="wolf_den", tier="Raid", bracket="prepared",
                               cleared=True, lost=6, loss_gold=3100, loss_lumber=300, gold=2700, lumber=650)
    assert gate_prepared([unprofitable]) == 1


def test_a_prepared_gate_requires_some_prepared_coverage():
    """An early-only curve cannot claim the prepared accessibility gate passed."""
    early = Measurement("squad", "human", "wolf_den", "Raid", cleared=True, gold=1200, bracket="early")
    assert gate_prepared([early]) == 1
    assert gate_prepared([]) == 1


def test_the_whole_match_gate_fails_losses_untouched_maps_and_missing_clears():
    """Negative economics always fail; an idle, prepared opportunity requires a paid clear."""
    def row(agent, race, cleared, gold, loss_gold, lumber=0, loss_lumber=0):
        return Measurement(agent=agent, race=race, encounter="wolf_den", tier="Raid", cleared=cleared,
                           lost=0, loss_gold=loss_gold, loss_lumber=loss_lumber, gold=gold, lumber=lumber)
    coverage = [SeatCoverage(seat, "pro", race, {"Raid": 3}, {"Raid": 1}, {"Raid": 1})
                for seat, race in enumerate(("human", "orc"))]
    paid = [row("pro", "human", True, 2700, 1000, 650, 100),
            row("pro", "orc", True, 2700, 1000, 650, 100)]
    assert gate_matches([ReportResult(paid, coverage)]) == 0
    losing = [row("pro", "human", True, 2700, 3000, 650, 700)]
    assert gate_matches([ReportResult(losing, coverage)]) == 1
    clearless = [row("pro", "human", False, 0, 1000, 0, 100)]
    assert gate_matches([ReportResult(clearless, coverage)]) == 1
    assert gate_matches([ReportResult([], coverage)]) == 1
    # Even without a viable expedition window, losing workers to a camp fails.
    no_opportunity = [SeatCoverage(0, "pro", "human", {"Raid": 3})]
    assert gate_matches([ReportResult(losing, no_opportunity)]) == 1


def test_a_match_without_discovered_opportunities_does_not_require_a_clear():
    """A side cannot pursue a camp it never discovered; missing coverage is reported separately."""
    coverage = [SeatCoverage(seat, "pro", race, {"Raid": 3})
                for seat, race in enumerate(("human", "orc"))]
    assert gate_matches([ReportResult([], coverage)]) == 0
    # A discovered Ancient with no prepared force is also no feasible opportunity.
    coverage[0].discovered = {"Ancient": 1}
    assert gate_matches([ReportResult([], coverage)]) == 0


def test_unordered_match_results_keep_their_original_race_pairing(capsys):
    """A slow Human result finishing after the Orc result still belongs to the Human match."""
    human = ReportResult([], [SeatCoverage(0, "pro", "human", {"Raid": 1}, {"Raid": 1}, {"Raid": 1})],
                         arena.MatchSpec(seed=1, agents=("pro",), races=("human",)))
    orc = ReportResult([], [SeatCoverage(0, "pro", "orc", {"Raid": 1})],
                       arena.MatchSpec(seed=2, agents=("pro",), races=("orc",)))
    assert gate_matches([orc, human]) == 1
    output = capsys.readouterr().out
    assert "FAIL: pro/human" in output
    assert "FAIL: pro/orc" not in output


def readiness_world(*, with_camp=True, reveal=True, scattered=False, army_kind=UnitType.ARCHER):
    """A prepared army at home, one scouted camp, and an unprepared rival on open known ground."""
    world = World(72, 48, [[Terrain.GRASS] * 72 for _ in range(48)], 2,
                  races=[Race.HUMAN, Race.ORC], scripted=True)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (62, 40))
    camp = camps.place_encounter(world, (24, 20), "wolf_den") if with_camp else None
    if scattered:
        spots = [(x + i % 2, y + i // 2) for x, y in ((8.5, 10.5), (45.5, 10.5), (8.5, 33.5), (45.5, 33.5))
                 for i in range(4)]
    else:
        spots = [(8.5 + i % 4, 10.5 + i // 4) for i in range(16)]
    army = [world.spawn_unit(0, army_kind, point) for point in spots]
    world.spawn_unit(1, UnitType.FOOTMAN, (65.5, 44.5))
    if reveal:
        world.reveal_all(0)
    else:
        world.update_vision()
    profile = replace(PRO, scout=False, magic=False, push_after=600)
    brains = [ProBrain(seat, profile) for seat in range(world.seats)]
    return world, camp, army, brains


def test_discovery_is_feasible_only_when_that_side_has_a_prepared_free_force():
    """An observed camp becomes an opportunity after preparation, without borrowing its rival's army."""
    world, camp, army, brains = readiness_world()
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == {}
    world.time = 180
    measure.sample_opportunities(world, brains)
    first, second = measure.coverage(world)
    assert first.feasible == {"Raid": 1}
    assert second.feasible == second.discovered == {}
    # Retained wounded soldiers are not an expedition, despite their headcount.
    for unit in army:
        unit.hp = 1
    wounded = Measurements(world, ("pro", "pro"))
    wounded.sample_opportunities(world, brains)
    assert wounded.coverage(world)[0].feasible == {}


@pytest.mark.parametrize("policy", ["medium", "pro"])
@pytest.mark.parametrize("formation", ["cohesive", "scattered", "wounded"])
def test_feasible_expeditions_use_a_healthy_local_army_for_each_shipped_policy(policy, formation):
    """A map-wide headcount cannot fund separate small groups or wounded bodies as an army ready to clear."""
    world, _camp, army, brains = readiness_world(scattered=formation == "scattered",
                                              army_kind=UnitType.KNIGHT if formation == "wounded" else UnitType.ARCHER)
    world.time = 180
    if policy == "medium":
        brains = [Brain(seat) for seat in range(world.seats)]
    if formation == "wounded":
        for unit in army:
            unit.hp = int(.6 * unit.max_hp)
    measure = Measurements(world, (policy, policy))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == ({"Raid": 1} if formation == "cohesive" else {})


@pytest.mark.parametrize("duty", ["pvp", "defense", "tower"])
def test_a_sensible_pvp_or_defense_assignment_is_not_an_ignored_camp(duty):
    """A ready army needs to be free to creep; continuing an enemy push or answering a raid is valid."""
    world, camp, _army, brains = readiness_world(with_camp=duty != "pvp")
    world.time = 700
    if duty == "pvp":
        brains[0].think(world, random.Random(11))
        assert brains[0].attacking
        camp = camps.place_encounter(world, (24, 20), "wolf_den")
    elif duty == "defense":
        world.spawn_unit(1, UnitType.FOOTMAN, (8.5, 7.5))
    else:
        world.place_building(1, BuildingType.TOWER, (9, 6))
    world.reveal_all(0)
    assert camp.lair in world.worker_knowledge[0].encounters
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == {}
    assert gate_matches([ReportResult([], measure.coverage(world))]) == 0


def test_an_air_scouts_glimpse_across_unknown_ground_is_not_certified_army_access():
    """An air scout can see a camp whose approach the ground army has never scouted."""
    world, camp, _army, brains = readiness_world(reveal=False)
    world.time = 180
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (30.5, 24.5))
    world.update_vision()
    assert camp.lair in world.worker_knowledge[0].encounters
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    first = measure.coverage(world)[0]
    assert first.discovered == {"Raid": 1}
    assert first.feasible == {}


def test_unseen_guard_deaths_do_not_turn_an_unprepared_side_into_a_feasible_one():
    """A report may use watched casualties; it must not borrow hidden deaths from the authority world."""
    world, camp, army, brains = readiness_world()
    world.time = 180
    for unit in army[8:]:
        unit.hp = 0
    world.update_vision()  # the camp recedes into fog before any guard falls
    assert not world.is_visible(0, world.units[camp.guards[0]].tile)
    for uid in camp.guards:
        world.units[uid].hp = 0
    world.step()
    assert not world.worker_knowledge[0].fallen_guards
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == {}


def test_a_witnessed_empty_den_is_a_cleanup_opportunity_for_one_soldier():
    """Once every guard was watched falling, clearing the lair no longer needs a whole expedition."""
    world, camp, army, brains = readiness_world()
    world.time = 180
    for unit in army[1:]:
        unit.hp = 0
    for uid in camp.guards:
        world.units[uid].hp = 0
    world.step()
    assert sum(world.worker_knowledge[0].fallen_guards[camp.lair].values()) == len(camp.guards)
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == {"Raid": 1}
    army[0].hp = 0
    world.step()
    empty = Measurements(world, ("pro", "pro"))
    empty.sample_opportunities(world, brains)
    assert empty.coverage(world)[0].feasible == {}


def test_fresh_recruits_do_not_make_a_failed_committed_expedition_ready():
    """The army already at a camp is its cohort; fresh bodies at home cannot hide that cohort's losses."""
    world, camp, army, brains = readiness_world()
    world.time = 180
    brains[0].think(world, random.Random(11))
    assert brains[0].creeping == camp.lair
    for unit in army:
        unit.hp = 0
    world.step()
    for i in range(16):
        world.spawn_unit(0, UnitType.ARCHER, (8.5 + i % 4, 10.5 + i // 4))
    world.reveal_all(0)
    measure = Measurements(world, ("pro", "pro"))
    measure.sample_opportunities(world, brains)
    assert measure.coverage(world)[0].feasible == {}


def test_a_neutral_kill_is_counted_at_the_victims_replacement_price():
    """The report must price the actual casualty, including its lumber, rather than count all units equally."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (14, 10), "wolf_den")
    guard = world.units[camp.guards[0]]
    victim = world.spawn_unit(0, UnitType.ARCHER, (guard.x + .8, guard.y))
    victim.hp = 1
    price = victim.info.cost
    measure = Measurements(world, ("human", "idle"))
    world.hold([victim.id])
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if victim.id not in world.units:
            break
    row = measure.finish(world)[0]
    assert row.lost == 1
    assert (row.loss_gold, row.loss_lumber) == (price.gold, price.lumber)
    assert row.gold == row.lumber == 0


def test_a_bystander_loss_is_not_a_clear_when_another_seat_claims_the_camp():
    """An incidental victim earns neither the other expedition's clear nor its bounty."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(11))
    world.scripted = True
    camp = camps.place_encounter(world, (14, 10), "wolf_den")
    guard = world.units[camp.guards[0]]
    victim = world.spawn_unit(0, UnitType.PEASANT, (guard.x + .8, guard.y))
    victim.hp = 1
    measure = Measurements(world, ("bystander", "expedition"))
    world.hold([victim.id])
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if victim.id not in world.units:
            break
    army = [world.spawn_unit(1, UnitType.KNIGHT, (8.5 + i % 4, 9.5 + i // 4)) for i in range(16)]
    world.reveal_all(1)
    world.attack_move([unit.id for unit in army], camp.posts[0])
    for _ in range(int(30 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if camp.cleared:
            break
    rows = {row.agent: row for row in measure.finish(world)}
    assert camp.cleared
    assert rows["expedition"].cleared
    assert not rows["bystander"].cleared
    assert rows["bystander"].lost == rows["bystander"].lost_workers == 1


@pytest.mark.slow
@pytest.mark.parametrize("cleared", [False, True])
def test_a_former_camp_participants_later_pvp_siege_death_is_not_a_camp_loss(cleared):
    """Slow: a scout leaves a real encounter, then dies to its own siege at a distant PvP battle."""
    world = World(72, 44, [[Terrain.GRASS] * 72 for _ in range(44)], 2,
                  scripted=True, rng=random.Random(11))
    camp = camps.place(world, (12, 12), [UnitType.TROLL], 500)
    scout = world.spawn_unit(0, UnitType.ARCHER, (8.5, 13.5))
    measure = Measurements(world, ("human", "idle"))
    world.reveal_all(0)
    world.attack([scout.id], camp.lair)
    for _ in range(int(5 / SIM_DT)):
        world.step()
        events = world.take_events()
        measure.observe(world, events)
        if any(e.kind == "hit" and e.entity == scout.id and e.other == camp.lair for e in events):
            break
    assert (0, camp.lair) in measure.rows
    world.move([scout.id], (49.5, 17.5))
    for _ in range(int(25 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if dist(scout.pos, (49.5, 17.5)) < .1:
            break
    assert scout.id in world.units and dist(scout.pos, (49.5, 17.5)) < .1
    world.hold([scout.id])
    if cleared:
        army = [world.spawn_unit(0, UnitType.KNIGHT, (8.5 + i % 4, 9.5 + i // 4)) for i in range(16)]
        world.attack_move([unit.id for unit in army], camp.posts[0])
        for _ in range(int(60 / SIM_DT)):
            world.step()
            measure.observe(world, world.take_events())
            if camp.cleared:
                break
    assert camp.cleared == cleared
    row = measure.rows[0, camp.lair]
    losses = (row.lost, row.loss_gold, row.loss_lumber)
    hall = world.place_building(1, BuildingType.TOWN_HALL, (50, 16))
    siege = world.spawn_unit(0, UnitType.CATAPULT, (43.5, 17.5))
    world.attack([siege.id], hall.id)
    friendly_hit = False
    for _ in range(int(25 / SIM_DT)):
        world.step()
        events = world.take_events()
        measure.observe(world, events)
        friendly_hit |= any(e.kind == "hit" and e.entity == siege.id and e.other == scout.id
                            and e.player == 0 for e in events)
        if scout.id not in world.units:
            break
    assert friendly_hit and scout.id not in world.units
    assert (row.lost, row.loss_gold, row.loss_lumber) == losses


@pytest.mark.slow
@pytest.mark.parametrize("cleared_before_impact", [False, True])
@pytest.mark.parametrize("siege_order", ["attack", "hold"])
def test_camp_directed_siege_costs_include_friendly_bystanders(cleared_before_impact, siege_order):
    """Slow: camp siege kills a new ally, including a stone still airborne when a wounded lair falls."""
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2,
                  scripted=True, rng=random.Random(11))
    camp = camps.place(world, (12, 12), [UnitType.WOLF], 500)
    army = [world.spawn_unit(0, UnitType.KNIGHT, (16.5 + i % 2, 16.5 + i // 2)) for i in range(4)]
    measure = Measurements(world, ("human", "idle"))
    world.reveal_all(0)
    world.attack([unit.id for unit in army], camp.guards[0])
    for _ in range(int(10 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if camp.guards[0] not in world.units:
            break
    assert not camps.guards(world, camp) and camp.lair in world.buildings
    world.move([unit.id for unit in army if unit.id in world.units], (25.5, 20.5))
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
    if siege_order == "hold":
        # A real intruder keeps the den active while its siege crew holds
        # outside the watch. This soldier cannot reach the wall with its blade.
        intruder = world.spawn_unit(0, UnitType.KNIGHT, (17.0, 17.0))
        world.hold([intruder.id])
    siege = world.spawn_unit(0, UnitType.CATAPULT, (6.5, 13.5))
    if cleared_before_impact:
        world.buildings[camp.lair].hp = 1  # an encounter already close to completion
    if siege_order == "attack":
        world.attack([siege.id], camp.lair)
    else:
        world.hold([siege.id])
    for _ in range(int(3 / SIM_DT)):
        world.step()
        measure.observe(world, world.take_events())
        if any(p.source == siege.id for p in world.projectiles.values()):
            break
    assert any(p.source == siege.id for p in world.projectiles.values())
    # A wounded reinforcement arrives at the wall after the crew committed
    # its stone. Automatic siege could not avoid an ally absent at launch.
    ally = world.spawn_unit(0, UnitType.CLERIC, (11.5, 13.5))
    ally.hp, ally.cooldown = 1, 10
    world.hold([ally.id])
    if cleared_before_impact:
        finisher = world.spawn_unit(0, UnitType.KNIGHT, (13.5, 11.4))
        world.attack([finisher.id], camp.lair)
        world.move([siege.id], (4.5, 4.5))
    friendly_hit = False
    saw_clear_before_loss = False
    for _ in range(int(25 / SIM_DT)):
        world.step()
        events = world.take_events()
        measure.observe(world, events)
        friendly_hit |= any(e.kind == "hit" and e.entity == siege.id and e.other == ally.id
                            and e.player == 0 for e in events)
        saw_clear_before_loss |= camp.cleared and ally.id in world.units
        if ally.id not in world.units:
            break
    assert friendly_hit and ally.id not in world.units and camp.cleared == cleared_before_impact
    assert saw_clear_before_loss == cleared_before_impact
    row = measure.rows[0, camp.lair]
    assert row.lost == 1
    assert (row.loss_gold, row.loss_lumber) == (ally.info.cost.gold, ally.info.cost.lumber)
    assert gate_matches([ReportResult([row])]) == 1


@pytest.mark.slow
def test_encounter_settles_airborne_camp_stones_without_changing_clear_time(monkeypatch):
    """Slow: the real staged fight must price a reinforcement struck after completion by its last stones."""
    monkeypatch.setitem(SQUADS, "wolf_outpost", ((UnitType.CATAPULT, 8),))
    original_place = camps.place_encounter

    def empty_outpost(world, point, identity):
        camp = original_place(world, point, identity)
        for uid in camp.guards:
            world.units[uid].hp = 0  # an already-won guard fight; the crew still must clear the den
        return camp

    monkeypatch.setattr(camps, "place_encounter", empty_outpost)
    before = encounter(1000, "human", "wolf_outpost")
    assert before.cleared
    original_observe = Measurements.observe
    arrivals = []

    def reinforcement_after_completion(measure, world, events):
        original_observe(measure, world, events)
        if not arrivals and world.camps[0].cleared:
            pending = [p for p in world.projectiles.values() if p.player == 0 and p.kind == "stone"]
            if pending:
                # The encounter has finished. A wounded reinforcement reaches
                # the first stone's actual ground aim while that stone is airborne.
                ally = world.spawn_unit(0, UnitType.ARCHER, pending[0].aim)
                ally.hp, ally.cooldown = 1, 100
                world.hold([ally.id])
                arrivals.append((world, ally))

    monkeypatch.setattr(Measurements, "observe", reinforcement_after_completion)
    after = encounter(1000, "human", "wolf_outpost")
    assert len(arrivals) == 1, "the real staged fight needs a camp stone still airborne at completion"
    world, ally = arrivals[0]
    assert ally.id not in world.units
    assert after.cleared and after.seconds == before.seconds
    assert after.lost == before.lost + 1
    assert after.loss_gold == before.loss_gold + ally.info.cost.gold
    assert after.loss_lumber == before.loss_lumber + ally.info.cost.lumber


@pytest.mark.slow
@pytest.mark.parametrize("race", list(Race))
@pytest.mark.parametrize("identity", list(CAMP_ENCOUNTERS))
def test_every_race_can_clear_each_encounter_profitably_with_common_units(race, identity):
    """Slow: a complete multi-unit combat encounter through real orders and fixed simulation steps."""
    row = encounter(1000, race.value, identity)
    info = CAMP_ENCOUNTERS[identity]
    assert row.bracket == "prepared"
    assert row.cleared, row
    assert (row.gold, row.lumber) == (info.gold, info.lumber)
    assert row.gold + row.lumber >= row.loss_gold + row.loss_lumber, row
    assert row.seconds > 0


def test_bracket_fights_run_under_their_names():
    """Early and mid brackets stage smaller magic-free forces than the prepared expedition."""
    early = encounter(11, "human", "wolf_den", minutes=0.1, bracket="early")
    mid = encounter(11, "human", "wolf_den", minutes=0.1, bracket="mid")
    assert (early.bracket, mid.bracket) == ("early", "mid")
    assert early.preparation < mid.preparation


def test_prepared_stronghold_quotes_include_the_price_of_required_research(monkeypatch):
    """Research that makes the fight accessible must be priced; raising that price raises the preparation quote."""
    before = encounter(1000, "dwarf", "troll_toll", minutes=0)
    armor = UPGRADES[Upgrade.ARMOR_1]
    monkeypatch.setitem(UPGRADES, Upgrade.ARMOR_1,
                        replace(armor, cost=Cost(armor.cost.gold + 100, armor.cost.lumber)))
    after = encounter(1000, "dwarf", "troll_toll", minutes=0)
    assert after.preparation == before.preparation + 100
