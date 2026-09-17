"""Find visual defects automatically: the registered art, and every screen of the game.

    uv run python tools/visual_lint.py                     # everything, findings on stdout
    uv run python tools/visual_lint.py --screens select    # only the screens whose name contains "select"
    uv run python tools/visual_lint.py --evidence DIR      # also write PNGs: each flagged sprite, each screen (pyglet)
    uv run python tools/visual_lint.py --no-images         # skip the art checks (about a minute)

The checks live in :mod:`warband.visual_lint`; this walks the game's screens
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
from warband import visual_lint as lint  # noqa: E402
from warband.model import World, tile_center  # noqa: E402
from warband.rules import BuildingType, Race, Terrain, UnitType, Upgrade  # noqa: E402
from warband.scene import TOAST_TOP, CodexScene, GameScene, HelpScene, PauseScene, SaveBrowserScene, SettingsScene, new_game  # noqa: E402
from warband.score_scene import HighScoreScene  # noqa: E402
from warband.style import build_theme  # noqa: E402
from warband.textures import TILE  # noqa: E402
from warband.title import TitleScene  # noqa: E402

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
    world.place_building(None, BuildingType.GOLD_MINE, (32, 17))
    world.place_building(1, BuildingType.TOWN_HALL, (43, 30))
    world.update_vision()
    world.reveal_all(0)
    return world


def match(game: Game, *, seed: int = 3, settings: dict | None = None, **kwargs) -> GameScene:
    scene = new_game(seed=seed, settings=settings, **kwargs)
    game.push(scene)
    ticks(game)
    return scene


def town(game: Game, *, race: Race = Race.HUMAN, zoom: float = 1.0) -> GameScene:
    """The settlement, banner gone, camera on the buildings."""
    world = settlement()
    world.players[0].race = race
    scene = GameScene(world, 17, settings=dict(QUIET))
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
def match_start(game: Game) -> None:
    match(game)
    ticks(game, 30)  # the banner has slid in and holds


@screen
def match_tutorial(game: Game) -> None:
    scene = match(game)
    ticks(game, 60, 0.1)
    scene.say("Peasants gather and build on their own; plan the settlement with B, T and U")
    ticks(game)


for _unit in UnitType:
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


for _building in BuildingType:
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
        scene.toggle_settlement(menu)
        ticks(game)

    SCREENS[f"menu_{_menu}"] = _menu_screen


@screen
def menu_build_hover(game: Game) -> None:
    scene = town(game)
    scene.toggle_settlement("build")
    ticks(game)
    button = next(c for c in scene.card_panel.walk() if hasattr(c, "hotkey") or type(c).__name__ == "ProductionButton")
    x, y, w, h = button.bounds
    move_mouse(game, x + w / 2, y + h / 2)
    ticks(game)


@screen
def plans(game: Game) -> None:
    scene = town(game)
    scene.place_plan(BuildingType.FARM, (12.5, 11.5))
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
    scene.start_pending("build:farm")
    move_mouse(game, *scene.camera.world_to_screen(13 * TILE, 12 * TILE))
    ticks(game)


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


@screen
def help(game: Game) -> None:
    game.push(HelpScene())
    ticks(game)


for _page in range(4):
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
