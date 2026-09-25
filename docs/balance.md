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
its knobs that each commit to one way of playing — `warband/league/archetypes.py`:

| posture | commits to |
|---------|-----------|
| `pro` | the shipped Master: its race's own army plan |
| `rush` | out at three soldiers, footmen and archers, no expansion, no tech |
| `boom` | an early second hall, a big workforce, out at twelve |
| `mass` | five barracks a hall, out at fifteen |
| `turtle` | five towers, three guards, out at twelve only when clearly ahead |
| `footmen` | the line alone, with a smith up early for the blades |
| `archers` | four in five archers |
| `knights` | stables first, three in four knights |
| `raiders` | half knights, four of them riding at the enemy's peasants |
| `siege` | smith and workshop first, a third catapults, out at eight |
| `clerics` | a church first, a quarter healers |
| `noresearch` | Master that never buys an upgrade, to price the research path |

A posture is checked to be what its name says: the report prints what each
one fielded per game.

## Tuning the numbers

Edit the TOML, not the Python. The tunable numbers are nine commented
files in `warband/assets/constants/`:

- `units.toml` — every soldier and worker: cost, hit
  points, damage, armour, range, timings, sight, body.
- `neutrals.toml` — the four wild creatures, tuned the same way.
- `buildings.toml` — every building: cost, hit points, work, the
  tower's shot, and the two deposits (gold per trip, places at the face).
- `upgrades.toml` — every research: price, time, and what it does.
- `races.toml` — what each race renames and retunes on top.
- `economy.toml` — harvest timings, mine stocks, starting resources,
  what mending and salvaging cost.
- `combat.toml` — melee reach, projectile speeds, the armour rule,
  and how a siege crew weighs its own side against the enemy's.
- `buffs.toml` — the timed conditions a unit carries (Rage, Bleeding, and
  from WB-066 the spells): what each multiplies, adds and drains, how long
  it lasts, whether a machine can take it, whether a heal ends it. A row is
  the whole of a kind; the rule that lays it on names it (see below).
- `behavior.toml` — formation marching, creature camps, crowd
  spacing, how far an idle unit chases.

What stays in code, deliberately: the engine timing (`SIM_DT`), the order
bounds, the pathfinder's budgets and cadence, the seats, and the alert
cooldown — planner internals and protocol, not balance. `behavior.toml`
names the boundary at its top.

Restart after editing. The simulation reads all nine files once at startup,
validates them, and builds its typed rule tables. File edits cannot affect an
already launched game, even if another table is imported later. No generator
or duplicate Python catalogue needs updating.

The TOMLs ship under `warband/assets/constants/`, alongside the other bundled
game data. Their bytes join the simulation sources in the online compatibility
hash. A compiled league build captures its startup snapshot and gives that
same snapshot to every spawned worker; changes made during a run apply to the
next run, never just some matches in a league.

`units.toml` and `neutrals.toml` each have a `[defaults]` table. Every entry
overrides those values. Each race's `units` and `buildings` table follows the
same rule, so a racial bonus appears once:

```toml
[orc.units]
defaults = { hp_mult = 1.15 }
peasant = { name = "Peon", summary = "Digs gold, hacks lumber, builds and repairs" }
knight = { name = "Ogre", summary = "Two-headed brute; thin armour, all rage", hp_mult = 1.2, damage_mult = 1.1, armor_add = -1 }
```

Every playable role and building still needs its own entry; the example
above omits the other roles for brevity. There is no inheritance between
entries or files. An explicit value always wins, including `0`, `1.0` and
`false`. Omitted racial modifiers mean multiply by one, add zero, and retain
the base formation setting. Base units may omit costs, heal, splash,
min_range and regen (zero), attack (`"normal"`), armor_class (`"light"`),
formation/mounted/flying (`false`), turn_deg (`360`), living (`true`: a machine,
the catapult, the flying machine and the golem, says `false` and takes no living
condition nor a healer's cast), inflicts (none: the archer's `"bleeding"` names
the buffs.toml row its wounding shot lays on) and sound (`""`: the fielding
race's voice; a machine or creature names its family, `docs/adding-a-unit.md`).
Other fields must appear
in the entry or its defaults. Misspelled keys, wrong types and missing
required fields fail startup validation, including invalid defaults that every
entry overrides.

`buffs.toml` has a `[defaults]` table too, and any number of rows: `rage`,
`bloodlust_rage` and `bleeding` are the ones the rules lay on by name, and a
row nothing names yet is a kind waiting for its rule. A unit carries at most
one of each kind; laying it on again restarts its timer, and different kinds
combine (multipliers multiply, armour adds). A seat sees the conditions of a
rival's units in its sight, so a kind that only research lays on would tell
that research: until the match is decided, the authority sends
`bloodlust_rage` to the other seats as `rage` (`authority.STRANGER_KINDS`), and
a new kind like it gets a row there.

To *try* a price before committing to it, skip the files: a `scale:` variant
patches the numbers in every worker for one league — see below.

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
comes back with a `PlayerTally` per player (`warband/league/telemetry.py`): what
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
they do not.  (The scout rider in these tables went in WB-064; the flying
machine that took its place as the side's eyes carries no weapon, so it has
no row.)

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
   see (a longer-sighted tower, a scout that flees) is. WB-064 took the
   second road: the rider is gone, and the eyes are a flying machine that
   sees nine tiles over the trees and that only shooters can reach.
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

### The gold seam: a reason to hold ground (2026-09-21)

The same equilibrium — `mass` at 77 % and `turtle` at 76 %, and nothing else
played — is what the **gold seam** is aimed at. It is a second kind of
deposit, five tiles across, twenty gold a trip against a hundred, twelve
places at its face against eight, and it never runs out. It sits in the
shared ground at least eighteen tiles from every hall, on Plains, Crossings
and Bastion, and only on maps bigger than the three shipped sizes — so the
ratings and the league above were measured on maps that have none, and still
hold. The design and the measurements are in
[the maps note](warband-maps.md#the-gold-seam-2026-09-21).

### Creature camps: a job for the army at minute four (2026-09-21)

The same equilibrium again, from the other side. A seam gives an army a
*reason* to hold ground; a **creature camp** gives it something to do to get
there. Every contested deposit — the thirds and the seam, never a seat's own
mine and never its natural — is guarded by a lair and its creatures, so the
army a player builds before the timing push has a use that is not suicide into
towers, and the middle of the map has to be taken from somebody at minute four.

The measurement that matters is not a win rate but whether every side can use
it: `tools/creep_report.py` reports lairs torn down against units lost to the
wilds. Over 60 matches a side on Medium, `pro` cleared 0.74 lairs a match for
1.17 units and `medium` 0.94 for 1.45 — a soldier and a half per den, against
its hoard and the deposit it sat on. On the ladder, `pro` scores 63.7 % against
`hard` with the camps and 70.0 % without, about one and a half standard errors
apart on 80 games each, while peak army rises from 13 to 17 (`hard`) and 19 to
21 (`pro`) and kills from 20 to 24 and 28 to 34. The design is in
[the creatures note](warband-monsters.md).

The shape of the incentive: a hand at a seam earns 2.9 gold a second against
a miner's 12.8, so it is never the place to put the next peasant. But an
expansion mine's 30 000 gold is drunk by a saturated crew in three and a
quarter minutes, while a hall at a seam pays 34.8 gold a second for as long
as it stands — the same 30 000 in fourteen and a half minutes, and every
minute after that for nothing. Taken in the third minute of a long match it
out-earns an expansion mine; taken in the fifteenth it is a rounding error.
A posture that waits at home is paying for the wait.

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

## Revalidated on 2026-09-19 (WB-014)

After WB-043 (held build prices), WB-037 (the answers to a tower rush) and
WB-036 (Master's third posture), on main, with evidence under
`docs/evidence/wb014/`:

* **Races**, Master against Master, 24 seeds a pair both ways (288 matches, 6
  undecided; `tools/race_report.py --seeds 24 --difficulty master`, which had
  been unable to play Hard or Master since they became a ProBrain and now asks
  `make_brain`): human 55.6%, elf 51.4%, dwarf 51.4%, orc 41.4%. Pairs: dwarf
  31–15 orc, human 29–19 orc, human 29–19 dwarf, elf 25–21 human, elf 22–24
  orc, dwarf 23–25 elf. The orcs sit where the third league left them (41.7%
  on 96 matches), now on three times the sample; their loss to the dwarves is
  the widest gap. Not retuned here: that is a balance change with a server
  rollout, filed as WB-045.
* **The ogres (WB-045)**: an orc-only change had to hold on both brains, and
  they disagree. On Medium the orcs were already strong (55.2%) and the
  humans weak (39.2%), the reverse of Master, because Medium's longer fights
  pay for hit points and Frenzy (Rage since WB-062) where Master's first clash pays for tempo. Of
  the candidates rated against the other three races (144 matches each,
  `docs/evidence/wb045/`), every buff that lifted the orcs on Master lifted
  them further on Medium (training 7% faster: 52.9% and 59.9%; grunts
  without their armour penalty: 55.6% and 66.7%; grunts at 125% hit points
  with the ogres' change: 49.3% and 60.1%), except the ogres' armour penalty
  halved (−2 to −1): 45.1% on Master, 53.1% on Medium. It is applied. The
  full race reports with it, 288 matches each: Master human 54.9%, orc 45.1%,
  elf 50.0%, dwarf 50.0%; Medium human 41.3%, orc 53.1%, elf 55.6%, dwarf
  50.0% (the humans and elves were at 39.2% and 56.3% on Medium before, a
  Medium-brain matter this change moves the right way).
* **Free-for-all endings**, the four settings in four-player matches, 24 seeds
  with every seat rotation (96 matches): 85 decided, median 11.5 minutes;
  placement scores Master 71.9%, Hard 52.8%, Medium 47.4%, Easy 28.0%. Hard
  barely clears Medium here, where one against one it is 400 points above it:
  the pro brains' caution in a free-for-all (`ffa_caution`).
* **Easy against a plain opening**: see [the difficulty
  settings](ai-ladder.md#the-difficulty-settings). Easy now waits until
  minute eight before its first wave, and the scripted opening beats it again.

## The catapult, and the two weapons it was (2026-09-20)

A player said catapults were too strong for their price. Every number in this
document said the opposite — the siege posture scored 34.7% in the second
league and catapults earned 650 per 1,000 spent — and both were right, because
they were not talking about the same weapon.

`model._aim_point` used to end `return None if auto else spots[-1]`. A crew
firing on its own judgement refused a landing point its own side could be
standing on; a crew a player right-clicked onto a target fired anyway, and the
player answered for the splash. The league only ever plays brains, so every reading here is the
first weapon. `tools/battle_bench.py --aimed left|right|both` now drives a
side's crews the way a player does — every half second a crew with no live
target in reach is right-clicked onto the enemy its stone is worth most on —
so the second one can be measured too.

The gap was the whole complaint. Seven footmen and two catapults against ten
footmen, 60 fights a pairing, half from each side:

| | on its own judgement | aimed by hand |
|---|---:|---:|
| won | 26.7% | 100.0% |
| stones thrown in the clash | one every 31 s | one every 5.4 s |
| damage on the enemy | 358 | 564 |
| damage on our own side | 0 | 248 |
| of nine units left | 1.5 | 3.7 |

A catapult's reload is 3.8 seconds. The crew was firing at an eighth of its
rate and the player at seven tenths, so they were not the same unit at all: at
the old price the hand-aimed pair was worth three times what it cost (seven
footmen and two catapults held sixteen footmen: 5,400 gold of infantry against
1,800 of engines) and the crews' own pair twice.

### The crew now weighs the trade

Refusing every stone that could touch our own side means refusing every stone
there is once the lines meet, and the per-unit bodies of
[unit-motion part 7](unit-motion.md) made it worse: fatter bodies are shoved
further, so `FRIENDLY_MARGIN` had to rise from 0.3 to 0.45 and the same
pairing fell from 90.0% to 26.7%.

`_clear_of_friends` is now `_friendly_cost`, which weighs a friend exactly
where it used to place it — where it stands, where its velocity carries it,
where its move order carries it, at arm's length of the enemy it is walking up
to fight — but returns what it would cost rather than a veto: each friend under
the stone counts its `SIEGE_WORTH`, in full within `DIRECT_HIT` and
`SPLASH_FRACTION` out to the splash, `FRIENDLY_MARGIN` further out again on
both because the prediction is a guess. `_aim_trade` then throws the landing
point with the best `enemy − FRIENDLY_WORTH × ours`, and holds when nothing
comes down ahead. `_siege_choice` picks its target by the same number.

`FRIENDLY_WORTH` is two of ours for one of theirs, which is the least that is
clean. Won is the set piece again, 60 fights a pairing; the damage columns are
the same seven footmen and two catapults against ten footmen over twelve seeds:

| our own count | won vs footman:10 | vs footman:12 | damage on the enemy | on our own |
|---|---:|---:|---:|---:|
| the old veto | 26.7% | 6.7% | 358 | 0 |
| ×5 | 50.0% | — | 344 | 2 |
| ×3 | 91.7% | 30.0% | 412 | 16 |
| **×2** | **95.0%** | **71.7%** | **425** | **29** |
| ×1.5 | 98.3% | — | 458 | 54 |
| ×1 | 98.3% | — | 504 | 77 |

At 1.5 and below the crew shells its own line on the clash seeds of
`tests/warband/test_siege_judgement.py`; at 3 it holds fire where it is pressed. `FRIENDLY_MARGIN` was not touched: it is the slop in
the prediction, not the appetite for a trade, and it is already the least value
that keeps stones off our own footmen with the new bodies.

### Then the price

With its crew fixed the catapult was the best thing per gold in the game, and
for the brains as much as for the player. Six postures on four maps from both
corners, 120 matches and 240 player-games a rulebook — the price-experiment
shape, so roughly eight points of noise on a posture's score and far less on
the usage columns:

| rulebook | `siege` | value per 1,000 | trade | a game | workshops |
|---|---:|---:|---:|---:|---:|
| before the crew's judgement changed | 50.0% | 1,417 | 2.65 | 2.11 | 48% |
| with the trade | 60.0% | 1,457 | 2.77 | 2.19 | 48% |
| price 900 → 1,200 | 47.5% | 1,255 | 2.20 | 1.95 | 47% |
| damage 36 → 30 | 47.5% | 1,222 | 2.23 | 1.99 | 48% |
| reload 3.0 → 4.0 | 55.0% | 1,325 | 2.50 | 2.12 | 50% |
| price and damage | 50.0% | 1,119 | 2.16 | 1.85 | 47% |
| price and reload | 47.5% | 1,116 | 2.17 | 1.73 | 47% |
| price and reload 4.5 | 45.0% | 1,098 | 2.07 | 1.80 | 47% |
| price, reload and damage 32 | 47.5% | 1,010 | 1.89 | 1.88 | 48% |
| price 1,750 and reload | 48.8% | 1,106 | 2.17 | 1.51 | 48% |
| **price, reload and 80 hit points** | **46.2%** | **1,029** | **1.76** | **1.87** | **45%** |
| price, reload, 70 hit points, damage 34 | 40.0% | 946 | 1.57 | 1.85 | 47% |

In the same league the archer destroys 1,003 per 1,000 spent and trades 1.35,
the knight 799 and 1.17, the footman 538 and 0.71. **Applied: `Cost(700, 200)`
→ `Cost(900, 300)`, cooldown 3.0 → 4.0 and 100 → 80 hit points.** That is the
price the catapult carried before the second league cut it, restored now that
the crew can use the thing; a stone every 4.8 seconds instead of 3.8; and the
one lever measured to cost a hand-driven crew more than a brain's, because a
brain keeps its engines further back than a player does.

Damage, splash, range, minimum range, speed, the wind-up, the ×1.5 against
buildings and Siege Engineering are all untouched: they are what the unit is,
and three hands on one unit is already two more than a price. The workshop's
own price is untouched too — the path is still reached in 45% of player-games.

What it comes to, 60 fights a pairing.  The left army is always seven footmen
and two catapults, which came to 6,000 gold-plus-lumber before and 6,600 after,
so its equal-price opponent in footmen goes from ten to eleven and the two
fixed opponents below go from ten per cent richer than it to exactly its price:

| against | before, on its own | before, aimed | after, on its own | after, aimed |
|---|---:|---:|---:|---:|
| its price in footmen | 26.7% | 100.0% | 61.7% | 96.7% |
| twelve archers (6,600) | 100.0% | 90.0% | 96.7% | 66.7% |
| six knights and a footman (6,600) | 50.0% | 88.3% | 26.7% | 61.7% |
| what a catapult is worth, against footmen | 2.0× its price | 3.0× | 1.2× | 2.0× |

(The last row is where the win rate crosses a half as footmen are added: before,
the pair held sixteen footmen aimed and about thirteen on its own; after,
fifteen and under twelve, against a price that rose by a third.)

The player's catapult falls from three times its price to twice; the brains'
from twice to a little over its price, having been lifted four-fold by the
judgement first, so the `siege` posture lands at 46.2% against the 50.0% it
had before any of this. The remaining gap between the two is a player picking
better ground and pushing the engines into range, which is skill, not a rule.

### What it did to the difficulty ladder

Nothing that shows. The same 400-match ladder (`tools/arena.py ladder --agents
easy,medium,hard,master,grandmaster --seeds 20`) run either side of the whole
change: Grandmaster 1488 → 1575, Master 1347 → 1395, Hard 1222 → 1188, Medium
the anchor, Easy 515 → 517. Every one of those is inside its own 90% interval,
and the order and the gaps are unchanged, so `brains.ai.DIFFICULTY_ELO` stands.
(The absolute numbers are lower than that table throughout: a Bradley-Terry fit
reads against the field it was played in, and five agents on twenty seeds is
not the measurement the shipped table came from.)

### What is stale above

The second league's readings on the catapult — 650 per 1,000, a trade of 0.97,
the siege posture at 34.7% — are three leagues and a dozen changes old
(the price cut, the mine cap, WB-052's siege judgement, the Keep, the bodies).
On this branch, before anything here, the catapult already destroyed 1,417 per
1,000 and traded 2.65. Read the dated sections downwards; the price experiments
above are the record of what was tried in September, not the state of the game.


## The flying machine replaces the scout rider (WB-064, 2026-09-24)

The stables trains knights only, and the workshop trains an unarmed flying
machine: the eyes, not a soldier (sight 9 over trees and walls, 400 gold, 100
lumber; only shooters and towers reach it). The army plans lost their scout
shares, renormalised onto the rest; the raids went to knights and, measured
at a cost, off by default for the pro brain ([the ladder
doc](ai-ladder.md#the-flying-machine-takes-the-riders-place-wb-064)).
`tools/race_report.py --seeds 24`, 288 matches a run, on the same seeds either
side of the change, and then with the hunt that change needed (below):

| race | Master before | Master after | Master, hunting | Medium before | Medium after | Medium, hunting |
|------|--------------:|-------------:|----------------:|--------------:|-------------:|----------------:|
| human | 74–67 (52.5%) | 61–64 (48.8%) | 72–70 (50.7%) | 75–69 (52.1%) | 73–66 (52.5%) | 75–69 (52.1%) |
| orc | 50–81 (38.2%) | 47–82 (36.4%) | 51–91 (35.9%) | 58–83 (41.1%) | 49–89 (35.5%) | 53–91 (36.8%) |
| elf | 68–70 (49.3%) | 63–61 (50.8%) | 66–74 (47.1%) | 73–68 (51.8%) | 76–63 (54.7%) | 78–66 (54.2%) |
| dwarf | 80–54 (59.7%) | 81–45 (64.3%) | 94–48 (66.2%) | 79–65 (54.9%) | 80–60 (57.1%) | 82–62 (56.9%) |
| undecided | 16 | 36 | 5 | 3 | 10 | 0 |

The rider's going first made more matches run to the twenty-minute cap, and
those looked alike: the loser down to one peasant somewhere off its old base,
and no brain going to look for it. The riders circling the enemy's base and
the raiders waiting for prey used to stumble on such a peasant. So a brain
that has lost track of every rival now hunts (`brains.ai.Hunt`, [the ladder
doc](ai-ladder.md#the-flying-machine-takes-the-riders-place-wb-064)), and the
undecided matches fell below where they started: the five Master mirrors
still at the cap are standoffs, both sides alive with dry mines and a handful
of soldiers, not a lost peasant.

Deciding those matches moves the table more than the rider did. The orcs,
already the weak race (WB-045), lost ground on both brains, most on Medium,
whose orcs had the heaviest cavalry plan and now open their harass with two
knights where they sent two cheap riders; and the dwarves' Master lead grew to
66%. Neither is tuned here: a race-balance pass waits for WB-062, whose buffs
touch orc Rage.


## Rage and Bleeding (WB-062, 2026-09-24)

WB-062 made the orcs' Frenzy a timed condition, Rage, and gave every race's
archer a wound, Bleeding (`buffs.toml`): a hit point a second through armour
for five seconds and a fifth slower, renewed by every arrow, never on heavy
armour. Measured with `tools/race_report.py`, Master against Master and
Medium against Medium, every pair of races both ways: on Master 47 seeds (564
matches), on Medium two blocks of seeds (`--first-seed 1` and
`--first-seed 49`, 1,140 matches), because one block of Medium swung by as
much as six points between two samples of the same rules. Before is main at
`190a9ae`; after is the same main with WB-062. Share of decided matches won:

| | Master before | Master after | Medium before | Medium after |
|---|---:|---:|---:|---:|
| human | 47.0% | 46.6% | 45.2% | 47.5% |
| orc | 37.4% | 36.3% | 45.3% | 42.7% |
| elf | 52.1% | 51.8% | 54.6% | 52.4% |
| dwarf | 63.5% | 65.4% | 54.9% | 57.4% |
| undecided | 2 | 5 | 2 | 1 |

No race moves more than 2.6 points on either difficulty (the orcs on Medium);
the dwarves' lead on Master and the orcs' deficit are main's, before and after
alike.

Rage costs nothing: without healers it is Frenzy, and with them it outlasts a
heal by ten seconds, which the race games barely see (Rage alone, no wound,
moved no race more than 2.1 points on Medium). The wound is what moves races,
and what it moved is the heavy melee's reach: the elves' Medium army is 45 %
rangers that kite, and a slowed, bleeding footman or knight never closes on
them. Before heavy armour turned the barb, on Medium:

| the wound, before heavy armour was spared | human | orc | elf | dwarf |
|---|---:|---:|---:|---:|
| as designed, with a group's pace frozen by one wounded member (564, an older main) | −0.4 | −1.6 | +9.2 | −7.0 |
| as designed, each member at its own pace (564, an older main) | −7.1 | −1.4 | +18.1 | −9.7 |
| a point a second, a tenth slower (1,140, main `07cb63d`) | −2.4 | −3.6 | +11.0 | −5.1 |
| a point a second, no slow | −4.8 | +1.6 | +5.0 | −2.0 |
| half a point a second, a tenth slower | −3.9 | +1.4 | +4.5 | −2.1 |
| half a point a second for three seconds, no slow | −3.6 | −0.7 | +2.3 | +1.9 |
| a tenth slower, the archer at 550 gold (1,140, an older main) | +0.2 | −3.4 | +7.9 | −4.7 |

Weakening the wound for everyone brought the races back into band, and a
dearer archer did not, since every race pays it and the elves still field the
most. Sparing heavy armour keeps the wound whole where it was meant to bite
(the light, the unarmoured, the raider and the shooter) and takes it off the
units that have to walk into the arrows (`spares = ["heavy"]` on the row,
checked where any condition is laid on, so a spell can spare an armour too).

The group-pace fix belongs to the conditions, not the balance: a group's pace
is its slowest member's speed as listed (`World.listed_speed`), and each
member walks it at its own condition's rate, so a slowed soldier falls behind
while it is slowed rather than setting the whole army's pace for the rest of
an order it was given while slowed.

Two Master runs of the variants stopped on a crash that was main's, not the
wound's, and is fixed on main (`190a9ae`): a recruit sent to its rally point
went through `World.smart`, which ordered an attack on a rival flying machine
hovering over the point, refused with a `RuleError` inside the step.

## The last-stand reveal waits for the last two (WB-072, 2026-09-24)

A side left with no hall and no building that trains used to have its last
buildings revealed to every other seat. In a free-for-all that told the
bystanders where a beaten side hid. The reveal now happens only while exactly
two sides remain (`World._exposures`), and only the one rival is told. The
brains' hunt looks for whatever is no longer revealed. The reveal is also sight
lent to the rival before its memory is refreshed. Before, a brain never
remembered a revealed building, and a seat's snapshot left out any that lay
beyond the box its own forces' sight spanned.

`tools/arena.py ffa --agents easy,medium,hard,master`, every seat rotation,
on the same seeds either side of the change:

| league | matches | undecided | settled early | played out | median length | changed at all |
|--------|--------:|----------:|--------------:|-----------:|--------------:|---------------:|
| four players, `--seeds 48`, before | 192 | 3 | 172 | 17 | 11.8 min | |
| four players, after | 192 | 4 | 169 | 19 | 11.8 min | 19 |
| three players, `--seeds 24`, before | 288 | 1 | 265 | 22 | 10.0 min | |
| three players, after | 288 | 0 | 266 | 22 | 10.0 min | 12 |

That is 4 undecided in 480 before and 4 after. The ratings moved by at most
two points (four players: Master 1056 to 1058, Easy 878 to 876). The four-player
match that stopped deciding, seed 1036 (medium, hard, master, easy), shows how
these swaps come about. In the old run Easy stood exposed for six seconds at
minute 8.2 with all four alive, and the other three were shown its base. With
nothing shown, the match drifted to a standoff between two full bases at the
cap; nobody was hiding. The three-player match that now finishes (seed 1013)
is the same kind of swap in the other direction. Neither `sim_fingerprint`
(Hard–Medium duels, six minutes) nor `sim_bench` (eight settled duels and one
four-player match) reaches an exposure, and both are unchanged.

## The Mother Lode (WB-071, 2026-09-24)

The shared ground's prize is now a gold seam or a Mother Lode, dealt by the
seed ([the maps note](warband-maps.md#the-mother-lode-2026-09-24-wb-071)), and
the brains value a deposit by its pace and its stock. None of it reaches the
three shipped sizes: no prize lies on them, every deposit there paces as a mine
and no camp keeps more than an expansion's thirty thousand, so every value the
brains now compute is exactly one there. `tools/sim_fingerprint.py --check` is
unmoved, and `tools/sim_bench.py`'s nine arena matches give the recorded results
to the bit once the two keys this change added to the record (the spec's
`prize`, the tally's `mined`) are taken out; the digest moved for those keys
alone. So `tools/race_report.py` and the difficulty ladder, which play only the
shipped sizes, give the same tables before and after at any sample size:
`race_report.py --seeds 3` on Master and on Medium (72 matches each) and
`arena.py ladder --agents easy,medium,hard,master,grandmaster --seeds 3` (60
matches) printed the same result for every match on `origin/main` (`a9b3d8a`)
and on this branch. The full-size runs WB-062 asked for would print the same
tables twice, so they were not played.

What was measured instead is where the lode lives: `tools/prize_report.py`,
every seed played twice on a Huge map, once with each prize on the same ground,
every pairing from both corners, the layouts that hold a prize (Plains,
Crossings, Bastion) cycled by seed, seeds from 7100. The seam's side is the
game as it was on these maps, but for the brain hiring three tenths of a crew
for a seam where it hired two (the pace). The league was played on `a9b3d8a`,
before Rage and Bleeding (WB-062, above) landed: the lode's moves against the
seam are what it measures, not the races' standing since.

Races, every pair both ways, share of decided matches:

| race | Master, seam | Master, lode | Medium, seam | Medium, lode |
|---|---:|---:|---:|---:|
| dwarf | 76–63 (54.7%) | 78–62 (55.7%) | 148–138 (51.7%) | 145–141 (50.7%) |
| elf | 76–67 (53.1%) | 71–70 (50.4%) | 188–100 (65.3%) | 193–95 (67.0%) |
| human | 70–69 (50.4%) | 67–71 (48.6%) | 116–170 (40.6%) | 123–164 (42.9%) |
| orc | 57–80 (41.6%) | 63–76 (45.3%) | 121–165 (42.3%) | 113–174 (39.4%) |
| undecided | 9 | 9 | 3 | 2 |
| matches | 288 | 288 | 576 | 576 |

Master is one block of 24 seeds (576 matches), Medium two (`--first-seed 7100`
and `7124`, 1 152), as WB-062 measured them. No race moves by more than 3.7
points between the prizes, and on Medium, where one block alone moved the elves
by 5.5 and the second the humans by 7.5, the pooled moves are under three: the
lode is in band. The elves' lead on Medium is the seam's too, so it is Huge's,
not the lode's (the ladder's sizes put them at 54.2%).

The difficulties, every pair both ways (twelve seeds, 240 matches a prize),
rated with Medium anchored at 1000:

| setting | seam | lode |
|---|---|---|
| Grandmaster | 1267 (1188 .. 1369), 79.2% | 1255 (1156 .. 1360), 77.1% |
| Master | 1084 (1016 .. 1159), 55.2% | 1118 (1045 .. 1190), 60.4% |
| Hard | 1121 (1035 .. 1215), 59.4% | 1112 (1029 .. 1199), 57.3% |
| Medium | 1000, 44.8% | 1000, 44.8% |
| Easy | 713 (633 .. 786), 11.5% | 711 (629 .. 788), 10.4% |

Every rating stays inside the other's interval. Hard and Master are within
noise of each other on Huge two-seat maps with either prize, where the ladder's
sizes put Master well above Hard (`brains.DIFFICULTY_ELO`); that is Huge's, not
the lode's, and why is not measured here.

Who takes the prize and when, from the league's telemetry (`PlayerTally.mined`
and its `hall.<kind>` and `mined.<kind>` times):

| panel | prize | matches | a hall at it | first hall (median) | worked at all | gold out of it a match (mean) | share of all gold mined |
|---|---|---:|---:|---:|---:|---:|---:|
| Master races | seam | 288 | 10 (3%) | 8.0 min | 115 (40%) | 342 | 0.5% |
| Master races | lode | 288 | 13 (5%) | 8.3 min | 128 (44%) | 2 413 | 2.5% |
| Medium races | seam | 576 | 89 (15%) | 7.0 min | 203 (35%) | 990 | 1.0% |
| Medium races | lode | 576 | 142 (25%) | 7.6 min | 229 (40%) | 7 956 | 5.5% |
| difficulties | seam | 240 | 14 (6%) | 9.2 min | 78 (32%) | 568 | 0.7% |
| difficulties | lode | 240 | 26 (11%) | 9.0 min | 90 (38%) | 3 593 | 3.6% |
| four seats (Easy, Medium, Hard, Master) | seam | 24 | 4 (17%) | 6.5 min | 17 (71%) | 2 586 | 1.1% |
| four seats | lode | 24 | 14 (58%) | 8.4 min | 21 (88%) | 60 048 | 17.6% |

The halls at a lode in the race panels were every race's (Medium: elf 68,
dwarf 54, human 36, orc 36; Master: orc 5, human 4, dwarf 4); in the
difficulty panel Medium's 20, Easy's 7 and Grandmaster's 1; on four seats
Medium's 10, Easy's 6 and Master's 4.

The lode is contested where the brains reach it. On a Huge map with two seats it
lies 57 tiles from each hall, and a Master match there is settled by the first
push at a median of eight minutes, before anybody has needed a third hall; Hard
never expands at all (`PRO_HARD.expand`), so the ladder's halls at the lode are
Medium's, Easy's and one Grandmaster's. Medium, which expands on its own clock,
halls at the lode in a quarter of its race matches against a seventh at the seam,
and on four seats, where the prize lies in every cell eighteen tiles out, the
lode is worked in 88% of matches, a hall stands at it in 58%, and a median
27 700 gold comes out of it: 17.6% of all the gold the match mined, against the
seam's 1.1%. Whoever drew the most from a lode won 209 of the 229 Medium race
matches it was worked in; that is as much the winner's freedom to walk out as
the lode's gold, which is why the race and difficulty shares above, and not
this, are the balance evidence.

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
