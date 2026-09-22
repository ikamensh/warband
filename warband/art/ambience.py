"""Quiet life around visible buildings, driven entirely by simulation time: motes and glints
over a mine that still holds gold, smoke and a forge glow at a smith, a den breathing its own
tint with spores off its mouth and glints on its tips, and at a site going up its
builder hammering at the front corner, dust rising from the work and a spark at every strike.  First built on the
unmerged ``warband`` branch; the geometry matches the buildings in :mod:`warband.art.textures`."""

from __future__ import annotations

import math

from saga2d import RenderLayer
from warband.sim.rules import BuildingType, UnitType
from warband.art import textures
from warband.art.textures import PROJECTION, TILE

STRIKE_EVERY = 0.7  # seconds from one hammer blow to the next at a site


def draw(scene, world, player: int) -> None:
    time = world.time
    left, top, right, bottom = scene.camera.visible_world_rect()
    layer = {"space": "world", "layer": RenderLayer.EFFECTS}
    for building in world.buildings.values():
        bx, by = building.center
        x, y = bx * TILE, by * TILE
        if not (left - 80 < x < right + 80 and top - 80 < y < bottom + 100):
            continue
        if not world.is_visible(player, (int(bx), int(by))):
            continue
        phase = time + building.id * .37
        if not building.done:
            builder = world.units.get(building.builder) if building.builder is not None else None
            if builder is not None and builder.constructing == building.id:
                _site_at_work(scene, building, builder, x, y, phase, layer)
            continue
        if building.has_gold:
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
        elif building.type is BuildingType.LAIR:
            # A den breathes: a slow halo pulse in its own tint, spores or dust rising from its mouth,
            # and glints on its tips.  The anchors live with the meshes that placed them
            # (:data:`warband.art.monsters.LAIR_ANCHORS`), so the life and the den agree.
            _lair_alive(scene, world, building, x, y, phase, layer)
        elif building.type is BuildingType.BLACKSMITH:
            # Three drifting puffs from the chimney and a flicker at the furnace mouth.
            chimney_x, chimney_y = PROJECTION.project((-.72, -.51, 2.39))
            for i in range(3):
                age = (phase * .3 + i / 3) % 1
                scene.draw_circle(x + chimney_x + age * 10, y + chimney_y - age * 28, 3 + age * 7, (164, 159, 156, round(65 * (1 - age))), **layer)
            flicker = .5 + .5 * math.sin(phase * 9)
            forge_x, forge_y = PROJECTION.project((-.29, .564, .49))
            scene.draw_circle(x + forge_x, y + forge_y, 6 + flicker * 2, (255, 169, 78, round(13 + flicker * 9)), **layer)


def _lair_alive(scene, world, building, x: float, y: float, phase: float, layer: dict) -> None:
    """One den breathing: a slow halo pulse in its own tint, motes rising from its mouth, glints on
    its tips, and the wolf den's breath puffing at its mouth on a slower clock."""
    from warband.art.monsters import LAIR_ANCHORS, LairKind, lair_kind_for_camp

    camp = next((c for c in world.camps if c.lair == building.id), None)
    kind = lair_kind_for_camp(camp) if camp is not None else LairKind.WOLF
    anchors = LAIR_ANCHORS[kind]
    halo = anchors["halo"]
    breath = 0.5 + 0.5 * math.sin(phase * 2.1)  # about three seconds a breath
    scene.draw_circle(x, y - 24, 30 + 3 * math.sin(phase * 2.1), (*halo, round(11 + breath * 7)), **layer)
    mx, my = PROJECTION.project(anchors["mouth"])
    for i in range(5):  # spores or dust off the mouth, each on its own clock
        lift = (phase * .18 + i / 5) % 1
        px = x + mx + math.cos(phase * .9 + i * 2.4) * 8
        py = y + my - lift * 44
        alpha = round(150 * math.sin(lift * math.pi))
        size = 1.2 + .6 * math.sin(phase * 1.7 + i)
        scene.draw_circle(px, py, size, (*halo, alpha), **layer)
    for index, tip in enumerate(anchors["glints"]):
        dx, dy = PROJECTION.project(tip)
        strength = max(0.0, math.sin(phase * 1.6 + index * 1.8)) ** 8
        if strength > .05:
            size, alpha = 4 * strength, round(220 * strength)
            scene.draw_line(x + dx - size, y + dy, x + dx + size, y + dy, (255, 250, 230, alpha), 1, **layer)
            scene.draw_line(x + dx, y + dy - size * 1.4, x + dx, y + dy + size * 1.4, (255, 250, 230, alpha), 1, **layer)
    if kind is LairKind.WOLF:  # breath puffing at the mouth, slower than the spore drift
        for i in range(2):
            age = (phase * .25 + i / 2) % 1
            scene.draw_circle(x + mx + age * 6, y + my - age * 16, 2 + age * 5, (200, 195, 185, round(60 * (1 - age))),
                              **layer)


def _site_at_work(scene, building, builder, x: float, y: float, phase: float, layer: dict) -> None:
    """The builder, hidden inside its site by the rules, hammers at the site's front left corner (the peasant's own blow
    frames, facing in), with dust rising from the work around the foot of the site and a spark at every strike."""
    half = building.size * TILE / 2
    beat = (phase % STRIKE_EVERY) / STRIKE_EVERY
    frame = "wind" if beat < .45 else "strike" if beat < .6 else "follow" if beat < .75 else "recover"
    fx, fy = x - half - 4, y + half * .55  # stands just off the front left corner, facing the work to its upper right
    key = textures.unit_image(scene.game, UnitType.PEASANT, builder.player, textures.facing_index(-math.pi / 4), frame, race=builder.race)
    placement = textures.placements[key]
    w, h = placement.size
    scene.draw_image(key, fx - w / 2, fy + placement.drop - h, w, h, space="world", layer=RenderLayer.EFFECTS)
    if .45 <= beat < .6:  # the blow lands
        sx, sy = fx + 13, fy - 12
        for i in range(4):
            angle = -math.pi / 2 + (i - 1.5) * .6
            scene.draw_line(sx, sy, sx + math.cos(angle) * 7, sy + math.sin(angle) * 7, (255, 236, 170, 220), 1, **layer)
    for i in range(5):  # dust drifting up from the work, each puff on its own clock
        age = (phase * .45 + i / 5) % 1
        px = x + (i / 4 - .5) * half * 1.5 + math.sin(phase * .7 + i) * 4
        py = y + half * .7 - age * 34
        scene.draw_circle(px, py, 5 + age * 11, (190, 164, 120, round(120 * (1 - age))), **layer)
