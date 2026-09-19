# Warband maps: a generator with five layouts

Design note, 2026-09-15, implemented the same day in `warband/mapgen.py`
(the section *What was built* at the end records where the build departs
from the plan). The fairness audit runs inside the generator; the per-seed
tests are `tests/warband/test_mapgen.py` and `tests/warband/test_maps.py`,
the numbers over many seeds come from `tools/map_report.py`.

## The proposal in short

Replace "one kind of map with three palettes" by **five named layouts** the
player picks on the New game screen, each a different game in the way Age of
Empires' Arabia, Black Forest, Arena and Gold Rush are different games, plus
**Any**, which draws one from the seed. All five share one skeleton: bases
placed by exact symmetry, a main mine, a natural expansion that needs its own
hall, contested third mines in the middle, edges of forest, every base and
mine reachable within the pathfinder's budget. The layouts differ in what the
walls are made of (nothing, trees, water, rock), where the gold is, and how
many ways there are from one base to another.

| Layout | One-line promise | Walls | Gold | Ways between bases |
|--------|------------------|-------|------|--------------------|
| Plains | Open ground: raids come early, expansions lie exposed | scattered groves and ponds | main, natural, thirds spread evenly | many |
| Forest | Deep woods: narrow paths, hidden clearings, chop your own way through | trees everywhere (soft: 5 s a tile) | main, a natural hidden in a clearing, thirds in the middle clearing | two winding paths, plus any you cut |
| Crossings | A river splits the land: hold the fords or find the long way round | one river, permanent | thirds sit on the banks by the fords | three fords: a wide short one, two narrow long ones |
| Klondike | Little gold at home; the rest lies in a walled pit in the middle | a rock ring with three gates | 20 k at home, 4 × 30 k in the pit, a poor 10 k mine in each free corner | many, but the gold is in one place |
| Bastion | Walled in: boom in safety, then break out and fight for the middle | a tree ring around each base with one gate | main inside, natural just outside the gate, thirds in the open middle | one gate each, plus any you cut |

Theme (summer, winter, wasteland) stays what it is today, the palette, and
stops steering terrain density; layout owns the shape.

## What Warband is, as a map problem

The numbers a map has to respect (Medium is 48 × 40 tiles; corner to corner
between halls is about 43 tiles):

| Fact | Value | Consequence for maps |
|------|-------|----------------------|
| Walk corner to corner, Medium | footman 18 s, knight 13 s, scout 10 s, catapult 27 s | Rush distance is short by nature; a layout lengthens it with detours, not size |
| Walk corner to corner, Large (64 × 48) | footman 25 s, catapult 38 s | Large is where three paths and a long flank route fit |
| Main mine | 50 000 gold; five peasants take about 49 gold/s, empty in 17 min | A match that runs long *must* expand; the natural is not optional |
| Expansion mine | 30 000 gold; five peasants empty it in 10 min | Thirds get fought over twice: taking them and holding them |
| A tree | 5 s to fell, 100 lumber, blocks movement | Forest is a **soft wall**: three tiles thick costs one peasant 15 s. Elves with Regrowth get it back after 60 s |
| Water and rock | block movement, permanent | The only hard walls; no boats, no flying, no high ground |
| Guard tower | range 6 (elves 7), sight 8 | A three-tile gate is covered by one tower each side |
| Catapult | range 7 (8 with Siege Engineering), splash | The answer to a towered gate; the reason a closed map still ends |
| Sight | peasant 4, footman 5, archer 6, scout 8, elves +2 | Clearings and walls hide armies; scouting matters on closed maps |
| Base footprint | hall 3 × 3, mine 3 × 3 plus a free ring, clearing radius 7 | A base site needs about 120 open tiles; the audit already demands 90 |
| AI | expands to a mine more than 14 tiles from its hall; raids mines that enemy workers stand at; attacks by walking its army at enemy buildings; bounded A* of 3 000 expansions | Naturals sit 16–20 tiles out so the AI builds a hall there; every route must be found inside the budget or units stall at a wall |
| Sizes and seats | 40 × 32, 48 × 40, 64 × 48; 2–4 players; the edge row is trees | Features are sized in tiles per size, not scaled |

## What today's generator makes

`mapgen.generate` puts a hall in each corner with the mine five tiles away
and a wood beside it, warps four noise regions (meadow, woodland, wetland,
rock) between them, carves grass corridors until every base reaches the
first, and drops two or three expansion mines on the openest ground away from
the bases. Six Medium seeds side by side (rendered 2026-09-15 with
`title.preview_image`, [contact sheet](evidence/warband-maps-2026-09-15/current-medium.png)):

- Every map is the same map: one lake, one rock patch, a few groves, bases in
  the corners, expansions on open ground. Nothing to read in the preview,
  nothing to plan around.
- No structure to fight over: no choke, no natural, no contested resource.
  The first fight happens wherever the armies meet.
- Not symmetric. The audit keeps every start *sufficient* (open ground,
  mine, wood, connectivity) but not *equal*: one player's expansion mine is
  ten tiles away, the other's twenty.
- The carving step can open corridors anywhere, so even a seed that happened
  to grow a wall loses it.

It is fair enough and it works, which is why it is the right base for
Plains. It is not engaging.

## What the best maps do

Distilled from the ranked map pools of Age of Empires II, the melee-map
guides of StarCraft II and Warcraft III, and the procedural-generation
literature on RTS maps (sources at the end).

1. **A map is a named promise.** Arabia means open ground and early
   aggression; Black Forest means trees, chokes and a late fight; Arena means
   a walled start and a boom; Gold Rush means all the gold in the middle and
   a fight for a monopoly. Players choose the *game* they want by choosing
   the map, and they learn a map's openings. A random generator earns that
   by having a few layouts that stay recognisable across seeds, not by
   maximising variety per seed.
2. **Fairness by symmetry.** Competitive StarCraft maps are two or four
   identical parts; rotational symmetry for two players, mirrored for four.
   Blizzard's Warcraft III guidelines ask for equal distances from every
   base to the next, equal worker travel to trees, identical base entrances.
   Symmetry makes every loss the player's own fault, which is what keeps
   people rerolling.
3. **A base grammar: main, natural, thirds.** The natural is the next
   logical base, close to the main and defensible from it; the third and
   later bases are in contested ground. Chokes are made by limiting the
   entrances to the main and the natural. The expansion ladder is what gives
   the middle game a plot.
4. **Force interaction.** Limited high-value expansions and a central
   feature make the players meet; a map with plenty of everything at home is
   a map where nothing happens.
5. **Even the rush distance, then give paths of different length.** Two or
   three routes between bases, a short risky one and a long safe one, so a
   single wall or tower line does not decide the game and armies can flank.
6. **Small and uncluttered.** Blizzard notes that smaller melee maps are the
   popular ones and warns against crowding them with features.
7. **Measure it.** Togelius et al. evolve maps against objectives (base
   distance, resource fairness, choke points, path lengths); PSMAGE scores
   StarCraft maps on start-location distribution and choke-point symmetry
   among others. Warband already has `audit`; each layout gets its own
   structural assertions on top.
8. **Warcraft II's own lesson.** Its maps shape lanes with forests that
   peasants can cut, and its gold is finite: the Gold Rush map's blurb tells
   the player to expand early and often. Trees as soft walls are Warband's
   most distinctive map material and should be used on purpose.

## The layouts

Sketches are point-symmetric halves of a Medium map at one character per
two tiles: `H`/`h` halls, `$` main and third mines, `n` naturals, `s` a small
start mine, `p` a poor corner mine, `g` a gate, `T` trees, `~` water, `#`
rock, `.` grass. Shapes, not pixels; the real thing has noise on every edge.

### Plains

    TTTTTTTTTTTTTTTTTTTTTTTT
    T......................T
    T$.........n...........T
    T..H...........TT......T
    T.......TT.....TT......T
    T.......TT.............T
    T............~~~.......T
    T............~~~.......T
    T.TT..TT.........$.....T
    T.TT..TT$..............T
    T..............$TT..TT.T
    T.....$.........TT..TT.T
    T.......~~~............T
    T.......~~~............T
    T.............TT.......T
    T......TT.....TT.......T
    T......TT...........h..T
    T...........n.........$T
    T......................T
    TTTTTTTTTTTTTTTTTTTTTTTT

**Promise.** Open ground: raids come early, expansions lie exposed.

**Recipe.** Today's noise terrain retuned: no large water or rock region,
groves of 6–20 trees and ponds of 6–12 tiles scattered so that no straight
line between two halls is blocked for more than a few tiles. Wood is
deliberately modest away from the bases (the Arabia rule: manage your
lumber). Natural along the home edge, 16–20 tiles from the hall; thirds in
the middle band, each within 10 tiles of the straight line between the two
nearest halls.

**Decisions.** When to leave the base to take the natural; whether to tower
it; scouts and knights pay off because nothing slows them; a lumber mill by
a grove is a target.

**Races.** Humans (Horse Breeding) and Orcs (Plunder) are at home here;
Dwarves want walls they do not get.

**AI.** Nothing new: this is the map the AI was tuned on.

**Audit.** Symmetry; natural distance 16–20 and nearer its own hall than any
enemy by a factor of 1.5; a straight walk between any two halls detours by
at most 1.3 ×; trees 12–22 % of the map, water under 8 %.

### Forest

    TTTTTTTTTTTTTTTTTTTTTTTT
    T.....TTTTTTTTTTTTTTTTTT
    T$.....TTT...TTTTTTTTTTT
    T..H.......n..TTTTTTTTTT
    T......TTT...T..TTTTTTTT
    T.....TTTTTTTTTT.TTTTTTT
    TTT..TTTTTTTTTT.TTTTTTTT
    TTTT.TTTTTTTTTT.TTTTTTTT
    TTTT.TTTTT.....TTTTTTTTT
    TTTT.TTTT.$....TTTTTTTTT
    TTTTTTTTT....$.TTTT.TTTT
    TTTTTTTTT.....TTTTT.TTTT
    TTTTTTTT.TTTTTTTTTT.TTTT
    TTTTTTTT.TTTTTTTTTT..TTT
    TTTTTTT.TTTTTTTTTT.....T
    TTTTTTTT..T...TTT......T
    TTTTTTTTTT..n.......h..T
    TTTTTTTTTTT...TTT.....$T
    TTTTTTTTTTTTTTTTTT.....T
    TTTTTTTTTTTTTTTTTTTTTTTT

**Promise.** Deep woods: narrow paths, hidden clearings, chop your own way
through.

**Recipe.** Start from solid trees. Cut a base clearing (radius 7), a
natural clearing (radius 4) 14–18 tiles away joined by a short path, and one
middle clearing on the map's centre holding the thirds. Join every clearing
to the middle by a winding path two tiles wide (a random walk biased towards
the target, then widened), and add one longer path from the natural to the
middle so each base has two ways out. Paths never run straighter than a
detour factor of 1.4, so a scout cannot see down them. Ponds and rock only
as decoration inside clearings.

**Decisions.** Towers at the two path mouths hold a base against far more
than they cost; a peasant cutting a third path is a flank the enemy cannot
see; catapults are how a towered mouth falls; lumber is free, so the
lumber-hungry units (archers, catapults, knights) come earlier.

**Races.** Elves: Regrowth closes the paths behind them and reopens their
own; Longbows reach past a two-tile path. Dwarves (Stonework) turtle best.

**AI.** Its army walks the path; its raiders will find the natural by the
short path. The risk is the pathfinder: a Large Forest hall-to-hall route is
80–110 tiles with turns, and A* under 3 000 expansions can give up in a maze
and send the army to the "nearest reachable tile", i.e. into a wall. The
audit runs the production pathfinder, not a flood fill, between every door
and mine; a map whose route is not found is rejected and regenerated. If
Large Forest rejects too often, raise the budget and re-measure with
`tools/perf.py`.

**Audit.** Symmetry; every hall has exactly two path mouths of width 2–3 at
the clearing's edge; the shortest walk between halls detours by at least 1.4
× and at most 2.0 ×; the natural is not visible from any path mouth but its
own; trees 55–70 %.

### Crossings

    TTTTTTTTTTTTTTTTTTTTTTTT
    T......................T
    T$.........n....TT.....T
    T..H............TT.....T
    T......TT..............T
    T......TT..............T
    T........$.............T
    T........#...........~~T
    T...............~~~~.~~T
    T....$...~~..~~~~~~~~..T
    T..~~~~~~~~..~~...$....T
    T~~.~~~~...............T
    T~~...........#........T
    T.............$........T
    T..............TT......T
    T..............TT......T
    T.....TT............h..T
    T.....TT....n.........$T
    T......................T
    TTTTTTTTTTTTTTTTTTTTTTTT

**Promise.** A river splits the land: hold the fords or find the long way
round.

**Recipe.** One river, 3–5 tiles wide, from edge to edge through the centre
with two or three bends (a smoothed random polyline, point-symmetric), each
player on their own bank. Three fords: a wide one (6 tiles) near the centre
and a narrow one (3 tiles) near each edge, so the short route is the exposed
one and the long routes are the safe ones. A rock outcrop flanks the centre
ford on each bank. Thirds sit on the banks just off the fords, one per
player on the home bank and none in the water's way, so taking a third means
standing where the enemy crosses. With four players the river becomes a
cross of two rivers and the fords a ring; with three players the third
seat's bank holds the empty seat's mine.

**Decisions.** Which ford to tower, which to leave; whether to cross at the
centre in force or walk the edge with a raid; expansions on the far bank are
possible but on the wrong side of the water.

**Races.** Elven sight reads the far bank; Dwarven mortars (Blasting Powder)
punish a crowd on a narrow ford; Human horses make the long ford short.

**AI.** Walks the shortest ford; a human learns to meet it there. Add a
`fuzz.py` run per layout to be sure no wave stalls on a ford's rock.

**Audit.** Symmetry; the two banks are connected only through the fords
(remove the ford tiles and the halls are in different regions); ford widths
as specified; the centre ford route between halls is at most 1.2 × the
straight distance, the edge fords 1.6–2.2 ×; every third within 8 tiles of a
ford and nearer its own hall.

### Klondike

    TTTTTTTTTTTTTTTTTTTTTTTT
    T......................T
    Ts............TT....p..T
    T..H....TT....TT.......T
    T.......TT.............T
    T......................T
    T......................T
    T........######........T
    T..TT...##...$##.......T
    T..TT.....$....#.......T
    T.......#....$.....TT..T
    T.......##$...##...TT..T
    T........######........T
    T......................T
    T......................T
    T.............TT.......T
    T.......TT....TT....h..T
    T..p....TT............sT
    T......................T
    TTTTTTTTTTTTTTTTTTTTTTTT

**Promise.** Little gold at home; the rest lies in a walled pit in the
middle.

**Recipe.** Plains ground, but the start mine holds 20 000 gold (seven
minutes for five peasants: enough for a barracks and a first wave, not for a
second hall) and there is no natural. A rock ring of radius 8–10 on the
centre with three gates 3–4 tiles wide, one facing each player (on the
symmetric copy the third gate lands on the empty side); four mines of
30 000 inside, spaced so two halls fit. Each corner without a player gets a
poor mine of 10 000 far from everyone: the coward's gold, enough to lose
slowly. A `Building.gold` of a mine is already per mine (expansions hold
`EXPANSION_GOLD`), so the layout sets three sizes and nothing in the rules
changes.

**Decisions.** The whole game: when to move into the pit, whether to hold a
gate with towers against the other player's gate, whether to take the poor
mine and go long. Every match on this layout has a middle game.

**Races.** Dwarves (Deep Mining) squeeze more out of the same pit; Orcs
(Plunder) get paid for razing the enemy's pit hall.

**AI.** When the small mine is empty the AI already builds a hall at the
nearest mine (`Brain`: a mine farther than 14 tiles gets its own hall), which
is a pit mine, so it walks into the pit on its own. Check with
`tools/ai_report.py` that Hard still beats the scripted opening here; if the
AI starves before moving, lower its expansion trigger on this layout.

**Audit.** Symmetry; start mine 20 000, pit mines 30 000, corner mines
10 000; the pit is enclosed except at its gates (remove the gate tiles and
the pit is its own region); each player's gate is nearer their hall than any
other gate; a hall fits beside every pit mine (90 open tiles).

### Bastion

    TTTTTTTTTTTTTTTTTTTTTTTT
    T.....TT...............T
    T$.....gT..............T
    T..H...gTn.............T
    T......TT.......#......T
    T.....TT........#......T
    TTT.TTT................T
    TTTTTT..$.....$........T
    T..........~~..........T
    T..........~~..........T
    T..........~~..........T
    T..........~~..........T
    T........$.....$..TTTTTT
    T................TTT.TTT
    T......#........TT.....T
    T......#.......TT......T
    T.............nTg...h..T
    T..............Tg.....$T
    T...............TT.....T
    TTTTTTTTTTTTTTTTTTTTTTTT

**Promise.** Walled in: boom in safety, then break out and fight for the
middle.

**Recipe.** A tree ring 4–5 tiles thick around each base clearing (radius
8) with one gate three tiles wide; the gate faces sideways along the home
edge, never straight at the centre, so the walk to the enemy bends. The
natural sits just outside the gate, 14–18 tiles from the hall. The middle is
open Plains ground with a pond or rock spine on the centre and the thirds
either side of it. The ring is trees on purpose: a peasant cuts a second
gate in a minute, a catapult does not need to, and Elves grow the wall back.

**Decisions.** Boom behind the wall or come out early; tower the gate or
save for knights; cut a back gate for a raid and risk that the enemy uses
it; when to take the exposed natural.

**Races.** Dwarves: the natural turtle; Elves: Regrowth makes the wall
theirs. Orcs lose their early edge and get it back at the natural.

**AI.** Its waves funnel through the gate: the most legible fights the AI
offers. Its own peasants will cut the wall when a tree is the nearest wood;
make the start wood a grove *inside* the ring so the wall stands for the
first ten minutes.

**Audit.** Symmetry; the ring is closed except at the gate (a flood fill
from the hall with the gate tiles blocked stays inside the ring); gate width
3; the natural nearer its own gate than any other hall; ring thickness 4–5
everywhere (no seed may grow a ring a single tile thin).

### Any

Not a generator: the layout is drawn from the seed, so a seed still
reproduces the whole match and Reroll changes both. The New game caption
shows what was drawn ("Any · Forest"). It is the default, because the point
of five layouts is that the next match differs from the last.

## The shared skeleton

Everything the layouts have in common, in the order the generator does it.

1. **Symmetry.** Generate one wedge, copy it. Two players: point reflection
   through the centre (bases in opposite corners, as now). Four players:
   mirror in both axes (works on 48 × 40; rotation would need a square).
   Three players: the four-player skeleton with the fourth seat empty; the
   empty seat keeps its natural as a neutral 30 000 mine, the map's best
   third. Exact symmetry looks made rather than grown; that is what
   competitive maps look like, and the noise on the edges is symmetric too.
2. **Start kit.** Hall with its peasants spawned on the side facing the
   centre, main mine five tiles away, a grove of 12–16 trees five to seven tiles away, clearing radius 7.
   Unchanged from today; the tests already check it.
3. **Natural.** 30 000 gold, 16–20 tiles from the hall (beyond the AI's
   14-tile expansion trigger), nearer its own hall than any enemy by 1.5 ×,
   90 open tiles around it. Forest hides it; Klondike has none.
4. **Thirds.** 30 000 gold in the contested middle, equidistant to the two
   nearest halls within 3 tiles. Two players: two; three: two plus the empty
   seat's; four: four. Small drops one, Large adds one.
5. **Layout pass.** The layout's own terrain on the wedge, before the copy.
6. **Routes.** Layouts build their paths deliberately (Forest cuts them,
   Crossings leaves fords, Klondike and Bastion leave gates). Carving stays
   only as a last resort and obeys the layout: two tiles wide, through trees
   only, never through a river, a pit wall or a ring. A map that would need
   a forbidden carve is rejected.
7. **Audit and retry.** `audit` grows a `layout` section with the assertions
   listed per layout, and the walkability check uses `path.find_path_grid`
   with the production budget between every hall door and every mine door
   (a flood fill proves connectivity, not that units will find it). A map
   that fails is regenerated from a stream the seed derives
   (`seed * 16 + attempt`), up to eight times, then the generator raises
   `NoFairMap`: a layout that cannot make a fair map at some size is a bug
   to fix, not a fallback to hide, and `tests/warband/test_properties.py`
   asks for a fair map within twenty seeds at every setting New game offers.
   A few seeds in a thousand exhaust their eight tries all the same (Small
   with two seats, Medium with three: WB-046). Where the game drew the seed
   (New game, the next match, a room, the title's backdrop), it plays the
   first seed after it that makes a fair map (`scene.fair_map`), and New
   game shows the seed it plays. A seed the player gives (`--seed`) is
   generated as given; the retry count is deterministic from it.
8. **Variation.** Within a layout the seed decides the side the gate faces,
   where the river bends and the fords lie, the shape of every clearing and
   grove, which pit gate is wide. The preview always shows it.

## User interface

One new row on the New game screen, between **Land** and **Race**, in the
style of the rows there:

    Map      [Plains] [Forest] [Crossings] [Klondike] [Bastion] [Any]

Hotkeys P, F, C, K, B, Y; the screen's existing keys (S M L, 2 3 4, E N H,
G W D, U O V A, R, Enter, Esc) stay free. Under the row a caption in the
style of the race tagline: the layout's one-line promise, and for Any the
drawn layout after the dot. The preview already regenerates on every option
change and its 4 px per tile picture shows a river, a ring or a pit
unmistakably; naturals stay gold like every mine. The title backdrop draws a
random layout. `--layout` joins the command line. Multiplayer rooms carry a
`layout` option next to `theme` (`option_choice`, default `any` resolved by
the host's seed); the live server refuses unknown options until it is
redeployed, exactly as it refuses races today. `World` records its layout
as it records its theme, so **New game** after a match keeps the layout with
`seed + 1`, and `SAVE_VERSION` goes up: older saves are refused with the
usual message rather than loaded with a guessed layout. The high-score
entry names the layout beside the theme; the top-ten key (difficulty, size,
players) does not change.

## Verification

- `tests/warband/test_maps.py` runs its 40 seeds × 3 sizes × 3 themes per
  layout (six times the maps, about 2 000 generations; measure, and thin the
  theme axis if the suite grows past its four minutes, since theme no longer
  changes structure). Every layout's structural assertions live in `audit`
  and are asserted there; symmetry is asserted by comparing the terrain and
  the buildings with their reflection.
- `tools/map_report.py --layout X` prints the per-layout numbers (detour
  factors, gate and ford widths, natural distances, rejection count per
  seed) beside the existing ones.
- A frame of each layout in each theme, looked at, before the row ships;
  the preview image of each layout too. The visual review of the last
  release is the model (`warband-early-access-progress.md`).
- `tools/fuzz.py --games 2` per layout with the invariants, and a regression
  test from the seed's exact tiles for anything it finds. `tools/ai_report.py`
  on Klondike and Forest: Hard must still beat the scripted opening, Easy
  still lose to it.
- The pathfinder budget on Large Forest, measured, before deciding whether
  3 000 expansions stays.

## Implementation plan

Each step is a commit that leaves the suite green.

1. `Layout` enum in `rules.py`; `generate(..., layout=)` with Plains as
   today's generator; `World.layout`, save version bump, `--layout`, room
   option, the New game row with its caption, title backdrop. Any resolves
   from the seed. UI screenshot looked at.
2. The skeleton: wedge-and-copy symmetry for 2, 3 and 4 players; naturals;
   thirds by the new rule; pathfinder-based audit with retry. Plains retuned
   to its promise. `map_report` per layout.
3. Bastion (the smallest step from Plains: a ring and a gate), then
   Klondike (a pit and three mine sizes), then Crossings (the river and its
   fords), then Forest (the path network and the pathfinder measurement).
   Each with its audit section, tests, fuzz run and a looked-at frame.
4. AI checks on Klondike and Forest with `ai_report`; adjustments only if
   the report demands them.
5. README and `warband-early-access-progress.md` (W03) updated; this note
   rewritten from proposal to description.

Rough size: steps 1–2 a day, each layout half a day to a day, with Forest
the longest.

## Not in this design

- **Nomad** (no hall at start, choose where to settle): the most engaging
  Age of Empires opening, but it changes the rules (a player with no hall
  and no army counts as eliminated today) and the AI; a candidate for a
  sixth layout once the five exist.
- Neutral guard towers or creeps: there is no neutral combatant in the
  model.
- Islands: no boats.
- Asymmetric maps with per-base compensation: symmetry is cheaper and
  players trust it more.

## Sources

- Age of Empires II map families: [Arabia](https://liquipedia.net/ageofempires/Arabia),
  [Black Forest](https://ageofempires.fandom.com/wiki/Black_Forest),
  [Arena](https://liquipedia.net/ageofempires/Arena),
  [Gold Rush](https://ageofempires.fandom.com/wiki/Gold_Rush),
  [Hideout](https://ageofempires.fandom.com/wiki/Hideout).
- StarCraft II melee design: [Level design: introduction and melee maps](https://code.tutsplus.com/starcraft-ii-level-design-introduction-and-melee-maps--gamedev-3304t)
  (symmetry, natural, chokes, forcing interaction), [The Mapper's Index](https://ktvmaps.wordpress.com/portfolio/the-mappers-index-mapmaking-tutorials-help/),
  [Resource placement for competitive play](https://s2editor-guides.readthedocs.io/New_Tutorials/07_Lessons/086_Resource_Placement_for_Competitive_Play/).
- Warcraft III: [Blizzard's competitive melee map designer note](http://classic.battle.net/mod/dev/melee.shtml)
  (equal distances, identical entrances, small maps, no clutter).
- Warcraft II: [multiplayer maps](https://warcraft.wiki.gg/wiki/Warcraft_II_multiplayer_maps),
  [Gold Rush](https://liquipedia.net/warcraft/Gold_Rush).
- Research: Togelius et al., [Controllable procedural map generation via multiobjective evolution](https://www.researchgate.net/publication/257564581_Controllable_procedural_map_generation_via_multiobjective_evolution)
  and [Multiobjective exploration of the StarCraft map space](https://www.semanticscholar.org/paper/Multiobjective-exploration-of-the-StarCraft-map-Togelius-Preuss/13179d4846f3a787c4d8a9e02a4864a7ecee176e);
  Uriarte and Ontañón, [PSMAGE: balanced map generation for StarCraft](https://www.researchgate.net/publication/261266936_PSMAGE_Balanced_map_generation_for_StarCraft).

## What was built

The generator draws the first seat on a canvas and copies it by the map's
symmetry (point reflection for two players, both mirrors for three and four),
places the natural and the thirds by a scored site search over the canonical
region, carves corridors only through unprotected ground, audits the result
with the production pathfinder and retries the seed up to eight times.
Where it departs from the plan above:

- **Sizes.** 40 × 32 is gone: four symmetric seats with a natural each do not
  fit on it, and Klondike's pit and Bastion's rings collide with the base
  clearings. The sizes are now Small 48 × 40, Medium 64 × 48 and Large
  80 × 64, so every layout works at every size with two to four players
  (the suite proves 40 seeds of each). The 80 × 64 map is the "Huge" the
  plan asked for; the names shifted so the hotkeys S, M, L stay.
- **Thirds.** Two players get one contested site (two mines) on Small and
  two on Medium and Large; four seats get none on Small, one on Medium and
  two on Large. On mirror maps the contested line runs along the axes where
  a mine cannot sit, so a third there may be up to twelve tiles nearer one
  hall than the next (fourteen on Crossings, where the river itself runs down
  the bisector); every seat has the same, by symmetry.
- **Naturals.** Ten to eighteen tiles out (twelve on Bastion, thirteen on
  Forest), nine on mirror maps whose quadrants are 24 × 20. The AI builds a
  hall at a mine more than fourteen tiles away and mines a nearer one from
  its main hall.
- **The AI claims mines.** Klondike starved the old brain: it expanded only
  once its nearest mine was gone, by which time it had spent everything on
  soldiers. `Brain._mine_to_claim` now plans a hall at the nearest unclaimed
  mine while the worked one is far, below 6 000 gold or gone (at most three
  halls, one at a time), and holds army training and research until the hall
  is paid for. Six-minute Hard-vs-Hard probes on 2026-09-15: both brains
  hold two or three halls in the pit by eight minutes.
- **Forest clearings** are radius 9, not 7: at 7 a full base ran out of farm
  sites. The brain's own habits (one barracks for the first four minutes,
  defending piecemeal) show more on Forest, where the enemy's whole army
  walks the road into the clearing; that is the AI gap recorded in
  `warband-gaps-2026-09-09.md`, not a map fault, and is left as it was.
- **Crossings.** Two players get one wandering river through the centre;
  four seats get a straight cross whose width swells and narrows, because a
  wandering river mirrored across an axis doubles into an unpassable band.
  Fords are cuts straight across the water: six tiles at the centre, three
  near each end.
- **Klondike.** Two gates for two players and four for four, one per seat,
  each four tiles wide; two pit mines on Small and Medium, four on Large for
  two players, four for four seats. A poor corner mine only when two play.
- **Bastion.** The ring is 8 to 11.5 tiles from the hall's middle for two
  players and 8 to 10.5 for four, whose gates always face along the map's
  long axis so the two facing gates share the middle column.
- **Forest.** Roads zigzag between waypoints six to ten tiles off the
  straight line; the audit asks for a detour of at least 1.1 between the
  first two halls and at least 40 % trees.
- **Theme** no longer changes the terrain at all: the same seed gives the
  same map in summer, winter and wasteland.
- **Scores** do not yet name the layout.
- **Preview.** The New game screen puts the preview beside the options, up
  to 320 × 240 pixels, with the layout's promise under the Map row; under
  Any the caption names what the seed drew.
