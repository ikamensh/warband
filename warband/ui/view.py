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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from saga2d import Game, ParticleEmitter, RenderLayer, Scene, Sprite, SpriteAnchor
from warband.art import monsters, textures
from warband.art.monsters import Monster
from warband.sim.model import Building, Entity, Pos, Projectile, Unit, World, dist
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, CREATURES, SIM_DT, VISION_EVERY, BuildingType, Race, Terrain, UnitType, UPGRADES
from warband.art.textures import CHUNK, CHUNK_PX, TILE

CREATURE_SET = frozenset(CREATURES)  # the neutral creatures, asked of a unit's type on every frame

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


def building_look(b: Building, worked: Collection[int] = ()) -> str:
    """Which painted look a building wears: going up, founded for the first half of its construction
    and raised for the second; damaged under half its hit points, active while it trains or
    researches, intact otherwise.  A gold deposit is active while a peasant works inside it: its id
    is among *worked*."""
    if b.info.mine is not None:
        return "active" if b.id in worked else "intact"
    if b.type is BuildingType.LAIR:
        # A den is raised complete and trains nothing, so it wears only intact and damaged: whole,
        # or torn down to half its hit points like every other building.
        return "damaged" if b.hp < b.max_hp / 2 else "intact"
    if not b.done:
        return "founded" if b.progress < b.info.build_time / 2 else "raised"
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
    bars_for_all: bool = False  # Alt held: every visible unit and building shows its health


@dataclass
class Sighting:
    """A building as the player last saw it.  Under the fog this is all the map, the minimap and the
    selection panel show of it: a rival's new hall is not there until somebody looks, and a razed one
    stands until somebody looks again."""

    id: int
    type: BuildingType
    player: int | None
    race: Race
    rect: tuple[int, int, int, int]
    hp: int
    max_hp: int
    built: float  # share of its construction done: 1 once it stands
    gold: int  # what a mine held
    abandoned: bool
    look: str  # the painted look it wore, see :func:`building_look`
    lair_kind: str = "wolf"  # whose den it is, for a lair: a :class:`~warband.art.monsters.LairKind` value

    @classmethod
    def of(cls, b: Building, worked: Collection[int] = ()) -> Sighting:
        sighting = cls(b.id, b.type, b.player, b.race, b.rect, 0, 0, 0.0, 0, False, "intact")
        sighting.refresh(b, worked)
        return sighting

    def refresh(self, b: Building, worked: Collection[int] = ()) -> None:
        """The player is looking at *b* (and at the mines in *worked* being worked): remember it as it is now."""
        self.hp, self.max_hp, self.gold, self.abandoned, self.look = b.hp, b.max_hp, b.gold, b.abandoned, building_look(b, worked)
        self.built = 1.0 if b.done else b.progress / b.info.build_time

    @property
    def done(self) -> bool:
        return self.built >= 1.0

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.rect
        return (x + w / 2, y + h / 2)

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type.value, "player": self.player, "race": self.race.value, "rect": list(self.rect), "hp": self.hp,
                "max_hp": self.max_hp, "built": self.built, "gold": self.gold, "abandoned": self.abandoned, "look": self.look,
                "lair_kind": self.lair_kind}

    @classmethod
    def from_dict(cls, d: dict) -> Sighting:
        if d["look"] not in textures.BUILDING_LOOKS:
            raise ValueError(f"unknown building look {d['look']!r}")
        kind = monsters.LairKind(d.get("lair_kind", "wolf"))  # saves from before the dens diverged remember none
        return cls(d["id"], BuildingType(d["type"]), d["player"], Race(d["race"]), tuple(d["rect"]), d["hp"], d["max_hp"], d["built"], d["gold"],
                   d["abandoned"], d["look"], kind.value)


def check_memory(memory: dict, world: World) -> None:
    """Raise ValueError (or KeyError, TypeError) unless *memory* is what :meth:`MapView.memory` writes for a map like *world*."""
    for saved in memory["buildings"]:
        x, y, w, h = Sighting.from_dict(saved).rect
        if not (world.in_bounds((x, y)) and world.in_bounds((x + w - 1, y + h - 1))):
            raise ValueError("a remembered building lies off the map")


def minimap_terrain(world: World, terrain_at: Callable[[Pos], Terrain] | None = None) -> np.ndarray:
    """Terrain colours for *world* from ``textures.PALETTES[theme].minimap``: the ground as it
    is, or as *terrain_at* tells it (what a player remembers of it).

    A ``(height, width, 3)`` float array shared by the HUD minimap and the
    new-game preview, so both pictures agree on what grass, water, trees
    and rock look like.
    """
    colours = textures.PALETTES[world.theme].minimap
    terrain_at = terrain_at if terrain_at is not None else world.terrain_at
    base = np.zeros((world.height, world.width, 3), dtype=np.float32)
    for y in range(world.height):
        for x in range(world.width):
            base[y, x] = colours[terrain_at((x, y))]
    return base


STRIDE = 0.22  # tiles travelled per walk frame: feet stay planted instead of sliding, and faster units step faster
STRIKE, FOLLOW, RECOVER = 0.1, 0.16, 0.16  # seconds after the blow: driven forward, swept across, settling to guard
#: Whose shot is not the arrow the model flies it as.  The model tells a shot that follows its mark from a stone
#: that comes down on the ground; what it looks like is the striker's, as what it lands as is (``sound.impact_sound``):
#: a healer looses no arrow but a mote of light, from the head of its staff.
SHOT_LOOKS = {UnitType.CLERIC.value: "mote", UnitType.SPIDER.value: "venom"}
SHOT_SIZE = {"arrow": (22, 6), "stone": (14, 14), "mote": (20, 20), "venom": (16, 16)}
STAFF_REACH = 0.4  # tiles before a healer that the head of its staff is held, where its mote is first seen
RING_FLATTEN = 0.62  # a circle on the ground seen from the game's elevation is this much shorter than it is wide
PICK_SLACK = 0.35  # tiles beyond a unit's body a click still picks it: the figure stands above the ground point it is clicked at
TRAIL = {"arrow": 0.12, "stone": 0.45, "mote": 0.1, "venom": 0.14}  # seconds of flight a shot leaves hanging in the air behind it
TRAIL_COLOR = {"arrow": (250, 246, 226), "stone": (228, 216, 194), "mote": (255, 232, 150), "venom": (198, 132, 226)}
TRAIL_WIDTH = {"arrow": (1.5, 1.5), "stone": (3.0, 1.0), "mote": (3.0, 0.5), "venom": (2.6, 0.5)}  # at the shot and where the trail ends
BAR_OUTLINE = (0, 0, 0, 190)  # the backing and outline of every health and progress bar
#: Nobody's building on the minimap and on the New game preview: a gold deposit, and the one thing on
#: either picture that is not a seat.  The gold it used to be, (232, 196, 70), is three units of
#: CIE76 from Amber, so an Amber player's halls were their own mines; this straw is twenty-seven
#: from the nearest seat colour and forty-three from any ground.
NEUTRAL_MINIMAP = (255, 255, 159)
ABANDONED_MINIMAP = (150, 150, 150)


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
    if u.state in ("repair", "salvage"):  # the same swing of the hammer, one way or the other
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


def shot_look(p: Projectile) -> str:
    """What shot *p* is drawn as: its striker's own look (:data:`SHOT_LOOKS`), or else its kind."""
    return SHOT_LOOKS.get(p.source_type, p.kind)


def projectile_point(p: Projectile, world: World, now: float) -> tuple[float, float, float]:
    """Where a shot is at simulation time *now*: its ground position in tiles and its height above the
    ground, in tiles.  An arrow flies at its mark's current position on a flat arc; a mote of light straight,
    from the head of the staff held out before the healer; a stone lobs high to the ground it was fired at."""
    t = max(0.0, min(1.0, (now - p.launched) / p.flight))
    x, y = world.shot_ground(p, now)
    mark = world.shot_mark(p)
    span = dist(p.start, mark)
    if p.kind == "stone":
        return x, y, 0.55 + 4 * (0.5 + 0.14 * span) * t * (1 - t)
    if shot_look(p) in ("mote", "venom"):
        ahead = STAFF_REACH * (1 - t) / span if span > STAFF_REACH else 0.0  # the drawn start only: the blow is the model's
        return x + (mark[0] - p.start[0]) * ahead, y + (mark[1] - p.start[1]) * ahead, 1.0 + (0.45 - 1.0) * t
    lift = 1.7 if p.source_type == BuildingType.TOWER.value else 0.55  # loosed from the battlements, or from the shoulder
    return x, y, lift + (0.45 - lift) * t + 0.35 * math.sin(math.pi * t) * min(1.0, span / 4)


@dataclass
class _Shot:
    """What the view keeps per projectile in the air."""

    sprite: Sprite
    look: str  # which image, trail and flight: shot_look's answer when it was loosed
    trail: list[tuple[float, float, float]] = field(default_factory=list)  # (view time, x, y) samples in world pixels
    ground: tuple[float, float] = (0.0, 0.0)  # the point on the ground under the shot, in world pixels
    height: float = 0.0  # tiles above it


@dataclass
class _Recoil:
    started: float
    direction: tuple[float, float]


class MapView:
    def __init__(self, scene: Scene, world: World, player: int, *, reveal: bool = False, memory: dict | None = None) -> None:
        """The map as *player* sees it, or the whole of it when *reveal* is set (a replay watched from above).

        *memory* is what an earlier view of this match remembered (see :meth:`memory`): ground out of
        sight shows what the player last saw there, not what stands there now."""
        self.scene = scene
        self.world = world
        self.player = player
        self.reveal = reveal
        self.game: Game = scene.game
        self.time = 0.0
        textures.register_static(self.game)
        textures.register_theme(self.game, world.theme)
        self.scale = self.game.backend.scale_factor
        # Ground and edge images are rasterised for this window: another scale is another image, never a redraw in place.
        self._map_key = f"{world.width}x{world.height}@{self.scale:g}"
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
        self._sightings: dict[int, Sighting] = {}  # every building the player has seen, as they last saw it
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
        self._minimap_ground = minimap_terrain(world, self.terrain_at)  # as the player knows it: a tree felled out of sight still stands
        self._register(self.fog_key, self.fog_image())
        self._register(self.minimap_key, self.minimap_image())
        self._fog = scene.add_sprite(Sprite(self.fog_key, position=(-FOG_MARGIN * TILE, -FOG_MARGIN * TILE),
                                            size=((world.width + 2 * FOG_MARGIN) * TILE, (world.height + 2 * FOG_MARGIN) * TILE),
                                            anchor=SpriteAnchor.TOP_LEFT, layer=RenderLayer.EFFECTS, y_sort=True))
        self._build_ground()
        self._build_edge()
        self._build_props()
        self._recall(memory)
        self.sync()

    # -- Setup ------------------------------------------------------------------------

    def _register(self, key: str, image: Image.Image) -> None:
        """Register an image, or redraw it in place if an earlier map of this size left one at this scale."""
        if self.game.assets.has_image(key):
            self.game.assets.update_image(key, image)
        else:
            self.game.assets.image_from_pil(key, image)

    def chunk_has_water(self, index: int) -> bool:
        world = self.world
        cols = math.ceil(world.width / CHUNK)
        cx, cy = index % cols, index // cols
        return any(world.in_bounds((x, y)) and world.terrain_at((x, y)) is Terrain.WATER
                   for y in range(cy * CHUNK - 1, (cy + 1) * CHUNK + 1) for x in range(cx * CHUNK - 1, (cx + 1) * CHUNK + 1))

    def chunk_keys(self, index: int) -> list[str]:
        world = self.world
        phases = textures.WATER_PHASES if self.chunk_has_water(index) else 1
        return [f"ground.{index}.{self._map_key}.{phase}" for phase in range(phases)]

    def _paint_chunk(self, index: int, phase: int) -> None:
        world = self.world
        cols = math.ceil(world.width / CHUNK)
        self._register(self._ground_keys[index][phase], textures.ground_chunk(world.terrain_at, world.in_bounds, index % cols, index // cols, self.scale, world.theme, phase))

    def _build_ground(self) -> None:
        world = self.world
        cols, rows = math.ceil(world.width / CHUNK), math.ceil(world.height / CHUNK)
        for index in range(cols * rows):
            cx, cy = index % cols, index // cols
            self._ground_keys.append(self.chunk_keys(index))
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
            key = f"edge.{side}.{self._map_key}"
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

    def _tree(self, pos: Pos) -> Sprite:
        x, y = pos
        return self._prop(f"tree.{self.world.theme.value}.{textures.scatter(x, y, 3) % textures.TREE_VARIANTS}", (x + 0.5, y + 0.5))

    def _build_props(self) -> None:
        world = self.world
        for y in range(world.height):
            for x in range(world.width):
                terrain = self.terrain_at((x, y))
                if terrain is Terrain.TREES:
                    self._trees[(x, y)] = self._tree((x, y))
                elif terrain is Terrain.ROCK:
                    self._rocks[(x, y)] = self._prop(f"rock.{world.theme.value}.{textures.scatter(x, y, 4) % textures.ROCK_VARIANTS}", (x + 0.5, y + 0.5))

    def reset(self, world: World, memory: dict | None = None) -> None:
        """Point the view at another world of the same size (after loading a save), with the *memory* saved with it."""
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
        self._sightings.clear()
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
            keys = self._ground_keys[index] = self.chunk_keys(index)  # the water may lie elsewhere on this map
            self._paint_chunk(index, 0)
            sprite.image = keys[0]
            self._water_pending.extend((index, phase) for phase in range(1, len(keys)))
        self._build_props()
        self._minimap_ground = minimap_terrain(world, self.terrain_at)
        self._recall(memory)
        self.sync()

    # -- What the player remembers ----------------------------------------------------------

    def memory(self) -> dict:
        """The buildings as the player last saw them, as JSON for a save.  Where things stand and what the
        ground is like the model remembers itself (``World.worker_knowledge``); how a building looked it does not."""
        return {"buildings": [sighting.to_dict() for sighting in self._sightings.values()]}

    def _recall(self, memory: dict | None) -> None:
        """Start from *memory*; without one (a new match, a save from before the view remembered) from the
        buildings whose footprints the model remembers for the player, as they look now."""
        world = self.world
        if memory is None:
            footprints = world.worker_knowledge[self.player].buildings
            known = [Sighting.of(b) for b in world.buildings.values() if b.player == self.player or b.id in footprints]
        else:
            known = [Sighting.from_dict(d) for d in memory["buildings"]]
        for sighting in known:
            self._show(sighting)

    def sighting(self, building_id: int) -> Sighting | None:
        """What the player knows of a building: as it is while they see it, as they last saw it otherwise."""
        return self._sightings.get(building_id)

    def terrain_at(self, pos: Pos) -> Terrain:
        """The ground at *pos* as the player knows it: a tree felled out of sight still stands for them."""
        world = self.world
        remembered = None if self.reveal else world.worker_knowledge[self.player].terrain[pos[1] * world.width + pos[0]]
        return remembered if remembered is not None else world.terrain_at(pos)

    # -- Sync ----------------------------------------------------------------------------

    def tree_felled(self, pos: Pos) -> None:
        """A tree came down: gone from the map at once when the player sees it fall, rather than at the next look around."""
        if pos in self._trees and (self.reveal or self.world.is_visible(self.player, pos)):
            self._trees.pop(pos).remove()
            self._minimap_ground[pos[1], pos[0]] = textures.PALETTES[self.world.theme].minimap[Terrain.GRASS]

    def _sync_trees(self) -> None:
        """The trees the player knows of, each with a sprite: one they see felled loses it, one they see
        grown back (the elven art) gets one like the original; out of sight both wait to be seen."""
        world, width = self.world, self.world.width
        if self.reveal:
            standing = {(x, y) for y, row in enumerate(world.terrain) for x, terrain in enumerate(row) if terrain is Terrain.TREES}
        else:
            knowledge = world.worker_knowledge[self.player]
            standing = {(index % width, index // width) for index in knowledge.trees}
            standing.update(pos for pos in self._trees if knowledge.terrain[pos[1] * width + pos[0]] is None)  # never looked at: left as it is
        colours = textures.PALETTES[world.theme].minimap
        for pos in self._trees.keys() - standing:
            self._trees.pop(pos).remove()
            self._minimap_ground[pos[1], pos[0]] = colours[Terrain.GRASS]
        for pos in standing - self._trees.keys():
            self._trees[pos] = self._tree(pos)
            self._minimap_ground[pos[1], pos[0]] = colours[Terrain.TREES]

    def before_step(self) -> None:
        """Retain the unit positions immediately before an authoritative local step.

        The scene supplies its accumulator fraction to ``sync``. Network scenes
        that do not own fixed steps keep their existing snapshot presentation.
        """
        self._previous_positions = {u.id: u.pos for u in self.world.units.values() if not u.hidden}

    def drawn_positions(self) -> dict[int, tuple[float, float]]:
        """Where every unit in the open is drawn now."""
        return {u.id: self.unit_position(u) for u in self.world.units.values() if not u.hidden}

    def present_from(self, drawn: dict[int, tuple[float, float]]) -> None:
        """Move units on from *drawn*, where they were drawn before a network snapshot replaced the world, towards
        where the snapshot puts them, as the scene's fraction runs to one.  A unit not in *drawn* is placed."""
        self._previous_positions = drawn

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
            if gap <= PICK_SLACK and gap < distance:
                nearest, distance = unit, gap
        if nearest is not None:
            return nearest
        tile = (math.floor(point[0]), math.floor(point[1]))
        building = self.world.building_at(tile) if self.world.in_bounds(tile) else None
        return building if building is not None and building.id in self._sightings else None  # one never seen is not there to pick

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
        self._sync_buildings()
        self._sync_units()
        self._sync_projectiles(dt)
        if world.tick // VISION_EVERY != self._vision_tick:  # what the player knows of the ground changes with what they see
            self._vision_tick = world.tick // VISION_EVERY
            self._sync_trees()
            self.game.assets.update_image(self.fog_key, self.fog_image())
        if self.time - self._minimap_time >= 0.25:
            self._minimap_time = self.time
            self.game.assets.update_image(self.minimap_key, self.minimap_image())

    def set_reveal(self, reveal: bool) -> None:
        """Show the whole map, or only what the player sees; the fog and minimap follow on the next sync.  With the fog
        back, what only the reveal showed goes back into it: a building the player never saw is not remembered."""
        self.reveal = reveal
        if not reveal:
            known = self.world.worker_knowledge[self.player].buildings
            for bid, sighting in list(self._sightings.items()):
                if sighting.player != self.player and bid not in known:
                    self._forget(bid)
        self._vision_tick = -1
        self._minimap_time = -1.0

    def _sync_buildings(self) -> None:
        """Buildings in sight are shown as they are and remembered so; out of sight they stay as last seen,
        until the player looks at the ground again and finds them changed or gone."""
        world = self.world
        worked = {u.inside for u in world.units.values() if u.inside is not None}  # mines with a peasant at the face
        for b in world.buildings.values():
            if not self._seen(b):
                self._quench(b.id)
                continue
            sighting = self._sightings.get(b.id)
            if sighting is None:
                sighting = Sighting.of(b, worked)
            else:
                sighting.refresh(b, worked)
            if sighting.type is BuildingType.LAIR:
                # Whose den it is never changes: the roster it was raised with names it, so looking at it
                # again cannot rename it, and a den remembered out of sight keeps the kind it was seen with.
                camp = next((c for c in world.camps if c.lair == b.id), None)
                if camp is not None:
                    sighting.lair_kind = monsters.lair_kind_for_camp(camp).value
            self._sync_smoke(b, self._show(sighting))
        for bid, sighting in list(self._sightings.items()):
            if bid not in world.buildings and (self.reveal or sighting.player == self.player or world.any_visible(self.player, sighting.rect)):
                self._forget(bid)

    def _forget(self, building_id: int) -> None:
        """Drop the sighting of *building_id* and the sprite that showed it."""
        del self._sightings[building_id]
        self._buildings.pop(building_id).remove()
        del self._building_keys[building_id]
        self._quench(building_id)

    def _show(self, sighting: Sighting) -> Sprite:
        """Keep *sighting* and the sprite that shows it."""
        self._sightings[sighting.id] = sighting
        x, y, size, _ = sighting.rect
        # A site wears its painted founded or raised look; without the painting (the low-poly art), a plain site for
        # the first half and the building faded in for the second.
        deposit = BUILDINGS[sighting.type].mine
        lair = sighting.type is BuildingType.LAIR
        painted_site = not sighting.done and deposit is None and not lair and textures.has_look(sighting.race, sighting.look)
        rising = not painted_site and not lair and 0.5 <= sighting.built < 1.0
        if lair:
            # One den per creature, never a race's and never a team's — wearing the match's landscape.
            key = monsters.lair_image(self.game, monsters.LairKind(sighting.lair_kind), sighting.look, self.world.theme)
        elif deposit is not None:
            key = textures.deposit_image(self.game, sighting.type, textures.scatter(x, y, 8) % textures.mine_variants(), sighting.look)
        elif sighting.done or painted_site:
            key = textures.building_image(self.game, sighting.type, sighting.player, sighting.race, sighting.look, abandoned=sighting.abandoned)  # type: ignore[arg-type]
        elif rising:
            key = textures.building_image(self.game, sighting.type, sighting.player, sighting.race, "intact", abandoned=sighting.abandoned)  # type: ignore[arg-type]
        else:
            key = f"site.{size}"
        sprite = self._buildings.get(sighting.id)
        if sprite is None:
            sprite = self._buildings[sighting.id] = self._prop(key, sighting.center)
            self._building_keys[sighting.id] = key
        elif self._building_keys[sighting.id] != key:
            sprite.image = key
            sprite.size = textures.placements[key].size
            sprite.ground = textures.placements[key].ground
            self._building_keys[sighting.id] = key
        sprite.opacity = 150 if rising else 255
        return sprite

    def _quench(self, building_id: int) -> None:
        """No smoke or flames over a building out of sight, or gone."""
        for burning in (self._smoke, self._fire):
            emitter = burning.pop(building_id, None)
            if emitter is not None:
                emitter.remove()

    def _sync_smoke(self, b: Building, sprite: Sprite) -> None:
        """A damaged building smoulders under half health and burns under a quarter: smoke from the
        roof, then flames licking up from it."""
        seen = b.done and b.info.mine is None and (self.reveal or self.world.is_visible(self.player, (int(b.center[0]), int(b.center[1]))))
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
            if not self.shows(u):
                reaction = self._recoil.pop(u.id, None)
                if sprite is not None:
                    sprite.visible = False
                    if reaction is not None:
                        sprite.rotation = 0.0
                continue
            # Draw the combat tool with free hands; the model keeps the worker's load.
            carrying = None if u.state == "attack" else u.carrying
            facing, frame = textures.facing_index(u.facing), self._frame(u)
            # A creature is nobody's: its sheet takes no player and is never team-recoloured, so it is
            # reached through warband.art.monsters rather than through the units' own table — in the
            # match's landscape coat, like the ground it stands on.
            key = (monsters.monster_image(self.game, Monster(u.type.value), facing, frame, world.theme) if u.type in CREATURE_SET
                   else textures.unit_image(self.game, u.type, u.player, facing, frame, carrying, race=u.race))
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
                look = shot_look(p)
                sprite = Sprite(look, position=position, size=SHOT_SIZE[look], layer=RenderLayer.EFFECTS)
                shot = self._shots[p.id] = _Shot(self.scene.add_sprite(sprite), look)
            if shot.look == "arrow":  # it points where it flies: from where it just was, or on its first frame to where it will be
                if shot.trail:
                    behind, ahead = shot.trail[-1][1:], position
                else:
                    ax, ay, above = projectile_point(p, world, now + SIM_DT)
                    behind, ahead = position, (ax * TILE, (ay - above) * TILE)
                shot.sprite.rotation = math.degrees(math.atan2(ahead[1] - behind[1], ahead[0] - behind[0]))
            shot.sprite.position = position
            shot.sprite.visible = True
            shot.ground, shot.height = (gx, gy), height
            shot.trail.append((self.time, *position))
            while self.time - shot.trail[0][0] > TRAIL[shot.look]:
                shot.trail.pop(0)

    def _draw_projectiles(self) -> None:
        """The trail behind each shot, and under a stone its shadow on the ground and the ring where it will come down."""
        world, scene = self.world, self.scene
        for p in world.projectiles.values():
            shot = self._shots.get(p.id)
            if shot is None or not shot.sprite.visible:
                continue
            color, hang, (head, tail) = TRAIL_COLOR[shot.look], TRAIL[shot.look], TRAIL_WIDTH[shot.look]
            for (_, x0, y0), (t1, x1, y1) in zip(shot.trail, shot.trail[1:]):
                age = (self.time - t1) / hang
                scene.draw_line(x0, y0, x1, y1, (*color, round(210 * (1 - age))), head + (tail - head) * age,
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

    @property
    def tree_sprites(self) -> Mapping[Pos, Sprite]:
        """The trees the player's map shows, by tile, as the player last saw them."""
        return self._trees

    @property
    def ground_sprites(self) -> Sequence[Sprite]:
        """The ground's chunks, row by row."""
        return self._ground

    @property
    def ground_keys(self) -> Sequence[Sequence[str]]:
        """Each ground chunk's image, or one per water phase for a chunk that holds water."""
        return self._ground_keys

    @property
    def water_pending(self) -> int:
        """Water phases still to be painted, one a frame."""
        return len(self._water_pending)

    @property
    def smoke(self) -> Mapping[int, ParticleEmitter]:
        """The smoke rising from damaged buildings, by building id."""
        return self._smoke

    @property
    def fires(self) -> Mapping[int, ParticleEmitter]:
        """The fires on badly damaged buildings, by building id."""
        return self._fire

    @property
    def shot_sprites(self) -> dict[int, Sprite]:
        """The shots in the air, by projectile id."""
        return {shot_id: shot.sprite for shot_id, shot in self._shots.items()}

    # -- Fog and minimap --------------------------------------------------------------------

    def fog_image(self) -> Image.Image:
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

    def minimap_image(self) -> Image.Image:
        world = self.world
        shape = (world.height, world.width)
        visible = np.frombuffer(bytes(world.visible[self.player]), dtype=np.uint8).reshape(shape) > 0
        explored = np.frombuffer(bytes(world.explored[self.player]), dtype=np.uint8).reshape(shape) > 0
        if self.reveal:
            visible[:] = explored[:] = True
        img = self._minimap_ground * np.where(visible, 1.0, np.where(explored, 0.6, 0.18))[..., None]
        for b in self._sightings.values():  # as last seen: a rival's new hall is not on the minimap before it is on the map
            x, y, w, h = b.rect
            img[y:y + h, x:x + w] = ABANDONED_MINIMAP if b.abandoned else NEUTRAL_MINIMAP if b.player is None else world.players[b.player].color
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

    def _entity_color(self, entity: Unit | Sighting) -> Color:
        from warband.ui.style import ENEMY, GOLD, SELECT

        if entity.player is None:
            return GOLD
        if isinstance(entity, Sighting) and entity.abandoned:
            return (150, 150, 150, 255)
        return SELECT if entity.player == self.player else ENEMY

    def _bar(self, x0: float, y: float, width: float, fill: float, color: Color) -> None:
        """A bar *width* wide from (*x0*, *y*), 5 screen pixels tall at any zoom: *fill* of it in *color* on a dark
        backing inside a 1 px outline.  The backing and the fill span the same rows, so the scene gives them one
        draw order (a world rect sorts by its bottom edge, in bands) and the fill, pushed second, lands on top
        wherever the bar is; the outline's top and bottom edges are strips of their own that overlap nothing."""
        px = 1 / self.scene.camera.zoom  # one screen pixel in world units
        height = 5 * px
        draw = self.scene.draw_rect
        draw(x0 - px, y - px, width + 2 * px, px, BAR_OUTLINE, space="world", layer=RenderLayer.UI_WORLD)
        draw(x0 - px, y, width + 2 * px, height, BAR_OUTLINE, space="world", layer=RenderLayer.UI_WORLD)
        draw(x0, y, fill, height, color, space="world", layer=RenderLayer.UI_WORLD)
        draw(x0 - px, y + height, width + 2 * px, px, BAR_OUTLINE, space="world", layer=RenderLayer.UI_WORLD)

    def _health_bar(self, entity: Entity, x: float, y: float, width: float) -> None:
        """A health bar *width* wide centred on *x* with its fill's top at *y*."""
        if isinstance(entity, Building) and entity.info.mine is not None:
            return
        frac = max(0.0, min(1.0, entity.hp / max(1, entity.max_hp)))
        color = (110, 230, 110, 255) if frac > 0.5 else (240, 200, 80, 255) if frac > 0.25 else (240, 90, 70, 255)
        self._bar(x - width / 2, y, width, width * frac, color)

    def _progress_bar(self, left: float, top: float, w: int, h: int, frac: float, *, work: bool) -> None:
        """A gold bar in five segments along a building's bottom edge; *work* adds the pulsing mark of a building making something."""
        px = 1 / self.scene.camera.zoom
        x0, width, y0 = left + 4, w * TILE - 8, top + h * TILE - 4 - 5 * px
        self._bar(x0, y0, width, width * max(0.0, min(1.0, frac)), (255, 214, 110, 255))
        for tick in range(1, 5):  # the same rows as the fill: the same order, pushed after it
            self.scene.draw_rect(x0 + width * tick / 5 - px / 2, y0, px, 5 * px, BAR_OUTLINE, space="world", layer=RenderLayer.UI_WORLD)
        if work:
            pulse = 0.55 + 0.45 * math.sin(self.time * 5)
            self.scene.draw_circle(x0 - 6 * px, y0 + 2.5 * px, 3.5 * px, (255, 214, 110, int(120 + 135 * pulse)), space="world", layer=RenderLayer.UI_WORLD)

    def _seen(self, building: Building) -> bool:
        return self.reveal or building.player == self.player or self.world.any_visible(self.player, building.rect)

    def shows(self, unit: Unit) -> bool:
        """Whether *unit* is on the map as the player sees it: out of a mine and a site, and theirs or in their sight."""
        return not unit.hidden and (self.reveal or unit.player == self.player or self.world.is_visible(self.player, unit.tile))

    def _draw_bars(self, overlay: Overlay) -> None:
        """Health over every wounded, selected or hovered unit and building (over everything while Alt is held);
        progress along the bottom of every site under construction and of own buildings at work."""
        world = self.world
        shown = set(overlay.selected) | ({overlay.hovered} if overlay.hovered is not None else set())
        px = 1 / self.scene.camera.zoom
        for uid, sprite in self._units.items():
            unit = world.units.get(uid)
            if unit is None or not sprite.visible:
                continue
            if overlay.bars_for_all or uid in shown or unit.hp < unit.max_hp:
                placement = textures.placements[self._unit_keys[uid]]
                # Over the figure's top, not the sprite's cell: three screen pixels of air, then the outline's bottom edge and the 5 px fill.
                self._health_bar(unit, sprite.x, sprite.y - placement.drop - placement.head - 9 * px, TILE * 0.8)
        for bid, building in world.buildings.items():
            if bid not in self._buildings or not self._seen(building):
                continue
            x, y, w, h = building.rect
            left, top = x * TILE, y * TILE
            if not building.done:
                if not building.abandoned:  # a ruin's site goes nowhere
                    self._progress_bar(left, top, w, h, building.progress / building.info.build_time, work=False)
                if bid in shown:
                    self._health_bar(building, left + w * TILE / 2, top - 8, w * TILE * 0.8)
                continue
            if overlay.bars_for_all or bid in shown or building.hp < building.max_hp:
                self._health_bar(building, left + w * TILE / 2, top - 8, w * TILE * 0.8)
            if building.player == self.player and building.queue:
                self._progress_bar(left, top, w, h, building.train_progress / RACES[building.race].units[building.queue[0]].build_time, work=True)
            elif building.player == self.player and building.research is not None:
                self._progress_bar(left, top, w, h, building.research_progress / UPGRADES[building.research].time, work=True)

    def draw(self, overlay: Overlay) -> None:
        world, scene = self.world, self.scene
        self._draw_wood_chips()
        self._draw_projectiles()
        self._draw_melee_trails()
        for eid in overlay.selected + ([overlay.hovered] if overlay.hovered is not None and overlay.hovered not in overlay.selected else []):
            entity = world.units.get(eid) or self._sightings.get(eid)  # a building where the player knows it to stand
            if entity is None:
                continue
            color = self._entity_color(entity)
            if isinstance(entity, Unit):
                if entity.hidden:
                    continue
                wx, wy = to_world(self.unit_position(entity))
                # The ring is the body: what the click picks and what the crowd keeps clear (rules.UnitInfo.radius).
                self._ring(wx, wy + 2, TILE * entity.radius, TILE * entity.radius * RING_FLATTEN,
                           color if eid in overlay.selected else rgba(color[:3], 120))
            else:
                x, y, w, h = entity.rect
                left, top = x * TILE, y * TILE
                scene.draw_rect(left, top, w * TILE, h * TILE, (0, 0, 0, 0), border_color=color if eid in overlay.selected else rgba(color[:3], 120),
                                border_width=2, space="world", layer=RenderLayer.OBJECTS)
        self._draw_bars(overlay)
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
