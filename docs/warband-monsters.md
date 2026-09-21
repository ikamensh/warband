# Warband — the neutral creatures

The artwork is `warband/art/monsters.py` and
[what was painted and how](warband-monsters-art.md).  This note is the other half: the rules, where the
camps go on the map, and what the computer players do about them.

## Why camps exist

`docs/balance.md` measures the standing equilibrium as `mass` 77 % and `turtle` 76 % and nothing else:
sitting at home and massing is dominant, and every soldier bought before the timing push is pure cost
until it goes out.  A camp is somewhere to spend an army at minute four that is not suicide into towers.
That is the tuning target — **creeping has to be a tempo investment, not a toll**.  If players route
round the camps, nothing has changed and the feature has failed.

## The neutral seat

`Building.player` was already `int | None` (a gold mine is nobody's), but `Unit.player` is a plain `int`
and `self.players[u.player]` is read on every step, so a `-1` sentinel would quietly answer with the last
real seat — exactly the silent fallback this repository forbids.  So the wilds are **a seat of their
own**, appended after the playing ones:

* `World.seats` is how many seats are *playing*; `len(world.players)` is one more.  Everything that
  means "a seat in the match" reads `world.seats`.
* `World.neutral` is that seat's number, and it is what every creature and every lair carries as its
  `player`.  `Player.neutral` marks it.
* It is left out of **victory and elimination** (`_check_elimination` walks `players[:seats]`), out of
  the **fog** (its `visible` and `explored` grids are all ones and `update_vision` leaves them alone:
  a creature decides nothing from a fog grid, and painting discs for it would cost a pass a tick), out
  of the **last-stand reveal**, out of the **gatherer policy**, out of the **league's tallies**
  (`Telemetry` keeps one column per playing seat), and out of the **online authority** — no client can
  name it as its own seat, and a snapshot blanks its purse and memory exactly as it blanks a rival's.
* It has no purse, no supply, no research, no plans and no brain.

Everything else already worked: `_hit`, `_alarm`, `_remove_unit` and `_tally_kill` index `self.players`
by a unit's owner, and now find a real record there.

## The camp

`warband/sim/camps.py`.  A camp is a **lair** (`BuildingType.LAIR`) with its guards placed round it when
the map is drawn.  It **resets**; it does not stream.  A den that emitted units would either eat an army
during the fight, with no decision in it, or trickle so slowly that clearing it is beating down an
undefended building.  Three rules:

* **They rouse together** (`CAMP_WATCH`, 7 tiles).  Anything of a playing seat that comes that near the
  lair sends *every* guard at it at once.  Pulling one wolf at a time and whittling the camp down is the
  cheese this exists to stop, and shared aggro — not a spawn timer — is what stops it.  A creature picks
  no fight of its own at all: `_idle`'s auto-acquire is off for the wilds, or a guard would answer
  whatever came into its own sight and could be pulled out from beyond the camp's watch.  Being hit still
  answers (`_hit`'s retaliation), and a guard struck in the last three seconds makes the camp look as far
  as one could be sent, because a catapult outranges every one of them.
* **They leash to the camp** (`CAMP_HOLD`, 11 tiles).  A guard chased or kited past that breaks off and
  walks back to its post.  The camp's own hold is the leash: a roused guard's `home` is cleared, because
  the six tiles `LEASH` gives an idle chase are shorter than a camp is wide.
* **The camp resets** (`CAMP_CALM` 8 s, then `CAMP_REGEN` 10 hp/s and one guard back every
  `CAMP_RESPAWN` 25 s).  Left alone, the wounded mend and the lair sends the fallen out again.

So the decision is crisp: clear the whole camp, **lair included**, in one committed push and it is yours
for good; break off half way and you paid units for nothing.

The lair is the payout as well as the anchor.  Its hoard is its `Building.gold`, paid whole to whoever
brings it down (`World._hoard`, beside `_plunder`).  It wears a building's **fortified** armour, so a
siege stone lands on it at ×1.5 — which is what hands a catapult a job before the first walls, after its
price rise left it with none.

## The four

Each is chosen for a unit the balance data says is dead weight.

| creature | hp | dmg | armour | range | wind-up + cooldown | speed | what it rewards |
|---|---|---|---|---|---|---|---|
| **Dire Wolf** | 40 | 6 | 0 light | melee | 0.2 + 0.9 | 4.0 | nothing: the cheap minute-two camp |
| **Venom Spider** | 45 | 8 | 0 light | 5 | 0.4 + 1.6 | 2.2 | the **scout** — something you must close on is scout work, and a scout returns 610 gold per 1 000 spent today |
| **Troll** | 220 | 14 | 0 unarmoured, regen 8/s | melee | 0.45 + 1.4 | 1.9 | the **archer** — piercing lands ×1.5 on the unarmoured |
| **Stone Golem** | 170 | 18 | 2 heavy, splash 1.3 | melee | 0.7 + 2.5 | 1.3 | the **archer** again, by punishing a melee ball |

Two of those numbers are load-bearing and are not free to move:

* The troll is **unarmoured on purpose**.  Armour is flat subtraction with a floor of one, so a
  high-armour sponge would make an archer's arrow land for 1 and turn every camp into a knights-only
  check.  High hit points and no armour cost time and exposure instead.
* Its regeneration is **out of combat only** (`UnitInfo.regen`, gated by `Unit.struck` and `REGEN_CALM`).
  Continuous regeneration puts a hard floor under the damage needed to kill the thing at all, and with
  blows rolling 75–125 % a camp sitting at that floor is a coin flip.  Gated, a single archer plinking
  it every 1.65 s never lets the six seconds elapse, so the floor never exists.

The golem's slam (`World._slam`) catches every **enemy** around its mark, not its own side, unlike a
siege stone: a camp whose guards knocked each other down as they swung would clear itself, and the
lesson the slam teaches — do not walk a melee ball into it — lands either way.

## Where they go

`mapgen._camp_site` and `_guard`, beside `_natural_site`/`_third_site`/`_seam_site`.  A camp is placed
the way a deposit is: one canonical site in the first seat's cell, one copy per cell, so every seat faces
the same camp at the same remove from the same deposit and the audit's congruence still holds.  Its own
spacing is tighter than a deposit's (`_CAMP_SPACING`, 5), because a den that had to keep a mine's
distance from the dig it guards would not be guarding it.

**Only the contested deposits are guarded** — the third mines and the gold seam, never a seat's own mine
and never its natural.  That is the whole rule, and it is what the camps are for: the opening is
untouched, the expansion every build order needs is free, and the ground a seat has to leave home for is
held by something.  Leaving the naturals open is also the genuine choice the design wants: a safe poor
expansion or a guarded rich one.

Klondike gets no camps, because its expansion gold is inside a rock ring with gates rather than at a
`_third_site`: its walls are already its gate.  A camp is a **wish**, never a fault — a layout whose own
walls leave no room beside a dig gets an unguarded deposit, not a refused seed.  `mapgen.build(...,
wilds=False)` draws the same maps with nothing guarding them, which is how the ladder is measured both
ways.

## The computer players

**Workers** needed nothing: `worker_ai._navigation` blacklists the ground inside any *hostile* unit's
threat radius, and a creature is hostile to every playing seat, so peasants route round a camp for free.
What was added is that a brain **never expands onto guarded ground** (`ai.guarded`): a hall put up beside
a live camp is a hall whose peasants walk into the guards.

**Camps are not raids.**  `_threats` in both brains skips the wilds: a camp is leashed to its lair and
comes at nobody who has not walked into it, so answering one as a raid would march the army out at
ground it was never losing.  A lair is likewise kept out of `known_enemy_buildings`, or `_victim` would
pick the wilds as the weakest opponent and walk the army across the map at a den.

**Clearing one** is `ProBrain._creep` (and a plainer `Brain._creep`), taken between defending and the
push.  The whole army goes at once and stays until the lair is down.  A camp is priced at the most its
guards were ever *seen* to be worth (`_camp_strength`; a camp never grows, so the high-water mark is the
whole truth once it has been looked at) and never at less than `creep_prior` soldiers of ours — the floor
is what keeps two soldiers from strolling into a troll.  A push worn past `creep_abort` of what it set
out with gives up and leaves that camp alone for `creep_retry` seconds.

That last rule is the one worth writing down: **a camp that mends its wounded and calls its dead back
out of the den is a sink with no bottom** for a brain that feeds soldiers into it a few at a time.
`tools/creep_report.py` measures exactly that, as `trickle` — units lost to the wilds per lair cleared.

## What it measures at

`tools/creep_report.py`, 60 matches a side on Medium 64x48 across all five layouts (2026-09-21):

| agent | lairs cleared | creatures killed | own units lost | **trickle** | hoard |
|---|---|---|---|---|---|
| `pro` | 0.74 | 3.55 | 1.17 | **1.57** | 402 |
| `medium` | 0.94 | 4.14 | 1.45 | **1.54** | 512 |

Both brains creep, and neither feeds a camp: about one and a half soldiers spent per den torn down,
against a hoard of 400-500 gold and the deposit the den was sitting on.  The failure this number exists
to catch -- units lost climbing while lairs cleared stays near zero -- is not there.

On the ladder itself (`tools/arena.py ladder --agents hard,pro --seeds 40`, 80 matches each way), `pro`
scores **70.0 %** against `hard` with the deposits unguarded and **63.7 %** with the camps on them -- a
narrowing of about one and a half standard errors on 80 games, so the order is unchanged and the step
between the two settings is the step it was.  What does move is what the armies do: peak army 13 -> 17
for `hard` and 19 -> 21 for `pro`, kills 20 -> 24 and 28 -> 34, and a median match half a minute longer.
That is the point of the feature showing up in the telemetry: an army built before the timing push now
has somewhere to go.

A camp cleared *per seat per match* is under one because the median ladder match is 7.5 simulation
minutes long and a camp is not opened before `creep_from` at 2.5: the brains take the camps that are
worth the walk in the time they have, and go at the enemy otherwise, which is the decision the feature
is supposed to create rather than a toll it collects.

## Fuzz

`uv run python -u tools/fuzz.py --games 12 --monkey 4 --seed 81` (2026-09-21): **12 AI games, 1 failed;
4 monkey runs, 0 failed.** The one failure is seed 86, a peasant stuck twenty seconds on a `Deposit` on a
sixteen-seat map -- the pre-existing unit stall that was already filed, and nothing to do with the camps.
Seeds 82 and 92, which the same run failed on before, pass now: what failed them was the wilds counted
as a seat "alive with nothing left", which they always are.

The run before the fixes is worth recording, because fuzz found both real bugs in this branch and no
others: `tools/fuzz.py` handed *every* Player in `world.players` a brain, the wilds included, so a camp's
wolves were taking group attack-move orders from a ProBrain and walking off across the map (one was
reported stuck twenty seconds on a march to the far side of the world), and its own invariant then read
the wilds as a seat alive with nothing. `race_report` and `step_bench` seated them the same way.

## Verification

```sh
uv run python tools/creep_report.py --agents pro,pro --seeds 12      # the gate: can the brains creep?
uv run python tools/creep_report.py --agents medium,medium --seeds 12
uv run python tools/arena.py ladder --agents hard,pro --seeds 40     # the ladder, with camps on the maps
uv run pytest -q tests/warband/test_camps.py
uv run python tools/verify_camp.py docs/evidence/camps                # frames of a camp to look at
```
