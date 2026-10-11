"""Online menus retain the live room and never switch a player into a solo game."""
import time
from types import SimpleNamespace

import pytest

from saga2d import Button, Game, MatchMenu
from saga2d.online import OnlineClient
from saga2d.testing.online import server_fixture

server_url = server_fixture('warband.online.authority:ONLINE')
from warband.ui.multiplayer import (MatchSetupMenu, NetworkGameScene, NetworkResultScene, WarbandLobby,
                                    identity_notice, online_identity, refresh_online_identity, stored_online_profile)
from warband.sim.rules import Layout
from warband.ui.scene import SettingsScene
from warband.ui.style import build_theme
from warband.ui.title import LibraryScene, TitleScene


def wait_for(game, partner, predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        game.tick(1 / 30)
        partner.poll()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError(f'Online menu did not converge: {type(game.scene).__name__}')


def press(game, key):
    game.backend.inject_key(key)
    game.tick(1 / 30)


def buttons(game):
    return [button.text for button in game.scene.ui.walk() if isinstance(button, Button)]


@pytest.fixture
def online_game(server_url, tmp_path, monkeypatch):
    monkeypatch.setenv('SAGA2D_SERVER_URL', server_url)
    partner = OnlineClient('warband-v2', endpoint=server_url, options={'seed': 3, 'width': 48, 'height': 40})
    game = Game('online menu', backend='mock', resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        game.push(TitleScene())
        wait_for(game, partner, lambda: bool(partner.room))
        press(game, 'm')
        assert isinstance(game.scene, MatchMenu)
        for character in partner.room:
            press(game, character)
        press(game, 'return')
        wait_for(game, partner, lambda: isinstance(game.scene, NetworkGameScene) and partner.ready)
        yield game, partner
    finally:
        game.close()
        partner.close()


@pytest.mark.slow
def test_online_menu_keeps_play_live_and_leaving_preserves_rejoin(online_game):
    """Real room state keeps advancing under menus; leaving returns to a recoverable seat.

    A real room's match runs under the menu for most of a second: the slow tier."""
    game, partner = online_game
    match = game.scene
    room = match.session.room
    press(game, 'f10')
    menu = game.scene
    assert buttons(game) == ['Return to match', 'Settings', 'How to play', 'Resign', 'Leave match', 'Quit']
    text = '\n'.join(item['text'] for item in game.backend.texts)
    assert 'Match menu' in text and 'Paused' not in text
    assert 'The match continues while this menu is open.' in text
    assert 'Multiplayer → Rejoin last room' in text
    before = match.world.tick
    wait_for(game, partner, lambda: match.world.tick >= before + 4)
    for key in ('n', 'f5', 'f9'):
        press(game, key)
        assert game.scene is menu and match.session.ready
    press(game, 's')
    assert isinstance(game.scene, SettingsScene)
    before = match.world.tick
    wait_for(game, partner, lambda: match.world.tick >= before + 4)
    press(game, 'escape')
    assert game.scene is menu
    press(game, 'escape')
    assert game.scene is match and match.session.ready
    press(game, 'f10')
    press(game, 't')
    assert isinstance(game.scene, TitleScene) and match.session.closed
    wait_for(game, partner, lambda: not partner.ready)
    press(game, 'm')
    rejoin = next(button for button in game.scene.ui.walk()
                  if isinstance(button, Button) and str(button.text).startswith('Rejoin last room'))
    x, y, width, height = rejoin.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    wait_for(game, partner, lambda: isinstance(game.scene, NetworkGameScene) and partner.ready)
    assert game.scene.session.room == room and game.scene.human == match.human


@pytest.mark.parametrize('winner', [0, 1])
def test_network_result_has_no_solo_rematch_and_escape_leaves(tmp_path, winner):
    """An authoritative victory or defeat ends at the title, never a new local match."""
    from saga2d import MatchClient, MatchHost
    from tests.warband.test_multiplayer import converge
    from warband.sim.model import World
    from warband.online.authority import WarbandMatch
    from warband.sim.rules import Terrain, UnitType

    match = WarbandMatch(3)
    match.world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2)
    for player in match.world.players:
        player.human = True
    attacker = match.world.spawn_unit(winner, UnitType.FOOTMAN, (10.5, 10.5))
    victim = match.world.spawn_unit(1 - winner, UnitType.PEASANT, (11, 10.5))
    victim.hp = 1
    match.world.update_vision()
    host = MatchHost('warband-v2', match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    client = MatchClient('warband-v2', host.address, token='test')
    game = Game('network result', backend='mock', resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / 'saves')
    try:
        converge(host, client, lambda: client.ready)
        scene = NetworkGameScene(client)
        game.push(scene)
        game.tick(1 / 30)
        command = {'action': 'attack', 'args': [[attacker.id], victim.id]}
        (host if winner == 0 else client).submit(command)
        converge(host, client, lambda: bool(match.world.units[attacker.id].orders))
        for _ in range(40):
            match.step()
            if match.world.winner is not None:
                break
        assert match.world.winner == winner
        host.publish()
        converge(host, client, lambda: client.state['world']['winner'] == winner)
        game.tick(1 / 30)
        result = game.scene
        assert result is not scene
        assert buttons(game) == ['Back to title', 'Quit']
        text = '\n'.join(item['text'] for item in game.backend.texts)
        assert ('Victory!' if winner == 1 else 'Defeat') in text
        assert 'choose Multiplayer on the title screen' in text
        press(game, 'n')
        assert game.scene is result and not client.closed
        press(game, 'escape')
        assert isinstance(game.scene, TitleScene) and client.closed
    finally:
        game.close()
        client.close()
        host.close()


# -- Focused title, setup, lobby and identity ---------------------------------------

from warband.ui.scene import CodexScene, HelpScene
from warband.ui.score_scene import HighScoreScene


def title_game(tmp_path, **kwargs):
    game = Game("Warband title", backend="mock", resolution=(1280, 800), theme=build_theme(),
                save_dir=tmp_path / "saves")
    game.push(TitleScene(**kwargs))
    game.tick(0.1)
    return game


def click(game, label):
    """Click the top scene's button reading *label*."""
    button = next(b for b in game.scene.ui.walk() if isinstance(b, Button) and b.text == label)
    x, y, width, height = button.bounds
    game.backend.inject_click(x + width / 2, y + height / 2)
    game.backend.inject_release(x + width / 2, y + height / 2)
    game.tick(0.1)


def texts(game):
    return "\n".join(item["text"] for item in game.backend.texts)


def test_multiplayer_is_principal_and_skirmish_and_library_are_secondary(tmp_path):
    """Enter and M open multiplayer, N keeps the skirmish, Y opens the Library with a Back."""
    from warband.ui.title import NewGameScene

    game = title_game(tmp_path)
    try:
        assert buttons(game) == ["Multiplayer", "Skirmish", "Campaign", "Library & help", "Quit"]
        press(game, "return")
        assert isinstance(game.scene, MatchSetupMenu)
        press(game, "escape")
        assert isinstance(game.scene, TitleScene)
        press(game, "m")
        assert isinstance(game.scene, MatchSetupMenu)
        press(game, "escape")
        press(game, "n")
        assert isinstance(game.scene, NewGameScene)
        game.pop()
        press(game, "y")
        assert isinstance(game.scene, LibraryScene)
        assert "Back" in buttons(game)
        press(game, "escape")
        assert isinstance(game.scene, TitleScene)
    finally:
        game.close()


def test_multiplayer_opens_on_whatever_offline_size_was_chosen(tmp_path):
    """Sixteen skirmish seats never prevent opening multiplayer from the keyboard."""
    game = title_game(tmp_path, players=16)
    try:
        press(game, "m")
        assert isinstance(game.scene, MatchSetupMenu)
        assert game.scene.create_options()["players"] == 2
    finally:
        game.close()


def test_moved_title_shortcuts_still_answer(tmp_path):
    """Continue, load, profile, scores and help answer from the title without their buttons."""
    game = title_game(tmp_path)
    try:
        press(game, "h")
        assert isinstance(game.scene, HelpScene)
        game.pop()
        game.tick(0.1)
        press(game, "p")
        from warband.ui.profile_scene import ProfileScene
        assert isinstance(game.scene, ProfileScene)
        game.pop()
        game.tick(0.1)
        press(game, "b")
        assert isinstance(game.scene, HighScoreScene)
    finally:
        game.close()


def test_first_screen_hides_the_offline_record(tmp_path):
    """No skirmish rating or history on the first screen; the Library holds them."""
    game = title_game(tmp_path)
    try:
        assert "Skirmish rating" not in texts(game)
        assert "No online matches yet" in texts(game)
        assert "Profile & replays" not in buttons(game)
        press(game, "y")
        assert "Skirmish rating" in texts(game)  # the labelled offline rating lives here
        assert "No rated matches yet" in texts(game)
        assert "Profile & replays" in buttons(game)
    finally:
        game.close()


def open_setup(tmp_path):
    game = title_game(tmp_path)
    press(game, "m")
    assert isinstance(game.scene, MatchSetupMenu)
    return game


def test_setup_defaults_make_a_valid_room_and_keep_the_wire_contract(tmp_path):
    """Rated duel defaults pass the authority with the exact option keys the server speaks."""
    from warband.online.authority import _create

    game = open_setup(tmp_path)
    try:
        menu = game.scene
        assert (menu.rated, menu.seats, menu.size) == (True, 2, "Medium")
        options = menu.create_options()
        assert set(options) == {"seed", "width", "height", "theme", "players", "races", "layout", "magic"}
        assert _create(options).world.seats == 2
        assert menu.create_match().world.seats == 2
    finally:
        game.close()


@pytest.mark.parametrize("seats", [2, 3, 4])
def test_setup_seats_sizes_and_layouts_stay_valid_rooms(tmp_path, seats):
    """Every seat count offers only sizes and layouts the authority accepts."""
    from warband.online.authority import ONLINE_SIZE, _create
    from warband.sim import mapgen

    game = open_setup(tmp_path)
    try:
        menu = game.scene
        menu.set_seats(seats)
        menu.set_size("Small" if "Small" in menu.online_sizes() else menu.online_sizes()[0])
        sizes = menu.online_sizes()
        assert sizes and all(mapgen.dimensions(name, seats) <= ONLINE_SIZE for name in (sizes[0], sizes[-1]))
        assert _create(menu.create_options()).world.seats == seats
        offered = menu.room_layouts()
        assert set(offered) <= set(Layout)
        if offered:
            menu.set_layout(offered[0])
            assert _create(menu.create_options()) is not None
        invalid = [layout for layout in Layout if layout not in offered]
        if invalid:
            before = menu.layout
            menu.set_layout(invalid[0])
            assert menu.layout is before, "unoffered layouts are refused, not silently reset"
    finally:
        game.close()


def test_setup_faction_is_shared_by_creating_and_joining(tmp_path):
    """Your faction leads the created room and waits as player options; nothing sends it yet."""
    from warband.sim.rules import Race

    game = open_setup(tmp_path)
    try:
        menu = game.scene
        menu.set_faction(Race.ELF)
        assert menu.create_options()["races"][0] == "elf"
        assert menu.create_match().world.players[0].race is Race.ELF
        assert menu.player_options() == {"race": "elf"}
    finally:
        game.close()


@pytest.mark.parametrize("clipboard, expected", [
    ("ab12", "AB12"),
    ("https://games.tachyon-ai.eu/join/warband-v2/cd34", "CD34"),
    ("https://games.tachyon-ai.eu/join/warband-v2/ef56/", "EF56"),
    ("games.tachyon-ai.eu/join/warband-v2/gh78?x=1", None),  # query forms are refused
    ("https://games.tachyon-ai.eu/join/tribes-v1/ab12", None),  # another game's path
    ("https://games.tachyon-ai.eu/join/warband-v2/ab12?resume_token=secret", None),  # private seat
    ("0123456789abcdef", None),  # a long token is never a room code
    ("", None),
])
def test_paste_invite_takes_codes_and_links_but_never_seats(tmp_path, clipboard, expected):
    """Paste invite accepts a bare code or the exact public invite path, nothing private."""
    game = open_setup(tmp_path)
    try:
        game.backend.set_clipboard_text(clipboard)
        click(game, "Paste invite")
        assert game.scene.fields[2] == (expected or "")
        assert ("Paste invite" in game.scene.message) is (expected is None)
    finally:
        game.close()


def test_join_without_a_code_says_so_and_stays(tmp_path):
    """Enter on an empty code field refuses with a message instead of opening a lobby."""
    game = open_setup(tmp_path)
    try:
        press(game, "return")
        assert isinstance(game.scene, MatchSetupMenu)
        assert "room code" in game.scene.message
    finally:
        game.close()


def test_online_identity_is_server_issued_and_locally_named(tmp_path):
    """Identity carries an empty token until a room issues one, named by the local profile."""
    from warband.records.profile import Profile

    game = title_game(tmp_path)
    try:
        identity = online_identity(game, "wss://test.example/play")
        assert set(identity) == {"player_token", "player_name"}
        assert identity["player_token"] == ""
        assert identity["player_name"] == Profile.load(game.data_dir).name
        assert stored_online_profile(game, "wss://test.example/play") is None
    finally:
        game.close()


def test_match_reports_refresh_the_cached_profile_once(tmp_path, monkeypatch):
    """A session's own token, id, profile and result persist per endpoint, on change only."""
    from saga2d.settings import Settings

    saves = []
    original_save = Settings.save

    def counting_save(self):
        saves.append(self.path)
        return original_save(self)

    monkeypatch.setattr(Settings, "save", counting_save)
    game = title_game(tmp_path)
    try:
        endpoint = "wss://test.example/play"
        profile = {"player_id": "p1", "name": "Al", "rating": 1500, "games": 3, "wins": 2, "losses": 1}
        result = {"match_id": "m1", "winner": 0,
                  "ratings": [{"player_id": "p1", "name": "Al", "before": 1484, "after": 1500,
                               "delta": 16, "games": 3, "wins": 2, "losses": 1}]}
        session = SimpleNamespace(online=True, endpoint=endpoint, player_token="tok123", player_id="p1",
                                  rating=profile, result=result)
        refresh_online_identity(game, session)
        assert stored_online_profile(game, endpoint) == profile
        assert online_identity(game, endpoint)["player_token"] == "tok123"
        from warband.records.profile import Profile as LocalProfile
        assert online_identity(game, endpoint)["player_name"] == LocalProfile.load(game.data_dir).name
        before = list(saves)
        refresh_online_identity(game, session)
        assert saves == before, "unchanged values write nothing"
    finally:
        game.close()


def test_damaged_identity_record_surfaces_and_still_opens(tmp_path):
    """A corrupt private record is reported once, and the setup still opens on a fresh one."""
    game = title_game(tmp_path)
    try:
        (tmp_path / "online-identity.json").write_text("{broken", encoding="utf-8")
        assert "damaged" in identity_notice(game)
        press(game, "m")
        assert isinstance(game.scene, MatchSetupMenu)
        assert "damaged" in texts(game)
    finally:
        game.close()


def fake_session(**kwargs):
    """An online waiting session: counts, room and lifecycle hooks, no network."""
    session = SimpleNamespace(online=True, incompatible=False, game_id="warband-v2",
                              endpoint="wss://test.example/play", room="AB12", seats=3, present=1,
                              retention=900, state={"seed": 3}, error="", closed=False, ready=False,
                              revision=0, resume_token="saved-seat", player_token="", player_id="",
                              rating=None, result=None, rated=False, rated_grace=None, match_id="",
                              players=None)
    session.poll = lambda: None
    session.close = lambda: setattr(session, "closed", True)
    for key, value in kwargs.items():
        setattr(session, key, value)
    return session


def test_rated_grace_clause_uses_the_server_seconds_or_names_none():
    """The departure grace comes from the welcome, never a hard-coded number."""
    from warband.ui.multiplayer import rated_grace_clause

    assert "over 60 s" in rated_grace_clause(SimpleNamespace(online=True, rated_grace=60))
    assert "over 45 s" in rated_grace_clause(SimpleNamespace(online=True, rated_grace=45))
    assert "60" not in rated_grace_clause(SimpleNamespace(online=True, rated_grace=None))


def test_lobby_lists_seats_and_cancel_returns_and_closes(tmp_path):
    """The roster names seats in order with open seats waiting; Cancel returns to setup closed."""
    game = open_setup(tmp_path)
    try:
        session = fake_session(players=[
            {"seat": 0, "player_id": "p1", "name": "Al", "rating": 1500, "games": 4, "connected": True},
            None,
            {"seat": 2, "player_id": "", "name": "", "rating": None, "games": 0, "connected": False}])
        game.push(WarbandLobby(session, lambda connection: None, title="Warband multiplayer"))
        game.tick(0.1)
        body = texts(game)
        assert "Room code: AB12" in body
        assert "Seat 1: Al · 1500 · connected" in body
        assert "Seat 2: open — waiting for a player" in body
        assert "Seat 3: Guest · waiting" in body
        click(game, "Copy room code")
        assert game.backend.get_clipboard_text() == "AB12"
        invite = game.scene.invite_link()
        assert "AB12" in invite and "tok" not in invite and "resume" not in invite
        click(game, "Cancel")
        assert isinstance(game.scene, MatchSetupMenu)
        assert session.closed
    finally:
        game.close()


def test_lobby_falls_back_to_honest_counts_without_a_roster(tmp_path):
    """Count-only sessions report present of required and invent no opponents."""
    game = open_setup(tmp_path)
    try:
        game.push(WarbandLobby(fake_session(), lambda connection: None))
        game.tick(0.1)
        body = texts(game)
        assert "1 of 3 seats connected" in body
        assert "Seat 1" not in body
    finally:
        game.close()


def test_lobby_reports_errors_and_update_required(tmp_path):
    """Cancelled rooms and outdated clients say so plainly, with a way out."""
    game = open_setup(tmp_path)
    try:
        game.push(WarbandLobby(fake_session(closed=True, error="Room not found. Check the code."),
                               lambda connection: None))
        game.tick(0.1)
        assert "Could not connect" in texts(game) and "Room not found" in texts(game)
        game.pop()
        game.tick(0.1)
        game.push(WarbandLobby(fake_session(incompatible=True, closed=True), lambda connection: None))
        game.tick(0.1)
        assert "Update required" in texts(game)
        assert "Open download page" in buttons(game)
    finally:
        game.close()


def result_game(tmp_path, session):
    """A real match scene carrying a metadata session, with its result overlay open."""
    from warband.ui.scene import DEFAULT_SETTINGS, new_game

    game = Game("Warband result", backend="mock", resolution=(1280, 800), theme=build_theme(),
                save_dir=tmp_path / "saves")
    scene = new_game(3, settings=dict(DEFAULT_SETTINGS, tutorial=False, music=0, sfx=0))
    scene.session = session
    game.push(scene)
    game.tick(0.1)
    game.push(NetworkResultScene(scene, False))
    game.tick(0.1)
    return game


def test_rated_receipt_arrives_on_the_open_overlay(tmp_path):
    """The open result screen waits for the authoritative receipt, then shows before/after/delta.

    Engine Elo values are floats: whole ones read plain, fractional free-for-all shares
    read to one decimal — an integer format would crash the render."""
    from warband.ui.multiplayer import format_rating

    assert format_rating(1500) == "1500"
    assert format_rating(1500.0) == "1500"
    assert format_rating(16.0, signed=True) == "+16"
    assert format_rating(10.666, signed=True) == "+10.7"
    assert format_rating(-3.5, signed=True) == "-3.5"
    session = SimpleNamespace(online=True, rated=True, result=None, player_id="p1")
    game = result_game(tmp_path, session)
    try:
        assert "Waiting for the rating result" in texts(game)
        session.result = {"match_id": "m1", "winner": 0,
                          "ratings": [{"player_id": "p1", "name": "Al", "before": 1484.0, "after": 1500.0,
                                       "delta": 16.0, "games": 4, "wins": 3, "losses": 1}]}
        game.tick(0.1)
        assert "Rated: 1484 → 1500 (+16) over 4 games." in texts(game)
        session.result = {"match_id": "m2", "winner": 0,
                          "ratings": [{"player_id": "p1", "name": "Al", "before": 1500.0, "after": 1510.666,
                                       "delta": 10.666, "games": 5, "wins": 4, "losses": 1}]}
        game.tick(0.1)
        assert "Rated: 1500 → 1510.7 (+10.7) over 5 games." in texts(game)
    finally:
        game.close()


def test_casual_result_changes_no_rating(tmp_path):
    """A casual room's open result screen says plainly that nothing changes."""
    session = SimpleNamespace(online=True, rated=False, result=None, player_id="p1")
    game = result_game(tmp_path, session)
    try:
        assert "A casual room: no rating changes." in texts(game)
    finally:
        game.close()


def test_lan_result_changes_no_rating(tmp_path):
    """A LAN room's open result screen says plainly that nothing changes."""
    session = SimpleNamespace(online=False)
    game = result_game(tmp_path, session)
    try:
        assert "A LAN room: no rating changes." in texts(game)
    finally:
        game.close()


def test_defeat_names_the_server_name_where_the_roster_knows_it(tmp_path):
    """Online defeat prefers the victor's persistent server name; LAN keeps the world label."""
    from warband.ui.scene import DEFAULT_SETTINGS, new_game

    def decided_game(tmp_path, session, winner):
        game = Game("Warband defeat", backend="mock", resolution=(1280, 800), theme=build_theme(),
                    save_dir=tmp_path / "saves")
        scene = new_game(3, settings=dict(DEFAULT_SETTINGS, tutorial=False, music=0, sfx=0))
        scene.session = session
        scene.world.winner = winner
        game.push(scene)
        game.tick(0.1)
        game.push(NetworkResultScene(scene, False))
        game.tick(0.1)
        return game

    online = SimpleNamespace(online=True, rated=False, result=None, player_id="p1",
                             players=[{"seat": 0, "player_id": "p1", "name": "Al",
                                       "rating": 1500, "games": 4, "connected": True},
                                      {"seat": 1, "player_id": "p2", "name": "Bo",
                                       "rating": 1480, "games": 9, "connected": True}])
    game = decided_game(tmp_path, online, 1)
    try:
        assert "Defeat — Bo prevails" in texts(game)
    finally:
        game.close()
    lan = SimpleNamespace(online=False)
    game = decided_game(tmp_path, lan, 1)
    try:
        world_name = game.scene.game_scene.world.players[1].name
        assert f"Defeat — {world_name} prevails" in texts(game)
    finally:
        game.close()
