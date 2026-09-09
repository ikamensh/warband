"""Quiet life around visible buildings, driven entirely by simulation time: motes and glints
over a mine that still holds gold, smoke and a forge glow at a smith.  First built on the
unmerged ``warband`` branch; the geometry matches the buildings in :mod:`warband.textures`."""

from __future__ import annotations

import math

from saga2d import RenderLayer
from warband.rules import BuildingType
from warband.textures import PROJECTION, TILE


def draw(scene, world, player: int) -> None:
    time = world.time
    left, top, right, bottom = scene.camera.visible_world_rect()
    layer = {"space": "world", "layer": RenderLayer.EFFECTS}
    for building in world.buildings.values():
        bx, by = building.center
        x, y = bx * TILE, by * TILE
        if not (left - 80 < x < right + 80 and top - 80 < y < bottom + 100):
            continue
        if not building.done or not world.is_visible(player, (int(bx), int(by))):
            continue
        phase = time + building.id * .37
        if building.type is BuildingType.GOLD_MINE and building.gold > 0:
            # A faint halo grounds the crystals; the glints stay small and bright.
            scene.draw_circle(x, y - 20, 34 + 2 * math.sin(phase), (255, 214, 110, 13), **layer)
            for i in range(7):
                angle = i * 2.4 + phase * .18
                lift = (phase * .22 + i / 7) % 1
                mx = x + math.cos(angle) * (20 + i * 2)
                my = y - lift * 78 + math.sin(angle) * 12
                alpha = round(175 * math.sin(lift * math.pi))
                size = 1.3 + .7 * math.sin(phase * 1.7 + i)
                scene.draw_polygon([(mx - size, my), (mx, my - size * 1.8), (mx + size, my), (mx, my + size * 1.8)], (255, 236, 170, alpha), **layer)
            for index, tip in enumerate(((-.38, -.42, 1.95), (.65, -.05, 1.48), (-.90, .14, 1.20))):
                dx, dy = PROJECTION.project(tip)
                strength = max(0.0, math.sin(phase * 1.6 + index * 1.8)) ** 8
                if strength > .05:
                    size, alpha = 4 * strength, round(220 * strength)
                    scene.draw_line(x + dx - size, y + dy, x + dx + size, y + dy, (255, 250, 230, alpha), 1, **layer)
                    scene.draw_line(x + dx, y + dy - size * 1.4, x + dx, y + dy + size * 1.4, (255, 250, 230, alpha), 1, **layer)
        elif building.type is BuildingType.BLACKSMITH:
            # Three drifting puffs from the chimney and a flicker at the furnace mouth.
            chimney_x, chimney_y = PROJECTION.project((-.72, -.51, 2.39))
            for i in range(3):
                age = (phase * .3 + i / 3) % 1
                scene.draw_circle(x + chimney_x + age * 10, y + chimney_y - age * 28, 3 + age * 7, (164, 159, 156, round(65 * (1 - age))), **layer)
            flicker = .5 + .5 * math.sin(phase * 9)
            forge_x, forge_y = PROJECTION.project((-.29, .564, .49))
            scene.draw_circle(x + forge_x, y + forge_y, 6 + flicker * 2, (255, 169, 78, round(13 + flicker * 9)), **layer)
