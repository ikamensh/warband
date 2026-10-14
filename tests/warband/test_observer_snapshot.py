"""The authority's dedicated observer snapshot: the whole match as a watcher may see it.

Watching is a deliberate omniscient role, not a third seat. The observer sees the current map whole —
every faction's units, buildings and shots, the ground as it stands, every purse, research and score — but
never what would let the snapshot stand in for the authority: no random stream, no explored memory, no
settlement plans, no unit intentions, no camp damage ledger, and none of the seats' private chatter.
"""
import json

from warband.online.authority import NO_DICE, PRIVATE_EVENTS, WarbandMatch
from warband.sim.model import World, tile_center
from warband.sim.rules import BuildingType, UnitType, Upgrade
from warband.sim.worker_knowledge import WorkerKnowledge


def fogged_match() -> WarbandMatch:
    """A match two seconds in: each seat sees its own corner, nothing of the other's."""
    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    return match


def wire(snapshot: dict) -> dict:
    """What travels to an observer: the snapshot as JSON, the way the server writes it to the socket."""
    return json.loads(json.dumps(snapshot))


def site_near(world: World, player: int, building_type: BuildingType, around: tuple[int, int]) -> tuple[int, int]:
    """Open ground near *around* where *player*, who must have explored it, may build."""
    for reach in range(2, 12):
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                site = (around[0] + dx, around[1] + dy)
                if world.can_place(building_type, site, player) is None:
                    return site
    raise AssertionError(f"no room for a {building_type.value} near {around}")


def test_the_observer_sees_what_no_seat_may_know() -> None:
    """Rivals at home and neutral guards, absent from a seat's snapshot, all travel to the observer."""
    match = fogged_match()
    world = match.world
    hidden_rivals = [u.id for u in world.player_units(1) if not world.is_visible(0, u.tile)]
    assert hidden_rivals, "seed 3 must keep some of seat 1's force out of seat 0's sight"
    rival_hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    assert rival_hall.id not in {b['id'] for b in wire(match.snapshot(0))['world']['buildings']}
    guards = [guard for camp in world.camps for guard in camp.guards if guard in world.units]
    assert guards, "the map must hold neutral guards for the observer to see"
    assert [g for g in guards if world.units[g].player == world.neutral], "some guard must fight for the wilds"

    seen = wire(match.observer_snapshot())['world']
    units, buildings = {u['id']: u for u in seen['units']}, {b['id']: b for b in seen['buildings']}
    assert {u.id for u in world.units.values()} == set(units)
    assert {b.id for b in world.buildings.values()} == set(buildings)
    assert {s.id for s in world.projectiles.values()} == {s['id'] for s in seen['projectiles']}
    assert set(hidden_rivals) <= set(units) and rival_hall.id in buildings
    assert set(guards) <= set(units)
    assert {camp['lair'] for camp in seen['camps']} == {camp.lair for camp in world.camps}


def test_the_observer_snapshot_survives_the_wire_as_a_world() -> None:
    """The envelope matches a seat's, and its world loads through World.from_dict with purses and scores intact."""
    match = fogged_match()
    world = match.world
    rival = world.players[1]
    rival.gold, rival.lumber, rival.aether = 4321, 1234, 7
    rival.upgrades.add(Upgrade.BLADES_1)
    rival.stats["units_trained"] = 17
    snapshot = wire(match.observer_snapshot())
    assert set(snapshot) == {'seed', 'world', 'events'}
    assert snapshot['seed'] == match.seed == 3
    assert snapshot['world']['rng'] == json.loads(json.dumps(NO_DICE))
    seen = World.from_dict(snapshot['world'])
    assert ({u.id for u in seen.units.values()} == {u.id for u in world.units.values()}
            and {b.id for b in seen.buildings.values()} == {b.id for b in world.buildings.values()}
            and {s.id for s in seen.projectiles.values()} == {s.id for s in world.projectiles.values()})
    assert seen.terrain == world.terrain
    assert [(p.gold, p.lumber, p.aether) for p in seen.players] == [(p.gold, p.lumber, p.aether) for p in world.players]
    assert [set(p.upgrades) for p in seen.players] == [set(p.upgrades) for p in world.players]
    assert [dict(p.stats) for p in seen.players] == [dict(p.stats) for p in world.players]
    assert [p.human for p in seen.players] == [p.human for p in world.players]
    assert [p.race for p in seen.players] == [p.race for p in world.players]
    assert (seen.time, seen.tick) == (world.time, world.tick)
    assert seen.settlement.plans == [] and seen.settlement.next_id == 1


def test_the_observer_is_told_no_memory_plans_or_intentions() -> None:
    """Explored ground, worker memory, settlement plans and unit intentions stay with the authority."""
    match = fogged_match()
    world = match.world
    hall = world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    world.plan_building(1, BuildingType.FARM, site_near(world, 1, BuildingType.FARM, (hall.x, hall.y)))
    assert world.settlement.player_plans(1), "seat 1 must hold a plan for the observer to be denied"
    seen = wire(match.observer_snapshot())['world']
    width, height = world.width, world.height
    assert seen['explored'] == [bytes(width * height).hex()] * len(world.players)
    blank = WorkerKnowledge(width, height).to_dict()
    assert seen['worker_knowledge'] == [blank] * len(world.players)
    assert seen['settlement'] == {'next_id': 1, 'plans': []}
    for unit in seen['units']:
        told_no_intentions = {'orders': [], 'worker_orders': [], 'home': None, 'auto_work': False, 'commanded': None}
        for key, withheld in told_no_intentions.items():
            assert unit[key] == withheld, f"unit {unit['id']} tells its {key}"
        assert unit['constructing'] == world.units[unit['id']].constructing
    sent = [d['id'] for key in ('units', 'buildings', 'projectiles') for d in seen[key]]
    assert seen['next_id'] == max(sent) + 1
    for camp in seen['camps']:
        assert camp['credit'] == {} and camp['quiet_since'] == -1.0 and camp['struck'] == -1000.0
    assert not any(plan for plan in seen['settlement']['plans'])
    assert all(fields['kind'] not in PRIVATE_EVENTS for _, fields in wire(match.observer_snapshot())['events'])


def test_what_the_observer_is_sent_is_theirs_to_keep() -> None:
    """Mutating a received snapshot changes neither the authority nor the next snapshot."""
    from warband.online.authority import ONLINE

    match = fogged_match()
    before = wire(match.observer_snapshot())
    before_seats = [wire(match.snapshot(seat)) for seat in range(match.world.seats)]
    before_checkpoint = wire(ONLINE['warband-v2'].checkpoint(match))
    received = match.observer_snapshot()
    received['world']['units'][0]['x'] = -999.0
    received['world']['players'][0]['gold'] = -1
    received['world']['terrain'][0] = 'x' * match.world.width
    received['world']['settlement']['plans'].append({'id': 1, 'player': 0})
    received['events'].append([999999, {'kind': 'victory'}])
    assert wire(match.observer_snapshot()) == before
    assert [wire(match.snapshot(seat)) for seat in range(match.world.seats)] == before_seats
    assert wire(ONLINE['warband-v2'].checkpoint(match)) == before_checkpoint


def test_a_kept_snapshot_cannot_bleed_orders_into_the_next() -> None:
    """Appending to a returned unit's orders leaves later observer and seat snapshots clean."""
    match = fogged_match()
    received = match.observer_snapshot()
    received['world']['units'][0]['orders'].append({'kind': 'Move', 'probe': True})
    received['world']['units'][1]['worker_orders'].append({'probe': True})
    again = match.observer_snapshot()
    assert all(u['orders'] == [] and u['worker_orders'] == [] for u in again['world']['units'])
    for seat in range(match.world.seats):
        strangers = [u for u in match.snapshot(seat)['world']['units'] if u['id'] not in
                     {own.id for own in match.world.player_units(seat)}]
        assert all(u['orders'] == [] and u['worker_orders'] == [] for u in strangers)


def test_a_rivals_site_under_construction_survives_the_wire_with_its_builder_inside() -> None:
    """The observer's reloaded world keeps the unfinished site, and the hidden builder stays hidden."""
    match = fogged_match()
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    site = world.place_building(1, BuildingType.FARM, site_near(world, 0, BuildingType.FARM, (hall.x + hall.size + 3, hall.y)), done=False)
    builder = next(u for u in world.player_units(1) if u.is_worker and not u.hidden)
    world._start_building(builder, site)  # staged: a rival peasant raising it where seat 0 looks
    world.update_vision()
    assert world.is_visible(0, site.tiles()[0])
    assert builder.id not in {u['id'] for u in match.snapshot(0)['world']['units']}
    seen = World.from_dict(wire(match.observer_snapshot())['world'])
    assert site.id in seen.buildings and not seen.buildings[site.id].done
    assert seen.buildings[site.id].builder == builder.id
    assert builder.id in seen.units and seen.units[builder.id].hidden


def test_watching_leaves_the_match_unchanged() -> None:
    """Repeated snapshots agree, and a watched match steps exactly as one never watched."""
    from warband.online.authority import ONLINE

    match, twin = fogged_match(), WarbandMatch(seed=3)
    for _ in range(40):
        twin.step()
    spec = ONLINE['warband-v2']
    assert match.observer_snapshot() == match.observer_snapshot()
    assert wire(spec.checkpoint(match)) == wire(spec.checkpoint(twin))
    match.observer_snapshot()
    for _ in range(20):
        match.step()
        twin.step()
    assert wire(match.snapshot(0)) == wire(twin.snapshot(0))
    assert wire(match.snapshot(1)) == wire(twin.snapshot(1))
    assert wire(spec.checkpoint(match)) == wire(spec.checkpoint(twin))


def test_the_observer_hears_every_battle_but_no_private_chatter() -> None:
    """Blows no seat sees still ride the observer's news, while alarms and private affairs do not."""
    match = fogged_match()
    world = match.world
    middle = (world.width // 2, world.height // 2)
    assert not world.is_visible(0, middle) and not world.is_visible(1, middle)
    wilds = world.neutral
    striker = world.spawn_unit(wilds, UnitType.FOOTMAN, tile_center(middle))
    victim = world.spawn_unit(1, UnitType.FOOTMAN, tile_center((middle[0] + 1, middle[1])))
    victim.hp = 5  # staged: one exchange decides it, where seat 0 never looks
    world.attack([striker.id], victim.id)
    world.attack([victim.id], striker.id)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    world.train(hall.id, UnitType.PEASANT)
    hall.train_progress = world.unit_info(0, UnitType.PEASANT).build_time - 0.06  # staged: the recruit walks out next step
    hand = next(u for u in world.player_units(1) if u.is_worker and not u.hidden)
    world.build(hand.id, BuildingType.BARRACKS, next_site_for_refusal(world, hand))
    world.players[1].gold = world.players[1].lumber = 0  # staged: the site cannot be paid for on arrival
    for _ in range(60):
        match.step()
    kinds = [fields['kind'] for _, fields in match.events]
    assert 'hit' in kinds and 'death' in kinds, f"the staged battle must strike blows: {sorted(set(kinds))}"
    assert 'under_attack' in kinds and 'trained' in kinds and 'refused' in kinds

    watching = {fields['kind'] for _, fields in wire(match.observer_snapshot())['events']}
    assert {'hit', 'death'} <= watching, "combat anywhere on the map is the observer's news"
    assert not (set(PRIVATE_EVENTS) & watching), "a seat's own affairs are never the observer's"
    seats = [{fields['kind'] for _, fields in wire(match.snapshot(seat))['events']} for seat in range(2)]
    assert 'hit' not in seats[0] and 'death' not in seats[0], "seat 0 neither owns nor sees the far fight"
    assert 'under_attack' in seats[1] and 'under_attack' not in seats[0]
    assert 'trained' in seats[0] and 'refused' in seats[1], "each seat still hears its own affairs"


def next_site_for_refusal(world: World, hand) -> tuple[int, int]:
    """Open ground beside *hand* where its order is taken but arrival finds no building standing."""
    tile = hand.tile
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            site = (tile[0] + dx, tile[1] + dy)
            if world.can_place(BuildingType.BARRACKS, site, hand.player, builder=hand.id) is None:
                return site
    raise AssertionError(f"no room for a refused barracks near {tile}")
