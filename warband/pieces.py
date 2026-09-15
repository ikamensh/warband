"""Committed generated sound pieces: reading them and picking a take.

The pieces under ``assets/<folder>/`` are generated recordings (Stable Audio 3 through
``sagaforge.foley``; each folder's manifest records prompts, seeds and hashes, and
``tools/pieces.py`` remakes them).  A module composes cues from them by placing and
scaling takes; nothing here synthesises.
"""

from __future__ import annotations

from pathlib import Path
import wave

import numpy as np

from sagaforge.synth import SAMPLE_RATE, level

ROOT = Path(__file__).resolve().parent / "assets"


def read(path: Path) -> np.ndarray:
    """A committed piece as mono floats in −1..1."""
    with wave.open(str(path), "rb") as src:
        channels, width, rate, frames = src.getparams()[:4]
        if rate != SAMPLE_RATE or width != 2:
            raise ValueError(f"{path.name}: expected 16-bit {SAMPLE_RATE} Hz, got {width * 8}-bit {rate} Hz")
        data = np.frombuffer(src.readframes(frames), dtype="<i2").astype(float) / 32767
    return data.reshape(-1, channels).mean(axis=1)


def paths(folder: str, prefix: str, kind: str) -> list[Path]:
    """The committed takes of *kind* for *prefix* (a race, a material) under *folder*, in take order."""
    found = sorted((ROOT / folder).glob(f"{prefix}_{kind}_*.wav"))
    if not found:
        raise FileNotFoundError(f"No {prefix} {kind} pieces under {ROOT / folder}")
    return found


def take(folder: str, prefix: str, kind: str, index: int, gain: float) -> np.ndarray:
    """Take *index* (wrapping round) of *kind*, levelled to *gain*."""
    options = paths(folder, prefix, kind)
    return level(read(options[index % len(options)]), gain)
