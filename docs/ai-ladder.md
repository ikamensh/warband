# The AI ladder

How Warband's computer players are ranked, and how a new one is shown to be
stronger rather than asserted to be.

## Why a ladder

"This AI feels better" is not a claim anyone can check, and single matches
cannot settle it: the same two brains on the same twelve seeds swing between
seven and eleven wins depending only on which random stream drives the build
site jitter. Nothing below a few dozen games means anything, and most of the
numbers here come from a few hundred.

The ladder is `warband/arena.py`, driven by `tools/arena.py`.

## Running it

```bash
uv run python tools/arena.py ladder --agents hard,pro --seeds 40   # 80 games, both corners
uv run python tools/arena.py ffa --players 4 --seeds 12            # free-for-all placements
uv run python tools/arena.py variants --shuffles 6 --seeds 6       # under jittered rulebooks
uv run python tools/arena.py report --seeds 24                     # all three
```

Matches are independent and fully determined by their `MatchSpec`, so they
are handed to a process pool (`--workers`, default: most of the machine).

## What it measures

**Fairness.** Every pairing is played from every corner of the same map. A
seed that favours the north-west start cannot favour an agent.

**Free-for-all.** Three and four player games end with a placement per player
rather than a winner: last eliminated places higher, and anyone still standing
at the time cap is ranked by what they have left on the map, priced in gold
and lumber. Each game contributes every pair of its players to the ratings, so
one four-player match is six head-to-head results.

**Generalisation.** `shuffle-N` variants multiply every unit and building's
hit points, damage, cost and build time by a factor drawn from seed `N`. An
agent that only wins under the numbers it was tuned against has learnt the
table rather than the game, and the pooled rating across jittered rulebooks
says which kind it is.

## Ratings

Sequential Elo has two problems here: the answer depends on the order the
games are fed in, and an agent that never loses runs away to infinity.

`rate()` instead fits a Bradley-Terry model over all pairwise results at once
by the standard MM iteration, then converts log-strength to the Elo scale
(`400 / ln 10` points per unit). Half a virtual win and loss is added to each
pair that actually met, which keeps a perfect record finite while still
letting a longer unbeaten run rate higher than a short one. One agent is
anchored — `hard` at 1000 by default — so numbers are comparable across runs.
The interval is a bootstrap over matches, so it widens honestly when an agent
has played few games.

Because the fit is over all pairs at once, a large gap is best measured with
rungs in between: `hard` against `pro` against a stronger `pro` gives a
well-conditioned chain, where `hard` against the strongest alone would only
say "it never lost".

## Where the agents stand

**1v1** — 60 seeds it had never been measured on, every pairing from both
corners, 720 games, `hard` anchored at 1000:

| agent | Elo | 90% interval | score |
|-------|-----|--------------|-------|
| `pro` | 1534 | 1456 .. 1627 | 97.2% |
| `hard` | 1000 | — | 46.8% |
| `normal` | 994 | 952 .. 1035 | 46.0% |
| `easy` | 697 | 636 .. 745 | 10.0% |

`pro` takes **97.5%** against `hard`, 95.8% against `normal`, 98.3% against `easy`.

**Free-for-all** — each agent rotated through every corner:

| | `pro` against `hard` | games |
|---|---|---|
| three players | 88.2% | 288 |
| four players | 80.0% | 120 |

The margin narrows with the company, as it should: three opponents can wear a
leader down between them, and a placement is a softer result than a win.

**Under jittered balance** — six `shuffle-N` rulebooks, every unit and
building's hit points, damage, cost and build time multiplied by a factor
drawn from the seed, 216 games: `pro` 1446, taking **93.1%** against `hard`
under rulebooks it has never seen, against 97.5% under the one it was built
on. Whatever it has learnt, it is very nearly not this table of numbers.

Two things are worth reading off the 1v1 table. The three shipped
difficulties span about 300 Elo and `hard` beats `normal` only 55%, so "the
current AI" is one strength with three settings. And `pro` against `easy` is
98%: this game has no floor of upsets a strong player cannot escape, so the
distance between two agents is limited by the agents rather than the dice.

### Against the 2000 that was asked for

`pro` is about **535 Elo above the anchor, not 1000**. A 1000-point gap means
winning 99.7% of games — two losses in 720 rather than the eighteen it takes
now. The remaining losses are not systematic: no seed loses from both
corners, no race is broken, and the brain kills four soldiers for every one
it loses. They are games where an early rush lands before there is anything
to meet it. Every fix tried for that — early towers, peasants called to
fight, a militia rule, holding the opening lumber, reacting to a visible
rush, stronger counters against archers — measured neutral or worse, and is
recorded below.

### On seed sets

`pro` measured 96.7% against `hard` on one set of thirty seeds and 84.6% on
another set of seventy. Neither was wrong; both were too small. The
several-hundred-game figures above are the ones to quote, and the lesson is
in the rules: a few dozen games is the floor for noticing anything, a few
hundred for trusting it.

## What each change was worth

Every number below is a measured ladder result, and several of them
contradicted the reasoning that produced the change:

| change | effect |
|--------|--------|
| attacking on less information, with a smaller army | **+126 Elo** (1408 → 1534), 97.5% against `hard` where caution took 90.0% |
| …the same posture in a four player game | **−512 Elo** (1534 → 1022) until aggression was divided by the number of opponents |
| reacting to a rush the scout can see | neutral |
| a proportional counter to massed archers | neutral — but the rule it replaced had never once fired |
| directing focus fire | **−109 Elo** — it switches off the model's own kiting and retargeting |
| feeding the workforce in gradually | **−187 Elo** (1516 → 1329) against hiring it at once |
| early towers | 68.8% against `hard` where every other variant took 100% |
| answering a raid with just enough soldiers | 81% against `hard`, where sending everyone took 90% |
| more production once gold piles up | +52 Elo |
| pulling wounded soldiers out to heal | beat the baseline 68.8% |
| counting build orders in flight | −18 points on its own, good once the site limit was raised to match |
| peasants called to defend | −35 Elo, under either of the two rules tried |
| holding the opening lumber for the barracks | **−400 Elo** — it buys the barracks 64s earlier and starves the farms |

Two of those are worth dwelling on. Holding the opening lumber was reasoned
out from arithmetic — the game starts with 500 lumber, a farm costs 250 and a
barracks 450, so the second farm is what delays the barracks — and it did
exactly what it was supposed to, moving the barracks from 138s to 74s. It
also collapsed the brain to 901 Elo, below `hard`, because the farms it
displaced are what the supply cap is made of.

And the caution the brain had been taught was itself an overcorrection. It
learnt not to attack blind after a push of ten walked into a defended base;
the right lesson, at four times the dose it needed. It kills four soldiers
for every one it loses, so a fight it is unsure of is still a fight worth
having.

The build-order one is the other cautionary tale. The brain had been re-ordering the same
barracks on every pass because a building does not exist until its peasant
arrives; fixing that was plainly correct and immediately made the brain
worse, because the double-ordering had been buying a build rate nothing else
was configured for.

## The agents

| agent | what it is |
|-------|------------|
| `easy`, `normal`, `hard` | the shipped difficulties, `warband.ai.Brain` |
| `pro` | `warband.pro_ai.ProBrain` |
| `pro-*` | one-knob variants of `pro`, used to attribute its strength |

Every `pro-*` name differs from `pro` in exactly one field of `ProProfile`, so
a ladder over all of them attributes a change instead of guessing at it. This
is worth the discipline: scaling `pro`'s economy and production together looked
obviously right and cost it 84 Elo.

## Keeping the simulation honest

`tools/sim_fingerprint.py` digests whole matches — positions as exact float
`repr`, so the bits themselves have to match — and checks the result against a
recorded hash. Any change that claims to be only a speed change has to leave it
alone; lockstep online play depends on the simulation being reproducible.

```bash
uv run python tools/sim_fingerprint.py --check tools/sim_fingerprint.txt
```

A deliberate change to the rules or to `warband/ai.py` is expected to move it,
and the recorded file is refreshed in the same commit.
