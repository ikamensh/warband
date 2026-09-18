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

## What was changed

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
5. **Races**: Master against Master, every pair of distinct races, eight
   maps each way (96 matches, 48 a race, about seven points of noise):
   human 66.7%, elf 66.7%, dwarf 35.4%, orc 31.2%. With orcs training at
   the common rate and Drill cut to 10% (`races-tweak.jsonl`): elf 75.0%,
   human 50.0%, orc 41.7%, dwarf 33.3% — orcs recover ten points, humans
   fall seventeen, and the elves, who beat every other race three games in
   four, are the real outlier. What the elves have is speed (+0.3) and
   sight, and what the dwarves lack is speed (−0.3): in a game decided at
   the first clash, being there first is the race. Halve both speed
   modifiers before touching training rates; measure again with the same
   ladder.
6. **Scouts**: ten a game, trading 0.67, most of them Master's rule that
   keeps one scout alive for eyes. A price is not the fix; a cheaper way to
   see (a longer-sighted tower, a scout that flees) is.
7. **Clerics**: not the price. At 30% off, the clerics posture moved from
   25% to 33% (inside the noise) and the brains bought exactly as many. A
   healer's worth cannot be read off kills; it needs its own measure
   (hit points restored per gold) before its price is judged.

Two things the experiments found that are not prices:

* **Master does not expand when its mine runs dry.** Under the dry-mine
  rulebook (base mines of 12,000) not one town hall went up in 336 seats,
  peak armies fell to a third, towers vanished, and 28 matches of 168 ran
  to the cap with fifteen to twenty thousand lumber banked, because the
  idle miners went to the trees. The expansion wish sits behind the
  saturation gate, and a brain with no income never saturates; and the
  hall costs 1,200 gold that the barracks spend first. A base mine lasts
  ten to twelve minutes at Master's mining rate, so this bites in any long
  match against a human too. Fix before the mine size can be judged: an
  expansion, and the gold for it, gets first claim once the worked mines
  are low.
* **The league prices what the brain can use.** Catapults that out-range
  towers and walk into them, scouts bought as eyes, a healer measured by
  kills: each is a place where the readout is a floor on the true value,
  not the value. Read the pathologies and the fielded table before every
  number.


## The changes this evidence bought

### Staying at home now costs something

Nothing in the game punished a player for never leaving base: a mine held
50,000 gold and absorbed every peasant that could be hired, so a bigger
workforce at home always beat taking a second mine. That is why the
league's equilibrium was the two postures that sit at home longest.

A mine now works `MINE_SLOTS` peasants at its face and the rest wait their
turn, so it yields at most `MINE_SLOTS * GOLD_PER_TRIP / MINE_TIME`. With
the walk to the hall on top, a mine next door is saturated by about ten
peasants and a distant one by a few more; past that the way to more gold is
another mine. Crews are counted as peasants enter and leave, rebuilt on
load, and the automatic worker policy sends nobody to a face that is full.

This needed the expansion bug fixing first. Master's expansion wish sat
behind the saturation gate, and a brain with no income never saturates, so
the dry-mine rulebook saw no second hall in 336 seats. Scarcity — a mine
below `mine_floor`, or every place at the face taken — now opens that gate
too, while the old mine still has the gold to pay for the move.

### Prices

Applied as measured in the experiments table above: knight 800 → 900 gold,
archer 5 → 6 damage, catapult 900+300 → 700+200 with 100 hit points,
workshop 900+500 → 700+350, tower 500+200 → 700+250, and the elf and dwarf
speed modifiers halved to ±0.15.

The archer's is the one worth restating. Armour is a flat subtraction with
a floor of one, so a five-damage arrow did a single point to a knight's
four armour: ninety shots to fell it. At six it does two. That is a
workaround, not a fix — the rule that floors a shot at one point is still
there, and an armour rule that scales instead would make the archer the
counter the rules table says it is. A test now pins the margin so a future
change cannot quietly take it back.

### A settled match stops

A fifth of the average match was spent razing a beaten player's farms, and
every stalemate paid the twenty-minute cap in full. A match now ends when
one player has both the field and the map: an army five times every
rival's, while also half again ahead on everything standing, held for
thirty seconds. Checked over 112 matches played both ways — identical
placements in all 112, the same winner in 110, and the two others were
stalemates the full match left undecided and the rule called. It saves 22%
of a league's wall time and the simulation is untouched.

### Scanning less often: measured and dropped

A unit looks around for something else to fight four times a second; the
proposal was two. It was tried and dropped, because the measurements did
not support it:

| | 4 Hz (kept) | 2 Hz |
|---|---|---|
| whole matches, same seeds, one process | 0.518 ms/step | 0.524 ms/step |
| Master over Hard, 108 matches | 86.1% | 75.0% |
| Hard over Medium | 88.9% | 100.0% |
| Medium's score on the ladder | 5.6% | 0.0% |

It buys nothing on a whole match because a match is worker routes,
pathfinding and crowd separation, not target scanning — the 150-unit battle
benchmark where scanning does show up is not what a league spends its time
on. And slower reactions cost the weaker brains far more than the stronger
ones, which would flatten the shipped difficulty ladder and make the
easiest setting easier still. The mop-up rule above is where the league's
time actually was.

### The sawmill does nothing for lumber

It is a drop-off point and a research building, nothing more: lumber is a
flat `LUMBER_PER_TRIP` wherever it is delivered, and the only per-trip
bonus in the game is Deep Mining, on gold, for dwarves alone. For 600 gold
and 450 lumber that is a thin building, and now that mines are capped and
lumber is the resource that gates farms and supply, a sawmill that actually
increased the load a peasant carries would be the obvious counterpart to
Deep Mining. Untested: it needs a rule, not a `scale:` variant.


## The third league: what the changes did, and what they did not

The same 1,056 matches under the new rules
(`docs/evidence/balance/league-3.jsonl`, 1,040 decided). What the changes
were aimed at, they hit:

| | league 2 | league 3 |
|---|---|---|
| knight, value destroyed per 1,000 spent | 1,340 | 1,071 |
| knight, destroyed per lost | 2.68 | 2.02 |
| archer, value per 1,000 | 1,053 | 1,118 |
| catapults bought in | 9% of seats | 17% |
| workshops bought in | 16% | 31% |
| catapult, destroyed per lost | 0.97 | 1.22 |
| towers bought in | 83% | 58% |
| tower, value per 1,000 | 2,488 | 1,662 |
| halls built per seat | 0.30 | 0.39 |
| minutes at the supply cap | 23% | 15% |
| unspent bank at the end | 6,400 | 3,372 |
| undecided matches | 63 | 16 |
| median match | 8.5 min | 7.0 min |

The knight is no longer the best thing per gold, archers trade better than
footmen, the siege path is reached twice as often and its stones now trade
above their cost, towers are bought in a quarter fewer games, brains expand
a third more often, and matches are shorter and far more decisive. A league
costs 3.4 core-hours where it cost 5.0.

**And none of it changed the answer.** The equilibrium went from `mass` 61%
/ `turtle` 39% to `turtle` 99.9% alone. Waiting still wins, and capping the
mines did not punish it, because a cap binds on both players equally: the
patient player expands too, and defends the expansion better.

## What actually decides it: the map

Breaking the same league down by layout says more than any price did:

| layout | games | mines | `turtle` | `mass` | `rush` | `raiders` | `knights` |
|--------|------:|------:|---------:|-------:|-------:|----------:|----------:|
| plains | 660 | 7.6 | 87.3% | 87.3% | 30.9% | 26.4% | 61.8% |
| crossings | 132 | 8.0 | 61.4% | 59.1% | 45.5% | 59.1% | 70.5% |
| klondike | 132 | 8.0 | 50.0% | 54.5% | 36.4% | 40.9% | 63.6% |
| bastion | 132 | 6.0 | 77.3% | 77.3% | 54.5% | 36.4% | 18.2% |

On plains the patient postures take seven games in eight and raiding is the
worst thing in the game. On klondike the same postures are merely average
and the meta is flat. Raiders go from 26% to 59% between the two. Knights
swing from 70% on crossings to 18% on bastion, where walls mean cavalry
cannot get at anything.

Two things follow.

**The instrument was measuring plains.** Eight seeds drew plains five times
and forest not at all, so five eighths of every number in this document is a
statement about one layout. A `MatchSpec` now names its layout and the
runner cycles all five, as it already cycled the map size. Every league from
here is spread across the generator; these tables are not, and the
per-layout rows above are 132 games each — a couple of dozen per posture,
which is below the floor this project sets for believing anything. They say
where to look, not what is true.

**Balance is a map problem at least as much as a price problem.** The reason
waiting wins on plains is that nothing is contested: seven or eight mines on
open ground mean a player can take a second base without ever meeting the
enemy, so an attack buys nothing an expansion does not buy more cheaply.
Where mines are few or the ground is broken, aggression pays. The lever is
in `mapgen`, not in `rules`: fewer mines on open maps, or mines placed so
that the second one is between the players rather than behind them.

## What to change next

1. **Re-measure across the layouts**, now that a league can ask for them.
   Every conclusion here is weighted towards plains and needs restating.
2. **Make plains contest its mines** — fewer of them, or placed so a second
   base is forward rather than behind. This is the change most likely to
   move the equilibrium, and no price tried today came close.
3. **Orcs: measured and fixed.** After halving the speed modifiers the race
   ladder gave human 62.5%, elf 62.5%, dwarf 50.0% and orc 25.0% (96
   matches, Master against Master, every pair both ways): the dwarves
   recovered from 35% and the orcs fell to 19% against both leaders. They
   had been training 10% slower in a game decided by who reaches the first
   clash with more, which is a penalty paid twice. At the common rate the
   ladder reads elf 58.3%, human 56.2%, dwarf 43.8%, orc 41.7% — a spread of
   seventeen points where it had been thirty-eight — and that is applied.
   Ninety-six matches a run, so the ordering inside the remaining spread is
   not established; a few hundred would settle it.
4. **The armour rule.** Raising the archer to six damage is a workaround for
   a floor of one point against four armour. A rule that scales would make
   the archer the counter the table promises without the patch.
