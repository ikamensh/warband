"""Warband's neutral creatures: the beasts that belong to nobody.

A wolf, a troll, a venom-spitting giant spider and a stone golem, drawn with the
same low-poly renderer, the same camera and the same nine frames per facing as
the units in :mod:`warband.art.textures`, so they stand beside a footman without
looking imported from another game.  They reuse that module's helpers
(:func:`~warband.art.textures._unit_rod`, the shadow, the colours) and its
:data:`~warband.art.textures.POSES` table; what they do not reuse is the team
colour.  **A neutral creature is nobody's**: no mesh here takes a player,
:func:`monster_image` takes none either, and ``test_monsters.py`` holds every
face to a palette that carries none of the four team hues.

The meshes are the stand-ins.  What the game draws is the painted sheet each
creature has under ``warband/assets/restyled`` (``tools/restyle.py --monsters``,
:func:`restyled_monster`), which is a gold mine's kind of sheet rather than a
unit's: nothing recolours it, because there is no player to recolour it for.  A
sheet that no longer holds every frame warns and is ignored, and
``WARBAND_ART=procedural`` keeps the renders.

Each of them is a shape no unit in the game already owns, which is a harder bar
than it sounds: ``warband/sim/races.py`` makes the orc knight an **Ogre** and the
dwarf knight a **Bear Rider** on a war bear, and a neutral creature has no team
colour to tell it from a mounted enemy at 32 px.  The wolf was exactly that
collision while the orcs had a wolf rider (the scout, gone since WB-064), and was
painted russet against the rider's grey: the coat stays.

Each creature declares a :class:`Creature` rig, which says how the shared pose
is carried:

* a *planted* rig (the spider, the wolf) keeps everything below :data:`PLANTED`
  on the ground and bobs the body over it, as a mount does.  It only bobs and
  lunges, so a planted creature's blow has to be its own body: the wolf's front
  half pitches about its hips with an opening jaw, the spider rears about its
  back legs.
* a *hipped* rig (the troll, the golem) leans, twists and sways everything above
  its hip.  Their hips are at 0.94 and 0.50 against the humanoid ``HIP`` of
  0.28, and the golem damps the whole pose through :attr:`Creature.carry`: the
  table is authored for a man, and a man's lean threw a golem off its feet.

The rules are somebody else's business.  This module offers the images:
:func:`monster_image` for one frame, :func:`warm_monsters` for all of them and
:func:`monster_portrait_image` for the selection panel.  A caller that has
added a ``UnitType`` per creature reaches the art with ``Monster(unit.type.value)``,
and :data:`DEATH_OUTCOME` says how each one goes down.  Every image takes the match's
landscape (:class:`~warband.sim.rules.MapTheme`) and wears its coat off summer —
:data:`COATS` for the creatures, :data:`LAIR_COATS` for the dens — so the wilds look
at home on snow and on waste while reading as themselves everywhere.

Each creature also names a den: :class:`LairKind` holds the four, one per creature, and
:func:`lair_kind_for_roster` reads whose den a camp is from the roster it was raised with.
:func:`lair_image` draws one in its intact or damaged look, :func:`lair_portrait_image`
its selection-panel picture, and :data:`LAIR_ANCHORS` tells :mod:`warband.art.ambience`
where each den breathes from.  The dens share a footprint, a dark mouth and a bone-white
mark, so every camp reads as a camp; silhouette and palette tell them apart.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterator

import numpy as np
from PIL import Image

from saga2d import Game
from sagaforge import render3d as r3
from sagaforge import restyle
from sagaforge.render3d import Mesh

from warband.art.textures import (
    BONE, DROP_UNIT, FACINGS, FRAMES, FUR_WOLF, INK, PAD, POSES, PROJECTION, TILE, TUSK, UNIT_SCALE,
    WALK_FRAMES, Color, Placement, _BOB, _LEG_LIFT, _LEG_SWING, _painted, _prop, _shadow, _shift,
    _unit_panel, _unit_pitch, _unit_rod, darker, figure_top, placements,
)
from warband.sim.rules import IdentityEnum, MapTheme, UnitType


class Monster(IdentityEnum):
    """A neutral creature.  The values are the names a rule table would use."""

    WOLF = "wolf"
    TROLL = "troll"
    SPIDER = "spider"
    GOLEM = "golem"


#: A cold, mossy blue-green hide with a pale belly and near-black limbs.  Nothing here may be
#: mistaken for a team (Azure, Crimson, Viridian, Amber) — nor for the orcs' warm yellow-green
#: (98, 142, 76), because the orc knight is already an ogre.
TROLL_HIDE = (76, 111, 109)
TROLL_BELLY = (157, 179, 163)
TROLL_LIMBS = (42, 65, 66)
#: Granite, its crevices and the pale quartz seams that say stone rather than flesh.
GOLEM_STONE = (139, 142, 145)
GOLEM_DARK = (66, 71, 76)
GOLEM_SEAM = (226, 222, 207)
CHITIN = (48, 40, 52)
CHITIN_LIGHT = (86, 70, 92)
#: Violet, the one strong hue no player wears (Azure, Crimson, Viridian, Amber).
VENOM = (168, 92, 196)

PLANTED = 0.2  # a planted rig's feet: what lies at or below this height stays on the ground


# -- The beasts ------------------------------------------------------------------------

#: A four-legged stride, diagonal pairs opposed, as :func:`~warband.art.textures._mount` walks.
_BEAST_SWING = {
    "stand": 0.0, "walk1": 0.12, "walk2": 0.025, "walk3": -0.12, "walk4": -0.025,
    "wind": -0.035, "strike": 0.09, "follow": 0.065, "recover": 0.02,
}
_BEAST_LIFT = {"walk2": (0.0, 0.045), "walk4": (0.045, 0.0)}  # (near diagonal, far diagonal) paw lifted


_WOLF_PIVOT = (0.0, -0.245, 0.415)
_WOLF_SNAP = {  # (front pitch, forward travel, vertical travel)
    "wind": (-12, -0.10, -0.025),
    "strike": (-18, 0.14, 0.01),
    "follow": (-14, 0.10, 0.0),
    "recover": (-4, 0.025, 0.0),
}
_WOLF_JAW_HINGE = (0.0, 0.4975, 0.53)
_WOLF_JAW = {  # (upper skull pitch, lower jaw pitch): 65-degree strike gape
    "wind": (0, 0),
    "strike": (25, -40),
    "follow": (5, -10),
    "recover": (0, 0),
}
_WOLF_FORELEG = {  # (paw reach beyond standing contact, lift)
    "wind": (0.02, 0.0),
    "strike": (0.30, 0.04),
    "follow": (0.25, 0.0),
    "recover": (0.07, 0.0),
}


def _beast_joint(
    point: r3.Vec3,
    pivot: r3.Vec3,
    pitch: float,
    forward: float,
    rise: float,
) -> r3.Vec3:
    """Carry a shoulder with its pitched body; paw contacts stay independent."""
    x, y, z = point
    _, py, pz = pivot
    sine, cosine = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    return (
        x,
        py + (y - py) * cosine - (z - pz) * sine + forward,
        pz + (y - py) * sine + (z - pz) * cosine + rise,
    )


def _carry_low_faces(mesh: Mesh, frame: str, hip: float, carry: float = 1.0) -> Mesh:
    """Move a limb that hangs below the hip with the body it hangs from.

    :func:`_posed` leans and twists what is above the hip and leaves the legs planted, which is
    right for a leg and wrong for a troll's knuckles or a golem's fists: they belong to the
    shoulders but hang below the waist, and would be left behind.  A mesh function calls this on
    such a limb, which applies the frame's pose to the low faces here and leaves the high ones
    for :func:`_posed`, so the whole arm arrives in one piece.  The low faces stay below the
    cutoff afterwards, so they are moved once, not twice.
    """
    pose = POSES.get(frame)
    if pose is None:
        return mesh
    low = [face for face in mesh if max(p[2] for p in face.points) <= hip + 0.02]
    high = [face for face in mesh if max(p[2] for p in face.points) > hip + 0.02]
    return high + _shift(
        _unit_pitch(r3.rotate_z(low, pose.twist * carry), -pose.lean * carry, (0, 0, hip)),
        (pose.sway * carry, 0, 0),
    )


def _bulk(center: r3.Vec3, radii: r3.Vec3, color: Color, *, rings: int = 3, sides: int = 6) -> Mesh:
    """An ellipsoid: the body mass of a beast, which a sphere alone makes a ball."""
    cx, cy, cz = center
    rx, ry, rz = radii
    return [r3.Face(tuple((cx + x * rx, cy + y * ry, cz + z * rz) for x, y, z in face.points), face.color)
            for face in r3.sphere((0, 0, 0), 1.0, color, rings=rings, sides=sides)]


def _wedge(center: r3.Vec3, size: r3.Vec3, color: Color) -> Mesh:
    """A box that narrows and dips towards +y: a muzzle, a snout, a jaw."""
    cx, cy, cz = center
    sx, sy, sz = size
    return [r3.Face(tuple((cx + x * sx * (0.80 - 0.40 * y), cy + y * sy, cz + (z - 0.20 * y) * sz)
                          for x, y, z in face.points), face.color)
            for face in r3.box((0, 0, 0), (1, 1, 1), color)]


def _paws(x: float, y: float, step: float, up: float, radius: float, foot: r3.Vec3, hip_z: float, color: Color) -> Mesh:
    """One leg: a rod from the hip to the ankle and the broad foot under it."""
    return (_unit_rod((x, y, hip_z), (x, y + step, foot[2] + 0.045 + up), radius, color, sides=5)
            + r3.box((x, y + step + 0.025, foot[2] + up), (foot[0], foot[1], 0.12), color))


def _wolf(frame: str) -> Mesh:
    """Crouch, snap forward with an open mouth, bite down, then settle."""
    dark = darker(FUR_WOLF, 0.72)
    swing = _BEAST_SWING[frame]
    lifts = _BEAST_LIFT.get(frame, (0.0, 0.0))
    pitch, forward, rise = _WOLF_SNAP.get(frame, (0, 0.0, 0.0))
    mesh = _shadow(0.28)

    # Hindquarters and hind contacts remain outside the front's rotation.
    for x in (-0.125, 0.125):
        diagonal = 0 if x < 0 else 1
        step = swing if diagonal == 0 else -swing
        mesh += _paws(
            x, -0.245, step, lifts[diagonal], 0.045,
            (0.09, 0.13, 0.06), 0.415, dark,
        )
    mesh += _bulk(
        (0, -0.06, 0.425), (0.155, 0.30, 0.15),
        FUR_WOLF, rings=4, sides=8,
    )
    mesh += _unit_rod(
        (0, -0.28, 0.42), (0, -0.365, 0.26),
        0.05, FUR_WOLF, sides=5,
    )
    mesh += r3.cone((0, -0.365, 0.26), 0.055, -0.17, dark, sides=5)

    front = _bulk(
        (0, 0.19, 0.50), (0.175, 0.15, 0.185),
        dark, rings=4, sides=8,
    )
    front += _unit_rod(
        (0, 0.235, 0.51), (0, 0.36, 0.615),
        0.085, FUR_WOLF, sides=5,
    )
    head = _wedge((0, 0.415, 0.625), (0.22, 0.20, 0.18), FUR_WOLF)
    head += _wedge((0, 0.55, 0.585), (0.13, 0.14, 0.09), dark)
    head += r3.box((0, 0.617, 0.588), (0.075, 0.035, 0.05), INK)

    jaw = _wedge((0, 0.5575, 0.53), (0.115, 0.12, 0.035), FUR_WOLF)
    jaw += _wedge((0, 0.5575, 0.548), (0.10, 0.11, 0.008), INK)

    for side in (-1, 1):
        head += r3.cone(
            (side * 0.071, 0.355, 0.70),
            0.046, 0.13, FUR_WOLF, sides=4,
        )
        head += r3.box(
            (side * 0.071, 0.455, 0.701),
            (0.037, 0.045, 0.025), BONE,
        )
        head += r3.cone(
            (side * 0.036, 0.585, 0.55),
            0.014, -0.038, TUSK, sides=4,
        )

    # Lifting the skull slightly exposes the gape to the elevated camera.
    upper, lower = _WOLF_JAW.get(frame, (0, 0))
    front += _unit_pitch(head, upper, _WOLF_JAW_HINGE)
    front += _unit_pitch(jaw, lower, _WOLF_JAW_HINGE)
    mesh += _shift(
        _unit_pitch(front, pitch, _WOLF_PIVOT), (0, forward, rise),
    )

    # Carry the shoulders with the chest, then articulate to explicit contacts.
    # Rigidly pitching the standing legs would drive their paws underground.
    for x in (-0.125, 0.125):
        diagonal = 0 if x > 0 else 1
        step = swing if diagonal == 0 else -swing
        reach, up = _WOLF_FORELEG.get(frame, (step, lifts[diagonal]))
        shoulder = _beast_joint(
            (x, 0.19, 0.415), _WOLF_PIVOT, pitch, forward, rise,
        )
        mesh += _unit_rod(
            shoulder, (x, 0.19 + reach, 0.105 + up),
            0.045, dark, sides=5,
        )
        mesh += r3.box(
            (x, 0.215 + reach, 0.06 + up), (0.09, 0.13, 0.12), dark,
        )
    return mesh




# Dorsal roots, length and backward pitch: shoulder crest to small hip spurs.
_TROLL_SPINES = (
    ((0, -0.090, 1.93), 0.20, 42),
    ((0, -0.275, 1.72), 0.18, 58),
    ((0, -0.300, 1.47), 0.15, 70),
    ((0, -0.215, 1.24), 0.12, 78),
    ((0, -0.190, 1.04), 0.09, 84),
)


# -- The troll -------------------------------------------------------------------------

TROLL_HIP = 0.94  # its hips, where the shared Pose pivots: a troll is taller than a mounted knight


# Elbow, fist centre, fist pitch; x is mirrored for the two arms.
_TROLL_REACH = {
    "stand": ((0.43, 0.00, 0.94), (0.45, 0.14, 0.27), 0),
    "walk1": ((0.43, 0.00, 0.99), (0.45, 0.14, 0.27), 0),
    "walk2": ((0.43, 0.00, 0.96), (0.45, 0.14, 0.30), 0),
    "walk3": ((0.43, 0.00, 0.99), (0.45, 0.14, 0.27), 0),
    "walk4": ((0.43, 0.00, 0.96), (0.45, 0.14, 0.30), 0),
    "wind": ((0.47, -0.38, 2.08), (0.38, -0.43, 2.68), -155),
    "strike": ((0.46, 0.72, 1.08), (0.42, 1.00, 0.43), 55),
    "follow": ((0.45, 0.48, 0.87), (0.45, 0.35, 0.25), 20),
    "recover": ((0.44, 0.12, 1.13), (0.46, 0.26, 0.53), -20),
}

# Dorsal roots, length and backward pitch: shoulder crest to small hip spurs.
_TROLL_SPINES = (
    ((0, -0.090, 1.93), 0.20, 42),
    ((0, -0.275, 1.72), 0.18, 58),
    ((0, -0.300, 1.47), 0.15, 70),
    ((0, -0.215, 1.24), 0.12, 78),
    ((0, -0.190, 1.04), 0.09, 84),
)


def _troll(frame: str) -> Mesh:
    """A deep-chested brute with sloping shoulders and long, heavy limbs."""
    swing = _LEG_SWING.get(frame, 0.0) * 0.80
    lifts = _LEG_LIFT.get(frame, (0.0, 0.0))
    mesh = _shadow(0.39)

    for index, side in enumerate((-1, 1)):
        step = swing if index == 0 else -swing
        up = lifts[index] * 0.75
        knee = (side * 0.195, 0.10 + step * 0.45, 0.50 + up * 0.5)
        ankle = (side * 0.205, -0.075 + step, 0.12 + up)

        # Thick thigh caps stay below the shared pose's hip cutoff.
        mesh += _unit_rod(
            (side * 0.175, 0, TROLL_HIP - 0.04), knee,
            0.125, TROLL_LIMBS, sides=6,
        )
        mesh += _unit_rod(knee, ankle, 0.083, TROLL_LIMBS, sides=5)
        mesh += r3.box(
            (ankle[0], ankle[1] + 0.055, 0.065 + up),
            (0.18, 0.27, 0.13), TROLL_LIMBS,
        )

    body = r3.cylinder(
        (0, 0, TROLL_HIP - 0.06), 0.21, 0.49, TROLL_HIDE, sides=7,
    )
    body += _bulk(
        (0, -0.025, 1.59), (0.32, 0.29, 0.40),
        TROLL_HIDE, rings=4, sides=8,
    )
    body += _bulk(
        (0, 0.205, 1.32), (0.235, 0.17, 0.34),
        TROLL_BELLY, rings=4, sides=8,
    )
    for side in (-1, 1):
        body += _bulk(
            (side * 0.285, 0.005, 1.67), (0.19, 0.225, 0.235),
            TROLL_HIDE, rings=3, sides=6,
        )

    # The head still hangs ahead of the chest, below the shoulder ridge.
    body += _unit_rod(
        (0, 0.16, 1.44), (0, 0.43, 1.445),
        0.105, TROLL_LIMBS, sides=6,
    )
    body += _bulk(
        (0, 0.465, 1.465), (0.165, 0.145, 0.145),
        TROLL_HIDE, rings=4, sides=6,
    )
    body += _wedge(
        (0, 0.535, 1.335), (0.27, 0.235, 0.135), TROLL_BELLY,
    )
    body += r3.box((0, 0.622, 1.39), (0.16, 0.015, 0.023), INK)
    body += r3.box(
        (0, 0.570, 1.51), (0.24, 0.065, 0.045), TROLL_HIDE,
    )
    for side in (-1, 1):
        body += r3.box(
            (side * 0.061, 0.602, 1.476), (0.038, 0.019, 0.024), INK,
        )

    for root, length, pitch in _TROLL_SPINES:
        body += _unit_pitch(
            r3.pyramid(
                root, (0.11, 0.13), length, BONE,
                apex_shift=(0, -0.025),
            ),
            pitch, root,
        )

    elbow_at, fist_at, claw_pitch = _TROLL_REACH[frame]
    for side in (-1, 1):
        counter = side * swing if frame.startswith("walk") else 0.0
        elbow = (
            side * elbow_at[0],
            elbow_at[1] + counter * 0.45,
            elbow_at[2],
        )
        hand = (side * fist_at[0], fist_at[1] + counter, fist_at[2])

        arm = _unit_rod(
            (side * 0.31, 0.015, 1.67), elbow,
            0.125, TROLL_LIMBS, sides=6,
        )
        arm += _unit_rod(elbow, hand, 0.085, TROLL_LIMBS, sides=5)
        fist = _bulk(
            hand, (0.12, 0.145, 0.13), TROLL_HIDE, rings=3, sides=6,
        )
        for offset in (-0.07, 0.0, 0.07):
            fist += r3.cone(
                (hand[0] + offset, hand[1] + 0.085, hand[2] - 0.045),
                0.026, -0.155, BONE, sides=4,
            )
        arm += _unit_pitch(fist, claw_pitch, hand)
        body += _carry_low_faces(arm, frame, TROLL_HIP)

    return mesh + body


# -- The golem -------------------------------------------------------------------------

GOLEM_HIP = 0.50  # low and heavy: the mass above it is what leans
GOLEM_CARRY = 0.35  # and it barely leans at all; see Creature.carry
_GOLEM_FIST = (0.35, 0.34, 0.34)


# Rock across the planted feet, tiny stride, alternating foot lifts, arm swing.
_GOLEM_LUMBER = {
    "stand": (0.0, 0.0, (0.0, 0.0), 0.0),
    "walk1": (-0.065, 0.045, (0.0, 0.0), 0.11),
    "walk2": (-0.035, 0.014, (0.0, 0.035), 0.035),
    "walk3": (0.065, -0.045, (0.0, 0.0), -0.11),
    "walk4": (0.035, -0.014, (0.035, 0.0), -0.035),
}

# Extra torso bend, elbow, fist centre; the hipped Pose is applied afterwards.
_GOLEM_SLAM = {
    "wind": (-2, (0.46, 0.015, 1.91), (0.46, 0.015, 2.43)),
    "strike": (3, (0.48, 0.34, 0.79), (0.46, 0.72, 0.22)),
    "follow": (4, (0.48, 0.36, 0.77), (0.46, 0.73, 0.20)),
    "recover": (1, (0.52, 0.17, 1.05), (0.53, 0.28, 0.69)),
}


def _stone_link(
    start: r3.Vec3,
    end: r3.Vec3,
    width: float,
    color: Color,
) -> Mesh:
    """A square, unchamfered block between joints."""
    dx, dy, dz = (b - a for a, b in zip(start, end))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    block = r3.box((0, 0, length / 2), (width, width, length), color)
    block = _unit_pitch(
        block, -math.degrees(math.atan2(math.hypot(dx, dy), dz)), (0, 0, 0),
    )
    return _shift(
        r3.rotate_z(block, -math.degrees(math.atan2(dx, dy))), start,
    )


def _golem(frame: str) -> Mesh:
    """Misaligned granite shoulders, a visible waist and two planted columns."""
    if frame in _GOLEM_SLAM:
        rock, step, lifts, swing = _GOLEM_LUMBER["stand"]
        bend, elbow_at, hand_at = _GOLEM_SLAM[frame]
    else:
        rock, step, lifts, swing = _GOLEM_LUMBER[frame]
        bend, elbow_at, hand_at = (
            0, (0.52, 0.015, 0.95), (0.53, 0.09, 0.54),
        )

    mesh = _shadow(0.48)
    for index, side in enumerate((-1, 1)):
        stride = step if index == 0 else -step
        up = lifts[index]
        mesh += r3.box(
            (side * 0.26, stride + 0.07, 0.31 + up / 2),
            (0.22, 0.25, 0.38 - up), GOLEM_DARK,
        )
        mesh += r3.box(
            (side * 0.26, stride + 0.20, 0.10 + up),
            (0.27, 0.38, 0.20), GOLEM_STONE,
        )
        mesh += r3.box(
            (side * 0.26, stride + 0.095, 0.34 + up),
            (0.24, 0.27, 0.23), GOLEM_STONE,
        )

    body = r3.box(
        (0.015, -0.025, 0.585), (0.58, 0.31, 0.18), GOLEM_STONE,
    )
    body += r3.box(
        (0.02, -0.025, 0.76), (0.34, 0.29, 0.26), GOLEM_DARK,
    )
    chest = r3.box(
        (-0.015, -0.02, 1.055), (0.47, 0.35, 0.47), GOLEM_STONE,
    )
    # An off-centre, near-vertical vein avoids a mouth beneath the head.
    chest += _stone_link(
        (-0.15, 0.16, 0.91), (-0.06, 0.16, 1.29), 0.03, GOLEM_SEAM,
    )
    body += r3.rotate_z(chest, -5, about=(-0.015, -0.02))

    for side in (-1, 1):
        centre = (
            side * 0.29,
            -0.035 - side * 0.02,
            1.345 + side * 0.015,
        )
        slab = r3.box(
            centre, (0.39, 0.40, 0.27),
            GOLEM_STONE if side < 0 else darker(GOLEM_STONE, 0.86),
        )
        # One lengthwise shoulder vein avoids paired eye-like marks.
        if side < 0:
            slab += r3.box(
                (centre[0] - 0.055, centre[1], centre[2] + 0.138),
                (0.034, 0.31, 0.006), GOLEM_SEAM,
            )
        body += r3.rotate_z(slab, side * 7, about=centre[:2])

    # Raised skull with a single dark recess framed by stone.
    body += r3.box(
        (0, 0, 1.63), (0.27, 0.24, 0.30), GOLEM_STONE,
    )
    body += r3.box(
        (0, 0.124, 1.63), (0.18, 0.023, 0.17), GOLEM_DARK,
    )
    for side in (-1, 1):
        body += r3.box(
            (side * 0.115, 0.14, 1.63),
            (0.045, 0.075, 0.22), GOLEM_STONE,
        )
    body += r3.box(
        (0, 0.14, 1.754), (0.275, 0.075, 0.055), GOLEM_STONE,
    )
    body += r3.pyramid(
        (0, 0, 1.78), (0.27, 0.29), 0.055,
        GOLEM_STONE, apex_shift=(-0.045, -0.02),
    )

    pivot = (0, 0, GOLEM_HIP)
    body = _shift(_unit_pitch(body, -bend, pivot), (rock, 0, 0))

    for side in (-1, 1):
        shoulder = _beast_joint(
            (side * 0.40, -0.035, 1.345), pivot, -bend, 0, 0,
        )
        shoulder = (shoulder[0] + rock, shoulder[1], shoulder[2])
        elbow = (
            side * elbow_at[0] + rock,
            elbow_at[1] + side * swing * 0.5,
            elbow_at[2],
        )
        hand = (
            side * hand_at[0] + rock,
            hand_at[1] + side * swing,
            hand_at[2],
        )

        # Solve contact after the shared lean/twist, including the cube's
        # corners. Both fists touch z=0 despite the asymmetric shared twist.
        if frame in ("strike", "follow"):
            pose = POSES[frame]
            probe = _unit_pitch(
                r3.rotate_z(
                    r3.box(hand, _GOLEM_FIST, GOLEM_STONE),
                    pose.twist * GOLEM_CARRY,
                ),
                -pose.lean * GOLEM_CARRY, pivot,
            )
            lowest = min(p[2] for face in probe for p in face.points)
            hand = (
                hand[0],
                hand[1],
                hand[2] - lowest / math.cos(
                    math.radians(pose.lean * GOLEM_CARRY)
                ),
            )

        arm = _stone_link(shoulder, elbow, 0.225, GOLEM_STONE)
        arm += _stone_link(elbow, hand, 0.21, GOLEM_DARK)
        arm += r3.box(hand, _GOLEM_FIST, GOLEM_STONE)
        body += _carry_low_faces(arm, frame, GOLEM_HIP, GOLEM_CARRY)

    return mesh + body


# -- The spitter -----------------------------------------------------------------------

#: Legs in left/right pairs from the front, so 1-4-5-8 and 2-3-6-7 are the alternating tetrapods
#: a spider actually walks on: (leg root y, knee y, foot y, knee x).
_SPIDER_LEGS = ((0.23, 0.34, 0.45, 0.32), (0.14, 0.15, 0.18, 0.37), (0.02, -0.11, -0.13, 0.37), (-0.075, -0.31, -0.40, 0.32))
_SPIDER_STEP = {"stand": 0.0, "walk1": 0.05, "walk2": 0.012, "walk3": -0.05, "walk4": -0.012,
                "wind": 0.0, "strike": 0.0, "follow": 0.0, "recover": 0.0}
_SPIDER_LIFT = {"walk2": (0.0, 0.055), "walk4": (0.055, 0.0)}
#: The spit: crouch back, rear up on the back legs, snap down as the venom leaves, settle.
_SPIDER_REAR = {"wind": -10, "strike": 25, "follow": -6, "recover": 7}
_SPIDER_SINK = {"wind": -0.035, "follow": -0.02}
#: How the front pair of legs reaches and rises through the spit.
_SPIDER_FORELEG = {"wind": (-0.12, 0.0), "strike": (0.07, 0.23), "follow": (0.08, 0.035), "recover": (0.02, 0.06)}
_SPIDER_PIVOT = (0.0, -0.27, 0.36)  # it rears about its back legs
_SPIDER_KNEE_Z = 0.66  # knees above the back: what makes a spider read from directly above


def _spider(frame: str) -> Mesh:
    """A giant venom-spitter.  Eight legs kneed above the body carry the silhouette; the
    abdomen is the mass; a violet droplet leaves the fangs on the follow-through."""
    pitch, sink = _SPIDER_REAR.get(frame, 0), _SPIDER_SINK.get(frame, 0.0)
    sine, cosine = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))

    def carried(point: r3.Vec3) -> r3.Vec3:
        """Where the rearing body takes a leg's root."""
        x, y, z = point
        return (x, _SPIDER_PIVOT[1] + (y - _SPIDER_PIVOT[1]) * cosine - (z - _SPIDER_PIVOT[2]) * sine,
                _SPIDER_PIVOT[2] + (y - _SPIDER_PIVOT[1]) * sine + (z - _SPIDER_PIVOT[2]) * cosine + sink)

    body: Mesh = []
    for face in r3.sphere((0, -0.30, 0.42), 0.28, CHITIN, rings=4, sides=8):
        y = sum(p[1] for p in face.points) / len(face.points)
        body.append(r3.Face(face.points, CHITIN_LIGHT if abs(y + 0.30) < 0.065 else CHITIN))
    for corner in (-0.40, -0.20):  # a small violet hourglass on the crown, not a violet abdomen
        body += _unit_panel([(-0.075, corner, 0.66), (0.075, corner, 0.66), (0, -0.30, 0.708)], VENOM)
    if frame == "wind":
        body = _unit_pitch(body, 18, (0, -0.08, 0.42))  # the abdomen tips down as it draws back
    body += _bulk((0, 0.115, 0.36), (0.18, 0.245, 0.15), CHITIN)
    body += _unit_rod((0, -0.12, 0.39), (0, 0, 0.36), 0.095, CHITIN, sides=5)
    for side in (-1, 1):
        body += _unit_rod((side * 0.10, 0.26, 0.36), (side * 0.145, 0.40, 0.32), 0.026, CHITIN_LIGHT, sides=4)  # palps
        fang = (side * 0.06, 0.345, 0.335)
        body += _unit_pitch(r3.cone(fang, 0.027, -0.115, BONE, sides=4), 55, fang)
        body += r3.sphere((side * 0.06, 0.345, 0.35), 0.032, VENOM, rings=2, sides=5)
    mesh = _shadow(0.36) + _shift(_unit_pitch(body, pitch, _SPIDER_PIVOT), (0, 0, sink))
    step, lift = _SPIDER_STEP[frame], _SPIDER_LIFT.get(frame, (0.0, 0.0))
    for row, (root_y, knee_y, foot_y, knee_x) in enumerate(_SPIDER_LEGS):
        for index, side in enumerate((-1, 1)):
            group = 0 if row * 2 + index + 1 in (1, 4, 5, 8) else 1
            stride = step if group == 0 else -step
            reach, rise = _SPIDER_FORELEG.get(frame, (0.0, 0.0)) if row == 0 else (0.0, 0.0)
            knee = (side * knee_x, knee_y + stride * 0.45 + reach * 0.5, _SPIDER_KNEE_Z + rise * 0.45 + sink)
            foot = (side * 0.465, foot_y + stride + reach, 0.055 + lift[group] + rise)
            mesh += _unit_rod(carried((side * 0.115, root_y, 0.355)), knee, 0.03, CHITIN_LIGHT, sides=4)
            mesh += _unit_rod(knee, foot, 0.023, CHITIN, sides=4)
    if frame == "follow":
        mesh += r3.sphere((0, 0.60, 0.23), 0.045, VENOM, rings=3, sides=6)  # the venom, away
    return mesh


# -- The rig ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Creature:
    """One monster's mesh and how it carries a :class:`~warband.art.textures.Pose`.

    *hip* is the height the upper body pivots at, or ``None`` for a creature whose feet stay
    planted while its body bobs over them (the branch a mount takes).  *bob* scales that bob: a
    spider's body does not bounce as it walks.  *carry* scales the lean, twist and sway a hipped
    creature takes from the shared :class:`~warband.art.textures.Pose`, which is authored for a
    man: a golem is a stack of stone and barely bends, and leaning its wide shoulder slab a man's
    fourteen degrees over a low hip throws the whole mass off its feet."""

    mesh: Callable[[str], Mesh]
    hip: float | None
    bob: float = 1.0
    carry: float = 1.0


#: How a creature goes down, in the vocabulary of :data:`warband.art.effects.DEATHS`: a beast on
#: four or eight legs folds where it stands, the ogre topples like the humanoid it is.  A caller
#: that gives its monsters a ``UnitType`` reads this instead of :func:`effects.death_outcome`,
#: which knows only the game's own mounted units.
DEATH_OUTCOME: dict[Monster, str] = {
    Monster.WOLF: "collapse", Monster.SPIDER: "collapse", Monster.TROLL: "topple", Monster.GOLEM: "wreck",
}

CREATURES: dict[Monster, Creature] = {
    Monster.WOLF: Creature(_wolf, None),
    Monster.TROLL: Creature(_troll, TROLL_HIP),
    Monster.SPIDER: Creature(_spider, None, bob=0.0),
    Monster.GOLEM: Creature(_golem, GOLEM_HIP, carry=GOLEM_CARRY),
}


# -- Landscape coats -----------------------------------------------------------------
#
# The wilds look different on different ground: a wolf reads pale on snow and sandy on waste,
# while still reading as a wolf everywhere.  Summer is the painted sheet (or the stand-in) as it
# stands; winter and wasteland are procedural coats over it — per-channel gains plus a blend
# towards a landscape colour, masked by brightness so a cave mouth, a nose or dark chitin stays
# dark on every landscape while the coat takes the weather.  The same coat tints the stand-in
# render where there is no sheet, so both paths agree, and the silhouette never moves: only the
# palette does.  The rosters are the same on every landscape (mapgen draws the same camps from
# the same seed whatever the theme), so this is presentation only — no rules, no fingerprint.

#: A coat: per-channel gains, the landscape colour blended in, and how far (0 to 1).
Coat = tuple[tuple[float, float, float], "Color", float]

#: Winter white and waste sand, as the ground palettes in textures.PALETTES paint them.
SNOW = (232, 238, 246)
SAND = (214, 184, 136)

COATS: dict[tuple[Monster, MapTheme], Coat] = {
    (Monster.WOLF, MapTheme.WINTER): ((0.92, 0.97, 1.10), (236, 241, 249), 0.50),  # a snow wolf: pale grey-white
    (Monster.WOLF, MapTheme.WASTELAND): ((1.10, 1.01, 0.85), (218, 188, 140), 0.48),  # a dune wolf: sandy blonde
    (Monster.SPIDER, MapTheme.WINTER): ((0.92, 0.97, 1.09), (214, 226, 238), 0.38),  # frost-pale chitin
    (Monster.SPIDER, MapTheme.WASTELAND): ((1.09, 1.01, 0.86), (212, 190, 152), 0.38),  # sun-bleached chitin
    (Monster.TROLL, MapTheme.WINTER): ((0.90, 0.96, 1.08), (204, 222, 232), 0.38),  # an ice troll: pale, cold
    (Monster.TROLL, MapTheme.WASTELAND): ((1.10, 1.01, 0.84), (208, 180, 134), 0.40),  # a sand troll: dusty
    (Monster.GOLEM, MapTheme.WINTER): ((0.93, 0.98, 1.08), (234, 240, 248), 0.40),  # snow dust on the slabs
    (Monster.GOLEM, MapTheme.WASTELAND): ((1.10, 1.02, 0.86), (216, 188, 142), 0.40),  # sandstone slabs
}


def coerce_theme(theme: MapTheme | str) -> MapTheme:
    """*theme* as a :class:`~warband.sim.rules.MapTheme`, falling back to summer.

    A landscape the coats do not know (a string from an old save, a theme added later) wears
    the summer coat rather than failing: the fallback is the rule, and a test holds it.
    """
    try:
        return MapTheme(theme)
    except ValueError:
        return MapTheme.SUMMER


def _themed(image: Image.Image, coat: Coat) -> Image.Image:
    """*image* in *coat*: gains everywhere, the landscape colour blended into what is lit.

    The blend is masked by brightness — pixels near black keep their darkness — so the mouths,
    eyes and dark chitin that say *camp* and *creature* survive every landscape.  Alpha is
    untouched throughout.
    """
    gains, blend, amount = coat
    arr = np.asarray(image).astype(np.float32)
    rgb = arr[..., :3] * np.array(gains, dtype=np.float32)
    mask = np.clip((rgb.mean(axis=-1, keepdims=True) - 8.0) / 70.0, 0.0, 1.0)
    rgb += (np.array(blend, dtype=np.float32) - rgb) * (amount * mask)
    arr[..., :3] = np.clip(rgb, 0.0, 255.0)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def monster_asset_key(monster: Monster, facing: int, frame: str, theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """The asset key of one creature frame on one landscape: the sheet key on summer, suffixed
    with the landscape elsewhere, so every landscape's coat is its own registered image."""
    theme = coerce_theme(theme)
    return monster_key(monster, facing, frame) + ("" if theme is MapTheme.SUMMER else f".{theme.value}")


def _posed(mesh: Mesh, frame: str, creature: Creature) -> Mesh:
    """Apply the frame's shared :class:`~warband.art.textures.Pose` to one creature's rig."""
    pose = POSES.get(frame)
    if pose is None:
        return mesh
    if creature.hip is None:
        planted = [face for face in mesh if max(p[2] for p in face.points) <= PLANTED]
        body = [face for face in mesh if max(p[2] for p in face.points) > PLANTED]
        mesh = planted + _shift(body, (0.0, 0.0, _BOB.get(frame, 0.0) * creature.bob))
    else:
        hip, carry = creature.hip, creature.carry
        upper = [face for face in mesh if max(p[2] for p in face.points) > hip + 0.02]
        lower = [face for face in mesh if max(p[2] for p in face.points) <= hip + 0.02]
        upper = r3.rotate_z(upper, pose.twist * carry)
        mesh = lower + _shift(_unit_pitch(upper, -pose.lean * carry, (0.0, 0.0, hip)), (pose.sway * carry, 0.0, 0.0))
    return _shift(mesh, (0.0, pose.lunge, 0.0))


def monster_mesh(monster: Monster, frame: str) -> Mesh:
    """One creature's posed mesh at unit scale, facing +y (the camera): what the images render."""
    creature = CREATURES[monster]
    return r3.scale(_posed(creature.mesh(frame), frame, creature), UNIT_SCALE)


def monster_key(monster: Monster, facing: int, frame: str) -> str:
    return f"monster.{monster.value}.{facing}.{frame}"


def monster_sheet(monster: Monster) -> str:
    """The name of one creature's painted sheet under ``warband/assets/restyled``."""
    return f"monster.{monster.value}"


@lru_cache(maxsize=None)
def restyled_monster(monster: Monster) -> tuple[restyle.Sheet, dict[str, Image.Image]] | None:
    """The hand-painted frames of one creature (every facing and frame), or None when it has no
    sheet, or a stale one.  ``tools/restyle.py --monsters`` paints them; a sheet whose frames no
    longer match :data:`~warband.art.textures.FRAMES` warns and is ignored, exactly as a unit's
    does, and ``WARBAND_ART=procedural`` keeps the renders.

    Unlike a unit's sheet there is no player in it and no recolouring after it: a creature is
    nobody's, so the painted cell is what the game draws."""
    return _painted(monster_sheet(monster),
                    [monster_key(monster, facing, frame) for facing in range(FACINGS) for frame in FRAMES])


@lru_cache(maxsize=None)
def monster_heads(monster: Monster) -> tuple[float, ...]:
    """Per facing, how far above its feet a painted creature reaches standing or walking: what a
    health bar hangs over, since a painted cell is far taller than the creature in it."""
    painted = restyled_monster(monster)
    if painted is None:
        raise ValueError(f"no painted sheet for {monster.value}")
    sheet, frames = painted
    return tuple(max(figure_top(sheet, frames[monster_key(monster, facing, name)]) for name in ("stand",) + WALK_FRAMES)
                 for facing in range(FACINGS))


def monster_image(game: Game, monster: Monster, facing: int, frame: str, theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """Register (once) and return the key of one creature image on one landscape: the painted
    frame where the creature has a sheet, the low-poly render otherwise, wearing the landscape's
    coat off summer.  Never recoloured: a neutral creature has no player, so unlike
    :func:`~warband.art.textures.unit_image` this takes none — and the coat keeps clear of the
    team hues for the same reason (``test_monsters.py`` holds the winter and waste frames to it)."""
    theme = coerce_theme(theme)
    key = monster_asset_key(monster, facing, frame, theme)
    if not game.assets.has_image(key):
        painted = restyled_monster(monster)
        if painted is None:
            mesh = r3.rotate_z(monster_mesh(monster, frame), facing * 45 - 90)
            image = _prop(key, mesh, DROP_UNIT, game.backend.scale_factor)
        else:
            sheet, frames = painted
            placements[key] = Placement(sheet.logical_size, sheet.drop, head=monster_heads(monster)[facing])
            image = frames[monster_key(monster, facing, frame)]
        coat = COATS.get((monster, theme))
        if coat is not None:
            image = _themed(image, coat)
        game.assets.image_from_pil(key, image)
    return key


def warm_monsters(game: Game, theme: MapTheme | str = MapTheme.SUMMER) -> Iterator[str]:
    """Every creature image on one landscape, one per step, for a scene to spread over its opening
    frames.  A scene warms its world's own landscape only: three landscapes' coats are three sets."""
    theme = coerce_theme(theme)
    for monster in Monster:
        for facing in range(FACINGS):
            for frame in FRAMES:
                yield monster_image(game, monster, facing, frame, theme)


def monster_portrait_image(game: Game, monster: Monster, theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """A tightly framed picture of a creature at rest, for the selection panel: the painted frame
    facing the viewer where there is one, the low-poly render otherwise — wearing the landscape's
    coat, so the card shows the animal standing on that landscape."""
    theme = coerce_theme(theme)
    key = f"portrait.monster.{monster.value}" + ("" if theme is MapTheme.SUMMER else f".{theme.value}")
    if not game.assets.has_image(key):
        painted = restyled_monster(monster)
        if painted is not None:
            frame = painted[1][monster_key(monster, 2, "stand")]
            figure = frame.crop(frame.split()[3].getbbox())
            coat = COATS.get((monster, theme))
            if coat is not None:
                figure = _themed(figure, coat)
            fit = 128 * game.backend.scale_factor / max(figure.size)
            game.assets.image_from_pil(key, figure.resize((max(1, round(figure.width * fit)), max(1, round(figure.height * fit))),
                                                          Image.LANCZOS))
            return key
        mesh = monster_mesh(monster, "stand")
        min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
        w, h = max_x - min_x + 2 * PAD, max_y - min_y + 2 * PAD
        px = 128 * game.backend.scale_factor / max(w, h)
        image = r3.render(mesh, PROJECTION, scale=px, canvas=(w, h), origin=(-min_x + PAD, -min_y + PAD))
        coat = COATS.get((monster, theme))
        if coat is not None:
            image = _themed(image, coat)
        game.assets.image_from_pil(key, image)
    return key


# -- The lairs -------------------------------------------------------------------------

#: The rock the dens are piled out of: the golem's granite, darkened, so every camp reads as one thing.
LAIR_ROCK = (98, 101, 106)
LAIR_DARK = (54, 57, 62)
LAIR_MOUTH = (22, 20, 26)  # the hole itself: darker than INK, because a cave mouth has no light in it
#: Trampled silk a spider nest stands on, and the drapes strung across it.
SILK_GROUND = (178, 164, 178)
SILK = (226, 218, 230)
#: Packed earth of the spider's dome.
NEST_EARTH = (104, 88, 66)
NEST_DARK = (78, 64, 50)
#: Cream of a spider's egg sacs: bone-white, like the skull on a wolf den, so the nest keeps the
#: camps' shared mark of something living here.
SAC = (232, 224, 200)


class LairKind(IdentityEnum):
    """Whose den a camp is: one lair per creature, named by the guard it was raised for.

    A camp's roster is mixed, so the toughest guard names the den (:data:`LAIR_PRECEDENCE`):
    a wolf pack gets an earth den, a spider-led camp a silk nest, and the big seam camp its
    troll mound, after the 220-hit-point anchor listed first in its roster.  The values are
    the names a rule table would use, so ``LairKind(UnitType.TROLL.value)`` is the troll's.
    """

    WOLF = "wolf"
    SPIDER = "spider"
    TROLL = "troll"
    GOLEM = "golem"


#: Toughest first: the guard whose hide the den is built to house.  Hit points, strongest to
#: weakest (troll 220, golem 170, spider 45, wolf 40), so the order is the threat order and never
#: a second table to keep beside the rules.
LAIR_PRECEDENCE: tuple[UnitType, ...] = (UnitType.TROLL, UnitType.GOLEM, UnitType.SPIDER, UnitType.WOLF)

#: What the selection panel calls each den: a name of its own, not one shared "Lair".
LAIR_NAMES: dict[LairKind, str] = {
    LairKind.WOLF: "Wolf Den",
    LairKind.SPIDER: "Spider Nest",
    LairKind.TROLL: "Troll Mound",
    LairKind.GOLEM: "Stone Cairn",
}

#: The looks a den wears: whole, or under half its hit points like every other building
#: (:func:`warband.ui.view.building_look`).  A den is raised complete, so there are no
#: founded/raised looks, and it trains nothing, so no active one either.
LAIR_LOOKS = ("intact", "damaged")


def lair_kind_for_roster(kinds: list[UnitType | str]) -> LairKind:
    """Whose den a camp holding *kinds* is: the toughest guard present names it.

    A den with no known guards reads as the common wolf den.  An unknown kind raises,
    because a roster holds only what :class:`~warband.sim.rules.UnitType` names.
    """
    known = [UnitType(kind) for kind in kinds]
    for unit_type in LAIR_PRECEDENCE:
        if unit_type in known:
            return LairKind(unit_type.value)
    return LairKind.WOLF


def lair_kind_for_camp(camp) -> LairKind:
    """Whose den *camp* is, from the roster it was raised with (:attr:`kinds` are unit names)."""
    return lair_kind_for_roster(list(camp.kinds))


def _wolf_den(damaged: bool) -> Mesh:
    """A creature den: a horseshoe of dark boulders opening towards the viewer, a black mouth under a
    lintel slab, and bone spines driven into the trodden earth in front of it.

    It is nobody's, like the gold mine it stands beside, so no team colour goes anywhere near it, and
    like the mine it has to say one thing at a glance on three tiles of ground: *something lives here,
    and it eats*.  The camera looks from +y, so the opening faces that way and the cairn stands behind
    it; a ring closed all the way round hid the mouth completely and read as a boulder.
    """
    rng = random.Random(51023)
    mesh = _shadow(1.30)
    # The cairn: the far half of a ring, biggest at the back, leaning inwards over the mouth.
    cairn = 11 if not damaged else 7
    for i in range(cairn):
        angle = math.pi * (1.06 + 0.88 * i / 10)  # pi..2pi is the far side: away from the camera
        x, y = math.cos(angle) * rng.uniform(0.80, 1.06), math.sin(angle) * rng.uniform(0.60, 0.84) - 0.10
        mesh += r3.sphere((x, y, rng.uniform(0.22, 0.52)), rng.uniform(0.34, 0.50), LAIR_ROCK, rings=3, sides=6)
    if not damaged:
        for i in range(5):
            angle = math.pi * (1.18 + 0.64 * i / 4)
            x, y = math.cos(angle) * rng.uniform(0.40, 0.60), math.sin(angle) * rng.uniform(0.28, 0.44) - 0.06
            mesh += r3.sphere((x, y, rng.uniform(0.70, 1.02)), rng.uniform(0.30, 0.44), LAIR_DARK, rings=3, sides=6)
    # The mouth: a black recess in the near face, under a lintel slab, between two jamb boulders.
    mesh += r3.box((0.0, 0.10, 0.34), (0.92, 1.02, 0.68), LAIR_MOUTH)
    # The brow over the hole is two leaning boulders, not a slab: a flat lintel read as a shelf.
    for x, radius, lift in ((-0.34, 0.46, 0.80), (0.36, 0.42, 0.86)):
        mesh += r3.sphere((x, 0.24, lift), radius, LAIR_ROCK, rings=3, sides=6)
    for x in (-0.82, 0.84):
        mesh += r3.sphere((x, 0.26, 0.32), 0.46, LAIR_ROCK, rings=3, sides=6)
        mesh += r3.sphere((x * 0.86, 0.12, 0.84), 0.32, LAIR_DARK, rings=3, sides=6)
    # A skull set on the brow.  Grey stone alone reads as the map's own rock outcrop at the game's zoom;
    # this is the one mark that says at a glance that the hole is somebody's front door.  Torn down,
    # it lies knocked into the dirt in front.
    skull = (0.0, 0.46, 1.16) if not damaged else (0.28, 0.95, 0.14)
    mesh += r3.sphere((skull[0], skull[1], skull[2]), 0.24, TUSK, rings=4, sides=7)
    mesh += r3.box((skull[0], skull[1] + 0.16, skull[2] - 0.13), (0.26, 0.22, 0.17), TUSK)  # the muzzle, thrust towards the viewer
    for x in (-0.10, 0.10):
        mesh += r3.sphere((skull[0] + x, skull[1] + 0.14, skull[2] + 0.04), 0.075, LAIR_MOUTH, rings=3, sides=5)
    # Bone spines planted either side of the mouth: thick and near upright, so they read at the game's zoom.
    spines = ((-1.10, -0.12, 1.12), (1.12, 0.10, 0.96), (-0.70, -0.05, 0.78), (0.76, 0.06, 0.70))
    for index, (x, lean, height) in enumerate(spines):
        if damaged and index >= 2:  # the smaller pair snapped: stubs in the dirt
            mesh += _unit_rod((x, 0.94, 0.0), (x + lean, 0.94 + lean * 0.3, 0.25), 0.085, BONE)
            continue
        top = (x + lean, 0.94 + lean * 0.3, height)
        mesh += _unit_rod((x, 0.94, 0.0), top, 0.085, BONE)
        mesh += r3.sphere(top, 0.135, TUSK, rings=3, sides=6)
    # What has been dragged in and gnawed, on the trodden earth in front: its own stream, so the
    # scatter lies the same whether the crown above it stands or has fallen.
    foreground = random.Random(51024)
    for _ in range(6):
        angle, radius = foreground.uniform(0, math.tau), foreground.uniform(0.55, 1.05)
        x, y = math.cos(angle) * radius, abs(math.sin(angle)) * radius * 0.55 + 0.95
        mesh += _unit_rod((x, y, 0.03), (x + foreground.uniform(-0.22, 0.22), y + foreground.uniform(-0.10, 0.10), 0.07),
                          0.055, BONE)
    if damaged:  # the crown's fall: rubble across the mouth's step
        for x, z, radius in ((-0.45, 0.14, 0.22), (0.10, 0.10, 0.28), (0.55, 0.16, 0.18)):
            mesh += r3.sphere((x, 0.72, z), radius, LAIR_DARK, rings=3, sides=6)
    return mesh


def _spider_nest(damaged: bool) -> Mesh:
    """A low silk nest: a packed-earth dome under draped silk, cream egg sacs to one side and a low
    dark slit for a mouth, with violet venom beading at its corners.

    Low and wide where the wolf den is tall and ringed, so the two never share a silhouette; the
    sacs are the bone-white mark every den carries, and the mouth faces the camera like every den's.
    """
    rng = random.Random(51071)
    mesh = _shadow(1.30)
    mesh += r3.flat([(1.35 * math.cos(a), 1.10 * math.sin(a) + 0.15) for a in (i * math.tau / 14 for i in range(14))],
                    0.02, SILK_GROUND)  # trampled silk the nest stands on
    # The dome: overlapping earth, flatter and wider than any cairn.
    for center, radius, color in (((0, -0.35, 0.30), 0.62, NEST_EARTH), ((-0.55, -0.15, 0.22), 0.52, NEST_DARK),
                                  ((0.55, -0.20, 0.24), 0.55, NEST_EARTH), ((0, -0.10, 0.55), 0.55, NEST_EARTH),
                                  ((-0.25, 0.05, 0.30), 0.42, NEST_DARK), ((0.30, 0.05, 0.32), 0.44, NEST_EARTH)):
        if damaged and center[2] > 0.5:
            continue  # the crown caved in
        mesh += r3.sphere(center, radius, color, rings=3, sides=7)
    # Silk drapes from the dome to stakes in the dirt: two-sided sheets the camera always sees.
    drapes = [([(-0.75, 0.05, 0.75), (-0.20, 0.10, 0.80), (-0.40, 1.35, 0.05), (-0.90, 1.30, 0.05)]),
              ([(0.75, 0.00, 0.70), (0.25, 0.10, 0.78), (0.45, 1.30, 0.05), (0.95, 1.25, 0.05)]),
              ([(-0.10, -0.55, 0.85), (0.35, -0.45, 0.80), (0.60, -1.05, 0.05), (0.10, -1.10, 0.05)])]
    for index, points in enumerate(drapes):
        if damaged and index == 2:
            continue  # torn away
        mesh += _unit_panel(points, SILK)
    for x in (-0.90, 0.95):  # the stakes the silk is strung from
        mesh += _unit_rod((x, 1.27, 0.0), (x, 1.27, 0.55), 0.04, darker(SILK_GROUND, 0.6), sides=5)
    # The sacs: a crowded clutch on the right, two apart on the left, cream against the dark earth.
    sacs = [(0.80, 0.30, 0.16, 0.19), (1.00, 0.45, 0.13, 0.15), (0.62, 0.48, 0.12, 0.14), (0.90, 0.62, 0.11, 0.13),
            (-0.85, 0.35, 0.13, 0.15), (-0.65, 0.55, 0.10, 0.12)]
    for x, y, z, radius in sacs if not damaged else sacs[:3]:
        mesh += r3.sphere((x, y, z), radius, SAC, rings=3, sides=6)
        mesh += r3.sphere((x - radius * 0.3, y - radius * 0.2, z + radius * 0.45), radius * 0.45, SILK, rings=2, sides=5)
    # The mouth: a low wide slit under the dome's lip, venom beading at its corners.
    mesh += r3.box((0.0, 0.30, 0.20), (0.95 if not damaged else 1.10, 0.55, 0.40), LAIR_MOUTH)
    for x in (-0.42, 0.42):
        mesh += r3.sphere((x, 0.52, 0.16), 0.055, VENOM, rings=2, sides=5)
    for _ in range(4):
        angle, radius = rng.uniform(0, math.tau), rng.uniform(0.60, 1.00)
        x, y = math.cos(angle) * radius, abs(math.sin(angle)) * radius * 0.5 + 1.00
        mesh += _unit_rod((x, y, 0.03), (x + rng.uniform(-0.18, 0.18), y + rng.uniform(-0.08, 0.08), 0.06), 0.045, BONE)
    if damaged:
        for x, z, radius in ((-0.30, 0.12, 0.20), (0.35, 0.10, 0.24)):
            mesh += r3.sphere((x, 0.90, z), radius, NEST_DARK, rings=3, sides=6)
    return mesh


def _troll_mound(damaged: bool) -> Mesh:
    """A mossy tor: tall boulders patched with the troll's own cold blue-green, a ribcage arch
    framing a tall dark mouth, and small pale mushrooms at its foot.

    The tallest den, single-peaked where the wolf den is a ring and the cairn is stepped; the ribs
    are its bone-white mark, grown to an arch because a troll's den would be built of what it ate.
    """
    rng = random.Random(51091)
    mesh = _shadow(1.30)
    # The tor: one peak, biggest stone at the back.
    stones = [((0, -0.30, 0.45), 0.75, LAIR_ROCK), ((-0.60, -0.10, 0.32), 0.55, LAIR_DARK),
              ((0.60, -0.15, 0.36), 0.60, LAIR_ROCK), ((0, -0.30, 1.10), 0.60, LAIR_ROCK),
              ((-0.20, -0.25, 1.65), 0.45, LAIR_DARK)]
    for center, radius, color in stones if not damaged else stones[:3]:
        mesh += r3.sphere(center, radius, color, rings=3, sides=7)
    # Moss in the troll's own hide colours, on the camera faces.
    for center, radius in (((-0.35, 0.28, 0.75), 0.28), ((0.40, 0.25, 0.90), 0.24), ((0.05, 0.30, 1.30), 0.30),
                           ((-0.15, 0.05, 1.70), 0.22), ((0.55, -0.05, 0.55), 0.18)):
        if damaged and center[2] > 1.2:
            continue
        mesh += r3.sphere(center, radius, TROLL_HIDE, rings=3, sides=6)
        mesh += r3.sphere((center[0] - 0.06, center[1] + 0.05, center[2] + radius * 0.5), radius * 0.55, TROLL_BELLY,
                          rings=2, sides=5)
    # The mouth: a tall dark arch at the foot of the tor.
    mesh += r3.box((0.0, 0.25, 0.50), (0.80 if not damaged else 0.95, 0.65, 1.00), LAIR_MOUTH)
    # The ribs: three arches a side over the mouth, ground to crown, of heavy bone.
    for side in (-1, 1):
        for depth, reach in ((0.45, 0.62), (0.58, 0.74), (0.71, 0.86)):
            joints = [(side * reach, depth + 0.25, 0.05), (side * (reach - 0.15), depth + 0.12, 0.55),
                      (side * (reach - 0.32), depth, 0.95), (side * (reach - 0.45), depth - 0.08, 1.25)]
            if damaged and depth > 0.6:
                joints = joints[:2]  # the outer ribs snapped off
            for start, end in zip(joints, joints[1:]):
                mesh += _unit_rod(start, end, 0.055, BONE, sides=5)
            if not damaged or depth <= 0.6:
                mesh += r3.sphere(joints[-1], 0.085, TUSK, rings=3, sides=5)
    # Mushrooms at the foot: pale stems, moss-dark caps.
    for x, y, height in ((-0.95, 0.55, 0.22), (1.00, 0.40, 0.18), (-0.70, 0.85, 0.15)):
        mesh += _unit_rod((x, y, 0.0), (x, y, height), 0.035, TUSK, sides=5)
        mesh += r3.cone((x, y, height), 0.09, 0.08, TROLL_LIMBS, sides=6)
    for _ in range(4):
        angle, radius = rng.uniform(0, math.tau), rng.uniform(0.60, 1.00)
        x, y = math.cos(angle) * radius, abs(math.sin(angle)) * radius * 0.5 + 1.00
        mesh += _unit_rod((x, y, 0.03), (x + rng.uniform(-0.18, 0.18), y + rng.uniform(-0.08, 0.08), 0.06), 0.05, BONE)
    if damaged:
        for x, z, radius in ((-0.40, 0.14, 0.24), (0.30, 0.12, 0.20), (0.65, 0.16, 0.16)):
            mesh += r3.sphere((x, 0.95, z), radius, LAIR_DARK, rings=3, sides=6)
    return mesh


def _golem_cairn(damaged: bool) -> Mesh:
    """A cairn of stacked granite slabs, each course set slightly out of true the way the golem's own
    shoulders sit, with pale quartz seams across the joints and a square dark mouth under a lintel.

    Stepped and square where the mound is peaked and the nest is low; the seams catch the light the
    way the golem's do, and a small skull rides the cap slab for the camps' shared mark.
    """
    rng = random.Random(51121)
    mesh = _shadow(1.30)
    slabs = [((0, -0.10, 0.30), (2.00, 1.50, 0.60), GOLEM_DARK, 0.0),
             ((0.05, -0.10, 0.85), (1.70, 1.30, 0.50), GOLEM_STONE, 5.0),
             ((-0.05, -0.15, 1.30), (1.30, 1.00, 0.45), darker(GOLEM_STONE, 0.88), -6.0),
             ((0, -0.10, 1.62), (0.80, 0.70, 0.30), GOLEM_STONE, 3.0)]
    for index, (center, size, color, turn) in enumerate(slabs):
        if damaged and index == 3:
            center, turn = (0.45, 0.05, 1.15), 18.0  # the cap knocked askew
        slab = r3.rotate_z(r3.box((0, 0, 0), size, color), turn, about=(0, 0))
        mesh += [r3.Face(tuple((p[0] + center[0], p[1] + center[1], p[2] + center[2]) for p in face.points), face.color)
                 for face in slab]
    # Quartz seams across the course joints, on the camera faces.
    seams = [((-0.30, 0.56, 0.62), (0.55, 0.03, 0.06)), ((0.35, 0.56, 1.10), (0.45, 0.03, 0.06)),
             ((-0.10, 0.36, 1.52), (0.40, 0.03, 0.05))]
    for center, size in seams if not damaged else seams[:1]:
        mesh += r3.box(center, size, GOLEM_SEAM)
    # The mouth: a square opening between the base slabs, under a lintel.
    mesh += r3.box((0.0, 0.45, 0.30), (0.70 if not damaged else 0.85, 0.45, 0.60), LAIR_MOUTH)
    mesh += r3.box((0.0, 0.45, 0.68), (0.95, 0.55, 0.18), GOLEM_DARK)
    # The skull on the cap: grey slabs alone read as a rock pile at the game's zoom.
    skull = (0.0, -0.05, 1.92) if not damaged else (0.55, 0.60, 0.14)
    mesh += r3.sphere(skull, 0.20, TUSK, rings=3, sides=6)
    mesh += r3.box((skull[0], skull[1] + 0.14, skull[2] - 0.10), (0.22, 0.18, 0.14), TUSK)
    for x in (-0.08, 0.08):
        mesh += r3.sphere((skull[0] + x, skull[1] + 0.12, skull[2] + 0.03), 0.06, LAIR_MOUTH, rings=3, sides=5)
    # Stone chips knocked off in front.
    for _ in range(5 if not damaged else 9):
        angle, radius = rng.uniform(0, math.tau), rng.uniform(0.60, 1.10)
        x, y = math.cos(angle) * radius, abs(math.sin(angle)) * radius * 0.5 + 1.00
        mesh += r3.box((x, y, 0.06), (rng.uniform(0.10, 0.22), rng.uniform(0.08, 0.16), 0.12), GOLEM_DARK)
    return mesh


_LAIRS = {
    LairKind.WOLF: _wolf_den,
    LairKind.SPIDER: _spider_nest,
    LairKind.TROLL: _troll_mound,
    LairKind.GOLEM: _golem_cairn,
}

#: Where each den lives and breathes, in mesh coordinates: the mouth its breath and dust rise
#: from, the tips its glints flash on, and the tint of the halo that hangs over it while it stands.
#: :mod:`warband.art.ambience` draws all three from here, so a den's life and its mesh agree.
LAIR_ANCHORS: dict[LairKind, dict[str, Any]] = {
    LairKind.WOLF: {"mouth": (0.0, 0.90, 0.35), "glints": [(-0.34, 0.24, 1.10), (0.36, 0.24, 1.15)],
                    "halo": (150, 140, 120)},
    LairKind.SPIDER: {"mouth": (0.0, 0.55, 0.25), "glints": [(-0.42, 0.52, 0.20), (0.42, 0.52, 0.20)],
                      "halo": (168, 92, 196)},
    LairKind.TROLL: {"mouth": (0.0, 0.50, 0.55), "glints": [(-0.35, 0.28, 1.05), (0.40, 0.25, 1.20)],
                     "halo": (110, 160, 130)},
    LairKind.GOLEM: {"mouth": (0.0, 0.62, 0.30), "glints": [(-0.30, 0.56, 0.65), (0.35, 0.56, 1.13)],
                     "halo": (226, 222, 207)},
}


def lair_mesh(kind: LairKind | str = LairKind.WOLF, look: str = "intact") -> Mesh:
    """One den's mesh: *kind* names whose it is, *look* whether it stands whole or torn down to half."""
    if look not in LAIR_LOOKS:
        raise ValueError(f"unknown lair look {look!r}")
    return _LAIRS[LairKind(kind)](damaged=look == "damaged")


def lair_key(kind: LairKind | str, look: str = "intact") -> str:
    """The asset key of one den's picture."""
    return f"building.lair.{LairKind(kind).value}.{look}"


@lru_cache(maxsize=None)
def restyled_lair(look: str = "intact") -> tuple[restyle.Sheet, dict[str, Image.Image]] | None:
    """The hand-painted dens in one look (one cell per kind), or None when there is no sheet, or a
    stale one.  ``tools/restyle.py --lairs`` paints them; like a gold mine's sheet there is no
    player in it and nothing recolours it.  ``WARBAND_ART=procedural`` keeps the renders."""
    return _painted(f"lair.{look}", [lair_key(kind, look) for kind in LairKind])


def lair_asset_key(kind: LairKind | str, look: str = "intact", theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """The asset key of one den's picture on one landscape: the sheet key on summer, suffixed
    with the landscape elsewhere, so every landscape's coat is its own registered image."""
    theme = coerce_theme(theme)
    return lair_key(kind, look) + ("" if theme is MapTheme.SUMMER else f".{theme.value}")


#: The dens wear the weather too: snow dust on the crowns in winter, sand drifted against the
#: stones on waste.  The same brightness-masked coats as the creatures, milder — a den's dark
#: mouth and bone-white mark are the shared camp affordance and must survive every landscape.
LAIR_COATS: dict[tuple[LairKind, MapTheme], Coat] = {
    (LairKind.WOLF, MapTheme.WINTER): ((0.92, 0.97, 1.09), (234, 240, 248), 0.38),
    (LairKind.WOLF, MapTheme.WASTELAND): ((1.09, 1.01, 0.86), (214, 186, 140), 0.38),
    (LairKind.SPIDER, MapTheme.WINTER): ((0.92, 0.97, 1.09), (216, 226, 238), 0.34),
    (LairKind.SPIDER, MapTheme.WASTELAND): ((1.09, 1.01, 0.87), (210, 188, 152), 0.34),
    (LairKind.TROLL, MapTheme.WINTER): ((0.90, 0.96, 1.08), (206, 222, 232), 0.34),
    (LairKind.TROLL, MapTheme.WASTELAND): ((1.10, 1.01, 0.85), (206, 178, 134), 0.34),
    (LairKind.GOLEM, MapTheme.WINTER): ((0.93, 0.98, 1.08), (234, 240, 248), 0.38),
    (LairKind.GOLEM, MapTheme.WASTELAND): ((1.10, 1.02, 0.86), (214, 186, 140), 0.38),
}


def lair_image(game: Game, kind: LairKind | str = LairKind.WOLF, look: str = "intact",
               theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """Register (once) and return the key of one den's picture on one landscape: the painted cell
    where the lairs have a sheet in *look* (a look without a sheet shows the intact painting),
    the low-poly render otherwise, wearing the landscape's coat off summer.

    Never recoloured and never per race: a den belongs to the wilds, exactly as the gold mine
    belongs to nobody (:func:`~warband.art.textures.mine_image`).
    """
    if look not in LAIR_LOOKS:
        raise ValueError(f"unknown lair look {look!r}")
    theme = coerce_theme(theme)
    kind = LairKind(kind)
    painted = restyled_lair(look) or (restyled_lair() if look != "intact" else None)
    if painted is None:
        key = lair_asset_key(kind, look, theme)
        if not game.assets.has_image(key):
            front = 1.5 * TILE
            image = _prop(key, lair_mesh(kind, look), front + PAD, game.backend.scale_factor, front=front)
            coat = LAIR_COATS.get((kind, theme))
            if coat is not None:
                image = _themed(image, coat)
            game.assets.image_from_pil(key, image)
        return key
    sheet, frames = painted
    show = look if restyled_lair(look) is not None else "intact"
    base = lair_key(kind, show)
    key = base + ("" if theme is MapTheme.SUMMER else f".{theme.value}")
    if not game.assets.has_image(key):
        placements[key] = Placement(sheet.logical_size, sheet.drop, 1.5 * TILE, head=figure_top(sheet, frames[base]))
        image = frames[base]
        coat = LAIR_COATS.get((kind, theme))
        if coat is not None:
            image = _themed(image, coat)
        game.assets.image_from_pil(key, image)
    return key


def warm_lairs(game: Game, theme: MapTheme | str = MapTheme.SUMMER) -> Iterator[str]:
    """Every den image on one landscape, one per step, for a scene to spread over its opening frames."""
    theme = coerce_theme(theme)
    for kind in LairKind:
        for look in LAIR_LOOKS:
            yield lair_image(game, kind, look, theme)


def lair_portrait_image(game: Game, kind: LairKind | str = LairKind.WOLF, theme: MapTheme | str = MapTheme.SUMMER) -> str:
    """A tightly framed picture of one den, for the selection panel: the painted cell where there
    is one, the low-poly render otherwise — wearing the landscape's coat, so the card shows the
    den standing on that landscape."""
    theme = coerce_theme(theme)
    kind = LairKind(kind)
    key = f"portrait.lair.{kind.value}" + ("" if theme is MapTheme.SUMMER else f".{theme.value}")
    if not game.assets.has_image(key):
        painted = restyled_lair()
        if painted is not None:
            frame = painted[1][lair_key(kind)]
            figure = frame.crop(frame.split()[3].getbbox())
            coat = LAIR_COATS.get((kind, theme))
            if coat is not None:
                figure = _themed(figure, coat)
            fit = 128 * game.backend.scale_factor / max(figure.size)
            game.assets.image_from_pil(key, figure.resize((max(1, round(figure.width * fit)), max(1, round(figure.height * fit))),
                                                          Image.LANCZOS))
            return key
        mesh = lair_mesh(kind)
        min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
        w, h = max_x - min_x + 2 * PAD, max_y - min_y + 2 * PAD
        px = 128 * game.backend.scale_factor / max(w, h)
        image = r3.render(mesh, PROJECTION, scale=px, canvas=(w, h), origin=(-min_x + PAD, -min_y + PAD))
        coat = LAIR_COATS.get((kind, theme))
        if coat is not None:
            image = _themed(image, coat)
        game.assets.image_from_pil(key, image)
    return key
