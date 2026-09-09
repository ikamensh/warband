"""Race voices: the cues a player hears for their own selections, orders, recruits, buildings and
alarms, in the timbre of the race they lead.  Humans keep the plain cues in :mod:`warband.sound`;
orcs answer with drums and growls, elves with bells, harp and flute, dwarves with anvil and horn.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from sagaforge.synth import BELL, BRASS, DARK, GLASS, SOFT, level, mix, noise, thump, tone
from warband.rules import Race

CUES = ("select", "command", "attack_command", "trained", "built", "under_attack")


def voiced(name: str, race: Race) -> str:
    """The effect to play for cue *name* when the listener leads *race*."""
    return f"{race.value}_{name}" if race is not Race.HUMAN and name in CUES else name


def anvil_strike(seed: int = 0) -> np.ndarray:
    """Hammer on iron: a hard tap, a bright splash and two inharmonic rings."""
    return mix(
        thump(520, 240, 0.12, tau=0.03),
        noise(0.09, 2000, 7000, tau=0.02, seed=700 + seed) * 0.55,
        tone(1830.0, 0.26, attack=0.001, tau=0.09, partials=((1, 1),)) * 0.35,
        tone(2740.0, 0.2, attack=0.001, tau=0.07, partials=((1, 1),)) * 0.2,
    )


# -- Orcs: drums and growls ------------------------------------------------------------------


def orc_select() -> np.ndarray:
    return level(mix(thump(160, 60, 0.12, tau=0.04), noise(0.08, 200, 1200, tau=0.03, seed=101) * 0.5), 0.5)


def orc_command() -> np.ndarray:
    """A grunt: a dark note under a throaty rasp, dropping a fourth."""
    return level(mix(tone("D3", 0.14, attack=0.01, tau=0.06, partials=DARK), noise(0.12, 150, 900, attack=0.01, tau=0.05, seed=102) * 0.7,
                     (0.1, tone("A2", 0.16, attack=0.01, tau=0.08, partials=DARK))), 0.55)


def orc_attack_command() -> np.ndarray:
    """A war drum struck twice under a growl."""
    drum = thump(120, 40, 0.3, tau=0.1)
    return level(mix(drum, noise(0.25, 100, 700, attack=0.02, tau=0.09, seed=103) * 0.8, (0.12, drum * 0.8)), 0.65)


def orc_trained() -> np.ndarray:
    drum = thump(140, 50, 0.2, tau=0.07)
    return level(mix(drum, (0.16, drum), (0.3, tone("D3", 0.35, attack=0.03, tau=0.2, partials=BRASS) * 0.5)), 0.6)


def orc_built() -> np.ndarray:
    """A low horn over the drum."""
    return level(mix(thump(110, 40, 0.3, tau=0.1), tone("A2", 0.6, attack=0.05, tau=0.35, partials=BRASS) * 0.6,
                     (0.25, tone("D3", 0.5, attack=0.04, tau=0.3, partials=BRASS) * 0.5)), 0.65)


def orc_under_attack() -> np.ndarray:
    drum = thump(100, 35, 0.5, tau=0.16)
    return level(mix(drum, tone("D2", 0.7, attack=0.05, tau=0.45, partials=BRASS) * 0.8, (0.3, drum * 0.8),
                     noise(0.5, 80, 500, attack=0.05, tau=0.2, seed=104) * 0.3), 0.7)


# -- Elves: bells, harp and flute --------------------------------------------------------------


def elf_select() -> np.ndarray:
    return level(mix(tone("D6", 0.1, tau=0.05, partials=BELL), (0.05, tone("A6", 0.12, tau=0.06, partials=BELL) * 0.7)), 0.45)


def elf_command() -> np.ndarray:
    """Two flute notes, rising."""
    return level(mix(tone("A5", 0.1, attack=0.02, tau=0.06, partials=SOFT), (0.09, tone("D6", 0.14, attack=0.02, tau=0.08, partials=SOFT))), 0.5)


def elf_attack_command() -> np.ndarray:
    """A harp run downward."""
    return level(mix(*[(i * 0.05, tone(note, 0.2, tau=0.08, partials=GLASS)) for i, note in enumerate(("D6", "B5", "A5", "F#5", "D5"))]), 0.55)


def elf_trained() -> np.ndarray:
    return level(mix(tone("D6", 0.3, tau=0.15, partials=BELL), (0.12, tone("A6", 0.35, tau=0.2, partials=BELL) * 0.7)), 0.5)


def elf_built() -> np.ndarray:
    """A rising harp arpeggio ending on a held high note."""
    layers = [(i * 0.08, tone(note, 0.3, tau=0.14, partials=GLASS)) for i, note in enumerate(("D5", "F#5", "A5", "D6"))]
    layers.append((0.34, tone("A6", 0.45, attack=0.01, tau=0.25, partials=GLASS) * 0.7))
    return level(mix(*layers), 0.6)


def elf_under_attack() -> np.ndarray:
    """A high horn with a shimmer over it."""
    return level(mix(tone("A4", 0.6, attack=0.04, tau=0.35, partials=BRASS) * 0.7, tone("D5", 0.6, attack=0.05, tau=0.3, partials=BRASS) * 0.5,
                     tone("A6", 0.5, attack=0.1, tau=0.3, partials=BELL) * 0.25), 0.65)


# -- Dwarves: anvil and horn ------------------------------------------------------------------


def dwarf_select() -> np.ndarray:
    return level(anvil_strike(1), 0.45)


def dwarf_command() -> np.ndarray:
    return level(mix(anvil_strike(2), (0.08, tone("A2", 0.18, attack=0.01, tau=0.09, partials=DARK) * 0.7)), 0.5)


def dwarf_attack_command() -> np.ndarray:
    """Hammer twice, with a deep drum under it."""
    return level(mix(anvil_strike(3), (0.13, anvil_strike(4) * 0.9), (0.02, thump(90, 40, 0.25, tau=0.09) * 0.7)), 0.6)


def dwarf_trained() -> np.ndarray:
    return level(mix(anvil_strike(5), (0.1, tone("E3", 0.3, attack=0.03, tau=0.18, partials=BRASS) * 0.6)), 0.55)


def dwarf_built() -> np.ndarray:
    """Two strikes and a low brass chord."""
    return level(mix(anvil_strike(6), (0.18, anvil_strike(7)), (0.3, tone("A2", 0.5, attack=0.04, tau=0.3, partials=BRASS) * 0.6),
                     (0.3, tone("E3", 0.5, attack=0.04, tau=0.28, partials=BRASS) * 0.45)), 0.65)


def dwarf_under_attack() -> np.ndarray:
    return level(mix(tone("A2", 0.7, attack=0.05, tau=0.45, partials=BRASS), tone("E2", 0.7, attack=0.06, tau=0.4, partials=BRASS) * 0.6,
                     (0.05, anvil_strike(8) * 0.8), (0.35, anvil_strike(9) * 0.6)), 0.7)


SOUNDS: dict[str, Callable[[], np.ndarray]] = {
    f"{race.value}_{cue}": globals()[f"{race.value}_{cue}"] for race in (Race.ORC, Race.ELF, Race.DWARF) for cue in CUES
}
