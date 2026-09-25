"""The spell bar and the aim (WB-066): the side's chosen spells above the minimap, and what the map shows while one is aimed.

A spell is cast by the side, not by a unit (``docs/warband-magic.md``): its button, or Alt with its level's number in
every control scheme (``docs/controls.md``), arms it, the next click on the map casts it there and Esc takes it back.
Each button shows the spell's emblem with its cooldown sweeping round it, its name, its aether at the plain price (red
while the store cannot pay it, and the most the vaults hold beside it when that is less) and its key.
While a spell is aimed the map shows its radius at the pointer, a circle on the ground as the rules measure it, the
reach of every vault of the player's, and whether a cast there costs the plain price or
:data:`~warband.sim.rules.SPELL_FAR` times it.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from saga2d import Anchor, Button, KeyHints
from warband.art.production import fit, production_image
from warband.art.textures import AETHER_LIGHT, SPELL_INKS
from warband.sim.rules import AETHER_STORE, LEVEL_NAMES, SIM_DT, SPELL_FAR, SPELLS, SpellInfo, Upgrade
from warband.ui.icons import draw_price, price_width
from warband.ui.style import AETHER, BAD, GHOST_BUTTON, TEXT

if TYPE_CHECKING:
    from warband.ui.scene import GameScene

INKS = SPELL_INKS  # each spell's own: its button's rim while it is armed, its burst where it lands
NEAR_INK = AETHER_LIGHT  # the aim's ring and words where a cast costs the plain price: within a vault's reach, its violet
FAR_INK = (255, 128, 80)  # where it costs SPELL_FAR times the plain price: beyond every vault's reach
WIDTH = 200  # the minimap's width: the bar stands over it
HEIGHT = 40
EMBLEM = 30


def sweep_parts(cx: float, cy: float, radius: float, left: float, steps: int = 36) -> list[list[tuple[float, float]]]:
    """The shadow of a cooldown: *left* (0 to 1) of a disc about (cx, cy), clockwise from the top, as convex slices, since
    the backend fans every polygon from its first point."""
    parts = []
    reach = max(1, math.ceil(steps * min(1.0, left)))
    for i in range(reach):
        a = -math.pi / 2 + math.tau * i / steps
        b = -math.pi / 2 + math.tau * min(i + 1, steps * left) / steps
        parts.append([(cx, cy), (cx + radius * math.cos(a), cy + radius * math.sin(a)), (cx + radius * math.cos(b), cy + radius * math.sin(b))])
    return parts


class SpellButton(Button):
    """One spell on the bar: a click arms it, as Alt with its level's number does."""

    def __init__(self, scene: GameScene, spell: Upgrade, **kwargs: Any) -> None:
        self.scene, self.spell, self.info = scene, spell, SPELLS[spell]
        super().__init__("", on_click=lambda: scene.aim_spell(spell), style=GHOST_BUTTON, width=WIDTH, height=HEIGHT, **kwargs)
        self.key = str(self.info.level)
        self.add(KeyHints([(self.key, "")], gap=0, spacing=0, anchor=Anchor.RIGHT, margin=6))

    @property
    def left(self) -> float:
        """How much of its cooldown is left, from 1 just after a cast to 0 when it is ready."""
        return self.scene.cooldown_share(self.spell)

    @property
    def hint(self) -> str:
        """What the tooltip panel says while the pointer is over it."""
        info, world = self.info, self.scene.world
        waits = world.cooldown_left(self.scene.human, self.spell)
        state = f"ready in {math.ceil(waits * SIM_DT)} s" if waits else "ready"
        cap = world.aether_cap(self.scene.human)
        store = f" · more than your vaults hold ({cap}): each holds {AETHER_STORE}" if info.aether > cap else ""
        return (f"{info.name} (level {LEVEL_NAMES[info.level - 1]}) — {info.summary} · {info.aether} aether, cools "
                f"{info.cooldown * SIM_DT:g} s; {SPELL_FAR}× both beyond your vaults' reach{store} · {state} · "
                f"Alt+{self.key}, then click the map")

    def on_draw(self) -> None:
        super().on_draw()
        game = self._game
        if game is None:
            return
        scene, info = self.scene, self.info
        x, y, w, h = self.bounds
        backend, order = game.backend, self._order
        if scene.aiming is self.spell:
            ink = (*INKS[self.spell.value], 255)
            for inset in (0, 1):
                backend.draw_line(x + inset, y + inset, x + w - inset, y + inset, ink, 1, order=order)
                backend.draw_line(x + inset, y + h - inset, x + w - inset, y + h - inset, ink, 1, order=order)
                backend.draw_line(x + inset, y + inset, x + inset, y + h - inset, ink, 1, order=order)
                backend.draw_line(x + w - inset, y + inset, x + w - inset, y + h - inset, ink, 1, order=order)
        key = production_image(game, self.spell, scene.human, scene.player.race)
        ex, ey = x + 6, y + (h - EMBLEM) / 2
        left = self.left
        backend.draw_image(game.assets.image(key), *fit(game, key, ex, ey, EMBLEM), opacity=0.55 if left else 1.0, order=order)
        if left:
            for part in sweep_parts(ex + EMBLEM / 2, ey + EMBLEM / 2, EMBLEM / 2, left):
                backend.draw_polygon(part, (8, 8, 12, 170), order=order)
            seconds = str(math.ceil(scene.world.cooldown_left(scene.human, self.spell) * SIM_DT))
            backend.draw_text(seconds, ex + EMBLEM / 2, ey + EMBLEM / 2, 13, TEXT, font=game.theme.font, anchor_x="center",
                              anchor_y="center", order=order)
        tx = ex + EMBLEM + 8
        name = game.theme.get_text_style("body")
        backend.draw_text(info.name, tx, y + h * 0.34, name.font_size, TEXT if not left else (200, 196, 190, 255),
                          font=name.font or game.theme.font, anchor_x="left", anchor_y="center", order=order)
        caption = game.theme.get_text_style("caption")
        font = caption.font or game.theme.font
        ink = BAD if scene.player.aether < info.aether else AETHER
        price = [("aether", str(info.aether), ink)]
        draw_price(game, price, tx, y + h * 0.56, 12, caption.font_size, font, order=order)
        cap = scene.world.aether_cap(scene.human)
        if info.aether > cap:  # no wait fills a store too small for it: say what the vaults hold, as the top bar does
            backend.draw_text(f"max {cap}", tx + price_width(game, price, 12, caption.font_size, font) + 6, y + h * 0.56 + 6,
                              caption.font_size, BAD, font=font, anchor_x="left", anchor_y="center", order=order)


def far_vaults(aether: int) -> int:
    """How many vaults hold the price beyond every vault's reach of a spell whose plain price is *aether*."""
    return -(-aether * SPELL_FAR // AETHER_STORE)


def far_needs() -> str:
    """What the dearer price beyond every vault's reach takes in vaults, for each level where one vault does not hold
    it ("; beyond it a level II cast takes 2 vaults, a level III 3"), or nothing when one holds every level's."""
    prices = sorted({info.level: info.aether for info in SPELLS.values()}.items())
    needs = [(LEVEL_NAMES[level - 1], far_vaults(aether)) for level, aether in prices if far_vaults(aether) > 1]
    words = ", ".join(f"a level {name} cast takes {vaults} vaults" if not i else f"a level {name} {vaults}"
                      for i, (name, vaults) in enumerate(needs))
    return f"; beyond it {words}" if words else ""


def aim_words(info: SpellInfo, aether: int, far: bool, cap: int) -> str:
    """What the pointer says while *info* is aimed: its price at that point, why when it is the dearer one, and what the
    vaults hold (*cap*) when that is less, since no wait pays such a price."""
    words = f"{info.name} · {aether} aether" + (f" · {SPELL_FAR}× beyond your vaults' reach" if far else "")
    if aether > cap:
        words += f" · they hold {cap}" if far else f" · your vaults hold {cap}"
    return words


def aim_ink(far: bool) -> tuple[int, int, int]:
    """The aim's ink: the vaults' violet at the plain price, the warning's orange at the dearer one."""
    return FAR_INK if far else NEAR_INK

