"""Unit deaths: a cry, then the weapon, the body and the gear landing, one cue per race and take.

The pieces are generated recordings committed under ``assets/deaths`` (Stable Audio 3 Medium; the
manifest there records every prompt, seed and hash, and ``docs/warband-deaths.md`` how they were made
and how to remake one).  The bank's generator only places and scales them, so a cue is deterministic
for a given set of pieces.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
import wave

import numpy as np

from sagaforge.synth import SAMPLE_RATE, level, mix
from warband.rules import Race

ASSETS = Path(__file__).resolve().parent / "assets" / "deaths"
STAGES = ("weapon", "body", "settle")
#: When the weapon hits the ground, in seconds from the end of the cry (negative: before the voice cuts off).
FALL_START = -0.15
WEAPON_TO_BODY = 0.18
BODY_TO_SETTLE = 0.25
GAINS = {"cry": 0.72, "weapon": 0.62, "body": 0.85, "settle": 0.5}
PEAK = 0.72


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        channels, width, rate, frames = src.getparams()[:4]
        if rate != SAMPLE_RATE or width != 2:
            raise ValueError(f"{path.name}: expected 16-bit {SAMPLE_RATE} Hz, got {width * 8}-bit {rate} Hz")
        data = np.frombuffer(src.readframes(frames), dtype="<i2").astype(float) / 32767
    return data.reshape(-1, channels).mean(axis=1)


def pieces(race: Race, kind: str) -> list[Path]:
    """The committed takes of *kind* (``cry`` or a stage) for *race*, in take order."""
    found = sorted(ASSETS.glob(f"{race.value}_{kind}_*.wav"))
    if not found:
        raise FileNotFoundError(f"No {kind} pieces for {race.value} under {ASSETS}")
    return found


def takes(race: Race) -> int:
    """How many death cues *race* has: one per committed cry."""
    return len(pieces(race, "cry"))


def _piece(race: Race, kind: str, take: int) -> np.ndarray:
    options = pieces(race, kind)
    return level(_read_wav(options[take % len(options)]), GAINS[kind])


def death(race: Race, take: int) -> np.ndarray:
    """Cry *take*, then the fall: the weapon drops as the voice cuts off, the body lands, the gear settles.

    The body take is rotated one step against the others so no two cues share a whole fall."""
    cry = _piece(race, "cry", take)
    weapon_at = max(0.0, len(cry) / SAMPLE_RATE + FALL_START)
    body_at = weapon_at + WEAPON_TO_BODY
    return level(mix(
        cry,
        (weapon_at, _piece(race, "weapon", take)),
        (body_at, _piece(race, "body", take + 1)),
        (body_at + BODY_TO_SETTLE, _piece(race, "settle", take)),
    ), PEAK)


def cue(race: Race) -> str:
    """The event name the scene plays when a unit of *race* dies; the bank picks the take."""
    return f"{race.value}_death"


#: Cue name → how many takes the bank can choose from.
CUES = {cue(race): takes(race) for race in Race}
SOUNDS = {f"{cue(race)}_{take}": partial(death, race, take) for race in Race for take in range(takes(race))}
