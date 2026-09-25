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
| WB-066 | Now | proposed | Magic II: the Mage Tower, one spell of three per level, cast anywhere, dearer beyond the vaults | Ilya 2026-09-24 |
| WB-067 | Now | proposed | Magic III: the computer players research, choose and cast; the nine spells balanced | Ilya 2026-09-24 |
| WB-068 | Now | proposed | A unique unit per race: Gryphon Rider, Goblin Sappers, Treant, Rune Golem | Ilya 2026-09-24 |
| WB-069 | Now | proposed | A voice for every body: creatures and machines sound like what they are, deaths first; sound in the new-unit protocol | Ilya 2026-09-24 |
| WB-070 | Now | proposed | Painted sheets for every unit, the flying machines first; painting in the new-unit protocol | Ilya 2026-09-24 |
| WB-071 | Now | proposed | The seam looks as poor as it pays; its rich look goes to a new Mother Lode (over 50k gold) | Ilya 2026-09-24 |
| WB-072 | Now | proposed | No last-standing reveal in a free-for-all: only the last two sides learn where the other hides | Ilya 2026-09-24 |
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

## WB-066 — Magic II: the Mage Tower and the spells

**Design.** The **Mage Tower** (race names; 900 gold 400 lumber, needs an
Aether Vault) researches three **levels** of magic: I (600/200, 60 s), II
(1000/400, 90 s, needs the Keep and I), III (1600/600, 120 s, needs II).
Researching a level is choosing one of its three spells; the other two are
closed for the match. Spells are cast by the side, not a caster: from a
spell bar on the HUD, at any point of the map (a point in fog is allowed,
blind), costing aether, each with its own cooldown; beyond every vault's
reach the cost and the cooldown are tripled, and the aim cursor says which.
The effects are WB-062 conditions (rows of `buffs.toml`) plus a few direct
blows. Friendly spells touch only the caster's units, hostile ones every
rival's and the wilds', flyers included unless named.

| level | cost / cooldown | spell | effect |
|---|---|---|---|
| I | 30 / 30 s | Haste | own units within 3: +40 % speed, blows 25 % faster, 10 s |
| I | | Mend | own units within 3: +5 hp a second for 6 s, bleeding staunched |
| I | | Flame Strike | enemies within 1.5: 25 damage through armour, then 2 a second for 4 s; buildings too |
| II | 60 / 60 s | Stoneskin | own units within 3: +4 armour, 15 s |
| II | | Entangle | enemy ground units within 2.5 cannot move for 4 s (they still strike); flyers are out of reach |
| II | | Wither | enemies within 3 deal 30 % less damage and move 20 % slower, 12 s |
| III | 120 / 120 s | Meteor | lands 2 s after the cast (its shadow grows), 120 damage within 2 falling to 60 at the edge, ×1.5 on buildings, friend and foe alike |
| III | | Summon | three Aether Elementals (hp 120, damage 12, melee) for 40 s at the point |
| III | | Battle Fury | own units within 6: +40 % damage, +20 % speed, 12 s |

The rule of the triads: each level offers one tempo spell, one that holds a
fight, and one that hurts, so the choice follows the posture, not a best
answer.

**Acceptance.** One `@recorded` World order `cast(player, spell, point)`
checked atomically (researched, aether, cooldown, a point on the map) with
rows in the atomicity tests; the choice of a level closes the other two;
cost and cooldown tripled beyond reach; each spell's effect tested; saves,
snapshots (a rival's research and aether stay private; a cast others see is
public news) and replays; the tower, the spell bar, the aim cursor and each
spell's effect rendered and looked at, with sounds; visual lint;
fingerprint refreshed.

## WB-067 — Magic III: the AI casts, the spells balanced

**Design.** Hard, Master and Grandmaster (the `ProBrain` family) build a
vault on their rift in the mid game, a tower, and research a spell per level
chosen by posture (a rush takes Haste, Flame Strike, Battle Fury; a warden
Mend, Stoneskin, Meteor; the bred brains get the choice as genes). They cast:
buffs over their own army when it engages (the point covering most of it),
damage on clumps of rivals or workers at a mine, Entangle on a retreat or a
chase, Meteor on a clump or a tower line, Summon where they are losing.
Easy and Medium stay without magic.

**Acceptance.** On the arena, a magic-using ProBrain beats the same brain
without magic over enough seeds to mean it; each spell's pick is within a
band of its two rivals when the brain is made to take it (no spell that is
always right or never), tuned by numbers in `buffs.toml` and the spell table;
race balance in band; `docs/balance.md` records the numbers; fuzz; the
fingerprint and `sim_bench.txt` refreshed.

## WB-068 — A unique unit per race

**Design.** "Something exotic and expensive, but sometimes useful": each race
gets one unit that is a *situational* answer, never the new best buy. Each
has a signature mechanic no other unit has, costs about two knights, needs
the Keep, and a side may keep at most **three alive at once** (a
`limit = 3` on the unit type, refused with the reason at the card), so it
stays a centrepiece and cannot be massed.

| race | unit | trained at | what it is | when it is right | what answers it |
|---|---|---|---|---|---|
| Humans | **Gryphon Rider** | Stables | the first *armed* flyer: hurls a storm hammer at ground **and** air (range 2.5, damage 14, cooldown 1.6); hp 110, armour 2, speed 3.8, living (it bleeds) | hunting flyers, catapults and lone shooters; raids across water and forest | massed shooters, towers; archers' bleeding slows it |
| Orcs | **Goblin Sappers** | Siege Yard | a runner with a powder keg (hp 40, speed 3.4): its "blow" is its end, 240 siege damage within 1.5 (×1.5 on buildings), 60 to every unit there, its own side's too | cracking a tower line or a hall in one strike | anything that catches it before it arrives; shooters |
| Elves | **Treant** | Moonwell | a walking tree: walks *through* forest (its own navigation), hp 320, armour 3, damage 22 melee, ×2 on buildings; mends 4 hp a second while it stands among trees | a siege that comes out of the woods behind a base | open ground, catapults, being kited |
| Dwarves | **Rune Golem** | Rune Shrine | the neutral golem's slam, carved and bound: hp 300, armour 4, damage 20, cooldown 2.4, splash 1.3 on enemies only; speed 1.4; a construct (not living: never bleeds, never healed) | breaking a clumped melee line | shooters and siege from range; attrition, since it cannot be mended |

Prices: Gryphon Rider 1800 gold 400 lumber, Sappers 800/300 (one use),
Treant 1500/500, Rune Golem 1600/500; build times 35–45 s. Each race's
names and summaries in races.toml; the codex and the tech tree show them.

- The brains train their race's unique unit only when it is right, by what
  they know: gryphons against catapults, flyers or a shooter-light army;
  sappers against a tower line or a hall within reach; treants when a
  forest route reaches the rival; golems against a melee-heavy army. A
  brain that never needs one never buys one.
- Implementation seams: the armed flyer extends WB-064's air layer (a
  flying unit with a weapon that can target air); sappers are a unit whose
  blow ends it; the treant a unit type with a forest-walking navigation grid;
  the golem reuses the creature's slam. Each should be a row plus the least
  code, and the seam named, so the next unique unit is cheap.

**Acceptance.** Rules tests per unit (the gryphon strikes air and ground and
is struck only by shooters, towers and gryphons; a sapper's blast and its
friendly fire; a treant crosses a forest a footman must walk round, and
mends only among trees; the golem's slam spares its own side; the limit of
three refuses the fourth); the arena shows each race's balance within band
and a brain that may buy its unique unit not weaker than one that may not,
with telemetry on how often each is bought; each unit rendered per race and
looked at; the codex and the card; fuzz; fingerprint refreshed.

## The 2026-09-24 evening intake (WB-069 … WB-072)

Four more requests. WB-069 and WB-070 turn two lessons of the day into a
protocol: a new unit was added three times today (the flying machines, and
WB-068's four unique units in flight), and each time its sounds were the race's
and its art the render's, because nothing asked for more. The protocol is
`docs/adding-a-unit.md`, a checklist, and tests that fail when a unit type
skips a step, so the next unit cannot.

## WB-069 — A voice for every body

**Design.** A death is the body's, not the race's: a catapult splinters, a
flying machine sputters and crashes, a golem grinds apart. A unit type names
its sound family in its TOML row (`sound = "…"`, defaulting to its race's for
living soldiers of a race); a family holds its death pieces (and, where it
has them, its blow's impact material and a presence sound).

| body | death | presence |
|---|---|---|
| catapult (every race's siege engine) | timbers splinter, a rope snaps, the frame crashes | a creak and a winch on its order |
| flying machine | an engine or wings sputter, a whistle down, wood and metal crash | a whirr or wing-beat on its order |
| wolf | a yelp, a body falls | a snarl when its camp rouses |
| spider | a screech, a wet crunch | a hiss when its camp rouses |
| troll | a deep bellow, a heavy fall | a roar when its camp rouses |
| golem | stone grinds and breaks, rubble settles | a stony rumble when its camp rouses |

WB-068's four unique units get theirs by the same protocol (a gryphon's
screech, a sapper's blast as its death, a treant's splitting wood, a rune
golem's stone and fading runes). The pieces are generated with Stable Audio 3
through `sagaforge.foley` and `tools/pieces.py`, committed with their
provenance, as the other pieces were.

**The protocol.** `docs/adding-a-unit.md` lists what a unit type needs: its
row, names and plurals for every race that fields it, the render, a painted
sheet (WB-070), its sounds, its codex line, its brain handling, its lint.
Tests enforce what can be enforced: every unit type resolves a death cue with
at least two takes on disk; no creature or machine dies with a race's cry.

**Acceptance.** Every unit type and creature has a death of its body; the
presence sounds play; spectrograms and stats of each new cue looked at
(`tools/music.py`-style render; Ilya has not heard them yet, say so); the
protocol document and its tests; the audio tests; visual lint unaffected;
fingerprint unchanged (sound is no rule).

## WB-070 — Painted sheets for every unit

**Design.** Every unit type wears a painted sheet (`tools/restyle.py` through
`sagaforge.restyle`), recoloured per team, with its animation (a flyer's rotor
turning or wings beating across its walk frames). A unit type without one is
a test failure unless it stands in a small exemption table with the reason
and the date, so procedural art is a visible, conscious debt rather than a
default. First the four flying machines; WB-068's units follow by the
protocol. The painters are Codex (`codex exec`), an OpenRouter image model,
or a direct image model API: probe which works today and record it; if none
does, stop and say so rather than exempting silently.

**Acceptance.** The four flyers painted, animated, recoloured and in play,
looked at on the map and on the card; visual lint (painted frame off its
render, team recolour) clean; the exemption table and its test; the
protocol document updated; fingerprint unchanged.

## WB-071 — The seam looks as poor as it pays; the Mother Lode

**Design.** The endless seam pays 20 gold a trip against a mine's 100, but it
wears the richest picture on the map. It gets a poor look: thin veins in
mostly bare rock, a few old props, so a glance says "slow, but forever". The
rich bank of three faces goes to a new deposit that earns it, the **Mother
Lode**: 5×5, twelve places at the face like the seam, a mine's 100 gold a
trip, 100,000 gold and finite. It wears the rich bank while it holds more
than 50,000 gold and a worked-out bank below, so how much is left shows.
Where: on the maps big enough for a seam, the shared ground's prize is a seam
or a Mother Lode, dealt by the map seed, so the middle of a big map is either
a long siege for a trickle or a short war for a fortune; camps guard it as
they guard the seam. Why: a map's centre that differs from map to map is the
diversity the maps were asked for, and the lode is the fight worth having.

**Acceptance.** The seam's poor look and the lode's two looks rendered and
looked at (painted where WB-070's painter works); mapgen deals lodes fairly
(the audit covers them) and the seed decides; the brains contest a lode
(telemetry from the league: who takes it, when); race and difficulty balance
in band; fingerprint and sim_bench refreshed.

## WB-072 — No last-standing reveal in a free-for-all

**Design.** A side left with no hall and no building that trains is exposed:
its remaining buildings are revealed to every other seat, with public news.
In a duel that ends a hide-and-seek; in a free-for-all it tells bystanders
where a weakened side hides, which is information they did nothing to earn.
The reveal (and its news) now happens only while exactly two sides remain in
play: a duel, or a free-for-all down to its last two, so the only side told
is the one left fighting it. The brains' hunt (07cb63d) searches for what is
not revealed.

**Acceptance.** Rules tests: a duel reveals; a three-side free-for-all does
not, until two remain; a bystander's snapshot shows nothing of the exposed
side; the news follows the reveal; the free-for-all league's undecided count
does not rise (before/after); fingerprint refreshed.

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
