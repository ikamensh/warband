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
