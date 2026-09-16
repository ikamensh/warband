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

## Findings

*(filled in from the first league)*
