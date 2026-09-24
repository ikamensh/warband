"""A seat's snapshot is the match as that seat may know it (WB-011), and so is every answer to its orders.

All of its own; of everyone else's, what its forces see now; of the ground and the mines out of sight,
what it remembers; of the news, what it saw happen, its own affairs and what is public.  The client
already drew the fog honestly (WB-027), but everything it hid was in the data, a JSON dump away.
"""
import json

import pytest

from saga2d import CommandError, Game
from warband.online.authority import WarbandMatch
from warband.sim.model import dist, tile_center
from warband.sim.rules import BuildingType, Terrain, UnitType, Upgrade


def fogged_match() -> WarbandMatch:
    """A match two seconds in: each seat sees its own corner, nothing of the other's."""
    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    return match


def sent(match: WarbandMatch, seat: int) -> dict:
    """What travels to *seat*: the snapshot as JSON, the way the server writes it to the socket."""
    return json.loads(json.dumps(match.snapshot(seat)))


def answer(match: WarbandMatch, seat: int, action: str, args: list, **kwargs) -> str:
    """What *seat* is told of an order it sends: "accepted", or the refusal it reads."""
    try:
        match.apply(seat, {'action': action, 'args': args, 'kwargs': kwargs})
    except CommandError as exc:
        return str(exc)
    return 'accepted'


def site_near(world, player: int, building_type: BuildingType, around: tuple[int, int]) -> tuple[int, int]:
    """Open ground near *around* where *player*, who must have explored it, may build."""
    for reach in range(2, 12):
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                site = (around[0] + dx, around[1] + dy)
                if world.can_place(building_type, site, player) is None:
                    return site
    raise AssertionError(f"no room for a {building_type.value} near {around}")


def in_front_of_seat_0(match: WarbandMatch):
    """A rival footman marching past seat 0's hall and a rival barracks at work beside it, both in seat 0's sight."""
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    site = site_near(world, 0, BuildingType.BARRACKS, (hall.x + hall.size + 3, hall.y))  # ground seat 1 has not explored
    camp = world.place_building(1, BuildingType.BARRACKS, site)
    camp.queue.append(UnitType.FOOTMAN)
    camp.rally = (2.5, 2.5)
    world.set_auto_train(camp.id, UnitType.ARCHER, True)
    footman = world.spawn_unit(1, UnitType.FOOTMAN, tile_center((site[0] - 1, site[1] - 1)))
    world.move([footman.id], (world.width - 3.5, world.height - 3.5))
    world.update_vision()
    assert world.is_visible(0, footman.tile) and world.is_visible(0, camp.tiles()[0])
    return camp, footman


def test_a_seat_has_all_of_its_own_and_of_the_rival_only_what_it_sees_without_its_intentions() -> None:
    match = fogged_match()
    world = match.world
    camp, footman = in_front_of_seat_0(match)
    snapshot = sent(match, 0)['world']
    units = {u['id']: u for u in snapshot['units']}
    buildings = {b['id']: b for b in snapshot['buildings']}
    assert {u.id for u in world.player_units(0)} <= units.keys() and {b.id for b in world.player_buildings(0)} <= buildings.keys()
    stranger = units[footman.id]
    assert stranger['orders'] == [] and stranger['worker_orders'] == [] and stranger['home'] is None
    assert (stranger['x'], stranger['y'], stranger['hp']) == (footman.x, footman.y, footman.hp)
    works = buildings[camp.id]
    assert works['queue'] == [] and works['train_progress'] == 0 and works['rally'] is None and works['research'] is None
    assert works['auto'] == [], "what a rival's barracks trains endlessly is its own business"
    far = [u.id for u in world.player_units(1) if not world.is_visible(0, u.tile)]
    assert far and not set(far) & units.keys(), "the rival's units at home travel to seat 0"
    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    assert rival_hall.id not in buildings, "the rival's hall, never seen, travels to seat 0"
    theirs = sent(match, 1)['world']
    assert {u['id']: u for u in theirs['units']}[footman.id]['orders'], "a seat's own orders are its own to see"
    assert {b['id']: b for b in theirs['buildings']}[camp.id]['queue'] == ['footman']
    assert {b['id']: b for b in theirs['buildings']}[camp.id]['auto'] == ['archer']


def test_a_rivals_building_going_up_in_sight_stays_in_the_seats_world() -> None:
    """The snapshot left a rival site's builder out with the rest of its work, and loading it took the site for one
    left half built in a save from before WB-048, when builders could walk off, and removed it: online, a seat never
    saw a rival's building go up, a tower beside its hall included, until it stood."""
    from warband.sim.model import World

    match = fogged_match()
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    site = world.place_building(1, BuildingType.FARM, site_near(world, 0, BuildingType.FARM, (hall.x + hall.size + 3, hall.y)), done=False)
    builder = next(u for u in world.player_units(1) if u.is_worker and not u.hidden)
    world._start_building(builder, site)  # staged: a rival peasant raising it where seat 0 looks, without its walk across the map
    world.update_vision()
    assert world.is_visible(0, site.tiles()[0])
    seen = World.from_dict(sent(match, 0)['world'])
    assert site.id in seen.buildings and not seen.buildings[site.id].done
    assert builder.id not in seen.units, "the builder is inside its site, out of sight"


def test_a_worker_in_a_mine_is_nobodys_business_but_its_owners() -> None:
    match = fogged_match()
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    peasant = world.spawn_unit(1, UnitType.PEASANT, tile_center((hall.x + hall.size + 1, hall.y + hall.size + 1)))
    peasant.inside = world.mines()[0].id
    world.update_vision()
    assert peasant.hidden
    assert peasant.id not in {u['id'] for u in sent(match, 0)['world']['units']}
    assert peasant.id in {u['id'] for u in sent(match, 1)['world']['units']}


def test_the_rivals_purse_research_plans_and_alarms_stay_home_until_the_match_is_decided() -> None:
    match = fogged_match()
    world = match.world
    rival = world.players[1]
    rival.gold, rival.lumber = 4321, 1234
    rival.upgrades.add(Upgrade.BLADES_1)
    rival.stats["units_trained"] = 17
    rival.last_alert = 40.5
    rival.last_hit = 12.5
    rival.assembly = (41.5, 31.5)
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    world.plan_building(1, BuildingType.FARM, site_near(world, 1, BuildingType.FARM, (hall.x, hall.y)))
    snapshot = sent(match, 0)['world']
    theirs = snapshot['players'][1]
    assert (theirs['gold'], theirs['lumber'], theirs['upgrades'], theirs['last_alert'], theirs['last_hit'], theirs['assembly']) == (
        0, 0, [], None, None, None)
    assert not any(theirs['stats'].values()) and theirs['stats'].keys() == rival.stats.keys()
    assert (theirs['name'], theirs['race'], theirs['alive']) == (rival.name, rival.race.value, True)
    assert not [plan for plan in snapshot['settlement']['plans'] if plan['player'] == 1]
    assert snapshot['settlement']['next_id'] == 1 + max((plan['id'] for plan in snapshot['settlement']['plans']), default=0)
    ours = sent(match, 1)['world']
    assert ours['players'][1]['gold'] == 4321 and [plan for plan in ours['settlement']['plans'] if plan['player'] == 1]
    world.resign(1)
    decided = sent(match, 0)['world']['players'][1]
    assert decided['stats']['units_trained'] == 17, "once the match is decided, the scores are everybody's"


def test_the_id_counter_says_nothing_beyond_what_was_sent() -> None:
    match = fogged_match()
    snapshot = sent(match, 0)['world']
    sent_ids = [e['id'] for key in ('units', 'buildings', 'projectiles') for e in snapshot[key]]
    assert snapshot['next_id'] == max(sent_ids) + 1 < match.world._next_id  # the true counter, which must not be told


def test_an_order_may_name_what_the_seat_was_shown_and_anything_else_is_no_target() -> None:
    """The authority took any id.  An attack on the rival's hall, never seen, walked a footman across the map to
    it, and the refusals told the ids that stand from those that do not: a client that tried them all counted the
    rival's army.  What a seat was not shown is now what an id nobody has is."""
    match = fogged_match()
    world = match.world
    in_front_of_seat_0(match)  # a rival barracks and footman in sight, so some rival ids are fair targets
    footman = world.spawn_unit(0, UnitType.FOOTMAN, world.player_units(0)[0].pos)
    world.update_vision()
    shown = {entity['id'] for key in ('units', 'buildings') for entity in sent(match, 0)['world'][key]}
    assert world.player_buildings(1, BuildingType.TOWN_HALL)[0].id not in shown
    for target in [*world.units, *world.buildings, 99999]:
        for action, args, kwargs in (('attack', [[footman.id], target], {}),
                                     ('smart', [[footman.id], list(footman.pos)], {'target_id': target})):
            told = answer(match, 0, action, args, **kwargs)
            assert (told == 'No such target') == (target not in shown), f"{action} on {target}: {told}"


def test_a_right_click_finds_what_the_seat_knows_there_and_a_building_it_saw_stays_a_target() -> None:
    """A right-click that names nothing is picked on the server, and it found a farm the rival raised where seat 0
    had looked once, out of its sight since: the footman went to strike it, and its orders named the farm."""
    match = fogged_match()
    world = match.world
    world.reveal_all(0)
    world.update_vision()  # seat 0 has seen the whole map once and now sees only what its forces see
    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    farm = world.place_building(1, BuildingType.FARM, site_near(world, 1, BuildingType.FARM, (rival_hall.x, rival_hall.y)))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, world.player_units(0)[0].pos)
    world.update_vision()
    assert world.is_explored(0, farm.pos) and not world.any_visible(0, farm.rect)

    def orders() -> list[str]:
        return [order['kind'] for order in {u['id']: u for u in sent(match, 0)['world']['units']}[footman.id]['orders']]

    assert answer(match, 0, 'smart', [[footman.id], list(farm.center)]) == 'accepted' and orders() == ['Move']
    assert answer(match, 0, 'attack', [[footman.id], farm.id]) == 'No such target'
    assert answer(match, 0, 'attack', [[footman.id], rival_hall.id]) == 'accepted' and orders() == ['Attack'], \
        "a hall seat 0 has seen is a target out of its sight"


def test_a_site_on_ground_the_seat_never_explored_is_unexplored_whatever_stands_there() -> None:
    """The placement rules looked at the ground before they asked whether the seat had ever seen it, and the refusal
    went back to the seat: "Something is in the way" traced the rival's hall under the fog, and "Needs open ground"
    told its trees from the ground they were felled on."""
    match = fogged_match()
    world = match.world
    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    x0, y0 = rival_hall.pos
    sites = [(x, y) for y in range(y0 - 2, y0 + rival_hall.size + 1) for x in range(x0 - 2, x0 + rival_hall.size + 1)]
    sites += [(x, y) for y in range(world.height - 1) for x in range(world.width - 1)
              if world.terrain[y][x] is Terrain.TREES and not world.is_explored(0, (x, y))][:8]
    assert not any(world.is_explored(0, site) for site in sites)
    peasant = next(unit for unit in world.player_units(0) if unit.is_worker)
    told = {answer(match, 0, 'plan_building', [0, 'farm', list(site)]) for site in sites}
    told |= {answer(match, 0, 'build', [peasant.id, 'farm', list(site)], plan_if_short=True) for site in sites}
    assert told == {'Unexplored'}


def test_ground_and_mines_out_of_sight_are_as_the_seat_last_saw_them_and_unseen_ones_as_the_map_began() -> None:
    match = fogged_match()
    world = match.world

    def tree_out_of_sight(seat: int) -> tuple[int, int]:
        return next((x, y) for y in range(world.height) for x in range(world.width)
                    if world.terrain[y][x] is Terrain.TREES and not world.is_visible(seat, (x, y)))

    never_seen = tree_out_of_sight(0)
    assert not world.is_explored(0, never_seen)
    world.terrain[never_seen[1]][never_seen[0]] = Terrain.GRASS  # felled where seat 0 has never looked
    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    rival_mine = min(world.mines(), key=lambda mine: dist(mine.center, rival_hall.center))
    assert not any(world.is_explored(0, tile) for tile in rival_mine.tiles())
    snapshot = sent(match, 0)['world']
    assert snapshot['terrain'][never_seen[1]][never_seen[0]] == 't'
    assert rival_mine.id not in {b['id'] for b in snapshot['buildings']}, "a mine seat 0 never saw travels to it"

    world.reveal_all(0)
    world.update_vision()  # seat 0 has seen the whole map once and now sees only what its forces see
    remembered = tree_out_of_sight(0)
    world.terrain[remembered[1]][remembered[0]] = Terrain.GRASS
    gold = rival_mine.gold
    rival_mine.gold -= 900
    snapshot = sent(match, 0)['world']
    assert snapshot['terrain'][remembered[1]][remembered[0]] == 't', "a tree felled out of sight is news to seat 0"
    assert {b['id']: b for b in snapshot['buildings']}[rival_mine.id]['gold'] == gold


def news(match: WarbandMatch, seat: int) -> list[tuple[str, int | None]]:
    return [(fields['kind'], fields.get('entity')) for _index, fields in sent(match, seat)['events']]


def test_news_travels_to_who_saw_it_to_its_owner_and_the_public_to_everyone() -> None:
    match = fogged_match()
    world = match.world
    camp, footman = in_front_of_seat_0(match)
    home_unit = next(u for u in world.player_units(1) if not world.is_visible(0, u.tile))
    home_unit.hp = 0  # dies at home, in seat 0's fog
    footman.hp = 0  # dies in front of seat 0's hall
    match.step()
    assert ('death', footman.id) in news(match, 0) and ('death', footman.id) in news(match, 1)
    assert ('death', home_unit.id) not in news(match, 0) and ('death', home_unit.id) in news(match, 1)

    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    world.players[1].gold = 1000
    match.apply(1, {'action': 'train', 'args': [rival_hall.id, 'peasant'], 'kwargs': {}})
    for _ in range(600):
        match.step()
        if any(kind == 'trained' for kind, _entity in news(match, 1)):
            break
    assert any(kind == 'trained' for kind, _entity in news(match, 1)), "the peasant never came out"
    assert not any(kind == 'trained' for kind, _entity in news(match, 0))

    # Seat 1 loses its hall at home, out of seat 0's sight, keeping a farm: the rules expose what it has left
    # to everyone, which is public news; the hall's fall is not.  The barracks by seat 0's hall is seen to fall.
    world.place_building(1, BuildingType.FARM, site_near(world, 1, BuildingType.FARM, (rival_hall.x, rival_hall.y)))
    camp.hp = rival_hall.hp = 0
    for _ in range(8):  # the fall, then a fog recomputation, which is when the rules expose what is left
        match.step()
    assert any(kind == 'exposed' for kind, _entity in news(match, 0)) and ('destroyed', rival_hall.id) not in news(match, 0)
    assert ('destroyed', camp.id) in news(match, 0) and ('destroyed', rival_hall.id) in news(match, 1)


def test_the_checkpoint_keeps_who_saw_what_and_how_the_map_began() -> None:
    from warband.online.authority import ONLINE

    spec = ONLINE["warband-v2"]

    match = fogged_match()
    world = match.world
    home_unit = next(u for u in world.player_units(1) if not world.is_visible(0, u.tile))
    home_unit.hp = 0
    match.step()
    felled = next((x, y) for y in range(world.height) for x in range(world.width)
                  if world.terrain[y][x] is Terrain.TREES and not world.is_explored(0, (x, y)))
    world.terrain[felled[1]][felled[0]] = Terrain.GRASS
    restored = spec.restore(json.loads(json.dumps(spec.checkpoint(match))))
    for seat in (0, 1):
        assert sent(restored, seat) == sent(match, seat)
    assert not any(f.get('entity') == home_unit.id for _i, f in sent(restored, 0)['events'])


# -- The client: exploring, remembering and rejoining with what its seat is sent -------------------------------------


class RoomSeat:
    """A seat in an online room without the socket: it is sent its snapshot whenever the match has moved on."""

    online = True

    def __init__(self, match: WarbandMatch, player: int, room: str = "wb011") -> None:
        self.match, self.player, self.room = match, player, room
        self.ready, self.error, self.revision = True, "", 0
        self.state = match.snapshot(player)

    def poll(self) -> None:
        if self.match.world.tick != self.state['world']['tick']:
            self.state, self.revision = self.match.snapshot(self.player), self.revision + 1

    def submit(self, command: dict) -> None:
        self.match.apply(self.player, command)

    def close(self) -> None:
        pass


@pytest.fixture
def game(tmp_path):
    from warband.ui.style import build_theme

    g = Game("Warband WB-011", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def play(game: Game, match: WarbandMatch, ticks: int = 8) -> None:
    for _ in range(ticks):
        match.step()
        game.tick(1 / 60)


def test_a_client_sees_the_rivals_hall_when_it_looks_remembers_it_after_and_keeps_it_across_a_rejoin(game) -> None:
    from warband.ui.multiplayer import NetworkGameScene
    from warband.ui.title import TitleScene

    quiet = {'music': 0, 'sfx': 0, 'tutorial': False}
    match = fogged_match()
    world = match.world
    scene = NetworkGameScene(RoomSeat(match, 0), settings=quiet)
    game.push(scene)
    play(game, match)
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    assert hall.id not in scene.world.buildings and scene.view.building_sprite(hall.id) is None
    eyes = world.spawn_unit(0, UnitType.FLYING_MACHINE, tile_center((hall.x - 2, hall.y + 1)))
    play(game, match)
    assert hall.id in scene.world.buildings and scene.view.building_sprite(hall.id) is not None, "the flyer sees nothing"
    eyes.hp = 0
    play(game, match)
    assert hall.id not in scene.world.buildings, "the hall is still sent with nobody of seat 0 looking"
    assert scene.view.building_sprite(hall.id) is not None, "the client forgot the hall it saw"

    game.clear_and_push(TitleScene(settings=quiet))  # leave; later, Multiplayer → Rejoin last room
    game.tick(1 / 60)
    back = NetworkGameScene(RoomSeat(match, 0), settings=quiet)
    game.clear_and_push(back)
    game.tick(1 / 60)
    assert hall.id not in back.world.buildings and back.view.building_sprite(hall.id) is not None, "a rejoin forgot the hall"
    game.clear_and_push(TitleScene(settings=quiet))
    game.tick(1 / 60)
    elsewhere = NetworkGameScene(RoomSeat(match, 0, room="other"), settings=quiet)
    game.clear_and_push(elsewhere)
    game.tick(1 / 60)
    assert elsewhere.view.building_sprite(hall.id) is None, "another room's memory was taken for this one's"
