"""Tunable postures for the stronger computer opponent.

The brain owns the decisions; this module owns the data the ladder and
breeding tools vary.  No match state is kept here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from warband.sim.rules import BuildingType, UnitType, Upgrade

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
    # Creeping: the one job an army has before the timing push.  docs/balance.md measures the standing
    # equilibrium as mass 77 % / turtle 76 %, which is to say that an army built before the push is pure
    # cost; a camp is somewhere to spend it that is not suicide into towers.
    creep: bool = True
    creep_from: float = 150.0          # no camp before this: the opening comes first
    creep_army: int = 6                # never walk at a camp with fewer soldiers than this
    creep_ratio: float = 1.5           # …nor without this much more strength than the camp is reckoned to have
    creep_prior: float = 4.0           # a camp nobody has looked at is priced at this many of our own soldiers
    creep_reach: float = 34.0          # tiles from home a camp has to be within to be worth the walk
    creep_abort: float = 0.55          # break off once the push has lost this much of what it set out with
    creep_patience: float = 150.0      # …or once the lair has stood this long under the army, whatever it has left
    creep_retry: float = 120.0         # …and leave that camp alone for this long
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
