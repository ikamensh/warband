"""A side left with no hall and no building that trains stands exposed: its last holdings are revealed, with public
news, to the rival fighting it, and only while exactly two sides remain in play (WB-072).  In a free-for-all a
bystander would learn where a weakened side hides for nothing it did, so there the reveal waits for the last two.
Each seat's view is read from its own snapshot, as the online authority sends it."""

import json
import random

from warband.brains.adjutant import known_towers
from warband.brains.ai import known_enemy_buildings
from warband.online.authority import WarbandMatch
from warband.sim.model import World, tile_center
from warband.sim.rules import BuildingType, Terrain, UnitType
from warband.story.mission_scene import build_world
from warband.story.missions import CAMPAIGN


def sent(match: WarbandMatch, seat: int) -> dict:
    return json.loads(json.dumps(match.snapshot(seat)))


def shown(match: WarbandMatch, seat: int) -> set[int]:
    """The buildings in *seat*'s snapshot."""
    return {b['id'] for b in sent(match, seat)['world']['buildings']}


def news(match: WarbandMatch, seat: int) -> list[str]:
    return [fields['kind'] for _index, fields in sent(match, seat)['events']]


def expose(match: WarbandMatch, seat: int, farm_at: tuple[int, int]):
    """*seat* keeps a farm at *farm_at* and its peasants, and loses its hall: nothing left that trains."""
    world = match.world
    farm = world.place_building(seat, BuildingType.FARM, farm_at)
    world.player_buildings(seat, BuildingType.TOWN_HALL)[0].hp = 0
    for _ in range(8):  # the fall, then a fog recomputation
        match.step()
    assert world.players[seat].alive and not world.player_buildings(seat, BuildingType.TOWN_HALL)
    return farm


def far_sentries(match: WarbandMatch, seat: int) -> None:
    """Two footmen of *seat* in opposite corners: the box its sight spans is the whole map while the ground between
    stays dark, so nothing the rules keep from the seat is left out merely for lying far from its forces."""
    world = match.world
    world.spawn_unit(seat, UnitType.FOOTMAN, (1.5, world.height - 1.5))
    world.spawn_unit(seat, UnitType.FOOTMAN, (world.width - 1.5, 1.5))


def test_a_duel_reveals_the_exposed_sides_last_holdings_to_its_rival_and_says_so() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    farm = expose(match, 1, (34, 24))
    assert farm.id in shown(match, 0), "the rules reveal the farm, and seat 0 is sent it wherever its forces stand"
    assert farm.id in {record.id for record in known_enemy_buildings(world, 0)}, "and remembers it after"
    assert news(match, 0).count('exposed') == 1 and news(match, 1).count('exposed') == 1


def rebuilt(match: WarbandMatch, seat: int) -> World:
    """The world an online client rebuilds from *seat*'s snapshot, and the online AI plans on."""
    return World.from_dict(sent(match, seat)['world'])


def assert_rebuilt_as_the_authority_knows(match: WarbandMatch, seat: int) -> None:
    """The client sees what the authority lets *seat* see and remembers what the authority says it remembers: it
    holds too little of its rivals to judge an exposure of its own."""
    world, client = match.world, rebuilt(match, seat)
    assert client.visible[seat] == world.visible[seat]
    assert client.worker_knowledge[seat].buildings == world.worker_knowledge[seat].buildings
    assert [t.id for t in known_towers(client, seat)] == [t.id for t in known_towers(world, seat)]


def test_a_duel_reveals_as_much_to_the_rebuilt_world_as_the_authority_does() -> None:
    match = WarbandMatch(seed=3)
    farm = expose(match, 1, (34, 24))
    client = rebuilt(match, 0)
    assert client.any_visible(0, farm.rect), "the revealed farm stands in the light, not in memory"
    assert_rebuilt_as_the_authority_knows(match, 0)
    assert_rebuilt_as_the_authority_knows(match, 1)


def test_a_rebuilt_world_that_sees_a_rivals_farm_alone_forgets_no_tower_beside_it() -> None:
    """A scout at the edge of a base sees a farm and nothing that trains: to the snapshot's world that is a side
    exposed, and a reveal it judged itself lit the tower touching the farm, which the snapshot leaves out for the
    seat no longer sees it, and so erased it from the seat's memory."""
    match = WarbandMatch(seed=3)
    world = match.world
    farm = world.place_building(1, BuildingType.FARM, (31, 21))
    tower = world.place_building(1, BuildingType.TOWER, (33, 21))
    scout = world.spawn_unit(0, UnitType.FOOTMAN, tile_center((33, 24)))
    world.update_vision()
    assert world.any_visible(0, farm.rect) and world.any_visible(0, tower.rect)
    scout.x, scout.y = tile_center((27, 21))  # stepped back to where it sees the farm alone
    world.update_vision()
    assert world.any_visible(0, farm.rect) and not world.any_visible(0, tower.rect)
    assert not any(world.any_visible(0, b.rect) for b in world.player_buildings(1) if b not in (farm, tower))
    assert [t.id for t in known_towers(world, 0)] == [tower.id] and not world.exposures()
    assert_rebuilt_as_the_authority_knows(match, 0)


def test_a_three_side_free_for_all_reveals_nothing_until_two_remain() -> None:
    match = WarbandMatch(seed=5, width=64, height=48, players=3)
    world = match.world
    for seat in (0, 2):
        far_sentries(match, seat)
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    farm = expose(match, 1, (hall.x - 3, hall.y))
    for _ in range(20):
        match.step()
    for seat in (0, 2):  # neither bystander is told where seat 1 hides, nor that it lies exposed
        assert not world.is_visible(seat, (farm.x, farm.y))
        assert not {b.id for b in world.player_buildings(1)} & shown(match, seat)
        assert 'exposed' not in news(match, seat)
    assert 'exposed' not in news(match, 1)

    match.apply(2, {'action': 'resign', 'args': [2], 'kwargs': {}})
    for _ in range(8):
        match.step()
    assert [p.alive for p in world.players[:world.seats]] == [True, True, False]
    assert farm.id in shown(match, 0), "the last two: seat 0 is told where its one rival's holdings stand"
    assert farm.id not in shown(match, 2), "and seat 2, out of the match, is not"
    assert news(match, 0).count('exposed') == 1 and news(match, 1).count('exposed') == 1


def test_a_side_exposed_while_three_fight_is_announced_once_when_two_remain_across_a_save() -> None:
    world = _three_sides()
    world.update_vision()
    farm = world.player_buildings(1)[0]
    assert not world.is_visible(0, (farm.x, farm.y)) and not _exposed_news(world)
    world = World.from_dict(json.loads(json.dumps(world.to_dict())))
    world.clear_player(2)  # the third side out: two remain
    world.update_vision()
    assert world.is_visible(0, (farm.x, farm.y)) and not world.is_visible(2, (farm.x, farm.y))
    assert [e.player for e in _exposed_news(world)] == [1]
    world.events.clear()
    world.update_vision()
    assert not _exposed_news(world), "once"
    loaded = World.from_dict(json.loads(json.dumps(world.to_dict())))
    loaded.update_vision()
    assert loaded.is_visible(0, (farm.x, farm.y)) and not _exposed_news(loaded), "a load already knows it was told"


def _three_sides() -> World:
    """Seat 1 down to a farm and a peasant between two halls, out of the sight of both."""
    world = World(40, 20, [[Terrain.GRASS] * 40 for _ in range(20)], 3, rng=random.Random(1))
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.FARM, (20, 15))
    world.spawn_unit(1, UnitType.PEASANT, (21.5, 18.5))
    world.place_building(2, BuildingType.TOWN_HALL, (35, 1))
    return world


def _exposed_news(world: World) -> list:
    return [e for e in world.events if e.kind == 'exposed']


def test_the_court_at_war_hides_its_last_lodges_until_the_orcs_are_driven_off() -> None:
    """The one mission with three sides: the Court of Thorns, the truce refused.  Razing the Court's hall and barracks
    while Ironjaw's warband still fights shows the player nothing; once the orcs are out it shows the rest."""
    run = build_world(CAMPAIGN.mission("court_of_thorns"), flags={"truce": False})
    world = run.world
    assert world.scripted and [p.alive for p in world.players[:world.seats]] == [True, True, True]
    for b in world.player_buildings(1):
        if b.type is BuildingType.TOWN_HALL or b.info.trains:
            world._remove_building(b, reason="destroyed")  # staged: what a siege would end in, without the siege
    towers = world.player_buildings(1, BuildingType.TOWER)
    assert towers and world.players[1].alive
    world.update_vision()
    assert not any(world.any_visible(0, tower.rect) for tower in towers)
    world.clear_player(2)
    world.update_vision()
    assert all(world.any_visible(0, tower.rect) for tower in towers)
    assert [e.player for e in _exposed_news(world)] == [1]
