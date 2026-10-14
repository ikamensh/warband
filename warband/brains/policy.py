"""A learned stance policy over the bred brain: the distillation target for macro-RL.

The bred postures play one fixed set of compromises for the whole match.
What no fixed posture can do is *change its mind with the game*: press when
the enemy army is seen small, boom while it is unseen, call for catapults
only once a towered base is the problem.  That choice — a handful of
stances, re-chosen every few seconds from what the brain can honestly see
and remember — is small enough to learn by evolution strategies over match
outcomes (``tools/learn.py``) and to ship as data: the policy is a table of
weights in this file, its forward pass a few dozen multiply-adds in plain
Python, no runtime the game does not already have.

:class:`PolicyBrain` wraps a :class:`~warband.brains.pro_ai.RaceBrain`
(any posture table) and swaps its profile among the stances below.  With
the placeholder weights all zero it always picks "as bred", which is the
wrapped brain untouched — the baseline any learned table must beat.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Final

from warband.brains.ai import known_camps
from warband.brains.pro_ai import RaceBrain
from warband.brains.pro_force import strength
from warband.brains.pro_profiles import ProProfile
from warband.sim.model import World, dist, plain_sum
from warband.sim.rules import BuildingType, Layout, Race

DECIDE_EVERY: Final = 5.0  # seconds between stance choices: often enough to matter, sparse enough to learn

#: The stance names, in policy order.  Index 0 is the wrapped posture untouched.
STANCES: Final = ("as bred", "press", "hold", "boom", "creep", "siege")

#: What the policy reads, in order (see :func:`features`).  Fog-honest throughout:
#: only what the wrapped brain itself can see or remember.
FEATURE_NAMES: Final = ("bias", "time", "soldiers", "army_strength", "workers", "gold", "lumber",
                        "supply_slack", "remembered_enemy", "defenders_at_target", "strength_ratio",
                        "blind_seconds", "enemy_army_distance", "halls", "towers", "upgrades",
                        "threat_strength", "attacking", "commit_kept", "enemy_halls_seen", "camps_known")

#: The learned table, one row of weights per stance over FEATURE_NAMES.  Zeros until
#: tools/learn.py earns better: every stance scores 0 and "as bred" wins the tie.
LEARNED: Final[tuple[tuple[float, ...], ...]] = tuple(
    (0.0,) * len(FEATURE_NAMES) for _ in STANCES)


def _clamp(value: float, low: float = 0.0, high: float = 3.0) -> float:
    return max(low, min(high, value))


def features(brain, world: World) -> tuple[float, ...]:
    """The wrapped brain's situation as the policy reads it (see FEATURE_NAMES)."""
    player = brain.player
    own = world.players[player]
    army = brain._army(world)
    mine = strength(world, army)
    used, cap = world.supply(player)
    victim = brain._victim(world)
    remembered = plain_sum(brain.remembered(victim).values()) if victim is not None else 0.0
    targets = brain._attack_targets(world)
    theirs = brain._defenders_near(world, targets[0]) if targets else 0.0
    hall = brain._hall(world)
    seen = brain._army_seen.get(victim) if victim is not None else None
    buildings = world.player_buildings(player)
    threats = brain._threats(world)
    return (
        1.0,
        _clamp(world.time / 600.0),
        _clamp(len(army) / 20.0),
        _clamp(mine / 200.0),
        _clamp(len(brain._peasants(world)) / 20.0),
        _clamp(own.gold / 2000.0),
        _clamp(own.lumber / 1000.0),
        _clamp((cap - used) / 10.0, -1.0),
        _clamp(remembered / 20.0),
        _clamp(theirs / 200.0),
        _clamp(mine / max(1.0, theirs), 0.0, 3.0),
        _clamp((world.time - brain.last_seen(victim)) / 60.0) if victim is not None else 3.0,
        _clamp(dist(seen[1], hall.center) / 50.0) if seen is not None and hall is not None else 1.0,
        _clamp(sum(1 for b in buildings if b.done and b.type is BuildingType.TOWN_HALL) / 2.0),
        _clamp(sum(1 for b in buildings if b.done and b.type is BuildingType.TOWER) / 3.0),
        _clamp(len(own.upgrades) / 6.0),
        _clamp(strength(world, threats) / 200.0),
        1.0 if brain.attacking else 0.0,
        _clamp(mine / max(1.0, brain.commit_strength)) if brain.attacking else 1.0,
        _clamp(sum(1 for r in brain._known_enemy_buildings(world)
                   if r.type is BuildingType.TOWN_HALL) / 2.0),
        _clamp(len(known_camps(world, player)) / 4.0),
    )


def stances(base: ProProfile) -> tuple[ProProfile, ...]:
    """The wrapped posture under each stance: the same brain, its compromises turned for the moment."""
    return (
        base,
        replace(base, attack_ratio=base.attack_ratio * 0.55,
                min_army=max(3, base.min_army - 3), symmetry_prior=base.symmetry_prior * 0.5),
        replace(base, attack_ratio=base.attack_ratio * 1.7, retreat_ratio=min(0.95, base.retreat_ratio + 0.2)),
        replace(base, workers_per_mine=base.workers_per_mine + 3, max_workers=base.max_workers + 10,
                expand=True, expand_early=True, attack_ratio=base.attack_ratio * 1.4),
        replace(base, creep=True, creep_from=0.0, creep_ratio=min(base.creep_ratio, 1.25),
                attack_ratio=base.attack_ratio * 1.3),
        replace(base, siege_answer=max(base.siege_answer, 3), siege_share=0.15,
                early_tech=tuple(dict.fromkeys((*base.early_tech, BuildingType.WORKSHOP)))),
    )


class PolicyBrain:
    """A RaceBrain whose posture is re-chosen every few seconds by a linear policy over :func:`features`."""

    def __init__(self, player: int, table: dict[Race, tuple[ProProfile, ...]], seed: int = 0,
                 weights: tuple[tuple[float, ...], ...] = LEARNED,
                 by_layout: dict[tuple[Race, Layout], tuple[ProProfile, ...]] | None = None) -> None:
        self.inner = RaceBrain(player, table, seed, by_layout or {})
        self.player = player
        self.weights = weights
        self._stances: tuple[ProProfile, ...] = ()
        self._next_decide = 0.0
        self.stance = 0

    @property
    def log(self) -> list[tuple[float, str]]:
        return self.inner.log

    @property
    def profile(self) -> ProProfile | None:
        return self.inner.brain.profile if self.inner.brain is not None else None

    def think(self, world: World, rng: random.Random) -> None:
        if self.inner.brain is None:
            self.inner.think(world, rng)  # settles the race's posture; the first pass plays as bred
            self._stances = stances(self.inner.brain.profile)
            return
        if world.time >= self._next_decide:
            self._next_decide = world.time + DECIDE_EVERY
            reading = features(self.inner.brain, world)
            scores = [plain_sum(w * x for w, x in zip(row, reading)) for row in self.weights]
            self.stance = max(range(len(scores)), key=lambda i: scores[i])
            self.inner.brain.profile = self._stances[self.stance]
        self.inner.think(world, rng)
