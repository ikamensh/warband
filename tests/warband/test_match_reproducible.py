"""A seed is a match: what the player looks at, and how it is dressed up, never moves the computer players.

The brains draw from the scene's random stream (where to build, give or take).  Sparks, blood and dust
once drew from the same stream, so a fight in view, or the Blood setting, sent the rest of the match
down another road, and a seed from a bug report did not reproduce it.
"""

import pytest

from saga2d import Game
from warband.replay import digest
from warband.rules import BuildingType, UnitType
from warband.scene import new_game
from warband.style import build_theme


def played(blood: bool, seconds: float = 100.0) -> tuple[str, int]:
    """Seed 5 with a skirmish at the player's gates from the first second; the digest of where it stands later."""
    game = Game("Warband Seed", backend="mock", resolution=(1280, 800), theme=build_theme())
    try:
        scene = new_game(seed=5)
        scene.settings["blood"] = blood
        game.push(scene)
        world = scene.world
        rival = next(p.id for p in world.players if p.id != scene.human)
        hall = world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]
        for i in range(3):  # a fight the player watches: every blow throws sparks, blood and dust
            world.spawn_unit(rival, UnitType.FOOTMAN, (hall.x - 1.5, hall.y + 0.5 + i))
            world.spawn_unit(scene.human, UnitType.FOOTMAN, (hall.x - 2.5, hall.y + 0.5 + i))
        shown = 0
        while world.time < seconds:
            game.tick(0.25)
            shown = max(shown, len(scene.effects))
        return digest(world), shown
    finally:
        game.close()


@pytest.mark.slow
def test_the_blood_setting_and_the_effects_in_view_leave_the_match_alone() -> None:
    """It plays a hundred seconds of a skirmish twice, about six seconds: the slow tier. The fast tier's replay
    tests check that a match reproduces."""
    with_blood, shown = played(True)
    without, _ = played(False)
    assert shown > 0, "the skirmish threw no effects: the test watches nothing"
    assert with_blood == without, "the same seed played out differently once the effects drew from the brains' random stream"
