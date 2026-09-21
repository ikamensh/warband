"""Matches of more than four seats, whole and at every size: the slow tier.

Each of these plays a whole match, or generates every map the New game screen offers, which is
minutes of simulation and dozens of maps — far past the fast tier's half a second.  What they hold
to is that a seat count past four is a match like any other: the map is fair, the brains play it,
the result names every warband and the screen never offers a pairing that cannot be generated.
"""

import pytest

from saga2d import Game
from warband.brains.ai import make_brain
from warband.sim import mapgen
from warband.sim.rules import BuildingType, Difficulty, Layout, UnitType
from warband.ui.scene import GameScene, new_game
from warband.ui.style import build_theme
from warband.ui.title import NewGameScene, TitleScene

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("seats", mapgen.SEAT_COUNTS)
def test_every_offered_pairing_generates_a_fair_map(seats: int) -> None:
    """Every size and layout New game offers for this many seats, generated and audited."""
    sizes = mapgen.sizes_for(seats)
    assert sizes, f"no size seats {seats}"
    for size in sizes:
        width, height = mapgen.dimensions(size, seats)
        assert mapgen.refusal(width, height, seats, None) is None
        for layout in mapgen.layouts_for(width, height, seats):
            world = mapgen.generate(seed=5, width=width, height=height, players=seats, layout=layout)
            report = mapgen.audit(world)
            assert report["players"] == seats and report["connected"], (size, layout, report)
            assert all(open_ground >= 90 for open_ground in report["open"]), (size, layout, report["open"])
            peasants = [u for u in world.units.values() if u.type is UnitType.PEASANT]
            assert len(peasants) == 3 * seats


@pytest.mark.parametrize("seats", (8, 16))
def test_a_match_of_many_seats_plays(seats: int, tmp_path) -> None:
    """Sixteen brains on the map the screen would give them, played for two minutes of game time:
    every seat builds, nobody is eliminated by a rule that assumed four, and the world stays sane."""
    size = mapgen.sizes_for(seats)[0]
    width, height = mapgen.dimensions(size, seats)
    world = mapgen.generate(seed=5, width=width, height=height, players=seats, human=None, layout=Layout.PLAINS)
    brains = [make_brain(p.id, Difficulty.HARD, 5) for p in world.players[:world.seats]]
    import random

    rng = random.Random(5)
    for _ in range(2400):  # two minutes at 20 Hz
        for brain in brains:
            brain.think(world, rng)
        world.step()
    assert world.winner is None, "nobody wins a two-minute free-for-all"
    assert all(p.alive for p in world.players[:world.seats]), [p.id for p in world.players[:world.seats] if not p.alive]
    for player in world.players[:world.seats]:
        assert world.player_buildings(player.id, BuildingType.TOWN_HALL), player.id
        assert world.player_units(player.id), player.id
    assert len(world.units) > 3 * seats, "every seat should have trained something"


def test_a_sixteen_seat_match_opens_and_ticks_in_a_window(tmp_path) -> None:
    """The scene, its HUD and its results: sixteen fog layers and sixteen sets of recoloured sprites."""
    game = Game("Warband sixteen", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        width, height = mapgen.dimensions(mapgen.sizes_for(16)[0], 16)
        scene = new_game(seed=5, width=width, height=height, players=16, difficulty=Difficulty.MEDIUM)
        game.push(scene)
        for _ in range(60):
            game.tick(0.1)
        assert isinstance(game.scene, GameScene) and scene.world.seats == 16
        assert scene.view.minimap_image().size[0] > 0
        assert len(scene.brains) == 15
    finally:
        game.close()


def test_new_game_never_offers_a_pairing_it_cannot_generate(tmp_path) -> None:
    """Every size button at every seat count: the screen moves whichever the player did not touch,
    and what it settles on always has a map."""
    game = Game("Warband new game", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        title = TitleScene()
        scene = NewGameScene(title)
        game.push(scene)
        game.tick(0.1)
        for seats in mapgen.SEAT_COUNTS:
            scene.set_players(seats)
            assert mapgen.refusal(*scene.dimensions, scene.players, scene.layout) is None, (seats, scene.size)
            for size in mapgen.SIZES:
                scene.set_size(size)
                assert mapgen.refusal(*scene.dimensions, scene.players, scene.layout) is None, (seats, size, scene.players)
                for layout in [*Layout, None]:
                    scene.set_layout(layout)
                    assert mapgen.refusal(*scene.dimensions, scene.players, scene.layout) is None, (size, layout)
    finally:
        game.close()


# -- What a room can hold ------------------------------------------------------------


def test_a_room_refuses_more_seats_than_a_client_can_join() -> None:
    """The seat count online is the engine's, not Warband's: a room is ``ONLINE_SEATS`` whatever the
    offline game seats, and asking for more is refused with a message, not a crash."""
    from saga2d import CommandError
    from warband.online.authority import ONLINE_SEATS, ONLINE_SIZE, _create

    for seats in (ONLINE_SEATS + 1, 8, 16):
        with pytest.raises(CommandError, match=f"players must be an integer from 2 to {ONLINE_SEATS}"):
            _create({"seed": 3, "players": seats})
    with pytest.raises(CommandError, match="width must be an integer from 48 to 80"):
        _create({"seed": 3, "players": 2, "width": 144, "height": 108})
    match = _create({"seed": 3, "players": ONLINE_SEATS, "width": ONLINE_SIZE[0], "height": ONLINE_SIZE[1]})
    assert match.world.seats == ONLINE_SEATS


def test_the_online_table_keeps_the_options_the_live_server_speaks() -> None:
    """A change to these is a new game id, not a rules deploy: every client in the wild sends them."""
    from saga2d import CommandError
    from warband.online.authority import ONLINE, _create

    assert set(ONLINE) == {"warband-v2"}
    with pytest.raises(CommandError, match="Unknown match option"):
        _create({"seed": 3, "seats": 4})
    for name, bad, good in (("players", 5, 4), ("width", 81, 80), ("height", 65, 64)):
        with pytest.raises(CommandError):
            _create({"seed": 3, name: bad})
        _create({"seed": 3, name: good, "players": 2 if name != "players" else good})


def test_the_title_refuses_a_room_it_cannot_make_and_says_why(tmp_path) -> None:
    """Multiplayer with sixteen seats chosen says what a room holds instead of quietly seating four."""
    game = Game("Warband rooms", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        from warband.online.authority import ONLINE_SEATS

        title = TitleScene(players=16, size=mapgen.sizes_for(16)[0])
        game.push(title)
        game.tick(0.1)
        scene = game.scene
        title.multiplayer()
        game.tick(0.1)
        assert game.scene is scene, "no room menu opened"
        assert str(ONLINE_SEATS) in title.notice and "16" in title.notice
        title.players, title.size = ONLINE_SEATS, "Giant"  # a map a room cannot hold either
        assert title.room_refusal() is not None and "Large" in title.room_refusal()
        title.size = "Large"
        assert title.room_refusal() is None
    finally:
        game.close()
