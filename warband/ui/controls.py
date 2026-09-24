"""The control schemes: which key does what in a match (docs/controls.md).

The keyboard works in modes: the command card of what is selected, the Build, Train and Upgrade
catalogues, and a pending order that waits for its click.  Every scheme shares the modes, the mouse and
the modifiers — Shift keeps going (it queues an order, places another building, trains endlessly), Esc
goes back one level, Ctrl (Cmd) with B, T, U, G or P reaches the settlement from anywhere — and a scheme
decides which plain keys do what, and how long a mode lasts.  Ctrl+X is cancel mode in every scheme: a click takes
back a plan, a site or a building's work, a box everything of the player's inside it (WB-065).

* **Classic** — the letter of the name, as Warcraft II had it: A attack, F footman, B build.  B, T, U and G
  open the catalogues and set the assembly point whenever the card leaves the letter free.
* **Grid** — the card's position: Q W E / A S D / Z X C, whatever the card shows, so the left hand never
  moves; the catalogues and the assembly point sit beside the grid on B, T, G and R, the plans on F.
* **Modal** — the letters again, in modes that last, as vim has them: with nothing selected the Train
  catalogue is open, so a letter recruits; a building placed leaves the next one ready to place until Esc;
  ``.`` repeats the last recruit or placement.

A command on the card has a letter and a slot; :meth:`Scheme.card_key` picks which of the two is its key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

CARD_COLS: Final = 3
GRID_KEYS: Final = ("q", "w", "e", "a", "s", "d", "z", "x", "c")  # the card's nine slots, row by row
#: The row below the grid, which only a catalogue longer than nine reaches (the Build catalogue since the Aether Vault,
#: WB-063): the column of keys beside the grid, top to bottom.  Those are Grid's global keys otherwise, and while a card
#: holds them they are its; the assembly point and the plans stay on Ctrl+G and Ctrl+P.
GRID_BELOW: Final = ("r", "f", "v")
#: With Ctrl (Cmd on a Mac) in every scheme: the settlement from whatever the card shows, and cancel mode.  A chord
#: is resolved before any card, so no card's letter, now or later, can take one from a scheme.
CHORDS: Final = {"b": "build", "t": "train", "u": "upgrade", "g": "assembly", "p": "plans", "x": "cancel"}
ACTIONS: Final = {
    "build": "the Build catalogue", "train": "the Train catalogue", "upgrade": "the Upgrade catalogue",
    "assembly": "the assembly point for new soldiers", "plans": "every plan and its progress",
    "cancel": "cancel mode: a click takes back a plan, a site or a building's work",
    "idle_soldier": "the next idle soldier", "repeat": "the last recruit or placement again",
}


@dataclass(frozen=True)
class Scheme:
    """One way of laying the match out on the keyboard."""

    id: str  # what the settings file keeps
    name: str
    summary: str  # one line for the settings screen
    positional: bool  # a card command's key is its slot's (Grid), not its letter
    keys: dict[str, str] = field(default_factory=dict)  # a global action (ACTIONS) -> its plain key
    sticky: bool = False  # placing a building leaves the next one ready to place, until Esc
    home: str | None = None  # the catalogue open while nothing that has a card is selected

    def card_key(self, letter: str, slot: int) -> str:
        """The key of a card command with *letter* in *slot*: the slot's, in a positional scheme, and past the grid the
        key beside it (:data:`GRID_BELOW`)."""
        if self.positional:
            if slot < len(GRID_KEYS):
                return GRID_KEYS[slot]
            below = slot - len(GRID_KEYS)
            return GRID_BELOW[below] if below < len(GRID_BELOW) else ""
        return letter

    def action(self, key: str) -> str | None:
        """The global action a plain *key* gives, if the card has not taken it."""
        return next((action for action, bound in self.keys.items() if bound == key), None)

    def shortcut(self, action: str) -> str:
        """How a keycap names the key that reaches *action* whatever the card shows."""
        if self.positional and action in self.keys:
            return label(self.keys[action])  # beside the grid: never taken by a card
        chord = next((letter for letter, chosen in CHORDS.items() if chosen == action), None)
        if chord is not None:
            return f"Ctrl+{chord.upper()}"
        return label(self.keys[action]) if action in self.keys else ""


def label(key: str) -> str:
    """A key as its keycap reads: ``b`` -> B, ``period`` -> ., ``escape`` -> Esc."""
    names = {"escape": "Esc", "period": ".", "comma": ",", "tab": "Tab", "space": "Space", "return": "Enter"}
    return names.get(key, key.upper() if len(key) == 1 else key.title())


SCHEMES: Final[dict[str, Scheme]] = {
    "classic": Scheme("classic", "Classic", "Letters of the names: A attack, F footman, B build. B, T, U and G open the "
                      "catalogues when the card leaves them free; Ctrl+letter always does.", positional=False,
                      keys={"build": "b", "train": "t", "upgrade": "u", "assembly": "g", "idle_soldier": "period"}),
    "grid": Scheme("grid", "Grid", "Keys by the card's position, Q W E / A S D / Z X C, so the left hand stays put; "
                   "B build, T train, G upgrade, R assembly, F plans beside the grid.", positional=True,
                   keys={"build": "b", "train": "t", "upgrade": "g", "assembly": "r", "plans": "f", "idle_soldier": "v"}),
    "modal": Scheme("modal", "Modal", "Vim-like modes that last until Esc: with nothing selected letters recruit, placing "
                    "keeps the next building ready, and . repeats the last recruit or placement.", positional=False,
                    keys={"build": "b", "train": "t", "upgrade": "u", "assembly": "g", "idle_soldier": "comma", "repeat": "period"},
                    sticky=True, home="train"),
}
DEFAULT: Final = "classic"
