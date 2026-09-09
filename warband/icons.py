"""Small colour-coded HUD symbols: resources in the top bar, a unit's numbers on its card.

Each symbol is a few flat polygons in unit coordinates, drawn at any size in
one of the panel's colours, so the HUD stays readable at a glance without a
word beside every number.  First built on the unmerged ``warband`` branch.
"""

from __future__ import annotations

import math

from saga2d.ui import Component

Color = tuple[int, int, int, int]

COLORS: dict[str, Color] = {
    "gold": (255, 214, 110, 255), "lumber": (206, 162, 105, 255), "supply": (232, 215, 161, 255), "health": (130, 225, 155, 255),
    "damage": (237, 205, 164, 255), "armor": (159, 192, 221, 255), "range": (210, 185, 228, 255), "speed": (221, 201, 155, 255),
}
LABELS = {"gold": "Gold", "lumber": "Lumber", "supply": "Supply used / capacity", "health": "Health", "damage": "Damage",
          "armor": "Armour", "range": "Range", "speed": "Movement speed"}


def _parts(name: str, color: Color | None = None) -> list[tuple[list[tuple[float, float]], Color]]:
    color = color if color is not None else COLORS[name]
    dark = tuple(round(c * .6) for c in color[:3]) + (color[3],)
    light = tuple(min(255, round(c * 1.2)) for c in color[:3]) + (color[3],)

    def disc(x, y, radius):
        return [(x + radius * math.cos(i * math.tau / 12), y + radius * math.sin(i * math.tau / 12)) for i in range(12)]

    if name == "gold":
        return [([(.5, .03), (.89, .33), (.76, .77), (.5, .97), (.16, .73), (.11, .32)], dark),
                ([(.5, .03), (.58, .39), (.5, .97), (.16, .73), (.11, .32)], color),
                ([(.5, .03), (.89, .33), (.58, .39)], light)]
    if name == "health":
        return [([(.5, .88), (.08, .43), (.08, .24), (.24, .12), (.42, .17), (.5, .32)], color),
                ([(.5, .88), (.5, .32), (.58, .17), (.76, .12), (.92, .24), (.92, .43)], color)]
    if name == "damage":
        return [([(.83, .05), (.91, .07), (.89, .30), (.38, .77), (.27, .65)], light),
                ([(.13, .58), (.21, .50), (.52, .81), (.44, .9)], color),
                ([(.25, .69), (.34, .78), (.17, .95), (.08, .86)], dark)]
    if name == "armor":
        return [([(.14, .10), (.86, .10), (.85, .54), (.70, .78), (.5, .96), (.30, .78), (.15, .54)], color),
                ([(.5, .21), (.76, .21), (.73, .54), (.61, .73), (.5, .82)], dark),
                ([(.22, .13), (.48, .13), (.48, .21), (.22, .21)], light)]
    if name == "range":
        return [([(.06, .38), (.26, .21), (.26, .34), (.74, .34), (.74, .21), (.94, .38), (.74, .55), (.74, .43), (.26, .43), (.26, .55)], color),
                ([(.12, .69), (.20, .69), (.20, .84), (.80, .84), (.80, .69), (.88, .69), (.88, .92), (.12, .92)], dark)]
    if name == "speed":
        return [([(.42, .08), (.76, .16), (.65, .59), (.87, .75), (.9, .86), (.79, .94), (.34, .82), (.28, .70)], color),
                ([(.10, .26), (.35, .26), (.33, .33), (.06, .33)], light),
                ([(.06, .43), (.30, .43), (.28, .50), (.02, .50)], light),
                ([(.34, .82), (.79, .94), (.9, .86), (.9, .97), (.31, .88)], dark)]
    if name == "supply":
        return [(disc(.5, .24, .17), light), ([(.32, .46), (.68, .46), (.79, .94), (.21, .94)], color),
                (disc(.14, .46, .1), dark), (disc(.86, .46, .1), dark)]
    if name == "lumber":
        return [([(.17, .20), (.71, .10), (.88, .33), (.31, .49)], color),
                (disc(.25, .36, .14), light), ([(.17, .64), (.73, .48), (.91, .73), (.31, .94)], color),
                (disc(.25, .79, .14), light), (disc(.25, .79, .065), dark), (disc(.25, .36, .065), dark)]
    raise ValueError(f"Unknown icon: {name}")


def draw_icon(scene, name: str, x: float, y: float, size: float = 24, color: Color | None = None, space: str = "screen") -> None:
    """Draw *name* immediately with its top-left corner at (x, y)."""
    for points, ink in _parts(name, color):
        scene.draw_polygon([(x + u * size, y + v * size) for u, v in points], ink, space=space)


class Icon(Component):
    """A retained symbol for layouts (the HUD's resource rows)."""

    def __init__(self, name: str, size: int = 24, color: Color | None = None, **kwargs) -> None:
        super().__init__(width=size, height=size, **kwargs)
        self.name, self.color = name, color

    def on_draw(self) -> None:
        if self._game is None:
            return
        x, y, w, h = self.bounds
        for points, ink in _parts(self.name, self.color):
            self._game.backend.draw_polygon([(x + u * w, y + v * h) for u, v in points], ink, order=self._order)
