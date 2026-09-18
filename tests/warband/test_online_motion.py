"""Online units move on screen between snapshots (WB-010).

A room publishes every other 20 Hz tick.  The client once applied each snapshot as it landed, so a unit stood
still for five frames in six and then jumped; now it moves on from where it was drawn towards where the snapshot
puts it, over the measured interval between snapshots, and after a stall or a resume it is placed, not slid.
"""
import math
import random

import pytest

from saga2d import CommandError, Game
from warband.authority import WarbandMatch
from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.style import build_theme

FRAME = 1 / 60
QUIET = {"music": 0, "sfx": 0, "tutorial": False}


class Seat:
    """A seat in a room without the socket: it is sent its snapshot when the test publishes."""

    online = True

    def __init__(self, match: WarbandMatch, player: int = 0) -> None:
        self.match, self.player, self.room = match, player, "motion"
        self.ready, self.error, self.revision = True, "", 0
        self.state = match.snapshot(player)

    def publish(self) -> None:
        self.state, self.revision = self.match.snapshot(self.player), self.revision + 1

    def poll(self) -> None:
        pass

    def submit(self, command: dict) -> None:
        if not self.ready:
            raise CommandError(self.error or "Waiting for your partner to connect.")
        self.match.apply(self.player, command)

    def close(self) -> None:
        pass


@pytest.fixture
def game(tmp_path):
    g = Game("Warband motion", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g._teardown()


def field() -> WarbandMatch:
    """Open grass, two halls far apart, and seat 0's footman ordered east."""
    match = WarbandMatch(3)
    match.world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 2)
    for player in match.world.players:
        player.human = True
    match.world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    match.world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    match.world.update_vision()
    return match


def walk(game: Game, match: WarbandMatch, seat: Seat, arrivals, frames: int = 150):
    """Seat 0's footman walks east while the host steps at 20 Hz and publishes on the frames *arrivals* names;
    where the client draws it on every frame."""
    from warband.multiplayer import NetworkGameScene

    footman = match.world.spawn_unit(0, UnitType.FOOTMAN, (6.5, 12.5))
    footman.facing = 0.0
    match.world.move([footman.id], (36.5, 12.5))
    seat.publish()
    scene = NetworkGameScene(seat, settings=QUIET)
    game.push(scene)
    drawn = []
    for frame in range(frames):
        if frame % 3 == 0:
            match.step()
        if frame in arrivals:
            seat.publish()
        game.tick(FRAME)
        drawn.append(scene.view.unit_position(scene.world.units[footman.id]))
    return scene, footman, drawn


def steps(drawn: list[tuple[float, float]], start: int = 30, count: int = 59) -> list[float]:
    return [math.dist(a, b) for a, b in zip(drawn[start:start + count], drawn[start + 1:start + count + 1])]


def test_a_unit_walks_on_screen_between_regular_snapshots(game) -> None:
    match = field()
    scene, footman, drawn = walk(game, match, Seat(match), arrivals=set(range(0, 150, 6)))
    travel = steps(drawn)
    per_frame = match.world.speed_of(footman) * FRAME
    assert sum(1 for d in travel if d < 1e-6) <= 3, f"stationary intervals: {sum(1 for d in travel if d < 1e-6)}/59"
    assert max(travel) <= 2 * per_frame, f"a jump of {max(travel):.3f} tiles against {per_frame:.3f} a frame"


def test_a_unit_walks_on_through_uneven_snapshots(game) -> None:
    rng = random.Random(10)
    arrivals, frame = set(), 0
    while frame < 150:
        arrivals.add(frame)
        frame += rng.choice((4, 5, 6, 7, 8))  # a hundred milliseconds, give or take a third
    match = field()
    scene, footman, drawn = walk(game, match, Seat(match), arrivals=arrivals)
    travel = steps(drawn)
    per_frame = match.world.speed_of(footman) * FRAME
    assert sum(1 for d in travel if d < 1e-6) <= 3, f"stationary intervals: {sum(1 for d in travel if d < 1e-6)}/59"
    assert max(travel) <= 2 * per_frame, f"a jump of {max(travel):.3f} tiles against {per_frame:.3f} a frame"


def test_after_a_stall_units_are_placed_where_the_snapshot_says_not_slid(game) -> None:
    match = field()
    arrivals = set(range(0, 60, 6)) | {130}  # over a second of silence, then one snapshot
    scene, footman, drawn = walk(game, match, Seat(match), arrivals=arrivals, frames=131)
    sent = scene.world.units[footman.id].pos
    assert drawn[130] == sent, "after a stall the unit slid from where it was drawn"
    assert any("No word from the server" in t["text"] for t in game.backend.texts), "the silence was not said"


def test_a_unit_that_comes_into_sight_is_placed_not_slid(game) -> None:
    from warband.multiplayer import NetworkGameScene

    match = field()
    seat = Seat(match)
    scene = NetworkGameScene(seat, settings=QUIET)
    game.push(scene)
    for frame in range(12):
        if frame % 3 == 0:
            match.step()
        if frame % 6 == 0:
            seat.publish()
        game.tick(FRAME)
    newcomer = match.world.spawn_unit(0, UnitType.KNIGHT, (20.5, 20.5))
    match.step()
    seat.publish()
    game.tick(FRAME)
    unit = scene.world.units[newcomer.id]
    assert scene.view.unit_position(unit) == unit.pos


def test_an_order_given_while_the_seat_waits_is_refused_with_the_reason(game) -> None:
    from warband.multiplayer import NetworkGameScene

    match = field()
    seat = Seat(match)
    worker = match.world.spawn_unit(0, UnitType.PEASANT, (5.5, 5.5))
    seat.publish()
    scene = NetworkGameScene(seat, settings=QUIET)
    game.push(scene)
    game.tick(FRAME)
    seat.ready, seat.error = False, "Connection lost — reconnecting to your room…"
    assert scene.attempt("move", [worker.id], (8.5, 5.5)) is False
    game.tick(FRAME)
    assert not match.world.units[worker.id].orders
    assert any("reconnecting" in t["text"] for t in game.backend.texts)


def test_over_a_real_socket_a_guest_walks_smoothly_hears_of_a_stall_and_is_placed_after_it(game) -> None:
    """Two real ends of a LAN match: the host steps at 20 Hz and publishes every other tick, then goes quiet for
    over a second (a stall, a pause, a dropped link that comes back), then publishes again."""
    import time

    from saga2d import MatchClient, MatchHost
    from warband.multiplayer import NetworkGameScene

    match = field()
    footman = match.world.spawn_unit(1, UnitType.FOOTMAN, (6.5, 12.5))
    footman.facing = 0.0
    match.world.move([footman.id], (36.5, 12.5))
    host = MatchHost('warband-v2', match.apply, match.snapshot, address=('127.0.0.1', 0), token='motion')
    client = MatchClient('warband-v2', host.address, token='motion')

    def converge(until):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            host.poll()
            client.poll()
            if until():
                return
            time.sleep(.001)
        raise AssertionError('the socket did not converge')

    try:
        converge(lambda: client.ready)
        scene = NetworkGameScene(client, settings=QUIET)
        game.push(scene)
        drawn, sent = [], []
        for frame in range(150):
            if frame % 3 == 0:
                match.step()
                if match.world.tick % 2 == 0 and not 60 <= frame < 140:
                    host.publish()
                    converge(lambda: client.state['world']['tick'] == match.world.tick)
            game.tick(FRAME)
            drawn.append(scene.view.unit_position(scene.world.units[footman.id]))
            sent.append(scene.world.units[footman.id].pos)
        travel = steps(drawn, start=24, count=30)
        assert sum(1 for d in travel if d < 1e-6) <= 1 and max(travel) <= 2 * match.world.speed_of(footman) * FRAME
        assert any("No word from the server" in t["text"] for t in game.backend.texts)
        arrival = next(frame for frame in range(140, 150) if sent[frame] != sent[frame - 1])
        assert drawn[arrival] == sent[arrival], "the first snapshot after the stall slid instead of placing the unit"
    finally:
        client.close()
        host.close()
