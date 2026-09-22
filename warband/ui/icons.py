"""Small colour-coded HUD symbols: resources in the top bar, a unit's numbers on its card, prices everywhere.

Each symbol is a few flat polygons in unit coordinates, drawn at any size in
one of the panel's colours, so the HUD stays readable at a glance without a
word beside every number.  A price is drawn from the same symbols
(:func:`price_pairs`, :func:`draw_price`, :class:`Price`), so the coin on a
command card is the coin in the top bar, and a floating gain
(:class:`ResourceFloat`) carries the same symbol instead of the word.
First built on the unmerged ``warband`` branch.
"""

from __future__ import annotations

import math

from saga2d.effects import Effect, ease_out
from saga2d.scene import Scene
from saga2d.ui import Component
from warband.sim.rules import Cost
from warband.ui.style import BAD, BODY

Color = tuple[int, int, int, int]

COLORS: dict[str, Color] = {
    "gold": (255, 214, 110, 255), "lumber": (206, 162, 105, 255), "supply": (232, 215, 161, 255), "health": (130, 225, 155, 255),
    "damage": (237, 205, 164, 255), "armor": (159, 192, 221, 255), "range": (210, 185, 228, 255), "speed": (221, 201, 155, 255),
}


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


def loop_parts(color: Color = COLORS["gold"]) -> list[tuple[list[tuple[float, float]], Color]]:
    """Two arrows chasing each other round a ring: endless training.  Quads along each arc and a triangle at its
    head, each convex, since the backend fans every polygon from its first point."""
    outer, inner, parts = .44, .27, []
    for start, end in ((-165.0, -30.0), (15.0, 150.0)):
        steps = 6
        for i in range(steps):
            a, b = (math.radians(start + (end - start) * j / steps) for j in (i, i + 1))
            parts.append(([(.5 + outer * math.cos(a), .5 + outer * math.sin(a)), (.5 + outer * math.cos(b), .5 + outer * math.sin(b)),
                           (.5 + inner * math.cos(b), .5 + inner * math.sin(b)), (.5 + inner * math.cos(a), .5 + inner * math.sin(a))], color))
        head, tip = math.radians(end), math.radians(end + 40)
        mid = (outer + inner) / 2
        parts.append(([(.5 + (outer + .08) * math.cos(head), .5 + (outer + .08) * math.sin(head)),
                       (.5 + mid * math.cos(tip), .5 + mid * math.sin(tip)),
                       (.5 + (inner - .08) * math.cos(head), .5 + (inner - .08) * math.sin(head))], color))
    return parts


def lock_parts(color: Color) -> list[tuple[list[tuple[float, float]], Color]]:
    """A padlock: what an item lacks is not coming.  The shackle is quads along a half ring on two short posts."""
    outer, inner, top, parts = .3, .17, .4, []
    for i in range(6):
        a, b = (math.radians(180 + 180 * j / 6) for j in (i, i + 1))
        parts.append(([(.5 + outer * math.cos(a), top + outer * math.sin(a)), (.5 + outer * math.cos(b), top + outer * math.sin(b)),
                       (.5 + inner * math.cos(b), top + inner * math.sin(b)), (.5 + inner * math.cos(a), top + inner * math.sin(a))], color))
    for x in (.5 - outer, .5 + inner):
        parts.append(([(x, top), (x + outer - inner, top), (x + outer - inner, .5), (x, .5)], color))
    parts.append(([(.12, .48), (.88, .48), (.88, 1.0), (.12, 1.0)], color))
    return parts


def hourglass_parts(color: Color) -> list[tuple[list[tuple[float, float]], Color]]:
    """An hourglass: what an item lacks is on its way, and the item waits for it."""
    return [([(.1, 0.0), (.9, 0.0), (.9, .1), (.1, .1)], color), ([(.18, .1), (.82, .1), (.5, .5)], color),
            ([(.5, .5), (.82, .9), (.18, .9)], color), ([(.1, .9), (.9, .9), (.9, 1.0), (.1, 1.0)], color)]


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


Pair = tuple[str, str, Color]  # a symbol, the number beside it and that number's ink

PRICE_GAP = 3      # between a symbol and its number
PRICE_SPACING = 9  # between one resource and the next


def price_pairs(cost: Cost, purse: tuple[int, int] | None = None) -> list[Pair]:
    """*cost* as symbols and numbers: the coin always, the log only when it takes lumber (a price reads "400",
    not "400 / 0").  Given *purse* — the gold and lumber the player holds now — a number the purse cannot cover
    turns red, so a glance at a card says what is out of reach, as StarCraft's cost lines do.  The symbols keep
    their own colours: they say which resource, the number says whether it is there."""
    pairs = [("gold", str(cost.gold), BAD if purse is not None and purse[0] < cost.gold else BODY)]
    if cost.lumber:
        pairs.append(("lumber", str(cost.lumber), BAD if purse is not None and purse[1] < cost.lumber else BODY))
    return pairs


def price_width(game, pairs: list[Pair], size: float, font_size: int, font: str | None = None) -> float:
    """How wide :func:`draw_price` draws *pairs*."""
    width = sum(size + PRICE_GAP + game.backend.measure_text(text, font_size, font)[0] + PRICE_SPACING for _name, text, _ink in pairs)
    return max(0.0, width - PRICE_SPACING)


def draw_price(game, pairs: list[Pair], x: float, y: float, size: float, font_size: int, font: str | None = None, order: int = 0) -> None:
    """Draw each symbol and its number from (x, y), the symbols *size* square and the numbers on their middle."""
    for name, text, ink in pairs:
        for points, tint in _parts(name):
            game.backend.draw_polygon([(x + u * size, y + v * size) for u, v in points], tint, order=order)
        x += size + PRICE_GAP
        game.backend.draw_text(text, x, y + size / 2, font_size, ink, font=font, anchor_x="left", anchor_y="center", order=order)
        x += game.backend.measure_text(text, font_size, font)[0] + PRICE_SPACING


class Price(Component):
    """A price in a layout: the symbols and their numbers, as wide as they need (the codex's cost column)."""

    def __init__(self, pairs: list[Pair], *, size: int = 14, text_style: str = "body", **kwargs) -> None:
        super().__init__(**kwargs)
        self.pairs, self.size, self.text_style = pairs, size, text_style

    def _font(self) -> tuple[int, str | None]:
        style = self._game.theme.get_text_style(self.text_style)
        return style.font_size, style.font or self._game.theme.font

    @property
    def natural_width(self) -> int:
        """How wide the symbols and numbers are drawn, whatever box the layout gives them: a column narrower than
        this crowds the one beside it, which is what ``visual_lint`` looks for."""
        return 0 if self._game is None else math.ceil(price_width(self._game, self.pairs, self.size, *self._font()))

    def get_preferred_size(self) -> tuple[int, int]:
        return (self._width if self._width is not None else self.natural_width,
                self._height if self._height is not None else self.size)

    def on_draw(self) -> None:
        if self._game is None:
            return
        x, y, _w, h = self.bounds
        draw_price(self._game, self.pairs, x, y + (h - self.size) / 2, self.size, *self._font(), order=self._order)


def _quantize(alpha: float) -> int:
    """Alpha in steps of 16 so fading text reuses cached labels, as saga2d's own floating text does."""
    return max(0, min(255, int(alpha) // 16 * 16))


class ResourceFloat(Effect):
    """A floating "+N" with the resource's symbol: what salvage tears out and what plunder loots.

    A gain reads at a glance — "+2" and the log, not "+2 lumber" — the same coin and log as the top bar
    and the command card, so a refund is recognised by its symbol wherever it is seen.  Drawn like
    saga2d's own floating text (a dark pill, rising and fading) with the symbol after the number;
    *suffix* keeps a qualifier where one is owed ("plundered").
    """

    def __init__(
        self, amount: int, resource: str, position: tuple[float, float], *,
        suffix: str = "", color: Color | None = None, font_size: int = 18, rise: float = 26.0, duration: float = 1.2,
    ) -> None:
        super().__init__(duration)
        _parts(resource)  # unknown names fail here, not mid-frame
        self.amount, self.resource, self.suffix = amount, resource, suffix
        self.text = f"+{amount}"  # the number beside the symbol: never the resource's word
        self.x, self.y = position
        self.color = color if color is not None else COLORS[resource]
        self.font_size, self.rise = font_size, rise

    def draw(self, scene: Scene) -> None:
        t = self.t
        alpha = _quantize(self.color[3] * (1 - t * t))
        if alpha == 0:
            return
        camera = scene.camera
        assert camera is not None
        theme = scene.game.theme
        style = theme.get_text_style("floating")
        font = style.font or theme.font
        sx, sy = camera.world_to_screen(self.x, self.y - self.rise * ease_out(t))
        size = max(8, round(self.font_size * camera.zoom))
        gap = max(3, round(size / 5))
        main_w, main_h = scene.game.backend.measure_text(self.text, size, font)
        side = size
        suffix_w = scene.game.backend.measure_text(self.suffix, size, font)[0] if self.suffix else 0
        content = main_w + gap + side + (gap + suffix_w if self.suffix else 0)
        pill_h = max(main_h, side) + 2
        scene.draw_rect(sx - content / 2 - pill_h / 2, sy - pill_h / 2, content + pill_h, pill_h,
                        (10, 12, 20, _quantize(alpha * 0.55)), radius=pill_h / 2)
        ink = (*self.color[:3], alpha)
        x = sx - content / 2
        scene.draw_text(self.text, x, sy, style="floating", font_size=size, color=ink, anchor_x="left", anchor_y="center")
        x += main_w + gap
        for points, tint in _parts(self.resource):
            scene.draw_polygon([(x + u * side, sy - side / 2 + v * side) for u, v in points], (*tint[:3], alpha))
        if self.suffix:
            scene.draw_text(self.suffix, x + side + gap, sy, style="floating", font_size=size, color=ink,
                            anchor_x="left", anchor_y="center")
