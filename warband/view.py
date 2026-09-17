"""MapView — everything drawn in world space, kept in step with the model.

Layers: ground chunks on ``BACKGROUND``; selection rings and rally lines on
``OBJECTS``; trees, rocks, mines, buildings and units on ``UNITS``, y-sorted
by the line they stand on (a unit's feet, a building's front edge: the
placement's *ground* tells the sprite how far its padded canvas continues
below that line); shots in flight, their trails and particles on ``EFFECTS`` under the fog
sprite, which is one image with a pixel per tile stretched over the whole
map (bilinear filtering makes the soft edges for free) and is redrawn with
``update_image`` whenever the model recomputes vision; health bars and the
build ghost on ``UI_WORLD``.  The minimap is a second dynamic image the HUD
draws in screen space.
"""

from __future__ import annotations

import math
from typing import Callable
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from saga2d import Game, ParticleEmitter, RenderLayer, Scene, Sprite, SpriteAnchor
from warband import textures
from warband.model import Building, Entity, Pos, Projectile, Unit, World, dist
from warband.rules import BUILDINGS, SIM_DT, VISION_EVERY, BuildingType, Terrain, UnitType
from warband.textures import CHUNK, CHUNK_PX, TILE

WATER_PERIOD = 0.45  # seconds between water phase changes
WATER_CYCLE = (0, 1, 2, 1)  # ping-pong through the phases so the ripples never jump
CHOP_PERIOD = 0.8

Color = tuple[int, int, int, int]
FOG_COLOR = (10, 12, 20)
FOG_EXPLORED = 150
FOG_MARGIN = 4  # Hide prop overhang beyond the board; the stone rim sits above it.
MINIMAP_SCALE = 2


def rgba(color: tuple[int, int, int], alpha: int = 255) -> Color:
    return (color[0], color[1], color[2], alpha)


def building_look(b: Building) -> str:
    """Which painted look a building wears: damaged under half its hit points, active while it
    trains or researches, intact otherwise (and while it is still going up)."""
    if not b.done:
        return "intact"
    if b.hp < b.max_hp / 2:
        return "damaged"
    if b.queue or b.research is not None:
        return "active"
    return "intact"


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


def minimap_terrain(world: World) -> np.ndarray:
    """Terrain colours for *world* from ``textures.PALETTES[theme].minimap``.

    A ``(height, width, 3)`` float array shared by the HUD minimap and the
    new-game preview, so both pictures agree on what grass, water, trees
    and rock look like.
    """
    colours = textures.PALETTES[world.theme].minimap
    base = np.zeros((world.height, world.width, 3), dtype=np.float32)
    for y in range(world.height):
        for x in range(world.width):
            base[y, x] = colours[world.terrain[y][x]]
    return base


STRIDE = 0.22  # tiles travelled per walk frame: feet stay planted instead of sliding, and faster units step faster
STRIKE, FOLLOW, RECOVER = 0.1, 0.16, 0.16  # seconds after the blow: driven forward, swept across, settling to guard
TRAIL = {"arrow": 0.12, "stone": 0.45}  # seconds of flight a shot leaves hanging in the air behind it
TRAIL_COLOR = {"arrow": (250, 246, 226), "stone": (228, 216, 194)}


def unit_frame(u: Unit, travel: float, time: float) -> str:
    """Which of the unit's frames shows now.  Walking is driven by distance travelled, a blow by the
    model's own clocks: the wind-up while the model has the weapon drawn back, then the strike,
    follow-through and recovery trailing the blow it just landed, read off the cooldown."""
    if u.state == "move":
        return textures.WALK_FRAMES[int(travel / STRIDE) % len(textures.WALK_FRAMES)]
    if u.state == "attack":
        if u.windup > 0.0:
            return "wind"
        if u.cooldown > 0.0:
            since = u.info.cooldown - u.cooldown
            if since < STRIKE:
                return "strike"
            if since < STRIKE + FOLLOW:
                return "follow"
            if since < STRIKE + FOLLOW + RECOVER:
                return "recover"
        return "stand"
    if u.state == "chop":
        if u.carrying is not None:
            return "stand"
        phase = (u.timer / CHOP_PERIOD) % 1.0
        return textures.CHOP_FRAMES[0 if phase < 0.25 else 1 if phase < 0.45 else 2 if phase < 0.7 else 3]
    if u.state == "repair":
        return "strike" if (time * 2 + u.id * 0.37) % 1.0 < 0.35 else "stand"
    return "stand"


def _melee_lunge(u: Unit, fraction: float) -> float:
    """Melee bodies load slowly, drive quickly, then settle to their ground point.

    These are pixels of presentation, never additional reach or model movement.
    The existing wind-up/cooldown clocks keep the weight shift tied to the blow.
    """
    if u.type not in (UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT) or u.state != "attack":
        return 0.0
    load, drive = (4.0, 6.0) if u.type is UnitType.KNIGHT else (3.0, 5.0)
    if u.windup > 0.0:
        remaining = max(0.0, u.windup - fraction * SIM_DT)
        if remaining > 0.09:
            return -load * (u.info.windup - remaining) / (u.info.windup - 0.09)
        progress = 1 - remaining / 0.09
        return -load + (load + drive) * progress * progress * (3 - 2 * progress)
    if u.cooldown > 0.0:
        age = u.info.cooldown - u.cooldown + fraction * SIM_DT
        if 0 <= age < STRIKE + FOLLOW + RECOVER:
            return drive * (1 - age / (STRIKE + FOLLOW + RECOVER)) ** 2
    return 0.0


def projectile_point(p: Projectile, world: World, now: float) -> tuple[float, float, float]:
    """Where a shot is at simulation time *now*: its ground position in tiles and its height above the
    ground, in tiles.  An arrow flies at its mark's current position on a flat arc; a stone lobs high to
    the ground it was fired at."""
    t = max(0.0, min(1.0, (now - p.launched) / p.flight))
    end = p.aim
    if p.target is not None:
        target = world.entity(p.target)
        if target is not None:
            end = target.pos if isinstance(target, Unit) else target.center
    x = p.start[0] + (end[0] - p.start[0]) * t
    y = p.start[1] + (end[1] - p.start[1]) * t
    span = dist(p.start, end)
    lift = 1.7 if p.source_type == BuildingType.TOWER.value else 0.55  # loosed from the battlements, or from the shoulder
    if p.kind == "stone":
        height = 0.55 + 4 * (0.5 + 0.14 * span) * t * (1 - t)
    else:
        height = lift + (0.45 - lift) * t + 0.35 * math.sin(math.pi * t) * min(1.0, span / 4)
    return x, y, height


@dataclass
class _Shot:
    """What the view keeps per projectile in the air."""

    sprite: Sprite
    trail: list[tuple[float, float, float]] = field(default_factory=list)  # (view time, x, y) samples in world pixels
    ground: tuple[float, float] = (0.0, 0.0)  # the point on the ground under the shot, in world pixels
    height: float = 0.0  # tiles above it


@dataclass
class _Recoil:
    started: float
    direction: tuple[float, float]


class MapView:
    def __init__(self, scene: Scene, world: World, player: int, *, reveal: bool = False) -> None:
        """The map as *player* sees it, or the whole of it when *reveal* is set (a replay watched from above)."""
        self.scene = scene
        self.world = world
        self.player = player
        self.reveal = reveal
        self.game: Game = scene.game
        self.time = 0.0
        textures.register_static(self.game)
        textures.register_theme(self.game, world.theme)
        self.scale = self.game.backend.scale_factor
        self._ground: list[Sprite] = []
        self._edge: list[Sprite] = []
        self._ground_keys: list[list[str]] = []  # per chunk: one image, or WATER_PHASES of them when it holds water
        self._water_pending: list[tuple[int, int]] = []  # (chunk, phase) images still to paint, one per frame
        self._water_time = 0.0
        self._water_step = 0
        self._trees: dict[Pos, Sprite] = {}
        self._rocks: dict[Pos, Sprite] = {}
        self._buildings: dict[int, Sprite] = {}
        self._building_keys: dict[int, str] = {}
        self._units: dict[int, Sprite] = {}
        self._travel: dict[int, float] = {}  # distance each unit has walked, for its stride
        self._last_pos: dict[int, tuple[float, float]] = {}
        self._previous_positions: dict[int, tuple[float, float]] = {}
        self._fraction = 1.0
        self._unit_keys: dict[int, str] = {}
        self._recoil: dict[int, _Recoil] = {}
        self._smoke: dict[int, ParticleEmitter] = {}
        self._fire: dict[int, ParticleEmitter] = {}
        self._shots: dict[int, _Shot] = {}
        self._tick_seen = -1
        self._since_tick = 0.0  # seconds of frames since the model last stepped: shots move between steps too
        self._vision_tick = -1
        self._minimap_time = -1.0
        self.fog_key = f"fog.{world.width}x{world.height}"
        self.minimap_key = f"minimap.{world.width}x{world.height}"
        self._register(self.fog_key, self._fog_image())
        self._register(self.minimap_key, self._minimap_image())
        self._fog = scene.add_sprite(Sprite(self.fog_key, position=(-FOG_MARGIN * TILE, -FOG_MARGIN * TILE),
                                            size=((world.width + 2 * FOG_MARGIN) * TILE, (world.height + 2 * FOG_MARGIN) * TILE),
                                            anchor=SpriteAnchor.TOP_LEFT, layer=RenderLayer.EFFECTS, y_sort=True))
        self._build_ground()
        self._build_edge()
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

    def _build_edge(self) -> None:
        world = self.world
        horizontal = textures.map_edge(world.width + 2, self.scale, world.theme)
        vertical = textures.map_edge(world.height, self.scale, world.theme)
        sides = (
            ("top", horizontal, (-TILE, -TILE)),
            ("bottom", horizontal.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (-TILE, world.height * TILE)),
            ("left", vertical.transpose(Image.Transpose.ROTATE_90), (-TILE, 0)),
            ("right", vertical.transpose(Image.Transpose.ROTATE_270), (world.width * TILE, 0)),
        )
        for side, image, position in sides:
            key = f"edge.{side}.{world.width}x{world.height}"
            self._register(key, image)
            if len(self._edge) < 4:
                self._edge.append(self.scene.add_sprite(Sprite(key, position=position,
                    size=(image.width / self.scale, image.height / self.scale), anchor=SpriteAnchor.TOP_LEFT,
                    layer=RenderLayer.UI_WORLD)))

    def _prop(self, key: str, point: tuple[float, float], **kwargs) -> Sprite:
        placement = textures.placements[key]
        wx, wy = to_world(point)
        return self.scene.add_sprite(Sprite(key, position=(wx, wy + placement.drop), size=placement.size, anchor=SpriteAnchor.BOTTOM_CENTER,
                                            layer=RenderLayer.UNITS, y_sort=True, ground=placement.ground, **kwargs))

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
        for burning in (self._smoke, self._fire):
            for emitter in burning.values():
                emitter.remove()
            burning.clear()
        for shot in self._shots.values():
            shot.sprite.remove()
        self._shots.clear()
        self._building_keys.clear()
        self._unit_keys.clear()
        self._travel.clear()
        self._last_pos.clear()
        self._previous_positions.clear()
        self._recoil.clear()
        self.world = world
        textures.register_theme(self.game, world.theme)
        self._build_edge()
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

    def tree_grown(self, pos: Pos) -> None:
        """A felled tree has grown back (the elven art): give it a sprite like the original."""
        if pos not in self._trees and self.world.terrain_at(pos) is Terrain.TREES:
            self._trees[pos] = self._prop(f"tree.{self.world.theme.value}.{textures.scatter(*pos, 3) % textures.TREE_VARIANTS}", (pos[0] + 0.5, pos[1] + 0.5))

    def before_step(self) -> None:
        """Retain the unit positions immediately before an authoritative local step.

        The scene supplies its accumulator fraction to ``sync``. Network scenes
        that do not own fixed steps keep their existing snapshot presentation.
        """
        self._previous_positions = {u.id: u.pos for u in self.world.units.values() if not u.hidden}

    def unit_position(self, unit: Unit) -> tuple[float, float]:
        """The presented ground point, shared by the sprite and attached overlays."""
        previous = self._previous_positions.get(unit.id, unit.pos)
        return (previous[0] + (unit.x - previous[0]) * self._fraction,
                previous[1] + (unit.y - previous[1]) * self._fraction)

    def hit_reaction(self, unit: Unit, source: tuple[float, float] | None) -> None:
        """Recoil from a real hit, composed with each frame's current ground point.

        Never retain a sprite position: the victim may start moving before the
        reaction ends. One reaction per unit also bounds simultaneous impacts.
        """
        dx, dy = (unit.x - source[0], unit.y - source[1]) if source is not None else (0.0, 0.0)
        distance = math.hypot(dx, dy)
        direction = (dx / distance, dy / distance) if distance else (0.0, 0.0)
        self._recoil[unit.id] = _Recoil(self.time, direction)

    def entity_at(self, point: tuple[float, float]) -> Entity | None:
        """Pick what is actually shown, including the interpolated unit bodies."""
        nearest, distance = None, math.inf
        for unit in self.world.units.values():
            sprite = self._units.get(unit.id)
            if unit.hidden or sprite is None or not sprite.visible:
                continue
            gap = math.dist(point, self.unit_position(unit)) - unit.radius
            if gap <= 0.35 and gap < distance:
                nearest, distance = unit, gap
        if nearest is not None:
            return nearest
        tile = (math.floor(point[0]), math.floor(point[1]))
        building = self.world.building_at(tile) if self.world.in_bounds(tile) else None
        return building if building is not None and self._known(building) else None

    def units_in_rect(self, a: tuple[float, float], b: tuple[float, float], *, player: int) -> list[Unit]:
        """Visible owned units whose presented ground points lie inside a box."""
        left, right = sorted((a[0], b[0]))
        top, bottom = sorted((a[1], b[1]))
        result = []
        for unit in self.world.player_units(player):
            sprite = self._units.get(unit.id)
            if unit.hidden or sprite is None or not sprite.visible:
                continue
            x, y = self.unit_position(unit)
            if left <= x <= right and top <= y <= bottom:
                result.append(unit)
        return result

    def sync(self, dt: float = 0.0, *, fraction: float = 1.0) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.time += dt
        world = self.world
        self._animate_water(dt)
        for pos in list(self._trees):
            if world.terrain_at(pos) is not Terrain.TREES:
                self._trees.pop(pos).remove()
        self._sync_buildings()
        self._sync_units()
        self._sync_projectiles(dt)
        if world.tick // VISION_EVERY != self._vision_tick:
            self._vision_tick = world.tick // VISION_EVERY
            self.game.assets.update_image(self.fog_key, self._fog_image())
        if self.time - self._minimap_time >= 0.25:
            self._minimap_time = self.time
            self.game.assets.update_image(self.minimap_key, self._minimap_image())

    def set_reveal(self, reveal: bool) -> None:
        """Show the whole map, or only what the player sees; the fog and minimap follow on the next sync."""
        self.reveal = reveal
        self._vision_tick = -1
        self._minimap_time = -1.0

    def _known(self, building: Building) -> bool:
        return self.reveal or building.player == self.player or any(self.world.is_explored(self.player, t) for t in building.tiles())

    def _sync_buildings(self) -> None:
        world = self.world
        for bid, sprite in list(self._buildings.items()):
            if bid not in world.buildings:
                sprite.remove()
                del self._buildings[bid]
                del self._building_keys[bid]
                for burning in (self._smoke, self._fire):
                    emitter = burning.pop(bid, None)
                    if emitter is not None:
                        emitter.remove()
        for b in world.buildings.values():
            if not self._known(b):
                continue
            rising = not b.done and b.progress >= b.info.build_time / 2  # the second half of construction shows the building going up
            if b.type is BuildingType.GOLD_MINE:
                key = textures.mine_image(self.game, textures.scatter(b.x, b.y, 8) % textures.MINE_VARIANTS)
            elif b.done or rising:
                key = textures.building_image(self.game, b.type, b.player, b.race, building_look(b))  # type: ignore[arg-type]
            else:
                key = f"site.{b.size}"
            sprite = self._buildings.get(b.id)
            if sprite is None:
                sprite = self._buildings[b.id] = self._prop(key, b.center)
                self._building_keys[b.id] = key
            elif self._building_keys[b.id] != key:
                sprite.image = key
                sprite.size = textures.placements[key].size
                sprite.ground = textures.placements[key].ground
                self._building_keys[b.id] = key
            sprite.opacity = 150 if rising else 255
            self._sync_smoke(b, sprite)

    def _sync_smoke(self, b: Building, sprite: Sprite) -> None:
        """A damaged building smoulders under half health and burns under a quarter: smoke from the
        roof, then flames licking up from it."""
        seen = b.done and b.type is not BuildingType.GOLD_MINE and (self.reveal or self.world.is_visible(self.player, (int(b.center[0]), int(b.center[1]))))
        wx, wy = to_world(b.center)
        roof = (wx, wy - b.size * TILE * 0.5)
        self._toggle_emitter(self._smoke, b.id, seen and b.hp < b.max_hp / 2, lambda: ParticleEmitter(
            "smoke", position=roof, speed=(8, 26), direction=(250, 290), lifetime=(1.2, 2.2), size=(18, 18), fade_out=True, layer=RenderLayer.EFFECTS,
        ).continuous(rate=3 + 3 * (1 - b.hp / max(1, b.max_hp))))
        self._toggle_emitter(self._fire, b.id, seen and b.hp < b.max_hp / 4, lambda: ParticleEmitter(
            "spark", position=(roof[0], roof[1] + TILE * 0.35), speed=(25, 60), direction=(250, 290), lifetime=(0.4, 0.8),
            size=(16, 26), fade_out=True, tint=(1.0, 0.45, 0.1), layer=RenderLayer.EFFECTS,
        ).continuous(rate=26))

    def _toggle_emitter(self, store: dict[int, ParticleEmitter], key: int, wanted: bool, make: Callable[[], ParticleEmitter]) -> None:
        """Keep exactly one emitter in *store* under *key* while *wanted*."""
        emitter = store.get(key)
        if wanted and emitter is None:
            store[key] = self.scene.add_emitter(make())
        elif not wanted and emitter is not None:
            emitter.remove()
            del store[key]

    def _frame(self, u: Unit) -> str:
        return unit_frame(u, self._travel.get(u.id, 0.0), self.time)

    def _sync_units(self) -> None:
        world = self.world
        for uid, sprite in list(self._units.items()):
            if uid not in world.units:
                sprite.remove()
                del self._units[uid]
                del self._unit_keys[uid]
                self._travel.pop(uid, None)
                self._last_pos.pop(uid, None)
                self._recoil.pop(uid, None)
        for u in world.units.values():
            position = self.unit_position(u)
            last = self._last_pos.get(u.id, position)
            self._travel[u.id] = self._travel.get(u.id, 0.0) + math.dist(position, last)
            self._last_pos[u.id] = position
            sprite = self._units.get(u.id)
            shown = not u.hidden and (self.reveal or u.player == self.player or world.is_visible(self.player, u.tile))
            if not shown:
                reaction = self._recoil.pop(u.id, None)
                if sprite is not None:
                    sprite.visible = False
                    if reaction is not None:
                        sprite.rotation = 0.0
                continue
            # Draw the combat tool with free hands; the model keeps the worker's load.
            carrying = None if u.state == "attack" else u.carrying
            key = textures.unit_image(self.game, u.type, u.player, textures.facing_index(u.facing), self._frame(u), carrying, race=u.race)
            if sprite is None:
                sprite = self._units[u.id] = self._prop(key, position)
                self._unit_keys[u.id] = key
            else:
                if self._unit_keys[u.id] != key:
                    sprite.image = key
                    sprite.size = textures.placements[key].size
                    sprite.ground = textures.placements[key].ground
                    self._unit_keys[u.id] = key
            wx, wy = to_world(position)
            wy += textures.placements[key].drop
            lunge = _melee_lunge(u, self._fraction)
            if lunge:
                wx += math.cos(u.facing) * lunge
                wy += math.sin(u.facing) * lunge
            reaction = self._recoil.get(u.id)
            if reaction is not None:
                t = (self.time - reaction.started) / 0.22
                if t >= 1.0:
                    del self._recoil[u.id]
                    sprite.rotation = 0.0
                else:
                    displacement = 3.0 * math.sin(math.pi * t)
                    wx += reaction.direction[0] * displacement
                    wy += reaction.direction[1] * displacement
                    sprite.rotation = 6.0 * math.sin(2 * math.pi * t) * (1 - t)
            sprite.position = (wx, wy)
            sprite.visible = True

    def _sync_projectiles(self, dt: float) -> None:
        """A sprite per shot in the air, moved every frame (between model steps as well), and the
        trail it leaves behind."""
        world = self.world
        if world.tick != self._tick_seen:
            self._tick_seen, self._since_tick = world.tick, 0.0
        else:
            self._since_tick = min(SIM_DT, self._since_tick + dt)
        now = world.time + self._since_tick
        for pid, shot in list(self._shots.items()):
            if pid not in world.projectiles:
                shot.sprite.remove()
                del self._shots[pid]
        for p in world.projectiles.values():
            x, y, height = projectile_point(p, world, now)
            shot = self._shots.get(p.id)
            if not (p.player == self.player or world.is_visible(self.player, (int(x), int(y)))):
                if shot is not None:
                    shot.sprite.visible = False
                continue
            gx, gy = to_world((x, y))
            position = (gx, gy - height * TILE)
            if shot is None:
                size = (14, 14) if p.kind == "stone" else (22, 6)
                shot = self._shots[p.id] = _Shot(self.scene.add_sprite(Sprite(p.kind, position=position, size=size, layer=RenderLayer.EFFECTS)))
            elif p.kind == "arrow" and shot.trail:
                shot.sprite.rotation = math.degrees(math.atan2(position[1] - shot.trail[-1][2], position[0] - shot.trail[-1][1]))
            shot.sprite.position = position
            shot.sprite.visible = True
            shot.ground, shot.height = (gx, gy), height
            shot.trail.append((self.time, *position))
            while self.time - shot.trail[0][0] > TRAIL[p.kind]:
                shot.trail.pop(0)

    def _draw_projectiles(self) -> None:
        """The trail behind each shot, and under a stone its shadow on the ground and the ring where it will come down."""
        world, scene = self.world, self.scene
        for p in world.projectiles.values():
            shot = self._shots.get(p.id)
            if shot is None or not shot.sprite.visible:
                continue
            color, hang = TRAIL_COLOR[p.kind], TRAIL[p.kind]
            for (_, x0, y0), (t1, x1, y1) in zip(shot.trail, shot.trail[1:]):
                age = (self.time - t1) / hang
                scene.draw_line(x0, y0, x1, y1, (*color, round(210 * (1 - age))), 3.0 - 2.0 * age if p.kind == "stone" else 1.5,
                                space="world", layer=RenderLayer.EFFECTS)
            if p.kind != "stone":
                continue
            gx, gy = shot.ground
            shade = max(2.0, 6.0 - shot.height * 1.2)
            scene.draw_polygon([(gx + shade * 1.6 * math.cos(i * math.pi / 5), gy + shade * math.sin(i * math.pi / 5)) for i in range(10)],
                               (20, 16, 12, 90), space="world", layer=RenderLayer.EFFECTS)
            if world.is_visible(self.player, (int(p.aim[0]), int(p.aim[1]))):
                ax, ay = to_world(p.aim)
                ring = (*world.players[p.player].color, 130) if p.player == self.player else (255, 90, 70, 110)
                self._ring(ax, ay, p.splash * TILE, p.splash * TILE * 0.62, ring, 1.5, layer=RenderLayer.EFFECTS)

    def unit_sprite(self, unit_id: int) -> Sprite | None:
        return self._units.get(unit_id)

    def release_unit_sprite(self, unit_id: int) -> Sprite | None:
        """Hand a unit's sprite to the caller (for a death animation) instead of removing it on the next sync."""
        sprite = self._units.pop(unit_id, None)
        self._unit_keys.pop(unit_id, None)
        self._recoil.pop(unit_id, None)
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
        if self.reveal:
            alpha[:] = 0
        rgba = np.empty((*shape, 4), dtype=np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = FOG_COLOR
        rgba[..., 3] = alpha
        image = Image.new("RGBA", (world.width + 2 * FOG_MARGIN, world.height + 2 * FOG_MARGIN), (*FOG_COLOR, 255))
        image.paste(Image.fromarray(rgba, "RGBA"), (FOG_MARGIN, FOG_MARGIN))
        return image

    def _minimap_terrain(self) -> np.ndarray:
        return minimap_terrain(self.world)

    def _minimap_image(self) -> Image.Image:
        world = self.world
        shape = (world.height, world.width)
        visible = np.frombuffer(bytes(world.visible[self.player]), dtype=np.uint8).reshape(shape) > 0
        explored = np.frombuffer(bytes(world.explored[self.player]), dtype=np.uint8).reshape(shape) > 0
        if self.reveal:
            visible[:] = explored[:] = True
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
        self._draw_wood_chips()
        self._draw_projectiles()
        self._draw_melee_trails()
        for eid in overlay.selected + ([overlay.hovered] if overlay.hovered is not None and overlay.hovered not in overlay.selected else []):
            entity = world.entity(eid)
            if entity is None:
                continue
            color = self._entity_color(entity)
            if isinstance(entity, Unit):
                if entity.hidden:
                    continue
                wx, wy = to_world(self.unit_position(entity))
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
            key = textures.building_image(self.game, building_type, self.player, world.players[self.player].race)
            placement = textures.placements[key]
            cx, cy = (gx + size / 2) * TILE, (gy + size / 2) * TILE
            w, h = placement.size
            scene.draw_image(key, cx - w / 2, cy + placement.drop - h, w, h, opacity=0.55 if ok else 0.3, space="world", layer=RenderLayer.UI_WORLD)

    def _draw_wood_chips(self) -> None:
        """A short burst at axe contact, driven by the same harvest clock as the pose."""
        for u in self.world.units.values():
            sprite = self.unit_sprite(u.id)
            if u.state != "chop" or u.carrying is not None or sprite is None or not sprite.visible:
                continue
            phase = (u.timer / CHOP_PERIOD) % 1.0
            if not 0.45 <= phase < 0.9:
                continue
            t = (phase - 0.45) / 0.45
            wx, wy = to_world(u.pos)
            dx, dy = textures.chop_contact_offset(textures.facing_index(u.facing), u.race)
            wx, wy = wx + dx, wy + dy
            for i in range(5):
                side = (i - 2) * 4.0
                x = wx + side * t
                y = wy - (10 + i % 3 * 4) * t + 20 * t * t
                self.scene.draw_line(x, y, x + 2 + i % 2, y - 1.5, (238, 202, 139, round(235 * (1 - t))), 1.5,
                                     space="world", layer=RenderLayer.EFFECTS)

    def _draw_melee_trails(self) -> None:
        """A brief afterimage of the released cut; damage still owns impact feedback."""
        for u in self.world.units.values():
            if u.type not in (UnitType.FOOTMAN, UnitType.PEASANT, UnitType.SCOUT, UnitType.KNIGHT) or u.state != "attack" or u.windup > 0 or u.cooldown <= 0:
                continue
            age = u.info.cooldown - u.cooldown + self._fraction * SIM_DT
            if not 0 <= age < 0.09:
                continue
            sprite = self.unit_sprite(u.id)
            if sprite is None or not sprite.visible:
                continue
            wx, wy = sprite.x, sprite.y - textures.placements[sprite.image].drop
            key = textures.melee_trail_image(self.game, u.type, textures.facing_index(u.facing), u.race)
            placement = textures.placements[key]
            width, height = placement.size
            fade = (1 - age / 0.09) ** 2
            self.scene.draw_image(key, wx - width / 2, wy + placement.drop - height, width, height,
                                  opacity=fade, space="world", layer=RenderLayer.EFFECTS)
