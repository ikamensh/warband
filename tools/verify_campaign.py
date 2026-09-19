"""The campaign's screens rendered by the real backend, to look at.

    uv run python tools/verify_campaign.py DIR [--size 1200x680]

Title with the Campaign entry, the campaign screen fresh and under way, a briefing, the first mission with its
objectives, Aldric's warning when the raid comes, a question with answers, the mission result.  Then every mission's
opening as the player sees it, and beside it a map of the whole mission drawn from the model, which the fog does not
hide (``NN-<mission>-map.png``: terrain, each side's buildings and units in its colour, the gold mines in gold, and a
white cross on every point the setup stored for its script).  Saves and progress go to a temporary data directory,
never the player's.  The display must be awake (``caffeinate -u -t 3``).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from warband.story.campaign_scene import CampaignScene  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.campaign import Run  # noqa: E402
from warband.story.mission_scene import MissionResultScene, MissionScene, build_world  # noqa: E402
from warband.story.missions import CAMPAIGN  # noqa: E402
from warband.sim.model import tile_center  # noqa: E402
from warband.sim.rules import PLAYERS, BuildingType, Difficulty, Terrain, UnitType  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from warband.ui.title import TitleScene  # noqa: E402


TERRAIN_COLORS = {Terrain.GRASS: (74, 112, 52), Terrain.TREES: (24, 58, 30), Terrain.WATER: (40, 84, 150), Terrain.ROCK: (112, 106, 100)}
FLAGS = {"truce": False, "powder": True}  # the choices that put the most on the later maps: the orcs at war, the siege train


def mission_map(run: Run, path: Path, scale: int = 8) -> None:
    """The whole mission as the model has it after its setup, fog or no fog."""
    world = run.world
    image = Image.new("RGB", (world.width * scale, world.height * scale))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(world.terrain):
        for x, terrain in enumerate(row):
            draw.rectangle((x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=TERRAIN_COLORS[terrain])
    for building in world.buildings.values():
        color = (235, 200, 60) if building.player is None else PLAYERS[building.player].color
        draw.rectangle((building.x * scale, building.y * scale, (building.x + building.size) * scale - 1, (building.y + building.size) * scale - 1),
                       fill=color, outline=(0, 0, 0))
    radius = scale * 0.4
    for unit in world.units.values():
        if not unit.hidden:
            draw.ellipse((unit.x * scale - radius, unit.y * scale - radius, unit.x * scale + radius, unit.y * scale + radius),
                         fill=PLAYERS[unit.player].color, outline=(255, 255, 255))
    for value in run.vars.values():
        if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
            x, y = value[0] * scale, value[1] * scale
            draw.line((x - scale, y - scale, x + scale, y + scale), fill=(255, 255, 255), width=2)
            draw.line((x - scale, y + scale, x + scale, y - scale), fill=(255, 255, 255), width=2)
    image.save(path)
    print(f"saved {path}")


def main(out: Path, size: tuple[int, int]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-campaign-") as temp:
        game = Game("Warband campaign verify", resolution=size, backend="pyglet", visible=False, theme=build_theme(),
                    save_dir=Path(temp) / "saves")
        fonts.load(game)

        def frames(n: int) -> None:
            for _ in range(n):
                game.tick(1 / 60)

        def shot(name: str) -> None:
            frames(2)
            path = out / f"{name}.png"
            game.backend.capture_frame().save(path)
            print(f"saved {path}")

        try:
            game.push(TitleScene())
            frames(3)
            shot("01-title")
            game.scene.campaign()
            frames(3)
            assert isinstance(game.scene, CampaignScene)
            shot("02-campaign-fresh")
            game.scene.continue_campaign()
            frames(3)
            assert isinstance(game.scene, DialogScene)
            shot("03-briefing")
            game.scene.advance()
            frames(2)
            shot("04-briefing-aldric")
            game.scene.skip()
            frames(40)
            scene = game.scene
            assert isinstance(scene, MissionScene)
            shot("05-mission-banner")
            frames(130)  # the banner passes; the objectives panel comes in
            shot("06-mission-objectives")
            world, hall = scene.world, scene.run.hall(0)
            world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
            world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
            for i in range(4):
                world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
            frames(12)
            assert isinstance(game.scene, DialogScene)
            shot("07-mission-dialogue")
            game.scene.advance()
            frames(30)
            shot("08-mission-raid")
            karst = CAMPAIGN.mission("karst_hold")
            game.push(DialogScene(karst.debrief[2:], CAMPAIGN.speakers, {}))
            frames(3)
            shot("09-choice")
            game.scene.choose(True)
            frames(2)
            game.scene.skip()
            frames(2)
            for building in world.player_buildings(1):
                building.hp = 0
            frames(12)
            assert isinstance(game.scene, MissionResultScene)
            shot("10-result")
            game.scene.proceed()
            frames(3)
            game.scene.skip()
            frames(3)
            assert isinstance(game.scene, CampaignScene)
            shot("11-campaign-under-way")
            for number, mission in enumerate(CAMPAIGN.missions, start=12):
                run = build_world(mission, flags=FLAGS)
                mission_map(run, out / f"{number}-{mission.id}-map.png")
                game.clear_and_push(MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM))
                frames(180)  # past the mission's banner (2.7 s)
                shot(f"{number}-{mission.id}")
        finally:
            game.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", nargs="?", type=Path, default=Path("docs/evidence/campaign"))
    parser.add_argument("--size", default="1280x800", help="the window, WIDTHxHEIGHT")
    args = parser.parse_args()
    width, height = (int(n) for n in args.size.split("x"))
    main(args.out, (width, height))
