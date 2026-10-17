"""Complete bodies for the campaign's named characters, on the game's existing animation clock.

These are costumes and rigs, not new simulation types: a keeper still has the same
orders, reach and statistics as their ordinary role. Mounted captains share the
horse's four-beat gait; the walkers share planted feet and the nine pose names.
Their faces, clothing and articulated tools are authored here as one mesh, then
painted into the production sheets under ``assets/campaign/units``. A turn or
blow carries the entire character rather than an extra floating emblem. Missing
painted art fails clearly; ``WARBAND_ART=procedural`` explicitly uses the rigs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image
from saga2d import Game
from sagaforge import render3d as r3
from sagaforge import restyle
from sagaforge.render3d import Mesh

from warband.art import textures as t
from warband.sim.rules import Race, UnitType


@dataclass(frozen=True)
class Character:
    """The ordinary role whose animation clock a named body follows."""

    race: Race
    unit_type: UnitType


CHARACTERS = {
    "issa": Character(Race.HUMAN, UnitType.KNIGHT),
    "brakk": Character(Race.ORC, UnitType.CLERIC),
    "wrenna": Character(Race.ELF, UnitType.CLERIC),
    "dagna": Character(Race.DWARF, UnitType.CLERIC),
    "pell": Character(Race.HUMAN, UnitType.FOOTMAN),
    "aldric": Character(Race.HUMAN, UnitType.KNIGHT),
    "maren": Character(Race.HUMAN, UnitType.CLERIC),
}

BLUE = (53, 84, 122)
BLUE_LIGHT = (94, 133, 165)
BRASS = (202, 161, 91)
BRASS_DARK = (119, 88, 49)
LEATHER = (91, 64, 45)
CREAM = (222, 215, 189)
GREEN = (70, 103, 65)
COPPER = (137, 78, 48)
HAIR_DARK = (49, 42, 40)
PAINTED = Path(__file__).resolve().parents[1] / "assets" / "campaign" / "units"


def _head(skin: t.Color, hair: t.Color, *, race: Race = Race.HUMAN, braid: bool = False) -> Mesh:
    """Bare practical faces; a dwarf woman keeps braids rather than the roster cleric's beard."""
    mesh = r3.sphere((0, 0.015, 0.86), 0.16, skin, rings=4, sides=8)
    mesh += r3.box((0, 0.165, 0.86), (0.065, 0.065, 0.065), skin)
    for x in (-0.065, 0.065):
        mesh += r3.box((x, 0.153, 0.905), (0.044, 0.025, 0.025), t.INK)
    # A cap of hair with a clear face opening; all hair remains attached to the skull.
    mesh += r3.sphere((0, -0.025, 0.96), 0.15, hair, rings=3, sides=8)
    mesh += r3.box((0, -0.1, 0.88), (0.25, 0.11, 0.22), hair)
    if braid:
        for side in (-1, 1):
            start = (side * 0.13, -0.005, 0.86)
            end = (side * 0.2, 0.08, 0.57)
            mesh += t._unit_rod(start, end, 0.045, hair)
            mesh += r3.sphere(end, 0.05, BRASS, rings=3, sides=6)
    if race is Race.ELF:
        for side in (-1, 1):
            mesh += t._unit_rod((side * 0.12, 0.0, 0.89), (side * 0.27, -0.04, 0.97), 0.034, skin, sides=4)
    if race is Race.ORC:
        # The left tusk is broken short, as in Brakk's portrait.
        for x, height in ((-0.09, 0.045), (0.09, 0.12)):
            mesh += r3.cone((x, 0.15, 0.76), 0.032, height, t.BONE, sides=4)
    return mesh


def _cloak(color: t.Color, frame: str, *, shoulder: float = 0.7, length: float = 0.55) -> Mesh:
    flutter = {"walk1": -0.07, "walk2": -0.1, "walk3": 0.07, "walk4": 0.1,
               "wind": 0.08, "strike": -0.14, "follow": -0.09, "recover": -0.03}.get(frame, 0.0)
    return t._unit_panel([(-0.24, -0.13, shoulder), (0.24, -0.13, shoulder),
                          (0.31 + flutter, -0.29, shoulder - length),
                          (-0.29 + flutter, -0.29, shoulder - length)], color)


def _walker(frame: str, skin: t.Color, hair: t.Color, coat: t.Color, *, race: Race = Race.HUMAN,
            robe: bool = False, braid: bool = False) -> Mesh:
    mesh = t._shadow(0.3) + t._legs(frame, LEATHER, spread=0.105)
    if robe:
        mesh += r3.cone((0, -0.01, 0.15), 0.285, 0.55, coat, sides=8)
    else:
        # Split workcoat: the two tails leave the walking feet and their direction readable.
        for side in (-1, 1):
            mesh += r3.box((side * 0.12, 0.015, 0.32), (0.2, 0.34, 0.28), coat)
    mesh += r3.cylinder((0, 0, 0.34), 0.205, 0.35, coat, sides=8)
    mesh += r3.cylinder((0, 0, 0.38), 0.217, 0.055, LEATHER, sides=8)
    mesh += r3.box((0, 0.219, 0.39), (0.09, 0.025, 0.065), BRASS)
    mesh += _head(skin, hair, race=race, braid=braid)
    return mesh


def _arm(shoulder: float, hand: r3.Vec3, sleeve: t.Color, skin: t.Color) -> Mesh:
    x = 0.2 if hand[0] > 0 else -0.2
    elbow = ((x + hand[0]) / 2, hand[1] * 0.35, shoulder - 0.12)
    return (t._unit_rod((x, 0, shoulder), elbow, 0.075, sleeve)
            + t._unit_rod(elbow, hand, 0.05, skin)
            + r3.sphere(hand, 0.055, skin, rings=3, sides=6))


def _staff(frame: str, kind: str) -> tuple[Mesh, r3.Vec3]:
    """The crook, living root and travel staff pivot with the keeper's hand during a cast."""
    grip = (-0.34, 0.16, 0.57)
    mesh = t._unit_rod((-0.34, 0.16, 0.06), (-0.34, 0.16, 1.2), 0.033, LEATHER)
    if kind == "brakk":
        # A herder's crook, lashed in bone: a practical hooked silhouette, not a cleric's skull banner.
        points = [(-0.34, 0.16, 1.2), (-0.43, 0.16, 1.34), (-0.58, 0.16, 1.32),
                  (-0.65, 0.16, 1.2), (-0.59, 0.16, 1.1)]
        for start, end in zip(points, points[1:]):
            mesh += t._unit_rod(start, end, 0.035, t.BONE)
        mesh += r3.box((-0.34, 0.16, 1.05), (0.08, 0.08, 0.14), BLUE)
    elif kind == "wrenna":
        for tip in ((-0.57, 0.14, 1.34), (-0.17, 0.16, 1.42), (-0.36, 0.32, 1.36)):
            mesh += t._unit_rod((-0.34, 0.16, 1.13), tip, 0.027, COPPER)
            mesh += r3.sphere(tip, 0.06, GREEN, rings=3, sides=5)
        mesh += r3.sphere((-0.34, 0.16, 1.27), 0.07, (178, 158, 210), rings=3, sides=6)
    else:
        mesh += r3.sphere((-0.34, 0.16, 1.28), 0.105, BRASS, rings=3, sides=8)
        mesh += r3.box((-0.34, 0.16, 1.28), (0.28, 0.045, 0.05), BRASS)
        mesh += r3.box((-0.34, 0.16, 1.28), (0.05, 0.045, 0.28), BRASS)
    pitch = {"walk1": 5, "walk3": -5, "wind": 18, "strike": -30, "follow": -20, "recover": -6}.get(frame, 0)
    return t._unit_pitch(mesh, pitch, grip), grip


def _keeper(name: str, frame: str, team: t.Color) -> Mesh:
    casting = frame in ("strike", "follow")
    if name == "brakk":
        skin = (128, 145, 91)
        mesh = _walker(frame, skin, (77, 76, 67), (105, 78, 49), race=Race.ORC, braid=True)
        mesh += _cloak(BLUE, frame, length=0.37)
        mesh += r3.box((0.22, -0.01, 0.43), (0.14, 0.17, 0.2), LEATHER)  # medicine pouch
        mesh += r3.box((0.235, 0.08, 0.45), (0.07, 0.012, 0.1), CREAM)  # folded receipt
    elif name == "wrenna":
        skin = (219, 192, 156)
        mesh = _walker(frame, skin, COPPER, GREEN, race=Race.ELF, robe=True, braid=True)
        mesh += _cloak((54, 81, 48), frame)
        mesh += t._unit_panel([(-0.13, 0.2, 0.69), (-0.035, 0.225, 0.7),
                               (0.2, 0.235, 0.24), (0.095, 0.25, 0.22)], BLUE_LIGHT)
        for x in (-0.14, 0.14):
            mesh += r3.sphere((x, -0.025, 1.04), 0.06, (122, 143, 77), rings=3, sides=5)
        mesh += r3.sphere((-0.02, 0.225, 0.61), 0.055, BRASS, rings=3, sides=6)
    else:  # Maren: a cream travelling habit, blue-grey hood, medicine roll.
        skin = (154, 110, 78)
        mesh = _walker(frame, skin, HAIR_DARK, CREAM, robe=True)
        mesh += _cloak((98, 119, 135), frame)
        mesh += r3.sphere((0, -0.07, 0.95), 0.19, (98, 119, 135), rings=3, sides=8)
        mesh += r3.box((0, 0.2, 0.59), (0.12, 0.035, 0.17), BLUE)
        mesh += r3.sphere((0, 0.23, 0.65), 0.045, BRASS, rings=3, sides=6)
        mesh += r3.box((0.24, -0.02, 0.39), (0.17, 0.2, 0.19), LEATHER)
    staff, grip = _staff(frame, name)
    mesh += staff + _arm(0.65, grip, BLUE if name == "brakk" else GREEN if name == "wrenna" else CREAM, skin)
    hand = (0.33, 0.34 if casting else 0.12, 0.72 if casting else 0.48)
    mesh += _arm(0.65, hand, GREEN if name == "wrenna" else BLUE, skin)
    mesh += r3.box((0.21, 0.02, 0.65), (0.08, 0.16, 0.1), team)
    return mesh


def _engineer(frame: str, team: t.Color) -> Mesh:
    skin, coat = (204, 160, 122), BLUE
    mesh = _walker(frame, skin, (156, 124, 98), coat, braid=True)
    mesh += _cloak((45, 65, 89), frame, length=0.48)
    for x in (-0.23, 0.23):
        mesh += r3.sphere((x, 0, 0.66), 0.105, BRASS, rings=3, sides=6)
    mesh += r3.box((0, 0.2, 0.55), (0.29, 0.05, 0.2), BRASS_DARK)
    mesh += r3.box((0.04, 0.234, 0.56), (0.04, 0.012, 0.15), BRASS)
    mesh += r3.box((0.04, 0.236, 0.58), (0.16, 0.012, 0.035), BRASS)
    mesh += r3.box((0.18, 0.13, 0.33), (0.17, 0.13, 0.19), LEATHER)
    grip = (-0.33, 0.15, 0.6)
    tool = t._unit_rod((-0.33, 0.15, 0.18), (-0.33, 0.15, 1.12), 0.04, BRASS_DARK)
    tool += r3.box((-0.33, 0.15, 1.1), (0.24, 0.1, 0.1), BRASS)
    for x in (-0.44, -0.22):
        tool += r3.box((x, 0.15, 1.19), (0.07, 0.1, 0.2), BRASS)  # open jaws of a lock wrench
    pitch = {"walk1": 6, "walk3": -6, "wind": 35, "strike": -40, "follow": -25, "recover": -10}.get(frame, 0)
    mesh += t._unit_pitch(tool, pitch, grip) + _arm(0.65, grip, coat, skin)
    hand = (0.33, 0.28 if frame in ("strike", "follow") else 0.1, 0.62)
    mesh += _arm(0.65, hand, coat, skin)
    # A carried gauge board is part of the hand's pose, never a detached effect.
    mesh += r3.box(hand, (0.16, 0.1, 0.2), BRASS_DARK)
    mesh += r3.sphere((hand[0], hand[1] + 0.07, hand[2] + 0.04), 0.055, CREAM, rings=3, sides=6)
    mesh += r3.box((0.24, 0, 0.68), (0.08, 0.1, 0.08), team)
    return mesh


def _blade(grip: r3.Vec3, frame: str) -> Mesh:
    x, y, z = grip
    mesh = t._unit_rod((x, y, z - 0.12), (x, y, z + 0.62), 0.024, BRASS)
    mesh += r3.box((x, y, z + 0.34), (0.072, 0.045, 0.45), t.IRON)
    mesh += r3.cone((x, y, z + 0.56), 0.055, 0.16, t.IRON, sides=4)
    mesh += r3.box((x, y, z + 0.08), (0.22, 0.055, 0.045), BRASS)
    pitch = {"wind": 55, "strike": -95, "follow": -70, "recover": -30,
             "walk1": -25, "walk3": -10}.get(frame, -18)
    return t._unit_pitch(mesh, pitch, grip)


def _captain(name: str, frame: str, team: t.Color) -> Mesh:
    mounted = name != "pell"
    skin = (224, 184, 145)
    if mounted:
        # Same proven gait as the knight, with the keeper's own saddlecloth and uncovered rider.
        mesh = t._mount(frame, True, BLUE if name == "issa" else (78, 96, 122), Race.HUMAN)
        z = 0.66
        for x in (-0.25, 0.25):
            mesh += t._unit_rod((x, -0.08, z + 0.12), (x, 0.08, z - 0.28), 0.07, t.IRON)
        rider = r3.cylinder((0, -0.06, 0.34), 0.2, 0.35, t.IRON, sides=8)
        rider += _head(skin, HAIR_DARK if name == "issa" else (85, 76, 65))
        rider += _cloak(BLUE, frame, shoulder=0.68, length=0.52)
        rider += r3.box((0, 0.14, 0.51), (0.28, 0.05, 0.3), BLUE)
        mesh += t._shift(rider, (0, -0.04, z - 0.02))
        # A brass key clasp and lock-shaped shield belong to Issa's Lockwatch kit.
        mesh += r3.sphere((0, 0.15, z + 0.59), 0.055, BRASS, rings=3, sides=6)
        mesh += r3.box((0, 0.15, z + 0.51), (0.035, 0.035, 0.12), BRASS)
    else:
        mesh = _walker(frame, skin, (151, 137, 108), BLUE)
        mesh += _cloak((63, 84, 106), frame, length=0.37)
        mesh += r3.box((0, 0.21, 0.57), (0.25, 0.05, 0.2), t.IRON)
        mesh += r3.box((-0.09, 0.25, 0.65), (0.11, 0.025, 0.1), CREAM)  # Pell's sealed warrant
        z = 0.0
    grip = (0.33, 0.15, z + 0.59)
    mesh += _arm(z + 0.64, grip, t.IRON, skin) + _blade(grip, frame)
    mesh += _arm(z + 0.64, (-0.3, 0.12, z + 0.48), t.IRON, skin)
    mesh += t._shield(-0.32, 0.16, z + 0.48, team, 0.86)
    if name == "issa":
        mesh += r3.sphere((-0.32, 0.205, z + 0.56), 0.07, BRASS, rings=3, sides=8)
    if name == "aldric":
        mesh += r3.box((0, 0.105, z + 0.73), (0.16, 0.045, 0.1), (85, 76, 65))
    return mesh


def _mesh(name: str, player: int, facing: int, frame: str) -> Mesh:
    character = CHARACTERS[name]
    team = t.team_color(player)
    if name in ("issa", "aldric", "pell"):
        mesh = _captain(name, frame, team)
    elif name == "dagna":
        mesh = _engineer(frame, team)
    else:
        mesh = _keeper(name, frame, team)
    mesh = t._posed(mesh, frame, character.unit_type)
    mesh = t._stretch(mesh, *t.LOOKS[character.race].stretch)
    return r3.rotate_z(r3.scale(mesh, t.UNIT_SCALE), facing * 45 - 90)


def unit_key(name: str, player: int, facing: int, frame: str) -> str:
    return f"campaign.unit.{name.lower()}.{player}.{facing}.{frame}"


@lru_cache(maxsize=None)
def painted_frames(name: str) -> tuple[restyle.Sheet, dict[str, Image.Image]]:
    """The complete painted animation; missing or stale production art is an authoring error."""
    sheet, frames = restyle.load_frames(PAINTED / name)
    wanted = {unit_key(name, 0, facing, frame) for facing in range(t.FACINGS) for frame in t.FRAMES}
    if set(frames) != wanted:
        raise ValueError(f"campaign character {name!r} must have exactly eight facings and all nine frames")
    return sheet, frames


@lru_cache(maxsize=None)
def _heads(name: str) -> tuple[float, ...]:
    sheet, frames = painted_frames(name)
    return tuple(max(t.figure_top(sheet, frames[unit_key(name, 0, facing, frame)])
                     for frame in ("stand",) + t.WALK_FRAMES) for facing in range(t.FACINGS))


def unit_image(game: Game, name: str, player: int, facing: int, frame: str) -> str:
    """Register one full character image at its ordinary feet anchor, and return its asset key."""
    name = name.lower()
    if frame not in t.FRAMES or not 0 <= facing < t.FACINGS:
        raise ValueError(f"invalid campaign character pose: {facing}, {frame!r}")
    key = unit_key(name, player, facing, frame)
    if not game.assets.has_image(key):
        if t.RESTYLED_ART:
            sheet, frames = painted_frames(name)
            image = t._recoloured(frames[unit_key(name, 0, facing, frame)], player)
            t.placements[key] = t.Placement(sheet.logical_size, sheet.drop, head=_heads(name)[facing])
        else:
            image = t._prop(key, _mesh(name, player, facing, frame), t.DROP_UNIT, game.backend.scale_factor)
        game.assets.image_from_pil(key, image)
    return key


def warm(game: Game, name: str, player: int) -> None:
    """Upload just an embodied character's animation before the first visible frame."""
    for facing in range(t.FACINGS):
        for frame in t.FRAMES:
            unit_image(game, name, player, facing, frame)
