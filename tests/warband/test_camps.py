"""Creature camps: the neutral seat, the rules that make a camp a decision, and the brains that clear one.

The load-bearing claims, in the order the design rests on them: the wilds are a seat like no other and
are left out of everything a seat is counted for; a camp rouses as a group, so it cannot be pulled apart
one guard at a time; it leashes, so it cannot be dragged into somebody else's fight; it resets, so a push
that breaks off half way paid for nothing; and tearing the lair down stops all of that for good and pays
out the hoard.
"""

import math
import random

import pytest

from warband.brains.ai import guarded, known_camps, known_enemy_buildings
from warband.sim import camps, mapgen
from warband.sim.model import Attack, Move, World, dist, hypot, tile_center
from warband.sim.rules import (CAMP_CALM, CAMP_HOLD, CAMP_WATCH, REGEN_CALM, SIM_DT, BuildingType, Layout, Terrain,
                               UnitType)


def flat_world(width: int = 40, height: int = 32, players: int = 2) -> World:
    return World(width, height, [[Terrain.GRASS] * width for _ in range(height)], players, rng=random.Random(1))


def run(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def a_camp(world: World, at=(20, 16), roster=(UnitType.WOLF, UnitType.WOLF, UnitType.WOLF), hoard=500):
    return camps.place(world, at, list(roster), hoard)


def a_shifted_watch_camp(world: World):
    """A guard camp whose watch stands ten tiles off its den, scouted and undisturbed.

    Seat 0's unarmed scout lays eyes on the den without rousing it, so the encounter is
    remembered; the guards fall with neutral credit, so no payout or clear follows and the
    marches below cross no living interference -- only remembered ground.
    """
    camp = camps.place(world, (20, 18), [UnitType.WOLF, UnitType.WOLF], 500, watch=(21.5, 29.5))
    site = camps.centre(world, camp)
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (site[0], site[1] - 7.5))
    world.update_vision()
    assert camp.lair in world.worker_knowledge[0].encounters
    lair = world.buildings[camp.lair]
    for uid in list(camp.guards):
        world._hit(world.units[uid], 10000, player=world.neutral, source=lair.id,
                    source_type=BuildingType.LAIR.value)
    assert not camp.cleared
    return camp, site


# -- The neutral seat ------------------------------------------------------------------


def test_the_wilds_are_a_seat_past_the_playing_ones_and_own_the_creatures() -> None:
    world = flat_world()
    assert world.seats == 2 and len(world.players) == 3
    assert world.neutral == 2 and world.players[world.neutral].neutral
    camp = a_camp(world)
    assert all(world.units[uid].player == world.neutral for uid in camp.guards)
    assert world.buildings[camp.lair].player == world.neutral


def test_the_wilds_never_win_are_never_eliminated_and_carry_no_supply() -> None:
    world = flat_world(players=2)
    a_camp(world)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.spawn_unit(0, UnitType.PEASANT, (8.0, 8.0))
    run(world, 1.0)
    # The one seat with anything left wins, and the creatures standing on the map are not a second side.
    assert world.winner == 0
    assert world.supply(world.neutral) == (0, 0)
    assert world.players[world.neutral].alive


def test_a_creature_that_falls_is_nobodys_loss_and_the_wilds_stay_in_the_game() -> None:
    world = flat_world()
    camp = a_camp(world)
    guard = world.units[camp.guards[0]]
    guard.hp = 0
    run(world, 0.1)
    assert camp.guards[0] not in world.units
    assert world.players[world.neutral].alive and world.winner is None


def test_the_brains_hunt_rivals_not_creatures() -> None:
    """Endgame with one rival peasant left and a camp in sight: winning needs the peasant, not the den."""
    from warband.brains.ai import Brain
    from warband.brains.pro_ai import PRO, ProBrain
    from warband.sim.rules import Difficulty

    world = flat_world()
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    rival = world.spawn_unit(1, UnitType.PEASANT, (30.5, 20.5))
    camp = a_camp(world, at=(10, 10), roster=(UnitType.TROLL, UnitType.WOLF))
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (30.5, 21.5))
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 12.5))
    world.update_vision()
    assert world.is_visible(0, rival.tile)
    assert all(world.is_visible(0, world.units[uid].tile) for uid in camp.guards)
    brain = Brain(0, Difficulty.MEDIUM)
    assert brain._enemy_targets(world) == [rival.pos]
    assert brain._enemy_soldiers(world) == 0, "the troll and the wolf are no enemy soldiers"
    pro = ProBrain(0, PRO)
    assert [u.id for u in pro._enemies(world)] == [rival.id]
    assert pro._attack_targets(world) == [rival.pos]


# -- Rousing, leashing, resetting -------------------------------------------------------


def test_the_whole_camp_answers_one_intruder() -> None:
    """Shared aggro is the anti-cheese: a camp that woke one guard at a time could be whittled down."""
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF,) * 4)
    lair = world.buildings[camp.lair]
    rider = world.spawn_unit(0, UnitType.KNIGHT, (lair.center[0], lair.center[1] - CAMP_WATCH + 1.0))
    run(world, 0.5)
    fighting = [world.units[uid] for uid in camp.guards if uid in world.units]
    assert fighting and all(isinstance(g.order, Attack) and g.order.target == rider.id for g in fighting)


def test_a_guard_kited_past_the_camps_hold_walks_back_to_its_post() -> None:
    world = flat_world(width=60, height=40)
    camp = a_camp(world, at=(20, 18), roster=(UnitType.WOLF,))
    lair = world.buildings[camp.lair]
    bait = world.spawn_unit(0, UnitType.PEASANT, (lair.center[0] + 4.0, lair.center[1]))
    world.hold([bait.id])  # a worker on hold strikes nothing back: the guard lives to be called home
    run(world, 0.5)
    guard = world.units[camp.guards[0]]
    assert isinstance(guard.order, Attack)
    bait.x, bait.y = lair.center[0] + CAMP_HOLD + 6.0, lair.center[1]
    run(world, 1.0)
    assert not isinstance(guard.order, Attack), "a guard whose intruder left must break off"
    post = camp.posts[0]
    run(world, 14.0)
    assert dist(guard.pos, post) <= camps.HOME


def test_a_settled_camp_mends_survivors_without_replacing_fallen_guards() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF, UnitType.WOLF))
    hurt = world.units[camp.guards[0]]
    hurt.hp = 5
    fallen = camp.guards[1]
    world.units[fallen].hp = 0
    run(world, CAMP_CALM + 30.0)
    assert hurt.hp == hurt.max_hp
    assert camp.guards[1] == fallen and fallen not in world.units


def test_a_camp_in_a_fight_neither_mends_nor_refills() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF, UnitType.WOLF))
    lair = world.buildings[camp.lair]
    world.spawn_unit(0, UnitType.KNIGHT, (lair.center[0] + 2.0, lair.center[1] + 2.0))
    hurt = world.units[camp.guards[0]]
    hurt.hp, hurt.max_hp = 5, hurt.max_hp
    fallen = camp.guards[1]
    world.units[fallen].hp = 0
    run(world, CAMP_CALM + 30.0)
    assert camp.guards[1] == fallen, "a camp with an enemy in it must not send anything back out"


def test_lair_sniping_waits_for_the_guards_before_paying_out_the_hoard() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF,), hoard=700)
    before = world.players[0].gold
    lair = world.buildings[camp.lair]
    lair.hp = 1
    world._hit(lair, 40, player=0, source=world.spawn_unit(0, UnitType.KNIGHT, (4.0, 4.0)).id,
               source_type=UnitType.KNIGHT.value)
    run(world, 0.1)
    assert camp.lair not in world.buildings
    assert world.players[0].gold == before
    world.units[camp.guards[0]].hp = 0
    run(world, CAMP_CALM + 30.0)
    assert camp.guards[0] not in world.units, "defeated guards never come back"
    assert world.players[0].gold == before + 700


def test_the_hoard_is_paid_once() -> None:
    """A completed encounter pays once even while the world keeps advancing."""
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF,), hoard=700)
    lair = world.buildings[camp.lair]
    lair.hp = 1
    world.units[camp.guards[0]].hp = 0  # staged guard defeat; this test isolates completion accounting
    striker = world.spawn_unit(0, UnitType.KNIGHT, (4.0, 4.0)).id
    # A staged lethal hit avoids coupling payout accounting to combat timing.
    world._hit(lair, 40, player=0, source=striker, source_type=UnitType.KNIGHT.value)
    run(world, 0.5)
    before = world.players[0].gold
    assert world.players[0].stats["bounty_gold"] == 700
    run(world, 10)
    assert world.players[0].gold == before


# -- What each creature is --------------------------------------------------------------


def test_a_troll_knits_its_wounds_back_only_once_nothing_is_hitting_it() -> None:
    world = flat_world()
    troll = world.spawn_unit(world.neutral, UnitType.TROLL, (10.0, 10.0))
    troll.hp = 100
    troll.struck = world.time
    run(world, REGEN_CALM - 1.0)
    assert troll.hp == 100, "a troll under the axe heals nothing"
    run(world, 4.0)
    assert troll.hp > 100


def test_an_archers_arrow_lands_harder_on_a_troll_than_a_knights_blow_would_suggest() -> None:
    """The troll is unarmoured on purpose: armour subtracts, so a plated sponge would make an arrow land
    for one and turn every camp into a knights-only check."""
    world = flat_world()
    troll = world.spawn_unit(world.neutral, UnitType.TROLL, (10.0, 10.0))
    archer = world.spawn_unit(0, UnitType.ARCHER, (10.0, 12.0))
    before = troll.hp
    world._strike(archer, troll)
    run(world, 1.0)
    assert before - troll.hp >= archer.info.damage, "piercing lands x1.5 on the unarmoured"


def test_a_golems_slam_catches_the_crowd_around_its_mark_but_never_its_own() -> None:
    world = flat_world()
    golem = world.spawn_unit(world.neutral, UnitType.GOLEM, (10.0, 10.0))
    mark = world.spawn_unit(0, UnitType.FOOTMAN, (10.0, 10.9))
    beside = world.spawn_unit(0, UnitType.FOOTMAN, (10.8, 10.9))
    away = world.spawn_unit(0, UnitType.FOOTMAN, (16.0, 10.0))
    kin = world.spawn_unit(world.neutral, UnitType.WOLF, (10.8, 10.4))
    world._index_units()
    world._strike(golem, mark)
    assert mark.hp < mark.max_hp and beside.hp < beside.max_hp
    assert away.hp == away.max_hp and kin.hp == kin.max_hp


# -- What the map and the brains make of them -------------------------------------------


def test_every_seat_gets_the_same_camps_on_a_generated_map() -> None:
    world = mapgen.generate(9, 64, 48, 2)
    assert world.camps, "a Medium map offers optional expeditions"
    counts: dict[tuple[str, ...], int] = {}
    for camp in world.camps:
        roster = tuple(sorted(camp.kinds))
        counts[roster] = counts.get(roster, 0) + 1
    assert counts and all(n == world.seats for n in counts.values()), counts
    for camp in world.camps:
        lair = world.buildings[camp.lair]
        assert min(dist(lair.center, hall.center) for hall in world.buildings.values()
                   if hall.type is BuildingType.TOWN_HALL) >= 14.0


def test_a_camp_never_stands_where_it_would_wall_a_deposit_off() -> None:
    for seed in (3, 4, 5):
        world, report = mapgen.build(seed, 64, 48, 2)
        assert report["connected"] and not report["problems"], (seed, report["problems"])


def test_a_lair_is_a_camp_to_clear_and_never_an_opponent_to_beat() -> None:
    world = mapgen.generate(9, 64, 48, 2)
    world.reveal_all(0)
    world.update_vision()
    camps_known = known_camps(world, 0)
    assert camps_known, "a player who can see the map knows where the dens are"
    assert not any(record.id in {c.lair for c in world.camps} for record in known_enemy_buildings(world, 0))
    lair = world.buildings[camps_known[0].lair] if hasattr(camps_known[0], "lair") else world.buildings[camps_known[0].id]
    assert guarded(world, 0, lair.center)


def test_the_gatherer_policy_keeps_its_workers_out_of_a_camp() -> None:
    """``worker_ai`` blacklists the ground inside a hostile unit's threat radius; a creature is hostile
    to every playing seat, so a peasant routes round a camp without a rule of its own."""
    from warband.sim import worker_ai

    world = flat_world()
    camp = a_camp(world, at=(20, 16), roster=(UnitType.WOLF,) * 4)
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.reveal_all(0)
    world._index_units()
    grid = worker_ai.safe_navigation(world, 0)
    guard = world.units[camp.guards[0]]
    assert grid[int(guard.y) * world.width + int(guard.x)] == 1


# -- Mirror-congruent orbits ------------------------------------------------------------


def test_an_orbit_mirrors_posts_species_and_facing_across_seats() -> None:
    """A mixed roster lands on congruent ground: the same species at mirrored posts, facing mirrored."""
    world = flat_world()
    first, second = camps.place_orbit(world, [(8, 8), (28, 8)], "cairn_watch", [(False, False), (True, False)])
    assert [camp.kinds for camp in (first, second)] == [["golem", "troll", "spider"]] * 2
    a = world.buildings[first.lair].center
    b = world.buildings[second.lair].center
    for (px, py), (qx, qy) in zip(first.posts, second.posts):
        assert (qx - b[0], qy - b[1]) == pytest.approx((-(px - a[0]), py - a[1]))
    for uid, vid in zip(first.guards, second.guards):
        assert world.units[vid].facing == pytest.approx(math.pi - world.units[uid].facing)


def test_an_orbit_mirrors_a_blocked_canonical_post_fallback() -> None:
    """One seat's blocked post resolves once, canonically; the images mirror the resolution."""
    world = flat_world()
    world.place_building(0, BuildingType.FARM, (22, 18))  # sits on a post of a lair at (20, 16)
    first, second = camps.place_orbit(world, [(20, 16), (8, 8)], "cairn_watch", [(False, False), (False, False)])
    lair = world.buildings[first.lair]
    assert all(post != lair.center for post in first.posts)  # the blocked post fell back, not into the lair
    a = lair.center
    b = world.buildings[second.lair].center
    for (px, py), (qx, qy) in zip(first.posts, second.posts):
        assert (qx - b[0], qy - b[1]) == pytest.approx((px - a[0], py - a[1]))
    assert [camp.kinds for camp in (first, second)] == [["golem", "troll", "spider"]] * 2
    for uid, vid in zip(first.guards, second.guards):
        assert world.units[vid].facing == pytest.approx(world.units[uid].facing)


def test_an_orbit_refuses_uncountable_inputs() -> None:
    """No silent seat drops: empty and ragged orbits fail loudly."""
    world = flat_world()
    with pytest.raises(ValueError):
        camps.place_orbit(world, [], "wolf_den", [])
    with pytest.raises(ValueError):
        camps.place_orbit(world, [(8, 8), (28, 8)], "wolf_den", [(False, False)])


# -- The online authority ---------------------------------------------------------------


def test_no_seat_can_drive_the_wilds() -> None:
    from saga2d import CommandError
    from warband.online.authority import WarbandMatch

    match = WarbandMatch(seed=9, width=64, height=48, players=2)
    with pytest.raises(CommandError):
        match.apply(match.world.neutral, {"action": "stop", "args": [[1]], "kwargs": {}})


def test_a_seats_snapshot_shows_the_creatures_it_sees_and_none_of_the_wilds_own_affairs() -> None:
    from warband.online.authority import WarbandMatch

    match = WarbandMatch(seed=9, width=64, height=48, players=2)
    assert not any(p.human for p in match.world.players if p.neutral), "the wilds are nobody's seat"
    snapshot = match.snapshot(0)
    wilds = [p for p in snapshot["world"]["players"] if p["neutral"]]
    assert len(wilds) == 1 and wilds[0]["gold"] == 0 and wilds[0]["upgrades"] == []
    assert snapshot["world"]["explored"][match.world.neutral] == bytes(match.world.width * match.world.height).hex()
    shown = {u["id"] for u in snapshot["world"]["units"]}
    for camp in match.world.camps:
        for uid in camp.guards:
            unit = match.world.units[uid]
            assert (uid in shown) == match.world.is_visible(0, unit.tile)


def test_a_seat_that_only_sees_the_mine_learns_nothing_of_the_lair_or_its_fall() -> None:
    """Completion news is earned, never leaked through a watched mine: a seat whose scout sees the
    guarded deposit while the den beside it stays in fog gets no camp row for the mine it sees --
    and when a rival clears that camp out of its sight, its picture does not move while the
    contributor's records its earned clear."""
    from warband.online.authority import WarbandMatch

    match = WarbandMatch(seed=5, width=64, height=48, players=2, layout=Layout.PLAINS)
    world = match.world
    camp = next(c for c in world.camps if c.watch is not None)
    lair = world.buildings[camp.lair]
    site = camps.centre(world, camp)
    watch = camps.watch_of(world, camp)
    assert site != watch  # the test needs a guard's shifted watch, not a den watch
    mine = next(b for b in world.buildings.values()
                if b.type is not BuildingType.LAIR and dist(b.center, watch) < 0.5)
    # An unarmed scout perches past the deposit, seeing it but not the den beside it: its
    # nine-tile sight still reaches the mine eight tiles off while the den sits four further on.
    dx, dy = watch[0] - site[0], watch[1] - site[1]
    length = hypot(dx, dy)
    world.spawn_unit(1, UnitType.FLYING_MACHINE, (watch[0] + dx / length * 8.0, watch[1] + dy / length * 8.0))
    world.update_vision()
    assert world.is_visible(1, mine.pos) and not world.is_visible(1, lair.pos)
    before = match.snapshot(1)
    assert all(row["lair"] != camp.lair for row in before["world"]["camps"])
    assert any(b["id"] == mine.id for b in before["world"]["buildings"])
    assert all(b["id"] != camp.lair for b in before["world"]["buildings"])
    # Seat 0 clears the camp under its own eyes; the rival learns nothing, the clearer everything.
    witness = world.spawn_unit(0, UnitType.KNIGHT, (site[0] + 3.0, site[1]))
    world.update_vision()
    for uid in list(camp.guards):
        world._hit(world.units[uid], 10000, player=0, source=witness.id, source_type=UnitType.KNIGHT.value)
    world._hit(lair, 10000, player=0, source=witness.id, source_type=UnitType.KNIGHT.value)
    run(world, 2.0)
    assert camp.cleared
    own = match.snapshot(0)
    assert [row["cleared"] for row in own["world"]["camps"] if row["lair"] == camp.lair] == [True]
    assert camp.lair in world.worker_knowledge[0].cleared_encounters
    rival = match.snapshot(1)
    assert all(row["lair"] != camp.lair for row in rival["world"]["camps"])
    assert camp.lair not in world.worker_knowledge[1].cleared_encounters


def test_a_lone_guard_cannot_be_pulled_out_of_its_camp() -> None:
    """A creature picks no fight of its own: only the camp does, and only within its watch.  A guard that
    answered whatever wandered into its own sight could be pulled out one at a time from beyond that."""
    world = flat_world(width=60, height=40)
    camp = a_camp(world, at=(20, 18), roster=(UnitType.WOLF,) * 4)
    lair = world.buildings[camp.lair]
    bait = world.spawn_unit(0, UnitType.KNIGHT, (lair.center[0], lair.center[1] - (CAMP_WATCH + 2.0)))
    world.hold([bait.id])
    run(world, 3.0)
    assert all(u.order is None or isinstance(u.order, Move) for u in camps.guards(world, camp))
    assert all(dist(u.pos, camps.centre(world, camp)) <= CAMP_WATCH for u in camps.guards(world, camp))


def test_a_camp_shot_at_from_beyond_its_watch_goes_after_the_shooter() -> None:
    """A catapult outranges every guard.  A camp that only ever looked as far as its own watch would
    stand there being taken apart; a guard struck lately makes it look as far as one could be sent."""
    world = flat_world(width=60, height=40)
    camp = a_camp(world, at=(20, 18), roster=(UnitType.WOLF, UnitType.WOLF))
    lair = world.buildings[camp.lair]
    crew = world.spawn_unit(0, UnitType.CATAPULT, (lair.center[0], lair.center[1] - (CAMP_WATCH + 3.5)))
    guard = camps.guards(world, camp)[0]
    world._hit(guard, 5, player=0, source=crew.id, source_type=UnitType.CATAPULT.value)
    run(world, 0.5)
    assert any(isinstance(u.order, Attack) and u.order.target == crew.id for u in camps.guards(world, camp))


def test_a_siege_beyond_the_lair_still_rouses_a_watch_on_the_mine() -> None:
    """A shifted watch defends the deposit, not the den: a catapult shelling from beyond the lair's
    own reach -- farther than a struck camp would even look -- but inside the mine's watch still
    brings every guard, because the watch is a defended point like the site."""
    world = flat_world(width=60, height=40)
    camp = camps.place(world, (20, 18), [UnitType.WOLF, UnitType.WOLF], 500, watch=(21.5, 29.5))
    site = camps.centre(world, camp)
    crew = world.spawn_unit(0, UnitType.CATAPULT, (21.5, 34.0))
    assert dist(crew.pos, site) > CAMP_HOLD + camps.CHASE_SLACK  # past even the answer radius from the den
    assert dist(crew.pos, camps.watch_of(world, camp)) < CAMP_WATCH  # but inside the mine's watch
    run(world, 0.5)
    assert camp.roused
    assert any(isinstance(u.order, Attack) and u.order.target == crew.id for u in camps.guards(world, camp))


def test_an_ordinary_move_into_the_den_names_its_encounter() -> None:
    """Deliberate movement chooses the union: a move onto ground inside the den but outside the
    mine watch walks in, instead of stalling at a circle nobody chose."""
    world = flat_world(width=60, height=40)
    camp, site = a_shifted_watch_camp(world)
    watch = camps.watch_of(world, camp)
    goal = (site[0] + 2.5, site[1])
    assert dist(goal, site) < CAMP_WATCH and dist(goal, watch) > CAMP_WATCH
    knight = world.spawn_unit(0, UnitType.KNIGHT, (10.0, site[1]))
    world.move([knight.id], goal)
    for _ in range(int(round(20.0 / 0.5))):
        run(world, 0.5)
        if dist(world.units[knight.id].pos, goal) < 1.5:
            break
    assert dist(world.units[knight.id].pos, goal) < 1.5


def test_a_formation_move_into_the_den_names_its_encounter() -> None:
    """Every slot chooses the union with its unit: a formation ordered into the den walks in
    together, instead of stalling each slot at a circle nobody chose."""
    world = flat_world(width=60, height=40)
    camp, site = a_shifted_watch_camp(world)
    watch = camps.watch_of(world, camp)
    goal = (site[0] + 2.5, site[1])
    assert dist(goal, site) < CAMP_WATCH and dist(goal, watch) > CAMP_WATCH
    party = [world.spawn_unit(0, UnitType.KNIGHT, (10.0 + i * 0.8, site[1])).id for i in range(5)]
    world.move(party, goal)
    for _ in range(int(round(25.0 / 0.5))):
        run(world, 0.5)
        if all(dist(world.units[uid].pos, goal) < 3.0 for uid in party):
            break
    assert all(dist(world.units[uid].pos, goal) < 3.0 for uid in party)


def test_an_attack_move_beside_the_den_names_its_encounter() -> None:
    """Explicit intent reaches the den's circle through the union: an attack-move onto ground
    inside the den but outside the mine watch is the encounter's business, and walks in."""
    world = flat_world(width=60, height=40)
    camp, site = a_shifted_watch_camp(world)
    watch = camps.watch_of(world, camp)
    goal = (site[0] - 3.5, site[1])
    assert dist(goal, site) < CAMP_WATCH and dist(goal, watch) > CAMP_WATCH
    knight = world.spawn_unit(0, UnitType.KNIGHT, (10.0, site[1]))
    world.attack_move([knight.id], goal)
    entered = False
    for _ in range(int(round(20.0 / 0.5))):
        run(world, 0.5)
        entered = entered or dist(world.units[knight.id].pos, site) < CAMP_WATCH
        if dist(world.units[knight.id].pos, goal) < 1.5:
            break
    assert dist(world.units[knight.id].pos, goal) < 1.5
    assert entered


def test_a_brain_calls_ground_held_by_either_circle() -> None:
    """Ordinary safety is the union: a mine mouth inside the mine watch counts as held ground
    even ten tiles off the den, and open ground far from both does not."""
    world = flat_world(width=60, height=40)
    camp, site = a_shifted_watch_camp(world)
    watch = camps.watch_of(world, camp)
    mouth = (watch[0], watch[1] + 3.0)
    assert dist(mouth, watch) < CAMP_WATCH and dist(mouth, site) > 10.0
    assert guarded(world, 0, mouth)
    assert not guarded(world, 0, (10.0, 10.0))


def test_a_creatures_card_names_it_and_says_what_it_wears(tmp_path) -> None:
    """The armour line is the teaching surface for the whole design: a troll reads *Unarmoured*, which is
    why an archer is the answer to it and a knight is not.  A creature is nobody's, so its picture comes
    from ``warband.art.monsters`` rather than the team-recoloured table, and its card must still draw."""
    from saga2d import Game
    from warband.ui.scene import GameScene
    from warband.ui.style import build_theme

    from tests.warband.battlefield import SETTINGS, field

    game = Game("Warband creatures", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = GameScene(field(), 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        world = scene.world
        camp = camps.place(world, (5, 5), [UnitType.TROLL, UnitType.GOLEM, UnitType.SPIDER, UnitType.WOLF], 900)
        # A flying machine of the player's hovers over the camp, which does not rouse for it: a creature in fog is
        # dropped from the selection.
        world.spawn_unit(0, UnitType.FLYING_MACHINE, (6.5, 6.5))
        world.update_vision()
        drawn = {UnitType.TROLL: "Unarmoured · normal blows", UnitType.GOLEM: "Heavy armour · normal blows",
                 UnitType.SPIDER: "Light armour · normal blows", UnitType.WOLF: "Light armour · normal blows"}
        for guard in camps.guards(world, camp):
            scene.select([guard.id])
            for _ in range(3):
                game.tick(1 / 60)
            assert scene.armour_notes == (drawn[guard.type],), guard.type
            assert guard.info.name in {str(t["text"]) for t in game.backend.texts}
        scene.select([camp.lair])
        for _ in range(3):
            game.tick(1 / 60)
        assert scene.armour_notes == ("Fortified",)  # a building says its class alone, in the corner beside its hit points
    finally:
        game.close()


@pytest.mark.slow
def test_the_den_is_a_picture_the_art_lint_passes(tmp_path) -> None:
    """The den is drawn by ``warband.art.monsters``, not by the buildings' own table, so the lint that
    walks every registered building image never sees it: it is held here instead.  Slow: it renders."""
    from saga2d import Game
    from warband.art import monsters, visual_lint
    from warband.ui.style import build_theme

    game = Game("Warband den", backend="mock", resolution=(640, 480), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        store = visual_lint.ImageStore(game)  # before the renders: it hooks the backend's loader
        keys = [monsters.lair_image(game, kind, look) for kind in monsters.LairKind for look in monsters.LAIR_LOOKS]
        keys += [monsters.lair_portrait_image(game, kind) for kind in monsters.LairKind]
        findings = [finding for key in keys
                    for finding in visual_lint.lint_image(key, store.image(key),
                                                          painted=key.startswith("building.lair."),
                                                          cropped=key.startswith("portrait."))]
        assert not findings, [str(finding) for finding in findings]
    finally:
        game.close()


def test_a_guard_walked_home_does_not_resume_an_old_step_away_from_the_crowd() -> None:
    """Fuzz seed 81: a spider that had begun a step away from a crowd (``Unit.ease``) before the camp sent it
    home kept that step.  The camp puts its walk home on the guard directly, not through an order, so nothing
    cleared the step; once the guard was within ``HOME`` of its post the camp dropped the walk, the old step
    took it back out past ``HOME``, and the camp sent it home again, for the rest of the match."""
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.SPIDER,))
    run(world, 0.5)
    [(guard, post)] = camps.posted(world, camp)
    guard.x, guard.y = post[0] - 4.0, post[1]  # led off, and left alone
    # The step it had begun: just past HOME, beside where the walk home ends, so nearer than the post was.
    guard.ease = (post[0] - 1.0, post[1] + 0.75)
    run(world, 0.5)
    assert guard.orders and guard.ease is None  # walking home, the old step dropped
    run(world, 12.0)
    assert dist(guard.pos, post) <= camps.HOME and not guard.orders and guard.state == "idle", (guard.pos, post, guard.orders, guard.state)
