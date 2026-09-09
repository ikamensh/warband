"""Warband's own transient effects on top of :mod:`saga2d.effects`."""

from __future__ import annotations

import math

from saga2d.effects import Effect
from saga2d.rendering import Sprite
from saga2d.scene import Scene
from warband.textures import DROP_UNIT

Point = tuple[float, float]


class UnitDeath(Effect):
    """Fall around the feet, then leave a body lying which slowly fades.

    Atlas cells include padding below the feet; compensating the centre-based
    sprite rotation keeps the body on the ground instead of spinning in mid-air.
    First built on the unmerged ``warband`` branch.
    """

    FALL = .62
    HOLD = 5.0
    FADE = 1.8

    def __init__(self, sprite: Sprite, position: Point, *, source: Point | None = None) -> None:
        super().__init__(self.FALL + self.HOLD + self.FADE)
        self.sprite, self.position = sprite, position
        self.size = sprite.size
        self.rotation, self.tint = sprite.rotation, sprite.tint
        angle = math.radians(self.rotation)
        pivot = self.size[1] / 2 - DROP_UNIT
        self.ground = (sprite.x - math.sin(angle) * pivot, sprite.y - self.size[1] / 2 + math.cos(angle) * pivot)
        dx, dy = (position[0] - source[0], position[1] - source[1]) if source is not None else (1.0, .2)
        length = math.hypot(dx, dy) or 1
        self.direction = (dx / length, dy / length)
        self.turn = 88 if dx >= 0 else -88  # fall away from the blow

    def advance(self) -> None:
        if self.sprite.is_removed:
            self.cancelled = True
            return
        age = self.elapsed
        fall = min(1.0, age / self.FALL)
        p = fall * fall * (3 - 2 * fall)  # a brief stagger gives way to gravity; the landing is firm, not a spin
        sx, sy = 1 - .08 * p, 1 - .22 * p
        w, h = self.size[0] * sx, self.size[1] * sy
        rotation = self.rotation + (self.turn - self.rotation) * p
        angle = math.radians(rotation)
        pivot = (self.size[1] / 2 - DROP_UNIT) * sy
        x = self.ground[0] + (self.position[0] - self.ground[0] + self.direction[0] * 9) * p
        y = self.ground[1] + (self.position[1] - self.ground[1] + self.direction[1] * 5) * p
        self.sprite.size = (w, h)
        self.sprite.rotation = rotation
        self.sprite.position = (x + math.sin(angle) * pivot, y - math.cos(angle) * pivot + h / 2)
        self.sprite.tint = tuple(start + (end - start) * p for start, end in zip(self.tint, (.72, .66, .62)))
        fade = max(0.0, (age - self.FALL - self.HOLD) / self.FADE)
        self.sprite.opacity = 255 * (1 - fade)

    def draw(self, scene: Scene) -> None:
        pass  # a retained sprite; nothing immediate to draw

    def finish(self) -> None:
        self.sprite.remove()
