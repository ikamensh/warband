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
from warband.sim.rules import CREATURES, SPELLS, BuildingType, MapTheme, Race, UnitType, Upgrade
from warband.art.monsters import Monster, lair_portrait_image, monster_portrait_image
from warband.art.textures import portrait_image

_CREATURES = frozenset(CREATURES)  # the neutral creatures: their pictures are monsters.py's, not textures.py's

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
# The spells' (WB-066): aether's violet, fire, stone and the sick green of withering.
_AETHER = (170, 104, 240, 255)
_AETHER_LIGHT = (224, 196, 255, 255)
_AETHER_DEEP = (104, 52, 170, 255)
_FLAME = (242, 128, 44, 255)
_EMBER = (255, 214, 110, 255)
_ROCK = (132, 124, 116, 255)
_ROCK_LIGHT = (176, 168, 158, 255)
_ROOT = (118, 80, 46, 255)
_SICK = (150, 158, 96, 255)
_MIST = (120, 96, 140, 255)


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
    if upgrade is Upgrade.KEEP:
        # A crenellated keep under its banner: the hall raised.
        polygon([(.18, .88), (.18, .40), (.82, .40), (.82, .88)], _SHADE)
        polygon([(.18, .40), (.50, .40), (.50, .88), (.18, .88)], (118, 148, 170, 255))
        for x in (.18, .34, .50, .66):  # battlements
            polygon([(x, .40), (x + .11, .40), (x + .11, .29), (x, .29)], _SHADE)
        polygon([(.41, .88), (.41, .62), (.50, .54), (.59, .62), (.59, .88)], _INK)
        polygon([(.44, .88), (.44, .64), (.50, .58), (.56, .64), (.56, .88)], _WOOD)
        for y in (.52, .64, .76):  # courses of stone
            line([(.18, y), (.82, y)], (66, 92, 112, 255), .012)
        line([(.50, .29), (.50, .12)], _LIGHT, .022)  # the staff stops short of the ring
        polygon([(.52, .14), (.78, .19), (.52, .26)], _GOLD)
    elif upgrade in (Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3):
        tier = 1 if upgrade is Upgrade.BLADES_1 else 2 if upgrade is Upgrade.BLADES_2 else 3
        polygon([(.73, .16), (.84, .15), (.84, .27), (.42, .70), (.31, .59)], _STEEL)
        polygon([(.84, .15), (.79, .27), (.37, .66), (.31, .59)], _LIGHT)
        line([(.26, .54), (.47, .75)], _GOLD, .055)
        line([(.34, .65), (.21, .79)], _WOOD, .075)
        ellipse((.15, .76, .25, .86), _GOLD)
        if tier >= 2:
            polygon([(.53, .43), (.57, .38), (.62, .42), (.58, .47)], _GOLD)
        if tier == 3:  # a second stone, and the edge itself runed in gold
            polygon([(.66, .30), (.70, .25), (.75, .29), (.71, .34)], _GOLD)
            line([(.78, .21), (.40, .61)], _GOLD, .016)
    elif upgrade in (Upgrade.ARMOR_1, Upgrade.ARMOR_2):
        tier = 1 if upgrade is Upgrade.ARMOR_1 else 2
        polygon([(.23, .20), (.77, .20), (.75, .57), (.65, .75), (.5, .85), (.35, .75), (.25, .57)], _STEEL)
        polygon([(.5, .26), (.69, .26), (.67, .56), (.59, .69), (.5, .77)], _SHADE)
        line([(.29, .28), (.31, .54), (.40, .69)], _LIGHT, .025)
        if tier == 2:
            polygon([(.44, .32), (.56, .32), (.56, .46), (.67, .46), (.66, .57), (.56, .57), (.56, .71), (.44, .71), (.44, .57), (.34, .57), (.33, .46), (.44, .46)], _GOLD)
    elif upgrade in (Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.ARROWS_3):
        tier = 1 if upgrade is Upgrade.ARROWS_1 else 2 if upgrade is Upgrade.ARROWS_2 else 3
        line([(.24, .76), (.70, .30)], _WOOD, .045)
        polygon([(.61, .28), (.84, .16), (.72, .39), (.70, .30)], _STEEL)
        polygon([(.70, .30), (.84, .16), (.72, .39)], _LIGHT)
        polygon([(.17, .67), (.25, .58), (.38, .58), (.28, .69)], _LIGHT)
        polygon([(.29, .84), (.39, .74), (.39, .62), (.28, .73)], _STEEL)
        if tier >= 2:
            polygon([(.59, .29), (.84, .16), (.71, .42), (.67, .34), (.58, .33)], _GOLD)
            line([(.28, .66), (.34, .72)], _GOLD, .035)
        if tier == 3:  # the fletching gilded too
            polygon([(.17, .67), (.25, .58), (.38, .58), (.28, .69)], _GOLD)
            polygon([(.29, .84), (.39, .74), (.39, .62), (.28, .73)], _GOLD)
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
    elif upgrade is Upgrade.MARKSMANSHIP:
        # A straw target, an arrow in its gold.
        ellipse((.16, .16, .84, .84), _LIGHT, _INK, .015)
        ellipse((.28, .28, .72, .72), (168, 58, 48, 255))
        ellipse((.40, .40, .60, .60), _GOLD)
        line([(.5, .5), (.86, .20)], _WOOD, .035)
        polygon([(.86, .20), (.74, .20), (.80, .26), (.86, .32)], _LIGHT)
        polygon([(.5, .5), (.58, .40), (.60, .48)], _STEEL)
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
    elif upgrade is Upgrade.HASTE:
        # A bolt of an arrow flying right, three streaks of speed behind it.
        for y, x0 in ((.34, .16), (.5, .10), (.66, .16)):
            line([(x0, y), (x0 + .26, y)], _AETHER, .04)
        polygon([(.40, .30), (.62, .30), (.86, .50), (.62, .70), (.40, .70), (.60, .50)], _AETHER_LIGHT)
        polygon([(.50, .38), (.62, .38), (.74, .50), (.62, .62), (.50, .62), (.60, .50)], _AETHER)
    elif upgrade is Upgrade.MEND:
        # A green cross in a ring of light, sparks rising.
        arc(.5, .52, .30, 0, 360, _LEAF, .03, steps=24)
        polygon([(.43, .26), (.57, .26), (.57, .45), (.76, .45), (.76, .59), (.57, .59), (.57, .78), (.43, .78), (.43, .59),
                 (.24, .59), (.24, .45), (.43, .45)], _GREEN)
        polygon([(.46, .30), (.54, .30), (.54, .48), (.46, .48)], _LEAF)
        for cx, cy in ((.24, .24), (.78, .28), (.72, .80)):
            ellipse((cx - .035, cy - .035, cx + .035, cy + .035), _LIGHT)
    elif upgrade is Upgrade.FLAME_STRIKE:
        # A tongue of fire, red about orange about yellow.
        polygon([(.5, .12), (.66, .36), (.78, .30), (.76, .58), (.68, .80), (.5, .88), (.32, .80), (.24, .58), (.28, .40),
                 (.38, .48), (.40, .30)], _RED)
        polygon([(.52, .28), (.64, .50), (.66, .66), (.58, .80), (.5, .84), (.40, .78), (.34, .62), (.42, .52), (.46, .40)], _FLAME)
        polygon([(.52, .50), (.58, .64), (.56, .76), (.5, .80), (.44, .76), (.44, .64)], _EMBER)
    elif upgrade is Upgrade.STONESKIN:
        # A shield of fitted stones.
        polygon([(.23, .20), (.77, .20), (.75, .57), (.65, .75), (.5, .85), (.35, .75), (.25, .57)], _ROCK)
        for points in ([(.27, .24), (.49, .24), (.47, .44), (.28, .46)], [(.53, .24), (.73, .24), (.72, .42), (.52, .44)],
                       [(.30, .50), (.49, .48), (.48, .70), (.38, .72)], [(.53, .48), (.70, .46), (.64, .68), (.52, .74)]):
            polygon(points, _ROCK_LIGHT)
    elif upgrade is Upgrade.ENTANGLE:
        # Roots coiling up out of the ground round an ankle's worth of nothing, leaves on their tips.
        line([(.14, .82), (.86, .82)], _ROOT, .04)
        for x0, bend in ((.26, .14), (.5, -.12), (.72, .12)):
            arc(x0 + bend, .56, .2, 120 if bend > 0 else -60, 300 if bend > 0 else 120, _ROOT, .045)
        for cx, cy, sx in ((.30, .30, -1), (.52, .24, 1), (.74, .32, 1)):
            polygon([(cx, cy), (cx + sx * .12, cy - .07), (cx + sx * .16, cy + .02), (cx + sx * .04, cy + .06)], _LEAF)
    elif upgrade is Upgrade.WITHER:
        # A leaf dried and curled, a sick mist rising off it.
        polygon([(.26, .78), (.34, .52), (.52, .34), (.74, .28), (.70, .48), (.56, .66), (.36, .76)], _SICK)
        line([(.26, .80), (.66, .36)], (96, 90, 60, 255), .025)
        for cx, cy, r in ((.30, .30, .12), (.56, .20, .09), (.78, .46, .08)):
            arc(cx, cy, r, 200, 520, _MIST, .03)
    elif upgrade is Upgrade.METEOR:
        # A rock falling, its fiery tail behind it to the top right.
        polygon([(.86, .14), (.72, .12), (.34, .48), (.52, .66)], _FLAME)
        polygon([(.80, .20), (.70, .20), (.42, .50), (.50, .58)], _EMBER)
        ellipse((.18, .46, .52, .80), _ROCK, _FLAME, .03)
        ellipse((.24, .52, .36, .64), _ROCK_LIGHT)
    elif upgrade is Upgrade.SUMMON:
        # A crystal of aether rising out of a summoning ring.
        ellipse((.18, .66, .82, .86), None, _AETHER, .035)
        polygon([(.5, .14), (.68, .40), (.5, .72), (.32, .40)], _AETHER)
        polygon([(.5, .14), (.68, .40), (.5, .44)], _AETHER_LIGHT)
        polygon([(.32, .40), (.5, .44), (.5, .72)], _AETHER_DEEP)
        for x in (.22, .78):
            ellipse((x - .06, .40, x + .06, .52), _AETHER_DEEP)
    elif upgrade is Upgrade.BATTLE_FURY:
        # Two crossed swords over a burst of red.
        for angle in range(0, 360, 30):
            a = math.radians(angle)
            line([(.5 + .18 * math.cos(a), .5 + .18 * math.sin(a)), (.5 + .36 * math.cos(a), .5 + .36 * math.sin(a))], _RED, .03)
        for flip in (1, -1):
            tip, grip = (.5 + flip * .30, .18), (.5 - flip * .22, .76)
            line([tip, grip], _STEEL, .055)
            line([(.5 - flip * .30, .62), (.5 - flip * .10, .70)], _GOLD, .04)
    else:
        raise ValueError(f"No production emblem for {upgrade!r}")
    if upgrade in SPELLS:
        tier = SPELLS[upgrade].level  # a spell's badge is its level: I, II or III

    if tier:
        # A Roman numeral badge makes every research tier legible at 32px.
        ellipse((.02, .65, .35, .98), _INK, _GOLD, .018)
        centers = (.185,), (.145, .225), (.115, .185, .255)
        for x in centers[tier - 1]:
            line([(x, .73), (x, .90)], _LIGHT, .038)
    return image.resize((edge, edge), Image.Resampling.LANCZOS)


def production_image(game, target: ProductionTarget, player: int | None, race: Race = Race.HUMAN,
                     theme: MapTheme = MapTheme.SUMMER) -> str:
    """Register once and return the portrait or emblem for a production target.  A creature wears
    the match's landscape coat, like on the map; everything else is theme-blind."""
    if target in _CREATURES:
        return monster_portrait_image(game, Monster(target.value), theme)  # nobody's, so no player and no race
    if target is BuildingType.LAIR:
        # A catalogue never lists a den; the selection panel draws its own portrait per kind.
        return lair_portrait_image(game, theme=theme)
    if isinstance(target, (UnitType, BuildingType)):
        return portrait_image(game, target, player, race)
    if not isinstance(target, Upgrade):
        raise TypeError(f"Unknown production target: {target!r}")
    key = f"production.{target.value}"
    if not game.assets.has_image(key):
        game.assets.image_from_pil(key, _research_emblem(target, game.backend.scale_factor))
    return key


def fit(game, key, x, y, size):
    """Where *key*'s image goes to stand centred in a square of *size* at (x, y), undistorted: ``(x, y, width, height)``."""
    width, height = game.backend.get_image_size(game.assets.image(key))
    ratio = size / max(width, height)
    width, height = width * ratio, height * ratio
    return x + (size - width) / 2, y + (size - height) / 2, width, height


def draw_production_icon(scene, target: ProductionTarget, player: int | None, race: Race, x: float, y: float, size: float, *,
                         opacity: float = 1.0, theme: MapTheme = MapTheme.SUMMER) -> None:
    """Draw a target centred in a square, without distorting its portrait."""
    key = production_image(scene.game, target, player, race, theme)
    scene.draw_image(key, *fit(scene.game, key, x, y, size), opacity=opacity)


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
            self._game.assets.image(key), *fit(self._game, key, x, y, min(width, height)),
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
