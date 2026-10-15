"""The dialogue's scenery: painted locations and an animated aether briefing chamber.

The stage owns presentation time alone. Portrait registration stays in dialog.py
so the same authored face is shared by the mission HUD, journal and conversation.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from saga2d import fonts
from saga2d import Scene
from warband.art.production import draw_production_icon
from warband.story.briefing import BriefingChart
from warband.story.campaign import Speaker

ASSETS = Path(__file__).resolve().parents[1] / "assets"
CYAN = (143, 224, 227, 255)
BRASS = (176, 144, 83, 255)


def register_art(game, path: str) -> str:
    key = f"story.scenery.{path}"
    if not game.assets.has_image(key):
        with Image.open(ASSETS / path) as picture:
            game.assets.image_from_pil(key, picture)
    return key


def _projection(game, speaker: Speaker) -> str | None:
    """An oval aperture and gentle spectral tint, composited from the original portrait at load time."""
    if speaker.portrait is None:
        return None
    key = f"story.projection.{speaker.portrait}"
    if not game.assets.has_image(key):
        size = (288, 440)
        with Image.open(ASSETS / speaker.portrait) as source:
            picture = ImageOps.fit(source.convert("RGBA"), size, centering=(.5, .35))
        mask = Image.new("L", size)
        ImageDraw.Draw(mask).ellipse((3, 3, size[0] - 3, size[1] - 3), fill=230)
        picture = Image.blend(picture, Image.new("RGBA", size, (53, 114, 136, 255)), .14)
        picture.putalpha(mask.filter(ImageFilter.GaussianBlur(5)))
        game.assets.image_from_pil(key, picture)
    return key


class DialogStage:
    def __init__(self, scene: Scene, backdrop: str, chart: BriefingChart | None) -> None:
        self.scene = scene
        self.chart = chart
        self.key = register_art(scene.game, "campaign/scenes/portal-room.webp" if chart else backdrop)
        self.clock = 0.0
        self.age = 0.0
        self.transmission_age = 0.0
        self.speaker: Speaker | None = None
        self.joined: dict[str, Speaker] = {}
        self.visited: set[int] = set()

    def attend(self, speaker: Speaker | None, index: int) -> None:
        self.age = 0.0
        self.visited.add(index)
        if speaker is not self.speaker:
            self.transmission_age = 0.0
        self.speaker = speaker
        if speaker is not None:
            self.joined[speaker.name] = speaker

    def update(self, dt: float) -> None:
        self.clock += dt
        self.age += dt
        self.transmission_age += dt

    def draw(self, index: int, panel_top: float) -> None:
        scene = self.scene
        w, h = scene.game.resolution
        iw, ih = scene.game.backend.get_image_size(scene.game.assets.image(self.key))
        scale = max(w / iw, h / ih)
        # A nearly imperceptible drift keeps a painted location alive without moving the text.
        zoom = 1 if self.chart else 1.025 + .008 * math.sin(self.clock * .12)
        sw, sh = iw * scale * zoom, ih * scale * zoom
        ox, oy = (w - sw) / 2, (h - sh) / 2 + (36 if self.chart else 0)
        scene.draw_image(self.key, ox, oy, sw, sh)
        with scene.screen_layer(1):
            scene.draw_rect(0, 0, w, h, (3, 10, 17, 32))
            # Gradients are small fixed strips, independent of output pixel density.
            for n in range(16):
                scene.draw_rect(0, n * 8, w, 8, (5, 12, 20, round(245 * (1 - n / 16))))
                scene.draw_rect(0, panel_top - 100 + n * 8, w, 8, (5, 12, 20, round(165 * n / 16)))
        if self.chart:
            with scene.screen_layer(2):
                self._room(ox, oy, sw, sh, panel_top)
            column_x, column_w = w * .62, w * .38 - 28
            with scene.screen_layer(4):
                scene.draw_rect(column_x, 108, column_w, panel_top - 124, (7, 18, 25, 232),
                                border_color=(167, 139, 81, 170), border_width=1, radius=3)
            with scene.screen_layer(7):
                scene.draw_text("FIELD CHART", column_x + 18, 122, font_size=10, font=fonts.SEMIBOLD,
                                color=BRASS, anchor_y="top")
            available = panel_top - 196
            map_h = min(available, (column_w - 36) * self.chart.size[1] / self.chart.size[0])
            map_w = map_h * self.chart.size[0] / self.chart.size[1]
            mx, my = column_x + (column_w - map_w) / 2, 176
            self.chart.draw(scene, index, self.age, self.clock, (mx, my, map_w, map_h), revealed=self.visited)
        # A few slow, deterministic motes; the simulation's random stream is never touched.
        with scene.screen_layer(8):
            for n in range(18):
                x = (n * 113.7 + math.sin(self.clock * .2 + n) * 17) % w
                y = 110 + (n * 53.3 - self.clock * (3 + n % 4)) % max(1, panel_top - 120)
                scene.draw_circle(x, y, 1 + (n % 2) * .5, (161, 197, 218, 35 + round(30 * math.sin(self.clock + n) ** 2)))

    def _room(self, ox: float, oy: float, sw: float, sh: float, panel_top: float) -> None:
        previous = next((speaker for speaker in reversed(self.joined.values()) if speaker is not self.speaker), None)
        for fraction, speaker, active in ((.268, self.speaker, True), (.50, previous, False)):
            cx, cy = ox + sw * fraction, oy + sh * .275
            rx, ry = sw * .069, sh * .188
            if speaker is None:
                continue
            opacity = min(1.0, self.transmission_age / .6) if active else .65
            key = _projection(self.scene.game, speaker)
            if key:
                self.scene.draw_image(key, cx - rx, cy - ry + math.sin(self.clock * 1.3) * 1.2,
                                      rx * 2, ry * 2, opacity=opacity)
            else:
                draw_production_icon(self.scene, speaker.subject, speaker.player, speaker.race,
                                     cx - rx, cy - rx, rx * 2, opacity=opacity)
            with self.scene.screen_layer(3):
                color = (255, 212, 122, 215) if active else (143, 224, 227, 100)
                # Both attendees use the same frame geometry and transmission, with state carried by light.
                for radius in (1.02, 1.08):
                    for n in range(64):
                        a = n * math.tau / 64
                        b = (n + 1) * math.tau / 64
                        self.scene.draw_line(cx + math.cos(a) * rx * radius, cy + math.sin(a) * ry * radius,
                                             cx + math.cos(b) * rx * radius, cy + math.sin(b) * ry * radius,
                                             color if radius == 1.02 else (143, 113, 63, 170), 2 if active else 1)
                for n in range(20):
                    a = n * math.tau / 64 + self.clock * .18
                    b = a + math.tau / 68
                    self.scene.draw_line(cx + math.cos(a) * rx * 1.12, cy + math.sin(a) * ry * 1.12,
                                         cx + math.cos(b) * rx * 1.12, cy + math.sin(b) * ry * 1.12, color, 1)
                sy = cy - ry + ((self.clock * .13) % 1) * ry * 2
                half = rx * math.sqrt(max(0, 1 - ((sy - cy) / ry) ** 2))
                self.scene.draw_line(cx - half, sy, cx + half, sy, (143, 224, 227, 35), 1)
                py = min(cy + ry + 4, panel_top - 54)
                self.scene.draw_rect(cx - 124, py, 248, 44, (7, 18, 25, 245), border_color=color, border_width=1, radius=3)
                self.scene.draw_text("SPEAKING" if active else "LISTENING", cx, py + 7, font_size=9,
                                     color=color, font=fonts.SEMIBOLD, anchor_x="center", anchor_y="top")
                self.scene.draw_text(speaker.name, cx, py + 23, font_size=11, color=(242, 232, 211, 255),
                                     font=fonts.SEMIBOLD, anchor_x="center", anchor_y="top")
