"""MapView — everything drawn in world space, kept in step with the model.

Layers: ground chunks on ``BACKGROUND``; selection rings and rally lines on
``OBJECTS``; trees, rocks, mines, buildings and units on ``UNITS``, y-sorted
by the point they stand on; arrows and particles on ``EFFECTS`` under the fog
sprite, which is one image with a pixel per tile stretched over the whole
map (bilinear filtering makes the soft edges for free) and is redrawn with
``update_image`` whenever the model recomputes vision; health bars and the
build ghost on ``UI_WORLD``.  The minimap is a second dynamic image the HUD
draws in screen space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from saga2d import Game, ParticleEmitter, RenderLayer, Scene, Sprite, SpriteAnchor
from warband import textures
from warband.model import Building, Entity, Pos, Unit, World
from warband.rules import BUILDINGS, VISION_EVERY, BuildingType, Terrain
from warband.textures import CHUNK, CHUNK_PX, DROP_TREE, DROP_UNIT, TILE

WATER_PERIOD = 0.45  # seconds between water phase changes
WATER_CYCLE = (0, 1, 2, 1)  # ping-pong through the phases so the ripples never jump

Color = tuple[int, int, int, int]
FOG_COLOR = (10, 12, 20)
FOG_EXPLORED = 150
MINIMAP_SCALE = 2


def rgba(color: tuple[int, int, int], alpha: int = 255) -> Color:
    return (color[0], color[1], color[2], alpha)


def to_world(point: tuple[float, float]) -> tuple[float, float]:
    """Model tiles → world pixels."""
    return (point[0] * TILE, point[1] * TILE)


def to_tiles(wx: float, wy: float) -> tuple[float, float]:
    return (wx / TILE, wy / TILE)


@dataclass
class Overlay:
    """What the scene wants drawn on the map this frame."""

    selected: list[int] = field(default_factory=list)
    hovered: int | None = None
    ghost: tuple[BuildingType, Pos, bool] | None = None  # building, top-left tile, placeable
    rally_for: list[int] = field(default_factory=list)


class MapView:
    def __init__(self, scene: Scene, world: World, player: int) -> None:
        self.scene = scene
        self.world = world
        self.player = player
        self.game: Game = scene.game
        self.time = 0.0
        textures.register_static(self.game)
        textures.register_theme(self.game, world.theme)
        self.scale = self.game.backend.scale_factor
        self._ground: list[Sprite] = []
        self._ground_keys: list[list[str]] = []  # per chunk: one image, or WATER_PHASES of them when it holds water
        self._water_pending: list[tuple[int, int]] = []  # (chunk, phase) images still to paint, one per frame
        self._water_time = 0.0
        self._water_step = 0
        self._trees: dict[Pos, Sprite] = {}
        self._rocks: dict[Pos, Sprite] = {}
        self._buildings: dict[int, Sprite] = {}
        self._building_keys: dict[int, str] = {}
        self._units: dict[int, Sprite] = {}
        self._unit_keys: dict[int, str] = {}
        self._smoke: dict[int, ParticleEmitter] = {}
        self._vision_tick = -1
        self._minimap_time = -1.0
        self.fog_key = f"fog.{world.width}x{world.height}"
        self.minimap_key = f"minimap.{world.width}x{world.height}"
        self._register(self.fog_key, self._fog_image())
        self._register(self.minimap_key, self._minimap_image())
        self._fog = scene.add_sprite(Sprite(self.fog_key, position=(0, 0), size=(world.width * TILE, world.height * TILE),
                                            anchor=SpriteAnchor.TOP_LEFT, layer=RenderLayer.EFFECTS, y_sort=True))
        self._build_ground()
        self._build_props()
        self.sync()

    # -- Setup ------------------------------------------------------------------------

    def _register(self, key: str, image: Image.Image) -> None:
        """Register an image, or redraw it in place if an earlier map left one of the same size."""
        if self.game.assets.has_image(key):
            self.game.assets.update_image(key, image)
        else:
            self.game.assets.image_from_pil(key, image)

    def _chunk_has_water(self, index: int) -> bool:
        world = self.world
        cols = math.ceil(world.width / CHUNK)
        cx, cy = index % cols, index // cols
        return any(world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.WATER
                   for y in range(cy * CHUNK - 1, (cy + 1) * CHUNK + 1) for x in range(cx * CHUNK - 1, (cx + 1) * CHUNK + 1))

    def _chunk_keys(self, index: int) -> list[str]:
        world = self.world
        phases = textures.WATER_PHASES if self._chunk_has_water(index) else 1
        return [f"ground.{index}.{world.width}x{world.height}.{phase}" for phase in range(phases)]

    def _paint_chunk(self, index: int, phase: int) -> None:
        world = self.world
        cols = math.ceil(world.width / CHUNK)
        self._register(self._ground_keys[index][phase], textures.ground_chunk(world.terrain_at, world.in_bounds, index % cols, index // cols, self.scale, world.theme, phase))

    def _build_ground(self) -> None:
        world = self.world
        cols, rows = math.ceil(world.width / CHUNK), math.ceil(world.height / CHUNK)
        for index in range(cols * rows):
            cx, cy = index % cols, index // cols
            self._ground_keys.append(self._chunk_keys(index))
            self._paint_chunk(index, 0)
            # The other phases are painted over the first frames rather than delaying the match.
            self._water_pending.extend((index, phase) for phase in range(1, len(self._ground_keys[index])))
            self._ground.append(self.scene.add_sprite(Sprite(
                self._ground_keys[index][0], position=((cx * CHUNK - 1) * TILE, (cy * CHUNK - 1) * TILE), size=(CHUNK_PX, CHUNK_PX),
                anchor=SpriteAnchor.TOP_LEFT, layer=RenderLayer.BACKGROUND,
            )))

    def _animate_water(self, dt: float) -> None:
        """Paint one pending phase image per frame; once all exist, cycle the water chunks through them."""
        if self._water_pending:
            self._paint_chunk(*self._water_pending.pop(0))
            return
        self._water_time += dt
        if self._water_time < WATER_PERIOD:
            return
        self._water_time = 0.0
        self._water_step += 1
        phase = WATER_CYCLE[self._water_step % len(WATER_CYCLE)]
        for sprite, keys in zip(self._ground, self._ground_keys):
            if len(keys) > 1:
                sprite.image = keys[phase]

    def _prop(self, key: str, point: tuple[float, float], **kwargs) -> Sprite:
        placement = textures.placements[key]
        wx, wy = to_world(point)
        return self.scene.add_sprite(Sprite(key, position=(wx, wy + placement.drop), size=placement.size, anchor=SpriteAnchor.BOTTOM_CENTER,
                                            layer=RenderLayer.UNITS, y_sort=True, **kwargs))

    def _build_props(self) -> None:
        world = self.world
        for y in range(world.height):
            for x in range(world.width):
                terrain = world.terrain[y][x]
                if terrain is Terrain.TREES:
                    self._trees[(x, y)] = self._prop(f"tree.{world.theme.value}.{textures.scatter(x, y, 3) % textures.TREE_VARIANTS}", (x + 0.5, y + 0.5))
                elif terrain is Terrain.ROCK:
                    self._rocks[(x, y)] = self._prop(f"rock.{world.theme.value}.{textures.scatter(x, y, 4) % textures.ROCK_VARIANTS}", (x + 0.5, y + 0.5))

    def reset(self, world: World) -> None:
        """Point the view at another world of the same size (after loading a save)."""
        if (world.width, world.height) != (self.world.width, self.world.height):
            raise ValueError("a loaded map must have the size of the current one")
        for group in (self._trees, self._rocks, self._buildings, self._units):
            for sprite in group.values():
                sprite.remove()
            group.clear()
        for emitter in self._smoke.values():
            emitter.remove()
        self._smoke.clear()
        self._building_keys.clear()
        self._unit_keys.clear()
        self.world = world
        textures.register_theme(self.game, world.theme)
        self._vision_tick = -1
        self._minimap_time = -1.0
        self._water_pending.clear()
        self._water_step = 0
        for index, sprite in enumerate(self._ground):
            keys = self._ground_keys[index] = self._chunk_keys(index)  # the water may lie elsewhere on this map
            self._paint_chunk(index, 0)
            sprite.image = keys[0]
            self._water_pending.extend((index, phase) for phase in range(1, len(keys)))
        self._build_props()
        self.sync()

    # -- Sync ----------------------------------------------------------------------------

    def sync(self, dt: float = 0.0) -> None:
        self.time += dt
        world = self.world
        self._animate_water(dt)
        for pos in list(self._trees):
            if world.terrain_at(pos) is not Terrain.TREES:
                self._trees.pop(pos).remove()
        self._sync_buildings()
        self._sync_units()
        if world.tick // VISION_EVERY != self._vision_tick:
            self._vision_tick = world.tick // VISION_EVERY
            self.game.assets.update_image(self.fog_key, self._fog_image())
        if self.time - self._minimap_time >= 0.25:
            self._minimap_time = self.time
            self.game.assets.update_image(self.minimap_key, self._minimap_image())

    def _known(self, building: Building) -> bool:
        return building.player == self.player or any(self.world.is_explored(self.player, t) for t in building.tiles())

    def _sync_buildings(self) -> None:
        world = self.world
        for bid, sprite in list(self._buildings.items()):
            if bid not in world.buildings:
                sprite.remove()
                del self._buildings[bid]
                del self._building_keys[bid]
                smoke = self._smoke.pop(bid, None)
                if smoke is not None:
                    smoke.remove()
        for b in world.buildings.values():
            if not self._known(b):
                continue
            rising = not b.done and b.progress >= b.info.build_time / 2  # the second half of construction shows the building going up
            if b.type is BuildingType.GOLD_MINE:
                key = "mine"
            elif b.done or rising:
                key = textures.building_image(self.game, b.type, b.player)  # type: ignore[arg-type]
            else:
                key = f"site.{b.size}"
            sprite = self._buildings.get(b.id)
            if sprite is None:
                sprite = self._buildings[b.id] = self._prop(key, b.center)
                self._building_keys[b.id] = key
            elif self._building_keys[b.id] != key:
                sprite.image = key
                sprite.size = textures.placements[key].size
                self._building_keys[b.id] = key
            sprite.opacity = 150 if rising else 255
            self._sync_smoke(b, sprite)

    def _sync_smoke(self, b: Building, sprite: Sprite) -> None:
        """A damaged building smoulders: smoke rises from its roof while it is under half health."""
        burning = b.done and b.type is not BuildingType.GOLD_MINE and b.hp < b.max_hp / 2 and self.world.is_visible(self.player, (int(b.center[0]), int(b.center[1])))
        emitter = self._smoke.get(b.id)
        if burning and emitter is None:
            wx, wy = to_world(b.center)
            emitter = ParticleEmitter("smoke", position=(wx, wy - b.size * TILE * 0.5), speed=(8, 26), direction=(250, 290), lifetime=(1.2, 2.2),
                                      size=(18, 18), fade_out=True, layer=RenderLayer.EFFECTS)
            emitter.continuous(rate=3 + 3 * (1 - b.hp / max(1, b.max_hp)))
            self._smoke[b.id] = self.scene.add_emitter(emitter)
        elif not burning and emitter is not None:
            emitter.remove()
            del self._smoke[b.id]

    def _frame(self, u: Unit) -> str:
        if u.state == "move":
            return "walk1" if int(self.time * 5 + u.id) % 2 == 0 else "walk2"
        if u.state == "attack":
            return "attack" if u.cooldown > u.info.cooldown - 0.3 else "stand"
        if u.state == "chop":
            return "attack" if (self.time * 2 + u.id * 0.37) % 1.0 < 0.35 else "stand"
        return "stand"

    def _sync_units(self) -> None:
        world = self.world
        for uid, sprite in list(self._units.items()):
            if uid not in world.units:
                sprite.remove()
                del self._units[uid]
                del self._unit_keys[uid]
        for u in world.units.values():
            sprite = self._units.get(u.id)
            shown = not u.hidden and (u.player == self.player or world.is_visible(self.player, u.tile))
            if not shown:
                if sprite is not None:
                    sprite.visible = False
                continue
            key = textures.unit_image(self.game, u.type, u.player, textures.facing_index(u.facing), self._frame(u), u.carrying)
            if sprite is None:
                sprite = self._units[u.id] = self._prop(key, u.pos)
                self._unit_keys[u.id] = key
            else:
                if self._unit_keys[u.id] != key:
                    sprite.image = key
                    sprite.size = textures.placements[key].size
                    self._unit_keys[u.id] = key
                wx, wy = to_world(u.pos)
                sprite.position = (wx, wy + DROP_UNIT)
                sprite.visible = True

    def unit_sprite(self, unit_id: int) -> Sprite | None:
        return self._units.get(unit_id)

    def release_unit_sprite(self, unit_id: int) -> Sprite | None:
        """Hand a unit's sprite to the caller (for a death animation) instead of removing it on the next sync."""
        sprite = self._units.pop(unit_id, None)
        self._unit_keys.pop(unit_id, None)
        return sprite if sprite is not None and sprite.visible else None

    def building_sprite(self, building_id: int) -> Sprite | None:
        return self._buildings.get(building_id)

    # -- Fog and minimap --------------------------------------------------------------------

    def _fog_image(self) -> Image.Image:
        world = self.world
        shape = (world.height, world.width)
        visible = np.frombuffer(bytes(world.visible[self.player]), dtype=np.uint8).reshape(shape)
        explored = np.frombuffer(bytes(world.explored[self.player]), dtype=np.uint8).reshape(shape)
        alpha = np.where(visible > 0, 0, np.where(explored > 0, FOG_EXPLORED, 255)).astype(np.uint8)
        rgba = np.empty((*shape, 4), dtype=np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = FOG_COLOR
        rgba[..., 3] = alpha
        return Image.fromarray(rgba, "RGBA")

    def _minimap_terrain(self) -> np.ndarray:
        world = self.world
        colours = textures.PALETTES[world.theme].minimap
        base = np.zeros((world.height, world.width, 3), dtype=np.float32)
        for y in range(world.height):
            for x in range(world.width):
                base[y, x] = colours[world.terrain[y][x]]
        return base

    def _minimap_image(self) -> Image.Image:
        world = self.world
        shape = (world.height, world.width)
        visible = np.frombuffer(bytes(world.visible[self.player]), dtype=np.uint8).reshape(shape) > 0
        explored = np.frombuffer(bytes(world.explored[self.player]), dtype=np.uint8).reshape(shape) > 0
        img = self._minimap_terrain() * np.where(visible, 1.0, np.where(explored, 0.6, 0.18))[..., None]
        for b in world.buildings.values():
            if not self._known(b):
                continue
            color = (232, 196, 70) if b.player is None else world.players[b.player].color
            img[b.y:b.y + b.size, b.x:b.x + b.size] = color
        for u in world.units.values():
            if u.hidden or not (u.player == self.player or visible[u.tile[1], u.tile[0]]):
                continue
            x, y = u.tile
            img[y, x] = world.players[u.player].color
        pixels = np.repeat(np.repeat(img.clip(0, 255).astype(np.uint8), MINIMAP_SCALE, 0), MINIMAP_SCALE, 1)
        rgba = np.concatenate([pixels, np.full((*pixels.shape[:2], 1), 255, dtype=np.uint8)], axis=-1)
        return Image.fromarray(rgba, "RGBA")

    # -- Overlays --------------------------------------------------------------------------

    def _ring(self, cx: float, cy: float, rx: float, ry: float, color: Color, width: float = 2.0, layer: RenderLayer = RenderLayer.OBJECTS) -> None:
        points = [(cx + rx * math.cos(2 * math.pi * i / 14), cy + ry * math.sin(2 * math.pi * i / 14)) for i in range(14)]
        for i in range(14):
            (x1, y1), (x2, y2) = points[i], points[(i + 1) % 14]
            self.scene.draw_line(x1, y1, x2, y2, color, width, space="world", layer=layer)

    def _entity_color(self, entity: Entity) -> Color:
        from warband.style import ENEMY, GOLD, SELECT

        if entity.player is None:
            return GOLD
        return SELECT if entity.player == self.player else ENEMY

    def _health_bar(self, entity: Entity, x: float, y: float, width: float) -> None:
        if isinstance(entity, Building) and entity.type is BuildingType.GOLD_MINE:
            return
        frac = max(0.0, min(1.0, entity.hp / max(1, entity.max_hp)))
        color = (110, 230, 110, 255) if frac > 0.5 else (240, 200, 80, 255) if frac > 0.25 else (240, 90, 70, 255)
        self.scene.draw_rect(x - width / 2, y, width, 4, (0, 0, 0, 170), space="world", layer=RenderLayer.UI_WORLD)
        self.scene.draw_rect(x - width / 2, y, width * frac, 4, color, space="world", layer=RenderLayer.UI_WORLD)

    def draw(self, overlay: Overlay) -> None:
        world, scene = self.world, self.scene
        for eid in overlay.selected + ([overlay.hovered] if overlay.hovered is not None and overlay.hovered not in overlay.selected else []):
            entity = world.entity(eid)
            if entity is None:
                continue
            color = self._entity_color(entity)
            if isinstance(entity, Unit):
                if entity.hidden:
                    continue
                wx, wy = to_world(entity.pos)
                self._ring(wx, wy + 2, TILE * 0.42, TILE * 0.26, color if eid in overlay.selected else rgba(color[:3], 120))
                self._health_bar(entity, wx, wy - TILE * 0.95, TILE * 0.8)
            else:
                x, y, w, h = entity.rect
                left, top = x * TILE, y * TILE
                scene.draw_rect(left, top, w * TILE, h * TILE, (0, 0, 0, 0), border_color=color if eid in overlay.selected else rgba(color[:3], 120),
                                border_width=2, space="world", layer=RenderLayer.OBJECTS)
                self._health_bar(entity, left + w * TILE / 2, top - 8, w * TILE * 0.8)
                if not entity.done:
                    frac = entity.progress / entity.info.build_time
                    scene.draw_rect(left + 4, top + h * TILE - 8, w * TILE - 8, 4, (0, 0, 0, 170), space="world", layer=RenderLayer.UI_WORLD)
                    scene.draw_rect(left + 4, top + h * TILE - 8, (w * TILE - 8) * frac, 4, (255, 214, 110, 255), space="world", layer=RenderLayer.UI_WORLD)
        for bid in overlay.rally_for:
            b = world.buildings.get(bid)
            if b is None or b.rally is None:
                continue
            bx, by = to_world(b.center)
            rx, ry = to_world(b.rally)
            scene.draw_line(bx, by, rx, ry, (255, 214, 110, 150), 1.5, space="world", layer=RenderLayer.OBJECTS)
            self._ring(rx, ry, 8, 5, (255, 214, 110, 220))
            scene.draw_line(rx, ry, rx, ry - 14, (255, 214, 110, 220), 2, space="world", layer=RenderLayer.OBJECTS)
            scene.draw_polygon([(rx, ry - 14), (rx + 9, ry - 11), (rx, ry - 8)], (255, 214, 110, 220), space="world", layer=RenderLayer.OBJECTS)
        if overlay.ghost is not None:
            building_type, (gx, gy), ok = overlay.ghost
            size = BUILDINGS[building_type].size
            tint = (120, 255, 140, 70) if ok else (255, 80, 70, 90)
            for ty in range(size):
                for tx in range(size):
                    scene.draw_rect((gx + tx) * TILE + 1, (gy + ty) * TILE + 1, TILE - 2, TILE - 2, tint, space="world", layer=RenderLayer.UI_WORLD)
            key = textures.building_image(self.game, building_type, self.player)
            placement = textures.placements[key]
            cx, cy = (gx + size / 2) * TILE, (gy + size / 2) * TILE
            w, h = placement.size
            scene.draw_image(key, cx - w / 2, cy + placement.drop - h, w, h, opacity=0.55 if ok else 0.3, space="world", layer=RenderLayer.UI_WORLD)
