"""Saveable campaign landmarks, their occupation rule, and their view.

A landmark is a story object rather than a simulation building: it neither blocks movement nor
leaks an enemy's state. Mission scripts add and change JSON records in ``Run.vars``; the scene
creates :class:`LandmarkView` after its ordinary map view, calls ``update()`` after the script,
and ``draw()`` with its map overlays. Ground props sit below the fog. Names appear only on
explored ground, inside the camera's clear area, and away from UI panels.
"""

from __future__ import annotations

import math
from typing import Any

from saga2d import Component, RenderLayer, Sprite, SpriteAnchor
from warband.art import campaign_landmarks as art
from warband.art.textures import TILE
from warband.audio import campaign as audio, sound

from warband.sim.model import Point, dist
from warband.story.campaign import Run

KINDS = frozenset(("bell", "anchor", "gate", "refuge", "memorial"))
STATES = frozenset(("dormant", "active", "ruined", "open"))


def add_landmark(run: Run, id: str, name: str, point: Point, *, kind: str = "bell", radius: float = 3.0,
                 state: str = "dormant", revealed: bool = True) -> dict[str, Any]:
    """Place a named story object; ``revealed`` charts its location without revealing ground or enemies."""
    if kind not in KINDS or state not in STATES:
        raise ValueError(f"unknown landmark kind/state: {kind!r}/{state!r}")
    if not id or not name or "\n" in name or "\r" in name:
        raise ValueError("a landmark needs an id and a single-line name")
    x, y = float(point[0]), float(point[1])
    if not math.isfinite(x) or not math.isfinite(y) or not run.world.in_bounds((int(x), int(y))) or x < 0 or y < 0:
        raise ValueError(f"landmark {id!r} lies outside the map")
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("a landmark radius must be positive and finite")
    records = run.vars.setdefault("landmarks", {})
    if id in records:
        raise ValueError(f"landmark {id!r} already exists")
    record = {"id": id, "name": name, "point": [x, y], "kind": kind, "radius": float(radius), "state": state, "revealed": revealed}
    records[id] = record
    return record


def landmark(run: Run, id: str) -> dict[str, Any]:
    """The saved record for *id*. An unknown id is a mission error and raises ``KeyError``."""
    return run.vars["landmarks"][id]


def set_landmark_state(run: Run, id: str, state: str) -> None:
    """Change a story object; the view hears each new state once, never on initial load."""
    if state not in STATES:
        raise ValueError(f"unknown landmark state {state!r}")
    landmark(run, id)["state"] = state


def occupied(run: Run, id: str, *, side: int = 0, contested: bool = True, soldiers_only: bool = True) -> bool:
    """Living ground soldiers hold the radius, provided no living enemy on the ground contests it.

    Workers may hold it only with ``soldiers_only=False``. Enemy workers still contest a hold;
    airborne units and units inside buildings have no feet on this ground. Neutral guards contest too.
    """
    record = landmark(run, id)
    point = (float(record["point"][0]), float(record["point"][1]))
    radius = record["radius"]
    present = [unit for unit in run.world.units.values()
               if unit.hp > 0 and not unit.hidden and not unit.flying and dist(unit.pos, point) <= radius]
    return (any(unit.player == side and (not soldiers_only or not unit.is_worker) for unit in present)
            and (not contested or not any(unit.player != side for unit in present)))


class _LandmarkMarkers(Component):
    """A minimap child: its diamonds draw above the map image and share its public coordinate conversion."""

    def __init__(self, view: LandmarkView) -> None:
        super().__init__()
        self.view = view

    def on_draw(self) -> None:
        if self._game is None:
            return
        scene = self.view.scene
        for id, record in scene.run.vars.get("landmarks", {}).items():
            if not self.view.known(id):
                continue
            x, y = scene.minimap.to_screen(*(value*TILE for value in record["point"]))
            color = art.hue(record["kind"], record["state"])
            for radius, tint in ((4.5, (13, 22, 29, 255)), (3, (*color, 255))):
                self._game.backend.draw_polygon([(x, y-radius), (x+radius, y), (x, y+radius), (x-radius, y)],
                                                tint, order=self._order)


class LandmarkView:
    """The scene's landmark props and cues, restored quietly from the mission's saved variables."""

    def __init__(self, scene) -> None:
        self.scene = scene
        self._sprites: dict[str, Sprite] = {}
        self._states: dict[str, str] = {}
        scene.minimap.add(_LandmarkMarkers(self))
        self.update()

    def known(self, id: str) -> bool:
        """Whether the player has a charted position or has discovered this landmark's ground."""
        record = landmark(self.scene.run, id)
        x, y = record["point"]
        return record["revealed"] or self.scene.world.is_explored(self.scene.human, (int(x), int(y)))

    def update(self) -> None:
        """Refresh changed art and hear state transitions once. Initial and newly discovered states are silent."""
        scene = self.scene
        records = scene.run.vars.get("landmarks", {})
        for id in self._sprites.keys() - records.keys():
            self._sprites.pop(id).remove()
            del self._states[id]
        for id, record in records.items():
            state, kind = record["state"], record["kind"]
            key = f"landmark.{kind}.{state}"
            if not scene.game.assets.has_image(key):
                scene.game.assets.image_from_pil(key, art.image(kind, state))
            if id not in self._sprites:
                self._sprites[id] = scene.add_sprite(Sprite(key, size=art.SIZE, anchor=SpriteAnchor.BOTTOM_CENTER,
                                                           layer=RenderLayer.UNITS, y_sort=True, ground=art.DROP))
            sprite = self._sprites[id]
            if sprite.image != key:
                sprite.image = key
            x, y = record["point"]
            sprite.position = (x*TILE, y*TILE + art.DROP)
            sprite.visible = self.known(id)
            previous = self._states.get(id)
            if previous is not None and previous != state and self.known(id):
                cue = audio.cue(kind, state)
                if cue is not None:
                    sound.play_sound(cue)
            self._states[id] = state

    def draw(self) -> None:
        """Occupation rings lie under units and fog; clear, explored map ground gets a compact nameplate."""
        scene, world = self.scene, self.scene.world
        records = scene.run.vars.get("landmarks", {})
        if not records:
            return
        # World overlays draw before the UI tree; refresh its public layout so newly opened
        # panels protect their space on this first frame as well as later ones.
        scene.ui.compute_layout(0, 0, *scene.game.resolution)
        left, top, right, bottom = scene.camera.visible_world_rect()
        for id, record in records.items():
            if not self.known(id):
                continue
            x, y = record["point"]
            wx, wy = x*TILE, y*TILE
            radius = record["radius"]*TILE
            color = art.hue(record["kind"], record["state"])
            if wx+radius < left or wx-radius > right or wy+radius < top or wy-radius > bottom:
                continue
            if record["state"] != "ruined":
                scene.draw_circle(wx, wy, radius, (*color, 7), space="world", layer=RenderLayer.OBJECTS)
                for i in range(48):
                    a, b = i*math.tau/48, (i+.72)*math.tau/48
                    scene.draw_line(wx+math.cos(a)*radius, wy+math.sin(a)*radius,
                                    wx+math.cos(b)*radius, wy+math.sin(b)*radius,
                                    (*color, 115), 1.4, space="world", layer=RenderLayer.OBJECTS)
            if not world.is_explored(scene.human, (int(x), int(y))):
                continue
            sx, sy = scene.camera.world_to_screen(wx, wy+art.DROP+5)
            name = scene.fit_text(record["name"], 190, font_size=11)
            width, height = scene.game.backend.measure_text(name, 11, scene.game.theme.font)
            box = (sx-width/2-7, sy, width+14, height+8)
            if not self._clear_label(box):
                continue
            scene.draw_rect(*box, (18, 29, 34, 208), border_color=(*color, 128), border_width=1, radius=3)
            scene.draw_text(name, sx, sy+4, font_size=11, color=(238, 234, 214, 255), anchor_x="center", anchor_y="top")

    def _clear_label(self, box: tuple[float, float, float, float]) -> bool:
        """Clip in screen space before Saga2D's strict text-fit check, including the objective and selection panels."""
        scene = self.scene
        x, y, w, h = box
        left, top, right, bottom = scene.camera.insets
        width, height = scene.game.resolution
        if x < left+4 or y < top+4 or x+w > width-right-4 or y+h > height-bottom-4:
            return False
        for component in scene.ui.walk():
            if not component.blocks_pointer and not component.focusable:
                continue
            ancestor = component
            while ancestor is not None and ancestor.visible:
                ancestor = ancestor.parent
            if ancestor is not None:
                continue
            cx, cy, cw, ch = component.bounds
            if x < cx+cw and x+w > cx and y < cy+ch and y+h > cy:
                return False
        return True
