"""Author the campaign characters' painted animation sheets without changing their game roles.

    uv run python tools/campaign_units.py reference /tmp/campaign-unit-refs
    uv run python tools/campaign_units.py install issa GENERATED.png

Edit each transparent reference with the built-in imagegen tool, asking for the
same eight columns and nine rows. The installer finds the alpha gutters, registers
each pose to its authored anchor, and refuses empty or clipped cells.
The per-character JSON records the feet anchor and scale used by the game.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
import numpy as np
from sagaforge import render3d as r3, restyle
from warband.art import campaign_units as characters, textures, visual_lint


def layout(name: str) -> restyle.Sheet:
    cells = tuple(restyle.Cell(characters.unit_key(name, 0, facing, frame), facing, row,
                              {"facing": facing, "frame": frame})
                  for row, frame in enumerate(textures.FRAMES) for facing in range(textures.FACINGS))
    return restyle.Sheet((160, 192), textures.FACINGS, len(textures.FRAMES), (80, 130), 1.25,
                         cells, (0, 0), grid=False)


def reference_frames(name: str) -> dict[str, Image.Image]:
    sheet = layout(name)
    # The authored mesh is the painter's exact pose/heading reference, never the production image fallback.
    return {cell.key: r3.render(characters._mesh(name, 0, cell.col, cell.tags["frame"]), textures.PROJECTION,
                               scale=sheet.scale, canvas=sheet.logical_size,
                               origin=tuple(value / sheet.scale for value in sheet.origin)) for cell in sheet.cells}


def reference(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in characters.CHARACTERS:
        sheet = layout(name)
        image = Image.new("RGBA", sheet.size)
        frames = reference_frames(name)
        for cell in sheet.cells:
            image.alpha_composite(frames[cell.key], sheet.box(cell)[:2])
        image.save(destination / f"{name}.png")


def _gutter_edges(alpha: np.ndarray, *, axis: int, count: int) -> list[int]:
    """Find the transparent gutters even when imagegen trimmed the sheet's outer margin."""
    occupied = (alpha >= 128).sum(axis=axis) > 5
    starts = np.flatnonzero(occupied & ~np.r_[False, occupied[:-1]])
    ends = np.flatnonzero(occupied & ~np.r_[occupied[1:], False])
    if len(starts) != count:
        raise ValueError(f"expected {count} separate sprite bands, found {len(starts)}")
    return [0, *(int((end + start) // 2) for end, start in zip(ends[:-1], starts[1:])), len(occupied)]


def _solid_box(image: Image.Image) -> tuple[int, int, int, int]:
    box = image.getchannel("A").point(lambda value: 255 if value >= 128 else 0).getbbox()
    if box is None:
        raise ValueError("an animation cell contains no solid figure")
    return box


def install(name: str, source: Path) -> None:
    sheet = layout(name)
    with Image.open(source) as raw:
        if "A" not in raw.getbands() or raw.getchannel("A").getextrema()[0] != 0:
            raise ValueError("campaign sheets require genuine generated transparent alpha")
        generated = raw.convert("RGBA")
    alpha = np.asarray(generated)[..., 3]
    xs = _gutter_edges(alpha, axis=0, count=sheet.cols)
    ys = _gutter_edges(alpha, axis=1, count=sheet.rows)
    frames = {cell.key: generated.crop((xs[cell.col], ys[cell.row], xs[cell.col + 1], ys[cell.row + 1]))
              for cell in sheet.cells}
    original = reference_frames(name)
    # One uniform scale keeps the character's anatomy consistent across the whole animation.
    scale = statistics.median((_solid_box(original[key])[3] - _solid_box(original[key])[1]) /
                              (_solid_box(frame)[3] - _solid_box(frame)[1]) for key, frame in frames.items())
    image = Image.new("RGBA", sheet.size)
    for cell in sheet.cells:
        frame = frames[cell.key]
        frame = frame.resize(tuple(round(side * scale) for side in frame.size), Image.Resampling.LANCZOS)
        target, painted = _solid_box(original[cell.key]), _solid_box(frame)
        dx = round((target[0] + target[2] - painted[0] - painted[2]) / 2)
        dy = target[3] - painted[3]
        placed = Image.new("RGBA", sheet.cell)
        placed.alpha_composite(frame, (dx, dy))
        image.alpha_composite(placed, sheet.box(cell)[:2])
    findings = [finding for cell in sheet.cells for finding in visual_lint.lint_image(cell.key, image.crop(sheet.box(cell)))]
    if findings:
        raise ValueError("\n".join(str(finding) for finding in findings))
    characters.PAINTED.mkdir(parents=True, exist_ok=True)
    image.save(characters.PAINTED / f"{name}.png")
    (characters.PAINTED / f"{name}.json").write_text(json.dumps(sheet.to_json(), indent=1) + "\n")
    print(f"{name}: installed {len(sheet.cells)} transparent, uncut animation frames")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("reference")
    make.add_argument("destination", type=Path)
    add = commands.add_parser("install")
    add.add_argument("name", choices=characters.CHARACTERS)
    add.add_argument("source", type=Path)
    args = parser.parse_args()
    if args.command == "reference":
        reference(args.destination)
    else:
        install(args.name, args.source)


if __name__ == "__main__":
    main()
