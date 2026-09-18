"""Make Warband's application icon, ``packaging/icon.png``.

    uv run python tools/make_icon.py schematic           # draw packaging/icon-schematic.png
    uv run python tools/make_icon.py paint DIR           # have the image model paint it; candidates land in DIR
    uv run python tools/make_icon.py install CANDIDATE   # square it, size it and write packaging/icon.png

The schematic fixes the composition (the knights' blue shield with its gold
cross over a crossed sword and axe, on the title screen's dark earth) and is
flat on purpose: big shapes that survive 16 px.  The image model repaints it
in the manner of the painted units (``sagaforge.restyle``'s provider, the one
``tools/restyle.py`` uses); a candidate is looked at before it is installed.
``saga2d.packaging`` gives the installed square each platform's outline.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SCHEMATIC = ROOT / "packaging" / "icon-schematic.png"
ICON = ROOT / "packaging" / "icon.png"
SIDE = 1024
OVERSAMPLE = 4

EARTH_CENTRE, EARTH_EDGE = (112, 78, 44), (30, 20, 14)
BLUE_TOP, BLUE_BOTTOM = (64, 112, 224), (28, 52, 140)
GOLD, GOLD_DARK = (255, 208, 96), (196, 132, 40)
STEEL, STEEL_DARK = (226, 232, 240), (130, 142, 160)
WOOD = (122, 78, 40)

PROMPT = (
    "Generate an image: repaint this flat schematic as a polished hand-painted game app icon, in the style of a classic fantasy "
    "real-time strategy game: a royal blue heater shield with a gold rim and a gold cross, over a crossed steel "
    "sword and battle axe, on dark warm earth. Keep the composition, the proportions, the colours and the square "
    "frame exactly; paint to every edge with no border, no text, no letters and no rounded corners. Give the metal "
    "and the enamel painted highlights and soft shading, thick readable shapes, strong contrast between the shield "
    "and the ground."
)


def vertical(size: int, top, bottom) -> Image.Image:
    column = Image.new("RGB", (1, size))
    column.putdata([tuple(round(a + (b - a) * y / (size - 1)) for a, b in zip(top, bottom)) for y in range(size)])
    return column.resize((size, size)).convert("RGBA")


def radial(size: int, centre, edge) -> Image.Image:
    small = 256
    image = Image.new("RGB", (small, small))
    middle = (small - 1) / 2
    image.putdata([tuple(round(a + (b - a) * min(1.0, math.hypot(x - middle, y - middle * 0.9) / (small * 0.72)))
                         for a, b in zip(centre, edge)) for y in range(small) for x in range(small)])
    return image.resize((size, size), Image.Resampling.BICUBIC).convert("RGBA")


def shield_outline(size: int, inset: float = 0.0) -> list[tuple[float, float]]:
    """A heater shield: flat top, straight shoulders, two curves meeting in a point."""
    left, right, top, bottom = 0.285 + inset, 0.715 - inset, 0.185 + inset, 0.855 - inset * 1.4
    shoulder = 0.44
    curve = [(math.cos(step / 24 * math.pi / 2) ** 0.8, math.sin(step / 24 * math.pi / 2)) for step in range(25)]
    points = [(left, top), (right, top)]
    points += [(0.5 + (right - 0.5) * x, shoulder + (bottom - shoulder) * y) for x, y in curve]
    points += [(0.5 - (right - 0.5) * x, shoulder + (bottom - shoulder) * y) for x, y in reversed(curve)]
    return [(x * size, y * size) for x, y in points]


# A weapon is drawn upright on a layer larger than the picture, through its
# centre, and then turned onto a diagonal: REACH is how far from the centre its
# ends lie, short of the corners a platform's outline rounds away.
LAYER, REACH = 1.5, 0.555


def upright(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw, float, float, float]:
    layer = Image.new("RGBA", (round(size * LAYER),) * 2, (0, 0, 0, 0))
    middle = layer.width / 2
    return layer, ImageDraw.Draw(layer), middle, middle - REACH * size, middle + REACH * size


def turned(layer: Image.Image, degrees: float, size: int) -> Image.Image:
    edge = (layer.width - size) // 2
    return layer.rotate(degrees, resample=Image.Resampling.BICUBIC).crop((edge, edge, edge + size, edge + size))


def sword(size: int) -> Image.Image:
    layer, draw, x, tip, end = upright(size)
    blade, guard = 0.048 * size, end - 0.215 * size
    draw.polygon([(x - blade, guard), (x - blade, tip + 0.09 * size), (x, tip), (x, guard)], fill=STEEL)
    draw.polygon([(x, tip), (x + blade, tip + 0.09 * size), (x + blade, guard), (x, guard)], fill=STEEL_DARK)
    draw.rounded_rectangle((x - 0.135 * size, guard - 0.02 * size, x + 0.135 * size, guard + 0.035 * size), 0.022 * size, fill=GOLD)
    draw.rectangle((x - 0.026 * size, guard + 0.035 * size, x + 0.026 * size, end - 0.06 * size), fill=WOOD)
    draw.ellipse((x - 0.046 * size, end - 0.092 * size, x + 0.046 * size, end), fill=GOLD)
    return turned(layer, -45, size)


def axe(size: int) -> Image.Image:
    layer, draw, x, top, end = upright(size)
    draw.rounded_rectangle((x - 0.027 * size, top + 0.02 * size, x + 0.027 * size, end), 0.02 * size, fill=WOOD)
    draw.ellipse((x - 0.046 * size, end - 0.092 * size, x + 0.046 * size, end), fill=GOLD)
    centre, horn, reach = top + 0.20 * size, 0.135 * size, 0.155 * size
    def edge(bulge: float, inset: float) -> list[tuple[float, float]]:
        return [(x - reach + inset - bulge * math.cos(math.radians(angle)), centre + horn * math.sin(math.radians(angle)))
                for angle in range(-90, 91, 6)]
    body = [(x + 0.03 * size, centre - 0.075 * size), (x - 0.09 * size, centre - 0.10 * size), *edge(0.05 * size, 0),
            (x - 0.09 * size, centre + 0.10 * size), (x + 0.03 * size, centre + 0.075 * size)]
    draw.polygon(body, fill=STEEL_DARK)
    draw.polygon([*edge(0.05 * size, 0), *reversed(edge(0.038 * size, 0.04 * size))], fill=STEEL)
    draw.rounded_rectangle((x - 0.04 * size, centre - 0.095 * size, x + 0.04 * size, centre + 0.095 * size), 0.014 * size, fill=GOLD_DARK)
    return turned(layer, 45, size)


def shadowed(picture: Image.Image, layer: Image.Image, size: int) -> None:
    shadow = ImageChops.offset(layer.getchannel("A"), round(size * 0.012), round(size * 0.02)).filter(ImageFilter.GaussianBlur(size * 0.014))
    picture.paste(Image.new("RGBA", picture.size, (8, 4, 2, 255)), (0, 0), shadow.point(lambda value: value * 0.65))
    picture.alpha_composite(layer)


def schematic() -> Image.Image:
    size = SIDE * OVERSAMPLE
    picture = radial(size, EARTH_CENTRE, EARTH_EDGE)
    shadowed(picture, axe(size), size)
    shadowed(picture, sword(size), size)
    shield = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shield)
    draw.polygon(shield_outline(size), fill=GOLD)
    draw.polygon(shield_outline(size, 0.014), fill=GOLD_DARK)
    field = Image.new("L", (size, size), 0)
    ImageDraw.Draw(field).polygon(shield_outline(size, 0.042), fill=255)
    shield.paste(vertical(size, BLUE_TOP, BLUE_BOTTOM), (0, 0), field)
    cross = Image.new("L", (size, size), 0)
    cross_draw = ImageDraw.Draw(cross)
    cross_draw.rounded_rectangle((0.462 * size, 0.275 * size, 0.538 * size, 0.715 * size), 0.012 * size, fill=255)
    cross_draw.rounded_rectangle((0.365 * size, 0.385 * size, 0.635 * size, 0.461 * size), 0.012 * size, fill=255)
    shield.paste(Image.new("RGBA", (size, size), (*GOLD, 255)), (0, 0), ImageChops.multiply(cross, field))
    gloss = Image.new("L", (size, size), 0)
    ImageDraw.Draw(gloss).ellipse((0.12 * size, -0.05 * size, 0.62 * size, 0.52 * size), fill=46)
    shield.paste(Image.new("RGBA", (size, size), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(gloss.filter(ImageFilter.GaussianBlur(size * 0.03)), field))
    shadowed(picture, shield, size)
    return picture.resize((SIDE, SIDE), Image.Resampling.LANCZOS).convert("RGB")


def squared(candidate: Image.Image) -> Image.Image:
    """The model's picture cut to its central square at the icon's size."""
    side = min(candidate.size)
    left, top = (candidate.width - side) // 2, (candidate.height - side) // 2
    return candidate.convert("RGB").crop((left, top, left + side, top + side)).resize((SIDE, SIDE), Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schematic")
    painter = commands.add_parser("paint")
    painter.add_argument("dir", type=Path)
    painter.add_argument("--count", type=int, default=3)
    painter.add_argument("--model", default="google/gemini-3.1-flash-image")
    installer = commands.add_parser("install")
    installer.add_argument("candidate", type=Path)
    args = parser.parse_args()
    if args.command == "schematic":
        schematic().save(SCHEMATIC, optimize=True)
        print(SCHEMATIC)
    elif args.command == "paint":
        from sagaforge import restyle
        args.dir.mkdir(parents=True, exist_ok=True)
        for index in range(args.count):
            target = args.dir / f"candidate-{index}.png"
            usage = restyle.render_with_openrouter(SCHEMATIC, PROMPT, target, model=args.model, api_key=restyle.openrouter_api_key(),
                                                   aspect_ratio="1:1", image_size="2K")
            print(target, f"{usage['elapsed']:.0f}s", flush=True)
    else:
        squared(Image.open(args.candidate)).save(ICON, optimize=True)
        print(ICON)


if __name__ == "__main__":
    main()
