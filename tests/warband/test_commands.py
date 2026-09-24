"""The side's commands (WB-061): Fortify, Withdraw, Scout, Harass, Gold and Lumber, on Ctrl with F, W, S, R, M and L in
every scheme and on the Commands row.  Pressed again within 1.5 s a command reaches its next level, and each press acts at
once for its step.  The adjutant (``warband.brains.adjutant``) decides from what the seat knows and gives recorded World
orders through ``GameScene.attempt``; a unit ordered by hand leaves its command.

What the commands decide is played on a bare world stepped directly, as the brains' tests play (:class:`Side`); the keys,
the row, the tags, the allowance and the replay go through the scene."""

from __future__ import annotations

import json
import math
import random

import pytest

from saga2d import Game
from warband.brains.adjutant import COMMANDS, LEVEL_WINDOW, Adjutant, Report
from warband.records.replay import Playback, Replay, digest
from warband.sim.model import Harvest, Move, RuleError, Unit, World
from warband.sim.rules import SIM_DT, BuildingType, Terrain, UnitType
from warband.art.textures import TILE
from warband.ui.controls import CHORDS, SCHEMES
from warband.ui.multiplayer import NetworkGameScene
from warband.ui.scene import DEFAULT_SETTINGS, GameScene, HelpScene
from warband.ui.style import build_theme

W, H = 64, 48
HALL, BARRACKS, MINE = (8, 20), (8, 26), (3, 20)  # the player's base on the west side, top-left tiles
WOOD = [(x, y) for x in range(14, 17) for y in range(8, 14)]  # a stand of trees north-east of the hall
RIVAL_HALL, RIVAL_MINE = (52, 20), (57, 20)  # the rival's base on the east side, in the fog
TOWER = (26, 22)  # where a rival tower stands east of the base, on the way out
KEYS = {command: letter for letter, command in CHORDS.items() if command in COMMANDS}


def staged(*, rival_known: bool = True, barracks: bool = False) -> World:
    """Seat 0's base in the west with a mine and a wood, seat 1's in the east with a mine and three peasants.  Seat 1 is
    a silent human: nothing of it moves unless a test says so, but for its peasants' work.  With *rival_known* seat 0
    has looked at the whole map once and remembers the rival's buildings, which it no longer sees."""
    terrain = [[Terrain.GRASS] * W for _ in range(H)]
    for x, y in WOOD:
        terrain[y][x] = Terrain.TREES
    world = World(W, H, terrain, 2, rng=random.Random(5))
    world.players[1].human = True
    world.place_building(0, BuildingType.TOWN_HALL, HALL)
    if barracks:
        world.place_building(0, BuildingType.BARRACKS, BARRACKS)
    world.place_building(None, BuildingType.GOLD_MINE, MINE)
    world.place_building(1, BuildingType.TOWN_HALL, RIVAL_HALL)
    world.place_building(None, BuildingType.GOLD_MINE, RIVAL_MINE)
    for i in range(3):
        world.spawn_unit(1, UnitType.PEASANT, (56.5, 24.5 + i))
    world.players[0].gold = world.players[0].lumber = 20000
    if rival_known:
        world.reveal_all(0)
    world.update_vision()
    return world


def army(world: World, *kinds: UnitType, at: tuple[float, float] = (12.5, 24.5), player: int = 0) -> list[Unit]:
    """Units of *kinds* in rows of four from *at*, and the side's sight brought up to date."""
    units = [world.spawn_unit(player, kind, (at[0] + i % 4, at[1] + i // 4)) for i, kind in enumerate(kinds)]
    world.update_vision()
    return units


def own(world: World, kind: BuildingType, player: int = 0):
    return world.player_buildings(player, kind)[0]


def goal(unit: Unit) -> tuple[float, float] | None:
    return unit.order.target if isinstance(unit.order, Move) else None


class Side:
    """Seat 0's adjutant on a world stepped directly: its orders go straight to the world, as a brain's do, and its
    clock is the match's."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.given: list[tuple[str, tuple]] = []
        self.news: list[str] = []
        self.adjutant = Adjutant(0, self.give, random.Random(1))

    def give(self, action: str, *args, **kwargs) -> bool:
        try:
            getattr(self.world, action)(*args, **kwargs)
        except RuleError:
            return False
        self.given.append((action, args))
        return True

    def press(self, command: str, times: int = 1) -> Report:
        """*command*, *times* in a row at this moment: the last press's level."""
        for _ in range(times):
            report = self.adjutant.press(self.world, command, self.world.time)
        return report

    def play(self, seconds: float) -> None:
        for _ in range(round(seconds / SIM_DT)):
            self.news += self.adjutant.think(self.world)
            self.world.step()
            self.world.take_events()

    def working(self, command: str) -> set[int]:
        return set(self.adjutant.members(command))


# -- Scout ---------------------------------------------------------------------------------------------------------------


def test_scouting_goes_up_a_level_at_a_time_and_each_level_asks_for_so_many_in_all() -> None:
    """Eight soldiers and a flyer: the flyer, then up to a quarter of the nine (three in all), then up to half (five in
    all), the fastest first; a press after the window starts over at one, and one is out already."""
    world = staged()
    army(world, *[UnitType.FOOTMAN] * 4, *[UnitType.KNIGHT] * 4, UnitType.FLYING_MACHINE)
    side = Side(world)
    counts = []
    for _ in range(3):
        side.press("scout")
        counts.append(len(side.working("scout")))
    assert counts == [1, 3, 5]
    kinds = sorted(world.units[i].type.value for i in side.working("scout"))
    assert kinds == ["flying_machine", "knight", "knight", "knight", "knight"]
    side.play(LEVEL_WINDOW + 0.5)
    report = side.press("scout")
    assert len(side.working("scout")) == 5 and report.said == "5 already scouting"


def test_a_scout_keeps_moving_to_the_ground_seen_least_lately() -> None:
    world = staged()
    flyer, = army(world, UnitType.FLYING_MACHINE)
    side = Side(world)
    side.press("scout")
    goals = []
    for _ in range(40):
        side.play(1.0)
        assert flyer.orders, "a scout never stands"
        if goal(flyer) not in goals:
            goals.append(goal(flyer))
    assert len(goals) >= 6 and side.working("scout") == {flyer.id}


def test_a_scout_hurt_below_half_comes_home_and_is_its_players_again_there() -> None:
    world = staged()
    knight, = army(world, UnitType.KNIGHT, at=(30.5, 24.5))
    side = Side(world)
    side.press("scout")
    side.play(1.0)
    knight.hp = knight.max_hp // 2 - 1
    side.play(1.0)
    hall = own(world, BuildingType.TOWN_HALL)
    assert side.adjutant.tags == {knight.id: "withdrawing"} and math.dist(goal(knight), hall.center) < 3
    side.play(15.0)
    assert side.adjutant.tags == {} and math.dist(knight.pos, hall.center) < 5


def test_a_scout_keeps_clear_of_a_tower_the_side_knows() -> None:
    world = staged()
    tower = world.place_building(1, BuildingType.TOWER, TOWER)
    world.reveal_all(0)
    flyer, = army(world, UnitType.FLYING_MACHINE)
    side = Side(world)
    side.press("scout")
    for _ in range(60):
        side.play(0.5)
        assert math.dist(flyer.pos, tower.center) > tower.info.range
    assert flyer.hp == flyer.max_hp


def orders_given(command: str, hidden: list[tuple[int, BuildingType | UnitType, tuple]], units: list[tuple[UnitType, tuple]], *,
                 times: int = 1, **staging) -> list[tuple[str, tuple]]:
    """The orders seat 0's adjutant gives for *command* pressed *times*, with seat 0's *units* (``(kind, where)``) and
    *hidden* (``(player, kind, where)``) put in the fog after the side last looked: there, and nothing it can know of."""
    world = staged(**staging)
    for kind, where in units:
        army(world, kind, at=where)
    placed = []
    for player, kind, where in hidden:
        placed.append(world.place_building(player, kind, where) if isinstance(kind, BuildingType) else world.spawn_unit(player, kind, where))
    world.update_vision()
    for thing in placed:
        seen = world.any_visible(0, thing.rect) if isinstance(thing.type, BuildingType) else world.is_visible(0, thing.tile)
        assert not seen and thing.id not in world.worker_knowledge[0].buildings
    side = Side(world)
    side.press(command, times)
    assert side.given, "a comparison of nothing proves nothing"
    return side.given


def test_what_stands_in_the_fog_changes_nothing_the_commands_do() -> None:
    """The adjutant reads the seat's fog and memory, never the world: a tower over where a scout would look, a rival hall
    nearer than the one the side knows, and a rival soldier by one of its own, all unseen, leave every order as it was."""
    flyer = [(UnitType.FLYING_MACHINE, (12.5, 24.5))]
    under_fire = [(1, BuildingType.TOWER, (12, 5))]  # its fire covers the nearest ground to look at, out of the flyer's sight
    assert orders_given("scout", under_fire, flyer) == orders_given("scout", [], flyer)
    near = [(1, BuildingType.TOWN_HALL, (8, 3))]  # north of the base and far out of its sight; the known rival is east
    assert orders_given("fortify", near, [], barracks=True) == orders_given("fortify", [], [], barracks=True)
    footmen = [(UnitType.FOOTMAN, (26.5, 30.5)), (UnitType.FOOTMAN, (36.5, 24.5))]  # half of them is the one more exposed
    lurking = [(1, UnitType.FOOTMAN, (26.5, 37.5))]  # seven tiles from the nearer one: in the fog
    assert orders_given("withdraw", lurking, footmen, times=2) == orders_given("withdraw", [], footmen, times=2)


# -- Harass --------------------------------------------------------------------------------------------------------------


def test_harass_refuses_while_no_rival_worker_is_known_though_they_stand_in_the_fog() -> None:
    world = staged(rival_known=False)
    army(world, UnitType.KNIGHT, UnitType.KNIGHT)
    side = Side(world)
    assert side.press("harass") == Report("No rival workers known: scout first", refused=True)
    assert side.given == [] and side.working("harass") == set()


def test_the_raiders_are_the_fastest_soldiers_never_a_worker_nor_the_unarmed_flyer() -> None:
    world = staged()
    others = army(world, UnitType.FOOTMAN, UnitType.FOOTMAN, UnitType.FLYING_MACHINE, UnitType.PEASANT, UnitType.PEASANT)
    knights = army(world, *[UnitType.KNIGHT] * 4, at=(12.5, 28.5))
    side = Side(world)
    side.press("harass")
    raiders = side.working("harass")
    assert len(raiders) == 3 and raiders <= {k.id for k in knights}
    mine = next(b for b in world.buildings.values() if (b.x, b.y) == RIVAL_MINE)
    assert all(goal(world.units[i]) == mine.center for i in raiders)
    assert side.press("harass").said == "3 already harassing (level 2)"  # a quarter of the six fighters is two
    side.press("harass")  # half of them is three
    assert side.working("harass") == raiders and not {u.id for u in others} & set(side.adjutant.party)


def test_the_raiders_strike_workers_and_ride_home_the_moment_rival_soldiers_come_into_sight() -> None:
    world = staged()
    knights = army(world, UnitType.KNIGHT, UnitType.KNIGHT, UnitType.KNIGHT, at=(44.5, 24.5))
    side = Side(world)
    side.press("harass")
    workers = {u.id for u in world.player_units(1)}
    for _ in range(40):
        side.play(0.5)
        if any(u.order is not None and getattr(u.order, "target", None) in workers for u in knights) or len(world.player_units(1)) < 3:
            break
    else:
        pytest.fail("the raiders never struck a worker")
    guard, = army(world, UnitType.FOOTMAN, at=(knights[0].x + 4, knights[0].y), player=1)
    side.play(1.0)
    hall = own(world, BuildingType.TOWN_HALL)
    assert side.working("withdraw") == {k.id for k in knights if k.id in world.units}
    assert all(math.dist(goal(k), hall.center) < 3 for k in knights if k.id in world.units)
    assert side.news == ["Raiders ride home: rival soldiers in sight"]


def test_a_raid_with_nobody_left_to_strike_ends_at_home() -> None:
    world = staged()
    for peasant in world.player_units(1):
        world.remove_unit(peasant.id) if hasattr(world, "remove_unit") else world.units.pop(peasant.id)
    knights = army(world, UnitType.KNIGHT, UnitType.KNIGHT, at=(44.5, 24.5))
    side = Side(world)
    side.press("harass")
    side.play(30.0)
    assert "The raid is over: the raiders ride home" in side.news
    side.play(20.0)
    hall = own(world, BuildingType.TOWN_HALL)
    assert side.adjutant.party == {} and all(math.dist(k.pos, hall.center) < 6 for k in knights)


def test_a_rival_mine_under_a_known_towers_fire_is_no_place_to_raid() -> None:
    world = staged()
    world.place_building(1, BuildingType.TOWER, (55, 25))
    world.reveal_all(0)
    world.update_vision()
    army(world, UnitType.KNIGHT)
    assert Side(world).press("harass").refused


# -- Withdraw ------------------------------------------------------------------------------------------------------------


def test_withdraw_brings_the_wounded_then_half_the_most_exposed_then_everyone_home_walking() -> None:
    world = staged()
    home = army(world, UnitType.FOOTMAN, UnitType.FOOTMAN, at=(12.5, 21.5))
    out = army(world, *[UnitType.FOOTMAN] * 5, at=(34.5, 20.5)) + army(world, UnitType.FOOTMAN, at=(30.5, 36.5))
    peasant, = army(world, UnitType.PEASANT, at=(30.5, 30.5))
    out[0].hp = out[1].hp = 20
    rival, = army(world, UnitType.FOOTMAN, at=(33.5, 36.5), player=1)  # beside the last, nearer home than the rest
    assert world.is_visible(0, rival.tile)
    side = Side(world)
    side.press("withdraw")
    assert side.working("withdraw") == {out[0].id, out[1].id}
    side.press("withdraw")  # half of the six outside: the wounded two and the one the rival stands by
    assert side.working("withdraw") == {out[0].id, out[1].id, out[5].id}
    side.press("withdraw")
    assert side.working("withdraw") == {u.id for u in out}
    hall = own(world, BuildingType.TOWN_HALL)
    assert all(isinstance(u.order, Move) and math.dist(goal(u), hall.center) < 3 for u in out)
    assert not {u.id for u in home} & set(side.adjutant.party) and peasant.id not in side.adjutant.party


def test_a_soldier_that_takes_up_a_fight_on_the_way_home_is_its_players_again() -> None:
    """Soldiers walking home fight what comes at them; one that does is no longer walking home, and a tag saying it is
    would stay on it for good (a smoke match left two archers "withdrawing" in a fight for the rest of it)."""
    world = staged()
    archer, = army(world, UnitType.ARCHER, at=(30.5, 24.5))
    archer.hp = 10
    side = Side(world)
    side.press("withdraw")
    rival, = army(world, UnitType.PEASANT, at=(archer.x + 2, archer.y), player=1)
    side.play(0.2)
    world.attack([archer.id], rival.id)  # the fight is the archer's own: nobody told the adjutant
    side.play(1.5)
    assert side.adjutant.party == {}


# -- Fortify -------------------------------------------------------------------------------------------------------------


def test_fortify_waits_for_what_a_tower_needs() -> None:
    world = staged()
    report = Side(world).press("fortify")
    assert report == Report("No tower can be built yet: it needs a Barracks", refused=True)
    assert world.player_plans(0) == []


def test_fortify_plans_one_three_then_six_towers_across_the_approaches_and_calls_the_wounded_home() -> None:
    world = staged(barracks=True)
    wounded, = army(world, UnitType.FOOTMAN, at=(30.5, 24.5))
    wounded.hp = 10
    side = Side(world)
    planned = []
    for _ in range(3):
        side.press("fortify")
        planned.append([plan.pos for plan in world.player_plans(0) if plan.type is BuildingType.TOWER])
    assert [len(sites) for sites in planned] == [1, 3, 6]
    hall, mine = own(world, BuildingType.TOWN_HALL), next(b for b in world.buildings.values() if (b.x, b.y) == MINE)
    first = planned[0][0]
    assert first[0] > hall.x + hall.size and abs(first[1] + 1 - hall.center[1]) <= 3, "the first faces the known rival, east"
    sites = planned[-1]
    centres = [(x + 1, y + 1) for x, y in sites]
    assert all(math.dist(a, b) >= 3 for i, a in enumerate(centres) for b in centres[i + 1:]), "spread, one an approach"
    for x, y in sites:  # none on the walk between the hall and its mine, which lies west of it
        assert not (x <= mine.x + mine.size and hall.x <= x + 2 and hall.y - 2 <= y <= hall.y + hall.size + 1), (x, y)
    assert side.working("withdraw") == {wounded.id}


# -- Gold and Lumber -----------------------------------------------------------------------------------------------------


def test_gold_takes_the_idle_and_a_share_of_the_lumber_crews_level_by_level_with_ordered_harvests() -> None:
    world = staged()
    idle = army(world, UnitType.PEASANT, UnitType.PEASANT, at=(12.5, 24.5))
    choppers = army(world, *[UnitType.PEASANT] * 4, at=(14.5, 15.5))
    world.harvest([u.id for u in choppers], WOOD[5])
    mine = next(b for b in world.buildings.values() if (b.x, b.y) == MINE)

    def mining() -> set[int]:
        return {u.id for u in world.player_units(0)
                if any(isinstance(o, Harvest) and o.target == mine.id and not o.placed for o in u.orders)}

    side = Side(world)
    counts = []
    for _ in range(3):
        side.press("gold")
        counts.append(len(mining()))
    assert counts == [3, 4, 6] and {u.id for u in idle} <= mining()
    side.play(10.0)
    assert len(mining()) == 6, "the worker policy leaves an ordered harvest alone"


def test_lumber_sends_workers_to_the_trees_the_side_remembers_two_to_a_tree() -> None:
    world = staged()
    workers = army(world, *[UnitType.PEASANT] * 4, at=(12.5, 24.5))
    report = Side(world).press("lumber")
    targets = [u.order.target for u in workers if isinstance(u.order, Harvest)]
    assert report.said == "4 more chopping" and len(targets) == 4
    assert all(world.terrain_at(t) is Terrain.TREES for t in targets) and max(targets.count(t) for t in targets) <= 2


# -- Through the scene ---------------------------------------------------------------------------------------------------


@pytest.fixture
def game(tmp_path):
    g = Game("Warband commands", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g.close()


def scene_of(game: Game, world: World, *, controls: str = "classic", ranked: bool = False,
             scene_class: type[GameScene] = GameScene) -> GameScene:
    scene = scene_class(world, 5, settings=dict(DEFAULT_SETTINGS, controls=controls, tutorial=False, sfx=0.0, music=0.0), ranked=ranked)
    game.push(scene)
    game.tick(1 / 60)
    scene.camera.center_on(14 * TILE, 22 * TILE)
    game.tick(1 / 60)
    return scene


def press(game: Game, command: str) -> None:
    game.backend.inject_key(KEYS[command], ctrl=True)
    game.tick(1 / 60)


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_every_scheme_takes_the_same_chords_and_shows_them(game, controls: str) -> None:
    """On the Commands row (its heading says Ctrl, each keycap the letter), in the hint bar and in the help, the same
    Ctrl chords in every scheme; the flyer goes scouting and wears its tag, and the button's tooltip counts it."""
    world = staged()
    footman, flyer = army(world, UnitType.FOOTMAN, UnitType.FLYING_MACHINE)
    scene = scene_of(game, world, controls=controls)
    for name, button in scene.command_buttons.items():
        x, y, w, h = button.bounds
        assert {t["text"] for t in game.backend.texts if x <= t["x"] < x + w and y <= t["y"] < y + h} == {button.text, KEYS[name].upper()}
    assert [c.text for c in scene.command_row.children][0] == "Ctrl +"
    assert ("Ctrl+F/W/S/R/M/L", "commands") in scene.hint()
    press(game, "scout")
    assert scene.adjutant.tags == {flyer.id: "scouting"} and scene.command_buttons["scout"].hint.endswith("1 scouting now")
    assert scene.status == "Scouting: a Flying Machine"
    game.push(HelpScene(scene.scheme))
    game.tick(1 / 60)
    assert "Ctrl + F W S R M L" in [t["text"] for t in game.backend.texts]


def test_the_pips_show_the_level_while_another_press_would_raise_it(game) -> None:
    world = staged()
    army(world, *[UnitType.FOOTMAN] * 8)
    scene = scene_of(game, world)
    button = scene.command_buttons["scout"]
    pips = []
    for _ in range(3):
        press(game, "scout")
        game.tick(0.5)
        pips.append((button.pips, sum(1 for c in game.backend.circles if c["space"] == "screen" and c["radius"] == 3.0
                                      and c["color"][:3] == (255, 214, 110))))
    assert pips == [(1, 1), (2, 2), (3, 3)]
    for _ in range(round(LEVEL_WINDOW / 0.1) + 1):
        game.tick(0.1)
    assert button.pips == 0


def test_a_press_with_nothing_to_do_says_why_and_still_counts_toward_the_next_level(game) -> None:
    """Nobody is wounded, so Withdraw's first level has nothing to do and the status line says so; pressed again at
    once it is the second level, half the soldiers outside."""
    world = staged()
    footmen = army(world, *[UnitType.FOOTMAN] * 4, at=(30.5, 24.5))
    scene = scene_of(game, world)
    press(game, "withdraw")
    assert scene.status == "Nobody wounded out there" and scene.command_buttons["withdraw"].pips == 1
    press(game, "withdraw")
    assert len(working(scene, "withdraw")) == 2 and scene.status == "Withdrawing 2 to the hall (level 2)"
    assert all(u.id in scene.world.units for u in footmen)


def test_a_unit_its_player_orders_by_hand_leaves_its_command(game) -> None:
    world = staged()
    knights = army(world, UnitType.KNIGHT, UnitType.KNIGHT, UnitType.KNIGHT)
    scene = scene_of(game, world)
    press(game, "harass")
    assert len(working(scene, "harass")) == 3
    scene.select([knights[0].id])
    game.backend.inject_key("s")  # Stop, on the knight's card
    game.tick(1 / 60)
    assert working(scene, "harass") == {knights[1].id, knights[2].id} and not knights[0].orders
    knights[1].hp = 0  # and one that falls leaves too
    for _ in range(10):
        game.tick(0.1)
    assert working(scene, "harass") == {knights[2].id}


def working(scene: GameScene, command: str) -> set[int]:
    return set(scene.adjutant.members(command))


def test_the_tag_sits_over_the_health_bar_never_on_it(game) -> None:
    world = staged()
    flyer, knight = army(world, UnitType.FLYING_MACHINE, UnitType.KNIGHT)
    scene = scene_of(game, world)
    press(game, "scout")
    knight.hp = 10
    press(game, "withdraw")
    game.tick(1 / 60)
    tags = {t["text"]: t for t in game.backend.texts if t["space"] == "world" and t["text"] in ("scouting", "withdrawing")}
    assert set(tags) == {"scouting", "withdrawing"}
    bar = min((r for r in game.backend.rects if r["space"] == "world" and r["color"] == (240, 90, 70, 255)), key=lambda r: r["y"])
    assert tags["withdrawing"]["y"] < bar["y"] - 1 / scene.camera.zoom and abs(tags["withdrawing"]["x"] - (bar["x"] + TILE * 0.4)) < TILE


class Metered(GameScene):
    order_burst = 4


def test_the_commands_keep_to_the_allowance_a_match_played_elsewhere_sets(game) -> None:
    """The room server drops a client that sends more than 40 orders at once: online, cancel mode and the commands give
    20 at most between them and 10 a second after that.  Scouts beyond the allowance are sent as it comes back."""
    assert NetworkGameScene.order_burst is not None and NetworkGameScene.order_burst <= 20
    world = staged()
    army(world, *[UnitType.KNIGHT] * 12)
    scene = scene_of(game, world, scene_class=Metered)
    given = []
    scene.order = lambda action, *args, **kwargs: (given.append(scene.clock), getattr(scene.world, action)(*args, **kwargs))
    for _ in range(3):
        press(game, "scout")
    scouts = [scene.world.units[uid] for uid in working(scene, "scout")]
    assert len(given) == 4 and len(scouts) == 6 and sum(bool(u.orders) for u in scouts) == 4
    for _ in range(30):
        game.tick(0.1)
    assert all(u.orders for u in scouts), "the two left over went as the allowance came back"
    for i, at in enumerate(given):  # never more than the burst at once, nor faster than half of it a second after
        assert sum(1 for other in given[i:] if other - at < 1.0) <= Metered.order_burst + Metered.order_burst / 2


def test_a_match_that_used_every_command_replays_to_the_bit(game) -> None:
    world = staged(barracks=True)
    soldiers = army(world, UnitType.FLYING_MACHINE, *[UnitType.KNIGHT] * 4, *[UnitType.FOOTMAN] * 4)
    soldiers[4].hp = 20  # a wounded knight: no raider, and home at Withdraw's first level
    army(world, *[UnitType.PEASANT] * 4, at=(12.5, 28.5))
    scene = scene_of(game, world, ranked=True)
    for command in ("scout", "harass", "fortify", "fortify", "gold", "lumber"):
        press(game, command)
    for _ in range(40):
        game.tick(0.1)
    press(game, "withdraw")
    for _ in range(40):
        game.tick(0.1)
    names = {row[1] for row in scene.replay.orders}
    assert {"move", "plan_building", "harvest"} <= names
    scene.replay.finish(world, "left")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(scene.replay.to_dict()))))
    playback.run()
    assert playback.faithful and digest(playback.world) == digest(world)


class Room:
    """A room server's seat in process: orders reach the authoritative match through the server's own rate check
    (``saga2d.server``: 40 at once, 20 a second after that, and a client past it is dropped), and the seat's snapshot
    comes back at each poll, a step of the match later."""

    BURST, REFILL = 40.0, 20.0
    online = False

    def __init__(self, match, player: int = 0) -> None:
        self.match, self.player = match, player
        self.revision, self.ready, self.room, self.error = 0, True, "", ""
        self.allowance, self.at, self.flooded = self.BURST, 0.0, 0
        self.moved: set[int] = set()  # the units the seat has sent somewhere
        self.state = match.snapshot(player)

    def submit(self, command: dict) -> None:
        now = self.match.world.time
        self.allowance, self.at = min(self.BURST, self.allowance + (now - self.at) * self.REFILL), now
        if self.allowance < 1:
            self.flooded += 1
            return
        self.allowance -= 1
        self.match.apply(self.player, json.loads(json.dumps(command)))
        if command["action"] == "move":
            self.moved.update(command["args"][0])

    def poll(self) -> None:
        self.match.step()
        self.state = self.match.snapshot(self.player)
        self.revision += 1

    def close(self) -> None:
        pass


@pytest.mark.slow
def test_online_the_commands_keep_under_the_room_servers_rate_and_work_from_the_seats_snapshot(game) -> None:
    """A seat with ninety knights and a flyer presses the commands three times in a row: forty-six scouts alone are more
    orders than the server takes at once, yet they all reach the authority and none goes past its rate.  The adjutant
    runs in the client, on the snapshot its seat is sent, which shows an order only once the server has it.  Five
    seconds of a match through a whole seat's snapshot at every step take more than a second: the slow tier."""
    from warband.online.authority import WarbandMatch

    match = WarbandMatch(seed=3)
    world = match.world
    hall = own(world, BuildingType.TOWN_HALL)
    for i in range(90):
        world.spawn_unit(0, UnitType.KNIGHT, (hall.x + 5.5 + i % 10, hall.y + 0.5 + i // 10))
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (hall.x + 4.5, hall.y + 4.5))
    world.reveal_all(0)
    world.update_vision()
    room = Room(match)
    scene = NetworkGameScene(room, settings=dict(DEFAULT_SETTINGS, tutorial=False, sfx=0.0, music=0.0))
    game.push(scene)
    game.tick(1 / 60)
    for command in ("scout", "harass", "fortify", "gold", "lumber", "withdraw"):  # Withdraw's first level: nobody wounded
        for _ in range(3 if command != "withdraw" else 1):
            press(game, command)
    for _ in range(50):
        game.tick(0.1)
    scouts = working(scene, "scout")
    assert room.flooded == 0 and len(scouts) == 46 and scouts <= room.moved, "every scout was sent, in time"
