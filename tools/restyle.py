"""Re-render Warband's unit sprites with an image model (see ``sagaforge.restyle``).

    uv run python tools/restyle.py dump DIR                 # one sheet + prompt per unit
    uv run python tools/restyle.py render DIR               # repaint the sheets (Codex by default)
    uv run python tools/restyle.py cut DIR                   # key, register, check; install into warband/assets/restyled
    uv run python tools/restyle.py preview DIR OUT_DIR       # walk/attack GIFs, original above restyled

``--race`` and ``--units`` narrow every step; ``render --provider openrouter --model ...``
uses an OpenRouter image model instead of Codex's built-in tool.  The sheets are rendered
for player 0; the game recolours them per player.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from sagaforge import render3d as r3  # noqa: E402
from sagaforge import restyle  # noqa: E402
from warband import textures  # noqa: E402
from warband.rules import Race, Resource, UnitType  # noqa: E402

RESTYLED = Path(__file__).resolve().parent.parent / "warband" / "assets" / "restyled"
SCALE = 2.0  # sheet pixels per logical unit
MARGIN = 6  # empty pixels around the widest frame inside a cell

STYLE = ("Re-render every cell as a polished, appealing game sprite in a rich hand-painted fantasy style "
         "(Warcraft 2 / Heroes of Might and Magic feel): readable silhouette, volumetric shading, metal highlights, "
         "cloth folds, light from the upper left, a small soft dark contact shadow under the feet. Sprites will be "
         "shown at about half this size, so keep shapes bold and edges crisp.")

FACINGS = "right, down-right, down (towards the viewer), down-left, left, up-left, up (away from the viewer), up-right"
FRAME_NAMES = {"stand": "standing", "walk1": "walk frame 1", "walk2": "walk frame 2", "attack": "attack",
               "chop1": "chopping a tree, axe raised", "chop2": "chopping, fast downswing", "chop3": "chopping, axe contact",
               "chop4": "chopping, recovery"}

SUBJECTS: dict[tuple[Race, UnitType], str] = {
    (Race.HUMAN, UnitType.PEASANT): "a human peasant worker in a blue tunic (blue is the team colour and must stay this blue) "
                                    "and a cloth cap, carrying a woodcutter's axe",
    (Race.HUMAN, UnitType.FOOTMAN): "a human footman: a stocky soldier in a steel helmet with a blue plume and mail, blue tunic "
                                    "(blue is the team colour and must stay this blue), a kite shield with a gold cross, and a sword",
    (Race.HUMAN, UnitType.ARCHER): "a human archer in a dark green hooded cloak over a blue tunic (blue is the team colour and must "
                                   "stay this blue), with a longbow and a quiver of arrows",
    (Race.HUMAN, UnitType.KNIGHT): "a human knight in full plate on an armoured warhorse with blue caparison and trim (blue is the "
                                   "team colour and must stay this blue), carrying a lance and a shield",
    (Race.HUMAN, UnitType.SCOUT): "a human scout: a light rider in leather armour and a blue tunic (blue is the team colour and must "
                                  "stay this blue) on a fast unarmoured horse",
    (Race.HUMAN, UnitType.CATAPULT): "a human catapult: a wooden siege engine on wheels with a throwing arm, a boulder and a blue "
                                     "team pennant (blue is the team colour and must stay this blue); the attack row swings the arm",
    (Race.HUMAN, UnitType.CLERIC): "a human cleric: a healer in a pale hooded robe with a blue sash (blue is the team colour and must "
                                   "stay this blue), holding a staff",
}
CARRY = {Resource.GOLD: ", carrying a heavy sack of gold", Resource.LUMBER: ", carrying a bundle of lumber on the shoulder"}


def subject_name(race: Race, unit: UnitType, carrying: Resource | None) -> str:
    return f"{race.value}.{unit.value}" + (f".{carrying.value}" if carrying else "")


def subjects(race: Race, units: list[UnitType]) -> list[tuple[UnitType, Resource | None]]:
    out: list[tuple[UnitType, Resource | None]] = []
    for unit in units:
        out.append((unit, None))
        if unit is UnitType.PEASANT:
            out += [(unit, Resource.GOLD), (unit, Resource.LUMBER)]
    return out


def unit_frames(unit: UnitType, carrying: Resource | None) -> tuple[str, ...]:
    return textures.FRAMES + textures.CHOP_FRAMES if unit is UnitType.PEASANT and carrying is None else textures.FRAMES


def build_sheet(race: Race, unit: UnitType, carrying: Resource | None) -> tuple[restyle.Sheet, dict[str, Image.Image]]:
    """The unit's frames laid out facings across, frames down, every frame's feet on the same point."""
    frames = unit_frames(unit, carrying)
    meshes = {(frame, facing): r3.rotate_z(textures._unit(unit, 0, frame, carrying, race), facing * 45 - 90)
              for frame in frames for facing in range(textures.FACINGS)}
    bounds = [r3.bounds(m, textures.PROJECTION) for m in meshes.values()]
    half_w = max(max(-b[0], b[2]) for b in bounds)
    top, below = max(-b[1] for b in bounds), max(b[3] for b in bounds)
    cell = (int(2 * half_w * SCALE) + 2 * MARGIN, int((top + below) * SCALE) + 2 * MARGIN)
    origin = (cell[0] / 2, MARGIN + top * SCALE)
    keys = [(textures.unit_key(unit, 0, facing, frame, carrying, race), {"frame": frame, "facing": facing})
            for frame in frames for facing in range(textures.FACINGS)]
    sheet = restyle.Sheet.layout(keys, cols=textures.FACINGS, cell=cell, origin=origin, scale=SCALE)
    images = {key: r3.render(meshes[(tags["frame"], tags["facing"])], textures.PROJECTION, scale=SCALE,
                             canvas=(cell[0] / SCALE, cell[1] / SCALE), origin=(origin[0] / SCALE, origin[1] / SCALE))
              for key, tags in keys}
    return sheet, images


def prompt(sheet: restyle.Sheet, race: Race, unit: UnitType, carrying: Resource | None) -> str:
    frames = unit_frames(unit, carrying)
    rows = ", ".join(FRAME_NAMES[f] for f in frames)
    w, h = sheet.size
    return (f"Edit target: the attached sprite sheet of one unit from a 2D real-time strategy game (Warcraft 2 style, "
            f"3/4 top-down camera). It is {w}x{h} px: a grid of {sheet.rows} rows x {sheet.cols} columns of "
            f"{sheet.cell[0]}x{sheet.cell[1]} px cells, surrounded by an empty margin, on a flat magenta #FF00FF background. "
            f"Thin dark grey lines mark the cell borders; keep the lines and the margin exactly where they are, and keep each "
            f"figure centred in its own cell exactly where it is now. Rows, top to bottom: {rows}. Columns, left to right: "
            f"the unit facing {FACINGS}.\n\nThe unit is {SUBJECTS[(race, unit)]}{CARRY.get(carrying, '')}.\n\n{STYLE}\n\n"
            f"Keep exactly: each figure's position, scale, pose, facing direction, limb and weapon placement, and feet position. "
            f"Every cell keeps the flat #FF00FF background with nothing else on it: no gradients, glows, outlines, text, borders "
            f"or extra objects. Output the same {w}x{h} layout.")


def selected(args: argparse.Namespace) -> list[tuple[Race, UnitType, Resource | None]]:
    race = Race(args.race)
    units = [UnitType(u) for u in args.units.split(",")] if args.units else list(UnitType)
    return [(race, unit, carrying) for unit, carrying in subjects(race, units)]


def cmd_dump(args: argparse.Namespace) -> None:
    args.dir.mkdir(parents=True, exist_ok=True)
    for race, unit, carrying in selected(args):
        name = subject_name(race, unit, carrying)
        sheet, images = build_sheet(race, unit, carrying)
        sheet.save(args.dir / name, images)
        (args.dir / f"{name}.prompt.txt").write_text(prompt(sheet, race, unit, carrying))
        print(f"{name}: {sheet.size[0]}x{sheet.size[1]}, {len(sheet.cells)} cells of {sheet.cell[0]}x{sheet.cell[1]}")


def cmd_render(args: argparse.Namespace) -> None:
    def one(name: str) -> str:
        out = args.dir / name / f"{args.provider}.png"
        if out.exists() and not args.force:
            return f"{name}: kept {out.name}"
        text = (args.dir / f"{name}.prompt.txt").read_text()
        if args.provider == "codex":
            restyle.render_with_codex(args.dir / f"{name}.png", text, out)
        else:
            usage = restyle.render_with_openrouter(args.dir / f"{name}.png", text, out, model=args.model, api_key=restyle.openrouter_api_key())
            (args.dir / name / "usage.json").write_text(json.dumps(usage, indent=1))
        return f"{name}: wrote {out}"

    names = [subject_name(*s) for s in selected(args)]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for line in pool.map(one, names):
            print(line)


def cmd_cut(args: argparse.Namespace) -> None:
    RESTYLED.mkdir(parents=True, exist_ok=True)
    for race, unit, carrying in selected(args):
        name = subject_name(race, unit, carrying)
        rendered = args.dir / name / f"{args.provider}.png"
        if not rendered.exists():
            print(f"{name}: no {rendered.name} yet")
            continue
        sheet = restyle.Sheet.load(args.dir / name)
        result = restyle.cut(sheet, Image.open(rendered), Image.open(args.dir / f"{name}.png"))
        flagged = result.flagged
        print(f"{name}: scale {result.registration.scale:.2f} shift ({result.registration.dx:.0f}, {result.registration.dy:.0f}), "
              f"{len(flagged)} of {len(result.report)} cells flagged")
        for r in flagged:
            print(f"   {r.key}: coverage {r.coverage:.3f} vs {r.original_coverage:.3f}, drift {r.drift:.0f}px, feet {r.feet_drift:+.0f}px, edge {r.touches_edge}")
        if len(flagged) > args.tolerate:
            print(f"   rejected (more than {args.tolerate} flagged); re-render or raise --tolerate")
            continue
        restyle.save_frames(result, sheet, RESTYLED / name)
        print(f"   installed {RESTYLED / name}.png")


def cmd_preview(args: argparse.Namespace) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    for race, unit, carrying in selected(args):
        name = subject_name(race, unit, carrying)
        if not restyle.file(RESTYLED / name, "png").exists():
            continue
        sheet, frames = restyle.load_frames(RESTYLED / name)
        original_sheet, original = build_sheet(race, unit, carrying)
        facings = range(textures.FACINGS)
        sequence = ["walk1", "walk2"] * 3 + ["stand", "attack", "attack", "stand"]
        if unit is UnitType.PEASANT and carrying is None:
            sequence += ["chop1", "chop2", "chop3", "chop4"] * 2
        gif_frames = []
        for frame in sequence:
            keys = [sheet.find(frame=frame, facing=f).key for f in facings]
            top = restyle.strip(original, keys, scale=0.5)
            bottom = restyle.strip(frames, keys, scale=0.5)
            both = Image.new("RGBA", (top.size[0], top.size[1] + bottom.size[1]))
            both.paste(top, (0, 0))
            both.paste(bottom, (0, top.size[1]))
            gif_frames.append(both)
        restyle.gif(gif_frames, args.out / f"{name}.gif", ms=180)
        print(f"{name}: {args.out / name}.gif")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--race", default="human")
    parser.add_argument("--units", default=None, help="comma-separated unit types (default: all)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("dump"); p.add_argument("dir", type=Path); p.set_defaults(run=cmd_dump)
    p = sub.add_parser("render"); p.add_argument("dir", type=Path); p.add_argument("--provider", default="codex", choices=["codex", "openrouter"])
    p.add_argument("--model", default="google/gemini-3.1-flash-image"); p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--force", action="store_true"); p.set_defaults(run=cmd_render)
    p = sub.add_parser("cut"); p.add_argument("dir", type=Path); p.add_argument("--provider", default="codex")
    p.add_argument("--tolerate", type=int, default=2, help="flagged cells allowed before a sheet is rejected"); p.set_defaults(run=cmd_cut)
    p = sub.add_parser("preview"); p.add_argument("dir", type=Path); p.add_argument("out", type=Path); p.set_defaults(run=cmd_preview)
    p = sub.add_parser("showcase"); p.add_argument("out", type=Path); p.add_argument("--seconds", type=float, default=6.0)
    p.add_argument("--zoom", type=float, default=1.5); p.set_defaults(run=cmd_showcase)
    args = parser.parse_args()
    args.run(args)



def cmd_showcase(args: argparse.Namespace) -> None:
    """A scripted skirmish through the real renderer, saved as a GIF: two human armies
    (so the second one shows the recolouring) attack-move into each other while peasants
    chop the wood behind the line.  The display must be awake."""
    from saga2d import Game, fonts
    from warband.view import to_world
    from warband.rules import Terrain
    from warband.scene import new_game
    from warband.style import build_theme

    game = Game("Warband showcase", resolution=(960, 600), backend="pyglet", visible=False, theme=build_theme())
    try:
        fonts.load(game)
        scene = new_game(seed=3, races=[Race.HUMAN, Race.HUMAN], settings={"tutorial": False, "edge_scroll": False})
        game.push(scene)
        world = scene.world
        for _ in range(160):  # the title banner passes
            game.tick(1 / 30)
        hall = world.player_buildings(0)[0]
        hx, hy = hall.center

        def open_ground(x0: int, y0: int, w: int, h: int) -> bool:
            return all(world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.GRASS and world.building_at((x, y)) is None
                       for x in range(x0, x0 + w) for y in range(y0, y0 + h))

        field = min(((x, y) for x in range(world.width - 12) for y in range(world.height - 8) if open_ground(x, y, 12, 8)),
                    key=lambda p: (p[0] - hx) ** 2 + (p[1] - hy) ** 2)  # the nearest meadow that fits two lines
        cx, cy = field[0] + 1.5, field[1] + 1.0
        line = [UnitType.FOOTMAN, UnitType.KNIGHT, UnitType.ARCHER, UnitType.FOOTMAN, UnitType.CLERIC, UnitType.SCOUT, UnitType.CATAPULT]
        north = [world.spawn_unit(0, unit, (cx + i * 1.3, cy)) for i, unit in enumerate(line)]
        south = [world.spawn_unit(1, unit, (cx + i * 1.3, cy + 6)) for i, unit in enumerate(line)]
        world.reveal_all(0)
        world.attack_move([u.id for u in north], (cx + 4, cy + 6))
        world.attack_move([u.id for u in south], (cx + 4, cy))
        trees = [(x, y) for x in range(int(cx) - 10, int(cx) + 16) for y in range(int(cy) - 8, int(cy) + 14)
                 if world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.TREES]
        for peasant in world.player_units(0):
            if peasant.type is UnitType.PEASANT and trees:
                nearest = min(trees, key=lambda t: (t[0] - peasant.x) ** 2 + (t[1] - peasant.y) ** 2)
                world.harvest([peasant.id], nearest)
        scene.camera.zoom = args.zoom
        scene.camera.center_on(*to_world((cx + 4, cy + 4.5)))
        frames = []
        for tick in range(int(args.seconds * 30)):
            game.tick(1 / 30)
            if tick % 2 == 0:
                frame = game.backend.capture_frame().convert("RGB")
                frames.append(frame.resize((frame.size[0] // 2, frame.size[1] // 2), Image.LANCZOS) if frame.size[0] > 1000 else frame)
        frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=66, loop=0)
        print(f"wrote {args.out}: {len(frames)} frames of {frames[0].size[0]}x{frames[0].size[1]}")
    finally:
        game.close()

if __name__ == "__main__":
    main()
