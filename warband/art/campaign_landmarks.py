"""Complete painted campaign structures, shared by map entities and freestanding scenery.

The three source atlases have nine equal cells. Their transparent figures are cut once,
then registered at the world's tile footprint and native pixel density. Each sprite
contains its own plinth, machinery and light: no ordinary building remains beneath it.
"""

from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageOps
from saga2d import Game
from sagaforge import restyle
from warband.art import textures
from warband.sim.rules import BuildingType

FORMS = ("pylon", "dam", "keystone", "vault", "root_vault", "refuge_tower", "sluice", "refuge", "rockfall")
SCENERY_FORMS = ("stone_ring",)
STATES = ("dormant", "active", "damaged", "ruined", "open")
SOURCE = Path(__file__).resolve().parents[1] / "assets" / "campaign" / "structures"
CYAN = (111, 231, 244)
AMBER = (255, 196, 98)
CRIMSON = (238, 83, 113)


def hue(kind: str, state: str) -> tuple[int, int, int]:
    """Navigation ink follows the story state, independently of a structure's remembered damage."""
    if state == "ruined":
        return (146, 145, 150)
    if kind in ("refuge", "memorial"):
        return AMBER
    if kind == "anchor" and state == "dormant":
        return CRIMSON
    return CYAN


@lru_cache(maxsize=3)
def _atlas(variant: str) -> Image.Image:
    with Image.open(SOURCE / f"{variant}.png") as source:
        return source.convert("RGBA")


@lru_cache(maxsize=9)
def _cells(form: str) -> dict[str, Image.Image]:
    """Preserve one common crop and scale across a subject's painted states."""
    col, row = FORMS.index(form) % 3, FORMS.index(form) // 3
    original = _atlas("intact")
    cell_size = (original.width // 3, original.height // 3)
    cells = {}
    for variant in ("intact", "changed", "damaged"):
        atlas = _atlas(variant)
        cell = atlas.crop((round(col * atlas.width / 3), round(row * atlas.height / 3),
                           round((col + 1) * atlas.width / 3), round((row + 1) * atlas.height / 3)))
        # Imagegen may return a different output resolution; the authored equal-cell grid is invariant.
        cell = cell.resize(cell_size, Image.Resampling.LANCZOS)
        # The generated opaque bodies use alpha 250–254. Mark those as solid before
        # removing edge spill, or their actual violet crystal colour would be desaturated too.
        cell.putalpha(cell.getchannel("A").point(lambda alpha: 255 if alpha >= 250 else alpha))
        # Use the established painted-sheet extraction, including neighbour-cell fragment removal.
        cell = restyle.clear_residue(restyle.declutter(restyle.clear_residue(restyle.despill(cell))))
        if cell.getbbox() is None:
            raise ValueError(f"empty campaign sprite {form}/{variant}")
        cells[variant] = cell
    boxes = [cell.getbbox() for cell in cells.values()]
    common = (min(box[0] for box in boxes), min(box[1] for box in boxes),
              max(box[2] for box in boxes), max(box[3] for box in boxes))
    return {variant: ImageOps.expand(cell.crop(common), border=3) for variant, cell in cells.items()}


def image(form: str, state: str = "active") -> Image.Image:
    """A complete transparent object. Dormant/open aliases are deliberate for each mechanism."""
    if form not in FORMS + SCENERY_FORMS or state not in STATES:
        raise ValueError(f"unknown campaign structure/state: {form!r}/{state!r}")
    if form == "stone_ring":
        return _stone_ring()
    variant = {"active": "intact", "damaged": "damaged", "dormant": "intact",
               "ruined": "changed", "open": "intact"}[state]
    if (form, state) in (("sluice", "open"), ("vault", "dormant")):
        variant = "changed"
    return _cells(form)[variant]


@lru_cache(maxsize=1)
def _stone_ring() -> Image.Image:
    """An open circle of low standing stones; the Ancient and ground belong to the live map, not this image."""
    with Image.open(SOURCE / "stone-ring.png") as source:
        ring = source.convert("RGBA")
    return restyle.clear_residue(restyle.declutter(restyle.clear_residue(restyle.despill(ring))))


def register_image(game: Game, form: str, state: str = "active", footprint: int = 2, player: int = 0) -> str:
    """Register a whole structure on its logical footprint, including selection/health-bar placement."""
    scale = game.backend.scale_factor
    key = f"campaign.structure.{form}.{state}.{footprint}.{player}.{scale:g}"
    if not game.assets.has_image(key):
        source = image(form, state)
        width = footprint * textures.TILE + 8
        height = width * source.height / source.width
        # The ring's stone feet circle around 58% down its painted canvas; its clear centre is the unit's ground point.
        drop = height * .42 if form == "stone_ring" else footprint * textures.TILE / 2 + 3
        # Cloth colours belong to these authored structures; ownership is also shown by the normal
        # selection ring, minimap and health bar. Crystal violet must never be team-recoloured.
        textures.placements[key] = textures.Placement((width, height), drop,
                                                     front=footprint * textures.TILE / 2, head=max(0, height - drop))
        game.assets.image_from_pil(key, source.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS))
    return key


def custom_structure(scene, building_id: int) -> str | None:
    """The complete body's form, if this entity wears campaign art rather than its rules-type art."""
    sprite = scene.view.building_sprite(building_id)
    if sprite is None or not sprite.image.startswith("campaign.structure."):
        return None
    return sprite.image.split(".")[2]


def draw_ambience(scene, building, x: float, y: float, phase: float, layer: dict) -> bool:
    """Light belongs inside the painted mechanism; an infirmary never inherits a mage-tower crown."""
    form = custom_structure(scene, building.id)
    if form is None:
        return False
    cores = {"pylon": (0.0, .45), "dam": (.3, .27), "keystone": (0.0, .43),
             "vault": (0.0, .55), "root_vault": (0.0, .57)}
    if form not in cores or (form == "vault" and building.type is BuildingType.FARM):
        return True
    if building.type is BuildingType.VAULT and building.player == scene.human:
        player = scene.world.players[scene.human]
        if player.aether >= scene.world.aether_cap(scene.human):
            return True
    sprite = scene.view.building_sprite(building.id)
    placement = textures.placements[sprite.image]
    width, height = placement.size
    across, down = cores[form]
    cx, cy = x + width * across, y + placement.drop - height * (1 - down)
    pulse = .5 + .5 * math.sin(phase * 2.2)
    radius = width * (.075 + .02 * pulse)
    scene.draw_circle(cx, cy, radius * 1.5, (*textures.AETHER, round(18 + 12 * pulse)), **layer)
    scene.draw_circle(cx, cy, radius * .55, (*textures.AETHER_LIGHT, round(25 + 20 * pulse)), **layer)
    return True
