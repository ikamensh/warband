"""A stronger computer opponent: one that never idles a building, never floats
a fortune, and picks its fights by comparing armies rather than counting them.

:class:`warband.brains.ai.Brain` plays a reasonable game and is what the difficulty
settings ship. It also leaves most of the board on the table: it builds one
thing at a time, stops at fourteen peasants, waits for round gold thresholds,
and attacks whenever it has collected N soldiers no matter what N soldiers are
waiting for it. :class:`ProBrain` is the answer to each of those, and the
arena (:mod:`warband.league.arena`) is how the answers are checked.

Where the strength comes from, in the order it matters:

*Macro.* Workers are hired against the mines actually being worked, several
building sites run at once, farms go up before the supply block rather than
after it, and every military building keeps a queue. Gold sitting in the bank
is a unit that is not fighting.

*Engagement.* Armies are compared by ``dps × effective hit points`` — Lanchester's
square law, the reason a concentrated army beats a trickle — including the
towers covering whatever is being attacked. The brain attacks when that
comparison says it wins, retreats when it stops saying so, and does not care
how many soldiers it has in absolute terms.

*Leaving the fighting alone.* An explicit ``Attack`` order switches off the
model's own automatic handling — archers kiting while they recover their shot,
a unit retargeting when something more dangerous arrives, a melee finishing a
wounded opponent in reach (see ``World._update_unit``). Directing focus fire
from outside the fight measured 109 Elo *worse* than not doing it, over 588
games, so the brain gives its army an objective and lets the model fight.
What it does still manage is which soldiers are in the fight at all: one
nearly dead walks home to be healed rather than dying for nothing.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from warband.brains.ai import (ARMY_PLANS, RESEARCH_ORDER, _shift, known_enemy_buildings, known_mines, release_arrived, site_search,
                              with_prerequisites)
from warband.sim.model import Attack, Build, Building, Harvest, Move, Point, Pos, Repair, Resource, Salvage, Unit, World, dist, rect_gap, tile_center
from warband.sim.races import RACES
from warband.sim.rules import BUILDINGS, MINE_SLOTS, UPGRADES, BuildingType, Cost, Layout, Race, UnitType, Upgrade
from warband.sim.worker_knowledge import KnownMine

_MELEE_TYPES: Final = (UnitType.FOOTMAN, UnitType.SCOUT, UnitType.KNIGHT)
WALK_OVER: Final = 4.0  # seconds the peasants sent at a frame by our own mine or hall take to reach it
STRICT_SLACK: Final = 0.1  # how far past its planned share a type may run under a strict plan
BUILD_MIN_DISTANCE: Final = 2
BUILD_MAX_DISTANCE: Final = 12
MUSTERED: Final = 1.0  # tiles from the place the brain wants it within which a soldier counts as standing there


@dataclass(frozen=True)
class ProProfile:
    """The numbers the brain plays by. Every one of them is a knob the arena can turn."""

    name: str
    think_every: float = 0.4          # seconds of simulation between macro passes
    combat_every: float = 0.2         # …and between combat passes, which are cheaper and matter more
    workers_per_mine: int = 10        # peasants a worked mine supports
    lumber_share: float = 0.35        # workforce hired above the mine slots; who chops is the model's own policy
    lumber_floor_panic: int = 350     # below this much lumber, with gold to spare, spare hands go to the trees
    panic_gold: int = 2000            # …'to spare' meaning this much unspendable gold
    lumber_stock: int = 2000          # above this much lumber, all but one chopper go back to the gold
    max_workers: int = 32
    supply_slack: int = 4             # farms go up to keep this much headroom…
    supply_per_producer: float = 2.0  # …plus this much per military building
    max_sites: int = 5                # building orders in flight at once; walking is most of a build
    surplus_gold: int = 800           # money piling up past this unlocks optional buildings
    lumber_floor: int = 150           # never spend the lumber the next few soldiers need
    max_halls: int = 3
    mine_floor: int = 6000            # a worked mine with less than this left is running out; take another
    barracks_per_hall: int = 3        # a barracks turns out ~4 soldiers a minute; income buys far more
    barracks_first: bool = False      # nothing but farms goes up before the first barracks
    towers_early: int = 0             # towers at the front point as soon as the barracks stands, before the mill
    gold_per_barracks: int = 1500     # …so every this much unspent gold justifies another one
    max_producers: int = 10
    attack_ratio: float = 0.85        # attack when my strength exceeds theirs by this
    retreat_ratio: float = 0.55       # break off once the push has lost this much of itself
    regroup_seconds: float = 45.0     # after a failed push, rebuild before trying again
    min_army: int = 5                 # never walk out with less than this, whatever the comparison says
    guards: int = 0                   # soldiers kept home against raiders, never sent out
    soldiers_before_workers: int = 6   # below this the barracks is fed before the hall
    tower_count: int = 2
    retreat_wounded: bool = True       # pull a soldier out at this much health and let it heal…
    retreat_hp: float = 0.25
    rejoin_hp: float = 0.7             # …and send it back once it is this whole again
    raid: bool = True                  # riders sent at the enemy's peasants
    raiders: int = 2
    reinforce_group: int = 1           # soldiers that must gather before walking to a fight together
    ignore_raid_ratio: float = 0.4     # a raid smaller than this share of the army does not stop a push
    scout: bool = True
    scout_from: float = 50.0           # send the first pair of eyes out at this many seconds
    stale_seconds: float = 25.0        # a sighting older than this is not worth attacking on
    symmetry_prior: float = 0.4        # an unlooked-at opponent is assumed to be this much of our own strength
    ffa_caution: float = 0.8           # how much more careful each extra opponent makes it
    expand: bool = True
    expand_early: bool = False        # a second mine before production has saturated
    siege: bool = True
    clerics: bool = True
    counter_from: float = 0.3         # an enemy more than this fraction shooters is answered with riders
    counter_strength: float = 1.0     # …this hard
    siege_share: float = 0.0          # if set, the share of the army that is catapults…
    cleric_share: float = 0.0         # …and that is healers, overriding the race's plan
    army_plan: Mapping[UnitType, float] | None = None  # shares of the army to aim for, instead of the race's own
    save_for_wanted: bool = True      # the unit the plan is shortest of has first claim on the bank, affordable yet or not
    early_tech: tuple[BuildingType, ...] = ()  # put up as soon as their requirements stand, saturated or not; twice for two
    strict_plan: bool = False         # a type already past its share of the plan is not trained, whatever is idle
    research: bool = True             # whether upgrades are bought at all
    hold_builds: bool = True          # hold the price of every build order in flight from all else it buys (WB-043)
    rush_towers: int = 0              # towers raised beside the enemy's main mine as soon as a barracks stands (one-on-one only)
    rush_builders: int = 1            # peasants that walk there, look and raise them; the brain holds their price meanwhile
    rush_tries: int = 3               # builders it drafts in all before it gives the rush up
    hunt_party: int = 5               # peasants sent at a lone enemy peasant inside our base, before it raises a frame there
    strike_seconds: float = 20.0      # a tower on our ground is struck by as many peasants as kill it this fast; 0: never
    strikers_max: int = 16            # …but no more peasants than this
    strike_lead: float = 25.0         # a frame this many seconds from standing is struck already, so the strike is there
    research_order: tuple[Upgrade, ...] | None = None  # the upgrades it buys, first first, instead of RESEARCH_ORDER
    push_upgrades: int = 0            # a push waits for this many upgrades…
    push_after: float = 0.0           # …and for this many seconds of play…
    push_by: float = 600.0            # …but not past this many
    wood_crew: int = 0                # peasants kept on the trees; 0 leaves the wood to the model's own policy
    wood_from: int = 8                # …once the workforce is this strong
    opening: tuple[BuildingType, ...] = ()  # put up in this order before anything else but farms, one at a time; twice for two
    opening_hold: bool = False        # …the next of them has first claim on the bank, ahead of soldiers and peasants
    defend_ratio: float = 0.0         # an attack on the base this many times the soldiers at home is met behind the hall, together; 0: at once
    prospect_floor: int = 0           # with less gold than this left in the mines it works and no other mine known, a peasant goes looking; 0: never
    abort_ratio: float = 0.0          # a push facing this many times its own strength where it fights, towers counted, turns back; 0: never
    wood_lead: bool = False           # hands follow the wood the next purchases are short of while the gold for them is banked
    wood_per_hand: int = 300          # …one more chopper for each this much lumber they are short
    wood_release: int = 1000          # …and back to the policy once nothing is short and this much lumber is banked


PRO: Final = ProProfile("pro")

#: The two postures Master plays, one drawn per game with the map. Both are
#: the first rung above `pro` on the ladder — nothing but farms before the
#: first barracks, the lumber panic a minute earlier — and the same strength,
#: measured 57–61% against `pro` over four seed sets each (docs/ai-ladder.md):
#: the Vanguard marches out at five soldiers with no tower, the Warden puts a
#: tower at the front point first and marches out at eight on level terms.
PRO_VANGUARD: Final = replace(PRO, name="pro-vanguard", barracks_first=True, panic_gold=1000, lumber_floor_panic=300)
#: The Warden also answers shooters earlier and harder (a fifth of the
#: enemy's soldiers rather than three tenths, twice the swing): 63% against
#: `pro` over 200 games where the same posture without it took 58%. The
#: Vanguard measured worse with it (51% against its 60%), and keeps its own.
PRO_WARDEN: Final = replace(PRO_VANGUARD, name="pro-warden", towers_early=1, min_army=8, attack_ratio=1.0,
                     counter_from=0.2, counter_strength=2.0)

#: Variants used to find out which knob is actually carrying the strength.
#: Each differs from :data:`PRO` in one thing, so a ladder over all of them
#: attributes the difference rather than guessing at it. What each one settled
#: is written down in ``docs/ai-ladder.md``.
#: The Hard difficulty: the same brain as Master, thinking once every second
#: and a half on a small economy, without raiders, scouts or expansions, and
#: back on the cautious posture Master gave up. It exists to put a real step
#: between Medium and Master — measured at 1218 Elo against Medium's 1000 and
#: Master's 1420 — not to be the best player available.
PRO_HARD: Final = replace(PRO, name="pro-hard", think_every=1.5, combat_every=0.5, workers_per_mine=6,
                   barracks_per_hall=1, max_sites=2, raid=False, retreat_wounded=False,
                   expand=False, min_army=10, attack_ratio=1.6, symmetry_prior=1.0, guards=2)

_TRIALS: Final = (
    PRO_HARD,
    replace(PRO, name="pro-timid", min_army=10, attack_ratio=1.6, symmetry_prior=1.0, guards=2,
            workers_per_mine=13, barracks_per_hall=4),   # the cautious posture it replaced
    replace(PRO, name="pro-noscout", scout=False),
    replace(PRO, name="pro-noraid", raid=False),
    replace(PRO, name="pro-noheal", retreat_wounded=False),
    replace(PRO, name="pro-noexpand", expand=False),
    replace(PRO, name="pro-lean", max_sites=3, barracks_per_hall=2),
    replace(PRO, name="pro-workersfirst", soldiers_before_workers=0),
    replace(PRO, name="pro-nopanic", lumber_floor_panic=0),
    replace(PRO, name="pro-nocounter", counter_from=1.1),
    # The balance league (docs/balance.md) found the wood crew only ever grew and
    # producers bought whatever was affordable at the moment: these two play the way it was.
    replace(PRO, name="pro-nostock", lumber_stock=10**9),
    replace(PRO, name="pro-nosave", save_for_wanted=False),
    replace(PRO, name="pro-old", lumber_stock=10**9, save_for_wanted=False),
    # Before WB-043 a build order's price was not held while its builder walked, and a quarter of the orders
    # died on arrival, unpaid: these play the way it was.
    replace(PRO_VANGUARD, name="pro-vanguard-nohold", hold_builds=False),
    replace(PRO_WARDEN, name="pro-warden-nohold", hold_builds=False),
    replace(PRO_HARD, name="pro-hard-nohold", hold_builds=False),
    # Before WB-037 a brain let a lone enemy peasant walk into its base and left a tower there standing: these do.
    replace(PRO_VANGUARD, name="pro-vanguard-unanswered", hunt_party=0, strike_seconds=0.0),
    replace(PRO_WARDEN, name="pro-warden-unanswered", hunt_party=0, strike_seconds=0.0),
    replace(PRO_HARD, name="pro-hard-unanswered", hunt_party=0, strike_seconds=0.0),
)
#: The tower rush (WB-036), Master's third posture: the Vanguard, with a peasant that walks to the far side of
#: the enemy's main mine as its first barracks goes up and raises a tower there once it stands. Rated after
#: WB-037's answers: 56% against the Vanguard and level with the Warden; Hard's version lost 42% to plain Hard.
PRO_RUSH: Final = replace(PRO_VANGUARD, name="pro-rush", rush_towers=1)
PRO_PROFILES: Final[dict[str, ProProfile]] = {"pro": PRO, PRO_VANGUARD.name: PRO_VANGUARD, PRO_WARDEN.name: PRO_WARDEN,
                                       PRO_RUSH.name: PRO_RUSH, **{p.name: p for p in _TRIALS}}


# -- Force comparison ---------------------------------------------------------------

def _dps(world: World, unit: Unit) -> float:
    if unit.info.heal:
        # A cleric adds to a fight by undoing damage; count its healing as if it were damage (its own blow is a last resort).
        return world.heal_rate(unit) * 0.8
    return world.damage_of(unit) / unit.info.period


def _effective_hp(world: World, unit: Unit) -> float:
    """Hit points inflated by armour, which is subtracted from every blow that lands."""
    return unit.hp * (1.0 + world.armor_of(unit) / 6.0)


def strength(world: World, units: list[Unit]) -> float:
    """How much fight a group has in it: ``sqrt(total dps × total effective hit points)``.

    Squaring it gives Lanchester's square-law combat power, ``N² × dps × hp``
    for a group of like units — twice the army is four times the force, which
    is why feeding soldiers in piecemeal loses. Comparing two of these numbers
    therefore ranks armies exactly as comparing the square law would, and the
    root keeps the ratios the brain is tuned against readable.
    """
    damage = sum(_dps(world, u) for u in units)
    body = sum(_effective_hp(world, u) for u in units)
    return math.sqrt(damage * body)


def _tower_strength(world: World, player: int, point: Point, radius: float = 9.0) -> float:
    """What the fortifications around *point* add to the defender.

    Only the ones we have seen: ``worker_knowledge`` remembers every armed
    structure this player has laid eyes on, and nothing else. A tower is priced
    at what it was built as rather than at its current health, because a
    remembered tower is not a tower we are looking at.
    """
    damage = body = 0.0
    for record in world.worker_knowledge[player].threats:
        if record.player in (None, player) or dist(record.center, point) > radius:
            continue
        building = world.buildings.get(record.id)
        if building is None or not building.info.damage:
            continue
        damage += world.damage_of(building) / building.info.cooldown
        body += building.max_hp
    return math.sqrt(damage * body)


def _tower_strength_own(world: World, player: int, point: Point, radius: float = 9.0) -> float:
    """What *player*'s own standing towers around *point* add to its defence, as :func:`_tower_strength` prices an enemy's."""
    damage = body = 0.0
    for building in world.player_buildings(player, BuildingType.TOWER, done=True):
        if dist(building.center, point) <= radius:
            damage += world.damage_of(building) / building.info.cooldown
            body += building.hp
    return math.sqrt(damage * body)


class ProBrain:
    """One per AI player; ``think`` every simulation step, as with :class:`warband.brains.ai.Brain`."""

    def __init__(self, player: int, profile: ProProfile = PRO) -> None:
        self.player = player
        self.profile = profile
        self.next_think = 0.0
        self.next_combat = 0.0
        self.attacking = False
        self.target: Point | None = None      # where the current push is aimed
        self.commit_strength = 0.0            # what the army was worth when it set out
        self.regroup_until = 0.0              # no new push before this, so a beaten army rebuilds
        self.scouts: list[int] = []
        self.prospector: int | None = None  # the peasant out looking for the next mine
        self._prospect_leg = 0              # how many places it has been sent to look
        self.raiders: list[int] = []
        self.rushers: list[int] = []  # peasants walking to the enemy's mine to raise a tower there
        self.rush_drafted = 0
        self.rush_over = False
        self._hurt: set[int] = set()  # soldiers pulled out to heal
        self.hunters: dict[int, int] = {}  # our peasants sent at an enemy peasant inside our base: hunter -> its prey
        self.strikers: set[int] = set()    # our peasants sent at an enemy tower standing on our ground
        self.lumber_short = 0  # the wood the purchases it has the gold for are waiting on; see _shortfall
        self._opening_next: BuildingType | None = None  # the building of the opening that goes up next, while one is left
        self.log: list[tuple[float, str]] = []
        self._seen: dict[int, dict[UnitType, float]] = {}  # per opponent: most of each kind ever seen at once
        self._seen_at: dict[int, float] = {}               # …and when that opponent was last looked at

    def note(self, world: World, what: str) -> None:
        self.log.append((world.time, what))

    # -- The pass ------------------------------------------------------------------

    def think(self, world: World, rng: random.Random) -> None:
        if not world.players[self.player].alive or world.winner is not None:
            return
        if world.time >= self.next_combat:
            self.next_combat = world.time + self.profile.combat_every
            self._combat(world)
        if world.time < self.next_think:
            return
        self.next_think = world.time + self.profile.think_every
        if not world.player_units(self.player):
            self._recover(world)
            return
        self._observe(world)
        self._economy(world)
        self._tower_rush(world)    # a rush tower's price is held from everything below
        self._training(world)      # soldiers get first call on the bank…
        self._construction(world, rng)  # …and buildings buy what is left
        self._research(world)
        self._repairs(world)
        self._military(world)

    def _recover(self, world: World) -> None:
        """Nothing left but buildings: buy the cheapest body that can still work."""
        buildings = world.player_buildings(self.player)
        if any(b.done and b.queue for b in buildings):
            return
        recruit = world.recovery_recruit(self.player)
        if recruit is None:
            return
        building, unit_type = recruit
        if world.can_train(building, unit_type) is not None:
            for b in buildings:
                if not b.done:
                    world.cancel_building(b.id)
                elif b.research is not None:
                    world.cancel_research(b.id)
        world.train(building.id, unit_type)

    # -- Helpers -------------------------------------------------------------------

    def _units(self, world: World) -> list[Unit]:
        return world.player_units(self.player)

    def _peasants(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if u.is_worker]

    def _army(self, world: World) -> list[Unit]:
        return [u for u in self._units(world) if not u.is_worker]

    def _halls(self, world: World) -> list[Building]:
        return world.player_buildings(self.player, BuildingType.TOWN_HALL, done=True)

    def _hall(self, world: World) -> Building | None:
        halls = self._halls(world)
        return halls[0] if halls else None

    def _knowledge(self, world: World):
        """What this player has actually seen: the model's own per-player memory."""
        return world.worker_knowledge[self.player]

    def _known_enemy_buildings(self, world: World) -> list:
        return known_enemy_buildings(world, self.player)

    def _unexplored_corner(self, world: World) -> Point:
        """Somewhere worth looking when nothing of theirs has been found yet.

        Starts sit in the corners, so the far one from ours is the first guess.
        """
        hall = self._hall(world)
        here = hall.center if hall is not None else (world.width / 2, world.height / 2)
        corners = [(2.5, 2.5), (world.width - 2.5, 2.5), (2.5, world.height - 2.5),
                   (world.width - 2.5, world.height - 2.5)]
        return max(corners, key=lambda c: dist(c, here))

    def _known_mines(self, world: World) -> list[KnownMine]:
        return known_mines(world, self.player)

    def _enemies(self, world: World) -> list[Unit]:
        """Visible enemy units of players still in the game."""
        return [u for u in world.units.values()
                if u.player != self.player and u.hp > 0 and not u.hidden
                and world.players[u.player].alive and world.is_visible(self.player, u.tile)]

    def _observe(self, world: World) -> None:
        """Remember the most of each kind the enemy was ever seen with, fading as the sighting ages.

        The memory holds a *count*, so it has to be the high-water mark rather
        than a running total: adding every sighting to a decaying tally reports
        roughly ten times the army that is actually there, and a brain that
        believes it is always outnumbered never attacks at all.
        """
        current: dict[int, dict[UnitType, float]] = {}
        for unit in self._enemies(world):
            if not unit.is_worker:
                seen = current.setdefault(unit.player, {})
                seen[unit.type] = seen.get(unit.type, 0.0) + 1.0
        fade = 0.99 ** (self.profile.think_every / 0.4)
        for player in world.players:
            if player.id == self.player or not player.alive:
                continue
            now = current.get(player.id, {})
            if now:
                self._seen_at[player.id] = world.time
            memory = self._seen.setdefault(player.id, {})
            for unit_type in set(memory) | set(now):
                memory[unit_type] = max(memory.get(unit_type, 0.0) * fade, now.get(unit_type, 0.0))

    def remembered(self, player: int | None = None) -> dict[UnitType, float]:
        """How many of each kind *player* was last seen with; every opponent's, added, if None."""
        if player is not None:
            return dict(self._seen.get(player, {}))
        out: dict[UnitType, float] = {}
        for memory in self._seen.values():
            for unit_type, count in memory.items():
                out[unit_type] = out.get(unit_type, 0.0) + count
        return out

    def last_seen(self, player: int | None = None) -> float:
        """When an opponent was last looked at; the most recent look at anyone if None."""
        if player is not None:
            return self._seen_at.get(player, -math.inf)
        return max(self._seen_at.values(), default=-math.inf)

    # -- Economy -------------------------------------------------------------------

    def _worked_mines(self, world: World) -> list[KnownMine]:
        """Mines with gold left inside reach of one of our halls."""
        halls = self._halls(world)
        if not halls:
            return []
        return [m for m in self._known_mines(world) if m.gold > 0 and min(dist(m.center, h.center) for h in halls) < 14.0]

    def _worker_target(self, world: World) -> int:
        """Peasants worth having: what the mines being worked can absorb.

        Hired as fast as the halls will make them. Feeding them in gradually
        instead was measured and is simply worse — 1516 Elo against 1329 for the
        same target reached over forty seconds a worker — because the economy
        that pays for the army is the thing being delayed.
        """
        mines = max(1, len(self._worked_mines(world)))
        wanted = round(mines * self.profile.workers_per_mine / (1.0 - self.profile.lumber_share))
        return min(self.profile.max_workers, wanted)

    def _economy(self, world: World) -> None:
        world.assign_workers(self.player)
        self._chop(world)
        self._prospect(world)

    def _prospect(self, world: World) -> None:
        """Send a peasant to look for gold while the mines being worked run low and no other is known.

        An expansion goes to a mine the player has seen, and a brain that does not scout has seen its own.  On
        Klondike, where home holds twenty thousand and the rest lies in a pit in the middle, the bred postures
        mined out in four minutes, never learnt of the pit, stalled at ten soldiers short of the army they wait
        for and lost to Easy: most of what Grandmaster lost to anyone.  The middle of the map first, then its
        corners, nearest first; the peasant goes back to work when a mine is found or the places run out."""
        profile = self.profile
        if profile.prospect_floor <= 0 or not profile.expand:
            return
        found = self._expansion_site(world) is not None
        low = sum(mine.gold for mine in self._worked_mines(world)) < profile.prospect_floor
        if self.prospector is not None and (found or not low or self.prospector not in world.units):
            if self.prospector in world.units:
                world.release_workers([self.prospector])
            self.prospector = None
        if found or not low:
            return
        hall = self._hall(world)
        if hall is None:
            return
        places = [(world.width / 2, world.height / 2)] + sorted(
            [(3.5, 3.5), (world.width - 3.5, 3.5), (3.5, world.height - 3.5), (world.width - 3.5, world.height - 3.5)],
            key=lambda corner: dist(corner, hall.center))[1:]
        if self._prospect_leg >= 2 * len(places):
            return  # looked everywhere twice: there is nothing to find
        if self.prospector is None:
            spare = [p for p in self._free_peasants(world) if p.carrying is None and not p.hidden]
            if len(spare) < 4:
                return
            self.prospector = min(spare, key=lambda p: dist(p.pos, places[0])).id
        walker = world.units[self.prospector]
        if not isinstance(walker.order, Move):
            world.move([walker.id], self._standable(world, places[self._prospect_leg % len(places)]))
            self._prospect_leg += 1
            self.note(world, f"prospect: peasant {walker.id} looks for gold")

    @staticmethod
    def _on_lumber(peasant: Unit) -> bool:
        """Whether this peasant is working wood: a tree is a tile, a mine is an id."""
        if peasant.carrying is Resource.LUMBER:
            return True
        return any(isinstance(order, Harvest) and not isinstance(order.target, int) for order in peasant.orders)

    def _chop(self, world: World) -> None:
        """Hands follow scarcity both ways: to the trees when the wood runs out, back to the gold when it piles up.

        A fixed share of the workforce on lumber is worse than the model's own
        policy, and measured so twice: as a standing share it cost 40 to 180
        Elo depending on the share, because every hand on wood is gold not
        coming in during the minutes that decide the game. What the policy
        does not handle is the map where the wood near home is gone — lumber
        sits at zero, no farm can be built, the supply cap freezes, and a bank
        of fifteen thousand gold buys nothing at all — so the rule fires on the
        symptom rather than running all the time.

        The model's policy only ever places a peasant once, so a crew sent to the
        trees stayed there for the rest of the game: the balance league's losers
        ended with five to sixteen thousand lumber banked while gold was what they
        lacked. Above ``lumber_stock`` all but one chopper go back to the mine.
        """
        player = world.players[self.player]
        peasants = [p for p in self._peasants(world)
                    if not p.hidden and not isinstance(p.order, (Build, Repair, Salvage)) and p.id not in self.scouts
                    and not self._answering(p)]
        if player.lumber >= self.profile.lumber_stock:
            # Let go of the axe and let the model's own policy place them. Naming a
            # mine here crashed a league sixty matches in: the brain chose from the
            # player's memory, which keeps a mine nobody has looked at lately, and a
            # harvest order on ground that no longer holds one is refused.
            world.release_workers([p.id for p in peasants if self._on_lumber(p) and p.carrying is None][1:])
            return
        crew = self.profile.wood_crew if len(peasants) >= self.profile.wood_from else 0
        if self.profile.wood_lead:
            choppers = [p for p in peasants if self._on_lumber(p)]
            if self.lumber_short > 0:
                crew = max(crew, min(len(peasants) // 2, -(-self.lumber_short // self.profile.wood_per_hand)))
            elif player.lumber >= self.profile.wood_release and len(choppers) > crew:
                world.release_workers([p.id for p in choppers if p.carrying is None][:len(choppers) - crew])
                return
        if player.lumber >= self.profile.lumber_floor_panic or player.gold < self.profile.panic_gold:
            want = crew
        else:
            # Never everyone: gold still has to come in, or the next peasant never does.
            want = max(crew, min(len(peasants) // 2, max(0, len(peasants) - 2)))
        short = want - sum(1 for p in peasants if self._on_lumber(p))
        if short <= 0:
            return
        for peasant in [p for p in peasants if not self._on_lumber(p) and p.carrying is None][:short]:
            tree = world.nearest_tree(peasant.pos, 24)
            if tree is not None:
                world.harvest([peasant.id], tree)

    def _repairs(self, world: World) -> None:
        damaged = [b for b in world.player_buildings(self.player, done=True)
                   if b.hp < b.max_hp * 0.6 and b.type is not BuildingType.GOLD_MINE]
        if not damaged or any(isinstance(p.order, Repair) for p in self._peasants(world)):
            return
        target = min(damaged, key=lambda b: b.hp / b.max_hp)
        if world._nearest_enemy(self.player, target.center, 8.0) is not None:
            return
        spare = [p for p in self._peasants(world) if not p.hidden and p.carrying is None and not isinstance(p.order, Build)
                 and not self._answering(p)]
        if spare:
            world.repair([min(spare, key=lambda p: dist(p.pos, target.center)).id], target.id)

    # -- Construction ---------------------------------------------------------------

    def _wish_list(self, world: World) -> list[tuple[BuildingType, Point]]:
        """What to put up next, best first. Nothing here waits on a round number of gold."""
        player = self.player
        profile = self.profile
        halls = self._halls(world)
        hall = halls[0] if halls else None
        peasants = self._peasants(world)
        fallback = peasants[0].pos if peasants else (world.width / 2, world.height / 2)
        if hall is None:
            mines = self._known_mines(world)
            nearest = min(mines, key=lambda m: dist(m.center, fallback)) if mines else None
            return [(BuildingType.TOWN_HALL, nearest.center if nearest is not None else fallback)]

        have = lambda t: len(world.player_buildings(player, t, done=True))  # noqa: E731
        # A building that has been ordered does not exist until the peasant walks
        # to the site and pays for it, so the orders in flight have to be counted
        # too — otherwise the same barracks is wished for again on the next pass.
        going_up = ([b.type for b in world.player_buildings(player) if not b.done]
                    + [order.type for order in self._ordered(world)])
        count = lambda t: have(t) + going_up.count(t)  # noqa: E731
        anchor = hall.center
        wishes: list[tuple[BuildingType, Point]] = []

        used, cap = world.supply(player)
        producers = sum(count(t) for t in (BuildingType.BARRACKS, BuildingType.STABLES,
                                           BuildingType.WORKSHOP, BuildingType.CHURCH))
        headroom = profile.supply_slack + int(profile.supply_per_producer * producers)
        farms_coming = going_up.count(BuildingType.FARM) + going_up.count(BuildingType.TOWN_HALL)
        if cap - used + 4 * farms_coming < headroom:
            wishes.append((BuildingType.FARM, anchor))
        self._opening_next = None
        listed: dict[BuildingType, int] = {}
        # An opening counts each building once. ``count`` sees a site twice while it goes up, as the building and as
        # its builder's order, which the knobs above were tuned with; a list that names the second barracks cannot
        # take the first one's frame for it.
        begun = [b.type for b in world.player_buildings(player) if not b.done] + [o.type for o in self._ordered(world) if o.building is None]
        for step in profile.opening:
            listed[step] = listed.get(step, 0) + 1
            needs = BUILDINGS[step].requires
            if have(step) + begun.count(step) >= listed[step] or (needs is not None and not have(needs)):
                continue  # up already, or waiting for what it needs: the next of the opening goes up meanwhile
            where = self._front_point(world, hall) if step is BuildingType.TOWER else anchor
            if step is BuildingType.TOWN_HALL:
                site = self._expansion_site(world)
                if site is None:
                    continue
                where = site
            # One at a time, in order, and nothing else but farms: an opening is a plan, and the cheaper building
            # further down the list is what the bank would otherwise buy first.
            self._opening_next = step
            wishes.append((step, where))
            return wishes
        if count(BuildingType.BARRACKS) < 1:
            wishes.append((BuildingType.BARRACKS, anchor))
            # The mill sits behind the barracks here and costs a hundred gold
            # less, so whenever the bank is between the two it is the mill that
            # gets bought — and its 450 lumber is the barracks' 450 lumber, a
            # minute of chopping later. Both brains in a mirror trace had their
            # first barracks at three minutes for exactly this reason.
            if profile.barracks_first:
                return wishes
        if count(BuildingType.TOWER) < profile.towers_early:
            # A tower is two footmen's worth of fight for less than one footman's
            # gold, for as long as the enemy comes to it — and Master comes to it.
            wishes.append((BuildingType.TOWER, self._front_point(world, hall)))
        if count(BuildingType.LUMBER_MILL) < 1:
            # Beside the hall, where the site search puts it. Siting it at the
            # edge of the nearest wood measured level (52–56% against Master,
            # where barracks-first alone took 59%): the wood is six tiles from
            # every start, and a second mill at the wood front no better.
            wishes.append((BuildingType.LUMBER_MILL, anchor))
        # A posture built around one branch of the tree — knights, siege, healers —
        # cannot wait for the bank to overflow before it is allowed that branch.
        for tech in set(profile.early_tech):
            needs = BUILDINGS[tech].requires
            if count(tech) < profile.early_tech.count(tech) and (needs is None or have(needs)):
                wishes.append((tech, anchor))
        # Everything past here is optional, and optional buildings are what lose games:
        # each one is an army that was not trained. They are unlocked only once the
        # production already standing cannot keep up with the money coming in.
        expansion = self._expansion_site(world) if profile.expand else None
        room_for_a_hall = expansion is not None and count(BuildingType.TOWN_HALL) < profile.max_halls
        if expansion is not None and room_for_a_hall and (profile.expand_early or self._mines_failing(world)):
            # Scarcity opens this gate as well as plenty. A brain whose mines are
            # spent or full has no income to saturate its production with, so
            # waiting for saturation meant never expanding at all: the dry-mine
            # league saw no second hall in 336 seats. A hall takes a minute to
            # build and a peasant longer to walk, so the move starts while the
            # old mine still has gold in it.
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if not self._producers_saturated(world):
            return wishes
        if expansion is not None and room_for_a_hall and not profile.expand_early:
            wishes.append((BuildingType.TOWN_HALL, expansion))
        if count(BuildingType.BLACKSMITH) < 1:
            wishes.append((BuildingType.BLACKSMITH, anchor))
        # Production capacity is what the bank is short of, not money. A barracks
        # turns out about four soldiers a minute; gold piling up past that is an
        # army that does not exist. Tie the target to what is actually unspent.
        barracks_target = min(profile.max_producers,
                              max(profile.barracks_per_hall * max(1, len(halls)),
                                  1 + world.players[player].gold // profile.gold_per_barracks))
        if count(BuildingType.BARRACKS) < barracks_target:
            wishes.append((BuildingType.BARRACKS, anchor))
        if count(BuildingType.STABLES) < 1:
            wishes.append((BuildingType.STABLES, anchor))
        if profile.siege and have(BuildingType.BLACKSMITH) and count(BuildingType.WORKSHOP) < 1:
            wishes.append((BuildingType.WORKSHOP, anchor))
        if profile.clerics and count(BuildingType.CHURCH) < 1:
            wishes.append((BuildingType.CHURCH, anchor))
        if count(BuildingType.TOWER) < profile.tower_count and len(self._army(world)) >= 4:
            wishes.append((BuildingType.TOWER, self._front_point(world, hall)))
        return wishes

    def _mines_failing(self, world: World) -> bool:
        """Whether the mines being worked can no longer grow this economy: spent, or every place at the face taken."""
        mines = self._worked_mines(world)
        if not mines:
            return True
        if sum(mine.gold for mine in mines) < self.profile.mine_floor * len(mines):
            return True
        miners = sum(1 for p in self._peasants(world)
                     if p.inside is not None or any(isinstance(o, Harvest) and isinstance(o.target, int) for o in p.orders))
        return miners >= MINE_SLOTS * len(mines)

    def _producers_saturated(self, world: World) -> bool:
        """Whether the buildings already standing are the bottleneck rather than the bank.

        A barracks that is always mid-queue is worth another barracks; one that
        idles for want of gold is not, and neither is a stables next to it.
        """
        producers = [b for b in world.player_buildings(self.player, done=True)
                     if b.info.trains and b.type is not BuildingType.TOWN_HALL]
        if not producers:
            return False
        if any(not b.queue and b.research is None for b in producers):
            return False
        player = world.players[self.player]
        return player.gold >= self.profile.surplus_gold

    def _expansion_site(self, world: World) -> Point | None:
        """An unclaimed mine with gold in it, nearest to home."""
        halls = self._halls(world)
        if not halls:
            return None
        claimed = [h.center for h in world.player_buildings(self.player, BuildingType.TOWN_HALL)]
        best, best_distance = None, math.inf
        for mine in self._known_mines(world):
            if mine.gold <= 0 or min(dist(mine.center, c) for c in claimed) < 12.0:
                continue
            away = min(dist(mine.center, h.center) for h in halls)
            enemy_halls = [r.center for r in self._known_enemy_buildings(world)]
            if enemy_halls and min(dist(mine.center, c) for c in enemy_halls) < away:
                continue  # not ours to take yet
            if away < best_distance:
                best, best_distance = mine.center, away
        return best

    def _ordered(self, world: World) -> list[Build]:
        """The build orders already given and not yet begun.

        ``World.build`` only hands a peasant an order: the building appears, and
        is paid for, when that peasant arrives. Between the two it is invisible
        to ``player_buildings``, and a brain that does not remember giving the
        order re-gives it every pass — which sends peasant after peasant off the
        gold to start the same barracks in four different places.
        """
        return [p.order for p in self._peasants(world) if isinstance(p.order, Build)]

    def _shortfall(self, world: World, wishes: Sequence[tuple[BuildingType, Point]]) -> int:
        """The lumber the wished-for buildings lack while the gold for them is in the bank, the list walked in order
        with what is left: the symptom of a bank of three thousand gold that buys nothing because every barracks
        and farm on the list wants wood the brain is not chopping."""
        gold, lumber = self._spendable(world)
        lumber -= self.profile.lumber_floor
        short = 0
        for wanted, _anchor in wishes:
            cost = BUILDINGS[wanted].cost
            if gold < cost.gold:
                break  # gold binds from here on: more wood would buy nothing
            gold -= cost.gold
            if lumber < cost.lumber:
                short += cost.lumber - max(0, lumber)
            lumber -= cost.lumber
        return short

    def _construction(self, world: World, rng: random.Random) -> None:
        wishes = self._wish_list(world)
        if self.profile.wood_lead:
            self.lumber_short = self._shortfall(world, wishes)
        sites = [b for b in world.player_buildings(self.player) if not b.done]
        free = self.profile.max_sites - len(sites) - len(self._ordered(world))
        if free <= 0:
            return
        builders = [p for p in self._peasants(world)
                    if not p.hidden and not isinstance(p.order, (Build, Repair, Salvage)) and not self._answering(p)]
        if not builders:
            return
        # Ground already spoken for by an order in flight: can_place cannot know
        # about it, so two buildings would otherwise be sent to the same tile.
        taken = [(o.pos, BUILDINGS[o.type].size) for o in self._ordered(world)]
        for wanted, anchor in wishes:
            if free <= 0 or not builders:
                break
            cost = BUILDINGS[wanted].cost
            if world.can_afford(self.player, cost) is not None or not self._payable(world, cost):
                continue
            if self._spendable(world)[1] - cost.lumber < self.profile.lumber_floor and wanted is not self._opening_next:
                continue
            site = self._site(world, wanted, anchor, rng, taken)
            if site is None:
                continue
            builder = min(builders, key=lambda p: dist(p.pos, (site[0] + 1.0, site[1] + 1.0)))
            world.build(builder.id, wanted, site)
            taken.append((site, BUILDINGS[wanted].size))
            builders.remove(builder)
            free -= 1
            self.note(world, f"build {wanted.value} at {site}")

    def _site(self, world: World, building_type: BuildingType, anchor: Point, rng: random.Random,
              taken: Sequence[tuple[Pos, int]] = ()) -> Pos | None:
        return site_search(world, building_type, self.player, anchor, rng, BUILD_MIN_DISTANCE, BUILD_MAX_DISTANCE, taken)

    # -- Tower rush -------------------------------------------------------------------

    def _held(self, world: World) -> tuple[int, int]:
        """What orders in flight will pay on arrival: every build order not begun yet, and a rush tower whose
        builder is still walking to its site. A build order is paid at the site, and a bank spent during the
        walk drops it there: a quarter of Master's orders died so before this held them (WB-043)."""
        gold = lumber = 0
        for peasant in self._peasants(world):
            order = peasant.order
            if isinstance(order, Build) and order.building is None and (self.profile.hold_builds or peasant.id in self.rushers):
                cost = BUILDINGS[order.type].cost
                gold, lumber = gold + cost.gold, lumber + cost.lumber
            elif peasant.id in self.rushers and peasant.constructing is None and not isinstance(order, Build):
                cost = BUILDINGS[BuildingType.TOWER].cost
                gold, lumber = gold + cost.gold, lumber + cost.lumber
        for saved in self._saving_for(world):
            gold, lumber = gold + saved.gold, lumber + saved.lumber
        return (gold, lumber)

    def _research_order(self) -> tuple[Upgrade, ...]:
        return self.profile.research_order if self.profile.research_order is not None else RESEARCH_ORDER

    def _saving_for(self, world: World) -> list[Cost]:
        """The prices held for what the posture buys ahead of soldiers: the next building of its opening.  The
        purchase itself is paid out of what was held for it."""
        saved = []
        if self.profile.opening_hold and self._opening_next is not None:
            saved.append(BUILDINGS[self._opening_next].cost)
        return saved

    def _payable(self, world: World, cost: Cost) -> bool:
        """Whether *cost* can be paid now: one of the prices being saved for out of the whole bank but for the other
        holds, anything else out of what is left."""
        if not any(cost is saved for saved in self._saving_for(world)):
            return self._affordable(world, cost)
        gold, lumber = self._spendable(world)
        return gold >= 0 and lumber >= 0  # what is left once every hold is counted, its own among them

    def _spendable(self, world: World) -> tuple[int, int]:
        bank, (gold, lumber) = world.players[self.player], self._held(world)
        return (bank.gold - gold, bank.lumber - lumber)

    def _affordable(self, world: World, cost: Cost) -> bool:
        gold, lumber = self._spendable(world)
        return gold >= cost.gold and lumber >= cost.lumber

    def _enemy_mine_guess(self, world: World) -> Point | None:
        """Where the one opponent's main mine must be: a two-seat map is the point reflection of itself
        through the centre, so it is the reflection of our own main mine."""
        hall = self._hall(world)
        mines = self._known_mines(world)
        if hall is None or not mines or len(world.players) != 2:
            return None
        ours = min(mines, key=lambda m: dist((m.x + m.size / 2, m.y + m.size / 2), hall.center))
        return (world.width - (ours.x + ours.size / 2), world.height - (ours.y + ours.size / 2))

    def _rush_mine(self, world: World, guess: Point) -> KnownMine | None:
        """The enemy's main mine, once seen."""
        seen = [m for m in self._known_mines(world) if dist((m.x + m.size / 2, m.y + m.size / 2), guess) < 3]
        return seen[0] if seen else None

    def _enemy_start(self, world: World) -> Point | None:
        """Where the one opponent started: the point reflection of our own start through the centre."""
        hall = self._hall(world)
        if hall is None or len(world.players) != 2:
            return None
        return (world.width - hall.center[0], world.height - hall.center[1])

    def _behind(self, mine: Point, start: Point, reach: float) -> Point:
        """*reach* tiles beyond *mine* seen from *start*: the side their gatherers do not walk."""
        away = (mine[0] - start[0], mine[1] - start[1])
        length = math.hypot(*away) or 1.0
        return (mine[0] + away[0] / length * reach, mine[1] + away[1] / length * reach)

    def _rush_site(self, world: World, mine: KnownMine, start: Point) -> Pos | None:
        """A tower site 1.5 to 3 tiles from the enemy's mine, as far round it from their hall as there is."""
        size = BUILDINGS[BuildingType.TOWER].size
        best: tuple[float, Pos] | None = None
        for y in range(mine.y - 6, mine.y + mine.size + 6):
            for x in range(mine.x - 6, mine.x + mine.size + 6):
                centre = (x + size / 2, y + size / 2)
                gap = rect_gap(centre, mine.rect) - size / 2
                if not 1.5 <= gap <= 3.0 or world.can_place(BuildingType.TOWER, (x, y), self.player) is not None:
                    continue
                score = dist(centre, start)
                if best is None or score > best[0]:
                    best = (score, (x, y))
        return None if best is None else best[1]

    def _tower_rush(self, world: World) -> None:
        """Towers beside the enemy's main mine, raised by a peasant who walks to where they must have started.

        A tower needs a barracks, so the walk starts when one stands. The peasant is kept off the
        gatherer policy (holding while it waits), and the tower's price is held from everything the
        brain buys until the peasant has paid it on arrival."""
        profile = self.profile
        if profile.rush_towers <= 0 or self.rush_over:
            return
        start, guess = self._enemy_start(world), self._enemy_mine_guess(world)
        # The walk takes most of a minute, so it starts as the barracks goes up; the tower is ordered when it stands.
        if start is None or guess is None or not world.player_buildings(self.player, BuildingType.BARRACKS):
            return
        barracks = bool(world.player_buildings(self.player, BuildingType.BARRACKS, done=True))
        mine = self._rush_mine(world, guess)
        if mine is not None and sum(1 for b in world.player_buildings(self.player, BuildingType.TOWER)
                                    if rect_gap(b.center, mine.rect) <= 4.5) >= profile.rush_towers:
            self._end_rush(world)
            return
        self.rushers = [i for i in self.rushers if i in world.units]
        while len(self.rushers) < profile.rush_builders and self.rush_drafted < profile.rush_tries:
            spare = [p for p in self._peasants(world) if not p.hidden and p.id not in self.rushers
                     and not isinstance(p.order, (Build, Repair, Salvage)) and p.constructing is None and not self._answering(p)]
            if not spare:
                break
            drafted = min(spare, key=lambda p: dist(p.pos, start))
            self.rushers.append(drafted.id)
            self.rush_drafted += 1
            self.note(world, f"rush: drafted peasant {drafted.id}")
        if not self.rushers:
            if self.rush_drafted >= profile.rush_tries:
                self._end_rush(world)  # every try spent and none of them left alive
            return  # nobody to spare this tick (all of them building, mending or answering a raid): look again next one
        post = self._standable(world, self._behind(guess, start, 4.0))
        for rusher in [world.units[i] for i in self.rushers]:
            if rusher.constructing is not None or isinstance(rusher.order, Build):
                continue
            site = self._rush_site(world, mine, start) if mine is not None and barracks else None
            if site is not None and world.can_afford(self.player, BUILDINGS[BuildingType.TOWER].cost) is None:
                world.build(rusher.id, BuildingType.TOWER, site)
                self.note(world, f"rush: tower at {site}")
            elif dist(rusher.pos, post) > 1.5:
                if not rusher.orders or rusher.path_goal is None:
                    world.move([rusher.id], post)
            else:
                world.hold([rusher.id])  # there, and waiting: off the gatherer policy

    def _end_rush(self, world: World) -> None:
        """The rush is done or given up: its builders go back to work and its price is no longer held."""
        self.rush_over = True
        self.rushers = []
        self.note(world, "rush: over")

    # -- Training -------------------------------------------------------------------

    def _training(self, world: World) -> None:
        player = self.player
        army = self._army(world)
        halls = self._halls(world)
        # Peasants come first only while there is something to defend them with.
        # Raiders killing workers is exactly the moment the hall wants to replace
        # them, and replacing them is what pays for the soldiers that would stop
        # the raid — bases have been lost at sixteen workers, four thousand gold
        # and no army at all.
        rebuilding = (len(army) < self.profile.soldiers_before_workers
                      and any(b.info.trains and b.type is not BuildingType.TOWN_HALL
                              for b in world.player_buildings(player, done=True)))
        if not rebuilding:
            target = self._worker_target(world)
            peasants = len(self._peasants(world))
            for hall in halls:
                if peasants + sum(len(h.queue) for h in halls) >= target:
                    break
                if len(hall.queue) < 2 and world.can_train(hall, UnitType.PEASANT) is None and self._affordable(world, world.unit_info(player, UnitType.PEASANT).cost):
                    world.train(hall.id, UnitType.PEASANT)
        counts = {t: sum(1 for u in army if u.type is t) for t in UnitType}
        targets = self._army_targets(world)
        wishes: list[tuple[float, UnitType, Building]] = []
        for building in world.player_buildings(player, done=True):
            if not building.info.trains or building.type is BuildingType.TOWN_HALL:
                continue
            if building.rally is None and halls:
                world.set_rally(building.id, self._front_point(world, halls[0]))
            if building.research is not None or len(building.queue) >= 2:
                continue
            wish = self._choose_unit(building, counts, targets)
            if wish is not None:
                wishes.append((*wish, building))
        # The unit the army is shortest of has first claim on the bank. Buying
        # whatever was affordable at the moment instead had the stables turn out
        # a scout every time the knight it wanted was a few hundred gold away:
        # fifteen scouts to eight knights, in a posture that asked for knights.
        gold, lumber = self._spendable(world)
        for _gap, choice, building in sorted(wishes, key=lambda w: -w[0]):
            cost = world.unit_info(player, choice).cost
            if gold >= cost.gold and lumber >= cost.lumber and world.can_train(building, choice) is None:
                world.train(building.id, choice)
                counts[choice] = counts.get(choice, 0) + 1
            elif not self.profile.save_for_wanted:
                continue
            gold -= cost.gold
            lumber -= cost.lumber

    def _army_targets(self, world: World) -> dict[UnitType, float]:
        """Shares of the army to aim for, shifted towards counters of what the enemy is remembered fielding."""
        plan = dict(self.profile.army_plan or ARMY_PLANS[world.players[self.player].race])
        if not self.profile.siege:
            plan.pop(UnitType.CATAPULT, None)
        if not self.profile.clerics:
            plan.pop(UnitType.CLERIC, None)
        # A catapult out-ranges everything in the game and hits buildings for half
        # again; a healer makes every other soldier last longer. Both are worth
        # more to an army that has to break into a defended base than the race's
        # own plan allows, so the profile can overrule it.
        for unit_type, share in ((UnitType.CATAPULT, self.profile.siege_share),
                                 (UnitType.CLERIC, self.profile.cleric_share)):
            if share > 0 and unit_type in plan:
                rest = sum(v for t, v in plan.items() if t is not unit_type) or 1.0
                plan = {t: (share if t is unit_type else v * (1.0 - share) / rest) for t, v in plan.items()}
        total = sum(plan.values())
        if total > 0:
            plan = {t: share / total for t, share in plan.items()}
        seen = self.remembered()
        archers = seen.get(UnitType.ARCHER, 0.0)
        knights = seen.get(UnitType.KNIGHT, 0.0)
        melee = sum(seen.get(t, 0.0) for t in _MELEE_TYPES)
        total = archers + melee
        # Answer shooters with whatever closes the distance, in proportion to how
        # many of them there are. The old rule only fired when archers outnumbered
        # everything else two to one, which no race on this map ever fields — so
        # against the Elves, who are half archers and the matchup this brain loses
        # most, it never fired at all.
        if total > 0:
            excess = archers / total - self.profile.counter_from
            if excess > 0:
                swing = min(0.3, excess * self.profile.counter_strength)
                _shift(plan, {UnitType.FOOTMAN: -swing, UnitType.SCOUT: swing / 2,
                              UnitType.KNIGHT: swing / 2})
        if knights >= 3:
            _shift(plan, {UnitType.SCOUT: -0.075, UnitType.KNIGHT: -0.075, UnitType.FOOTMAN: 0.075, UnitType.ARCHER: 0.075})
        return plan

    def _choose_unit(self, building: Building, counts: dict[UnitType, int],
                     targets: dict[UnitType, float]) -> tuple[float, UnitType] | None:
        """What *building* should train next and how short of it the army is: ``(gap, unit)``, affordable or not."""
        soldiers = sum(counts.values())
        if building.type is BuildingType.STABLES and self.profile.scout and counts.get(UnitType.SCOUT, 0) < 1:
            return math.inf, UnitType.SCOUT
        best: tuple[float, UnitType] | None = None
        for unit_type in targets:
            if unit_type not in building.info.trains:
                continue
            share = counts.get(unit_type, 0) / soldiers if soldiers else 0.0
            gap = targets[unit_type] - share
            if self.profile.strict_plan and gap < -STRICT_SLACK:
                continue
            if best is None or gap > best[0]:
                best = (gap, unit_type)
        return best

    def _research(self, world: World) -> None:
        if not self.profile.research:
            return
        player = world.players[self.player]
        buildings = world.player_buildings(self.player, done=True)  # nothing changes until the one order below
        for wanted in self._research_order():
            if wanted in player.upgrades or not RACES[player.race].upgrade_allowed(wanted):
                continue
            for upgrade in with_prerequisites(player.upgrades, wanted):
                cost = UPGRADES[upgrade].cost
                for building in buildings:
                    if upgrade in building.info.researches and world.can_research(building, upgrade) is None and self._payable(world, cost):
                        world.research(building.id, upgrade)
                        return

    # -- Military -------------------------------------------------------------------

    def _front_point(self, world: World, hall: Building) -> Point:
        """Where the army waits: between the hall and whoever is coming."""
        enemy_halls = [record.center for record in self._known_enemy_buildings(world)]
        towards = min(enemy_halls, key=lambda c: dist(c, hall.center)) if enemy_halls else (world.width / 2, world.height / 2)
        hx, hy = hall.center
        away = dist((hx, hy), towards) or 1.0
        return self._standable(world, (hx + (towards[0] - hx) / away * 6, hy + (towards[1] - hy) / away * 6))

    @staticmethod
    def _standable(world: World, point: Point) -> Point:
        """The nearest ground a unit can be told to walk to.

        Six tiles towards the enemy is a fine place for an army to wait until a
        farm is standing on it, at which point a Move there is an order the unit
        can never finish: it paths as close as it can and stops, for good. Fuzz
        catches that as a stalled unit.
        """
        x, y = int(point[0]), int(point[1])
        if world.in_bounds((x, y)) and world.passable(x, y):
            return point
        for ring in range(1, 9):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    tile = (x + dx, y + dy)
                    if world.in_bounds(tile) and world.passable(*tile):
                        return tile_center(tile)
        return point

    def _threats(self, world: World) -> list[Unit]:
        own = world.player_buildings(self.player)
        if not own:
            return []
        out = []
        for unit in self._enemies(world):
            if unit.info.damage == 0 and unit.is_worker:
                continue
            if any(dist(unit.pos, b.center) < 9.0 for b in own):
                out.append(unit)
        return out

    def _military(self, world: World) -> None:
        army = self._army(world)
        self._send_scout(world, army)
        busy = set(self.scouts) | set(self._raid(world, army))
        army = [u for u in army if u.id not in busy]
        # A couple of soldiers never leave. Riders picking off peasants cost more
        # than they are worth to chase with an army that is somewhere else, and a
        # base with nothing in it is what an early raid is looking for.
        guards, army = army[:self.profile.guards], army[self.profile.guards:]
        threats = self._threats(world)
        if threats and not (self.attacking and strength(world, threats)
                            < self.profile.ignore_raid_ratio * strength(world, army)):
            if self._outmatched_at_home(world, guards + army, threats):
                self._fall_back(world, guards + army, threats)
            else:
                self._defend(world, guards + army, threats)
            return
        if self._strike_towers(world, guards + ([] if self.attacking else army)):
            return
        self._post(world, guards)
        hall = self._hall(world)
        mine = strength(world, army)
        if self.attacking:
            # Judge a push by how it is going, not by how big the enemy looks from
            # where the army happens to be standing. Estimating the defence again
            # each pass walks the army home the moment a tower comes into view, and
            # then straight back out once it is out of view again; an army that
            # oscillates like that never fights at all.
            if len(army) < 3 or mine < self.profile.retreat_ratio * self.commit_strength or self._outmatched_at_target(world, army, mine):
                self.attacking = False
                self.regroup_until = world.time + self.profile.regroup_seconds
                self.note(world, f"withdraw at {mine:.0f} of {self.commit_strength:.0f}")
                if hall is not None:
                    home = self._front_point(world, hall)
                    for unit in army:
                        world.move([unit.id], self._muster(world, home, unit))
                return
            targets = self._attack_targets(world)
            if targets and (self.target is None or not self._still_there(world, self.target)):
                self.target = min(targets, key=lambda t: dist(t, hall.center if hall is not None else army[0].pos))
            if self.target is None:
                return
            # Reinforcements walk to the same place, so the push grows instead of
            # trickling. A soldier crossing the map alone arrives alone and dies
            # alone, so the ones still at home wait until there are enough to travel
            # together; the ones already at the front simply rejoin the fight.
            idle = [u for u in army if not u.orders]
            arrived = [u.id for u in idle if dist(u.pos, self.target) <= 12.0]
            if arrived:
                world.attack_move(arrived, self.target)
            waiting = [u for u in idle if dist(u.pos, self.target) > 12.0]
            if len(waiting) >= self.profile.reinforce_group:
                world.attack_move([u.id for u in waiting], self.target)
            elif waiting and hall is not None:
                point = self._front_point(world, hall)
                for unit in waiting:
                    if dist(unit.pos, point) > 4.0:
                        self._send_to_muster(world, point, unit)
            return
        if world.time < self.regroup_until or self._push_waits(world):
            self._gather(world, army, hall)
            return
        targets = self._attack_targets(world)
        origin = hall.center if hall is not None else (army[0].pos if army else None)
        if not targets or origin is None:
            self._gather(world, army, hall)
            return
        target = min(targets, key=lambda t: dist(t, origin))
        theirs = self._defenders_near(world, target)
        care = self._caution(world)
        if len(army) < self.profile.min_army * care:
            self._gather(world, army, hall)
            return
        if mine >= self.profile.attack_ratio * care * theirs:
            self.attacking = True
            self.target = target
            self.commit_strength = mine
            self.note(world, f"attack {len(army)} strong ({mine:.0f} against {theirs:.0f})")
            world.attack_move([u.id for u in army], target)
        else:
            self._gather(world, army, hall)

    def _outmatched_at_target(self, world: World, army: list[Unit], mine: float) -> bool:
        """Whether the push, where it fights, faces more than ``abort_ratio`` times what it has left: the defenders
        in sight round what it walked at and the towers known to cover it, against the soldiers of the push that
        are there.

        The push is otherwise judged by what it has lost of itself, which lets it lose half an army to two towers
        and a barracks that keeps answering before it turns round.  This reads the fight itself, only once the
        army stands in it (an estimate made on the way walks an army home each time a tower drifts out of sight),
        and the regrouping that follows a withdrawal keeps it from walking straight back."""
        if self.profile.abort_ratio <= 0.0 or self.target is None:
            return False
        target = self.target
        there = [u for u in army if dist(u.pos, target) <= 12.0]
        if len(there) < 3:
            return False  # not there yet
        defenders = [e for e in self._enemies(world) if not e.is_worker and e.info.soldier and dist(e.pos, target) <= 12.0]
        theirs = strength(world, defenders) + _tower_strength(world, self.player, target, 9.0)
        return theirs > self.profile.abort_ratio * strength(world, there)

    def _push_waits(self, world: World) -> bool:
        """Whether a push is still held for the hour and the upgrades the posture times it with."""
        profile = self.profile
        if world.time >= profile.push_by:
            return False
        return world.time < profile.push_after or len(world.players[self.player].upgrades) < profile.push_upgrades

    def _still_there(self, world: World, point: Point) -> bool:
        """Whether anything of the enemy's is still standing where the push was aimed."""
        return any(dist(record.center, point) < 3.0 for record in self._known_enemy_buildings(world))

    def _home_point(self, world: World, hall: Building) -> Point:
        """Somewhere a soldier can actually stand next to the hall.

        A hall's centre is inside its own footprint, which is blocked ground: a
        unit sent there paths towards it and stops a tile short for good. Fuzz
        caught an archer stalled twenty seconds on a move of two thirds of a
        tile, which is what that looks like from the outside.
        """
        tile = world.free_tile_near(hall.rect, prefer=hall.center)
        return tile_center(tile) if tile is not None else self._front_point(world, hall)

    def _post(self, world: World, guards: list[Unit]) -> None:
        """Send the home guard back to the hall whenever it has nothing to do, and leave it at its post once it is
        standing there (:meth:`_send_to_muster`)."""
        hall = self._hall(world)
        if hall is None:
            return
        home = self._home_point(world, hall)
        for guard in guards:
            if guard.orders or dist(guard.pos, hall.center) <= 6.0:
                continue
            self._send_to_muster(world, home, guard)

    def _caution(self, world: World) -> float:
        """How much more careful to be than in a duel.

        Starting a fight in a free-for-all pays for itself only if it is won
        cheaply: everything spent on it is a gift to the players who stayed out.
        The posture that rates 1562 Elo one against one rates 1022 in a four
        player game without this, which is barely ahead of the brain it
        replaced — so every extra opponent buys back some of the caution.
        """
        bystanders = sum(1 for p in world.players if p.id != self.player and p.alive) - 1
        return 1.0 + self.profile.ffa_caution * max(0, bystanders)

    def _army_centre(self, world: World, army: list[Unit]) -> Point | None:
        if not army:
            return None
        return (sum(u.x for u in army) / len(army), sum(u.y for u in army) / len(army))

    def _gather(self, world: World, army: list[Unit], hall: Building | None) -> None:
        """Wait in one place. An army that trickles forward is an army that loses twice."""
        if hall is None:
            return
        point = self._front_point(world, hall)
        for unit in army:
            if unit.orders or dist(unit.pos, point) <= 4.0:
                continue
            self._send_to_muster(world, point, unit)

    def _muster(self, world: World, point: Point, unit: Unit) -> Point:
        """*point*, nudged so the whole army is not walking at one tile.

        Twenty soldiers sent to the same coordinate cannot all stand on it. The
        ones that cannot keep a Move order they are unable to finish and stop
        taking part in the game — fuzz reports it as a stalled unit.
        """
        angle = (unit.id % 12) / 12.0 * 2.0 * math.pi
        spread = 1.0 + unit.id % 3
        return self._standable(world, (point[0] + spread * math.cos(angle), point[1] + spread * math.sin(angle)))

    def _send_to_muster(self, world: World, point: Point, unit: Unit) -> None:
        """Send *unit* to its own place around *point*, and leave it alone once it stands there.

        Its place is nudged per unit and nudged again onto standable ground, so it can be several tiles from
        *point*: a soldier judged by its distance from *point* alone was ordered onto ground it was already
        standing on, every pass of the brain, for the rest of the match.  It finished the walk in one step,
        went idle, and was sent again; fuzz reads a unit ordered about once a second and never getting
        anywhere as a stalled unit, which is what it was (seed 81, an archer of a bred orc posture)."""
        post = self._muster(world, point, unit)
        if dist(unit.pos, post) > MUSTERED:
            world.move([unit.id], post)

    def _defenders_near(self, world: World, point: Point, radius: float = 12.0) -> float:
        """What is waiting at *point*: the soldiers we can see, the towers covering it,
        and half of whatever the enemy was last seen with but is currently hidden.

        Strength is linear in the number of like units, so an unseen soldier can
        simply be priced at what one of ours is worth.
        """
        owner = self._owner_of(world, point)
        # Every soldier they have defends their base, not only the ones standing
        # in it: an army that is out on the map when the scout looks is an army
        # that walks home the moment the attack starts. Counting only what is
        # near the target is how a push goes out against an estimate of twelve
        # and meets two hundred.
        theirs = [u for u in self._enemies(world)
                  if not u.is_worker and (owner is None or u.player == owner)]
        counted = sum(self.remembered(owner).values()) if owner is not None else sum(self.remembered().values())
        hidden = max(0.0, counted - len(theirs))
        seen = (strength(world, theirs) + _tower_strength(world, self.player, point)
                + 0.5 * hidden * self._typical_soldier(world))
        if world.time - self.last_seen(owner) > self.profile.stale_seconds:
            # Nobody has looked at them lately. An enemy nobody has looked at is not
            # an enemy of zero strength — assuming so is how an army of ten walks
            # into a defended base and dies. Until a scout says otherwise, credit
            # them with a game as good as ours, which means no attack goes out on
            # no information at all.
            seen = max(seen, self.profile.symmetry_prior * self._caution(world)
                       * strength(world, self._army(world)))
        return seen

    def _owner_of(self, world: World, point: Point) -> int | None:
        """Whose ground *point* is: the player owning the nearest building to it."""
        owned = self._known_enemy_buildings(world)
        if not owned:
            return None
        return min(owned, key=lambda record: dist(record.center, point)).player

    def _typical_soldier(self, world: World) -> float:
        """What one average soldier of ours is worth, as a yardstick for unseen enemies."""
        army = [u for u in self._army(world) if u.info.soldier]
        return strength(world, army) / len(army) if army else 20.0

    def _victim(self, world: World) -> int | None:
        """Which opponent to go after: the one we believe is weakest.

        With two players this is the only opponent there is. With three or four
        it is the whole game — walking at the nearest neighbour while a third
        player grows is how a free-for-all is lost by the one who started it.
        """
        seen = {record.player for record in self._known_enemy_buildings(world)}
        living = [p.id for p in world.players if p.id != self.player and p.alive and p.id in seen]
        if not living:
            return None
        return min(living, key=lambda p: sum(self.remembered(p).values()))

    def _attack_targets(self, world: World) -> list[Point]:
        """What is worth walking to: the weakest opponent's production, then anything of theirs."""
        wanted = (BuildingType.BARRACKS, BuildingType.STABLES, BuildingType.WORKSHOP,
                  BuildingType.CHURCH, BuildingType.TOWN_HALL)
        victim = self._victim(world)
        buildings = self._known_enemy_buildings(world)
        theirs = [record for record in buildings if record.player == victim] or buildings
        # A structure we have seen, we know the kind of; one razed while we were
        # not looking reads as unknown and stays a place worth walking to.
        production = [record.center for record in theirs
                      if getattr(world.buildings.get(record.id), "type", None) in wanted]
        if production:
            return production
        if theirs:
            return [record.center for record in theirs]
        seen = [u.pos for u in self._enemies(world)]
        # Under fog an army with no target simply stands at home until the clock
        # runs out. If nothing of theirs has been found, the place to go is the
        # ground we have not looked at.
        return seen or [self._unexplored_corner(world)]

    def _defend(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Send the soldiers at whatever is nearest our buildings. The peasants keep mining.

        Calling peasants to fight was measured twice — once only when the army
        was already winning, once whenever the army alone could not win — and
        both cost about 35 Elo against the brain that leaves them on the gold.
        They die, and the economy that would have replaced the soldiers dies
        with them.
        """
        point = min(threats, key=lambda u: min(dist(u.pos, b.center)
                                               for b in world.player_buildings(self.player))).pos
        self.attacking = False
        world.attack_move([u.id for u in army if not isinstance(u.order, Attack)], point)

    def _outmatched_at_home(self, world: World, army: list[Unit], threats: list[Unit]) -> bool:
        """Whether the attack on the base is more than the soldiers at home can meet (``defend_ratio``)."""
        if self.profile.defend_ratio <= 0.0:
            return False
        hall = self._hall(world)
        if hall is None:
            return False
        ours = strength(world, army) + _tower_strength_own(world, self.player, hall.center)
        return strength(world, threats) > self.profile.defend_ratio * ours

    def _fall_back(self, world: World, army: list[Unit], threats: list[Unit]) -> None:
        """Gather behind the hall, away from the attack, rather than walk into it one soldier at a time: the ones
        the barracks turns out join there, and the defence goes in together once it is a match."""
        hall = self._hall(world)
        if hall is None:
            return
        tx = sum(u.x for u in threats) / len(threats)
        ty = sum(u.y for u in threats) / len(threats)
        hx, hy = hall.center
        away = dist((hx, hy), (tx, ty)) or 1.0
        point = self._standable(world, (hx + (hx - tx) / away * 5.0, hy + (hy - ty) / away * 5.0))
        self.attacking = False
        for unit in army:
            if dist(unit.pos, point) > 3.0 and not (isinstance(unit.order, Move) and dist(unit.order.target, point) < 4.0):
                world.move([unit.id], self._muster(world, point, unit))

    def _send_scout(self, world: World, army: list[Unit]) -> None:
        """Keep one pair of eyes on the enemy: a rider if we have one, a peasant if not.

        Everything the brain decides about attacking rests on knowing what is
        over there, so a scout is cheap at almost any price — and one peasant
        is a much smaller loss than the army that would otherwise walk in blind.
        """
        if not self.profile.scout or world.time < self.profile.scout_from:
            return
        self.scouts = [i for i in self.scouts if i in world.units]
        if not self.scouts:
            riders = [u for u in army if u.type is UnitType.SCOUT]
            if riders:
                self.scouts = [riders[0].id]
            else:
                spare = [p for p in self._peasants(world)
                         if not p.hidden and p.carrying is None and not isinstance(p.order, (Build, Repair, Salvage))
                         and not self._answering(p)]
                if len(spare) > 3:
                    # Drafted with a harvest order in hand, the peasant keeps it:
                    # the ring move below is only given to a scout with nothing to
                    # do, and the gatherer policy refills an idle peasant before
                    # the next pass, so the peasant never goes and the brain knows
                    # nothing of the enemy until the enemy arrives. Sending it
                    # (stop it, keep it off the policy) was measured: 44% and 39%
                    # against Master for the two postures, against 55% blind. The
                    # engagement rule is tuned for not knowing, and given real
                    # sightings it waits while Master attacks; using them takes a
                    # different rule, not a scout. So the peasant stays home.
                    self.scouts = [spare[-1].id]
        targets = [record.center for record in self._known_enemy_buildings(world)]
        if not targets:
            targets = [self._unexplored_corner(world)]  # nothing found yet: go and look
        for scout_id in self.scouts:
            scout = world.units[scout_id]
            if scout.orders:
                continue
            # Circle the enemy base rather than standing in it, so the sighting stays fresh.
            centre = min(targets, key=lambda c: dist(c, scout.pos))
            angle = (world.time / 12.0) % (2 * math.pi)
            ring = (centre[0] + 7.0 * math.cos(angle), centre[1] + 7.0 * math.sin(angle))
            world.move([scout_id], self._standable(world, (min(max(ring[0], 1.0), world.width - 1.0),
                                                           min(max(ring[1], 1.0), world.height - 1.0))))

    # -- Combat ----------------------------------------------------------------------

    def _home(self, world: World) -> list[tuple[int, int, int, int]]:
        """The ground a tower would take from us: our halls and the mines they work."""
        halls = self._halls(world)
        mines = [m.rect for m in known_mines(world, self.player)
                 if any(rect_gap((m.x + m.size / 2, m.y + m.size / 2), h.rect) <= 10.0 for h in halls)]
        return [h.rect for h in halls] + mines

    def _home_towers(self, world: World) -> list[Building]:
        """Enemy towers we can see, standing or going up, whose fire reaches a hall of ours or a mine it works."""
        home = self._home(world)
        towers = []
        for record in self._known_enemy_buildings(world):
            tower = world.buildings.get(record.id)
            if tower is None or tower.type is not BuildingType.TOWER or not world.any_visible(self.player, tower.rect):
                continue
            if any(rect_gap(tower.center, rect) <= tower.info.range + tower.size / 2 for rect in home):
                towers.append(tower)
        return towers

    def _strike_towers(self, world: World, army: list[Unit]) -> bool:
        """Bring down a tower on our ground (WB-037): a young frame if the peasants and soldiers at hand can
        outpace its building, else the frame in its last ``strike_lead`` seconds, so the strike is there as it
        stands, fast enough to be done in ``strike_seconds``; whether anything was sent.

        A tower by the mine or the hall stops the gold for as long as it stands, and soldiers sent a few at a
        time die a few at a time. A peasant's blow does a point through its armour, so a dozen peasants take
        twelve points a second off it where the tower kills one of them every six seconds, and a frame gains
        only ten or twelve a second: a dozen peasants and a footman bring a young frame down before it stands,
        for nothing but the mining they miss. Not while enemy soldiers stand by it: the ordinary defence meets
        them first.
        """
        self.strikers = {i for i in self.strikers if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.strike_seconds:
            return False
        towers = sorted(self._open_towers(world), key=lambda t: (t.hp, t.id))
        fighters = [u for u in army if u.info.soldier]
        for tower in towers:
            armour = world.armor_of(tower)
            pace = 0.0  # what the strike takes off the tower a second
            for unit in fighters:
                pace += self._blows(world, unit, armour)
            for i in self.strikers:
                striker = world.units[i]
                if isinstance(striker.order, Attack) and striker.order.target == tower.id:
                    pace += self._blows(world, striker, armour)
            spare = sorted(self._free_peasants(world, miners=True),
                           key=lambda p: dist(p.pos, tower.center))[:self.profile.strikers_max]
            if tower.done:
                need = tower.hp / self.profile.strike_seconds
            else:
                info = tower.info
                left = info.build_time - tower.progress
                # Its growth, and its hit points spread over what is left of the building once they have walked over.
                need = (info.hp - max(1, info.hp // 10)) / info.build_time + tower.hp / max(1.0, left - WALK_OVER)
                if left > self.profile.strike_lead:
                    near = [p for p in spare if dist(p.pos, tower.center) <= 16.0]
                    reach = pace
                    for peasant in near:
                        reach += self._blows(world, peasant, armour)
                    if reach < need:
                        continue  # it stands whatever we do: meet it then
                    need, spare = math.inf, near  # everyone in reach: the sooner it falls, the sooner they mine again
                else:
                    need = tower.hp / self.profile.strike_seconds
            drafted: list[int] = []
            for peasant in spare:
                if pace >= need:
                    break
                drafted.append(peasant.id)
                pace += self._blows(world, peasant, armour)
            if drafted:
                world.attack(drafted, tower.id)
                self.strikers.update(drafted)
                self.note(world, f"strike tower {tower.id}{'' if tower.done else ' frame'} with {len(drafted)} peasants "
                                 f"and {len(fighters)} soldiers")
            idle = [u.id for u in fighters if not (isinstance(u.order, Attack) and u.order.target == tower.id)]
            if idle:
                world.attack(idle, tower.id)
            return True
        return False

    def _open_towers(self, world: World) -> list[Building]:
        """The towers on our ground with no enemy soldier standing by."""
        soldiers = [e for e in self._enemies(world) if not e.is_worker and e.info.soldier]
        return [t for t in self._home_towers(world) if not any(dist(e.pos, t.center) < 8.0 for e in soldiers)]

    def _answering(self, peasant: Unit) -> bool:
        """Whether *peasant* is out answering a rush, so no other job takes it."""
        return peasant.id in self.hunters or peasant.id in self.strikers

    def _free_peasants(self, world: World, *, miners: bool = False) -> list[Unit]:
        """Peasants a rush's answer may draft: not building and on no other errand; with *miners*, the ones
        inside a mine too, who obey as they come out with their load."""
        return [p for p in self._peasants(world) if p.constructing is None and (miners or p.inside is None)
                and not isinstance(p.order, (Build, Repair, Salvage)) and p.id not in self.scouts and p.id not in self.rushers
                and p.id != self.prospector and not self._answering(p)]

    @staticmethod
    def _blows(world: World, unit: Unit, armour: int) -> float:
        """What *unit* takes off something wearing *armour*, a second."""
        return max(1, world.damage_of(unit) - armour) / unit.info.period

    def _hunt_builders(self, world: World) -> None:
        """A lone enemy peasant inside our base is a tower or a barracks about to go up by the hall or the mine: the
        peasants nearest it drop their work and kill it while it is still walking or waiting (WB-037).

        Once it is inside its frame nothing reaches it, and a tower's frame gains ten hit points a second, more than
        two footmen take off it; on the way in, a party of peasants settles it in a few seconds if it can catch it,
        so the party is drawn from where it will be. They go only where no enemy soldier is near, and are let go
        once it is dead, out of sight or out of the base.
        """
        self.hunters = {i: target for i, target in self.hunters.items()
                        if i in world.units and isinstance(world.units[i].order, Attack)}
        if not self.profile.hunt_party:
            return
        home = self._home(world)
        if not home:
            return
        enemies = self._enemies(world)
        soldiers = [e for e in enemies if not e.is_worker and e.info.soldier]
        intruders = {e.id: e for e in enemies if e.is_worker and min(rect_gap(e.pos, rect) for rect in home) <= 8.0
                     and not any(dist(s.pos, e.pos) < 6.0 for s in soldiers)}
        gone = [i for i, target in self.hunters.items() if target not in intruders]
        if gone:
            world.release_workers(gone)
            for i in gone:
                del self.hunters[i]
        for prey in intruders.values():
            want = self.profile.hunt_party - sum(1 for target in self.hunters.values() if target == prey.id)
            if want <= 0:
                continue
            # A chase at the same speed never closes: the ones ahead of it, where it will be in a few seconds, meet it.
            ahead = (prey.x + 2.5 * prey.vx, prey.y + 2.5 * prey.vy)
            free = sorted((dist(p.pos, ahead), p.id) for p in self._free_peasants(world) if dist(p.pos, prey.pos) <= 12.0)
            drafted = [i for _, i in free[:want]]
            if drafted:
                world.attack(drafted, prey.id)
                for i in drafted:
                    self.hunters[i] = prey.id
                self.note(world, f"hunt peasant {prey.id} with {len(drafted)}")

    def _withdraw_if_hurt(self, world: World, unit: Unit) -> bool:
        """Walk a nearly-dead soldier out of reach. A body that lives is damage next fight.

        Returns whether the unit is out of the fight, so the caller stops
        giving it targets.
        """
        profile = self.profile
        if unit.id in self._hurt:
            if unit.hp >= profile.rejoin_hp * unit.max_hp:
                self._hurt.discard(unit.id)
                return False
            return True
        if unit.hp >= profile.retreat_hp * unit.max_hp:
            return False
        if not any(e.info.damage and dist(e.pos, unit.pos) < world.range_of(e) + 2.0 for e in self._enemies(world)):
            return False  # nothing is shooting at it; no reason to leave
        hall = self._hall(world)
        if hall is None:
            return False
        self._hurt.add(unit.id)
        world.move([unit.id], self._muster(world, self._home_point(world, hall), unit))
        return True

    def _raid(self, world: World, army: list[Unit]) -> list[int]:
        """Riders sent at the peasants. Economy damage costs the enemy the whole game,
        not just the units lost, and the army never misses two scouts."""
        if not self.profile.raid:
            return []
        self.raiders = [i for i in self.raiders if i in world.units]
        spare = [u for u in army if u.type is UnitType.SCOUT and u.id not in self.raiders]
        while len(self.raiders) < self.profile.raiders and spare:
            self.raiders.append(spare.pop().id)
        prey = [u.pos for u in self._enemies(world) if u.is_worker]
        if not prey:
            return list(self.raiders)
        for raider_id in self.raiders:
            rider = world.units[raider_id]
            if rider.orders:
                continue
            world.attack_move([raider_id], min(prey, key=lambda p: dist(p, rider.pos)))
        return list(self.raiders)

    def _combat(self, world: World) -> None:
        """Take the nearly dead out of the fight. The fighting itself is the model's."""
        release_arrived(world, self.player)
        self._hunt_builders(world)
        if not self.profile.retreat_wounded:
            return
        army = [u for u in world.player_units(self.player) if not u.is_worker and u.info.soldier]
        if not army:
            return
        if not self._enemies(world):
            self._hurt.clear()
            return
        for unit in army:
            self._withdraw_if_hurt(world, unit)


class RaceBrain:
    """A player whose posture is its race's own: bred brains are bred per race, so which one plays is settled at the
    first pass, once the world says whom this player leads.  A race with several postures draws one from the map's
    seed and the player's seat, as Master draws its three."""

    def __init__(self, player: int, postures: Mapping[Race, Sequence[ProProfile]], seed: int = 0,
                 by_layout: Mapping[tuple[Race, Layout], Sequence[ProProfile]] | None = None) -> None:
        self.player = player
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
            self.brain = ProBrain(self.player, options[(self.seed + self.player) % len(options)])
        self.brain.think(world, rng)
