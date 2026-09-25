"""What a body sounds like: the sound families units die and answer in.

A family is data.  It names the pieces it is made of (generated recordings committed under ``assets/deaths`` and
``assets/presence``, made by ``tools/pieces.py``), how its death places them, what a blow on it lands on, and the
sound it makes itself heard with while it lives.  A unit type names its family on its row (``sound`` in
``units.toml`` or ``neutrals.toml``, :attr:`~warband.sim.rules.UnitInfo.sound`); a soldier of a race names none and
dies in the voice of the race that fields it.  The four race families are families like the rest: a cry, then
the weapon, the body and the gear landing.

Nothing here reads a file, so ``tools/pieces.py`` takes the stage names from :data:`FAMILIES` while it makes
the pieces the cue modules (:mod:`warband.audio.deaths`, :mod:`warband.audio.presence`) load.
``docs/adding-a-unit.md`` says what a new unit type owes this table, and ``tests/warband/test_bodies.py`` holds
every unit type to it.
"""

from __future__ import annotations

from dataclasses import dataclass

from warband.sim.rules import UNITS, Race, UnitType


@dataclass(frozen=True)
class Stage:
    """One piece of a death: the committed ``<family>_<kind>_<take>.wav``, levelled to *gain*.

    It starts *gap* seconds after the stage before it starts, or after it ends when *after_end* (a negative gap:
    under its tail), never before it; the first stage starts the cue.  *rotate* shifts its take against the
    cue's, so two cues do not share every piece."""

    kind: str
    gain: float
    gap: float = 0.0
    after_end: bool = False
    rotate: int = 0


@dataclass(frozen=True)
class Family:
    """*death*: its stages in order; the cue has a take for every committed piece of the first.
    *material*: what a blow on it lands on (:data:`warband.audio.combat_sound.MATERIALS`); ``None`` is armour or
    flesh by the armour it wears.  *presence*: the kind of piece it answers with, when its player orders it or its
    camp rouses; ``None`` for the soldiers of a race, whose orders the race's own cues answer."""

    death: tuple[Stage, ...]
    material: str | None = None
    presence: str | None = None


#: A soldier's death: the cry, the weapon dropping as the voice cuts off, the body landing, the gear settling.
#: The gaps are the pilot sound board's, not yet tuned by ear.
FALL = (Stage("cry", 0.72), Stage("weapon", 0.62, gap=-0.15, after_end=True), Stage("body", 0.85, gap=0.18, rotate=1),
        Stage("settle", 0.5, gap=0.25))

#: Every family by name.  The gaps of the bodies are first guesses read off their spectrograms, nobody has listened.
FAMILIES: dict[str, Family] = {
    **{race.value: Family(FALL) for race in Race},
    # A siege engine breaks: its timbers splinter, a rope lets go, the frame comes down as the wreck lands.
    "catapult": Family((Stage("splinter", 0.8), Stage("snap", 0.55, gap=0.15), Stage("crash", 0.9, gap=0.2, rotate=1)),
                       material="wood", presence="creak"),
    # A flyer fails, whistles down and breaks on the ground.  The crash waits for the whistle to end, a second or so
    # after the drawn body lands (UnitDeath drops it in 0.44 s), as a soldier's fall waits for his cry: a crash with
    # the whistle still falling over it, tried first, was the wrong way round.
    "flying_machine": Family((Stage("sputter", 0.7), Stage("whistle", 0.5, gap=0.1), Stage("crash", 0.9, gap=-0.05, after_end=True, rotate=1)),
                             material="wood", presence="whirr"),
    "wolf": Family((Stage("yelp", 0.72), Stage("body", 0.8, gap=-0.1, after_end=True, rotate=1)), presence="snarl"),
    "spider": Family((Stage("screech", 0.72), Stage("crunch", 0.8, gap=-0.1, after_end=True, rotate=1)), presence="hiss"),
    "troll": Family((Stage("bellow", 0.75), Stage("fall", 0.9, gap=-0.15, after_end=True, rotate=1)), presence="roar"),
    # Stone does not cry out: it grinds and breaks, and the rubble settles under the last of it.
    "golem": Family((Stage("grind", 0.85), Stage("rubble", 0.6, gap=-0.6, after_end=True, rotate=1)),
                    material="stone", presence="rumble"),
}
RACE_FAMILIES = frozenset(race.value for race in Race)

if _unknown := {kind.value: info.sound for kind, info in UNITS.items() if info.sound and info.sound not in FAMILIES}:
    raise ValueError(f"Unknown sound families {_unknown}; the families are {', '.join(FAMILIES)} (warband/audio/bodies.py)")


def family(unit_type: UnitType, race: Race) -> str:
    """The family a unit of *unit_type* fielded by *race* dies and answers in: its row's, or else its race's."""
    return UNITS[unit_type].sound or race.value


def material(unit_type: UnitType) -> str | None:
    """What a blow on *unit_type* lands on when its body decides it, whoever fields it; ``None``: its armour decides."""
    sound = UNITS[unit_type].sound
    return FAMILIES[sound].material if sound else None
