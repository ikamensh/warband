"""Automatic checks for visual defects, in the art and in drawn frames.

Two kinds of evidence, both from the mock backend so no window is needed:

* **Images** — every sprite the game registers (:class:`ImageStore` keeps the
  PIL image behind each key).  :func:`lint_images` checks each one for empty
  or clipped content and a chroma-key fringe, painted frames against the
  low-poly render they repaint (the game places the painting where the render
  stood) and for a team recolour that did not take, low-poly subjects' frames
  against each other (feet that hop between frames, a figure that slides
  sideways while it turns, frames that are pixel-identical), poses against
  the unit canvas' padding, and buildings against their footprint.
* **Frames** — after a tick, :func:`lint_frame` reads what the scene drew and
  laid out: texts drawn over each other or off screen, labels and buttons
  whose text is wider than the width they were given (with font-based approximate
  metrics, see :func:`use_real_text_metrics`), HUD panels overlapping each
  other or leaving the screen, sprites drawn at another size than their
  image, and sprites drawn in front of what they stand behind.

Every problem is a :class:`Finding`; ``tools/visual_lint.py`` walks the
game's screens and prints them.  Thresholds are loose on purpose: a finding
is something to look at, and the PNGs the tool writes are for looking.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from saga2d import Game, fonts
from saga2d.testing import overlapping_texts, text_boxes
from saga2d.scene import UI_ORDER_BASE, UI_ORDER_STRIDE
from saga2d.testing.cpu_budget import CpuBudget
from saga2d.ui import Button, Component, Label
from saga2d.ui.components import KEYCAP_GAP
from sagaforge import restyle
from warband import textures
from warband.rules import BUILDINGS, BuildingType, MapTheme, Race, Resource, UnitType

SOLID = 160  # alpha from which a pixel counts as the figure itself, not its shadow or fringe
EDGE = 96  # alpha from which a pixel at the canvas edge means the figure was cut off
CHROMA_SHARE = 0.05  # share of a painted frame's edge pixels that may carry the key's tint before its fringe shows
HOP = 3.0  # logical pixels the feet may move between frames of one facing before it is a hop
SLIDE = 4.0  # logical pixels the figure may shift sideways between frames of one facing
TURN_SLIDE = 6.0  # ... or between facings
FLOAT = 4.0  # logical pixels between the lowest solid pixel and the anchor before a subject floats
RECOLOUR_MIN = 0.01  # share of pixels a team recolour must change
DRIFT = 12.0  # logical pixels a painted figure may sit from the render it repaints
TEXT_SLACK = 0.2  # share of a text box's height above and below the letters (ascender and descender room)
DRIFT_FRAMES = ("stand", "walk1", "walk3", "strike", "chop3")  # the frames compared against their render


@dataclass(frozen=True)
class Finding:
    check: str
    subject: str
    detail: str
    image: Image.Image | None = field(default=None, compare=False, hash=False)

    def __str__(self) -> str:
        return f"{self.check:14s} {self.subject}: {self.detail}"


# -- Images -----------------------------------------------------------------------------


class ImageStore:
    """Keep the PIL image behind every key the game registers with the mock backend."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self.by_handle: dict[str, Image.Image] = {}
        backend = game.backend
        load, update = backend.load_image_from_pil, backend.update_image

        def load_image_from_pil(image: Image.Image) -> str:
            handle = load(image)
            self.by_handle[handle] = image
            return handle

        def update_image(handle: str, image: Image.Image) -> None:
            update(handle, image)
            self.by_handle[handle] = image

        backend.load_image_from_pil = load_image_from_pil
        backend.update_image = update_image

    def image(self, key: str) -> Image.Image:
        return self.by_handle[self.game.assets.image(key)]

    def keys_by_handle(self) -> dict[str, str]:
        return {handle: key for key, handle in self.game.assets._images.items()}


def alpha(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGBA"))[..., 3]


def solid_box(image: Image.Image, threshold: int = SOLID) -> tuple[int, int, int, int] | None:
    """``(left, top, right, bottom)`` of the pixels at least *threshold* opaque, right and bottom exclusive."""
    mask = alpha(image) >= threshold
    if not mask.any():
        return None
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


@dataclass(frozen=True)
class Figure:
    """Where a sprite's solid content lies relative to its anchor, in logical pixels."""

    feet: float  # lowest solid row minus the anchor row: positive is below the point the sprite stands on
    centre: float  # horizontal centre of the lowest quarter of the figure, from the canvas centre
    width: float
    height: float


def pixel_scale(image: Image.Image, placement: textures.Placement) -> float:
    """Pixels per logical unit of *image*: painted sheets are stored at their own scale."""
    return image.width / placement.size[0]


def figure(image: Image.Image, placement: textures.Placement) -> Figure | None:
    box = solid_box(image)
    if box is None:
        return None
    scale = pixel_scale(image, placement)
    left, top, right, bottom = box
    mask = alpha(image) >= SOLID
    band = mask[max(top, bottom - max(1, (bottom - top) // 4)):bottom]
    cols = np.where(band.any(axis=0))[0]
    centre = (cols[0] + cols[-1] + 1) / 2 - image.width / 2
    anchor_row = image.height - placement.drop * scale
    return Figure((bottom - anchor_row) / scale, centre / scale, (right - left) / scale, (bottom - top) / scale)


def lint_image(key: str, image: Image.Image, *, painted: bool = False, cropped: bool = False) -> list[Finding]:
    """Checks that need nothing but the image: empty, cut off by its canvas (unless it was
    *cropped* to its figure on purpose), chroma residue."""
    a = alpha(image)
    findings = []
    if not (a >= SOLID).any():
        return [Finding("empty", key, "no solid pixels", image)]
    edges = {"top": a[0], "bottom": a[-1], "left": a[:, 0], "right": a[:, -1]}
    cut = [side for side, line in edges.items() if (line >= EDGE).any()]
    if cut and not cropped:
        findings.append(Finding("clipped", key, f"solid pixels on the {', '.join(cut)} edge of the canvas", image))
    if painted:
        rgb = np.asarray(image.convert("RGBA")).astype(int)
        edge = (rgb[..., 3] >= EDGE) & (rgb[..., 3] < 250)
        cast = edge & (rgb[..., 0] - rgb[..., 1] > 40) & (rgb[..., 2] - rgb[..., 1] > 40)
        if cast.sum() > CHROMA_SHARE * edge.sum() and cast.sum() > 20:
            findings.append(Finding("chroma", key, f"{cast.sum() / edge.sum():.0%} of the visible edge pixels carry the chroma key's tint", image))
        for x0, y0, x1, y1 in restyle.strays(image):
            findings.append(Finding("stray", key, f"a fragment detached from the figure at ({x0}, {y0})–({x1}, {y1}), within the cell's edge band", image))
    return findings


def lint_subject(subject: str, frames: dict[tuple[int, str], tuple[str, Image.Image]], placement: textures.Placement) -> list[Finding]:
    """One subject's frames against each other: *frames* maps ``(facing, frame)`` to ``(key, image)``."""
    findings = []
    figures = {fk: figure(image, placement) for fk, (key, image) in frames.items()}
    if any(f is None for f in figures.values()):
        return findings  # reported as empty by lint_image
    feet = [f.feet for f in figures.values()]
    if statistics.median(feet) < -FLOAT:
        findings.append(Finding("floating", subject, f"solid content ends {-statistics.median(feet):.1f} px above the anchor", frames[next(iter(frames))][1]))
    by_facing: dict[int, list[tuple[str, Figure]]] = {}
    for (facing, frame), fig in figures.items():
        by_facing.setdefault(facing, []).append((frame, fig))
    for facing, items in by_facing.items():
        median_feet = statistics.median(f.feet for _, f in items)
        median_centre = statistics.median(f.centre for _, f in items)
        for frame, fig in items:
            key, image = frames[(facing, frame)]
            if abs(fig.feet - median_feet) > HOP:
                findings.append(Finding("hop", key, f"feet {fig.feet - median_feet:+.1f} px from the facing's median", image))
            if abs(fig.centre - median_centre) > SLIDE:
                findings.append(Finding("slide", key, f"figure {fig.centre - median_centre:+.1f} px sideways from the facing's median", image))
    stands = {facing: fig for (facing, frame), fig in figures.items() if frame == "stand"}
    if len(stands) > 1:
        centre = statistics.median(f.centre for f in stands.values())
        for facing, fig in stands.items():
            if abs(fig.centre - centre) > TURN_SLIDE:
                key, image = frames[(facing, "stand")]
                findings.append(Finding("turn-slide", key, f"standing figure {fig.centre - centre:+.1f} px sideways from the other facings", image))
    for facing, items in by_facing.items():
        seen: dict[bytes, str] = {}
        for frame, _ in items:
            key, image = frames[(facing, frame)]
            digest = image.tobytes()
            if digest in seen and {frame, seen[digest]} <= set(textures.WALK_FRAMES) | set(textures.ATTACK_FRAMES) | set(textures.CHOP_FRAMES):
                findings.append(Finding("identical", key, f"pixel-identical to frame {seen[digest]!r}", image))
            seen.setdefault(digest, frame)
    return findings


def lint_building(key: str, image: Image.Image, placement: textures.Placement, size: int) -> list[Finding]:
    fig = figure(image, placement)
    if fig is None:
        return []
    findings = []
    footprint = size * textures.TILE
    front = footprint / 2  # the anchor is the footprint's centre
    if fig.width > footprint * 1.5:
        findings.append(Finding("footprint", key, f"figure {fig.width:.0f} px wide on a {size}×{size} footprint ({footprint} px)", image))
    if fig.feet < front - 10:
        findings.append(Finding("floating", key, f"solid content ends {front - fig.feet:.1f} px above the footprint's front edge", image))
    if fig.feet > front + 10:
        findings.append(Finding("overhang", key, f"solid content reaches {fig.feet - front:.1f} px past the footprint's front edge", image))
    return findings


def lint_recolour(key: str, base: Image.Image, other: Image.Image) -> list[Finding]:
    a, b = np.asarray(base.convert("RGBA")), np.asarray(other.convert("RGBA"))
    if a.shape != b.shape:
        return [Finding("recolour", key, f"team frame is {other.size}, the base {base.size}", other)]
    visible = a[..., 3] >= SOLID
    changed = (np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).sum(axis=-1) > 12) & visible
    share = changed.sum() / max(1, visible.sum())
    if share < RECOLOUR_MIN:
        return [Finding("recolour", key, f"team colour changed {share:.1%} of the figure", other)]
    return []


def centroid(image: Image.Image, placement: textures.Placement) -> tuple[float, float] | None:
    """The solid pixels' mean position from the anchor, in logical units (x right, y down)."""
    mask = alpha(image) >= SOLID
    if not mask.any():
        return None
    scale = pixel_scale(image, placement)
    ys, xs = np.nonzero(mask)
    return ((xs.mean() + 0.5 - image.width / 2) / scale, (ys.mean() + 0.5 - (image.height - placement.drop * scale)) / scale)


def side_by_side(painted: Image.Image, placement: textures.Placement, render: Image.Image, render_placement: textures.Placement) -> Image.Image:
    """Both on one canvas, anchors aligned, for the eye."""
    sp, sr = pixel_scale(painted, placement), pixel_scale(render, render_placement)
    render = render.resize((round(render.width * sp / sr), round(render.height * sp / sr)), Image.LANCZOS) if sp != sr else render
    ap, ar = painted.height - placement.drop * sp, render.height - render_placement.drop * sp
    top = max(ap, ar)
    height = round(top + max(painted.height - ap, render.height - ar))
    canvas = Image.new("RGBA", (painted.width + render.width, height), (60, 90, 50, 255))
    canvas.alpha_composite(painted.convert("RGBA"), (0, round(top - ap)))
    canvas.alpha_composite(render.convert("RGBA"), (painted.width, round(top - ar)))
    ImageDraw.Draw(canvas).line((0, top, canvas.width, top), fill=(255, 220, 80, 255))
    return canvas


def lint_drift(game: Game, store: ImageStore, *, budget: CpuBudget | None = None) -> list[Finding]:
    """Painted unit frames against the low-poly renders they repaint: the game places the
    painting where the render stood, so a figure that moved in the painting stands beside its
    ring, health bar and the point it is ordered to."""
    from sagaforge import render3d as r3

    findings = []
    for name, race, unit_type, carrying, player in unit_subjects():
        if textures.restyled_frames(race, unit_type, carrying) is None:
            continue
        frames = [f for f in DRIFT_FRAMES if f in textures.FRAMES or (unit_type is UnitType.PEASANT and carrying is None)]
        for facing in range(textures.FACINGS):
            for frame in frames:
                if budget is not None:
                    budget.checkpoint()
                key = textures.unit_key(unit_type, player, facing, frame, carrying, race)
                painted, placement = store.image(key), textures.placements[key]
                mesh = r3.rotate_z(textures._unit(unit_type, player, frame, carrying, race), facing * 45 - 90)
                reach = r3.bounds(mesh, textures.PROJECTION)[3] + textures.PAD
                if reach > textures.DROP_UNIT:
                    findings.append(Finding("drop", key, f"the render reaches {reach:.1f} px below the feet, past the unit canvas' {textures.DROP_UNIT:.1f}"))
                render = textures._prop(f"{key}#render", mesh, max(textures.DROP_UNIT, math.ceil(reach)), 2.0)
                render_placement = textures.placements.pop(f"{key}#render")
                a, b = centroid(painted, placement), centroid(render, render_placement)
                if a is None or b is None:
                    continue
                dx, dy = a[0] - b[0], a[1] - b[1]
                if math.hypot(dx, dy) > DRIFT:
                    findings.append(Finding("drift", key, f"painted figure {dx:+.0f}, {dy:+.0f} px from the render it repaints",
                                            side_by_side(painted, placement, render, render_placement)))
    return findings


def register_everything(game: Game, *, players: tuple[int, ...] = (0, 1), budget: CpuBudget | None = None) -> None:
    """Register every image a match can show: units of every race in every frame and facing,
    buildings in every look, trees and rocks of every theme, mines, portraits and emblems."""
    from warband.production import production_image
    from warband.rules import Upgrade

    textures.register_static(game)
    for theme in MapTheme:
        textures.register_theme(game, theme)
    for variant in range(textures.MINE_VARIANTS):
        textures.mine_image(game, variant)
    for race in Race:
        for _ in textures.warm_units(game, [0], [race]):
            if budget is not None:
                budget.checkpoint()
        for _name, _race, unit_type, carrying, player in unit_subjects(players[1:]):
            if _race is race:
                textures.unit_image(game, unit_type, player, 2, "stand", carrying, race=race)  # one frame per team, for the recolour check
        for player in players:
            for building_type in BuildingType:
                if building_type is BuildingType.GOLD_MINE:
                    continue
                for look in textures.BUILDING_LOOKS:
                    textures.building_image(game, building_type, player, race, look)
                    if budget is not None:
                        budget.checkpoint()
        for subject in (*UnitType, *BuildingType):
            textures.portrait_image(game, subject, 0, race)
    for upgrade in Upgrade:
        production_image(game, upgrade, 0)


def unit_subjects(players: tuple[int, ...] = (0,)) -> Iterator[tuple[str, Race, UnitType, Resource | None, int]]:
    for race in Race:
        for unit_type in UnitType:
            carries: tuple[Resource | None, ...] = (None, Resource.GOLD, Resource.LUMBER) if unit_type is UnitType.PEASANT else (None,)
            for carrying in carries:
                for player in players:
                    name = f"{race.value}.{unit_type.value}" + (f".{carrying.value}" if carrying else "") + f".{player}"
                    yield name, race, unit_type, carrying, player


def lint_images(game: Game, store: ImageStore, *, budget: CpuBudget | None = None) -> list[Finding]:
    """Every check on every registered image (call :func:`register_everything` first)."""
    findings: list[Finding] = []
    painted_keys = {key for key in game.assets._images if key.startswith(("unit.", "building.", "portrait."))}
    for key in list(game.assets._images):
        if budget is not None:
            budget.checkpoint()
        if key not in textures.placements and not key.startswith(("portrait.", "production.")):
            continue  # the ground, fog, minimap and the soft effect images are not figures
        findings += lint_image(key, store.image(key), painted=key in painted_keys and textures.RESTYLED_ART,
                               cropped=key.startswith("portrait."))
    for name, race, unit_type, carrying, player in unit_subjects():
        if budget is not None:
            budget.checkpoint()
        frames = textures.FRAMES + textures.CHOP_FRAMES if unit_type is UnitType.PEASANT and carrying is None else textures.FRAMES
        keyed = {(facing, frame): (key, store.image(key))
                 for facing in range(textures.FACINGS) for frame in frames
                 for key in [textures.unit_key(unit_type, player, facing, frame, carrying, race)]}
        if textures.restyled_frames(race, unit_type, carrying) is None:
            findings += lint_subject(name, keyed, textures.placements[next(iter(keyed.values()))[0]])  # painted frames: lint_drift
        base = textures.unit_key(unit_type, 0, 2, "stand", carrying, race)
        team = textures.unit_key(unit_type, 1, 2, "stand", carrying, race)
        if game.assets.has_image(team):
            findings += lint_recolour(team, store.image(base), store.image(team))
    for race in Race:
        for building_type in BuildingType:
            if building_type is BuildingType.GOLD_MINE:
                continue
            for look in textures.BUILDING_LOOKS:
                key = textures.building_key(building_type, 0, race, look)
                if not game.assets.has_image(key):
                    continue
                findings += lint_building(key, store.image(key), textures.placements[key], BUILDINGS[building_type].size)
                team = textures.building_key(building_type, 1, race, look)
                if game.assets.has_image(team):
                    findings += lint_recolour(team, store.image(key), store.image(team))
    for key in list(game.assets._images):
        if key.startswith(("tree.", "rock.", "mine.")):
            fig = figure(store.image(key), textures.placements[key])
            if fig is not None and fig.feet < -FLOAT:
                findings.append(Finding("floating", key, f"solid content ends {-fig.feet:.1f} px above the anchor", store.image(key)))
    return findings + lint_drift(game, store, budget=budget)


# -- Frames -----------------------------------------------------------------------------


def use_real_text_metrics(game: Game) -> None:
    """Approximate native text on the mock backend using the bundled Nunito faces.

    PIL and native font metrics differ: these checks identify candidates for
    inspection. The tool's native lane also checks layout using pyglet metrics.
    """
    cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def font_for(name: str | None, size: int) -> ImageFont.FreeTypeFont:
        file = fonts.FILES.get(name or fonts.REGULAR, fonts.FILES[fonts.REGULAR])
        key = (file, size)
        if key not in cache:
            # Glyphs are laid out at the Retina size (twice the point size, at 96 dpi) and halved, as pyglet does.
            cache[key] = ImageFont.truetype(str(fonts.FONT_DIR / file), max(1, round(size * 2 * 96 / 72)))
        return cache[key]

    def measure_text(text: str, font_size: int, font: str | None = None) -> tuple[int, int]:
        if not str(text):
            return (0, 0)  # an empty label takes no room, as on pyglet
        face = font_for(font, font_size)
        ascent, descent = face.getmetrics()
        return (math.ceil(face.getlength(str(text)) / 2), (ascent + descent) // 2)

    game.backend.measure_text = measure_text


def _visible(component: Component) -> bool:
    node: Component | None = component
    while node is not None:
        if not node.visible:
            return False
        node = node.parent
    return True


def _label(component: Component) -> str:
    text = getattr(component, "text", "")
    return f"{type(component).__name__}({text!r})" if text else type(component).__name__


def lint_layout(game: Game, scene: Any) -> list[Finding]:
    """The top scene's UI tree: text wider than its box, panels over each other or off screen."""
    backend = game.backend
    width, height = game.resolution
    findings = []
    for component in scene.ui.walk():
        if not _visible(component):
            continue
        x, y, w, h = component.bounds
        if isinstance(component, Label) and component._width is not None and not component._wrap and component.text:
            resolved = component._resolve()
            tw, _ = backend.measure_text(component.text, resolved.font_size, resolved.font)
            if tw > w + 1:
                findings.append(Finding("overflow", _label(component), f"text {tw} px wide in a {w} px label"))
        elif isinstance(component, Button) and component._width is not None:
            resolved = component._resolve()
            iw, tw, kw, _ = component._content_size(resolved)
            content = iw + tw + kw + KEYCAP_GAP * max(0, sum(bool(v) for v in (iw, tw, kw)) - 1) + 2 * resolved.padding
            if content > w + 1:
                findings.append(Finding("overflow", _label(component), f"content {content} px wide in a {w} px button"))
        if x < -1 or y < -1 or x + w > width + 1 or y + h > height + 1:
            findings.append(Finding("off-screen", _label(component), f"bounds ({x}, {y}, {w}, {h}) leave the {width}×{height} screen"))
    roots = [c for c in scene.ui.children if _visible(c)]
    for i, a in enumerate(roots):
        ax, ay, aw, ah = a.bounds
        for b in roots[i + 1:]:
            bx, by, bw, bh = b.bounds
            if min(ax + aw, bx + bw) - max(ax, bx) > 2 and min(ay + ah, by + bh) - max(ay, by) > 2:
                findings.append(Finding("panel-overlap", f"{_label(a)} × {_label(b)}", f"{a.bounds} over {b.bounds}"))
    return findings


def lint_texts(game: Game) -> list[Finding]:
    """Check screen text in the active scene; overlays may cover paused animations below."""
    width, height = game.resolution
    findings = []
    for a, b in overlapping_texts(game, top_scene_only=len(game.scenes) > 1):
        # A text box spans ascender to descender; the letters fill about its middle three fifths.
        glyph_top = max(a.top + a.height * TEXT_SLACK, b.top + b.height * TEXT_SLACK)
        glyph_bottom = min(a.bottom - a.height * TEXT_SLACK, b.bottom - b.height * TEXT_SLACK)
        if glyph_bottom - glyph_top <= 2:
            continue
        findings.append(Finding("text-overlap", f"{a.text!r} × {b.text!r}", f"{a} over {b}"))
    floor = UI_ORDER_BASE + (len(game.scenes) - 1) * UI_ORDER_STRIDE
    for box in text_boxes(game.backend):
        if len(game.scenes) > 1 and box.order < floor:
            continue
        if box.space == "screen" and (box.left < -1 or box.top < -1 or box.right > width + 1 or box.bottom > height + 1):
            findings.append(Finding("text-off-screen", repr(box.text), str(box)))
    return findings


def lint_sprites(game: Game, store: ImageStore) -> list[Finding]:
    """World sprites with a placement: drawn at their image's size, and in front only of what they
    stand in front of (two overlapping sprites whose draw order contradicts their feet)."""
    findings = []
    props = []
    keys = store.keys_by_handle()
    for s in game.backend.sprites.values():
        if not s["visible"] or s["space"] != "world":
            continue
        key = keys.get(s["image"])
        placement = textures.placements.get(key) if key else None
        if placement is None:
            continue
        expected = placement.size
        if abs(s["width"] - expected[0]) > 1 or abs(s["height"] - expected[1]) > 1:
            findings.append(Finding("stretched", key, f"drawn {s['width']:.0f}×{s['height']:.0f}, the image is {expected[0]:.0f}×{expected[1]:.0f}"))
        line = s["y"] + s["height"] - placement.ground  # a unit's feet, a building's front edge
        props.append((key, s["x"], s["y"], s["x"] + s["width"], s["y"] + s["height"], line, s["order"]))
    wrong = []
    for i, a in enumerate(props):
        for b in props[i + 1:]:
            if min(a[3], b[3]) - max(a[1], b[1]) <= 0 or min(a[4], b[4]) - max(a[2], b[2]) <= 0:
                continue
            behind, front = (a, b) if a[5] < b[5] else (b, a)
            if front[5] - behind[5] > 4 and behind[6] > front[6]:
                wrong.append((behind, front))
    if wrong:
        behind, front = wrong[0]
        findings.append(Finding("draw-order", f"{len(wrong)} pairs", f"e.g. {behind[0]} (standing at y {behind[5]:.0f}) drawn over {front[0]} (at y {front[5]:.0f})"))
    return findings


def lint_frame(game: Game, store: ImageStore | None = None) -> list[Finding]:
    """Everything the last tick drew and laid out on the top scene."""
    scene = game.scene
    findings = lint_texts(game) + lint_layout(game, scene)
    if store is not None:
        findings += lint_sprites(game, store)
    return findings


# -- Pixels -----------------------------------------------------------------------------


def lint_pixels(name: str, frame: Image.Image) -> list[Finding]:
    """A captured frame: chroma-key residue anywhere on screen."""
    rgb = np.asarray(frame.convert("RGB")).astype(int)
    magenta = (rgb[..., 0] > 200) & (rgb[..., 2] > 200) & (rgb[..., 1] < 90)
    if magenta.sum() > 4:
        return [Finding("chroma", name, f"{int(magenta.sum())} magenta pixels on screen", frame)]
    return []


# -- Evidence ---------------------------------------------------------------------------


def evidence_image(finding: Finding, placement: textures.Placement | None) -> Image.Image | None:
    """The finding's image enlarged, with the anchor row and canvas edge marked."""
    if finding.image is None:
        return None
    image = finding.image.convert("RGBA")
    zoom = 3 if max(image.size) < 300 else 1
    big = image.resize((image.width * zoom, image.height * zoom), Image.NEAREST)
    canvas = Image.new("RGBA", big.size, (60, 90, 50, 255))
    canvas.alpha_composite(big)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width - 1, canvas.height - 1), outline=(255, 80, 80, 255))
    if placement is not None:
        y = (image.height - placement.drop * pixel_scale(image, placement)) * zoom
        draw.line((0, y, canvas.width, y), fill=(255, 220, 80, 255))
    return canvas


def save_evidence(findings: list[Finding], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for index, finding in enumerate(findings):
        image = evidence_image(finding, textures.placements.get(finding.subject))
        if image is None:
            continue
        path = directory / f"{index:03d}_{finding.check}_{finding.subject.replace('/', '_')[:60]}.png"
        image.save(path)
        written.append(path)
    return written
