# Warband backlog

Created 2026-09-16. This is the working queue for taking one task at a time.
The [Early Access criteria](docs/warband-early-access-criteria.md) remain the
release gates; [progress](docs/warband-early-access-progress.md) holds their
evidence. Shared engine work belongs in the [Saga2D backlog](../saga2d/BACKLOG.md).

Keep IDs stable and never reuse one. When starting an item, change its status
to `in progress` and record the branch; record its acceptance before
implementing and its evidence after, and split larger discoveries into new
IDs. `proposed` items still need scope selection. Within each priority, the
order is the suggested sequence, not a requirement to finish every earlier
item first. Once an item is done and merged into main, delete its row and
section; git history keeps the record. The last ID given is **WB-073**; a new
item takes the next one and updates this line.

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-055 | Next | proposed | A deeper tech tree: the tower behind the mill, the knight behind the smith | Ilya 2026-09-19 |
| WB-056 | Later | proposed | Bug-hunt leftovers: small defects confirmed on 2026-09-19 and not yet fixed | Bug hunt 2026-09-19 |
| WB-057 | Next | proposed | The smallest canvas the game lays out for: a 1024x768 or 1280x720 desktop gets a HUD off the screen | Bug hunt 2026-09-20 |
| WB-058 | Later | proposed | Bug-hunt leftovers 2026-09-20: a site nobody owns by its colour, two strike frames that hop, crowded workers | Bug hunt 2026-09-20 |
| WB-059 | Next | proposed | A route nobody can reach costs the whole pathfinder budget, and the budget grows with the map | Sixteen seats 2026-09-20 |
| WB-060 | Later | proposed | Sixteen seats online: an engine release, a snapshot that is not one world per seat, and room capacity | Sixteen seats 2026-09-20 |
| WB-067 | Now | proposed | Magic III: the computer players research, choose and cast; the nine spells balanced | Ilya 2026-09-24 |
| WB-073 | Now | proposed | Race balance: dwarves win ~64 % and orcs ~36 % of Master race games; bring every race within 45–55 % | Orchestrator 2026-09-25 |

## WB-055 — A deeper tech tree

Asked for with WB-054: if there are too few inter-dependencies, propose some.
There are. Seven building links, and one hub: once a barracks stands, four of
the six tech buildings are open, so the only real gate is the first barracks.
The lumber mill opens nothing (it is a lumber drop and arrow research), the
blacksmith only the workshop, and every recruit needs nothing but the building
that trains it, so the knight, the toughest soldier and the best buy per gold
until the balance league raised its price (docs/balance.md), comes off one
stables alone.

```
now                                          proposed
Town Hall ┬ Barracks ┬ Guard Tower           Town Hall ┬ Barracks ┬ Blacksmith ─ Workshop
          │          ├ Blacksmith ─ Workshop           │          ├ Stables
          │          ├ Stables                         │          └ Church
          │          └ Church                          └ Lumber Mill ─ Guard Tower
          └ Lumber Mill                                Knight: Stables and Blacksmith
                                                       (Archer: Barracks and Lumber Mill, to decide)
```

| change | why | what it costs |
|---|---|---|
| Guard Tower needs the Lumber Mill, not the Barracks | the mill opens something; towers shoot the arrows the mill improves (Arrows I/II already raise towers); the barracks stops being the hub of four; the tower rush needs a mill, a hundred gold cheaper than a barracks | Warden's `towers_early` ("as soon as the barracks stands, before the mill") and the tower rush posture order a mill first |
| Knight needs a Blacksmith as well as the Stables | armour comes from the smith; the strongest unit needs two buildings; the smith opens more than the workshop | a new unit prerequisite (`UnitInfo.requires`) in `can_train` and the settlement's unit plans; the knights posture's `early_tech` gains a smith |
| to decide: Archer needs the Lumber Mill as well as the Barracks | Warcraft II's rule: the barracks alone gives footmen, the mill (built early anyway; the stronger brains want one from the start) adds archers and towers | delays every archer opening by the mill's 35 s; elves, whose rangers are their army, feel it most (they lead the race table) |

**Done, in part: the hall upgrade.**  A Keep is researched at the Town Hall
(1500 gold, 800 lumber, 90 s; each race names it — Stronghold, Moonspire,
Stonehold), and behind it stand Blades II, Armour II, Arrows II and two new
third tiers of the weapon lines, Masterwork Blades (3000/600, 120 s, +4 melee)
and Masterwork Arrows (1800/1000, 120 s, +4 for shooters and towers).  Armour
keeps two tiers, and the race arts, Siege and Marksmanship stay ungated: the
gate is the shared stat ladder's upper half, not a toll on everything.  It
needed no new mechanic — `UpgradeInfo.requires` became a tuple — and no new
art: the hall keeps its look, and the Keep is an emblem like any other
research.  A visible Keep (a painted sheet per race) is still a job of its own.

The three building links above (tower behind the mill, knight behind the smith,
archer behind the mill) are still open.

**What the gate costs the brains, measured.**  Sixteen seats of 20-minute
Master and Grandmaster matches (seeds 11-14), with the gate and with its
`requires` patched back out:

| researched by | without the gate | with the Keep |
|---|---|---|
| Blades II | 5/16 | 2/16 |
| Arrows II | 6/16 | 1/16 |
| Armour II | 4/16 | 1/16 |
| the Keep | — | 4/16 |

No tier became unreachable (`brains.ai.with_prerequisites` buys the gate on
the way to what the research order names, which is what keeps `bred.py`'s
frozen orders working), but fewer are reached: a brain buys an upgrade in
whatever window its bank happens to leave, never saving for one, and 1500 gold
and 800 lumber in front of the tier makes those windows rarer.  Both seats pay
it alike, so the ladder is unmoved (`hard` 912 against `pro` 1088 over 80
matches, and `ai_report --seeds 3 --decide 0` unchanged: the scripted opening
takes 2/3 from Easy and 0/3 from every setting above it).  A human who does
save for it gains on them.  **Open:** a `save_for_research` hold in
`ProProfile`, so a brain banks for a gate the way it banks for a build; worth
what `tools/arena.py` says it is worth and nothing else.

All three are rules changes: the online contract and the fingerprint move, a
server rollout carries them (batched), the brains' openings follow the new
edges, and the difficulty ratings and the balance league are measured again
(`tools/balance_report.py`, `tools/arena.py report`). On the HUD, one line in
`warband.ui.tech.prerequisites` (a recruit's second building) is enough for the
card; the codex's tree links buildings only, so it would draw that second link
into the recruit's picture. Campaign missions place their buildings and spawn
their armies directly, so none of them breaks.

## WB-056 — Bug-hunt leftovers

The bug hunt of 2026-09-19 (main `cbb4b62`) found about forty defects and fixed thirty-six of them;
these were confirmed with a script but left, being minor, latent or needing a decision. Each is a small
item of its own when taken up. The campaign's dropped choice was one of them, called harmless here: it
is not (the objective the answer opens never shows, and the campaign never learns the choice), and it
is fixed as of 2026-09-20.

- **Online, fog leaks through refusals and picks** (a rules change; the fingerprint may move): placement
  refusals still tell a seat what stands on ground it explored but does not see now ("Something is in
  the way", "A unit is in the way", a mine it never saw in "Too close to the gold mine"); a recruit's
  rally resolves its target without the seat's knowledge, so a rival building raised out of sight on
  the rally point is attacked; snapshot projectiles carry their shooter's id and start point when the
  shooter is out of sight.
- **Rules**: Plate Armour ("+1 armour for soldiers") also armours clerics (`World.armor_of` gives it to
  every non-worker); a unit killed earlier in a step still acts in it (strikes, casts, walks), by id
  order; no draw when the last two players fall in one step; `stop` leaves `Unit.ease`, so a stopped
  unit finishes its elbow-room step; a builder the settlement sent is "refused: Not enough gold" when the
  money went elsewhere on its way, though its plan stands and retries; a harvest order on an unreachable
  tree or mine is dropped without a word; a regrowth entry under a building retries every 5 s for ever;
  chop progress and repair charge carry over to the next tree or building.
- **Scene**: Settings → Tutorial switched on in a match does nothing; a rival's building in sight shows its
  painted "active" look while it trains, which online (whose snapshots hide its queue) it does not.
- **Campaign and replays**: `shifted()` has no Master row, a KeyError for a hand-edited progress;
  the campaign screen has no Restore backup as the profile's has; `Playback.run()` never ends for a
  replay file with order rows after its end tick; the replay digest leaves out terrain, projectiles,
  plans and the random stream.
- **Engine (Saga2D)**: a key held when an overlay comes up is released over the overlay, and the camera
  keeps its held direction; Warband clears it on reveal, the engine could for every game.

## WB-057 — The smallest canvas the game lays out for

`Game(resolution=None)` fits the canvas to the desktop (`saga2d.game._fit_screen`: the window less a
margin, divided down while it is taller than 1440 units). Nothing holds it *up*, and every layout in the
game is made for 1200x680 or more — `tools/visual_lint.py` walks 1280x800 and 1200x680, and
`tests/warband/test_startup.py` starts on 1920x1080 and 4K desktops. Below 1200 px wide there is no
coverage and no fit. Measured on 2026-09-20, walking every screen of the lint at the canvas each desktop
actually gives:

| desktop | canvas | findings | screens |
|---------|--------|----------|---------|
| 1024x768 | 944x648 | 628 | 63 |
| 1280x720 | 1200x600 | 85 | 17 |
| 1366x768 | 1286x648 | 8 | 8 |
| 1280x800 and every larger desktop | | 0 | 0 |

A 1366x768 laptop is an ordinary machine and it loses the top and bottom of the New game screen (the
column is 674 px on a 648 px canvas), 8 px of Settings, 24 px of the codex's units page, 6 px of its tech
tree, and the title's hint line sits under the menu. A 1280x720 desktop clips "WARBAND" itself — the
engine's own text check says so on every frame. A 1024x768 desktop puts most of the HUD off the screen.

Two ways, both worth something:

* **A floor in the engine.** `Game(resolution=None, minimum=...)` never returns a canvas smaller than the
  size a game's layouts are made for; a smaller window then shows the whole canvas scaled down with bars,
  which the backend already does (`test_startup`'s "a small window" is 960x500 on an 1840x960 canvas). One
  change, every screen and every display at once, and the 1200x680 design stands. It costs an engine
  release and the cohort upgrade and server rollout behind it.
* **Layouts that fit 648.** Trim the five screens that overflow a 1366x768 laptop. No engine release, no
  rollout, and it is the display most likely to be someone's. It does nothing for 1200x600 or 944x648,
  and every screen written afterwards has to remember the constraint.

Acceptance either way: the lint walks the canvases of the desktops above, and the startup matrix gains
one of them.

## WB-058 — Bug-hunt leftovers 2026-09-20

The hunt of 2026-09-20 (main `6846e47`) fixed twenty-nine defects. These are confirmed and left, each
needing a decision or a piece of art rather than a patch.

- **Eleven pictures a player cannot tell the owner of.** `tools/visual_lint.py` reports what a picture
  wears of the team's colour: `human.farm/tower/lumber_mill/stables/workshop.founded`,
  `elf.lumber_mill.founded` and `dwarf.lumber_mill/stables/workshop.founded` wear none at all,
  `human.blacksmith.founded` 8 px and `dwarf.blacksmith.founded` 68 px. The smallest mark that reads is
  the elven Stag Pens' site at 218 px. Either the sheets gain a pennant (`tools/restyle.py`, an image
  model), or the view draws an owner's mark for a site itself.
- **Two painted strike frames hop.** `unit.elf.knight.{1,2}.strike`
  stand 10-14 px above the render they repaint, so the rider jumps as it strikes. Repaint the frames, or
  place a painted frame by its own centroid against its render.
- **Workers crowd a spot and stand still.** `tools/fuzz.py` reports a unit that stays within a tile for
  twenty seconds as a deadlock. Two are not: a third peasant sent to a tree edge two others are already
  chopping waits about 25 s beside it instead of taking another tree (fuzz seed 3), and twenty-odd
  peasants delivering to one hall jam at its door, each of them still for 20 s at a time (fuzz seed 106,
  four players, twelve minutes in). Soldiers do it too: a knight at the back of a one-tile notch in the
  trees waits 20.5 s for a dozen soldiers to file out past others still coming in (fuzz seed 81 since
  WB-064, seven minutes in; it walks out as soon as they have). The rules already say a mine saturates
  at eight peasants; nothing says what a hall's door or a tree's edge holds. Either the worker policy
  spreads them, or the fuzz check learns to tell a queue from a deadlock.
- **A catapult's minimum range is nowhere in the HUD.** `UnitInfo.min_range` is 2.0 and the codex and the
  selection panel show only the 7. A player learns it by watching a stone refuse to fly.

## WB-013 — Fresh-player and cross-platform acceptance

Refresh W06/W15 with the current candidate: observe first launch, first economy,
first battle, loss/resign, save/resume and the website-to-online-match journey.
Include a complete human match on the published Mac/Windows candidate and
record hardware, version and obstacles. Use `tools/visual_lint.py` for what it
can find, while retaining human assessment of animation and clarity.

**Done when:** each blocker becomes a reproducible ticket and is resolved or
explicitly deferred; current evidence replaces stale gate claims. Automated
checks cannot mark the human playtest complete.

**Blocked 2026-09-18:** this needs people who have not played before; nothing
to build until a playtest happens. What unblocks it: one or two fresh players'
sessions (a recording or notes on what confused them), on a Mac or on Windows.
The Windows report that came first is closed (WB-021, WB-022), and a Windows
desktop for scripted checks is [a runbook away](../saga-online/docs/windows-test-box.md).

## WB-059 — A route nobody can reach costs the whole budget

`path.budget(width, height)` grows the A\* bound with the map's area (3 000 expansions up to Large's
5 120 tiles, 13 921 on Epic's 23 760), because a route across a big map needs it or a unit gives up
halfway and walks into a wall. What that costs is paid by the requests that *fail*: A\* that runs out
returns the nearest reachable tile, so a goal nobody can reach burns the whole bound. Measured on
2026-09-20 with sixteen armies converging on the middle of a 180x132 map (`tools/perf.py --scenario
sixteen-player`): **16 % of path requests did not reach their goal**, `find_path_grid` cost 1.29 ms a
call against 0.11 ms on the four-player 80x64 board, and it was 39 % of all the time spent; the
simulation step ran 36 ms, which is every third frame over its budget while a full-map brawl lasts.

The walkable-region map (`path.Regions`, which `World._regions` already builds and keeps) can answer
"nothing of yours can reach that tile" without a search, which is most of the failures. It is not a
speed change: a different answer for an unreachable goal is a different match, so it moves
`tools/sim_fingerprint.txt` and `tools/sim_bench.txt` and wants a server rollout behind it. The other
half of the fix is a hierarchical route (region to region, then tile to tile) so that a long route
costs its length rather than its area.

Acceptance: `tools/perf.py --scenario sixteen-player` holds `world.step` under 16 ms; `--scenario
reference` and `four-player` do not regress; both records refreshed in the same commit.

## WB-060 — Sixteen seats online

The offline game seats sixteen since 2026-09-20; a room still seats four and this is why
(`warband/online/authority.py`, `ONLINE_SEATS`, and docs/warband-maps.md, "Sixteen seats online"):

1. **The engine caps it, at both ends.** A LAN host takes exactly one guest
   (`saga2d.network.MatchHost`: "Host one guest. Seat 0 belongs to the host, seat 1 to the guest"),
   and online every client declares `saga2d.online.SEATS` in its hello while the room server refuses
   a room with more seats than the client can play — 4 in the Saga2D Warband pins, so a sixteen-seat
   room is one no client built today can join. Raising either is a Saga2D release, the three-game
   cohort rebuilt and a rollout — engine work, not Warband's.
2. **The snapshot is one whole world per seat.** `WarbandMatch.snapshot` rebuilds `World.to_dict()`
   for each seat and the room publishes one per seat per tick, so a publish is O(seats² × area):
   about 5.8 MB/s of JSON at four seats on a Large map and about 92 MB/s at sixteen, against a hard
   8 MB `MAX_SNAPSHOT` whose breach fails the whole room. A delta or a compact fog encoding is a
   project of its own, and changing the snapshot's shape means `warband-v3`, not an edit of
   `warband-v2`.
3. **Capacity.** The live unit runs `--max-connections 96` on one VM at `MemoryMax=1200M` and
   `CPUQuota=150%`: 24 full four-seat rooms, or 6 sixteen-seat ones.

Until then the refusal is honest and tested: `TitleScene.room_refusal` says what a room holds instead
of quietly seating four of sixteen, `_create` refuses the options with a `CommandError`, and
`tests/warband/test_many_seats.py` holds both.

Acceptance: a sixteen-seat room hosted, joined by sixteen clients and played to a result, with the
publish rate measured; or a decision that rooms stay at four and the cap is documented as final.

## The 2026-09-24 intake (WB-061 … WB-067)

Five requests from `backlog_intake.txt`, the magic one split in three. They
are taken in the order of their dependencies, not their numbers: WB-062
(buffs) and WB-065 (cancel mode) first and side by side, then WB-064
(flyers, which need the buff system's "living" rule), WB-063 and WB-061,
then WB-066 and WB-067, which need the buffs and the Aether economy. WB-068
(a unique unit per race, added to the intake later that day) follows the
flyers, whose air layer its Gryphon Rider uses. Each
lands on main as one squashed commit with green CI; the design decisions
below are the orchestrator's, and a measured number that disagrees with
one of them wins over it.

## WB-067 — Magic III: the AI casts, the spells balanced

**Design.** Hard, Master and Grandmaster (the `ProBrain` family) build a
vault on their rift in the mid game, a tower, and research a spell per level
chosen by posture (a rush takes Haste, Flame Strike, Battle Fury; a warden
Mend, Stoneskin, Meteor; the bred brains get the choice as genes). They cast:
buffs over their own army when it engages (the point covering most of it),
damage on clumps of rivals or workers at a mine, Entangle on a retreat or a
chase, Meteor on a clump or a tower line, Summon where they are losing.
Easy and Medium stay without magic.

**A number to settle (from WB-066's review).** A vault holds 150 aether
(raised from WB-063's 100 so a level III spell's 120 fits one), so one vault
casts any spell within its reach; the dearer price beyond reach needs two
vaults at level II (180) and three at level III (360) (an off-rift vault
stores). The build keeps the design's prices and says so wherever a far price
shows. The brains' vault plan has to know it, and the arena decides whether
the far casts' gate stays or the store or the prices move.

**Acceptance.** On the arena, a magic-using ProBrain beats the same brain
without magic over enough seeds to mean it; each spell's pick is within a
band of its two rivals when the brain is made to take it (no spell that is
always right or never), tuned by numbers in `buffs.toml` and the spell table;
race balance in band; `docs/balance.md` records the numbers; fuzz; the
fingerprint and `sim_bench.txt` refreshed.

## WB-073 — Race balance

**Why.** Through every item of the 2026-09-24 intake the race games told the
same story (`tools/race_report.py`, 288–564 matches a run): dwarves win about
64 % of Master's race games and 55–64 % of Medium's, orcs 34–37 % and 36–45 %,
humans and elves near half. None of the intake's changes caused it and none
closed it (WB-062 moved no race more than 2.6 points, WB-068 about 2). A race
the player picks and then loses to three times in five is the biggest balance
fault the game has.

**Design.** Every race within 45–55 % of its decided Master and Medium race
games, on the shipped sizes and layouts, with the difficulty ladder no weaker.
The levers, in order: the race's own numbers in `races.toml` (its multipliers,
its passive, its arts' magnitudes in `upgrades.toml`), then its unique unit
(WB-068), never a shared unit (that moves every race). Diagnose before tuning:
which matchups and which phase decide the dwarves' wins (Stonework's +25 %
building hit points and +2 armour against a rush or a siege? Deep Mining's
150-gold trip?) and the orcs' losses (the Grunt's −2 armour and no shield wall,
the Ogre's thin armour, Rage now that it outlasts a heal), with
`tools/battle_bench.py` for a unit question and the race games for the whole.
Each change is measured before it is kept; the texts that promise the numbers
move with them.

**Acceptance.** The before and after tables (Master and Medium, sample sizes
that mean something: two seed blocks on Medium, as WB-062 found), each change
and its measured effect in `docs/balance.md`, the ladder before and after,
fingerprint and sim_bench refreshed. Runs after WB-067, whose magic will move
the races again.
