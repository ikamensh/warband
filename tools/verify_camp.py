"""Render a creature camp through the real backend and save the frames to look at.

    uv run python tools/verify_camp.py docs/evidence/camps

Five pictures, each of something the design has to get right on screen rather than in a table:

``camp.png``       a camp as a player first meets it: the den, its guards standing at their posts,
                   and the deposit it guards, at the real game zoom.
``approach.png``   the same camp with an army walking up to it, so the sizes can be compared.
``fight.png``      the camp roused: every guard at the intruder at once.
``card-<kind>.png`` the selection card for each creature, which now carries the armour class line --
                   the teaching surface for the whole design (a troll reads *No armour*, which is
                   why the archer is its answer).
``card-lair.png``  the den's own card.

The display must be awake (``caffeinate -u``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d import Game, fonts  # noqa: E402
from warband.sim import camps, mapgen  # noqa: E402
from warband.sim.model import tile_center  # noqa: E402
from warband.sim.rules import BuildingType, UnitType  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

SEED = 9
SIZE = (64, 48)


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    world = mapgen.generate(SEED, *SIZE, players=2, human=0)
    if not world.camps:
        print(f"seed {SEED} drew no camps; nothing to look at")
        return 1
    game = Game("Warband camps", resolution=(1280, 800), backend="pyglet", visible=False, theme=build_theme())
    fonts.load(game)
    scene = GameScene(world, seed=SEED, settings={"tutorial": False, "music": 0.0, "sfx": 0.0})
    game.push(scene)

    def frames(n: int) -> None:
        for _ in range(n):
            game.tick(1 / 60)

    def shot(name: str) -> None:
        frames(3)
        game.backend.capture_frame().save(out / f"{name}.png")
        print(f"  {name}.png")

    camp = min(world.camps, key=lambda c: world.buildings[c.lair].center[1])
    lair = world.buildings[camp.lair]
    scene.view.reveal = True  # the camp as a picture, not as the fog happens to leave it
    world.reveal_all(0)
    frames(180)  # the match's opening banner has its say before the map is worth looking at
    scene.hide_tutorial()
    scene.camera.zoom = 1.6
    scene.camera.center_on(lair.center[0] * 32, lair.center[1] * 32)
    frames(10)
    shot("camp")

    # An army walks up: the same frame with something of the player's beside the guards, for scale.
    squad = [world.spawn_unit(0, kind, (lair.center[0] - 7.0 + i * 0.9, lair.center[1] + 6.0))
             for i, kind in enumerate((UnitType.FOOTMAN, UnitType.FOOTMAN, UnitType.ARCHER, UnitType.ARCHER,
                                       UnitType.KNIGHT, UnitType.CATAPULT))]
    scene.camera.center_on(lair.center[0] * 32, lair.center[1] * 32)
    frames(20)
    shot("approach")

    world.attack_move([u.id for u in squad], lair.center)
    for _ in range(60):
        frames(6)
        if any(guard.state == "attack" for guard in camps.guards(world, camp)):
            break
    frames(20)
    fight = [u for u in world.units.values() if u.hp > 0 and u.state == "attack"] or squad
    scene.camera.center_on(sum(u.x for u in fight) / len(fight) * 32, sum(u.y for u in fight) / len(fight) * 32)
    frames(4)
    shot("fight")

    # The big camp is a troll, a golem and two spiders: it guards the endless seam, which only the larger
    # maps carry, so it is staged here rather than hunted for on a seed.
    den = camps.place(world, (lair.x, lair.y + 12), [UnitType.TROLL, UnitType.GOLEM, UnitType.SPIDER, UnitType.SPIDER], 1500)
    biggest = world.buildings[den.lair]
    scene.camera.center_on(biggest.center[0] * 32, biggest.center[1] * 32)
    frames(10)
    shot("lair")

    for kind in sorted({guard.type for guard in camps.guards(world, camp) + camps.guards(world, den)}
                       | {u.type for u in squad if u.hp > 0},
                       key=lambda t: t.value):
        alive = next((u for u in world.units.values() if u.type is kind and u.hp > 0), None)
        if alive is not None:
            scene.select([alive.id], quiet=True)
            shot(f"card-{kind.value}")
    scene.select([lair.id], quiet=True)
    shot("card-lair")
    game.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    raise SystemExit(main(parser.parse_args().out))
