"""Warband orders cross a LAN socket on the host's clock; ownership stays in the game."""
import time

import pytest

from saga2d import CommandError, Game, MatchClient, MatchHost, MatchMenu


def converge(host, client, until):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        host.poll()
        client.poll()
        if until():
            return
        time.sleep(.001)
    raise AssertionError('match did not converge')


def test_warband_guest_orders_and_host_simulation_stay_in_sync():
    """Guest units move on the authoritative clock; forged ownership is rejected atomically."""
    from warband.multiplayer import WarbandMatch
    from warband.model import World
    match = WarbandMatch(seed=3)
    host = MatchHost('warband-v1', match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband-v1', host.address, token='test')
    try:
        converge(host, client, lambda: client.ready)
        guest = match.world.player_units(1)[0]
        original = guest.pos
        ours = match.world.player_units(0)[0]
        with pytest.raises(CommandError):
            match.apply(1, {'action': 'move', 'args': [[guest.id, ours.id], [15., 15.]], 'kwargs': {}})
        assert not guest.orders
        client.submit({'action': 'move', 'args': [[guest.id], [original[0]-2, original[1]]], 'kwargs': {}})
        converge(host, client, lambda: bool(match.world.units[guest.id].orders))
        for _ in range(40):
            match.step()
        host.publish()
        converge(host, client, lambda: client.state['world']['tick'] == match.world.tick)
        assert match.world.units[guest.id].pos != original
        restored = World.from_dict(client.state['world'])
        assert all(p.human for p in restored.players)
        assert restored.to_dict() == match.world.to_dict()
    finally:
        client.close()
        host.close()


@pytest.mark.parametrize('audio_schema', ['current', 'basic', 'partial'])
def test_warband_fatal_impact_keeps_its_material_across_the_socket(tmp_path, audio_schema):
    """Guests hear fatal impacts, with explicit basic audio only for the old schema."""
    from saga2d import Game
    from warband.model import World
    from warband.multiplayer import WarbandMatch, NetworkGameScene
    from warband.rules import BuildingType, Terrain, UnitType
    from warband.style import build_theme

    match = WarbandMatch(3)
    match.world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    for player in match.world.players:
        player.human = True
    match.world.place_building(0, BuildingType.TOWN_HALL, (3, 3))
    match.world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    attacker = match.world.spawn_unit(1, UnitType.FOOTMAN, (10.5, 10.5))
    victim = match.world.place_building(0, BuildingType.TOWER, (11, 10), done=False)
    victim.hp = 1
    armor = match.world.armor_of(victim)
    match.world.update_vision()
    impact_fields = ('source_type', 'target_type', 'target_armor', 'target_complete')
    omitted_fields = {'current': (), 'basic': impact_fields, 'partial': ('target_type',)}[audio_schema]

    def snapshot(player):
        state = match.snapshot(player)
        for _, event in state['events']:
            for field in omitted_fields:
                del event[field]
        return state

    host = MatchHost('warband-v1', match.apply, snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband-v1', host.address, token='test')
    game = Game('network battle audio', backend='mock', theme=build_theme(), save_dir=tmp_path)
    try:
        converge(host, client, lambda: client.ready)
        scene = NetworkGameScene(client, settings={'tutorial': False})
        game.push(scene)
        scene.camera.center_on(11.5 * 32, 10.5 * 32)
        game.tick(1 / 30)
        scene.order('attack', [attacker.id], victim.id)
        converge(host, client, lambda: bool(match.world.units[attacker.id].orders))
        for _ in range(4):
            match.step()
            if match.world.entity(victim.id) is None:
                break
        assert match.world.entity(victim.id) is None
        host.publish()
        converge(host, client, lambda: client.revision == host.revision)
        hit = next(event for _, event in client.state['events']
                   if event['kind'] == 'hit' and event['other'] == victim.id)
        if audio_schema == 'current':
            assert {key: hit[key] for key in impact_fields} == {
                'source_type': 'footman', 'target_type': 'tower', 'target_armor': armor, 'target_complete': False,
            }
            assert armor > 0
        elif audio_schema == 'basic':
            assert not set(impact_fields).intersection(hit)
        else:
            with pytest.raises(ValueError, match='incomplete battle audio metadata'):
                game.tick(1 / 30)
            assert 'impact' not in scene.recent_sounds
            return
        game.tick(1 / 30)
        assert scene.world.entity(victim.id) is None
        assert ('sword_wood' if audio_schema == 'current' else 'impact') in scene.recent_sounds
        assert 'sword_stone' not in scene.recent_sounds
        if audio_schema == 'basic':
            assert scene.status == 'Server uses basic battle audio; update the server for weapon and material sounds.'
            # Later impacts must leave newer player feedback visible.
            next_victim = match.world.place_building(0, BuildingType.TOWER, (11, 10), done=False)
            next_victim.hp = 1
            scene.say('Holding the line.')
            scene.order('attack', [attacker.id], next_victim.id)
            converge(host, client, lambda: bool(match.world.units[attacker.id].orders)
                     and match.world.units[attacker.id].orders[0].target == next_victim.id)
            for _ in range(30):
                match.step()
                if match.world.entity(next_victim.id) is None:
                    break
            assert match.world.entity(next_victim.id) is None
            host.publish()
            converge(host, client, lambda: client.revision == host.revision)
            game.tick(1 / 30)
            assert scene.world.entity(next_victim.id) is None
            assert scene.status == 'Holding the line.'
    finally:
        game.close()
        client.close()
        host.close()


def test_warband_invalid_cancel_index_is_rejected_without_changing_the_queue():
    """Malformed remote orders are ordinary rejections and cannot crash the host loop."""
    from warband.multiplayer import WarbandMatch
    from warband.rules import UnitType, BuildingType
    match = WarbandMatch()
    hall = match.world.player_buildings(1, BuildingType.TOWN_HALL)[0]
    match.world.train(hall.id, UnitType.PEASANT)
    before = match.world.to_dict()
    with pytest.raises(CommandError):
        match.apply(1, {'action': 'cancel_train', 'args': [], 'kwargs': {'building_id': hall.id, 'index': 999}})
    assert match.world.to_dict() == before


def test_warband_selection_facts_are_drawn_above_their_background(tmp_path):
    """Native review found the inherited HUD panel covering its immediate text."""
    from saga2d import Game
    from warband.scene import new_game
    from warband.style import build_theme
    game = Game('selection', backend='mock', theme=build_theme(), save_dir=tmp_path)
    try:
        scene = new_game(3)
        game.push(scene)
        scene.select([scene.world.player_units(scene.human)[0].id])
        game.tick(.03)
        game.tick(.03)
        text = next(t for t in game.backend.texts if t['text'] == 'Peasant')
        covers = [r for r in game.backend.polygons if r['space'] == 'screen' and r['color'][3] > 128
                  and min(x for x,y in r['points']) <= text['x'] < max(x for x,y in r['points'])
                  and min(y for x,y in r['points']) <= text['y'] < max(y for x,y in r['points'])]
        assert covers
        assert all(r['order'] <= text['order'] for r in covers)
    finally:
        game.close()


def test_warband_host_clock_runs_under_its_menu_and_pauses_on_disconnect(tmp_path):
    """The actual host scene owns time independently of the local pause overlay."""
    from saga2d import Game
    from warband.multiplayer import WarbandMatch, NetworkGameScene
    from warband.style import build_theme
    match = WarbandMatch()
    host = MatchHost('warband', match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband', host.address, token='test')
    game = Game('host clock', backend='mock', theme=build_theme(), save_dir=tmp_path)
    try:
        converge(host, client, lambda: client.ready)
        scene = NetworkGameScene(host, match)
        game.push(scene)
        game.backend.inject_key('f10')
        game.tick(.03)
        assert game.scene is not scene
        before = match.world.tick
        deadline = time.monotonic() + 3
        while match.world.tick < before + 4 and time.monotonic() < deadline:
            time.sleep(.01)
            game.tick(.03)
            client.poll()
        assert match.world.tick >= before + 4
        assert scene.world.tick >= before + 2
        client.close()
        game.tick(.03)
        assert not host.ready
        stopped = match.world.tick
        time.sleep(.12)
        game.tick(.03)
        assert match.world.tick == stopped
    finally:
        game.close()
        client.close()
        host.close()



def test_guest_controls_reach_host_and_accepted_state_returns_to_the_scene(tmp_path):
    """The real match scene submits orders without mutating the guest world ahead of the host."""
    from warband.multiplayer import WarbandMatch, NetworkGameScene
    from warband.style import build_theme
    match = WarbandMatch(3)
    host = MatchHost('warband', match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband', host.address, token='test')
    game = Game('network test', backend='mock', theme=build_theme(), save_dir=tmp_path)
    try:
        converge(host, client, lambda: client.ready)
        scene = NetworkGameScene(client)
        game.push(scene)
        game.tick(1/30)
        unit = scene.world.player_units(1)[0]
        scene.select([unit.id])
        scene.command_move((unit.x-2, unit.y))
        assert not match.world.units[unit.id].orders
        converge(host, client, lambda: bool(match.world.units[unit.id].orders))
        converge(host, client, lambda: client.revision == host.revision)
        game.tick(1/30)
        assert scene.world.units[unit.id].orders
    finally:
        game.close()
        client.close()
        host.close()


def test_title_opens_a_usable_host_join_form(tmp_path):
    """Multiplayer is reachable from the title and address entry uses ordinary input."""
    from warband.style import build_theme
    from warband.title import TitleScene
    game = Game('title', backend='mock', theme=build_theme(), save_dir=tmp_path)
    try:
        game.push(TitleScene())
        game.backend.inject_key('m')
        game.tick(1/30)
        assert isinstance(game.scene, MatchMenu)
        assert game.scene.mode == 'online'
        lan = next(button for button in game.scene.ui.walk() if getattr(button, 'text', None) == 'LAN')
        x, y, w, h = lan.bounds
        game.backend.inject_click(x + w / 2, y + h / 2)
        game.tick(1/30)
        assert game.scene.mode == 'lan'
        for key in ['1', '9', '2', 'period', '1', '6', '8', 'period', '1', 'period', '9']:
            game.backend.inject_key(key)
            game.tick(1/30)
        assert game.scene.fields[0] == '192.168.1.9'
        game.backend.inject_key('tab')
        game.tick(1/30)
        game.backend.inject_key('8')
        game.tick(1/30)
        assert game.scene.fields[1] == '8'
    finally:
        game.close()
