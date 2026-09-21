# Hands off a peasant its player is using

Asked for on 2026-09-20: *"Worker auto-tasks are too aggressive in taking
workers. Especially when sending a worker to another side of the map, e.g.
tower rush, it's annoying when they auto mine. Make behavior different on how
far from home and how much manual control worker got recently."*

Send a peasant across the map to raise a forward tower, and the moment the
tower stood `worker_ai.assign_idle_workers` claimed it and walked it home to a
mine. The player's intention, overruled without a word. Two axes were asked
for, and they are one rule here: **how lately its player had the worker in hand
is the clock, and how far from home it stands is how long the clock runs.**

## The rule

`Unit.commanded` is the simulation time its player or its brain last had this
worker in hand — `None` while it is nobody's but the policy's, which is how
every peasant starts.

It is set in two places and cleared in two:

| | |
|---|---|
| `World._issue(..., manual=True)` | the default, because an order comes from a player or a brain: every `@recorded` command stamps the units it touches |
| `World._stood_down` | the last order given runs out and the worker stands: the window runs **from here**, not from the order, or the walk across the map and the tower at the end of it would spend it before the peasant ever stood still |
| `World._issue(..., manual=False)` | the policy's own placement: the worker it claims is no longer anybody's to hold |
| `World.release_workers` | a caller handing a peasant back on purpose, which is how the brains do it |

`worker_ai.manual_hold(distance)` turns the safe walk to the nearest depot —
the same depot distance field the gatherers route and the salvage policy reach
by, never a straight line to a point — into the seconds the policy keeps its
hands off:

| | |
|---|---|
| `HOME_REACH` | **8 tiles.** Inside the base the hold is **nothing at all**. A peasant that put up a farm beside the hall and went straight back to the mine is what everybody wants and what the whole policy is for; the complaint was never about it, and this is where the brains do nearly all of their commanding. |
| `AUTO_REACH` | **24 tiles**, the same reach `SALVAGE_REACH` uses for the same idea: past here a peasant is plainly away on business of its own. |
| `MANUAL_HOLD` | **45 seconds**, the hold at `AUTO_REACH` and beyond, including on ground no safe walk leads home from. Long enough to place a second tower without the policy interfering; short enough that a peasant its player forgot is not lost for the match. |

Between the two reaches the hold is a straight ramp: 11 s at 12 tiles, 22 s at
16, 34 s at 20.

**The axes are not independent and neither is a gate on its own.** A worker far
away that has been idle for a minute *is* taken — the memory of the command
fades, and a peasant that never works again is a bug of its own. A peasant
meant to stand for good is what Stop and Hold are for (`Unit.auto_work`), and
those are unconditional and already existed; this rule is the graduated middle
the binary switch was missing.

## What happens to a worker that finishes a job far from home

It stands where the player put it, for the hold. Then the policy takes it and
it walks home and works. Standing for ever was never on the table: the
automatic gatherer is the whole reason idle peasants earn anything.

A worker holding cargo is the one exception the gate is placed after: a load in
hand goes home whoever sent it for it. It then stands down at the depot, where
the walk home is nothing and the hold is nothing, and goes back to work at
once.

`rebalance_workers` needed no change — it only ever moved a `Harvest` the
policy `placed`, and by construction such a worker's `commanded` is `None`.

## The wire and the save

`commanded` is part of the match: it round-trips through `World.to_dict` /
`from_dict` (a save from before it reads as `None`, which is the old
behaviour), and it survives replays because every stamp is set inside a
`@recorded` World method or inside the step.

It does **not** travel to a rival. `authority.STRANGER_UNIT` masks it beside
`orders` and `home`: whose hand a peasant is in is an intention, and a seat is
told what a unit is doing, not what its owner means by it.

## What it cost

**The gatherers alone are untouched.** Twelve peasants on a mine and a wood,
three minutes, five seeds: 20,700 gold and 7,480 lumber, bit for bit what they
brought before. Nothing commands a worker there, so nothing can hold one.

**The brains lean on this policy for their whole economy**, which was the real
risk. They turn out to command peasants almost entirely inside the base —
farms, barracks, repairs — which is exactly where `HOME_REACH` makes the hold
zero; their far-flung peasants (the tower rush's builders, the prospector) were
already opted out by `world.hold` and `world.release_workers`, which the
brains had for their own reasons. Measured, per player over five minutes and
six seeds, against the same code with the window switched off:

| | gold | lumber | idle peasant share |
|---|---|---|---|
| Hard, window on | 22,408 | 6,025 | 2.2% |
| Hard, window off | 22,442 | 5,967 | 1.8% |
| Master, window on | 24,267 | 6,208 | 11.0% |
| Master, window off | 24,150 | 6,083 | 8.6% |

And the ladder is unmoved. `tools/arena.py ladder --agents hard,pro --seeds 40`
(80 matches): pro 1078 (1044..1118) against 1088 (1048..1125) before. All five
difficulties over 24 seeds (192 games each, Medium anchored at 1000):

| | grandmaster | master | hard | medium | easy |
|---|---|---|---|---|---|
| with the window | 1594 | 1350 | 1230 | 1000 | 550 |
| before | 1530 | 1351 | 1248 | 1000 | 521 |

Every one of those sits inside the other's 90% interval.
`tools/ai_report.py --seeds 3 --decide 0` is identical either way: the scripted
opening wins 2 of 3 against Easy and none against Medium, Hard, Master or
Grandmaster.

**A first shape that did cost something**, kept here because it is the argument
for `HOME_REACH`: a hold that ramped from zero with the square of the distance
(no home radius, 45 s at 24 tiles) gave a peasant that built a farm eight tiles
out a five-second pause. Over a Medium brain's four minutes that showed up as
12.33 peasants where the same twelve seeds gave 12.67, and it tipped two
otherwise-green slow tests. With `HOME_REACH` the same sweep is
`[14, 12, 13, 13, 14, 12, 12, 13, 12, 11, 14, 12]` on both — identical, seed for
seed.

## Tests

`tests/warband/test_worker_ai.py`, the last section. The reproduction is
`test_a_peasant_that_raised_a_forward_tower_keeps_its_post`: the walk across
the map, the tower, and the policy leaving the builder on its post. Beside it,
a plain move to the far side (`..._is_not_walked_home_to_a_mine`), the hold
running out and a forgotten peasant going back to work, a peasant ordered
beside the hall going straight back to work, the ramp's shape at its named
distances, and the save and snapshot round trip.
