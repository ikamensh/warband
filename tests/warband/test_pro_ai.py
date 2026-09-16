"""What the stronger brain must keep doing, including two things it once got wrong.

Both regressions were found by watching matches rather than by reasoning:
an army that re-decided every pass oscillated in and out of the enemy base
without ever fighting, and a remembered enemy count that was a running total
reported roughly ten times the army that was there.
"""

from __future__ import annotations

import random

from warband import mapgen
from warband.model import dist
from warband.pro_ai import PRO, ProBrain, _tower_strength, strength
from warband.rules import SIM_DT, BuildingType, UnitType


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


def test_a_soldier_seen_to_die_stops_counting_at_once():
    """Three archers stood in our base; two died in front of us. One is left, not three fading."""
    from dataclasses import replace
    world, brain = _world_with_army()
    brain.profile = replace(PRO, count_kills=True)
    archers = _raiders_at_our_base(world, 3)
    brain._observe(world)
    assert brain.remembered(1)[UnitType.ARCHER] == 3
    for unit in archers[:2]:
        world.units.pop(unit.id)  # what the model does with the dead at the end of a step
    world.update_vision()
    brain._observe(world)
    assert brain.remembered(1)[UnitType.ARCHER] == 1


def test_a_soldier_that_walked_out_of_sight_is_not_counted_as_dead():
    from dataclasses import replace
    world, brain = _world_with_army()
    brain.profile = replace(PRO, count_kills=True)
    archers = _raiders_at_our_base(world, 3)
    brain._observe(world)
    for unit in archers:
        unit.x, unit.y = world.width - 3.0, world.height - 3.0  # far away, out of our vision
    world.update_vision()
    brain._observe(world)
    assert brain.remembered(1)[UnitType.ARCHER] > 2.5, "out of sight is not dead"


def test_the_wood_share_puts_that_many_hands_on_the_trees_and_takes_them_off_again():
    from dataclasses import replace
    from warband.model import Harvest
    world, brain = _world_with_army()
    brain.profile = replace(PRO, wood_share=0.5, wood_stock=900)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    for i in range(8 - sum(1 for u in world.player_units(0) if u.is_worker)):
        world.spawn_unit(0, UnitType.PEASANT, (hall.center[0] + 3 + i * 0.6, hall.center[1] + 3))
    peasants = [u for u in world.player_units(0) if u.is_worker]
    assert len(peasants) == 8
    world.players[0].gold, world.players[0].lumber = 3000, 0
    for _ in range(4):
        brain._economy(world)  # two moves a pass, at most
    assert sum(1 for p in peasants if brain._on_lumber(p)) == 4
    world.players[0].lumber = 2000  # plenty: the crews go back to the gold, a third of the share stays
    for _ in range(4):
        brain._economy(world)
    on_wood = [p for p in peasants if brain._on_lumber(p)]
    assert len(on_wood) == round(8 * 0.5 / 3) == 1
    assert all(isinstance(p.order, Harvest) and isinstance(p.order.target, int) for p in peasants if p not in on_wood), \
        "the rest were sent to a mine, not left idle"


def test_a_profile_plays_each_race_by_its_own_numbers():
    from dataclasses import replace
    from warband.rules import Race
    world, _ = _world_with_army()
    profile = replace(PRO, min_army=5, by_race={Race.DWARF: {"min_army": 12}})
    assert profile.for_race(Race.DWARF).min_army == 12
    assert profile.for_race(Race.ELF).min_army == 5
    assert profile.for_race(Race.DWARF).by_race == profile.by_race, "the overrides travel with the profile"
    brain = ProBrain(0, profile)
    world.players[0].race = Race.DWARF
    brain.think(world, random.Random(0))
    assert brain.profile.min_army == 12


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
    """Regression: an unseen enemy read as strength zero, so ten soldiers walked in blind."""
    world, brain = _world_with_army()
    army = _spawn(world, 0, UnitType.FOOTMAN, 2, 10)
    world.time = 600.0  # long past any sighting
    enemy_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0].center
    assert brain._defenders_near(world, enemy_hall) >= strength(world, army) * PRO.symmetry_prior


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

def test_the_brain_plays_a_match_without_raising_and_builds_an_army():
    """The cheapest cover there is: the whole thing actually runs."""
    world = mapgen.generate(seed=12, players=2, human=None)
    brains = [ProBrain(0, PRO), ProBrain(1, PRO)]
    rngs = [random.Random(i) for i in range(2)]
    for _ in range(int(240 / SIM_DT)):
        if world.winner is not None:
            break
        for brain, rng in zip(brains, rngs):
            brain.think(world, rng)
        world.step()
        world.take_events()
    for player in (0, 1):
        assert any(not u.is_worker for u in world.player_units(player)), f"player {player} trained nothing"
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
    bystanders = sum(1 for p in world.players if p.id != 0 and p.alive) - 1
    assert bystanders == 1
    assert PRO.attack_ratio * (1 + PRO.ffa_caution * bystanders) > PRO.attack_ratio


def test_a_free_for_all_runs_to_placements():
    """Four brains, one map, and a finishing order rather than a winner."""
    from warband.arena import MatchSpec, play
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
    brain = ProBrain(0, PRO)
    riders = _spawn(world, 0, UnitType.SCOUT, 2, 2)
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
