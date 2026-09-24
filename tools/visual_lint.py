"""Find visual defects automatically: the registered art, and every screen of the game.

    uv run python tools/visual_lint.py                     # everything, findings on stdout
    uv run python tools/visual_lint.py --screens select    # only the screens whose name contains "select"
    uv run python tools/visual_lint.py --evidence DIR      # also write PNGs: each flagged sprite, each screen (pyglet)
    uv run python tools/visual_lint.py --no-images         # skip the art checks (about a minute)

The checks live in :mod:`warband.art.visual_lint`; this walks the game's screens
on the mock backend (with font-based approximate metrics) and reports what each one drew.
With ``--evidence`` the same screens are rendered through pyglet so a person
can look at what the numbers point at; that needs an awake display.  The
resolutions are the tests' 1280×800 and the smallest a laptop gives the
windowed game (a 1280×800 display leaves 1200×680).
"""

from __future__ import annotations

import argparse
import collections
import math
import os
import random
import sys
import tempfile
from pathlib import Path
from typing import Callable

os.environ.setdefault("SAGA2D_SILENT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from saga2d.effects import Toast  # noqa: E402
from saga2d.testing.cpu_budget import CpuBudget  # noqa: E402
from saga2d.testing.native_frames import tick as native_tick  # noqa: E402
from warband.art import visual_lint as lint  # noqa: E402
from warband.story.campaign import Progress, ProgressStore  # noqa: E402
from warband.story.campaign_scene import CampaignScene  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionResultScene, MissionScene, build_world  # noqa: E402
from warband.story.missions import CAMPAIGN  # noqa: E402
from warband.sim.model import World, tile_center  # noqa: E402
from warband.sim.rules import BUILT, PLAYABLE_UNITS, BuildingType, Difficulty, Race, Terrain, UnitType, Upgrade  # noqa: E402
from warband.ui.controls import SCHEMES  # noqa: E402
from warband.ui.scene import TOAST_TOP, CodexScene, GameScene, HelpScene, PauseScene, SaveBrowserScene, SettingsScene, new_game  # noqa: E402
from warband.ui.score_scene import HighScoreScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from warband.art.textures import TILE  # noqa: E402
from warband.ui.title import TitleScene  # noqa: E402

RESOLUTIONS = ((1280, 800), (1200, 680))
QUIET = {"tutorial": False, "music": 0.0, "sfx": 0.0, "edge_scroll": False}
Screen = Callable[[Game], None]
SCREENS: dict[str, Screen] = {}


def screen(fn: Screen) -> Screen:
    SCREENS[fn.__name__] = fn
    return fn


def ticks(game: Game, n: int = 3, dt: float = 1 / 60) -> None:
    tick = game.tick if hasattr(game.backend, "inject_mouse_move") else lambda dt: native_tick(game, dt)
    for _ in range(n):
        tick(dt)


def move_mouse(game: Game, x: float, y: float) -> None:
    """Put the pointer at logical (x, y) on either backend."""
    backend = game.backend
    if hasattr(backend, "inject_mouse_move"):
        backend.inject_mouse_move(int(x), int(y))
    else:
        s = backend.scale_factor
        backend.window.dispatch_event("on_mouse_motion", int(x * s + backend.offset_x), int((game.resolution[1] - y) * s + backend.offset_y), 0, 0)


def drag_mouse(game: Game, start: tuple[float, float], end: tuple[float, float]) -> None:
    """Press the left button at logical *start* and drag it, held, to *end*, on either backend."""
    backend = game.backend
    if hasattr(backend, "inject_drag"):
        backend.inject_click(int(start[0]), int(start[1]))
        backend.inject_drag(int(end[0]), int(end[1]), end[0] - start[0], end[1] - start[1])
        return
    from pyglet.window import mouse

    s, height = backend.scale_factor, game.resolution[1]
    (x0, y0), (x1, y1) = ((int(x * s + backend.offset_x), int((height - y) * s + backend.offset_y)) for x, y in (start, end))
    backend.window.dispatch_event("on_mouse_press", x0, y0, mouse.LEFT, 0)
    backend.window.dispatch_event("on_mouse_drag", x1, y1, x1 - x0, y1 - y0, mouse.LEFT, 0)


def settlement() -> World:
    """A compact working settlement of every building: player 0 owns it, player 1 is a
    silent human so no AI acts (the fixture of tools/verify_art.py)."""
    width, height = 48, 36
    rng = random.Random(17)
    terrain = [[Terrain.GRASS for _ in range(width)] for _ in range(height)]
    for y in range(3, 10):
        for x in range(28, 40):
            if rng.random() < 0.62:
                terrain[y][x] = Terrain.TREES
    for x, y in ((2, 17), (3, 18), (4, 17), (3, 16), (37, 18), (38, 19), (39, 17)):
        terrain[y][x] = Terrain.ROCK
    for y in range(11, 16):
        for x in range(0, 4):
            terrain[y][x] = Terrain.WATER
    world = World(width, height, terrain, 2, rng=rng)
    world.players[1].human = True
    buildings = {
        BuildingType.FARM: (3, 7), BuildingType.TOWN_HALL: (7, 6), BuildingType.BARRACKS: (13, 6),
        BuildingType.TOWER: (19, 6), BuildingType.LUMBER_MILL: (23, 7), BuildingType.BLACKSMITH: (7, 17),
        BuildingType.STABLES: (13, 17), BuildingType.WORKSHOP: (20, 17), BuildingType.CHURCH: (27, 17),
    }
    for kind, pos in buildings.items():
        world.place_building(0, kind, pos)
    world.lay_rifts([(3, 22), (10, 24)])  # one drawn from by the vault, one open
    world.place_building(0, BuildingType.VAULT, (3, 22))
    world.place_building(None, BuildingType.GOLD_MINE, (32, 17))
    world.place_building(None, BuildingType.GOLD_SEAM, (33, 25))  # five tiles of workings beside the three of a mine
    world.place_building(1, BuildingType.TOWN_HALL, (43, 30))
    world.update_vision()
    world.reveal_all(0)
    return world


def match(game: Game, *, seed: int = 3, settings: dict | None = None, **kwargs) -> GameScene:
    scene = new_game(seed=seed, settings=settings, **kwargs)
    game.push(scene)
    ticks(game)
    return scene


def town(game: Game, *, race: Race = Race.HUMAN, zoom: float = 1.0, controls: str = "classic") -> GameScene:
    """The settlement, banner gone, camera on the buildings, played with *controls*."""
    world = settlement()
    world.players[0].race = race
    scene = GameScene(world, 17, settings=dict(QUIET, controls=controls))
    game.push(scene)
    scene.paused = True
    ticks(game, 20, 0.2)
    scene.paused = False
    scene.camera.zoom = zoom
    scene.camera.center_on(16 * TILE, 12 * TILE)
    ticks(game)
    return scene


def own(scene: GameScene, kind: BuildingType):
    return scene.world.player_buildings(scene.human, kind)[0]


def spawn(scene: GameScene, unit_type: UnitType, tile: tuple[int, int], player: int | None = None):
    unit = scene.world.spawn_unit(scene.human if player is None else player, unit_type, tile_center(tile))
    unit.facing = math.pi / 2
    return unit


# -- Screens ----------------------------------------------------------------------------


@screen
def title(game: Game) -> None:
    game.push(TitleScene())
    ticks(game)


@screen
def title_first_frame(game: Game) -> None:
    game.push(TitleScene())
    ticks(game, 1)


@screen
def codex_from_title(game: Game) -> None:
    """The codex read before a match: the race New game is set to, and a tech tree nobody stands in."""
    game.push(TitleScene())
    ticks(game)
    game.scene.codex()
    ticks(game)
    game.scene.page_tree()
    ticks(game)


for _race in Race:
    def _new_game(game: Game, race: Race = _race) -> None:
        game.push(TitleScene())
        ticks(game)
        game.scene.new_game()
        ticks(game)
        game.scene.set_race(race)
        ticks(game)

    SCREENS[f"new_game_{_race.value}"] = _new_game


@screen
def new_game_master(game: Game) -> None:
    """The longest of the difficulty notes, under the buttons it describes."""
    game.push(TitleScene())
    ticks(game)
    game.scene.new_game()
    ticks(game)
    game.scene.set_difficulty(Difficulty.MASTER)
    ticks(game)


@screen
def match_start(game: Game) -> None:
    match(game)
    ticks(game, 30)  # the banner has slid in and holds


@screen
def match_tutorial(game: Game) -> None:
    scene = match(game)
    ticks(game, 60, 0.1)
    scene.say("Peasants gather and build on their own; plan the settlement with B, T and U")
    ticks(game)


for _unit in PLAYABLE_UNITS:
    def _select_unit(game: Game, unit_type: UnitType = _unit) -> None:
        scene = town(game, zoom=2.0)
        unit = spawn(scene, unit_type, (10, 12))
        scene.select([unit.id])
        scene.camera.center_on(10 * TILE, 12 * TILE)
        ticks(game)

    SCREENS[f"select_{_unit.value}"] = _select_unit


for _count in (18, 60):
    def _select_many(game: Game, count: int = _count) -> None:
        scene = town(game)
        units = [spawn(scene, UnitType.PEASANT if i % 5 == 0 else UnitType.FOOTMAN, (6 + i % 12, 9 + i // 12)) for i in range(count)]
        scene.select([u.id for u in units])
        scene.camera.center_on(12 * TILE, 11 * TILE)
        ticks(game)

    SCREENS[f"select_{_count}_units"] = _select_many


@screen
def select_60_archers(game: Game) -> None:
    """Sixty of one kind, on the first of three pages: the heading names the armour class the whole selection
    shares, and light armour with a page marker is the widest that row ever gets."""
    scene = town(game)
    units = [spawn(scene, UnitType.ARCHER, (6 + i % 12, 9 + i // 12)) for i in range(60)]
    scene.select([u.id for u in units])
    scene.camera.center_on(12 * TILE, 11 * TILE)
    ticks(game)


for _building in BUILT:
    def _select_building(game: Game, kind: BuildingType = _building) -> None:
        scene = town(game)
        building = next(b for b in scene.world.buildings.values() if b.type is kind)
        scene.select([building.id])
        scene.camera.center_on(*(c * TILE for c in building.center))
        ticks(game)

    SCREENS[f"select_{_building.value}"] = _select_building


@screen
def select_busy_hall(game: Game) -> None:
    scene = town(game)
    hall = own(scene, BuildingType.TOWN_HALL)
    scene.select([hall.id])
    for _ in range(4):
        scene.train(UnitType.PEASANT)
    scene.world.set_rally(hall.id, (hall.x + 6, hall.y + 5))
    ticks(game, 20)


@screen
def select_upgraded(game: Game) -> None:
    """A footman whose blades and plate are researched, with a comrade at each elbow: every number the research
    and the shield wall raised carries its gold mark."""
    scene = town(game)
    scene.world.players[scene.human].upgrades.update({Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARMOR_1})
    middle = spawn(scene, UnitType.FOOTMAN, (10, 12))
    for side in (-1, 1):
        spawn(scene, UnitType.FOOTMAN, (10 + side, 12))
    scene.select([middle.id])
    scene.camera.center_on(10 * TILE, 12 * TILE)
    ticks(game)


@screen
def pending_attack(game: Game) -> None:
    """The attack mode armed and waiting for its click: the card's button lit and the status line saying what to
    click, where pressing A once said nothing at all."""
    scene = town(game)
    units = [spawn(scene, UnitType.FOOTMAN, (9 + i, 12)) for i in range(3)]
    scene.select([u.id for u in units])
    ticks(game)
    scene.start_pending("attack")
    ticks(game)


@screen
def pending_salvage(game: Game) -> None:
    """A peasant's Salvage armed over a ruin: the card's eighth button lit under Repair, the status line saying what
    to click, and the grey ruin it is meant for on the ground."""
    scene = town(game)
    ruin = scene.world.place_building(1, BuildingType.FARM, (12, 12))
    ruin.abandoned = True  # staged: what a rival's resignation leaves behind, without playing one out
    scene.world.update_vision()
    scene.world.reveal_all(scene.human)
    peasant = spawn(scene, UnitType.PEASANT, (10, 13))
    scene.select([peasant.id])
    ticks(game)
    scene.start_pending("salvage")
    ticks(game)


@screen
def select_site(game: Game) -> None:
    scene = town(game)
    world = scene.world
    site = world.place_building(scene.human, BuildingType.FARM, (12, 11), done=False)
    site.progress = site.info.build_time * 0.3
    scene.select([site.id])
    ticks(game)


@screen
def select_enemy(game: Game) -> None:
    scene = town(game)
    enemy = spawn(scene, UnitType.KNIGHT, (11, 12), player=1)
    scene.select([enemy.id])
    scene.camera.center_on(11 * TILE, 12 * TILE)
    ticks(game)


@screen
def select_army(game: Game) -> None:
    scene = town(game)
    units = [spawn(scene, kind, (6 + i % 6 * 2, 11 + i // 6 * 2)) for i, kind in enumerate(list(UnitType) * 2)]
    scene.select([u.id for u in units])
    ticks(game)


@screen
def select_damaged(game: Game) -> None:
    scene = town(game)
    hall = own(scene, BuildingType.TOWN_HALL)
    hall.hp = hall.max_hp // 5
    unit = spawn(scene, UnitType.FOOTMAN, (10, 12))
    unit.hp = unit.max_hp // 3
    scene.select([hall.id, unit.id])
    ticks(game, 10)


for _menu in ("build", "train", "upgrade"):
    def _menu_screen(game: Game, menu: str = _menu) -> None:
        scene = town(game)
        scene.toggle_catalogue(menu)
        ticks(game)

    SCREENS[f"menu_{_menu}"] = _menu_screen


for _menu in ("build", "train"):
    def _menu_at_start(game: Game, menu: str = _menu) -> None:
        """The catalogue on the first minute: what lacks its prerequisite greyed out, its picture in the corner and
        "needs …" under it; with a barracks planned, what it opens reads "after Barracks"."""
        scene = match(game, settings=QUIET)
        scene.open_catalogue("build")
        scene.choose_building(BuildingType.BARRACKS)
        scene.choose_building(BuildingType.BARRACKS)  # the planner's spot
        scene.open_catalogue(menu)
        ticks(game)

    SCREENS[f"menu_{_menu}_at_start"] = _menu_at_start


@screen
def menu_upgrade_researched(game: Game) -> None:
    """The Upgrade catalogue later in a match: Blades, researched to its top tier, has left the card and its slot
    stands empty, while Arrows shows the tier above the one being researched with its hourglass."""
    scene = town(game)
    scene.player.upgrades.update({Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.ARMOR_1})
    scene.player.gold = scene.player.lumber = 5000
    scene.world.research(own(scene, BuildingType.LUMBER_MILL).id, Upgrade.ARROWS_1)
    scene.toggle_catalogue("upgrade")
    ticks(game)


@screen
def menu_upgrade_all_done(game: Game) -> None:
    """Nothing left to research: the card holds no orders at all, only the way back, and the readout says why."""
    scene = town(game)
    scene.player.upgrades.update(u for u in Upgrade if scene.race.upgrade_allowed(u))
    scene.toggle_catalogue("upgrade")
    ticks(game)


@screen
def hud_warnings(game: Game) -> None:
    """The top bar saying what stops production: the supply pair red with the farms full, and gold red for a
    moment after a recruit was refused for want of it, with the card's prices red beside their symbols."""
    scene = town(game)
    scene.player.gold, scene.player.lumber = 120, 80
    for i in range(scene.world.supply(scene.human)[1]):
        spawn(scene, UnitType.FOOTMAN, (5 + i % 10, 14 + i // 10))
    scene.select([own(scene, BuildingType.TOWN_HALL).id])
    ticks(game)
    scene.warn(scene.world.can_train(own(scene, BuildingType.TOWN_HALL), UnitType.PEASANT))
    scene.toggle_catalogue("build")
    ticks(game)


@screen
def menu_build_hover(game: Game) -> None:
    scene = town(game)
    scene.toggle_catalogue("build")
    ticks(game)
    button = scene.card_buttons[0]
    x, y, w, h = button.bounds
    move_mouse(game, x + w / 2, y + h / 2)
    ticks(game)


@screen
def menu_train_hover(game: Game) -> None:
    """The longest tooltip the card has: the dwarves' healer, its cost in two resources and what it does."""
    scene = town(game, race=Race.DWARF)
    scene.toggle_catalogue("train")
    ticks(game)
    button = next(b for command, b in zip(scene.card, scene.card_buttons) if command.target is UnitType.CLERIC)
    x, y, w, h = button.bounds
    move_mouse(game, x + w / 2, y + h / 2)
    ticks(game)


@screen
def plans(game: Game) -> None:
    scene = town(game)
    scene.place(BuildingType.FARM, (12.5, 11.5))
    scene.order_production("train", UnitType.FOOTMAN)
    scene.order_production("upgrade", Upgrade.BLADES_1)
    scene.open_plans()
    ticks(game)


@screen
def production(game: Game) -> None:
    scene = town(game)
    scene.select([own(scene, BuildingType.TOWN_HALL).id])
    for _ in range(3):
        scene.train(UnitType.PEASANT)
    scene.select([own(scene, BuildingType.BARRACKS).id])
    scene.train(UnitType.FOOTMAN)
    scene.train(UnitType.ARCHER)
    scene.select([own(scene, BuildingType.BLACKSMITH).id])
    scene.research(Upgrade.BLADES_1)
    scene.select([])
    ticks(game, 30)


@screen
def ghost(game: Game) -> None:
    scene = town(game)
    peasant = spawn(scene, UnitType.PEASANT, (10, 12))
    scene.select([peasant.id])
    scene.open_catalogue("build")
    scene.choose_building(BuildingType.FARM)
    move_mouse(game, *scene.camera.world_to_screen(13 * TILE, 12 * TILE))
    ticks(game)


@screen
def shift_build(game: Game) -> None:
    """A peasant's next sites in gold, the settlement's plans in blue, the next farm's ghost under the pointer."""
    scene = town(game)
    world = scene.world
    peasant = spawn(scene, UnitType.PEASANT, (10, 12))
    scene.select([peasant.id])
    scene.open_catalogue("build")
    scene.choose_building(BuildingType.FARM)
    for x in (11, 14):
        scene.place(BuildingType.FARM, (x + 1, 13), keep=True)
    world.plan_building(scene.human, BuildingType.FARM, (17, 12))
    move_mouse(game, *scene.camera.world_to_screen(21 * TILE, 13 * TILE))
    ticks(game)


@screen
def plan_row(game: Game) -> None:
    """Farms a tile apart, the row Shift-placing lays out: three of the settlement's plans, with a fight on the middle
    one, and below them three sites a peasant, still on its way, builds next."""
    scene = town(game)
    world = scene.world
    for x in (9, 12, 15):
        world.plan_building(scene.human, BuildingType.FARM, (x, 11))
    ours = [spawn(scene, UnitType.FOOTMAN, tile) for tile in ((12, 11), (13, 12))]
    theirs = [spawn(scene, UnitType.FOOTMAN, tile, player=1) for tile in ((13, 11), (12, 12))]
    world.attack([u.id for u in ours], theirs[0].id)
    world.attack([u.id for u in theirs], ours[0].id)
    peasant = spawn(scene, UnitType.PEASANT, (5, 14))
    scene.select([peasant.id])
    scene.open_catalogue("build")
    scene.choose_building(BuildingType.FARM)
    for x in (9, 12, 15):
        scene.place(BuildingType.FARM, (x + 1, 15), keep=True)
    scene.select([])
    ticks(game)


@screen
def endless_barracks(game: Game) -> None:
    """A barracks training footmen and archers in turn, endlessly: the loop on both portraits and the line under the readout."""
    scene = town(game, zoom=1.5)
    world = scene.world
    world.players[scene.human].gold = world.players[scene.human].lumber = 5000
    barracks = own(scene, BuildingType.BARRACKS)
    for unit_type in (UnitType.FOOTMAN, UnitType.ARCHER):
        world.set_auto_train(barracks.id, unit_type, True)
    scene.select([barracks.id])
    scene.camera.center_on(*(c * TILE for c in barracks.center))
    ticks(game, 30, 0.1)


def cancel_town(game: Game) -> GameScene:
    """The town with a barracks at work (a footman endlessly, two archers queued behind), a row of three farms planned
    below the hall, and cancel mode on."""
    scene = town(game)
    world = scene.world
    world.players[scene.human].gold = world.players[scene.human].lumber = 5000
    barracks = own(scene, BuildingType.BARRACKS)
    world.set_auto_train(barracks.id, UnitType.FOOTMAN, True)
    for _ in range(2):
        world.train(barracks.id, UnitType.ARCHER)
    for x in (9, 12, 15):
        world.plan_building(scene.human, BuildingType.FARM, (x, 11))
    scene.toggle_cancel_mode()
    return scene


@screen
def cancel_mode(game: Game) -> None:
    """Cancel mode over the barracks at work: the pointer a red cross, the barracks outlined in red, the hint bar
    saying what a click would cancel, the Cancel button red beside Plans."""
    scene = cancel_town(game)
    barracks = own(scene, BuildingType.BARRACKS)
    move_mouse(game, *scene.camera.world_to_screen(barracks.center[0] * TILE, (barracks.center[1] + 0.4) * TILE))
    ticks(game)


@screen
def cancel_box(game: Game) -> None:
    """A box dragged in cancel mode over two of the three plans: drawn red, the two outlined, the hint counting them."""
    scene = cancel_town(game)
    drag_mouse(game, scene.camera.world_to_screen(8.4 * TILE, 10.4 * TILE), scene.camera.world_to_screen(14.6 * TILE, 13.6 * TILE))
    ticks(game)


for _controls in ("grid", "modal"):
    def _scheme_screen(game: Game, controls: str = _controls) -> None:
        """The card with this scheme's keys: a peasant's in Grid (Q W E / A S D / Z), the home Train catalogue in Modal."""
        scene = town(game, controls=controls)
        if controls == "grid":
            scene.select([spawn(scene, UnitType.PEASANT, (10, 12)).id])
        ticks(game)

    SCREENS[f"controls_{_controls}"] = _scheme_screen


@screen
def alerts(game: Game) -> None:
    scene = town(game)
    scene.warn("Not enough gold")
    scene.effects.add(Toast("Building lost", ["Your farm was destroyed"], hold=4.0, top=TOAST_TOP))
    scene.effects.add(Toast("Under attack", ["Your town hall is under attack"], hold=4.0, top=TOAST_TOP))
    ticks(game, 30)


@screen
def battle(game: Game) -> None:
    """Units of both sides among trees and buildings, for draw order."""
    scene = town(game, zoom=1.5)
    rng = random.Random(5)
    kinds = list(UnitType)
    for i in range(40):
        tile = (rng.randint(4, 30), rng.randint(3, 20))
        if scene.world.passable(*tile):
            spawn(scene, rng.choice(kinds), tile, player=i % 2)
    scene.camera.center_on(18 * TILE, 10 * TILE)
    ticks(game)


@screen
def battle_bars(game: Game) -> None:
    """The same fight with Alt held: every unit's health."""
    battle(game)
    game.scene.all_bars = True
    ticks(game)


@screen
def town_at_work(game: Game) -> None:
    """A damaged farm, a barracks training, a tower going up: health and progress told apart."""
    scene = town(game, zoom=1.5)
    world = scene.world
    farm = own(scene, BuildingType.FARM)
    farm.hp = farm.max_hp // 3
    world.players[scene.human].gold = world.players[scene.human].lumber = 5000
    world.train(own(scene, BuildingType.BARRACKS).id, UnitType.FOOTMAN)
    hall = own(scene, BuildingType.TOWN_HALL)
    site = world.place_building(scene.human, BuildingType.TOWER, (hall.x + 8, hall.y + 5), done=False)
    site.progress = site.info.build_time * 0.4
    scene.camera.center_on(*(c * TILE for c in own(scene, BuildingType.BARRACKS).center))
    ticks(game)


@screen
def commands_pips(game: Game) -> None:
    """The Commands row with a level on three buttons: Scout pressed three times, Withdraw twice, Gold once, each within
    the window another press would raise it in, and the status line saying what the last press did."""
    scene = town(game)
    for i in range(8):
        spawn(scene, UnitType.FOOTMAN if i % 2 else UnitType.KNIGHT, (26 + i % 4, 12 + i // 4))
    spawn(scene, UnitType.PEASANT, (10, 12))
    for command, times in (("scout", 3), ("withdraw", 2), ("gold", 1)):
        for _ in range(times):
            scene.command(command)
    ticks(game)


@screen
def commands_tags(game: Game) -> None:
    """Units at work for the side's commands, each tag over its unit's health bar: a flyer scouting, knights riding at
    the rival's workers, and a wounded footman walking home."""
    scene = town(game, zoom=1.5)
    flyer = spawn(scene, UnitType.FLYING_MACHINE, (14, 13))
    for i in range(3):
        spawn(scene, UnitType.KNIGHT, (17 + i, 14))
    footman = spawn(scene, UnitType.FOOTMAN, (15, 15))
    footman.hp = footman.max_hp // 3
    scene.world.update_vision()  # what they see is seen before the scout picks where to look
    scene.select([flyer.id])
    for command in ("scout", "harass", "withdraw"):
        scene.command(command)
    ticks(game, 12, 0.05)
    tagged = [scene.world.units[uid] for uid in scene.adjutant.tags]
    scene.camera.center_on(*(sum(c) / len(tagged) * TILE for c in zip(*(u.pos for u in tagged))))
    ticks(game)


@screen
def battle_wood(game: Game) -> None:
    scene = town(game, zoom=2.0)
    for i, tile in enumerate(((30, 2), (31, 3), (33, 2), (34, 4), (36, 3), (29, 5))):
        if scene.world.passable(*tile):
            spawn(scene, UnitType.FOOTMAN, tile, player=i % 2)
    scene.camera.center_on(33 * TILE, 5 * TILE)
    ticks(game)


@screen
def pause(game: Game) -> None:
    scene = town(game)
    game.push(PauseScene(scene))
    ticks(game)


@screen
def settings(game: Game) -> None:
    scene = town(game)
    game.push(SettingsScene(scene))
    ticks(game)


@screen
def save_browser(game: Game) -> None:
    scene = town(game)
    scene.save_to(2)
    scene.quick_save()
    game.push(SaveBrowserScene(game, "load", on_pick=lambda slot: None))
    ticks(game)


for _controls in SCHEMES:
    def _help(game: Game, controls: str = _controls) -> None:
        game.push(HelpScene(SCHEMES[controls]))
        ticks(game)

    SCREENS["help" if _controls == "classic" else f"help_{_controls}"] = _help


for _page in range(5):
    def _codex(game: Game, page: int = _page) -> None:
        scene = town(game, race=Race.DWARF)
        game.push(CodexScene(scene.world, scene.human, page))
        ticks(game)

    SCREENS[f"codex_{_page}"] = _codex


for _won in (True, False):
    def _game_over(game: Game, won: bool = _won) -> None:
        scene = match(game)
        ticks(game, 120)  # the opening banner has come and gone
        scene.world.resign(1 if won else scene.human)
        ticks(game)

    SCREENS[f"game_over_{'won' if _won else 'lost'}"] = _game_over


@screen
def high_scores(game: Game) -> None:
    game.push(HighScoreScene())
    ticks(game)


@screen
def high_scores_after_match(game: Game) -> None:
    scene = match(game)
    ticks(game, 120)
    scene.world.resign(1)
    ticks(game)
    game.scene.high_scores()
    ticks(game)


@screen
def campaign_fresh(game: Game) -> None:
    game.push(CampaignScene())
    ticks(game)


@screen
def campaign_under_way(game: Game) -> None:
    ProgressStore(game.data_dir).save(Progress(CAMPAIGN.id, Difficulty.HARD, completed=["hollowmere", "greywater"], flags={"truce": True}))
    game.push(CampaignScene())
    ticks(game)


def mission(game: Game, mission_id: str, flags: dict | None = None) -> MissionScene:
    """A campaign mission past its title banner, which the objectives panel waits for."""
    scene = MissionScene(CAMPAIGN, build_world(CAMPAIGN.mission(mission_id), flags=flags or {}), difficulty=Difficulty.MEDIUM, settings=None)
    game.push(scene)
    ticks(game, 30, 0.1)  # three seconds in tenths
    return scene


@screen
def mission_raid(game: Game) -> None:
    """Hollowmere's panel at its tallest, the raid's objectives shown and a notice hanging under it."""
    scene = mission(game, "hollowmere")
    world, hall = scene.world, scene.run.hall(0)
    world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
    world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
    for i in range(4):
        world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
    ticks(game, 12)
    game.scene.skip()  # Aldric's warning
    ticks(game, 40)


@screen
def mission_choice(game: Game) -> None:
    scene = mission(game, "karst_hold")
    game.push(DialogScene(scene.mission.debrief[2:], CAMPAIGN.speakers, scene.run.vars))
    ticks(game)


@screen
def mission_result(game: Game) -> None:
    scene = mission(game, "court_of_thorns")
    scene.run.state.update(court="done", orcs="done")
    game.push(MissionResultScene(scene, won=True))
    ticks(game)


# -- Running ----------------------------------------------------------------------------


def run_screen(name: str, resolution: tuple[int, int], evidence: Path | None) -> list[lint.Finding]:
    """Play *name* on a mock game and lint what it drew; with *evidence*, render it through pyglet too."""
    with tempfile.TemporaryDirectory(prefix="warband-lint-") as scratch:
        game = Game("Warband lint", backend="mock", resolution=resolution, theme=build_theme(), save_dir=Path(scratch) / "mock" / "saves")
        try:
            lint.use_real_text_metrics(game)
            store = lint.ImageStore(game)
            SCREENS[name](game)
            findings = lint.lint_frame(game, store)
        finally:
            game.close()
        if evidence is not None:
            game = Game("Warband lint", backend="pyglet", resolution=resolution, visible=False, theme=build_theme(), save_dir=Path(scratch) / "native" / "saves")
            try:
                fonts.load(game)
                SCREENS[name](game)
                findings += [lint.Finding(f.check, f"native {f.subject}", f.detail)
                             for f in lint.lint_layout(game, game.scene)]
                frame = game.backend.capture_frame()
            finally:
                game.close()
            frame.save(evidence / f"{name}_{resolution[0]}x{resolution[1]}.png")
            findings += lint.lint_pixels(name, frame)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--screens", default="", help="run only the screens whose name contains one of these (comma-separated)")
    parser.add_argument("--no-images", action="store_true", help="skip the checks on the registered art")
    parser.add_argument("--no-screens", action="store_true", help="skip the screens")
    parser.add_argument("--evidence", type=Path, help="write PNGs of flagged sprites and of every screen here")
    parser.add_argument("--list", action="store_true", help="print the screen names and exit")
    parser.add_argument("--cpu-percent", type=float, default=25, help="cooperative CPU budget (default: 25%% of one core)")
    args = parser.parse_args()
    if args.list:
        print("\n".join(SCREENS))
        return
    if args.evidence is not None:
        args.evidence.mkdir(parents=True, exist_ok=True)
    budget = CpuBudget(args.cpu_percent)
    total: collections.Counter[str] = collections.Counter()
    if not args.no_images:
        with tempfile.TemporaryDirectory(prefix="warband-lint-art-") as scratch:
            game = Game("Warband lint", backend="mock", resolution=RESOLUTIONS[0], theme=build_theme(), save_dir=Path(scratch) / "saves")
            try:
                store = lint.ImageStore(game)
                lint.register_everything(game, budget=budget)
                findings = lint.lint_images(game, store, budget=budget)
                image_count = len(store.by_handle)
            finally:
                game.close()
        print(f"images: {image_count} registered, {len(findings)} findings")
        for finding in findings:
            print(f"  {finding}")
        total.update(f.check for f in findings)
        if args.evidence is not None:
            lint.save_evidence(findings, args.evidence / "images")
    if not args.no_screens:
        wanted = args.screens.split(",")
        names = [name for name in SCREENS if any(part in name for part in wanted)]
        for resolution in RESOLUTIONS:
            for name in names:
                findings = run_screen(name, resolution, args.evidence)
                print(f"{name} @ {resolution[0]}x{resolution[1]}: {len(findings)} findings")
                for finding in findings:
                    print(f"  {finding}")
                total.update(f.check for f in findings)
                budget.checkpoint()
    print("totals:", ", ".join(f"{check} {count}" for check, count in sorted(total.items())) or "nothing found")


if __name__ == "__main__":
    main()
