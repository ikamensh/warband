"""Capture blows landing, natively, and lay the frames out to look at.

    uv run python tools/verify_hits.py docs/evidence/blood/after
    uv run python tools/verify_hits.py docs/evidence/blood/after-near --zoom 2

A knight's blow on a footman, an arrow on a peasant, a blow on a catapult: frames every two display
frames for half a second from the blow; and a crowded fight at normal zoom. Builds on tools/verify_deaths.py.
The display must be awake (``caffeinate -u``). No real player data is read or written.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_deaths import Capture, field, montage  # noqa: E402

from warband.effects import Spray  # noqa: E402
from warband.rules import UnitType  # noqa: E402

BLOWS = {"melee": (UnitType.KNIGHT, UnitType.FOOTMAN, 1.3), "arrow": (UnitType.ARCHER, UnitType.PEASANT, 6.0),
         "siege": (UnitType.KNIGHT, UnitType.CATAPULT, 1.3)}


class Hits(Capture):
    def blow(self, name: str) -> "Image":
        striker_type, victim_type, distance = BLOWS[name]
        world = field()
        victim = world.spawn_unit(1, victim_type, (20.5, 12.5))
        victim.hp = victim.max_hp = 500
        striker = world.spawn_unit(0, striker_type, (20.5 - distance, 12.5))
        scene = self.scene(world, (20.5, 12.5))
        world.attack([striker.id], victim.id)
        for _ in range(60 * 6):
            self.game.tick(1 / 60)
            if any(isinstance(e, Spray) for e in scene.effects._items):
                break
        else:
            raise RuntimeError(f"{name}: no blow landed")
        cells = []
        for _ in range(14):
            cells.append(self.around(scene, (20.5, 12.5)))
            for _ in range(2):
                self.game.tick(1 / 60)
        self.game.pop()
        self.game.tick(1 / 60)
        return montage(cells, 7)

    def crowd(self) -> "Image":
        world = field()
        for row in range(4):
            for col in range(4):
                world.spawn_unit(1, UnitType.FOOTMAN, (19.5 + col * 0.9, 10.5 + row * 0.9))
                world.spawn_unit(0, UnitType.FOOTMAN, (14.5 + col * 0.9, 10.5 + row * 0.9))
        scene = self.scene(world, (18.0, 12.0))
        world.attack_move([u.id for u in world.player_units(0)], (21.0, 12.0))
        world.attack_move([u.id for u in world.player_units(1)], (15.0, 12.0))
        cells, elapsed = [], 0.0
        for seconds in (2.0, 3.0, 4.5, 6.0, 8.0, 12.0):
            while elapsed < seconds:
                self.game.tick(1 / 60)
                elapsed += 1 / 60
            frame = self.frame()
            sx, sy = scene.camera.world_to_screen(18.0 * 32, 12.0 * 32)
            cells.append(frame.crop((round(sx - 260), round(sy - 200), round(sx + 260), round(sy + 190))))
        self.game.pop()
        self.game.tick(1 / 60)
        return montage(cells, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--zoom", type=float, default=1.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    capture = Hits(args.output, args.zoom)
    try:
        for name in BLOWS:
            capture.blow(name).save(args.output / f"{name}.png")
            print(f"{name}: {args.output / f'{name}.png'}")
        capture.crowd().save(args.output / "crowd.png")
        print(f"crowd: {args.output / 'crowd.png'}")
    finally:
        capture.close()


if __name__ == "__main__":
    main()
