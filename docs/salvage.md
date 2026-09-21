# Salvage

Asked for on 2026-09-20: *"Allow workers to salvage buildings — an action that
can damage an enemy building and return a random resource, automatically done
to ruins."*

Salvage is **Repair run backwards**, and it is built on repair's shape on
purpose: the same order-and-charge loop, the same pro-rata running total, the
same command card row. Repair spends resources to put hit points in; salvage
takes hit points out and pays resources for them.

`warband/sim/rules.py` holds the numbers and the two pure functions,
`warband/sim/model.py` the `Salvage` order and `World.salvage`,
`warband/sim/worker_ai.py` the automatic job on ruins,
`warband/ui/scene.py` the card button, and `tests/warband/test_salvage.py`
pins all of it down.

## The numbers

| | |
|---|---|
| `SALVAGE_RATE` | 8.0 hp/s out of a **ruin** — exactly the rate a peasant mends at |
| `SALVAGE_HELD_RATE` | 2.0 hp/s out of a building somebody **still holds** |
| `SALVAGE_CHUNK` | 10 hit points, paid out one chunk at a time |
| `SALVAGE_SHARE` | 0.25 of the building's whole price, over all of its hit points |

A farm costs 500 gold and 250 lumber and has 400 hit points, so tearing it
apart whole returns 187 — about 0.47 a hit point, or 3.75 a second out of a
ruin. That is roughly a third of what the same peasant earns at a gold mine, so
salvage is never work the mine and the trees give up; it is what a spare hand
does with loot lying on the ground.

**Why it is not a siege engine.** A catapult costs 900 and puts about fourteen
hit points a second into a building from seven tiles away. A salvaging peasant
costs 400 and takes two a second out of one its owner still holds, from arm's
length, with thirty hit points of its own. Per coin that is a third of the
catapult's damage with none of its range or hide: a peasant swarm cannot
profitably demolish a base. Salvage is still better than a peasant's fists
(which a fortified building's armour cuts to about 0.8 hp/s) — a crowbar should
beat a fist — and what it really adds is the payout.

**Why the payout is worth less than a repair.** Mending all of a building's hit
points costs half its price (`REPAIR_COST`); tearing them all out returns a
quarter. So no loop through salvage and repair ever makes money, in any
direction, and no build-and-salvage refund loop can exist even in principle.

**Value already broken stays broken.** The running total counts damage *from
full*, so a building bombarded to a sliver holds almost nothing left to
salvage: a farm with a tenth of its hit points left is worth 19, not 187. The
prize is a ruin still standing whole, which is what sends a peasant into a
rival's base rather than picking over a battlefield.

## The random resource

Each chunk comes out as **one** resource, drawn from `World.rng` — the stream a
save keeps and a replay restores — and weighted by what the building is made
of: `salvage_resource(info, roll)` gives gold when `roll * (gold + lumber) <
gold`. A farm of 500 gold and 250 lumber gives up gold two draws in three, so a
whole salvage is worth, on average, exactly a quarter of its gold and a quarter
of its lumber. Pulling materials out of the building that is actually there.

The draw **must** come from `World.rng`: a bare `random` call would put every
replay and every lockstep online match out of step. `test_a_salvage_replays_to_the_bit`
is the test that holds it there.

`salvage_yield` is the difference of two rounded-down running totals, the same
trick `repair_cost` uses, so a salvage is worth the same however many chunks it
is torn out in; rounded down rather than up, because it is a payout and not a
price.

## What it refuses, and what it does not

- **Your own buildings: refused.** The user did not ask for it and nothing needs
  it. A right-click on your own building already means Repair, so the two would
  sit on top of each other, and a mis-click that dissolved a town hall would be
  unforgivable. It also ends any argument about refund loops before it starts.
- **A gold mine: refused.** Nobody built it.
- **A site still going up: refused**, whoever owns it. Its materials are not in
  it yet, and its hit points are not the building's; cancel your own for the
  whole cost back, or knock a rival's down.
- **A building someone still holds raises their alarm**, the same `under_attack`
  a blow raises, on the same cooldown. A building dissolving in silence would be
  the worst kind of surprise. It also marks the owner as recently hit, so their
  brain answers it.
- **Salvaging a held building down razes it**: it counts on the razer's tally
  (`buildings_razed`, `destroyed_value`), on the owner's `buildings_lost`, and
  an orc's Plunder loots its share of the gold on top — razing is razing.
- **A ruin razed by salvage counts for nothing but the materials**, as razing one
  by force always has (WB-007).

## Reaching it

`Salvage` sits in the eighth card slot beside Repair, on a peasant's card only:
**V** in Classic and Modal (free in both, and not a global key), **X** in Grid
(slot 8 of Q W E / A S D / Z X C; Grid's own `V` is the idle soldier, which a
positional card never claims). It arms a pending mode like Repair: the status
line asks for the click and the button stands lit until the click or Esc. Every
refusal goes through `GameScene.attempt` into the status line.

A **right-click on a ruin** with peasants selected salvages it, and any soldiers
in the selection raze it as they always did. A right-click on a rival's
*standing* building still means attack: salvaging one is slow and dangerous, so
it stays a deliberate, armed choice.

Nothing about salvage is ever unavailable, so it needs nothing from
`warband/ui/tech.py`: no prerequisite, no padlock, no hourglass. It is always on
the card and the rules answer for each target.

## Ruins, automatically

`Building.abandoned` is a ruin: what a resigned or surrendered player leaves
behind in a match of three or more. `worker_ai.assign_idle_workers` picks one up
the way it picks up a harvest, and on the same terms:

- only an **idle** worker with `auto_work` on, so Stop and Hold park a peasant
  and a ruin next door does not call it back;
- **one hand and no more** per player (`_salvagers`), so the mine and the trees
  keep their crews; the hand goes back into the pool the moment the ruin is gone;
- only when the crew can spare somebody: at least `SALVAGE_CREW` (6) workers;
- only a ruin the player **remembers** (`_Building.ruin` in the worker
  knowledge, set when one is seen), whose working edge is safe ground within
  `SALVAGE_REACH` (24 tiles) of a depot, by the same distance field that places
  gatherers. A record of a ruin somebody razed since costs one wasted walk and
  is then forgotten — exactly what a remembered mine that ran dry costs.

`rebalance_workers` never touches a salvager: it moves only a harvest the policy
placed. The computer players get the ruin for free, because the policy runs for
every player; the brains were taught to leave a salvaging peasant alone rather
than pull it back to the mine. No brain deliberately salvages a rival's
*standing* building — that would be a strength claim, and this change makes
none.

## Online

`salvage` is a group order in the authority's contract, beside `repair`: the
authority holds its unit ids to the seat and the rules answer for the building.
The `salvage` event is private news (`PRIVATE_EVENTS`), since its amount is a
seat's own purse; what the building's owner learns is their own `under_attack`.
Live once a server rollout carries this Warband.
