"""Keyboard layouts (docs/controls.md).

Modes is the default: B Build, T Train, U Upgrade, O whole-side Orders and V Spells
are reserved navigation keys. Pressing the active key returns to unit control;
Esc goes back one level. Options occupy stable absolute slots, paged nine at a
time on QWE / ASD / ZXC. Placement lasts until cancelled or switched.

Classic retains mnemonic card letters; Grid retains positional card keys. Both
use Ctrl chords for guaranteed global access. Every scheme shares the mouse,
control groups, Shift for queued orders/endless training, and direct global chords.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from warband.sim.rules import BuildingType, UnitType, Upgrade

CARD_COLS: Final = 3
GRID_KEYS: Final = ("q", "w", "e", "a", "s", "d", "z", "x", "c")  # the card's nine slots, row by row
#: The row below the grid, which only a catalogue longer than nine reaches (the Build catalogue since the Aether Vault,
#: WB-063): the column of keys beside the grid, top to bottom.  Those are Grid's global keys otherwise, and while a card
#: holds them they are its; the assembly point and the plans stay on Ctrl+G and Ctrl+P.
GRID_BELOW: Final = ("r", "f", "v")
# Mode keys are reserved before every card. Slots are page-relative; content gets
# an append-only absolute slot so adding an option never changes an existing key.
MODE_KEYS: Final = {"b": "build", "t": "train", "u": "upgrade", "o": "orders", "v": "spells"}
# Shared roles keep their positions across races; each race's own unit occupies its reserved role slot.
TRAIN_SLOTS = {UnitType.PEASANT: 0, UnitType.FOOTMAN: 1, UnitType.ARCHER: 2, UnitType.KNIGHT: 3,
               UnitType.CATAPULT: 4, UnitType.FLYING_MACHINE: 5, UnitType.CLERIC: 6,
               UnitType.GRYPHON: 7, UnitType.SAPPER: 7, UnitType.TREANT: 7, UnitType.RUNE_GOLEM: 7}
ORDER_SLOTS = {"scout": 0, "harass": 1, "withdraw": 2, "gold": 3, "lumber": 4, "fortify": 6}
ORDER_CHOICES = {"scout": ("One scout", "25% soldiers", "50% soldiers"),
                 "harass": ("Small party", "25% fighters", "50% fighters"),
                 "withdraw": ("Wounded", "Half outside", "All soldiers"),
                 "gold": ("25% lumber", "50% lumber", "All lumber"),
                 "lumber": ("25% gold", "50% gold", "All gold"),
                 "fortify": ("1 tower", "3 towers", "6 towers")}
ORDER_LABELS = {"scout": "Scout", "harass": "Raid", "withdraw": "Withdraw", "gold": "Gold", "lumber": "Lumber", "fortify": "Fortify"}
# An explicit slot ledger: new content is assigned a new slot, never inserted ahead of existing options.
BUILD_SLOTS = {BuildingType.FARM: 0, BuildingType.BARRACKS: 1, BuildingType.TOWN_HALL: 2, BuildingType.TOWER: 3,
               BuildingType.LUMBER_MILL: 4, BuildingType.BLACKSMITH: 5, BuildingType.STABLES: 6,
               BuildingType.WORKSHOP: 7, BuildingType.CHURCH: 8, BuildingType.VAULT: 9, BuildingType.MAGE_TOWER: 10}
# Tiers share a chain; mutually exclusive racial arts share reserved slots. Append new chains.
UPGRADE_CHAINS = ((Upgrade.KEEP,), (Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3),
                  (Upgrade.ARMOR_1, Upgrade.ARMOR_2), (Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.ARROWS_3),
                  (Upgrade.SIEGE,), (Upgrade.MARKSMANSHIP,),
                  (Upgrade.HORSES, Upgrade.BLOODLUST, Upgrade.LONGBOWS, Upgrade.DEEP_MINING),
                  (Upgrade.BLESSING, Upgrade.PLUNDER, Upgrade.REGROWTH, Upgrade.BLASTING_POWDER))
LOCAL_WORK = {
    BuildingType.TOWN_HALL: (UnitType.PEASANT, (Upgrade.KEEP,)),
    BuildingType.BARRACKS: (UnitType.FOOTMAN, UnitType.ARCHER),
    BuildingType.LUMBER_MILL: ((Upgrade.ARROWS_1, Upgrade.ARROWS_2, Upgrade.ARROWS_3), (Upgrade.MARKSMANSHIP,),
                             (Upgrade.LONGBOWS,), (Upgrade.REGROWTH,)),
    BuildingType.BLACKSMITH: ((Upgrade.BLADES_1, Upgrade.BLADES_2, Upgrade.BLADES_3), (Upgrade.ARMOR_1, Upgrade.ARMOR_2),
                             (Upgrade.BLOODLUST,), (Upgrade.DEEP_MINING,)),
    BuildingType.STABLES: (UnitType.KNIGHT, UnitType.GRYPHON, (Upgrade.HORSES,), (Upgrade.PLUNDER,)),
    BuildingType.WORKSHOP: (UnitType.CATAPULT, UnitType.FLYING_MACHINE, UnitType.SAPPER, (Upgrade.SIEGE,), (Upgrade.BLASTING_POWDER,)),
    BuildingType.CHURCH: (UnitType.CLERIC, UnitType.TREANT, UnitType.RUNE_GOLEM, (Upgrade.BLESSING,)),
}
SPELL_SLOTS = {Upgrade.HASTE: 0, Upgrade.MEND: 1, Upgrade.FLAME_STRIKE: 2, Upgrade.STONESKIN: 3,
               Upgrade.ENTANGLE: 4, Upgrade.WITHER: 5, Upgrade.METEOR: 6, Upgrade.SUMMON: 7, Upgrade.BATTLE_FURY: 8}

#: With Ctrl (Cmd on a Mac) in every scheme: the settlement from whatever the card shows, cancel mode, and the side's
#: six commands (WB-061, ``warband.brains.adjutant``).  A chord is resolved before any card, so no card's letter, now or
#: later, can take one from a scheme.  Cmd+H and Cmd+Q hide and quit the game on a Mac, so no chord uses H or Q.
CHORDS: Final = {"b": "build", "t": "train", "u": "upgrade", "g": "assembly", "p": "plans", "x": "cancel",
                 "f": "fortify", "w": "withdraw", "s": "scout", "r": "harass", "m": "gold", "l": "lumber"}
ACTIONS: Final = {
    "build": "the Build catalogue", "train": "the Train catalogue", "upgrade": "the Upgrade catalogue",
    "assembly": "the assembly point for new soldiers", "plans": "every plan and its progress",
    "cancel": "cancel mode: a click takes back a plan, a site or a building's work",
    "idle_soldier": "the next idle soldier", "repeat": "the last recruit or placement again",
    "fortify": "towers planned at the approaches: one, three, six", "withdraw": "soldiers home: the wounded, half, all",
    "scout": "scouts out: one, a quarter, half", "harass": "raiders at the rival's workers: three, a quarter, half",
    "gold": "the idle workers and a share of the lumber's to gold", "lumber": "the idle workers and a share of the gold's to lumber",
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
    modes: bool = False  # reserved mode navigation and a paged, positional card

    def card_key(self, letter: str, slot: int) -> str:
        """The key of a card command with *letter* in *slot*: the slot's, in a positional scheme, and past the grid the
        key beside it (:data:`GRID_BELOW`)."""
        if self.positional:
            if self.modes:
                return GRID_KEYS[slot % len(GRID_KEYS)]
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
        if self.modes and action in MODE_KEYS.values():
            return label(next(key for key, mode in MODE_KEYS.items() if mode == action))
        if self.positional and action in self.keys and (self.modes or self.keys[action] not in GRID_BELOW):
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
                   "B build, T train, G upgrade; Ctrl+G assembly and Ctrl+P plans are always available.", positional=True,
                   keys={"build": "b", "train": "t", "upgrade": "g", "assembly": "r", "plans": "f", "idle_soldier": "v"}),
    "modal": Scheme("modal", "Modes", "B Build, T Train, U Upgrade, O Orders, V Spells. QWE / ASD / ZXC chooses; "
                    "the active mode key leaves, Esc goes back. PageUp/PageDown changes page. Building placement lasts.", positional=True,
                    keys={"build": "b", "train": "t", "upgrade": "u", "assembly": "g", "plans": "f",
                          "idle_soldier": "comma", "repeat": "period"}, sticky=True, modes=True),
}
DEFAULT: Final = "modal"
