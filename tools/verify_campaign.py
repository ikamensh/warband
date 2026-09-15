"""The campaign's screens rendered by the real backend, to look at.

    uv run python tools/verify_campaign.py DIR

Title with the Campaign entry, the campaign screen fresh and under way, a briefing, the first mission with its
objectives, Aldric's warning when the raid comes, a question with answers, the mission result.  Saves and progress
go to a temporary data directory, never the player's.  The display must be awake (``caffeinate -u -t 3``).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saga2d import Game, fonts  # noqa: E402
from warband.campaign_scene import CampaignScene  # noqa: E402
from warband.dialog import DialogScene  # noqa: E402
from warband.mission_scene import MissionResultScene, MissionScene  # noqa: E402
from warband.missions import CAMPAIGN  # noqa: E402
from warband.model import tile_center  # noqa: E402
from warband.rules import BuildingType, UnitType  # noqa: E402
from warband.style import build_theme  # noqa: E402
from warband.title import TitleScene  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-campaign-") as temp:
        game = Game("Warband campaign verify", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme(),
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
            shot("05-mission-hollowmere")
            world, hall = scene.world, scene.run.hall(0)
            world.place_building(0, BuildingType.FARM, (hall.x + 5, hall.y + 5))
            world.place_building(0, BuildingType.BARRACKS, (hall.x + 5, hall.y - 1))
            for i in range(4):
                world.spawn_unit(0, UnitType.FOOTMAN, tile_center((hall.x + i, hall.y + 4)))
            frames(12)
            assert isinstance(game.scene, DialogScene)
            shot("06-mission-dialogue")
            game.scene.advance()
            frames(30)
            shot("07-mission-raid")
            karst = CAMPAIGN.mission("karst_hold")
            game.push(DialogScene(karst.debrief[2:], CAMPAIGN.speakers, {}))
            frames(3)
            shot("08-choice")
            game.scene.choose(True)
            frames(2)
            game.scene.skip()
            frames(2)
            for building in world.player_buildings(1):
                building.hp = 0
            frames(12)
            assert isinstance(game.scene, MissionResultScene)
            shot("09-result")
            game.scene.proceed()
            frames(3)
            game.scene.skip()
            frames(3)
            assert isinstance(game.scene, CampaignScene)
            shot("10-campaign-under-way")
        finally:
            game.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/evidence/campaign"))
