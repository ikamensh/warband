"""Portraits and research emblems for the command card and production queues.

A unit or building shows its race's portrait (rendered from the same mesh as
its sprite); an upgrade shows a painted emblem, with a Roman-numeral badge
for the second tier of a shared upgrade.  :class:`ProductionButton` is an
ordinary button with the portrait inside and the hotkey in its corner;
:func:`draw_production_icon` draws the same picture immediately, for the
selection panel's queue.
"""

from __future__ import annotations

import math
from typing import TypeAlias

from PIL import Image, ImageDraw

from saga2d.ui import Anchor, Button, Component, KeyHints
from warband.rules import BuildingType, Race, UnitType, Upgrade
from warband.textures import portrait_image

ProductionTarget: TypeAlias = UnitType | BuildingType | Upgrade

_STEEL = (196, 216, 229, 255)
_LIGHT = (243, 239, 214, 255)
_SHADE = (91, 120, 143, 255)
_GOLD = (215, 174, 93, 255)
_WOOD = (152, 102, 57, 255)
_INK = (28, 33, 36, 255)
_GREEN = (98, 170, 92, 255)
_LEAF = (146, 208, 120, 255)
_RED = (198, 52, 48, 255)
_BONE = (232, 224, 200, 255)


def _research_emblem(upgrade: Upgrade, scale: float) -> Image.Image:
    """Paint bold silhouettes at 2× display density for clean small-size edges."""
    edge = round(128 * scale)
    image = Image.new("RGBA", (edge * 2, edge * 2))
    draw = ImageDraw.Draw(image)
    px = edge * 2

    def polygon(points, color):
        draw.polygon([(round(x * px), round(y * px)) for x, y in points], fill=color)

    def line(points, color, width):
        draw.line([(round(x * px), round(y * px)) for x, y in points],
                  fill=color, width=max(1, round(width * px)), joint="curve")

    def ellipse(bounds, color, outline=None, width=.01):
        draw.ellipse(tuple(round(v * px) for v in bounds), fill=color,
                     outline=outline, width=max(1, round(width * px)))

    def arc(cx, cy, radius, start, end, color, width, steps=16):
        line([(cx + radius * math.cos(math.radians(start + (end - start) * i / steps)),
               cy + radius * math.sin(math.radians(start + (end - start) * i / steps))) for i in range(steps + 1)], color, width)

    ellipse((.035, .035, .965, .965), (63, 58, 48, 255), _GOLD, .025)
    ellipse((.085, .085, .915, .915), _INK, (103, 91, 66, 255), .012)
    tier = 0
    if upgrade in (Upgrade.BLADES_1, Upgrade.BLADES_2):
        tier = 1 if upgrade is Upgrade.BLADES_1 else 2
        polygon([(.73, .16), (.84, .15), (.84, .27), (.42, .70), (.31, .59)], _STEEL)
        polygon([(.84, .15), (.79, .27), (.37, .66), (.31, .59)], _LIGHT)
        line([(.26, .54), (.47, .75)], _GOLD, .055)
        line([(.34, .65), (.21, .79)], _WOOD, .075)
        ellipse((.15, .76, .25, .86), _GOLD)
        if tier == 2:
            polygon([(.53, .43), (.57, .38), (.62, .42), (.58, .47)], _GOLD)
    elif upgrade in (Upgrade.ARMOR_1, Upgrade.ARMOR_2):
        tier = 1 if upgrade is Upgrade.ARMOR_1 else 2
        polygon([(.23, .20), (.77, .20), (.75, .57), (.65, .75), (.5, .85), (.35, .75), (.25, .57)], _STEEL)
        polygon([(.5, .26), (.69, .26), (.67, .56), (.59, .69), (.5, .77)], _SHADE)
        line([(.29, .28), (.31, .54), (.40, .69)], _LIGHT, .025)
        if tier == 2:
            polygon([(.44, .32), (.56, .32), (.56, .46), (.67, .46), (.66, .57), (.56, .57), (.56, .71), (.44, .71), (.44, .57), (.34, .57), (.33, .46), (.44, .46)], _GOLD)
    elif upgrade in (Upgrade.ARROWS_1, Upgrade.ARROWS_2):
        tier = 1 if upgrade is Upgrade.ARROWS_1 else 2
        line([(.24, .76), (.70, .30)], _WOOD, .045)
        polygon([(.61, .28), (.84, .16), (.72, .39), (.70, .30)], _STEEL)
        polygon([(.70, .30), (.84, .16), (.72, .39)], _LIGHT)
        polygon([(.17, .67), (.25, .58), (.38, .58), (.28, .69)], _LIGHT)
        polygon([(.29, .84), (.39, .74), (.39, .62), (.28, .73)], _STEEL)
        if tier == 2:
            polygon([(.59, .29), (.84, .16), (.71, .42), (.67, .34), (.58, .33)], _GOLD)
            line([(.28, .66), (.34, .72)], _GOLD, .035)
    elif upgrade is Upgrade.HORSES:
        polygon([(.28, .78), (.37, .59), (.32, .47), (.31, .30), (.42, .18), (.42, .31), (.55, .22), (.67, .29), (.73, .46), (.83, .55), (.80, .66), (.66, .67), (.57, .54), (.51, .62), (.55, .81)], _GOLD)
        polygon([(.31, .30), (.27, .45), (.28, .61), (.18, .78), (.28, .78), (.37, .59), (.32, .47)], _WOOD)
        polygon([(.43, .35), (.48, .28), (.51, .35)], _LIGHT)
        ellipse((.61, .40, .65, .44), _INK)
        line([(.62, .48), (.70, .55), (.81, .55)], _WOOD, .025)
        line([(.29, .83), (.64, .83)], _STEEL, .055)
    elif upgrade is Upgrade.SIEGE:
        polygon([(.24, .64), (.70, .64), (.76, .72), (.21, .72)], _WOOD)
        polygon([(.41, .67), (.43, .40), (.51, .40), (.65, .67)], _GOLD)
        line([(.31, .73), (.62, .26)], _WOOD, .065)
        line([(.34, .71), (.64, .26)], _LIGHT, .018)
        polygon([(.53, .26), (.64, .19), (.78, .28), (.73, .34), (.63, .33)], _GOLD)
        ellipse((.60, .14, .75, .29), _STEEL)
        for cx in (.31, .68):
            ellipse((cx - .09, .67, cx + .09, .85), _INK, _GOLD, .028)
            ellipse((cx - .025, .735, cx + .025, .785), _STEEL)
    elif upgrade is Upgrade.BLESSING:
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            line([(.5 + .26 * math.cos(a), .49 + .26 * math.sin(a)),
                  (.5 + .35 * math.cos(a), .49 + .35 * math.sin(a))], _GOLD, .025)
        ellipse((.29, .28, .71, .70), (104, 83, 143, 255))
        polygon([(.44, .22), (.56, .22), (.56, .42), (.73, .42), (.73, .55), (.56, .55), (.56, .78), (.44, .78), (.44, .55), (.27, .55), (.27, .42), (.44, .42)], _LIGHT)
        polygon([(.5, .40), (.57, .49), (.5, .58), (.43, .49)], _GOLD)
    elif upgrade is Upgrade.BLOODLUST:
        # A drop of blood between two tusks.
        polygon([(.5, .18), (.66, .46), (.68, .60), (.60, .74), (.5, .79), (.40, .74), (.32, .60), (.34, .46)], _RED)
        polygon([(.5, .18), (.66, .46), (.62, .58), (.54, .48)], (232, 96, 84, 255))
        polygon([(.16, .84), (.24, .52), (.33, .58), (.30, .84)], _BONE)
        polygon([(.84, .84), (.76, .52), (.67, .58), (.70, .84)], _BONE)
    elif upgrade is Upgrade.PLUNDER:
        # A sack spilling coins.
        polygon([(.30, .40), (.70, .40), (.80, .58), (.78, .84), (.22, .84), (.20, .58)], _WOOD)
        polygon([(.36, .26), (.64, .26), (.70, .40), (.30, .40)], (112, 74, 42, 255))
        line([(.33, .42), (.67, .42)], _GOLD, .03)
        for cx, cy in ((.30, .87), (.44, .90), (.60, .89), (.74, .86)):
            ellipse((cx - .07, cy - .045, cx + .07, cy + .045), _GOLD, _INK, .012)
    elif upgrade is Upgrade.LONGBOWS:
        # A tall bow, strung, with an arrow on the string.
        arc(.30, .5, .34, -80, 80, _WOOD, .05)
        line([(.36, .165), (.36, .835)], _LIGHT, .018)
        line([(.36, .5), (.82, .5)], _WOOD, .03)
        polygon([(.82, .5), (.70, .44), (.70, .56)], _STEEL)
        polygon([(.36, .5), (.46, .44), (.44, .5), (.46, .56)], _LIGHT)
    elif upgrade is Upgrade.REGROWTH:
        # A sapling rising from a stump.
        polygon([(.30, .64), (.70, .64), (.66, .86), (.34, .86)], _WOOD)
        ellipse((.30, .58, .70, .70), (196, 160, 104, 255))
        line([(.5, .66), (.5, .28)], _GREEN, .04)
        polygon([(.5, .40), (.30, .30), (.24, .40), (.36, .50)], _LEAF)
        polygon([(.5, .30), (.70, .18), (.78, .28), (.64, .40)], _LEAF)
        polygon([(.5, .52), (.68, .46), (.72, .56), (.58, .62)], _GREEN)
    elif upgrade is Upgrade.DEEP_MINING:
        # A pick over a gold nugget.
        line([(.24, .80), (.70, .34)], _WOOD, .05)
        polygon([(.56, .18), (.84, .28), (.80, .40), (.66, .38), (.60, .34)], _STEEL)
        polygon([(.56, .18), (.44, .26), (.58, .40), (.66, .38)], _SHADE)
        polygon([(.16, .56), (.32, .48), (.46, .58), (.44, .74), (.28, .80), (.14, .70)], _GOLD)
        polygon([(.16, .56), (.32, .48), (.30, .60)], (240, 214, 140, 255))
    elif upgrade is Upgrade.BLASTING_POWDER:
        # A bomb with a lit fuse.
        ellipse((.22, .34, .74, .86), (52, 56, 62, 255), _STEEL, .02)
        ellipse((.32, .42, .44, .54), (96, 102, 110, 255))
        polygon([(.44, .30), (.56, .30), (.58, .38), (.42, .38)], _STEEL)
        line([(.5, .30), (.56, .20), (.68, .16)], _WOOD, .03)
        for angle in range(0, 360, 60):
            a = math.radians(angle)
            line([(.72 + .05 * math.cos(a), .16 + .05 * math.sin(a)), (.72 + .12 * math.cos(a), .16 + .12 * math.sin(a))], _GOLD, .02)
        ellipse((.67, .11, .77, .21), _LIGHT)
    else:
        raise ValueError(f"No production emblem for {upgrade!r}")

    if tier:
        # A Roman numeral badge makes both research tiers legible at 32px.
        ellipse((.02, .65, .35, .98), _INK, _GOLD, .018)
        centers = (.185,) if tier == 1 else (.145, .225)
        for x in centers:
            line([(x, .73), (x, .90)], _LIGHT, .043)
    return image.resize((edge, edge), Image.Resampling.LANCZOS)


def production_image(game, target: ProductionTarget, player: int | None, race: Race = Race.HUMAN) -> str:
    """Register once and return the portrait or emblem for a production target."""
    if isinstance(target, (UnitType, BuildingType)):
        return portrait_image(game, target, player, race)
    if not isinstance(target, Upgrade):
        raise TypeError(f"Unknown production target: {target!r}")
    key = f"production.{target.value}"
    if not game.assets.has_image(key):
        game.assets.image_from_pil(key, _research_emblem(target, game.backend.scale_factor))
    return key


def _fit(game, key, x, y, size):
    width, height = game.backend.get_image_size(game.assets.image(key))
    ratio = size / max(width, height)
    width, height = width * ratio, height * ratio
    return x + (size - width) / 2, y + (size - height) / 2, width, height


def draw_production_icon(scene, target: ProductionTarget, player: int | None, race: Race, x: float, y: float, size: float) -> None:
    """Draw a target centred in a square, without distorting its portrait."""
    key = production_image(scene.game, target, player, race)
    scene.draw_image(key, *_fit(scene.game, key, x, y, size))


class ProductionIcon(Component):
    def __init__(self, target: ProductionTarget, player: int | None, race: Race, size: int = 48, **kwargs):
        super().__init__(width=size, height=size, **kwargs)
        self.target, self.player, self.race = target, player, race

    def on_draw(self):
        if self._game is None:
            return
        key = production_image(self._game, self.target, self.player, self.race)
        x, y, width, height = self.bounds
        component = self
        enabled = True
        while component is not None:
            enabled = enabled and component.enabled
            component = component.parent
        self._game.backend.draw_image(
            self._game.assets.image(key), *_fit(self._game, key, x, y, min(width, height)),
            opacity=1 if enabled else .38, order=self._order,
        )


class ProductionButton(Button):
    """Standard button interaction with a target portrait and corner keycap."""

    def __init__(self, target: ProductionTarget, player: int | None, race: Race, *, hotkey: str | None = None,
                 width: int = 64, height: int = 64, **kwargs):
        super().__init__("", width=width, height=height, **kwargs)
        self.target = target
        self.add(ProductionIcon(target, player, race, size=min(width, height) - 10, anchor=Anchor.CENTER))
        if hotkey:
            self.add(KeyHints([(hotkey, "")], gap=0, spacing=0, anchor=Anchor.BOTTOM_RIGHT, margin=3))
