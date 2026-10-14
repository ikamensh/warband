"""Five readable campaign props: brass bells, bound anchors, resonance gates, refuges and memorials.

Painted with shaded facets at three times their logical size and reduced once. Each object has
its own silhouette, a grounded stone footprint and deliberate state art. They are story scenery,
not buildings; their placement is the centre of the shallow ellipse at the foot of the image.
"""

from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageFilter

SIZE = (112, 144)
DROP = 24
KINDS = ("bell", "anchor", "gate", "refuge", "memorial")
STATES = ("dormant", "active", "ruined", "open")
STONE = (139, 153, 161, 255)
STONE_LIGHT = (192, 204, 208, 255)
STONE_DARK = (73, 89, 102, 255)
BRASS = (183, 132, 66, 255)
BRASS_LIGHT = (252, 218, 134, 255)
CYAN = (111, 231, 244)
AMBER = (255, 196, 98)
CRIMSON = (238, 83, 113)


def hue(kind: str, state: str) -> tuple[int, int, int]:
    """The object's light, also used by its world-space ring and nameplate."""
    if state == "ruined":
        return (146, 145, 150)
    if kind in ("refuge", "memorial"):
        return AMBER
    if kind == "anchor" and state == "dormant":
        return CRIMSON
    return CYAN


@lru_cache(maxsize=20)
def image(kind: str, state: str = "dormant") -> Image.Image:
    """One complete RGBA prop, including its state light and grounded shadow."""
    if kind not in KINDS or state not in STATES:
        raise ValueError(f"unknown landmark kind/state: {kind!r}/{state!r}")
    scale = 3
    canvas = Image.new("RGBA", (SIZE[0] * scale, SIZE[1] * scale))
    draw = ImageDraw.Draw(canvas)

    def polygon(points, color):
        draw.polygon([(round(x * scale), round(y * scale)) for x, y in points], fill=color)

    def ellipse(box, color, outline=None, width=1):
        draw.ellipse(tuple(round(value * scale) for value in box), fill=color, outline=outline, width=round(width * scale))

    def line(points, color, width=1):
        draw.line([(round(x * scale), round(y * scale)) for x, y in points], fill=color, width=round(width * scale), joint="curve")

    def stone(x, y, width, height, depth=5):
        polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)], STONE)
        polygon([(x, y), (x + depth, y - depth), (x + width + depth, y - depth), (x + width, y)], STONE_LIGHT)
        polygon([(x + width, y), (x + width + depth, y - depth), (x + width + depth, y + height - depth), (x + width, y + height)], STONE_DARK)
        line([(x + 1, y + 1), (x + width - 1, y + 1)], (218, 221, 210, 220))

    def glow(x, y, radius, color, strength=1.0):
        halo = Image.new("RGBA", canvas.size)
        hd = ImageDraw.Draw(halo)
        for r, alpha in ((radius, 35), (radius * .55, 58), (radius * .23, 90)):
            hd.ellipse(tuple(round(v * scale) for v in (x-r, y-r, x+r, y+r)), fill=(*color, round(alpha * strength)))
        canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(4 * scale)))

    color = hue(kind, state)
    lit = state in ("active", "open")
    ellipse((13, 114, 101, 137), (12, 20, 28, 74))
    ellipse((18, 107, 94, 131), STONE_DARK)
    ellipse((18, 104, 94, 126), (109, 123, 132, 255), STONE_LIGHT)
    ellipse((25, 108, 87, 122), (64, 79, 89, 255), BRASS)
    for i in range(12):
        angle = i * math.tau / 12
        x, y = 56 + math.cos(angle) * 31, 115 + math.sin(angle) * 7
        line([(x, y), (x + math.cos(angle)*3, y + math.sin(angle))], (204, 177, 115, 210), 1)

    if state == "ruined":
        # Collapsed material retains the original object's identity rather than a generic grey replacement.
        stone(28, 100, 28, 14)
        stone(60, 106, 21, 9)
        polygon([(32, 100), (44, 85), (67, 92), (57, 105)], STONE_DARK)
        line([(28, 102), (48, 109), (64, 105), (76, 111)], (39, 48, 60, 255), 2)
        if kind == "bell":
            polygon([(49, 88), (72, 94), (70, 111), (42, 104)], BRASS)
            ellipse((42, 96, 58, 109), (84, 69, 53, 255), BRASS_LIGHT)
            line([(50, 88), (59, 97), (57, 104)], (74, 53, 40, 255), 2)
        elif kind == "anchor":
            polygon([(51, 88), (67, 71), (63, 101)], (100, 51, 69, 255))
            polygon([(35, 106), (51, 97), (44, 115)], (143, 65, 82, 255))
        elif kind == "gate":
            stone(24, 69, 12, 42)
            stone(79, 91, 11, 21)
        elif kind == "refuge":
            polygon([(25, 108), (52, 87), (87, 110), (58, 119)], (114, 99, 62, 255))
            line([(39, 94), (60, 120)], (191, 140, 74, 255), 2)
        else:
            polygon([(48, 87), (70, 74), (82, 87), (61, 110)], STONE)
            line([(58, 86), (68, 89), (61, 100)], BRASS_LIGHT)
        return canvas.resize(SIZE, Image.Resampling.LANCZOS)

    if lit:
        glow(56, 78 if kind != "refuge" else 101, 30, color)

    if kind == "bell":
        stone(25, 53, 11, 63)
        stone(78, 53, 10, 63)
        stone(25, 42, 63, 10)
        line([(34, 51), (34, 107)], BRASS, 2)
        line([(81, 51), (81, 107)], BRASS, 2)
        ellipse((51, 52, 61, 64), None, BRASS_LIGHT, 2)
        polygon([(46, 67), (52, 61), (61, 61), (67, 67), (71, 87), (78, 94), (35, 94), (42, 87)], BRASS)
        polygon([(46, 67), (52, 61), (56, 62), (52, 89), (39, 92), (44, 81)], BRASS_LIGHT)
        polygon([(61, 63), (67, 67), (71, 87), (77, 93), (60, 90)], (129, 85, 48, 255))
        ellipse((35, 89, 78, 99), (140, 94, 45, 255), BRASS_LIGHT, 2)
        ellipse((40, 91, 73, 97), (74, 63, 54, 255))
        line([(56, 93), (56, 105)], BRASS_LIGHT, 2)
        ellipse((52, 101, 60, 108), BRASS)
        line([(47, 77), (55, 73), (62, 77), (56, 84), (47, 77)], (*color, 255 if lit else 120), 2)
        polygon([(28, 40), (33, 34), (38, 40)], BRASS_LIGHT)
        polygon([(76, 40), (81, 34), (86, 40)], BRASS_LIGHT)
    elif kind == "anchor":
        stone(41, 102, 30, 12)
        stone(46, 95, 20, 8)
        for x, y, h in ((32, 79, 22), (80, 76, 25), (56, 41, 55)):
            polygon([(x, y), (x + 9, y + h*.43), (x, y + h), (x - 9, y + h*.43)], (*color, 255))
            polygon([(x, y), (x, y+h), (x-9, y+h*.43)], (*tuple(round(c*.48) for c in color), 255))
            line([(x, y + 4), (x+5, y+h*.43)], (229, 242, 237, 230))
        ellipse((35, 63, 78, 85), None, BRASS, 4)
        line([(31, 96), (42, 75), (56, 89), (75, 75), (83, 97)], (88, 80, 73, 255), 3)
        ellipse((51, 70, 61, 80), (248, 233, 166, 255))
    elif kind == "gate":
        # Segmented arch leaves a real opening, with a light skin recessed behind its masonry.
        if lit:
            ellipse((36, 49, 79, 117), (*color, 90))
            ellipse((43, 58, 72, 111), (216, 249, 255, 72))
        stone(24, 62, 14, 55)
        stone(78, 62, 13, 55)
        for i in range(7):
            a1, a2 = math.pi + i * math.pi/7, math.pi + (i+1)*math.pi/7
            polygon([(56+35*math.cos(a1), 64+32*math.sin(a1)), (56+35*math.cos(a2), 64+32*math.sin(a2)),
                     (56+22*math.cos(a2), 64+20*math.sin(a2)), (56+22*math.cos(a1), 64+20*math.sin(a1))],
                    STONE_LIGHT if i < 4 else STONE)
        line([(26, 65), (31, 45), (45, 34), (66, 34), (84, 49), (88, 65)], BRASS, 2)
        polygon([(51, 29), (61, 29), (66, 42), (56, 50), (47, 42)], BRASS)
        polygon([(56, 32), (61, 41), (56, 46), (51, 41)], (*color, 255 if lit else 130))
        if state != "open":
            for x in range(42, 77, 8):
                line([(x, 60), (x, 114)], (119, 91, 62, 255), 3)
            line([(39, 92), (77, 92)], BRASS_LIGHT, 2)
        else:
            for y in (69, 86, 103):
                line([(47, y), (66, y-4)], (215, 252, 255, 180), 2)
        stone(25, 109, 13, 8)
        stone(78, 109, 13, 8)
    elif kind == "refuge":
        polygon([(27, 80), (56, 64), (88, 81), (86, 115), (26, 115)], (154, 133, 78, 255))
        polygon([(27, 80), (56, 64), (59, 91), (26, 115)], (219, 186, 106, 255))
        polygon([(56, 64), (88, 81), (86, 115), (59, 91)], (105, 116, 88, 255))
        polygon([(48, 96), (60, 83), (72, 99), (73, 115), (46, 115)], (47, 56, 55, 255))
        polygon([(56, 89), (60, 83), (64, 92), (68, 113), (53, 113)], (154, 101, 50, 255))
        line([(56, 64), (58, 42)], BRASS_LIGHT, 2)
        polygon([(58, 44), (78, 47), (58, 55)], (222, 159, 76, 255))
        line([(28, 80), (20, 121)], (199, 185, 143, 255), 1)
        line([(88, 81), (95, 121)], (199, 185, 143, 255), 1)
        glow(43, 97, 16, AMBER, .65 if lit else .35)
        line([(40, 82), (40, 94), (46, 94)], BRASS, 2)
        polygon([(39, 92), (47, 92), (46, 103), (40, 103)], (90, 62, 39, 255))
        polygon([(41, 94), (45, 94), (45, 100), (41, 100)], (*AMBER, 255))
        line([(29, 81), (53, 69)], (249, 220, 157, 255), 2)
    else:
        stone(33, 103, 46, 12)
        stone(40, 94, 32, 10)
        stone(46, 48, 20, 45)
        polygon([(46, 48), (46, 42), (56, 33), (67, 42), (67, 48)], STONE_LIGHT)
        line([(55, 46), (55, 79)], BRASS, 2)
        line([(49, 53), (61, 53)], BRASS, 2)
        line([(51, 75), (55, 80), (62, 69)], (*color, 255 if lit else 120), 2)
        for x, y in ((35, 106), (78, 107), (58, 113)):
            ellipse((x-4, y-2, x+4, y+2), (195, 148, 79, 255))
            line([(x, y), (x, y-7)], (238, 220, 181, 255), 3)
            polygon([(x, y-14), (x+2, y-9), (x, y-6), (x-2, y-9)], (*AMBER, 255))
        line([(43, 88), (38, 79), (42, 64)], (79, 120, 93, 255), 2)

    if lit:
        for x, y in ((20, 98), (94, 96), (51, 20)):
            polygon([(x, y-3), (x+1.5, y), (x, y+3), (x-1.5, y)], (*color, 185))
    return canvas.resize(SIZE, Image.Resampling.LANCZOS)
