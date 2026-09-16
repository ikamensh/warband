# Balance

How Warband's prices are read rather than guessed at: a league of postures
played headless, tallied, and turned into a payoff matrix, a usage table and
a list of pathologies. Nothing here is a judgement of taste; every number
is a count of something the simulation did.

## Why a league of postures and not a learner

The instinct is to train agents and watch what they abuse. Two things argue
against it here. The sim is deterministic and headless at about a
millisecond a step, so a thousand-game league costs an hour; a learner good
enough to find prices would need millions of games, and the first things it
would find are engine pathologies (the double-ordered barracks that bought
a build rate nothing else could, the gatherer policy that starved lumber)
rather than prices. And an exploit that needs reactions at twenty hertz is
not a balance problem for a game people play.

What the instinct gets right is that one scripted brain hides "never used":
Master never reaches a workshop, so catapults were untested on the ladder.
So the league is the one brain, `pro_ai.ProBrain`, under twelve settings of
its knobs that each commit to one way of playing — `warband/archetypes.py`:

| posture | commits to |
|---------|-----------|
| `pro` | the shipped Master: its race's own army plan |
| `rush` | out at three soldiers, footmen and archers, no expansion, no tech |
| `boom` | an early second hall, a big workforce, out at twelve |
| `mass` | five barracks a hall, out at fifteen |
| `turtle` | five towers, three guards, out at twelve only when clearly ahead |
| `footmen` | the line alone, with a smith up early for the blades |
| `archers` | four in five archers |
| `knights` | stables first, two in three knights |
| `raiders` | half scouts, four raiders on the enemy's peasants |
| `siege` | smith and workshop first, a third catapults, out at eight |
| `clerics` | a church first, a quarter healers |
| `noresearch` | Master that never buys an upgrade, to price the research path |

A posture is checked to be what its name says: the report prints what each
one fielded per game.

## Running it

```bash
uv run python tools/balance_report.py --seeds 8 --workers 5            # 12 postures, 1056 matches, about an hour
uv run python tools/balance_report.py --from docs/evidence/balance/league-1.jsonl
uv run python tools/balance_report.py --variant scale:knight.cost_gold=1.25 --seeds 4   # the same league under a price change
```

Every pair of postures plays every seed from both corners; the map size
cycles with the seed as on the AI ladder, and the two races are drawn per
map and pairing (tied to the corner, so both corners of a pairing are one
fair pair). Seeds start at 70 000, which nothing was tuned on. Every match
comes back with a `PlayerTally` per player (`warband/telemetry.py`): what
was trained, built and researched and when, what it cost, damage dealt and
taken, kills credited to whoever struck last and priced at what the victim
cost, and a per-minute row of bank, supply and army value. The league is
saved as JSON lines under `docs/evidence/balance/` and can be re-read
without replaying.

## Reading it

In this order:

1. **Pathologies.** Unspent bank at the end, share of minutes at the supply
   cap, matches that ran to the cap, minutes to the first soldier. A
   posture that cannot spend its money is a bug in the brain or the rules,
   and its losses say nothing about prices until it is fixed.
2. **The matrix and its equilibrium.** `balance.equilibrium` plays
   multiplicative weights against itself on the head-to-head matrix and
   averages: the mix a player who knew the matrix would choose. A posture
   with all the weight names an ingredient too cheap or a counter that is
   missing; one with none was not worth what it cost. Ratings and intervals
   come from the same Bradley-Terry fit as the ladder.
3. **Usage.** For every unit, building and upgrade: the share of
   player-games in which it was bought, how many a game, what was spent on
   it, the value it destroyed per thousand spent, value destroyed per value
   lost, and the mean minute of the first one. Something bought in every
   game that never earns back its cost is over-priced or under-powered;
   something never bought is either unreachable or not worth reaching.
4. **Races**, from the same games.

A proposed fix is a `scale:` variant — `scale:knight.cost_gold=1.25,tower.hp=0.8`
patches those numbers in every worker — and the league, or a subset of it,
is played again under it. Nothing under a few dozen games per pairing means
anything; the ladder's lesson applies here unchanged.

## The arithmetic before the games

Armour is a flat subtraction with a floor of one, which decides several
matchups before any posture plays. Seconds for one unit of the row to kill
one of the column, from `rules.py` alone:

|          | peasant | footman | archer | scout | knight | catapult |
|----------|--------:|--------:|-------:|------:|-------:|---------:|
| peasant  | 12.5 | 75.0 | 16.7 | 14.6 | 112.5 | 33.3 |
| footman  | 5.6 | 15.6 | 7.4 | 6.5 | 39.0 | 14.9 |
| archer   | 9.9 | 33.0 | 13.2 | 11.6 | 148.5 | 26.4 |
| scout    | 7.9 | 31.5 | 10.5 | 9.2 | 94.5 | 21.0 |
| knight   | 4.1 | 10.1 | 5.4 | 4.7 | 20.3 | 10.8 |
| catapult | 3.2 | 6.7 | 4.2 | 3.7 | 10.7 | 8.4 |

Weighted by cost (Lanchester's square law: an army's strength is its
numbers squared times hit points times damage rate), value destroyed per
value lost when a purse of the row fights the same purse of the column:

|          | peasant | footman | archer | scout | knight | catapult |
|----------|--------:|--------:|-------:|------:|-------:|---------:|
| footman  | 5.98 | 1.00 | 3.73 | 1.65 | 0.58 | 1.81 |
| archer   | 0.89 | 0.27 | 1.00 | 0.37 | 0.10 | 0.76 |
| scout    | 2.42 | 0.61 | 2.72 | 1.00 | 0.33 | 2.07 |
| knight   | 5.49 | 1.71 | 10.27 | 3.02 | 1.00 | 1.76 |
| catapult | 1.17 | 0.55 | 1.31 | 0.48 | 0.57 | 1.00 |

The knight wins per gold against every unit in the game, ten to one
against the archer: five damage against four armour is one point a shot,
so an archer needs ninety shots. The archer loses per gold to everything
but peasants; its range buys free shots during the approach, which the
table cannot see, but nothing buys back a ten-to-one exchange. The rules
table says archers and catapults wear knights down; the arithmetic says
they do not.

## The first league (2026-09-16)

Twelve postures, eight maps each way, 1,056 matches, 997 decided, median
8.5 sim-minutes. `docs/evidence/balance/league-1.jsonl`.

**Timing decides, not composition.** The top four are one brain that
differs only in when it walks out: `turtle` 79.5%, `mass` 76.7%, `boom`
71.6%, `pro` 69.3%. Master, which attacks at five soldiers, loses three
games in four to the postures that wait for twelve or fifteen, and the
equilibrium is turtle 43%, mass 29%, boom 28% with nothing else in it.
Every composition posture (`knights` 46%, `clerics` 43%, `archers` 38%,
`siege` 37%, `footmen` 30%, `raiders` 31%) attacks at Master's timing, so
what they measured first is one branch of the tree at the wrong minute.
`rush` at 37% says the early push has no edge: the first soldier stands at
2.6 minutes for every posture, and three of them lose to a base.

**Two brain bugs, found in the pathologies and fixed before any price.**
Lumber piled up — losers ended with 5,600 banked, turtle's losers 16,500,
and by minute fifteen the mean seat held 16,000 lumber against 1,500 gold —
because the chop rule only ever sent hands to the trees and the model's
policy places a peasant once. And producers bought whatever they could
afford at the moment of choice: the knights posture fielded fifteen scouts
to eight knights, the siege posture 3.7 catapults a game, because the
stables took a scout every time the knight was a few hundred gold away.
Both are fixed in `pro_ai.py` (`lumber_stock`, `save_for_wanted`). On the
ladder the fixes are worth nothing to Master's strength — `pro`, `pro-old`,
`pro-nostock` and `pro-nosave` all measured 48% to 52% against each other
over 288 games — which is what the ladder doc predicted: the first clash
decides Master's games, not the bank. They are kept because they fix what
they were written for: the postures field their plans, and losers no
longer sit on sixteen thousand lumber.

Two more things a posture needed before it could be measured: `early_tech`
names how many of a building to put up (one stables cannot turn out a
knights army: 36 footmen to 5 knights in a check match), and `strict_plan`
stops a producer once its type is past its share of the living army.

**Usage, before the fixes**, so read with the above in mind:

| unit | bought in | a game | value per 1,000 | trade |
|------|----------:|-------:|----------------:|------:|
| knight | 42% | 2.8 | 1,458 | 2.82 |
| archer | 83% | 15.6 | 1,037 | 1.56 |
| footman | 100% | 19.1 | 750 | 1.03 |
| catapult | 8% | 0.4 | 635 | 0.96 |
| scout | 90% | 12.4 | 610 | 0.75 |

The knight earns the most per gold and wins its exchanges nearly three to
one, as the arithmetic said, and is still bought in fewer than half the
games. The scout is bought twelve times a game and loses value, most of
them the filler purchases above. Towers stood in 82% of player-games,
1.6 a game, and destroyed 2.7 times their cost — 8% of all damage dealt
in the league came from towers — which is how a posture of five towers
and a late push came to sit at the top. Arrows were researched in nine
games of ten (the mill stands in every game from minute two), blades in
79% and 54%, plate in 77% and 35%, the race arts in 7% to 23%, siege
engineering in 3%. `noresearch` took 42.6% to Master's 69.3%: the research
path as a whole earns its price.

**Races:** elf 58.2%, human 51.7%, dwarf 44.9%, orc 44.9% over about 530
pairings each; the elves beat all three others at 59% to 63%. Orcs train
10% slower and dwarves walk 0.3 slower, and a game decided by who has more
at the first clash punishes both.

**Undecided:** 59 matches, `turtle` in 27 of them.

## The second league, on the fixed brain

The same 1,056 matches with the economy fixes and the postures that can
field their plans (`docs/evidence/balance/league-2.jsonl`; 993 decided).
The postures now are what their names say: `knights` trained 22 knights
a game, `siege` 5.9 catapults, `clerics` 11.6 healers, `raiders` 36 scouts.

| posture | score | Elo | against `pro` |
|---------|------:|----:|--------------:|
| `mass` | 77.3% | 1073 | 68.8% |
| `turtle` | 76.1% | 1063 | 56.2% |
| `pro` | 68.2% | 1000 | — |
| `boom` | 67.6% | 996 | 56.2% |
| `knights` | 65.3% | 979 | 50.0% |
| `archers` | 42.0% | 816 | 31.2% |
| `noresearch` | 39.8% | 800 | 25.0% |
| `clerics` | 38.6% | 792 | 25.0% |
| `rush` | 36.4% | 776 | 12.5% |
| `siege` | 34.7% | 764 | 6.2% |
| `raiders` | 27.8% | 713 | 18.8% |
| `footmen` | 26.1% | 699 | 0.0% |

The equilibrium is `mass` 61%, `turtle` 39%, nothing else. Two readings
changed and one did not:

* **A knights army is as good as Master's mixed one** at the same timing
  (50% head to head, up from 12.5% when it could not field its plan), beats
  `boom` 62.5% and every composition posture 75% to 94%, and loses only to
  the later pushes. Knights earned 1,340 per 1,000 spent and traded 2.7 to
  1; the unit that is supposed to wear them down, the archer, took 18.8%
  against them. A single branch of the tree that matches the whole tree
  has no counter, which is what the arithmetic said before any game was
  played.
* **The siege path does not work even when it survives.** Holding behind
  three towers until the stones were ready, `siege` still took 6% against
  Master, 19% against `mass` and `turtle`. Catapults earned 650 per 1,000
  and traded 0.97; the workshop stood in 16% of player-games at minute 6.2.
  Nobody who was not made to reach it did.
* **Timing still decides.** `mass` and `turtle` beat everything, `rush`
  beats nothing, and towers destroyed 2.5 times their cost in 83% of
  player-games.

Races: elf 55.6%, human 55.2%, dwarf 46.0%, orc 43.0%. Orcs lose to elves
35% and to humans 40%; their 10% slower training is the whole race in a
game decided by who has more at the first clash.

## Price experiments

Six postures (`pro`, `mass`, `turtle`, `knights`, `archers`, `siege`) on the
league's first four maps, both corners, 120 matches per rulebook, against
the same 120 of the second league. Forty games per posture: about eight
points of noise on a score, seventeen on a single cell. The usage columns
are over 240 player-games and are the steadier readings.

| rulebook | `knights` | `archers` | `siege` | `turtle` | knight trade | archer vs knights | tower trade | towers bought in |
|----------|----------:|----------:|--------:|---------:|-------------:|------------------:|------------:|-----------------:|
| standard | 62.5% | 22.5% | 7.5% | 72.5% | 2.53 | 0% | 7.5 | 86% |
| tower damage 8 → 6 | 57.5% | 20.0% | 10.0% | 75.0% | 2.51 | 12% | 5.4 | 86% |
| tower 700 → 1,050 | 60.0% | 15.0% | 12.5% | 77.5% | 2.71 | 0% | 4.0 | 68% |
| knight 900 → 1,000 | 42.5% | 25.0% | 12.5% | 75.0% | 1.82 | 25% | 10.2 | 86% |
| knight 900 → 1,000 and archer 5 → 6 damage | 47.5% | 30.0% | 10.0% | 77.5% | 2.02 | 38% | 8.2 | 86% |
| catapult 1,200 → 875 and +25% hp, workshop 1,400 → 980 | 55.0% | 17.5% | 15.0% | 75.0% | 2.00 | 12% | 8.6 | 86% |

(The knight rows read 900 and 1,000 for gold and lumber together; the
package is a 12.5% gold rise. Catapult trade in the siege package: 1.09,
from 0.56; workshops stood in 56% of player-games, from 22%.)

What the table settles:

* **Towers are a symptom.** Weaker or dearer towers cut what a tower kills
  from 7.5 times its cost to 4 or 5 and leave `turtle` exactly where it
  was. What wins is waiting for twelve soldiers, with or without towers:
  `mass` has Master's two towers and the same record.
* **The knight is over-priced by about a tenth in the wrong direction.**
  A hundred gold more takes the knights posture from Master's equal to
  twenty points below it. With the archer's shot raised from five to six
  as well, archers take 38% against knights where they took none, and
  knights keep a trade of two to one. That is the package to ship, and the
  cause is the armour rule: flat subtraction with a floor of one leaves a
  five-damage archer doing one point to four armour.
* **The siege path is priced for a unit the brain cannot use.** Cheaper
  and sturdier, catapults trade evenly and the baseline brains reach the
  workshop in more than half their games, yet the siege posture still loses
  every game to a massed push. Catapults out-range towers by one tile and
  the brain walks them into range anyway; against a human who stands off
  they are worth more than this league can see.

## What to change

Fixed on this branch, before any price:

1. Repair charged up to 40% over the half price it promises (rounding per
   ten-point chunk). Fixed in `rules.repair_cost`.
2. The wood crew only ever grew; losers sat on sixteen thousand lumber.
   Fixed: above `lumber_stock` all but one chopper go back to the gold.
3. A producer bought whatever it could afford at that moment, so a knights
   plan fielded scouts. Fixed: the unit the army is shortest of has first
   claim on the bank.

Recommended, with the evidence above:

1. **Give waiting a cost.** The league's equilibrium is entirely postures
   that hold until twelve to fifteen soldiers; the rush posture is the
   worst thing in the game and raiding the second worst. Nothing punishes
   a player for sitting at home: a base mine holds 50,000 gold, so it never
   runs dry inside a match and the expansions are never fought over.
   Shrinking the base mine so it is spent around minute five (a dry-mine
   experiment is in `docs/evidence/balance/`) makes the map the fight, and
   is the one change here that reaches the top of the table. Master itself
   should also walk out later — the `ai-2000` branch found the same — but
   that is the brain, not the rules.
2. **Knight 800 → 900 gold and archer damage 5 → 6.** Measured above.
   Better still, and untested: an armour rule that cannot floor a shot to
   one point, so the archer is the counter the rules table says it is.
3. **Catapult 900+300 → 700+200 with 100 hit points, workshop
   900+500 → 700+350.** The path is then reached, and the unit trades
   evenly. Whether it also needs the blacksmith as a prerequisite is a
   design choice; the package left it in.
4. **Tower 500+200 → 700+250**, a modest rise: it does not move the
   standings, but a building that kills seven times its cost in every
   rulebook is too cheap even if it is not the problem.
5. **Races**: orcs at 43% and dwarves at 46% against elves and humans at
   55%. Orcs train 10% slower and humans 15% faster, a quarter apart, in a
   game decided by who has more at the first clash. The race ladder with
   orcs at the common rate and Drill at 10% is in the evidence directory.
6. **Scouts**: ten a game, trading 0.67, most of them Master's rule that
   keeps one scout alive for eyes. A price is not the fix; a cheaper way to
   see (a longer-sighted tower, a scout that flees) is.
