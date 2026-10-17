"""Capture staged, playable Warband scenes with the release's real pyglet renderer.

    SAGA2D_SILENT=1 python tools/capture_storefront.py OUTPUT

The scenes use genuine units, buildings, orders, spells and campaign dialogue.
Only setup, resources, visibility and camera composition are staged. No pixels,
UI, unit models or effects are composited or added after capture. Player data
is isolated in a temporary directory. Keep the display awake with caffeinate.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["SAGA2D_SILENT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d import Game, fonts
from saga2d.testing.native_frames import tick
from warband.sim.model import Unit, World
from warband.sim.rules import BuildingType as B, MapTheme, Race, Terrain as T, UnitType as U, Upgrade
from warband.ui.scene import GameScene
from warband.ui.style import build_theme

SPECIAL_UNITS = {Race.HUMAN: U.GRYPHON, Race.DWARF: U.RUNE_GOLEM, Race.ELF: U.TREANT, Race.ORC: U.SAPPER}
SETTINGS = {"music": 0.0, "sfx": 0.0, "tutorial": False, "edge_scroll": False, "controls": "modal"}


def landscape(theme: MapTheme, races: tuple[Race, Race], seed: int) -> World:
    rng = random.Random(seed)
    w, h = 52, 38
    ground = [[T.GRASS] * w for _ in range(h)]
    # Irregular natural edges frame the playable centre. Open roads stay clear.
    for y in range(h):
        for x in range(w):
            if (y < 6 or x < 3 or x > 47 or y > 32) and rng.random() < .68:
                ground[y][x] = T.TREES
            if x > 43 and 7 < y < 29:
                ground[y][x] = T.WATER
    for x, y in ((5, 7), (40, 6), (39, 28), (8, 30), (43, 31)):
        ground[y][x] = T.ROCK
    world = World(w, h, ground, 2, theme=theme, races=races, rng=rng, magic=True)
    for player in world.players[:world.seats]:
        player.human = True
        player.gold, player.lumber = 780, 460
    return world


def huts(world: World, seat: int, positions: list[tuple[int, int]]) -> None:
    for point in positions:
        world.place_building(seat, B.FARM, point)


def army(world: World, seat: int, types: list[U], origin: tuple[float, float], columns: int = 6) -> list[Unit]:
    return [world.spawn_unit(seat, kind, (origin[0] + (i % columns) * .85, origin[1] + (i // columns) * .86))
            for i, kind in enumerate(types)]


def base_world(race: Race, theme: MapTheme, seed: int) -> tuple[World, list[Unit]]:
    world = landscape(theme, (race, Race.ORC if race is not Race.ORC else Race.HUMAN), seed)
    for kind, point in ((B.TOWN_HALL, (14, 10)), (B.BARRACKS, (20, 10)), (B.LUMBER_MILL, (27, 7)),
                        (B.BLACKSMITH, (20, 17)), (B.STABLES, (25, 17)), (B.CHURCH, (8, 17)),
                        (B.TOWER, (31, 13)), (B.MAGE_TOWER, (8, 10))):
        world.place_building(0, kind, point)
    huts(world, 0, [(9, 7), (12, 7), (17, 7), (9, 24), (12, 24), (15, 24), (18, 24), (21, 24)])
    world.place_building(1, B.TOWN_HALL, (39, 29))
    mine = world.place_building(None, B.GOLD_MINE, (33, 18))
    world.lay_rifts([(6, 13)])
    world.place_building(0, B.VAULT, (6, 13))
    world.players[0].upgrades.update({Upgrade.KEEP, Upgrade.MEND, Upgrade.STONESKIN, Upgrade.SUMMON})
    world.players[0].aether = 135
    miners = army(world, 0, [U.PEASANT] * 6, (29.7, 21), columns=3)
    world.harvest([u.id for u in miners], mine.id)
    for i in range(6):
        target = (25 + i, 5)
        world.navigation.set_terrain(target, T.TREES)
        worker = world.spawn_unit(0, U.PEASANT, (target[0] + .5, 6.4))
        world.harvest([worker.id], target)
    special = SPECIAL_UNITS[race]
    band = army(world, 0, [U.FOOTMAN] * 6 + [U.ARCHER] * 4 + [U.KNIGHT] * 3 + [U.CLERIC] * 2 + [special] * 2,
                (16.5, 14), columns=8)
    world.hold([u.id for u in band])
    for u in band:
        u.facing = math.pi / 2
    world.update_vision()
    world.reveal_all(0)
    return world, band


def battle_world(theme=MapTheme.SUMMER, races=(Race.HUMAN, Race.ORC), seed=71) -> tuple[World, list[Unit]]:
    world = landscape(theme, races, seed)
    world.place_building(0, B.TOWN_HALL, (7, 12))
    world.place_building(0, B.BARRACKS, (11, 6))
    world.place_building(0, B.TOWER, (15, 9))
    world.place_building(0, B.CHURCH, (8, 21))
    world.place_building(1, B.TOWN_HALL, (36, 12))
    world.place_building(1, B.BARRACKS, (33, 6))
    world.place_building(1, B.TOWER, (31, 10))
    world.place_building(1, B.WORKSHOP, (34, 21))
    huts(world, 0, [(4, 7), (7, 7), (4, 21), (5, 26), (8, 26), (11, 26), (14, 26), (17, 26)])
    huts(world, 1, [(37, 7), (40, 7), (38, 21), (28, 26), (31, 26), (34, 26), (37, 26), (40, 26)])
    own_special = SPECIAL_UNITS[races[0]]
    enemy_special = SPECIAL_UNITS[races[1]]
    own = []
    foes = []
    for seat, band, x, direction, special in ((0, own, 22.1, -1, own_special), (1, foes, 26.1, 1, enemy_special)):
        for i, kind in enumerate([U.FOOTMAN] * 6 + [U.KNIGHT] * 3):
            point = (x + (i % 2) * direction * .75 + world.rng.uniform(-.6, .6),
                     10.4 + i * 1.05 + world.rng.uniform(-.22, .22))
            band.append(world.spawn_unit(seat, kind, point))
        for i, kind in enumerate([U.ARCHER] * 5 + [U.CLERIC] * 2 + [U.CATAPULT] * 2 + [special] * 2):
            band.append(world.spawn_unit(seat, kind, (x + direction * (2.4 + (i % 2) * 1.3), 10.8 + i * .81)))
    world.attack_move([u.id for u in own], (28, 15))
    world.attack_move([u.id for u in foes], (20, 15))
    world.lay_rifts([(12, 19), (30, 19)])
    world.place_building(0, B.VAULT, (12, 19))
    world.place_building(1, B.VAULT, (30, 19))
    world.place_building(0, B.MAGE_TOWER, (15, 21))
    world.place_building(1, B.MAGE_TOWER, (29, 21))
    for player in world.players[:2]:
        player.upgrades.update({Upgrade.KEEP, Upgrade.FLAME_STRIKE, Upgrade.STONESKIN, Upgrade.SUMMON})
        player.aether = 150
    world.update_vision()
    world.reveal_all(0)
    return world, own


def main(out: Path, animation_only: bool = False):
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-storefront-data-") as profile:
        game = Game("Warband storefront", resolution=(1600, 1000), backend="pyglet", visible=False,
                    save_dir=Path(profile) / "saves", theme=build_theme())
        fonts.load(game)

        def frames(count: int):
            for _ in range(count):
                tick(game, 1 / 60)

        def scene_for(world, band, centre, zoom):
            scene = GameScene(world, 71, settings=dict(SETTINGS), ranked=False, autosave=False)
            game.clear_and_push(scene)
            scene.execution.paused = True
            frames(210)
            scene.camera.zoom = zoom
            scene.camera.center_on(centre[0] * 32, centre[1] * 32)
            scene.select([u.id for u in band[:8]])
            frames(2)
            return scene

        def shot(name):
            frames(2)
            path = out / f"{name}.png"
            game.backend.capture_frame().resize((1600, 1000)).save(path)
            print(path.resolve(), flush=True)

        try:
            if not animation_only:
                world, band = base_world(Race.HUMAN, MapTheme.SUMMER, 17)
                scene = scene_for(world, band, (21, 14.2), 1.28)
                scene.select([world.player_buildings(0, B.TOWN_HALL)[0].id])
                scene.execution.paused = False
                frames(64)
                shot("01-build-your-kingdom")

            world, band = battle_world()
            scene = scene_for(world, band, (24, 15.5), 1.3)
            scene.execution.paused = False
            frames(176)
            if not animation_only:
                shot("02-armies-collide")
            else:
                frames(2)
            world.players[0].aether = 150
            world.cast(0, Upgrade.FLAME_STRIKE, (25.5, 14.2))
            frames(8)
            if not animation_only:
                shot("03-command-the-aether")
            else:
                frames(2)

            # A native sequence of this same battle, sampled at twelve frames a second.
            from PIL import Image
            scene.camera.center_on(24 * 32, 14.2 * 32)
            animation = []
            for _ in range(36):
                frames(5)
                capture = game.backend.capture_frame().convert("RGB")
                scale = game.backend.scale_factor
                # A crop of the actual battlefield: no HUD or composited overlay.
                crop = capture.crop(tuple(round(v * scale) for v in (350, 238, 1200, 769)))
                animation.append(crop.resize((960, 600), Image.Resampling.LANCZOS).quantize(colors=128))
            animation[0].save(out / "warband-battle.gif", save_all=True, append_images=animation[1:], duration=[80, 80, 90] * 12, loop=0, optimize=True)
            print((out / "warband-battle.gif").resolve(), flush=True)

            if animation_only:
                return

            world, band = battle_world(MapTheme.WINTER, (Race.DWARF, Race.ORC), 29)
            scene = scene_for(world, band, (23.5, 15.5), 1.25)
            scene.execution.paused = False
            frames(84)
            shot("04-dwarven-winter")

            from warband.story.campaign import Progress
            from warband.story.catalog import DEFAULT_CAMPAIGN
            from warband.story.mission_scene import start_mission
            from warband.story.dialog import DialogScene
            from warband.sim.rules import Difficulty
            campaign = DEFAULT_CAMPAIGN
            mission = campaign.missions[0]
            start_mission(game, campaign, mission, Progress(campaign.id, Difficulty.MEDIUM), None)
            frames(3)
            dialog = game.scene
            assert isinstance(dialog, DialogScene)
            dialog.advance()
            frames(45)
            shot("06-the-undertow-campaign")
        finally:
            game.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--animation-only", action="store_true", help="regenerate only the cropped gameplay GIF")
    args = parser.parse_args()
    main(args.out, args.animation_only)
