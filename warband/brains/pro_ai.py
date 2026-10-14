"""The stronger opponent's scheduler: intelligence, economy and army own their decisions.

Profiles and force estimates are separate pure inputs. RaceBrain chooses the
race's posture before constructing this scheduler.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import replace

from warband.brains.pro_force import _tower_strength, strength
from warband.brains.pro_profiles import PRO, PRO_PROFILES, PRO_RUSH, PRO_VANGUARD, PRO_WARDEN, ProProfile
from warband.brains.pro_intelligence import Intelligence
from warband.brains.pro_assignments import WorkerErrands
from warband.brains.pro_army import Army
from warband.brains.pro_economy import Economy
from warband.brains.unique import Commander
from warband.sim.model import World
from warband.sim.rules import SPELLS, Layout, Race, Upgrade

class ProBrain:
    """Schedule independent knowledge, economy and army decisions for one seat."""

    def __init__(self, player: int, profile: ProProfile = PRO) -> None:
        self.player = player
        self._profile = profile
        self.next_think = 0.0
        self.next_combat = 0.0
        self.intel = Intelligence(player, profile)
        workers = WorkerErrands()
        commander = Commander()
        self.army = Army(player, profile, self.intel, workers, commander)
        self.economy = Economy(player, profile, self.intel, self.army, workers, commander)

    @property
    def profile(self) -> ProProfile:
        return self._profile

    def set_profile(self, profile: ProProfile) -> None:
        """Change policy for a learned stance while retaining each module's match memory."""
        self._profile = profile
        self.intel.profile = profile
        self.economy.profile = profile
        self.army.profile = profile
        self.army.magus.profile = profile

    @property
    def log(self) -> list[tuple[float, str]]:
        return self.intel.log

    def think(self, world: World, rng: random.Random) -> None:
        if not world.players[self.player].alive or world.winner is not None:
            return
        self.army.prepare(world)
        if world.time >= self.next_combat:
            self.next_combat = world.time + self.profile.combat_every
            self.army.combat(world)
        if world.time < self.next_think:
            return
        self.next_think = world.time + self.profile.think_every
        if not world.player_units(self.player):
            self.economy.recover(world)
            return
        self.intel.observe(world)
        self.economy.step(world, rng)
        self.army.step(world)


def played(profile: ProProfile, *, own_units: bool = True, magic: bool = True, spell: Upgrade | None = None) -> ProProfile:
    """*profile* as the tools that price a part of it play it: without its race's own unit (*own_units* False, WB-068),
    without magic (*magic* False, WB-067), or made to take *spell* at that spell's level."""
    if not own_units:
        profile = replace(profile, unique=False)
    if not magic:
        profile = replace(profile, magic=False)
    if spell is not None:
        level = SPELLS[spell].level
        profile = replace(profile, **{f"spell_{level}": spell})  # type: ignore[arg-type]
    return profile


class RaceBrain:
    """A player whose posture is its race's own: bred brains are bred per race, so which one plays is settled at the
    first pass, once the world says whom this player leads.  A race with several postures draws one from the map's
    seed and the player's seat, as Master draws its three.  *own_units*, *magic* and *spell* change every posture as
    :func:`played` says, for the tools that price a part of them."""

    def __init__(self, player: int, postures: Mapping[Race, Sequence[ProProfile]], seed: int = 0,
                 by_layout: Mapping[tuple[Race, Layout], Sequence[ProProfile]] | None = None, *, own_units: bool = True,
                 magic: bool = True, spell: Upgrade | None = None) -> None:
        self.player = player
        self.own_units, self.magic, self.spell = own_units, magic, spell
        self.postures = postures
        self.by_layout = by_layout or {}  # a race's postures for one kind of map, where it was bred for it; the New game screen names the map
        self.seed = seed
        self.brain: ProBrain | None = None

    @property
    def log(self) -> list[tuple[float, str]]:
        return self.brain.log if self.brain is not None else []

    def think(self, world: World, rng: random.Random) -> None:
        if self.brain is None:
            race = world.players[self.player].race
            options = self.by_layout.get((race, world.layout)) or self.postures[race]
            profile = options[(self.seed + self.player) % len(options)]
            self.brain = ProBrain(self.player, played(profile, own_units=self.own_units, magic=self.magic, spell=self.spell))
        self.brain.think(world, rng)
