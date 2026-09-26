"""Footmen hold a line (WB-050): slower and better armoured, one armour more for a comrade at each side, and a group of
them marches as a line across the way it goes, re-forming past what split it.  The orc grunt is the fast brawler
instead: no line, no flank."""

import math
import random

from warband.sim.model import Move, World
from warband.sim.races import RACES
from warband.sim.rules import FORMATION_SPACING, BuildingType, Race, Terrain, UnitType


def field(rocks: set[tuple[int, int]] = frozenset(), races: tuple[Race, Race] = (Race.HUMAN, Race.HUMAN)) -> World:
    world = World(40, 20, [[Terrain.ROCK if (x, y) in rocks else Terrain.GRASS for x in range(40)] for y in range(20)], 2,
                  rng=random.Random(1))
    for player, race in zip(world.players, races):
        player.race = race
    world.place_building(0, BuildingType.TOWN_HALL, (0, 0))
    world.place_building(1, BuildingType.TOWN_HALL, (36, 16))
    return world


def test_footmen_are_slow_and_armoured_and_the_grunt_is_the_fast_brawler() -> None:
    """Read from the rules, which race balance tunes (WB-073 gave the grunt one armour back): what each race's
    footman is beside the others and beside its own archer and peasant."""
    line = {race: RACES[race].units[UnitType.FOOTMAN] for race in Race}
    grunt = line.pop(Race.ORC)
    assert not grunt.formation and all(footman.formation for footman in line.values())
    for race, footman in line.items():
        assert footman.speed < RACES[race].units[UnitType.PEASANT].speed  # a fleeing peasant outruns the line
        assert footman.armor > RACES[race].units[UnitType.ARCHER].armor
        assert footman.speed < grunt.speed and footman.armor > grunt.armor
    assert line[Race.DWARF].speed < line[Race.HUMAN].speed < line[Race.ELF].speed
    assert line[Race.DWARF].armor > line[Race.HUMAN].armor == line[Race.ELF].armor


def test_a_footman_wears_one_more_armour_for_a_comrade_at_each_side() -> None:
    world = field()
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    footman.facing = 0.0  # facing east: its left is north, the lesser y
    alone = world.armor_of(footman)
    left = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 9.5))
    assert world.flanks(footman) == 1 and world.armor_of(footman) == alone + 1
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 11.5))
    assert world.flanks(footman) == 2 and world.armor_of(footman) == alone + 2
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 8.6))  # a second on the same side guards nothing more
    assert world.flanks(footman) == 2
    left.x, left.y = 11.5, 10.5  # ahead of it is no flank
    assert world.flanks(footman) == 1
    world.spawn_unit(0, UnitType.ARCHER, (10.5, 9.5))  # nor is an archer beside it
    assert world.flanks(footman) == 1


def test_a_grunt_has_no_flank() -> None:
    world = field(races=(Race.ORC, Race.HUMAN))
    grunt = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5))
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 9.5))
    world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 11.5))
    assert world.flanks(grunt) == 0 and world.armor_of(grunt) == grunt.info.armor


def slots(world: World, units) -> list[tuple[float, float]]:
    return [world._slot(u.order) for u in units]  # the orders' own destinations: what the unit walks to


def test_sent_off_together_footmen_take_places_in_a_line_across_the_march_and_keep_their_sides() -> None:
    world = field()
    column = [world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5 + i)) for i in range(5)]  # centred on the target's row
    world.move([u.id for u in column], (30.5, 10.5))
    places = slots(world, column)
    assert all(isinstance(u.order, Move) and u.order.target == (30.5, 10.5) for u in column)  # one target: group pace holds
    assert all(abs(x - 30.5) < 1e-9 for x, _ in places)  # a line across an eastward march
    ys = [y for _, y in places]
    assert ys == sorted(ys) and all(abs(b - a - FORMATION_SPACING) < 1e-9 for a, b in zip(ys, ys[1:]))  # no one crosses
    ten = [world.spawn_unit(0, UnitType.FOOTMAN, (5.5 + (i % 2), 6.0 + i)) for i in range(10)]  # centred on the target's row too
    world.attack_move([u.id for u in ten], (30.5, 10.5))
    rows = sorted({round(x, 6) for x, _ in slots(world, ten)})
    assert rows == [29.5, 30.5]  # eight in front, two behind


def test_a_step_aside_is_no_march_and_a_slot_in_the_rocks_goes_to_the_spot() -> None:
    world = field(rocks={(x, y) for x in range(28, 33) for y in range(4, 9)})
    pair = [world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 10.5)), world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 11.5))]
    world.move([u.id for u in pair], (12.5, 11.0))
    assert all(u.order.offset is None for u in pair)
    column = [world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 7.0 + i)) for i in range(7)]
    world.move([u.id for u in column], (30.5, 11.5))  # the line's north end would stand in the rocks
    assert [u.order.offset is None for u in column] == [True] + [False] * 6


def test_a_line_of_five_keeps_its_shape_round_a_rock_and_forms_up_again_past_it() -> None:
    """Twenty-five tiles east with a three-tile rock in the way: the line splits round it, is dressed again (less
    than a tile and a half between first and last along the march, each back on its own side) by the time it is five
    tiles past, and ends in its slots in its order.  Before WB-050 the five went round in single file and stayed so."""
    world = field(rocks={(x, y) for x in range(15, 18) for y in range(9, 12)})
    line = [world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.0 + i)) for i in range(5)]
    for u in line:
        u.facing = 0.0
    world.move([u.id for u in line], (30.5, 10.5))
    places = slots(world, line)
    worst = 0.0
    past = False
    for _ in range(int(25 / 0.05)):
        world.step()
        xs, ys = [u.x for u in line], [u.y for u in line]
        worst = max(worst, max(xs) - min(xs))
        if not past and sum(xs) / 5 >= 23.0:
            past = True
            assert max(xs) - min(xs) < 1.5 and ys == sorted(ys), [u.pos for u in line]
        if all(not u.orders for u in line):
            break
    assert past and all(not u.orders for u in line)
    xs, ys = [u.x for u in line], [u.y for u in line]
    assert max(xs) - min(xs) < 1.5 and ys == sorted(ys), [u.pos for u in line]  # dressed at its slots, in its order
    assert all(math.dist(u.pos, p) < 0.6 for u, p in zip(line, places)), [u.pos for u in line]
    assert worst < 3.5, worst


def test_a_save_from_before_the_line_loads() -> None:
    world = field()
    pair = [world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 8.5)), world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 9.5))]
    world.move([u.id for u in pair], (30.5, 10.5))
    data = world.to_dict()
    for unit in data["units"]:
        for order in unit["orders"]:
            order.pop("offset", None)
    copy = World.from_dict(data)
    assert all(u.order.offset is None for u in copy.units.values() if u.order is not None)
    again = World.from_dict(world.to_dict())
    assert [again.units[u.id].order for u in pair] == [u.order for u in pair]


def test_a_footman_felled_earlier_in_the_step_does_not_bring_the_match_down() -> None:
    """A unit killed earlier in a step still takes its turn in it.  A marching footman alone in its row, felled after a
    comrade drew the step's line without it, found its row missing from the line: KeyError, and the match, or an
    online room, was over."""
    world = field()
    knight = world.spawn_unit(1, UnitType.KNIGHT, (3.5, 14.5))  # spawned first: its blow lands before the footmen move
    front = [world.spawn_unit(0, UnitType.FOOTMAN, (6.5, 8.5 + i)) for i in range(8)]
    rear = world.spawn_unit(0, UnitType.FOOTMAN, (4.5, 12.5))  # alone in the second row, and the last to take its turn
    world.move([f.id for f in (*front, rear)], (34.5, 12.5))
    rear.hp = 2
    world.attack([knight.id], rear.id)
    for _ in range(200):
        world.step()
        if rear.id not in world.units:
            break
    assert rear.id not in world.units and all(f.id in world.units for f in front)
