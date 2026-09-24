"""Creature camps: the neutral seat, the rules that make a camp a decision, and the brains that clear one.

The load-bearing claims, in the order the design rests on them: the wilds are a seat like no other and
are left out of everything a seat is counted for; a camp rouses as a group, so it cannot be pulled apart
one guard at a time; it leashes, so it cannot be dragged into somebody else's fight; it resets, so a push
that breaks off half way paid for nothing; and tearing the lair down stops all of that for good and pays
out the hoard.
"""

import random

import pytest

from warband.brains.ai import guarded, known_camps, known_enemy_buildings
from warband.sim import camps, mapgen
from warband.sim.model import Attack, Move, World, dist, tile_center
from warband.sim.rules import (CAMP_CALM, CAMP_HOLD, CAMP_RESPAWN, CAMP_WATCH, REGEN_CALM, SIM_DT, BuildingType, Terrain,
                               UnitType)


def flat_world(width: int = 40, height: int = 32, players: int = 2) -> World:
    return World(width, height, [[Terrain.GRASS] * width for _ in range(height)], players, rng=random.Random(1))


def run(world: World, seconds: float) -> None:
    for _ in range(int(round(seconds / SIM_DT))):
        world.step()


def a_camp(world: World, at=(20, 16), roster=(UnitType.WOLF, UnitType.WOLF, UnitType.WOLF), hoard=500):
    return camps.place(world, at, list(roster), hoard)


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


def test_a_settled_camp_mends_its_wounded_and_calls_its_dead_back_out_of_the_lair() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF, UnitType.WOLF))
    hurt = world.units[camp.guards[0]]
    hurt.hp = 5
    fallen = camp.guards[1]
    world.units[fallen].hp = 0
    run(world, CAMP_CALM + CAMP_RESPAWN + 4.0)
    assert hurt.hp == hurt.max_hp
    assert camp.guards[1] != fallen and camp.guards[1] in world.units


def test_a_camp_in_a_fight_neither_mends_nor_refills() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF, UnitType.WOLF))
    lair = world.buildings[camp.lair]
    world.spawn_unit(0, UnitType.KNIGHT, (lair.center[0] + 2.0, lair.center[1] + 2.0))
    hurt = world.units[camp.guards[0]]
    hurt.hp, hurt.max_hp = 5, hurt.max_hp
    fallen = camp.guards[1]
    world.units[fallen].hp = 0
    run(world, CAMP_CALM + CAMP_RESPAWN + 2.0)
    assert camp.guards[1] == fallen, "a camp with an enemy in it must not send anything back out"


def test_tearing_the_lair_down_ends_the_camp_for_good_and_pays_out_the_hoard() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF,), hoard=700)
    before = world.players[0].gold
    lair = world.buildings[camp.lair]
    lair.hp = 1
    world._hit(lair, 40, player=0, source=world.spawn_unit(0, UnitType.KNIGHT, (4.0, 4.0)).id,
               source_type=UnitType.KNIGHT.value)
    run(world, 0.1)
    assert camp.lair not in world.buildings
    assert world.players[0].gold == before + 700
    world.units[camp.guards[0]].hp = 0
    run(world, CAMP_CALM + CAMP_RESPAWN + 4.0)
    assert camp.guards[0] not in world.units, "a camp whose den is gone must never come back"


def test_the_hoard_is_paid_once() -> None:
    world = flat_world()
    camp = a_camp(world, roster=(UnitType.WOLF,), hoard=700)
    lair = world.buildings[camp.lair]
    lair.hp = 1
    striker = world.spawn_unit(0, UnitType.KNIGHT, (4.0, 4.0)).id
    world._hit(lair, 40, player=0, source=striker, source_type=UnitType.KNIGHT.value)
    before = world.players[0].gold
    world._hit(lair, 40, player=0, source=striker, source_type=UnitType.KNIGHT.value)
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
    assert world.camps, "a Medium plains map guards its contested deposits"
    counts: dict[tuple[str, ...], int] = {}
    for camp in world.camps:
        roster = tuple(sorted(camp.kinds))
        counts[roster] = counts.get(roster, 0) + 1
    assert counts and all(n == world.seats for n in counts.values()), counts
    for camp in world.camps:
        lair = world.buildings[camp.lair]
        assert min(dist(lair.center, mine.center) for mine in world.mines()) <= 12.0


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
