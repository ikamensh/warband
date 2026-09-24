"""What the stronger brain must keep doing, including two things it once got wrong.

Both regressions were found by watching matches rather than by reasoning:
an army that re-decided every pass oscillated in and out of the enemy base
without ever fighting, and a remembered enemy count that was a running total
reported roughly ten times the army that was there.

Many tests put the brain's own questions to it (what it remembers of the enemy,
what it would attack and with what, what it wishes to build next, where its
home and front are): a match shows them only through outcomes far too noisy to
pin, so these call its private helpers on purpose.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from warband.sim import camps, mapgen
from warband.sim.model import AttackMove, Move, World, dist
from warband.brains.ai import known_mines, make_brain
from warband.brains.bred import BRED
from warband.brains.pro_ai import CALM, PRO, ProBrain, _tower_strength, strength
from warband.sim.rules import SIM_DT, BuildingType, Difficulty, Layout, Race, Terrain, UnitType, Upgrade


def _world_with_army(seed: int = 5):
    """A generated map, plus a brain for player 0 that has already had a look round."""
    world = mapgen.generate(seed=seed, players=2, human=None)
    return world, ProBrain(0, PRO)


def _spawn(world, player, unit_type, near, count):
    hall = world.player_buildings(player, BuildingType.TOWN_HALL)[0]
    return [world.spawn_unit(player, unit_type, (hall.center[0] + near + i * 0.6, hall.center[1] + 1))
            for i in range(count)]


# -- Force comparison -----------------------------------------------------------

def test_strength_grows_with_the_size_of_the_army():
    world, _ = _world_with_army()
    few = _spawn(world, 0, UnitType.FOOTMAN, 2, 3)
    many = few + _spawn(world, 0, UnitType.FOOTMAN, 6, 3)
    assert strength(world, many) > strength(world, few)


def test_a_wounded_army_is_worth_less_than_a_whole_one():
    world, _ = _world_with_army()
    army = _spawn(world, 0, UnitType.FOOTMAN, 2, 4)
    whole = strength(world, army)
    for unit in army:
        unit.hp = max(1, unit.hp // 3)
    assert strength(world, army) < whole


def test_knights_are_worth_more_than_the_same_number_of_peasants():
    world, _ = _world_with_army()
    assert strength(world, _spawn(world, 0, UnitType.KNIGHT, 2, 4)) > \
           strength(world, _spawn(world, 0, UnitType.PEASANT, 8, 4))


# -- Remembering the enemy ------------------------------------------------------

def _raiders_at_our_base(world, count=3):
    """Enemy archers standing in our base, where our own buildings can see them."""
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    archers = [world.spawn_unit(1, UnitType.ARCHER, (hall.center[0] + 1 + i * 0.5, hall.center[1] + 1))
               for i in range(count)]
    world.update_vision()
    return archers


def test_the_enemy_memory_counts_soldiers_rather_than_sightings():
    """Regression: a decaying running total reported about ten armies instead of one.

    The brain compares the remembered count against its own army, so the number
    has to mean "how many of them there are", however many times it has looked.
    """
    world, brain = _world_with_army()
    _raiders_at_our_base(world, 3)
    for _ in range(40):
        brain._observe(world)
    assert brain.remembered(1)[UnitType.ARCHER] == 3


def test_a_sighting_fades_once_the_enemy_is_out_of_sight():
    world, brain = _world_with_army()
    archers = _raiders_at_our_base(world, 3)
    for _ in range(10):
        brain._observe(world)
    seen = brain.remembered(1)[UnitType.ARCHER]
    for unit in archers:
        world.units.pop(unit.id)
    world.update_vision()
    for _ in range(200):
        world.time += PRO.think_every
        brain._observe(world)
    assert brain.remembered(1).get(UnitType.ARCHER, 0.0) < seen


def test_barracks_first_wishes_for_nothing_else_until_it_stands():
    from dataclasses import replace
    world, brain = _world_with_army()
    brain.profile = replace(PRO, barracks_first=True)
    world.players[0].gold, world.players[0].lumber = 5000, 5000
    wanted = [building for building, _ in brain._wish_list(world)]
    assert BuildingType.BARRACKS in wanted
    assert set(wanted) <= {BuildingType.FARM, BuildingType.BARRACKS}
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 6, hall.y))
    wanted = [building for building, _ in brain._wish_list(world)]
    assert BuildingType.LUMBER_MILL in wanted, "once the barracks stands, the rest of the list is back"


def test_an_army_out_on_the_map_still_defends_its_base():
    """Regression: a scout looking at an empty base reported a defence of nothing,
    and the push that went out met the army that had simply been standing elsewhere."""
    world, brain = _world_with_army()
    world.reveal_all(0)
    _spawn(world, 1, UnitType.FOOTMAN, 2, 10)  # their army, nowhere near their hall
    brain._observe(world)
    enemy_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    assert brain._defenders_near(world, enemy_hall) > 0.0


def test_an_enemy_nobody_has_looked_at_is_not_assumed_to_be_harmless():
    """An unseen enemy has a finite prior, even before the first scout reports."""
    world, brain = _world_with_army()
    army = _spawn(world, 0, UnitType.FOOTMAN, 2, 10)
    world.time = 600.0  # long past any sighting
    enemy_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    assert brain._defenders_near(world, enemy_hall) == pytest.approx(strength(world, army[:PRO.min_army]) * PRO.symmetry_prior)


# -- Committing to a push --------------------------------------------------------

def test_a_push_is_not_called_off_while_the_army_is_still_whole():
    """Regression: re-deciding every pass walked the army home as soon as a tower came into view."""
    world, brain = _world_with_army()
    army = _spawn(world, 0, UnitType.FOOTMAN, 2, 12)
    brain.attacking = True
    brain.commit_strength = strength(world, army)
    brain.target = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    # A tower right next to the army: under the old rule this alone turned it round.
    world.place_building(1, BuildingType.TOWER, (int(army[0].x) + 3, int(army[0].y) + 3))
    brain._military(world)
    assert brain.attacking


def test_a_push_that_has_lost_most_of_itself_breaks_off():
    world, brain = _world_with_army()
    army = _spawn(world, 0, UnitType.FOOTMAN, 2, 12)
    brain.attacking = True
    brain.commit_strength = strength(world, army)
    brain.target = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    for unit in army[3:]:
        world.units.pop(unit.id)
    brain._military(world)
    assert not brain.attacking
    assert brain.regroup_until > world.time, "a beaten army rebuilds before trying again"


# -- Playing a whole game --------------------------------------------------------

@pytest.mark.slow
def test_the_brain_plays_a_match_without_raising_and_builds_an_army():
    """The cheapest cover there is: the whole thing actually runs.

    Both sides have soldiers only after three minutes, about a second of play: the slow tier. The fast tier's
    arena matches run the brain for a minute and a half."""
    world = mapgen.generate(seed=12, players=2, human=None)
    brains = [ProBrain(0, PRO), ProBrain(1, PRO)]
    rngs = [random.Random(i) for i in range(2)]
    # The most soldiers each side ever had at once, not the ones still standing at the end: whether the army
    # was trained is the brain's business, whether it survived the other brain's attack is the match's.
    army = [0, 0]
    for _ in range(int(240 / SIM_DT)):
        if world.winner is not None:
            break
        for brain, rng in zip(brains, rngs):
            brain.think(world, rng)
        world.step()
        world.take_events()
        for player in (0, 1):
            army[player] = max(army[player], sum(1 for u in world.player_units(player) if not u.is_worker))
    for player in (0, 1):
        assert army[player], f"player {player} trained nothing"
        assert len(world.player_buildings(player, done=True)) > 2


# -- Free-for-all ----------------------------------------------------------------

def test_the_weakest_opponent_is_the_one_attacked_not_the_nearest():
    """In a three player game the neighbour is usually the wrong target: fighting
    the strongest player is a gift to whoever is left over."""
    world = mapgen.generate(seed=9, players=3, human=None)
    brain = ProBrain(0, PRO)
    world.reveal_all(0)
    _spawn(world, 1, UnitType.FOOTMAN, 2, 8)
    _spawn(world, 2, UnitType.FOOTMAN, 2, 1)
    brain._observe(world)
    assert brain._victim(world) == 2
    weak_hall = world.player_buildings(2, BuildingType.TOWN_HALL)[0].center
    targets = brain._attack_targets(world)
    assert min(targets, key=lambda t: (t[0] - weak_hall[0]) ** 2 + (t[1] - weak_hall[1]) ** 2) in targets
    assert all(brain._owner_of(world, t) == 2 for t in targets)


def test_more_opponents_mean_a_bigger_margin_is_wanted_before_attacking():
    """Every extra player is someone who profits from a fight you started."""
    world = mapgen.generate(seed=9, players=3, human=None)
    brain = ProBrain(0, PRO)
    bystanders = sum(1 for p in world.players[:world.seats] if p.id != 0 and p.alive) - 1  # the wilds are nobody's rival
    assert bystanders == 1
    assert PRO.attack_ratio * (1 + PRO.ffa_caution * bystanders) > PRO.attack_ratio


def test_caution_stops_growing_past_five_seats():
    """Regression: uncapped caution needed twelve times the strength and sixty
    soldiers to leave home in sixteen seats, so no attack ever went out."""
    two = mapgen.generate(seed=9, players=2, human=None)
    four = mapgen.generate(seed=9, players=4, human=None)
    six = mapgen.generate(seed=11, width=144, height=108, players=6, human=None)
    assert ProBrain(0, PRO)._caution(two) == 1.0
    assert ProBrain(0, PRO)._caution(four) == 1.0 + PRO.ffa_caution * 2
    assert ProBrain(0, PRO)._caution(six) == 1.0 + PRO.ffa_caution * 3


def test_unknown_ground_is_priced_as_one_opponent_not_all():
    """Regression: summing every seat's army for an unexplored point scaled the
    pessimism with the seat count and blocked every blind attack in a big game."""
    world = mapgen.generate(seed=9, players=3, human=None)
    brain = ProBrain(0, PRO)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    first = [world.spawn_unit(1, UnitType.FOOTMAN, (hall.center[0] + 1 + i * 0.5, hall.center[1] + 1))
             for i in range(8)]
    second = [world.spawn_unit(2, UnitType.FOOTMAN, (hall.center[0] + 1 + i * 0.5, hall.center[1] + 2))
              for i in range(8)]
    world.update_vision()
    corner = brain._unexplored_corner(world)
    assert brain._owner_of(world, corner) is None
    one = max(strength(world, first), strength(world, second))
    assert brain._defenders_near(world, corner) == pytest.approx(one)
    assert brain._defenders_near(world, corner) < strength(world, first + second)


@pytest.mark.parametrize("posture", BRED[Race.HUMAN])
def test_a_blind_grandmaster_army_explores_in_a_large_free_for_all(posture):
    """A viable army must leave home even if this posture never sends a scout.

    Six seats reach the same capped FFA caution as sixteen; this keeps the
    exact passivity decision cheap enough for the fast tier.
    """
    world = mapgen.generate(seed=11, width=144, height=108, players=6, human=None, wilds=False)
    brain = ProBrain(0, replace(posture, creep=False))
    assert not brain.profile.scout
    assert not brain._known_enemy_buildings(world)
    _spawn(world, 0, UnitType.FOOTMAN, 2, 25)
    world.time = 650.0

    brain._military(world)

    assert brain.attacking, "the army needs to discover an opponent before it can judge one"
    home = world.player_buildings(0, BuildingType.TOWN_HALL)[0].center
    guesses = mapgen.start_guesses(world.width, world.height, world.seats)
    own_cell = min(guesses, key=lambda point: dist(point, home))
    nearby = min((point for point in guesses if point != own_cell), key=lambda point: dist(point, home))
    assert brain.target == nearby, "look in a nearby rival cell before crossing the entire map"


def test_a_scouted_enemy_keeps_the_full_free_for_all_attack_margin():
    """The blind expedition rule must not turn a known costly fight into a push."""
    world = mapgen.generate(seed=11, width=144, height=108, players=6, human=None, wilds=False)
    brain = ProBrain(0, replace(BRED[Race.HUMAN][0], creep=False))
    _spawn(world, 0, UnitType.FOOTMAN, 2, 25)
    for player in range(1, 6):
        _spawn(world, player, UnitType.FOOTMAN, 2, 20)
    world.reveal_all(0)
    world.time = 650.0
    brain._observe(world)

    brain._military(world)

    assert not brain.attacking


def test_a_stale_base_sighting_does_not_hold_a_large_army_home():
    """Remembering a hall without recent defenders still permits an expedition."""
    world = mapgen.generate(seed=11, width=144, height=108, players=6, human=None, wilds=False)
    brain = ProBrain(0, replace(BRED[Race.HUMAN][1], creep=False))
    world.reveal_all(0)
    world.update_vision()
    assert brain._known_enemy_buildings(world)
    _spawn(world, 0, UnitType.FOOTMAN, 2, 25)
    world.time = 650.0

    brain._military(world)

    assert brain.attacking


def test_a_visible_field_army_keeps_the_full_ffa_margin_without_a_known_base():
    """Seeing soldiers in the field is information even before finding their hall."""
    world = mapgen.generate(seed=11, width=144, height=108, players=6, human=None, wilds=False)
    brain = ProBrain(0, replace(BRED[Race.HUMAN][0], creep=False))
    _spawn(world, 0, UnitType.FOOTMAN, 2, 25)
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (70.5, 54.5))
    for index in range(12):
        world.spawn_unit(1, UnitType.FOOTMAN, (72.5 + index * 0.5, 54.5))
    world.update_vision()
    assert not brain._known_enemy_buildings(world)
    brain._observe(world)
    world.time = 650.0

    brain._military(world)

    assert not brain.attacking


@pytest.mark.slow
def test_a_free_for_all_runs_to_placements():
    """Four brains, one map, and a finishing order rather than a winner: six minutes on a large map, the
    slow tier's."""
    from warband.league.arena import MatchSpec, play
    outcome = play(MatchSpec(seed=21, agents=("pro", "pro", "hard", "medium"), minutes=6, width=64, height=56))
    assert len(outcome.placements) == 4
    assert min(outcome.placements) == 1


def test_soldiers_sent_home_are_sent_somewhere_they_can_stand():
    """Regression, found by fuzz: a hall's centre is inside its own footprint.

    A wounded soldier ordered onto blocked ground paths towards it, stops a
    tile short and stays there — an archer stalled for twenty seconds on a
    move of two thirds of a tile.
    """
    world, brain = _world_with_army()
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    point = brain._home_point(world, hall)
    assert world.building_at((int(point[0]), int(point[1]))) is None
    assert world.passable(int(point[0]), int(point[1]))


def test_the_muster_point_is_never_inside_a_building():
    """Regression, found by fuzz: a farm built on the muster point made walking there
    an order no unit could ever finish."""
    world, brain = _world_with_army()
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    point = brain._front_point(world, hall)
    world.place_building(0, BuildingType.FARM, (int(point[0]), int(point[1])))
    moved = brain._front_point(world, hall)
    assert world.passable(int(moved[0]), int(moved[1]))


# -- What the brain is allowed to know -------------------------------------------

def test_the_brain_knows_nothing_of_an_enemy_base_it_has_never_seen():
    """Fog of war binds the AI as much as the player.

    Everything the brain reads about the map goes through the model's own
    per-player memory, which holds only what this player has laid eyes on.
    """
    world = mapgen.generate(seed=31, players=2, human=None)
    world.update_vision()
    brain = ProBrain(0, PRO)
    enemy_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]

    assert brain._known_enemy_buildings(world) == [], "their base has not been seen"
    assert all(dist(t, enemy_hall.center) > 3.0 for t in brain._attack_targets(world)), \
        "an unseen hall is not a target"
    assert brain._victim(world) is None
    world.place_building(1, BuildingType.TOWER, (enemy_hall.x + 5, enemy_hall.y))
    assert _tower_strength(world, 0, enemy_hall.center) == 0.0, "an unseen tower defends nothing we know of"

    world.reveal_all(0)
    world.update_vision()
    assert brain._known_enemy_buildings(world), "once looked at, it is known"
    assert any(dist(t, enemy_hall.center) <= 3.0 for t in brain._attack_targets(world))
    assert _tower_strength(world, 0, enemy_hall.center) > 0.0


def test_raiders_hunt_only_peasants_they_can_see():
    world = mapgen.generate(seed=31, players=2, human=None)
    world.update_vision()
    brain = ProBrain(0, replace(PRO, name="raider", raid=True))
    riders = _spawn(world, 0, UnitType.KNIGHT, 2, 2)
    brain._raid(world, riders)
    for rider in riders:
        for order in rider.orders:
            target = getattr(order, "target", None)
            if isinstance(target, tuple):
                assert all(dist(target, u.pos) > 1.0 for u in world.player_units(1) if u.is_worker), \
                    "a rider was sent at a peasant nobody has seen"


def test_the_brain_cannot_conjure_resources():
    """Every purchase goes through the model's can_afford, so with no income and an
    empty bank the brain buys nothing at all — no free gold, no free lumber."""
    world = mapgen.generate(seed=31, players=2, human=None)
    for unit in list(world.player_units(0)):
        world.units.pop(unit.id)  # nobody left to earn anything
    world.players[0].gold = 0
    world.players[0].lumber = 0
    before = len(world.player_buildings(0))
    brain = ProBrain(0, PRO)
    rng = random.Random(1)
    for _ in range(int(60 / SIM_DT)):
        brain.think(world, rng)
        world.step()
    assert world.players[0].gold == 0 and world.players[0].lumber == 0, "resources appeared from nowhere"
    # Buildings can only go down here: with nothing left alive the player is
    # eliminated, which is the rules working rather than the brain cheating.
    assert len(world.player_buildings(0)) <= before, "something was built out of thin air"
    assert not world.player_units(0), "something was trained out of thin air"


# -- The economy follows scarcity both ways --------------------------------------

def test_choppers_go_back_to_the_gold_once_the_wood_is_plentiful():
    """Six hands on the trees with five thousand lumber banked and five hundred gold: all but a trickle go mining.

    The rule used to fire one way only — hands to the trees when the wood ran
    out — so the wood crew only ever grew, and the league's losers ended with
    five to sixteen thousand lumber unspent while gold was what they lacked.
    """
    from warband.sim.model import Harvest
    from warband.sim.rules import Resource

    world, brain = _world_with_army()
    player = world.players[0]
    player.gold, player.lumber = 500, 5000
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for i in range(4):
        world.spawn_unit(0, UnitType.PEASANT, (hall.center[0] + 2 + i * 0.6, hall.center[1] + 2))
    peasants = world.player_units(0)
    assert len(peasants) >= 6
    tree = world.nearest_tree(peasants[0].pos, 24)
    world.harvest([p.id for p in peasants], tree)
    rng = random.Random(1)
    for _ in range(int(3 / SIM_DT)):
        brain.think(world, rng)
        world.step()
    chopping = [p for p in world.player_units(0)
                if any(isinstance(o, Harvest) and not isinstance(o.target, int) for o in p.orders)
                or p.carrying is Resource.LUMBER]
    assert len(chopping) <= 1, "one hand may keep chopping; the rest belong at the mine"


def test_a_producer_saves_for_the_unit_the_plan_wants():
    """With a stables idle, six hundred gold and a plan of knights, the barracks does not buy a footman it could afford.

    Buying whatever was affordable at the moment of choice made the knights posture
    field fifteen scouts for eight knights."""
    from dataclasses import replace

    from warband.sim.model import Building

    world = mapgen.generate(seed=5, players=2, human=None)
    brain = ProBrain(0, replace(PRO, name="test-knights", scout=False,
                                army_plan={UnitType.FOOTMAN: 0.2, UnitType.KNIGHT: 0.8}))
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y))
    world.place_building(0, BuildingType.STABLES, (hall.x + 5, hall.y + 4))
    for _ in range(3):
        world.place_building(0, BuildingType.FARM, (hall.x - 3, hall.y + _ * 3))
    player = world.players[0]
    rng = random.Random(1)

    def pass_with(gold: int) -> list[UnitType]:
        player.gold, player.lumber = gold, 500
        for _ in range(int(PRO.think_every / SIM_DT) + 1):  # a macro pass comes once per think_every of sim time
            world.step()
        brain.think(world, rng)
        return [u for b in world.player_buildings(0) for u in b.queue]

    assert pass_with(600) == [], "six hundred gold is saved for the knight the plan is short of"
    assert pass_with(900) == [UnitType.KNIGHT]


# -- Expansion under scarcity ------------------------------------------------------

def _brain_with_a_failing_mine(seed: int = 5, gold_left: int = 2000, peasants: int = 12):
    """A settled base whose mine is nearly spent, a second mine known, and money to move."""
    from warband.sim.rules import MINE_SLOTS

    world = mapgen.generate(seed=seed, players=2, human=None)
    brain = ProBrain(0, PRO)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    world.reveal_all(0)
    # No producer, so the saturation gate that normally unlocks an expansion is shut:
    # this is the state the dry-mine league found Master stuck in.
    for i in range(3):
        world.place_building(0, BuildingType.FARM, (hall.x - 4, hall.y + i * 3))
    for i in range(peasants):
        world.spawn_unit(0, UnitType.PEASANT, (hall.center[0] + 2 + i % 5, hall.center[1] + 2 + i // 5))
    near = min(world.mines(), key=lambda m: dist(m.center, hall.center))
    near.gold = gold_left
    world.players[0].gold, world.players[0].lumber = 4000, 3000
    return world, brain, near


def test_a_brain_takes_another_mine_when_the_face_is_full_even_with_gold_left():
    """Twelve hands on a mine with eight places is a saturated mine: the way to more gold is a second one."""
    world, brain, _near = _brain_with_a_failing_mine(gold_left=40_000, peasants=12)
    rng = random.Random(1)
    for _ in range(int(20 / SIM_DT)):
        brain.think(world, rng)
        world.step()
    assert BuildingType.TOWN_HALL in [o.type for o in brain._ordered(world)] or \
        len(world.player_buildings(0, BuildingType.TOWN_HALL)) > 1


def test_a_brain_takes_another_mine_when_the_one_it_works_is_running_out():
    """A hall goes up at a second mine while the first still has gold: waiting for it to run dry is too late.

    Master never expanded under scarcity — the wish sat behind the saturation
    gate, and a brain with no income never saturates — so a dry-mine rulebook
    saw no second hall in 336 seats.
    """
    world, brain, near = _brain_with_a_failing_mine()
    rng = random.Random(1)
    for _ in range(int(20 / SIM_DT)):
        brain.think(world, rng)
        world.step()
    halls = [b for b in world.player_buildings(0, BuildingType.TOWN_HALL)]
    ordered = [o.type for o in brain._ordered(world)]
    assert len(halls) > 1 or BuildingType.TOWN_HALL in ordered, "no second hall was even ordered"
    assert near.gold > 0, "the mine still had gold: the brain moved before it was starved"


def test_a_brain_with_room_at_the_face_and_gold_left_does_not_expand_early():
    """The rule fires on scarcity, not on every pass: a few hands on a rich mine stay where they are."""
    world, brain, _near = _brain_with_a_failing_mine(gold_left=40_000, peasants=4)
    rng = random.Random(1)
    for _ in range(int(20 / SIM_DT)):
        brain.think(world, rng)
        world.step()
    ordered = [o.type for o in brain._ordered(world)]
    assert len(world.player_buildings(0, BuildingType.TOWN_HALL)) == 1 and BuildingType.TOWN_HALL not in ordered


def test_choppers_sent_back_to_the_gold_do_not_name_a_mine_that_is_gone():
    """A remembered mine may have been dug out since it was last seen; ordering a peasant to it is refused.

    Found by the balance league crashing sixty matches in: the brain picked
    its destination from the player's memory, which keeps a mine nobody has
    looked at lately, and the model refuses a harvest on ground that no longer
    holds one. Seed 12 has a mine thirteen tiles from the hall — close enough
    for the brain to want it, too far for anything at home to see it go.
    """
    from warband.sim.model import Harvest

    world = mapgen.generate(seed=12, players=2, human=None)
    brain = ProBrain(0, PRO)
    world.reveal_all(0)
    brain.think(world, random.Random(1))  # the mines round about are now remembered
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    far = max((m for m in world.mines() if dist(m.center, hall.center) < 14),
              key=lambda m: dist(m.center, hall.center))
    for mine in list(world.mines()):
        if mine.id != far.id:
            world._remove_building(mine, reason="exhausted")  # leave only the one nobody can see
    tree = world.nearest_tree(hall.center, 24)
    for peasant in world.player_units(0):
        world.harvest([peasant.id], tree)
    world.update_vision()
    world._remove_building(far, reason="exhausted")  # dug out where nobody is looking
    assert far.id in [m.id for m in known_mines(world, 0)], "the player still remembers it"
    world.players[0].lumber = PRO.lumber_stock + 1000
    rng = random.Random(1)
    for _ in range(int(PRO.think_every / SIM_DT) + 2):
        brain.think(world, rng)  # must not raise
        world.step()
    assert not any(isinstance(o, Harvest) and isinstance(o.target, int)
                   for p in world.player_units(0) for o in p.orders), "nobody was sent to a mine that is not there"


@pytest.mark.slow
@pytest.mark.parametrize("posture", ["pro-vanguard", "pro-warden", "pro-hard"])
def test_a_pro_brain_builds_what_it_orders_its_builders_arrive_to_a_paid_order(posture: str) -> None:
    """WB-043: a build order is paid at the site, and the brain once spent the bank during the walk, so a quarter of
    its orders died on arrival. It holds their price now. Four minutes of two brains' play: the slow tier."""
    from warband.league.arena import make_agent

    world = mapgen.generate(seed=17, players=2, human=None)
    agents = [make_agent(posture, 0, 17), make_agent("pro-vanguard", 1, 17)]
    rngs = [random.Random(17), random.Random(18)]
    unpaid = []
    while world.time < 240 and world.winner is None:
        for agent, rng in zip(agents, rngs):
            agent.think(world, rng)
        world.step()
        unpaid += [event.text for event in world.take_events()
                   if event.kind == "refused" and event.player == 0 and event.text.startswith("Cannot build: Not enough")]
    assert not unpaid, unpaid


def test_a_defence_is_not_ordered_again_to_soldiers_already_on_their_way_to_the_threat():
    """The threat moves a little between passes; a soldier already attack-moving to it keeps the order it has.  Given
    anew every pass, the order restarted the walk of a soldier wedged in its own crowd, and with it the watchdog that
    would have walked it round the bodies in its way (fuzz seed 82).  ``_defend`` is the brain's own step, called as
    ``_military`` calls it."""
    world = mapgen.generate(seed=31, players=2, human=None)
    brain = ProBrain(0, PRO)
    army = _spawn(world, 0, UnitType.FOOTMAN, 3, 4)
    threat = _spawn(world, 1, UnitType.FOOTMAN, 9, 1)
    brain._defend(world, army, threat)
    orders = [u.order for u in army]
    threat[0].x += 0.6  # it steps aside
    brain._defend(world, army, threat)
    assert [u.order for u in army] == orders and all(a is b for a, b in zip((u.order for u in army), orders))
    threat[0].x += 6.0  # it got well away: the soldiers go after it
    brain._defend(world, army, threat)
    assert all(u.order is not before for u, before in zip(army, orders))


# -- A defence that is over --------------------------------------------------------

# Fuzz seed 81 (six players, 180×132, Bastion) on main as it was at 07cb63d, at 394.0 s: the base of player 2, the
# Grandmaster dwarves, as a lone footman of player 4 walking past comes into sight hacking at their barracks going up
# at (121, 3).  The ground is the seed's from x = 100 and y = 0; the buildings stand where the seed had them (the ones
# still going up stand finished here); every soldier and every peasant out of doors stands where the seed had it,
# with the dwarves' purse and upgrades of the moment.  The raider carries the wounds it had.
RAID_GROUND = (
    "ttttttttttttttttttttttttttttggggggggggggtttttttttttt", "tttgggggttttgggttttttggggggtggggggggggggggtttttttttt", "ttttgggggtttgggttttttggggtttgggggggggggggggttttttttt",
    "gggggggggggggggggttttggggtgtgggggggggggggggtttttttgg", "gggggggggggggggggttttgggggggggggggggggggggggttttttgg", "ggggggggggggggggggggggggtgggggggggggggggggggttttttgg",
    "ggggggggggggggggggggggggggggggggggggggggggggttgggggg", "gggtggggggttttggggtttgtggggggggggggggggggggggggggggg", "gggtggggggttttggggtttttgtggggggggggggggggggggggggggg",
    "gggtggggggttttggggtttttgtggggggggggggggggggggwwwrggg", "gggtttttttttttggggttttggtggggggggggggggggggttwwwrggg", "ggtttttttttrttwggttttgggttggggggggggggggggtttwwgrggg",
    "ggttttttttttttwgggtttggggtggggggggggggggggttggggrrgg", "ggtttttgtttttggggttttgggggggggggggggggggggttgggggggg", "ggtttgggggtttggggtttttgggrgggwwgggggggggggtggggggggg",
    "ggtwwwwwggtttggggtttttgggrgggggwwgggggggttgggggggggg", "ggtwwwwwwgttggggggttttgggrgggggggggggggtttgggggggggg", "ggtwwwwwggggggggggttttggggggggggggggggggtggggggggggg",
    "gggwwwwggggrggtttttttttgggggggggggggggggtgggggggggtt", "gggwwwwtggrrrgtttttttttgggggggggggggggggggggggggggtt", "ggggwwggggrrggtttttttttggggggggggggggggggggggggggggt",
    "ggggwwgggggrgggggttttttgggggggggggggggggtggggggggggg", "gggggggggggggggggtttttggggggggggggggggggttgggggggggg", "ggggggggggggggggggtttggggggggggggggggggtttgggggggggg",
    "ggggggggggggggggggtttggrrggggggggggggggtttgggggggggg", "gggggggggggrggggggtttggggggggggggggggggtttgggggggggg", "gggggggggggrrrrrggtttggggggggggggggggggtttgggggggggg",
    "gggggggggggrrrrrrgtttggggggggggggggggggtttggggggtggg",
)
RAID_BASE = [
    (BuildingType.TOWN_HALL, (133, 7)),
    (BuildingType.GOLD_MINE, (128, 3)),
    (BuildingType.GOLD_MINE, (145, 16)),
    (BuildingType.FARM, (133, 3)),
    (BuildingType.FARM, (133, 12)),
    (BuildingType.BARRACKS, (128, 8)),
    (BuildingType.FARM, (137, 7)),
    (BuildingType.BLACKSMITH, (136, 2)),
    (BuildingType.STABLES, (136, 13)),
    (BuildingType.FARM, (140, 9)),
    (BuildingType.FARM, (140, 6)),
    (BuildingType.TOWER, (126, 16)),
    (BuildingType.WORKSHOP, (136, 19)),
    (BuildingType.FARM, (137, 10)),
    (BuildingType.LUMBER_MILL, (129, 19)),
    (BuildingType.FARM, (133, 0)),
    (BuildingType.TOWER, (133, 15)),
    (BuildingType.CHURCH, (122, 12)),
    (BuildingType.FARM, (140, 12)),
    (BuildingType.FARM, (140, 3)),
    (BuildingType.FARM, (125, 8)),
    (BuildingType.BARRACKS, (121, 3)),  # going up
    (BuildingType.BARRACKS, (125, 19)),  # going up
    (BuildingType.FARM, (129, 16)),  # going up
]
RAID_ARMY = [
    (UnitType.FOOTMAN, (134.4565225676375, 14.998521498151282), -0.12731135828078544),
    (UnitType.FOOTMAN, (130.47925550508398, 11.002470471630149), -2.149055000387059),
    (UnitType.FOOTMAN, (131.07239419067702, 14.999999999999998), 0.8625255247040824),
    (UnitType.FOOTMAN, (133.42104822887887, 14.999999979293152), -1.726380458283048),
    (UnitType.FOOTMAN, (133.1321823846172, 11.715467309601125), -0.2535524451102172),
    (UnitType.KNIGHT, (126.99103982467864, 13.983855291065105), 3.012462267308269),
    (UnitType.KNIGHT, (134.4692995468381, 11.693107358023639), -0.032836676969519196),
    (UnitType.KNIGHT, (132.24748024556277, 14.999817717354793), 0.5963405316814763),
    (UnitType.FOOTMAN, (128.4779012116579, 14.758407183214945), 1.6742893482849845),
    (UnitType.KNIGHT, (132.9354026670071, 13.004053475327154), -0.30062700379034535),
    (UnitType.FOOTMAN, (128.2909933221048, 12.171817613382961), -2.3375771584298306),
    (UnitType.KNIGHT, (131.77094196126944, 11.372551065969006), -0.51683566251454),
    (UnitType.KNIGHT, (128.38028196951498, 11.000000000099785), 3.041738994385179),
    (UnitType.CATAPULT, (129.44416600936424, 13.99956052453885), -0.5165370243501908),
    (UnitType.KNIGHT, (129.36513331735625, 12.634412771088074), -0.5170384370513998),
    (UnitType.KNIGHT, (129.49991840032027, 11.00000002907614), 2.8557413912585456),
    (UnitType.CLERIC, (128.46073876996584, 13.331345717209988), 1.627123874378892),
    (UnitType.CATAPULT, (130.6550067516684, 12.18717589121747), -1.7499680374959754),
    (UnitType.FOOTMAN, (131.73368302581534, 14.165804586999439), 2.716724081648916),
    (UnitType.KNIGHT, (130.79303510296427, 13.892204762224774), 0.8837418096116441),
    (UnitType.CLERIC, (131.1728099899045, 13.037333637087666), -0.41092094623619235),
]
RAID_PEASANTS = [
    (123.5, 22.5),
    (131.5, 6.5),
    (138.4891977690289, 22.500000000000036),
    (140.4001420666361, 19.36257459205308),
    (132.6334843994493, 5.631325313030382),
    (123.66250000000007, 18.5),
    (146.23411118315954, 8.508763352947275),
]
RAIDER = ((117.40884730840087, 8.642787605428078), -1.4912013828817259, 64)  # player 4's, a dwarf footman, hacking at the barracks going up at (121, 3)


def _seed_81_raid() -> tuple[World, list, object]:
    letters = {terrain.value[0]: terrain for terrain in Terrain}
    ground = [[Terrain.GRASS] * 152 for _ in range(len(RAID_GROUND))]
    for y, row in enumerate(RAID_GROUND):
        for dx, letter in enumerate(row):
            ground[y][100 + dx] = letters[letter]
    world = World(152, len(RAID_GROUND), ground, 5, human=None, layout=Layout.BASTION, scripted=True,
                  races=(Race.ELF, Race.ORC, Race.DWARF, Race.HUMAN, Race.DWARF))  # scripted: the raider's death ends no match
    placed = {pos: world.place_building(None if kind is BuildingType.GOLD_MINE else 2, kind, pos) for kind, pos in RAID_BASE}
    army = []
    for kind, pos, facing in RAID_ARMY:
        soldier = world.spawn_unit(2, kind, pos)
        soldier.facing = facing
        army.append(soldier)
    for pos in RAID_PEASANTS:
        world.spawn_unit(2, UnitType.PEASANT, pos)
    dwarves = world.players[2]
    dwarves.gold, dwarves.lumber = 650, 1450
    dwarves.upgrades.update({Upgrade.ARMOR_1, Upgrade.ARROWS_1, Upgrade.BLADES_1, Upgrade.BLASTING_POWDER,
                             Upgrade.DEEP_MINING, Upgrade.MARKSMANSHIP})
    pos, facing, hp = RAIDER
    raider = world.spawn_unit(4, UnitType.FOOTMAN, pos)
    raider.facing, raider.hp = facing, hp
    world.attack([raider.id], placed[(121, 3)].id)
    return world, army, raider


def test_once_the_raider_is_down_nobody_walks_on_to_where_it_was():
    """The brain sends its army at a raider near its buildings, again as the raider moves.  Once the raider was dead,
    the soldiers who had got there stood idle and were sent home, and the rest walked on to the empty spot through
    them: in the seed, down the one-tile passage below the barracks, where the army stood in its own way for twenty
    seconds and fuzz reported a knight wedged in it.  Here the raider falls six seconds in, and every soldier the
    defence sent has turned for home once the base has been calm for :data:`CALM` (a threat that drops out of sight for
    a moment is no reason to turn a defence round); under the old brain the last of them was still walking out
    fourteen seconds after the raider fell."""
    world, army, raider = _seed_81_raid()
    brain, rng = make_brain(2, Difficulty.GRANDMASTER, 81), random.Random(81)
    brain.think(world, rng)
    one_pass = brain.brain.profile.think_every  # the posture the seed's dwarves played (a RaceBrain picks it on its first pass)
    down = None
    defended = walking = 0.0
    for _ in range(round(20.0 / SIM_DT)):
        brain.think(world, rng)
        world.step()
        world.take_events()
        sent = [u for u in army if u.id in world.units and isinstance(u.order, AttackMove)]
        if down is None:
            defended = max(defended, len(sent))
            if raider.id not in world.units:
                down = world.time
        elif sent:
            walking = world.time - down
        elif world.time > down + CALM + 2.0:
            break
    assert defended > len(army) / 2 and down is not None, "the army goes out after the raider and kills it"
    assert walking <= CALM + 2 * one_pass, f"soldiers walked on at the raider's last place {walking:.1f} s after it fell"


def test_soldiers_still_walking_at_a_camp_that_fell_turn_for_home():
    """The same for a camp: the army walks at the lair, and when the lair is down the ones still on their way turn
    for home rather than walk on to where it stood and back.  The soldiers are fewer than a push needs, so after the
    camp the brain gathers them rather than sending them anywhere else."""
    world = World(48, 32, [[Terrain.GRASS] * 48 for _ in range(32)], 2, human=None, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 12))
    world.place_building(1, BuildingType.TOWN_HALL, (43, 1))  # a rival it knows of, so it is not out hunting for one
    army = [world.spawn_unit(0, UnitType.FOOTMAN, (9.5 + i, 14.5)) for i in range(4)]
    camp = camps.place(world, (32, 16), [UnitType.WOLF], 100)
    world.reveal_all(0)
    brain = ProBrain(0, replace(PRO, creep_from=0.0, push_after=0.0, push_upgrades=0, creep_army=3, creep_ratio=0.0))
    rng = random.Random(1)
    lair = world.buildings[camp.lair]
    spot = None
    for _ in range(round(3.0 / SIM_DT)):
        brain.think(world, rng)
        world.step()
        if spot is None and all(isinstance(u.order, AttackMove) for u in army):
            spot = army[0].order.target
    assert spot is not None and dist(spot, lair.center) < 3.0, "the four go for the camp"
    assert all(u.x < 25.0 for u in army), "and are still on their way"
    world.units[camp.guards[0]].hp = 0
    lair.hp = 1
    world._hit(lair, 40, player=0, source=army[0].id, source_type=UnitType.FOOTMAN.value)  # the lair falls, as test_camps tears one down
    for _ in range(round(2 * brain.profile.think_every / SIM_DT) + 1):
        brain.think(world, rng)
        world.step()
    assert camp.lair not in world.buildings
    assert not any(isinstance(u.order, AttackMove) for u in army), [u.order for u in army]
    assert all(isinstance(u.order, Move) and u.order.target[0] < 20.0 for u in army), [u.order for u in army]
