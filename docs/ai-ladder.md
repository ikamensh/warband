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

## What the AI is allowed to know

The computer plays under the same fog the human does, and out of the same
purse. Both are worth stating because neither was true to begin with.

**Fog.** Every question either brain asks about the map goes through
`world.worker_knowledge[player]` — the model's own per-player memory, holding
the last observed footprint of every structure that player has laid eyes on
and the contents of every mine it has found, and nothing else. A razed
building stays remembered until somebody looks at the ground again, which is
what a player would believe. Enemy units are counted only where they are
visible. `ai.known_enemy_buildings` and `ai.known_mines` are the only doors in,
and both brains use them.

Before this the AI read `world.buildings` and `world.mines()` straight: it knew
every enemy building, tower and gold mine from the first tick, and its raiders
rode at peasants nobody had seen. Taking that away cost real strength — Master
went from about 96% against Medium to 87% — which is the measure of how much
it had been leaning on it.

It also broke the game until exploration was added. An army with no remembered
target simply stands at home, so fog-honest matches ran to the twenty-minute
cap instead of ending around seven, and the ladder slowed to a third of its
pace. Both brains now walk at the far corner when they have found nothing:
starts sit in corners, which is a guess a player can make from the map's shape
rather than something read out of the model.

**Resources.** Nothing in either brain writes gold or lumber. Every purchase
goes through `can_afford`, `can_train`, `can_research` and `build`, which are
the same gates the player's clicks pass. A test starves a brain of both income
and reserves and checks that it builds and trains nothing at all.

## The maps a ladder is played on

A rating from one map is a rating of very little, so a ladder walks the map
generator rather than a map:

* **Layout** is drawn from the seed by `mapgen` itself, so a few dozen seeds
  meet all five — plains, forest, crossings, klondike, bastion — without the
  runner asking for anything.
* **Size** is cycled per seed across all three (48×40, 64×48, 80×64). Both
  corners of a seed share a board, or the side swap would not be a swap.
* **Land** is not varied, and deliberately: summer, winter and wasteland
  generate identical terrain tile for tile and differ only in how they are
  drawn. A test pins that, so if it ever stops being true the ladder should
  start cycling it.

Map size turns out to matter to the ratings: Master measures 1561 on 48×40
alone and 1489 across all three sizes, and Hard 1299 against 1222. The brain
is a little tuned to the small map it was developed on, and the honest number
is the one across all of them, which is what the New game screen shows.

## Running it

```bash
uv run python tools/arena.py ladder --agents hard,pro --seeds 40   # 80 games, both corners
uv run python tools/arena.py ffa --players 4 --seeds 12            # free-for-all placements
uv run python tools/arena.py variants --shuffles 6 --seeds 6       # under jittered rulebooks
uv run python tools/arena.py report --seeds 24                     # all three
uv run python tools/arena.py ladder --agents pro-rush,pro-boom --against pro --seeds 24 --anchor pro --anchor-elo 1450
uv run python tools/arena.py ladder --agents hard,pro,pro-x,pro-y --neighbours 1 --anchor pro --anchor-elo 1450
uv run python tools/arena.py ladder --agents pro,pro2 --seeds 60 --save runs/pro2.jsonl   # keep every match
uv run python tools/arena.py rate --from runs/*.jsonl --anchor pro --anchor-elo 1450      # one table over saved runs
```

`--save` appends every finished match to a JSON-lines file as it lands, and
`rate --from` pools any number of them into one table: the rungs of a chain
are measured in separate runs and rated together.

`--against` plays a panel: every agent meets only the agents named, which
is how candidates are screened against the best brain without paying for
every pair. `--neighbours N` plays a chain: only agents within N places of
each other in the list meet, which is where the information is once the
list is in rating order. `--anchor-elo` pins the anchor at a rating other
than 1000, so a ladder over the top rungs can be read on the same scale as
the difficulty table below (`pro` at 1450). Every table ends with the
medians of how each agent played — first attack, attacks, peak army,
workers, towers, halls, barracks, kills — which is the evidence behind
any claim that two agents of one strength are two different players.

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

**Settled by peers.** Each pair's games are weighted by how close the two
turn out to be — a pair 200 Elo apart counts half, 400 apart a fifth, a
thousand apart almost nothing (`arena.proximity_weight`, refitted until
the weights and the ratings agree). A game against an agent a thousand
points below is nearly always won and says almost nothing about *where*
in the top half the winner sits; counting it as much as a game against a
peer is how an agent that is 55% against the best and 99% against the
worst got rated on the 99%. With twenty head-to-head games between two
peers and a hundred each against a far weaker third, the flat fit puts the
one with the perfect far record 114 points clear; weighted, 22. One pair
alone is unchanged: with nothing to weigh it against, the odds are the
odds. `--proximity 0` gives the old flat fit.

## The difficulty settings

What the New game screen offers, and what each one is worth. 60 seeds, both
corners, every map size, all five layouts in turn, under fog, 720 games,
Medium anchored at 1000, measured on 2026-09-19 once the pro brains held a
build order's price while its builder walks (`hold_builds`, below):

| setting | Elo | 90% interval | plays |
|---------|-----|--------------|-------|
| Easy | 857 | 795 .. 910 | `ai.Brain`, the Easy profile |
| Medium | 1000 | — | `ai.Brain`, what Normal and Hard both were |
| Hard | 1400 | 1335 .. 1485 | `pro_ai.ProBrain`, `pro-hard` |
| Master | 1615 | 1535 .. 1701 | `pro_ai.ProBrain`, `pro-vanguard` or `pro-warden`, drawn with the map |

Each beats the one below it 69%, 88% and 78% of the time. The hold moved Hard
47 points and Master 26 from the measurement before it, on 2026-09-18 after the
balance merge (mine cap, prices, race numbers; `docs/balance.md`) and the rules
that went live with Warband 0.2.26: 856, 1353 and 1589, with steps of 69%, 87%
and 80%. Before that measurement the screen had
shown 740, 1250 and 1510: Easy and Hard were outside their intervals, and
Master's number had been inferred from the brain it replaced rather than
measured. Master is measured directly now. The 720 games took five minutes
where the same protocol used to take hours: a match stops once it is settled
rather than at the last building (`arena.SETTLED_ARMY`), which calls the same
placements as playing it out.

The measurement it replaced — the same protocol with the layout left to the
seed, on 2026-09-16, after blows were given a turn and a wind-up and shots
became projectiles (`docs/unit-motion.md` part 4):

| setting | Elo | 90% interval | plays |
|---------|-----|--------------|-------|
| Easy | 736 | 672 .. 799 | `ai.Brain`, the Easy profile |
| Medium | 1000 | — | `ai.Brain`, what Normal and Hard both were |
| Hard | 1253 | 1209 .. 1302 | `pro_ai.ProBrain`, `pro-hard` |
| Master | 1510 | — | `pro_ai.ProBrain`, `pro-vanguard` or `pro-warden`, drawn with the map |

Master's number is the rung's: the brain that measured 1452 on this
protocol (`pro`, still on the ladder under that name) plus the 57–61% its
two postures take against it over four seed sets each. The three lower
rows are the 720-game protocol. Measured directly against Hard and Medium
(40 seeds, both corners, 80 games a pairing), the two-posture Master takes
76% and 94% where `pro` on the same seeds takes 79% and 99% — 1485 to
`pro`'s 1521 on that run, within a sample of eighty games' noise of each
other and of the 1452. So the rung is an edge over the brain Master was,
not a step against everything below it: the postures were chosen by how
they fare against their nearest opponent, which is what a rating settled
by peers rewards, and a player who wants the difficulty step should read
this row as "about 1500, a different opponent" rather than "sixty points
harder". Each of those beats the one below it 84%, 82%, 78% of the time — a real step every
time, which the old three settings did not have: Normal and Hard measured 994
and 1000 and split their games 55/45. They are one setting now, and the
screen shows each rating beside its button so the choice is not a guess.
Before the combat rework the same protocol gave 768, 1000, 1218 and 1420 with
steps of 81%, 77% and 78%: the slower blows moved nobody's standing. (A
12-seed run had put Easy at 573 first; that was the sample, not the rules.)
None of the brains reaches a workshop in a 20-minute match against another
brain, so the catapult rules — stones on the ground, own-side splash, the
minimum range — are exercised against a human, not on this ladder; with three
catapults handed to each Medium side at minute one they threw 65–74 stones a
match, two thirds at buildings, and never hit their own side.

Hard is not a hobbled Master by accident: it is the same brain thinking once
every second and a half, on six peasants a mine, with one barracks a hall, no
scouting, no raiding, no expansions, and back on the cautious posture Master
gave up. Every one of those is a knob the ladder measured.

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

### Measuring against a saturated opponent

Master takes 88-95% against Medium depending on the seed set, which is close
enough to the ceiling that Medium can no longer tell two strong brains apart:
a candidate 50 Elo better and one 50 Elo worse both read as "about 90%". Once
that happens the ladder has to be run against the best agent, not the anchor.

That was done. Six candidates — thinking twice as often, a bigger workforce,
six barracks a hall, more farms, earlier and further expansion, and a shorter
leash on pushes — were rated against Master over 1008 games. Five of them
landed between 47% and 53% against it, which is nothing, and the sixth (more
farms) was clearly worse. The plateau is in the brain, not in the ruler.

### What decides a Master mirror

Before looking for the next rung, 48 games of `pro` against itself (24
seeds, both corners, every size, after the combat rework) were traced to
see what a game between two copies of the best brain turns on. Every one
was decided, in 8.4 minutes at the median, and almost every one the same
way: both sides march out at about 200 s with five soldiers, the armies
meet, and the side with more wins the fight and the game. The winner's
peak army is 33 at the median, the loser's 12; the winner kills 54 and
loses 24. There is no second act.

Two things set the size of the army at the clash.

**Lumber.** A snapshot at 150 s shows a side with 2900 gold in the bank,
one barracks, 350 lumber and a supply cap it has just hit; two minutes
later the same side has 3000 gold, 100 lumber and 29 of 29 supply. The
model's gatherer policy reserves one farm's worth of wood and sends every
other hand to the gold, which is a fair rule for a player and far too
little for a brain that spends 250 lumber per four supply and a farm's
worth twice over on every barracks, mill and hall. The supply block also
closes the gate on the second barracks — a barracks that is idle for want
of supply reads as "not saturated" — so the gold sits. The winner of a
mirror is supply-blocked with gold in hand for 72 s at the median; it is
simply the side that got blocked later.

**Race.** The brain plays every race with the same numbers and the same
minute, and the races do not train or walk at the same speed:

| race | mirror games | won | peak army | first attack |
|------|--------------|-----|-----------|--------------|
| elf | 16 | 75% | 20 | 222 s |
| human | 26 | 62% | 33 | 198 s |
| orc | 24 | 42% | 21 | 197 s |
| dwarf | 30 | 33% | 18 | 219 s |

Dwarves walk 0.3 slower and orcs arm 10% slower, so their five arrive
later and fewer, against elves whose rangers shoot a tile farther and
humans whose barracks turn out a soldier every 13 s instead of 15. A
quarter of the games either brain plays are lost or won on the draw of
the race, which a race-aware profile can take back.

### The opening, traced tick by tick

Three things in Master's first three minutes are not decisions but
accidents of ordering, found by printing every peasant's order at every
tick:

* **The farm at second zero is dropped.** The pass trains before it
  builds, the hall queues two peasants for 800 of the 1000 gold, and the
  farm ordered in the same pass finds 200 in the bank when its peasant
  arrives. It goes up again at eleven seconds and stands at thirty-eight;
  the hall is capped at five and idle for most of that time.
  `builds_before_peasants` holds the peasant back when a farm in flight
  could not then be paid (farms only: a peasant that delays a barracks is
  still income).
* **The mill is bought before the barracks.** The wish list puts the
  barracks first, but the mill costs 600 gold to the barracks' 700, so
  whenever the bank is between the two the mill is what gets bought — and
  its 450 lumber is the barracks' 450 lumber, a minute of chopping later.
  Both brains in a mirror have their first barracks at about three
  minutes. `barracks_first` wishes for nothing but farms until it stands,
  and lands it at about two.
* **The wood share had been measuring nothing.** A third to a half of the
  miners are inside the mine at any moment, and the first version of the
  rule took its share of the rest, so "thirty per cent on wood" put almost
  nobody there. The 17% it scored against Master was the score of a rule
  that did not run; the share is of the whole workforce now.

### The first rung above Master

Everything that measured stacks into one posture: nothing but farms before
the first barracks, the lumber panic a minute earlier, one tower at the
front point as soon as the barracks stands, and marching out at eight
soldiers on level terms. Over three seed sets it had never been tuned on:

| candidate | games against `pro`, by seed set | score |
|-----------|--------------------|-------|
| `pro-rax-panic-tower1-min8` (the Warden without its counter) | 72, 120, 120, 80, 120 | 67%, 57%, 61%, 54%, 60% — 60% pooled |
| `pro-warden` as shipped (with the counter) | 80, 120, 80 | 60%, 65%, 65% — 64% pooled |
| `pro-rax-panic` (the same without the tower or the wait: out at five) | 96, 120 | 67%, 60% |
| `pro-raxfirst` (barracks-first alone) | 72, 72, 96, 120 | 60%, 64%, 59%, 48% — 57% pooled |
| every barracks-first variant pooled | about 2400 | 57% |

That is about **+50 to +70 Elo**, a first rung at roughly 1510, and the
swing between seed sets of the same size is six points either way, which
is why nothing under a hundred games on two sets is quoted. It is two
players rather than one: `pro-rax-panic` walks out at five soldiers at
195 s with no tower, `pro-rax-panic-tower1-min8` builds a tower first and
walks out at eight at 245 s, and the two score the same. The gains do not
add: the tower, the later push and the kill memory each took the same
60% on top of barracks-first as barracks-first took alone, because they
all decide the same fight.

Where the losses are is now on the ladder table too, by the race drawn.
Over the combined ladder's 600 games whoever drew orcs won 22–41% and
dwarves 31–62%, elves 72–91%, under every profile including Master: the
elven rangers outrange and outrun the orcs' throwers and grunts, and the
brain plays every race by the same numbers. A quarter of the games on the
ladder are decided by that draw before either brain moves, which caps what
any posture change can take — and is where the next rung has to come from.

### The scout that never left

Tracing a tower rush on Master's mine turned up why every profile attacks
blind: the peasant drafted as the scout keeps the harvest order it was
drafted with, the ring move is only given to a scout with nothing to do,
and the gatherer policy refills an idle peasant before the next pass — so
no brain without a rider has ever sent anyone to look, and the enemy is
unknown until its push arrives. That is the ground the blind-attack
posture measured +126 on. Sending the peasant (stop it, keep it off the
policy) was measured on both postures: **44% and 39%** against Master,
against 55% blind, with peak armies of 13 to the blind Warden's 22. The
engagement rule is tuned for not knowing — a prior of four tenths of its
own strength stands in for an enemy nobody has looked at — and given real
sightings it waits while Master attacks. Using what a scout sees takes a
different engagement rule, not a scout, so the peasant stays home and the
comment in `_send_scout` says why. The rush itself was dropped: the
builder's order dies on arrival after a forty-second walk, five times a
game, and feeds peasants to the first soldiers.

### The wasp that would not live

Master's defence sends the whole army at any enemy unit within nine tiles
of any of its buildings, every pass, so one fast unit circling its base
looked like a way to keep that army home for as long as the unit lived.
Scripted directly — a scout handed to Master's opponent at 100 s and
driven round the elven hall at eight or ten tiles, still or at two laps a
minute — it lived forty seconds every time: rangers see eight tiles and
shoot five, and the first push left at 184 s whatever the wasp did.

### What the 2000 still needs

Every probe of this brain's numbers lands within a hundred points of
Master, on either side. The gains that measured — barracks first, the
earlier lumber panic, the tower and the later push — all decide the same
first clash, and stack to one rung of sixty or seventy points rather than
to the two hundred a real step takes. What decides the rest is settled
before either brain moves: the race drawn (orcs lose three in four to
elves under every profile), the corner, and the roll of the first fight.
A 2000 on this scale is 550 above Master, which means winning nine games
in ten against it — every orc game, every bad corner — and no posture of
this brain does that. The next rung needs a different kind of strength:
play that changes with the race and the map rather than the same numbers
for all of them, or fights that are not left entirely to the model. The
tooling for measuring it is here: `--save` a run, `rate --from` the pool,
read the score by race, and rate the rung against its neighbours.

### Against the 2000 that was asked for

`pro` is about **535 Elo above the anchor, not 1000**. A 1000-point gap means
winning 99.7% of games — two losses in 720 rather than the eighteen it takes
now. The remaining losses are not systematic: no seed loses from both
corners, no race is broken, and the brain kills four soldiers for every one
it loses. They are, almost all of them, one shape: the brain ends with a peak army of
two or three and no soldiers at four minutes. Tracing them lands on the wood.
On a map where the trees near home run out — `bastion` especially, which walls
a player in — lumber reaches zero, no farm can be built, the supply cap
freezes at twenty-five, and fifteen thousand gold sits in the bank buying
nothing while the soldiers that do trickle out die one at a time. Every fix tried for that — early towers, peasants called to
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
| six further candidates rated against Master itself | all neutral, over 1008 games |
| spare hands to the trees when the lumber runs out | 53.5% over 340 games — suggestive, not established; kept because it fixes a diagnosed pathology |
| directing focus fire | **−109 Elo** — it switches off the model's own kiting and retargeting |
| feeding the workforce in gradually | **−187 Elo** (1516 → 1329) against hiring it at once |
| early towers | 68.8% against `hard` where every other variant took 100% |
| answering a raid with just enough soldiers | 81% against `hard`, where sending everyone took 90% |
| more production once gold piles up | +52 Elo |
| pulling wounded soldiers out to heal | beat the baseline 68.8% |
| counting build orders in flight | −18 points on its own, good once the site limit was raised to match |
| peasants called to defend | −35 Elo, under either of the two rules tried |
| holding the opening lumber for the barracks | **−400 Elo** — it buys the barracks 64s earlier and starves the farms |
| nothing but farms before the first barracks stands (`barracks_first`) | **+65 Elo** — 60% over 72 games; the barracks lands at two minutes instead of three |
| …with the later push, or the kill memory, on top | 59% and 57%: the gains overlap rather than add |
| …with the later push and one tower at the front point as soon as the barracks stands (`towers_early`) | **67%** over 72 games on a third seed set, where barracks-first alone took 64% and every barracks-first variant 54–64% (59% pooled over 432); being confirmed on a fourth |
| holding a peasant back so the farm ordered at second zero is not dropped | level (50%), and it cancelled barracks-first when combined |
| an early blacksmith for Sharpened Blades | level (47–54%) |
| …with the lumber panic a minute earlier (`panic_gold` 1000, `lumber_floor_panic` 300: half the hands to the trees once lumber is short and a thousand gold idles) | **67%** over 96 games where barracks-first alone took 59% on the same seeds |
| …with less farm slack (`supply_slack` 2) | 64% on the same seeds |
| the mill at the edge of the nearest wood, a second mill at the wood front, a larger workforce | level with barracks-first alone (52–56%); the wood is six tiles from every start |
| the barracks itself at the front point, so Master's push meets tower, army and reinforcements in one place | **−35 Elo** (45% against Master, 43% against the Warden, 160 games each) |
| a raid too small to matter met by three soldiers rather than the whole army | level (51% and 52%, 141 games each) |
| dwarves and orcs holding harder — two towers, out at ten | level against Master, 44% against the Warden (149 games) |
| a farm only when supply is about to block, until the barracks stands (an opening slack of 1 or 2) | **−50 to −100 Elo** for the Warden (42%, 46% over 80 games), level for the Vanguard (54%): the farms it holds back are the supply the army is made of, again |
| a beaten push followed home at once, whatever the army's size | level (50%) |
| the counter to shooters earlier and harder (`counter_from` 0.2, `counter_strength` 2.0) on the Warden | **+25 Elo** on top of the posture — 60% and 65% on two seed sets where the Warden alone took 54% and 60%, 63% pooled over 200 games; the gain lands on humans and dwarves, not the orcs it was aimed at; worse on the Vanguard (51%) |
| the same, harder still (0.15, 3.0) | 61% pooled: no better |
| the Warden's combat knobs: pulling a wounded soldier out at 40% instead of 25%, at 15%, a combat pass every 0.1 s instead of 0.2, pushing through raids up to 70% of the army | level (65%), −50 (52%), −30 (55%), level (59%) against the Warden's 65% on the same 80 games |
| marching out at eight to ten soldiers on level terms instead of five on a guess (`min_army` 8–10, `attack_ratio` 1.0) | **+40 Elo** — 55–57% against Master over 96 games each, 55% pooled over 576; the one posture change that measured |
| soldiers seen to die dropped from the enemy count at once (`count_kills`) | +20 Elo alone (53%), about the same on top of the later push |
| a standing share of the workforce on wood | **−40 to −180 Elo** — 46% at 30%, 31% at 40%, 25% with farms ahead of demand as well; the model's own policy is better |
| an army plan of knights, of archers, or of raiders | **−110 Elo** each (33%); the race plans are right |
| pro-rush (three soldiers, ratio 0.6), pro-boom (twelve, 1.2, early expansion, towers), hall-first pushes, raiders | within noise (44–52%) |
| holding a build order's price while its builder walks (`hold_builds`): the brain had spent it on soldiers, peasants and research during the walk, and 227 of 838 orders over twenty Master mirrors died on arrival, unpaid; none do now | **+60 to +100 Elo** — 65% for the Vanguard, 62% for the Warden, 59% for Hard against the same posture without it, 96 games each; Hard's and Master's displayed ratings re-measured |
| a supply-blocked barracks counting as saturated, a second or third barracks ahead of the gate, gathering three or five before walking, race-aware postures for dwarves and orcs | within noise (48–56%, 48 games each) |

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
and the recorded file is refreshed in the same commit. The recorded hash is
macOS's: glibc and the Windows runtime round a few of the simulation's sines,
cosines and arctangents differently in the last bit, so on Linux or Windows the
same source hashes differently.

The ladder itself runs the simulation compiled (`docs/fast-simulation.md`),
about ten times faster than the source and to the same bits:
`tests/warband/test_fastsim.py` plays this fingerprint compiled, and
`tools/sim_bench.py --check tools/sim_bench.txt` times nine whole arena matches
and checks their results against the recorded digest.
