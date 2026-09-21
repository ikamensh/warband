# Warband maps: a generator with five layouts

Design note, 2026-09-15, implemented the same day in `warband/sim/mapgen.py`
(the section *What was built* records where the build departs from the plan, and
*Sixteen seats* at the end what the grid of congruent cells changed on
2026-09-20). The fairness audit runs inside the generator; the per-seed
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
| Sizes and seats | six sizes, 48 × 40 to 180 × 132; 2–16 players, one to a cell of a grid; the map's rim is trees | Features are sized in tiles per size, not scaled; see *Sixteen seats* |

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

## Sixteen seats (2026-09-20)

The generator knew exactly two symmetries: the point reflection through the
centre for two seats and the mirror in both axes for three and four. It now
deals every seat one **cell of a grid** — the canonical cell translated and
mirror-flipped into a `cols × rows` arrangement — of which those two are the
`1 × 2` and `2 × 2` cases. Two, three and four seats generate the maps they
always did, tile for tile: `tools/sim_fingerprint.py --check` and
`tools/sim_bench.py --check` are both unmoved by the whole change.

### The grid

`mapgen.grid(seats)` names the grid, `mapgen.cell_images(width, height, seats,
pos, size)` the copies of a square, and `mapgen.dimensions(size, seats)` the map
a nominal size makes (the nominal rounded **up** until the grid divides it, so
`Large` is 80 × 64 for four seats and 81 × 64 for a grid three cells wide).

| Seats | Grid | Why |
|-------|------|-----|
| 2 | 1 × 2 | the point reflection that shipped: the cell is the top half |
| 3, 4 | 2 × 2 | the two mirrors that shipped; three leaves one cell empty, its natural a neutral mine |
| 5, 6 | 6 × 1 | six lanes, each cell the full height |
| 7, 8 | 4 × 2 | |
| 9–12 | 6 × 2 | |
| 13–16 | 4 × 4 | |

**Every axis has an even number of cells, or exactly one, and no other count
will do.** Neighbouring cells mirror each other, so the canonical column a map
edge shows alternates along the axis: with an even number the two edges show the
same one and the map's rim is a single orbit of the canonical cell's; with one
cell the two edges *are* the two ends of the cell. With an odd number they
differ, and then one seat's rim is the forest fringe while another's is open
ground, and one seat's share of a feature built on a crossing of cells is cut
off by the map's edge instead of meeting three others. Three cells on an axis
was tried and produced exactly those two faults.

Seats take cells in checkerboard order, so the first two are diagonally
opposite and a count that does not fill its grid leaves a corner cell empty.

**The hall sits in the middle of its cell once an axis has three or more
cells.** With one or two, the mirror throws a hall near the cell's corner out to
the map's own corner, which is where halls have always stood; with more it would
throw two halls together against their shared border, fifteen tiles apart.

**The map's rim is a frame, not a cell's ground.** It is painted like any other
tile while the map is drawn and put back to forest once at the end
(`_Canvas.frame`), and an orbit that touches it is left out of the symmetry
audit. Without that, the column a cell shows at the map's edge — which is an
inner column of the next cell along — could never be opened, and two cells stayed
walled off from each other for good. The consequence is stated plainly: a cell
on the map's edge loses its outermost row or column to the frame and an inner
cell does not, so the seats' *neighbourhoods* differ on a grid with inner cells
(a corner seat has two neighbours, an inner seat four). Their *cells* are
congruent tile for tile, which is what the audit and `fair_map` rest on;
positional equivalence is only exact for 2 and 4 seats, as it has always been —
three seats of four were never positionally equal either.

### The layouts

`PLAINS`, `FOREST` and `BASTION` are per-seat features and tile without a word.
`CROSSINGS` and `KLONDIKE` are built around **the crossing of cells at the
canonical cell's far corner** (`_Canvas.junction`), which is the centre of the
map when the grid is one or two cells each way and one of several crossings
otherwise: the same code now draws one river cross or one pit for each group of
cells that meet, and the copies assemble them. That is why both need an even
grid.

`FOREST` needed one change of its own: its roads ran to a single crossing, which
on a bigger grid joins only half the borders, and the connector then tunnelled a
dead-straight corridor through the woods to reach the rest — the audit saw it as
"roads too straight". Roads now run to the middle of **every** border a cell
shares (`_meetings`), with a small clearing at each so the copies meet
four-connected. A roomy cell also earns extra glades (`_glades`, one per 1 300
tiles beyond the first), because the layout's clearings are sized in tiles and a
big cell would otherwise be one solid block of trees.

`mapgen.layouts_for(width, height, seats)` says which layouts a map can hold and
is what **Any** draws from, so Any is refused only when none of them fit.

### Which size seats how many

`mapgen.refusal(width, height, seats, layout)` gives the reason a pairing is not
offered, or `None`. A seat's cell must be at least 24 × 20 tiles (the smallest
share that has ever made a fair base: Small with four seats) and at most 5 000
(beyond that the walk to the next base is the whole match). Bastion needs 24
tiles across any axis whose hall is centred, for the ring to close inside the
cell; Klondike needs the hall far enough from the crossing not to stand in the
pit.

| | Small 48×40 | Medium 64×48 | Large 80×64 | Huge 108×84 | Giant 144×108 | Epic 180×132 |
|---|---|---|---|---|---|---|
| 2 | ● | ● | ● | ● | | |
| 3, 4 | ● | ● | ● | ● | ● | |
| 6 | | | | | ● | ● |
| 8 | | | | ● | ● | ● |
| 12 | | | | | ● | ● |
| 16 | | | | ○ | ● | ● |

● every layout · ○ Plains, Forest and Crossings only (a 27 × 21 cell has no room
for a ring or a pit).

The three sizes that shipped keep their tiles on purpose: the measured
difficulty ratings (`brains.DIFFICULTY_ELO`) and the balance league were played
on them, and `league.arena.LADDER_SIZES` now holds its own copy so that offering
a new size never moves a rating. The three new ones are what the seat counts
above four need; Epic at sixteen seats gives each seat 1 485 tiles, against the
1 280 a Large four-player map gives.

The New game screen never offers a pairing it cannot generate: changing the
seats moves the size, changing the size moves the seats, and a layout the pair
cannot hold falls back to Any. Greying out both rows instead would leave the
screen with no way from one end of it to the other.

### The sixteen colours

`rules.PLAYERS` holds sixteen names and colours, dealt in order: eight bright
hues spread round the wheel first, then deeper and lighter ones between them, so
a four- or eight-player game uses the colours that differ most. Every one keeps
enough saturation and value to survive the team recolour of a painted sprite
(`sagaforge.restyle.recolor` scales a sprite by the target's saturation and
value, so a pastel would give a colourless army and a near-black a black one).

They were laid out by hand and then annealed inside each colour's own hue
neighbourhood: an optimiser left to itself crowds the blue–yellow axis that
red-green vision keeps and throws away the hue variety everyone else sees.
Measured in CIE76 under normal, protanopic and deuteranopic vision (Viénot,
Brettel and Mollon's dichromat simulation):

- smallest gap between any two seats, normal vision: **33.5**;
- smallest gap under red-green vision: **15.7**, the same order as Crimson
  against Viridian, which is the pair Warband has always had;
- every colour is at least **9.6** from every theme's ground, which is the floor
  the four that shipped already sat at (Crimson against summer trees for a
  protanope).

Looked at on rendered minimaps in all three themes and all three vision types
(`docs/evidence/bigmaps/colours.png`, 2026-09-20). Under red-green vision the
yellows — Amber, Lime, Olive — do run together; sixteen colours a dichromat can
name apart do not exist in a space that also has to survive a sprite recolour,
and that is the honest limit.

One defect that predates the change was fixed with them: nobody's building on
the minimap and on the New game preview was `(232, 196, 70)`, **three** units
from Amber, so an Amber player's halls were their own gold mines. It is now
`view.NEUTRAL_MINIMAP`, a straw twenty-seven from the nearest seat colour.

### What a sixteen-seat match costs

Measured on 2026-09-20 on the Mac, with sibling agents running, so read the
comparisons rather than the absolutes.

Ten game-minutes of a real sixteen-seat match on Epic (823 units at the end),
`tools/step_bench.py --scenario seats --seats 16`, interpreted as the game runs
it — the simulation has 50 ms a step at 20 Hz:

| | mean | p50 | p95 | max |
|---|---|---|---|---|
| step, before | 7.87 ms | 4.45 | 35.41 | 87.05 |
| step, after bounding the fog lookups | **5.80 ms** | 3.48 | **22.11** | **57.99** |
| sixteen brains, a step | 0.80 ms | | 3.26 | 48.90 |
| step, four seats on Giant (240 units) | 1.07 ms | 0.66 | 4.18 | 10.38 |

Whether a structure is seen was asked of every structure once per seat, five
times a second: 4.3 million footprint scans over those ten minutes, most against
fog nowhere near. `update_vision` now tells a seat's worker memory where its
sight discs are and four comparisons refuse the rest — the same answers, a third
less time, and the fingerprint unmoved.

Frames on the real backend, `tools/perf.py --frames 480`:

| scenario | p50 | p95 | `world.step` | `find_path_grid` |
|---|---|---|---|---|
| reference, 150 units, 64×48 | 15.9 ms | 33.5 ms | | |
| four-player, 300 units, 80×64 | 15.6 ms | 34.1 ms | 8.3 ms a step | 0.11 ms a call |
| sixteen-player, 640 units, 180×132 | 10.0 ms | 41.0 ms | 36.0 ms a step | **1.29 ms a call** |

**A sixteen-seat match is playable but not smooth when the whole map fights.**
The median frame is fine — better than the reference, because the camera over
the middle of a big map draws fewer sprites — but the simulation step runs every
third frame and costs 36 ms in a full-map brawl, so the frame rate dips to about
24 FPS while it lasts. The cause is measured, not guessed: the pathfinder's
budget scales with the map's area (`path.budget`: 3 000 expansions up to Large's
5 120 tiles, 13 921 on Epic), because a route across a big map needs it or a unit
gives up halfway and walks into a wall — and **16 % of path requests do not reach
their goal**, each burning the full budget. On the four-player board the same
call costs 0.11 ms; on Epic it costs 1.29 ms.

Lowering the budget again is not a speed change: A\* that runs out returns the
nearest reachable tile, so a different budget is a different match. The fix is a
cheaper answer for the unreachable ones — the walkable-region map
(`path.Regions`, which `World._regions` already builds) can refuse most of them
without a search — and that is a rules change of its own, with a fingerprint and
a server rollout behind it. It is not in this branch.

A fair seed for what New game plays takes, per pairing (ten seeds each): 16 ms
at two seats on Small, 180 ms at four on Giant, 492 ms at sixteen on Giant and
**869 ms (max 1 081 ms) at sixteen on Epic**. The screen regenerates the preview
on every option change, so the biggest settings cost about a second of it.

### Sixteen seats online

**Not in this branch, and it cannot be.** A Warband room holds four seats and
`warband/online/authority.py` says so (`ONLINE_SEATS`). The ceiling is not the
game's: every client declares `saga2d.online.SEATS` in its hello and the room
server refuses a room with more seats than the client can play. That number is
**4** in Saga2D 0.3.8, the release Warband pins, so the room is four whatever the
authority allows. Raising it needs, in order:

1. a Saga2D release that raises `SEATS` and the two-seat wording in its room UI
   and server messages, and a re-pin here;
2. a snapshot that is not one whole world per seat. `WarbandMatch.snapshot`
   rebuilds `World.to_dict()` for each seat and the room publishes one per seat
   per tick, so a publish is O(seats² × area); on a Large map that is ~5.8 MB/s
   of JSON at four seats and ~92 MB/s at sixteen, against a hard
   `MAX_SNAPSHOT` of 8 MB per message that fails the whole room when a snapshot
   exceeds it. A delta or a compact fog encoding is a project of its own, and
   changing the snapshot's shape means `warband-v3`, not an edit of
   `warband-v2`;
3. room capacity: the live unit runs `--max-connections 96`, which is 24 full
   four-seat rooms and 6 sixteen-seat ones, on one VM capped at `MemoryMax=1200M`
   and `CPUQuota=150%`.

**Nothing this branch did changes what a room speaks.** `_create` accepts the
same seven option names with the same defaults and the same ranges — `players`
2 to 4, `width` 48 to 80, `height` 40 to 64 — with the literals given names
(`ONLINE_SEATS`, `ONLINE_SIZE`) and nothing else. `WarbandMatch.snapshot`,
`World.to_dict`, `SAVE_VERSION` and the three package docstrings the contract
hashes are untouched. So **`warband-v2` stays `warband-v2`**: this is a rules
deploy, not a game-id bump, and a client in the wild sees the options it always
did.

Sixteen seats are therefore a **one-machine** feature: you and fifteen computer
players. Playing against other people is sized by the engine at both ends — a
LAN host takes exactly one guest (`saga2d.network.MatchHost`: "Host one guest.
Seat 0 belongs to the host, seat 1 to the guest") and an online room holds four
— and neither number is Warband's to raise. Where New game's settings are past
what a room holds, the title refuses with the reason instead of quietly seating
four (`TitleScene.room_refusal`), and the authority refuses the same options
with `CommandError`; both refusals are held to by
`tests/warband/test_many_seats.py`.

### The seam for another kind of mine

`_claim(cv, pos, gold, rects, mines, clearing=..., kind=...)` is the whole of
placing a kind of deposit: one in every cell, the ground under and around it
cleared, and its footprints added to what later site searches keep away from.
Its footprint is whatever the rules give that kind, so a new kind is a site
search of its own (`_natural_site`, `_third_site` and `_seam_site` are the
three there are, all scoring `_canonical_sites` and picking through `_pick`)
plus one call to `_claim`, made after the existing claims so the order deposits
are built in does not move. `MINE_GOLD`, `EXPANSION_GOLD`, `POOR_GOLD` and
`KLONDIKE_START_GOLD` are untouched.

## The gold seam (2026-09-21)

> "Add a low-yield, endless mine on some maps. They take more space, give 20
> gold per run."

The **gold seam** is a second kind of deposit: `BuildingType.GOLD_SEAM`, five
tiles across against a mine's three, `SEAM_PER_TRIP` = 20 gold a trip against
`GOLD_PER_TRIP` = 100, `SEAM_SLOTS` = 12 places at its face against
`MINE_SLOTS` = 8, and it never runs out.

### Endless is a kind, not a number

`rules.MineInfo` hangs off `BuildingInfo.mine` and carries a deposit's `trip`,
its `slots` and whether it is `endless`; a building with one is a deposit and a
building without one is not, which is what every `is BuildingType.GOLD_MINE`
test in the game became. A seam's `Building.gold` is **zero and stays zero** —
it has no stock, it has a trip — so the question "is there gold to fetch here"
is `Building.has_gold`, and `KnownMine.has_gold` of what a player remembers
under fog. Nothing reads the number and infers a promise from it, and a mine
that is out still reads as out.

The kind rides in the save because a building's `type` always did.
`WorkerKnowledge.KnownMine` grew `trip`, `slots` and `endless` beside `gold`,
because every decision made under fog is made from the memory rather than from
the building: a seam remembered as a mine holding nothing is a seam nobody ever
walks back to. Their defaults are a plain gold mine's, which is exactly what a
save written before the seams existed means. `WarbandMatch.snapshot` needed no
change: it already sends a seat the mines it remembers, and it sends the
building's own type with it.

### The trip belongs to the deposit

`World.gold_per_trip(player, mine)` takes the deposit. A dwarf's Deep Mining is
an art of the miners, not of the rock, so it multiplies a trip rather than
adding to it: 100 becomes 150 as it always did, and 20 becomes 30. Adding the
mine's flat fifty would have trebled what an endless deposit is worth, and to
one race alone.

### What it is worth

A deposit's face serves its slots every `MINE_TIME`, so its ceiling is
`slots * trip / MINE_TIME`: **160 gold a second at a mine, 48 at a seam** (32,
had the seam kept a mine's eight places). Measured over four minutes with a
crew standing next to it:

| crew | mine, 6 tiles out | seam, 6 tiles out | mine, 20 tiles out | seam, 20 tiles out |
|------|-------------------|-------------------|--------------------|--------------------|
| 4    | 58.8 g/s          | 11.8 g/s          | 18.8 g/s           | 3.8 g/s            |
| 8    | 114.6             | 22.9              | 36.7               | 7.3                |
| 12   | 153.3             | 34.8              | 52.1               | 10.7               |
| 20   | 155.4             | 44.1              | 86.7               | 16.4               |

A mine next door saturates at twelve hands and about 155 gold a second; a seam
climbs past twelve because it has twelve places, and reaches about 44. A hand
at a seam earns 2.9 gold a second against a miner's 12.8 — a fifth, as the
trip says, until the extra slots push it to a little over a quarter.

**Twelve places at the face, not a mine's eight.** Five tiles of workings have
more mouth than three, and the number decides what a committed player gets for
committing. Measured six tiles from a hall, a seam with eight places is capped
at about 31 gold a second however many hands are thrown at it (22.9 at eight
hands, 30.7 at twelve, 31.1 at sixteen); with twelve places the same crews
reach 22.9, 34.8 and 42.4. Twenty tiles out — the seam without a hall of its
own — the two are within a gold a second of each other (17.2 against 16.4 at
twenty hands), because there the walk is the limit and not the face. So the
extra places pay only once somebody has put a hall beside the seam and means to
hold it, which is exactly the thing worth rewarding.

That makes the seam a poor place to put the next peasant and a good place to
put the next twenty minutes. An expansion mine holds `EXPANSION_GOLD` = 30 000
and a saturated crew drinks it in **three and a quarter minutes**; a hall at a
seam pays 34.8 gold a second for as long as it stands, which is the same 30 000
in **fourteen and a half minutes** and every minute after that for nothing.
Taken in the third minute of a twenty-minute match it out-earns an expansion
mine; taken in the fifteenth it is a rounding error. Its worth is how early you
take it and how long you keep it, which is what a reason to leave home is
supposed to be.

Without a hall beside it — walking the twenty tiles back to the one at home —
twelve hands bring 10.7 gold a second. That is the trickle a player gets for
free, and the argument for the hall.

### Where it goes

`_seam_site` looks for shared ground: at least `_SEAM_AWAY` = 18 tiles from
every hall (past the natural, out where a seat has to go and stay), as evenly
shared between the two nearest halls as a third is, and with `_SEAM_ROOM` = 110
open tiles within eight for the hall and the towers whoever means to keep it
will want.

**Three layouts hold one.** Plains is open ground where expansions lie exposed,
so a deposit nobody can exhaust is exactly the thing to fight over. Crossings
already asks who holds the fords, and a seam on the far bank gives the answer a
price. Bastion promises a boom in safety and then a fight for the middle, and
the seam is what the middle is finally worth. **Forest has none**: its
clearings and roads are cut by hand, and a five-tile dig with its open ground
around it would take a base's worth of woods out of a layout whose whole
promise is that the woods are thick. **Klondike has none either**: little gold
at home and the rest in a walled pit is a deliberate shape of economy, and an
endless trickle outside the pit unmakes it.

**Only maps bigger than the shipped three.** `_seam_orbits` asks for
`_SEAM_MAP` = 5200 tiles of map (a Large is 5120) and `_SEAM_CELL` = 1000 tiles
of a seat's own cell. So Small, Medium and Large never hold a seam at any seat
count or layout, and Huge, Giant and Epic do wherever a cell has the middle
ground for one — which leaves out Huge with sixteen seats (27 × 21 a seat) and
Giant with sixteen (36 × 27). Two reasons, and they agree: a permanent trickle
is worth most where matches are long and the middle is far from home, and the
measured difficulty ratings (`brains.DIFFICULTY_ELO`), the balance league and
`league.arena`'s own `LADDER_SIZES` all live on the three shipped sizes, which
therefore keep exactly the economy they were measured with. The simulation
fingerprint does not move.

**A seam is a wish, not a fault.** `build` separates `report["problems"]`, which
make a map unfair and are worth raising `NoFairMap` over, from
`report["wishes"]`, which are features a seed left no room for. Eight seeds get
the chance to fit a seam in, and a map that has everything else is a map rather
than a refusal. Over twenty seeds every Huge two-seat Plains, Crossings and
Bastion map got its two; the thin six-seat strips on Crossings (24 × 108 a
seat) get none, because the river cross and the thirds have already taken the
shared ground. `tools/map_report.py` prints a `seams` column.

### The picture

A seam is drawn as **three painted mine faces set into one bank of rock**: the
middle one at its own size standing on the footprint's front line, and the two
beside it at `SEAM_BACK` = 0.84 of their size and `SEAM_LIFT` = 0.75 tiles up
the picture, which is what standing further back looks like in this projection.
They are pasted back to front so the nearest working overlaps the others, and
the spread is computed from the middle face's own figure width so the three
together come to five tiles. **Nothing is ever enlarged**: the painted frames
were made for a three-tile mine and blown up to five they would be a smear.
`textures.deposit_image` picks the bank or the single face by kind, and the
whole thing wears the `active` look — lanterns lit in every mouth — while
anybody is inside. `tools/verify_map.py` renders one with a crew at its face.
