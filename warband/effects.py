"""Warband's own transient effects on top of :mod:`saga2d.effects`."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from saga2d.effects import Effect
from saga2d.rendering import Sprite
from saga2d.scene import Scene
from warband.rules import UnitType
from warband.textures import MOUNTED, placements

Point = tuple[float, float]


@dataclass(frozen=True)
class Outcome:
    """How a category of unit goes down: how far it turns (degrees), how much of its height is left lying,
    and how far the landing bounces (degrees)."""

    turn: float
    height: float
    bounce: float


OUTCOMES = {
    "topple": Outcome(88, .78, 7),    # infantry, archers, casters: over onto the ground
    "collapse": Outcome(36, .58, 4),  # a mount folds into a low heap; a plank on its nose is no horse
    "wreck": Outcome(9, .66, 2),      # a siege engine breaks where it stands
}


def death_outcome(unit_type: UnitType) -> str:
    if unit_type is UnitType.CATAPULT:
        return "wreck"
    return "collapse" if unit_type in MOUNTED else "topple"


class UnitDeath(Effect):
    """A killed unit goes down where it stood, away from the blow, and lies there a while.

    A lurch with the blow, a fall that speeds up like gravity, a landing that bounces and settles (the scene
    drops dust there through *on_land*), then the body lies darkened until it fades.  The feet stay on the
    death point: atlas cells include padding below the feet, and compensating the centre-based sprite rotation
    keeps the pivot there instead of spinning the body in mid-air.
    """

    LURCH = .12
    FALL = .32
    SETTLE = .14
    DOWN = LURCH + FALL + SETTLE  # lying still from here on
    HOLD = 5.0
    FADE = 1.8
    BODIES = 48  # lying at once; past that the oldest fade early

    def __init__(self, sprite: Sprite, position: Point, *, source: Point | None = None, outcome: str = "topple",
                 on_land: Callable[[Point, str], None] | None = None) -> None:
        super().__init__(self.DOWN + self.HOLD + self.FADE)
        self.sprite, self.position, self.outcome, self.on_land = sprite, position, OUTCOMES[outcome], on_land
        self.kind = outcome
        self.size = sprite.size
        self.rotation, self.tint = sprite.rotation, sprite.tint
        angle = math.radians(self.rotation)
        self.drop = placements[sprite.image].drop  # the feet lie this far above the image's bottom edge
        pivot = self.size[1] / 2 - self.drop
        self.stood = (sprite.x - math.sin(angle) * pivot, sprite.y - self.size[1] / 2 + math.cos(angle) * pivot)  # the feet now
        dx = position[0] - source[0] if source is not None else 1.0
        self.turn = self.outcome.turn if dx >= 0 else -self.outcome.turn  # away from the blow
        self.landed = False
        self.hurried = False
        self.feet = self.stood

    def hurry(self) -> None:
        """Fade as soon as the body lies still: room is needed for newer bodies."""
        self.hurried = True

    def advance(self) -> None:
        if self.sprite.is_removed:
            self.cancelled = True
            return
        age = self.elapsed
        turn, height, bounce = self.turn, self.outcome.height, self.outcome.bounce
        if age < self.LURCH:  # the blow itself: the body is knocked over the feet, the feet settle onto the death point
            q = age / self.LURCH
            rotation, sy, dark = turn * .12 * q, 1 - .05 * q, .15 * q
        elif age < self.LURCH + self.FALL:  # gravity takes over
            q = (age - self.LURCH) / self.FALL
            rotation, sy, dark = turn * (.12 + .88 * q * q), 1 - .05 - (1 - height - .05) * q * q, .15 + .85 * q
        elif age < self.DOWN:  # the landing: a short bounce back up, a thud into the ground, then still
            q = (age - self.LURCH - self.FALL) / self.SETTLE
            lift = math.sin(math.pi * q)
            rotation, sy, dark = turn - math.copysign(bounce, turn) * lift, height - .06 * lift, 1.0
            if not self.landed:
                self.landed = True
                if self.on_land is not None:
                    self.on_land(self.feet, self.kind)
        else:
            rotation, sy, dark = turn, height, 1.0
        blend = min(1.0, age / self.LURCH)
        feet = (self.stood[0] + (self.position[0] - self.stood[0]) * blend, self.stood[1] + (self.position[1] - self.stood[1]) * blend)
        self.feet = feet
        w, h = self.size[0] * (1 + (1 - sy) * .35), self.size[1] * sy  # what folds down spreads out a little
        angle = math.radians(rotation)
        pivot = (self.size[1] / 2 - self.drop) * sy
        self.sprite.size = (w, h)
        self.sprite.rotation = rotation
        self.sprite.position = (feet[0] + math.sin(angle) * pivot, feet[1] - math.cos(angle) * pivot + h / 2)
        self.sprite.tint = tuple(start + (end - start) * dark for start, end in zip(self.tint, (.72, .66, .62)))
        hold = 0.0 if self.hurried else self.HOLD
        fade = max(0.0, (age - self.DOWN - hold) / self.FADE)
        self.sprite.opacity = 255 * max(0.0, 1 - fade)
        if fade >= 1:
            self.cancelled = True

    @property
    def lying(self) -> bool:
        return self.elapsed >= self.DOWN

    def draw(self, scene: Scene) -> None:
        pass  # a retained sprite; nothing immediate to draw

    def finish(self) -> None:
        self.sprite.remove()
