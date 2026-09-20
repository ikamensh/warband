"""Warband's neutral creatures: the beasts that belong to nobody.

A troll, a venom-spitting giant spider and a stone golem — plus a wolf that is
parked — drawn with the same low-poly renderer, the same camera and the same
nine frames per facing as the units in :mod:`warband.art.textures`, so they
stand beside a footman without looking imported from another game.  They reuse
that module's helpers (:func:`~warband.art.textures._unit_rod`, the shadow, the
colours) and its :data:`~warband.art.textures.POSES` table; what they do not
reuse is the team colour.  **A neutral creature is nobody's**: no mesh here
takes a player, and ``test_monsters.py`` holds every face to a palette that
carries none of the four team hues.

Each of them is a shape no unit in the game already owns, which is a harder bar
than it sounds: ``warband/sim/races.py`` makes the orc knight an **Ogre**, the
orc scout a **Wolf Rider** and the dwarf knight a **Bear Rider** on a war bear,
and a neutral creature has no team colour to tell it from a mounted enemy at
32 px.  The wolf in this file is exactly that collision — it is the orc scout's
mount without its rider — so it is finished but parked, kept for the montages
rather than for a rule table.

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
and :data:`DEATH_OUTCOME` says how each one goes down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterator

from saga2d import Game
from sagaforge import render3d as r3
from sagaforge.render3d import Mesh

from warband.art.textures import (
    BONE, DROP_UNIT, FACINGS, FRAMES, FUR_WOLF, INK, PAD, POSES, PROJECTION, TUSK, UNIT_SCALE,
    Color, _BOB, _LEG_LIFT, _LEG_SWING, _prop, _shadow, _shift, _unit_panel, _unit_pitch,
    _unit_rod, darker,
)
from warband.sim.rules import IdentityEnum


class Monster(IdentityEnum):
    """A neutral creature.  The values are the names a rule table would use."""

    WOLF = "wolf"
    TROLL = "troll"
    SPIDER = "spider"
    GOLEM = "golem"


#: A cold, mossy blue-green hide with a pale belly and near-black limbs.  Nothing here may be
#: mistaken for a team (Azure, Crimson, Viridian, Amber) — nor for the orcs' warm yellow-green
#: (98, 142, 76), because the orc knight is already an ogre and the orc scout already rides a wolf.
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


def monster_image(game: Game, monster: Monster, facing: int, frame: str) -> str:
    """Register (once) and return the key of one creature image.  Never recoloured: a neutral
    creature has no player, so unlike :func:`~warband.art.textures.unit_image` this takes none."""
    key = monster_key(monster, facing, frame)
    if not game.assets.has_image(key):
        mesh = r3.rotate_z(monster_mesh(monster, frame), facing * 45 - 90)
        game.assets.image_from_pil(key, _prop(key, mesh, DROP_UNIT, game.backend.scale_factor))
    return key


def warm_monsters(game: Game) -> Iterator[str]:
    """Every creature image, one per step, for a scene to spread over its opening frames."""
    for monster in Monster:
        for facing in range(FACINGS):
            for frame in FRAMES:
                yield monster_image(game, monster, facing, frame)


def monster_portrait_image(game: Game, monster: Monster) -> str:
    """A tightly framed picture of a creature at rest, for the selection panel."""
    key = f"portrait.monster.{monster.value}"
    if not game.assets.has_image(key):
        mesh = monster_mesh(monster, "stand")
        min_x, min_y, max_x, max_y = r3.bounds(mesh, PROJECTION)
        w, h = max_x - min_x + 2 * PAD, max_y - min_y + 2 * PAD
        px = 128 * game.backend.scale_factor / max(w, h)
        game.assets.image_from_pil(key, r3.render(mesh, PROJECTION, scale=px, canvas=(w, h), origin=(-min_x + PAD, -min_y + PAD)))
    return key
