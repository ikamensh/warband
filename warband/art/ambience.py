"""Quiet life around visible buildings, driven entirely by simulation time: motes and glints
over a mine that still holds gold, smoke and a forge glow at a smith, a den breathing its own
tint with spores off its mouth and glints on its tips, at a site going up its
builder hammering at the front corner, dust rising from the work and a spark at every strike,
and aether streaming up out of a ley rift, or into the vault that draws it.  First built on the
unmerged ``warband`` branch; the geometry matches the buildings in :mod:`warband.art.textures`."""

from __future__ import annotations

import math

from saga2d import RenderLayer
from warband.sim.model import RIFT
from warband.sim.rules import BuildingType, MapTheme, UnitType
from warband.art import textures
from warband.art.textures import PROJECTION, TILE

STRIKE_EVERY = 0.7  # seconds from one hammer blow to the next at a site

#: The air a den breathes on each landscape: summer is its own tint, winter breathes cold white
#: and waste warm dust.  Mixed into the den's own halo tint so the kind still reads — a spider
#: nest breathes violet everywhere, frosted violet on snow and dusty violet on waste.
LANDSCAPE_AIR: dict[MapTheme, tuple[int, int, int] | None] = {
    MapTheme.SUMMER: None,
    MapTheme.WINTER: (232, 238, 246),
    MapTheme.WASTELAND: (214, 184, 136),
}


def landscape_halo(hue: tuple[int, int, int], theme: MapTheme | str) -> tuple[int, int, int]:
    """A den's halo tint on *theme*: its own hue on summer, breathed through the landscape's air
    elsewhere.  Unknown landscapes breathe summer air (monsters.coerce_theme)."""
    from warband.art.monsters import coerce_theme

    air = LANDSCAPE_AIR[coerce_theme(theme)]
    if air is None:
        return hue
    return tuple(round(h * 0.65 + a * 0.35) for h, a in zip(hue, air))  # type: ignore[return-value]


#: How high over its footprint's middle a vault's cube hangs (model units), where its glow and the motes it draws meet.
VAULT_CUBE = (0.0, 0.0, 1.01)


def draw(scene, world, player: int) -> None:
    time = world.time
    left, top, right, bottom = scene.camera.visible_world_rect()
    layer = {"space": "world", "layer": RenderLayer.EFFECTS}
    if world.rifts:
        _rifts(scene, world, player, (left, top, right, bottom), layer)
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
    halo = landscape_halo(anchors["halo"], world.theme)
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


def _rifts(scene, world, player: int, view: tuple[float, float, float, float], layer: dict) -> None:
    """Aether at the ley rifts in sight.  An open rift streams motes straight up out of its crack; a finished vault set
    square on one draws them in, its cube glowing and pulling at its chains, and a vault of the player's whose store
    is full draws nothing, so the motes stop and the cube goes dim.  Whether a rival's store is full is theirs to
    know: their vault is drawn drawing."""
    left, top, right, bottom = view
    full = world.players[player].aether >= world.aether_cap(player) if player < world.seats else False
    for rx, ry in world.rifts:
        cx, cy = rx + RIFT / 2, ry + RIFT / 2
        x, y = cx * TILE, cy * TILE
        if not (left - 80 < x < right + 80 and top - 120 < y < bottom + 80):
            continue
        if not any(world.is_visible(player, (rx + dx, ry + dy)) for dy in range(RIFT) for dx in range(RIFT)):
            continue
        phase = world.time + (rx * 7 + ry * 13) * .11
        vault = world.building_at((rx, ry))
        tapped = vault is not None and world.taps(vault) and vault.done and not vault.abandoned
        if not tapped:
            if vault is None or vault.type is BuildingType.VAULT:  # a site going up on it does not cap the light yet
                _streaming(scene, x, y, phase, layer)
            continue
        if vault.player == player and full:
            continue  # a full store: the vault draws nothing, and the motes stop
        _drawing(scene, x, y, phase, layer)


def _streaming(scene, x: float, y: float, phase: float, layer: dict) -> None:
    """Motes welling up out of an open rift's crack and rising a man's height and more, fading as they go."""
    scene.draw_circle(x, y, 22 + 3 * math.sin(phase * 1.3), (*textures.AETHER, 22), **layer)
    for i in range(10):
        lift = (phase * .32 + i / 10) % 1
        along = textures.RIFT_CRACK[1 + i % 5]
        mx = x + (along[0] - .5) * RIFT * TILE + math.sin(phase * 1.1 + i * 2.3) * 4 * lift
        my = y + (along[1] - .5) * RIFT * TILE - lift * 96
        alpha = round(230 * math.sin(lift * math.pi))
        size = 2.4 + 1.2 * math.sin(phase * 1.9 + i)
        tint = (194, 138, 255) if i % 3 else textures.AETHER_LIGHT
        scene.draw_polygon([(mx - size, my), (mx, my - size * 2.2), (mx + size, my), (mx, my + size * 1.4)], (*tint, alpha), **layer)


def _drawing(scene, x: float, y: float, phase: float, layer: dict) -> None:
    """A vault drawing: its cube glows in a slow pulse, and motes rise from the ground round it into the cube."""
    cube_x, cube_y = PROJECTION.project(VAULT_CUBE)
    pulse = .5 + .5 * math.sin(phase * 2.6)
    scene.draw_circle(x + cube_x, y + cube_y, 32 + 6 * pulse, (*textures.AETHER, round(40 + 40 * pulse)), **layer)
    scene.draw_circle(x + cube_x, y + cube_y, 14 + 4 * pulse, (*textures.AETHER_LIGHT, round(60 + 60 * pulse)), **layer)
    for i in range(8):
        t = (phase * .45 + i / 8) % 1
        angle = i * math.tau / 8 + phase * .2
        start_x, start_y = x + math.cos(angle) * 30, y + math.sin(angle) * 16 + 8
        mx = start_x + (x + cube_x - start_x) * t
        my = start_y + (y + cube_y - start_y) * t
        alpha = round(220 * math.sin(t * math.pi))
        size = 2.0 + .8 * math.sin(phase * 1.7 + i)
        scene.draw_polygon([(mx - size, my), (mx, my - size * 2.0), (mx + size, my), (mx, my + size * 1.4)], (194, 138, 255, alpha), **layer)
