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
section; git history keeps the record. The last ID given is **WB-046**; a new
item takes the next one and updates this line.

Done and removed 2026-09-18, every one merged into main (whose code is live as
Warband 0.2.30): WB-001 to WB-009, WB-015, WB-017 to WB-023 and WB-025 to
WB-034. Their acceptance and evidence are in
[the backlog at `1a6e08b`](https://github.com/ikamensh/warband/blob/1a6e08b73872cb595756a9d4ba7bc96c685c5ef0/BACKLOG.md).
Removed later the same day, each with its record in the backlog at the
commit named: WB-011 and WB-016, live as Warband 0.2.32
([`8a13fae`](https://github.com/ikamensh/warband/blob/8a13faeb65a0457ec0cd65d53e0461f01a734b49/BACKLOG.md));
WB-010, live as 0.2.33
([`5cb5959`](https://github.com/ikamensh/warband/blob/5cb5959df79bc09042e6f597736d7e43240a15a2/BACKLOG.md));
WB-012, live as 0.2.34
([`12ecf88`](https://github.com/ikamensh/warband/blob/12ecf88fef5ba74fe6c29a76bdf4defcf0774a02/BACKLOG.md)).
Removed 2026-09-19: WB-040, merged as `9c5caa4`
([`c49badb`](https://github.com/ikamensh/warband/blob/c49badb5f2baaca0d882f500caa09b38b4139864/BACKLOG.md)); WB-035, merged as `464328e`
([`2ad4dcb`](https://github.com/ikamensh/warband/blob/2ad4dcb7723c7d46d7c611fd254caa387a0df3e4/BACKLOG.md)); WB-043, merged as `66d35a5`
([`0680eb5`](https://github.com/ikamensh/warband/blob/0680eb570c73abba14d3c431f89bedeba5846246/BACKLOG.md)); WB-037, merged as `1b9880f`, live as 0.2.53
([`5a57cb9`](https://github.com/ikamensh/warband/blob/5a57cb94292cd1e39a20969cfe7c4a3b827fac61/BACKLOG.md)); WB-036, merged as `4a77498`, live as 0.2.55
([`3f22525`](https://github.com/ikamensh/warband/blob/3f22525a4db442d7f8d0d2c02b7532375ad1e075/BACKLOG.md)); WB-024, closed on its evidence as `dd7cf5f`
([`896c6ea`](https://github.com/ikamensh/warband/blob/896c6eab99fb426d7f0aa02588b0fd1dc1463d07/BACKLOG.md)); WB-014, merged as `18eaf4a`, live as 0.2.59
([`5fd2ef4`](https://github.com/ikamensh/warband/blob/5fd2ef41798f8162811b9eb0d286c80c65c9bb26/BACKLOG.md)); WB-045, merged as `6ad2779`, live as 0.2.61
([`493e3bf`](https://github.com/ikamensh/warband/blob/493e3bfb3df8eaefc809dbc0a86c80683eb490a1/BACKLOG.md)).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-038 | Next | blocked | Paint the gold mine with the image model, with a worked look, like every building | User 2026-09-18 |
| WB-039 | Next | blocked | Stop chiming on every selection | User 2026-09-18 |
| WB-041 | Next | proposed | Give the package folders: group the 43 flat modules by what they are | User 2026-09-18 |
| WB-042 | Later | done | Tests read through public accessors; try property tests for the model and paths | WB-040 |
| WB-044 | Next | blocked | Hold the push that comes with a rush tower; strike faster on Hard | WB-037 |
| WB-046 | Next | in progress (`fair-seeds`) | A seed that makes no fair map crashes the game where the game chose it | WB-042 |

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

## WB-038 — Paint the gold mine

Ilya asked on 2026-09-18 why the gold mine is not painted and animated like
the buildings. The painting procedure has no subject for it:
`tools/restyle.py` paints one race's units, or one race's nine buildings in
one look, and the game recolours each painting to its owner's team. The mine
belongs to no race and no player, so the sheets leave it out
(`textures.restyled_buildings` skips `BuildingType.GOLD_MINE`). The map
draws it from twenty low-poly stand-ins (`textures._mine`, one picked by a
tile hash in `view.py`), and its selection-panel portrait is the low-poly
render too. It is the last structure on the map still drawn as a stand-in.

The buildings come alive by swapping looks (`view.building_look`): `active`
(lit windows, open doors) while they train or research, and `damaged` under
half their hit points. A mine's own states are idle and worked (a peasant
inside). An exhausted mine is removed from the map, so there is no ruin to
paint. A neutral `mine` subject would paint a few of the stand-in variants
in an `intact` and an `active` look (lamps lit, a cart at the mouth), with
no team colour and no recolouring, keeping each variant's footprint and
anchor.

**Done when:** painted mine sheets are installed under
`warband/assets/restyled/`, and the map and the portrait use them (the
low-poly render stays behind `WARBAND_ART=procedural`). A worked mine wears
its active look only while the player can see it; out of sight it shows
what was last seen (WB-027's rule). `tools/visual_lint.py` passes the new
frames (no drift from the stand-in, no fringe), and native frames of an idle
and a worked mine on all three map themes are looked at. Presentation only:
the fingerprint and the contract are unchanged.

**Started 2026-09-19**, branch `painted-mine`.

**Acceptance (recorded before implementation):**

1. `tools/restyle.py` gets a neutral `mine` subject in two looks: `intact`,
   painted from four of the twenty stand-in variants, and `active` (a worked
   mine: lamps lit, a cart at the mouth), painted from the installed intact
   painting. No team colour: the prompt forbids blue and nothing recolours it.
   The vision judge passes every cell of both looks; each painted variant keeps
   its stand-in's footprint and anchor.
2. The map draws a mine from the painted variants (the tile hash picks one of
   the four), in the active look while a peasant works inside and the player
   sees it; out of sight it shows the look last seen, as buildings do since
   WB-027. The selection panel's portrait is the painted intact frame.
   `WARBAND_ART=procedural` still draws the twenty stand-ins.
3. Tests: the painted sheets load and a mine's image is painted; a worked mine
   in sight is active and one out of sight keeps what was seen; the portrait
   is painted; with procedural art the stand-ins return. `tools/visual_lint.py`
   passes, and native frames of an idle and a worked mine on the three map
   themes are looked at. The fingerprint and the contract do not move.

**First part merged 2026-09-19 as `7f7de57`** (`b491200` on `painted-mine`).
The intact look is painted and installed (`warband/assets/restyled/mine.intact`):
four stand-ins (0, 5, 10, 15) repainted in the buildings' style, each figure's
box within 2 px of its stand-in's, no blue; the cut registered at scale 0.99,
no cell flagged. The map draws only the painted four, never recoloured; the
portrait is the painting; a mine is `active` while a peasant works inside and
the player sees it, and keeps the look last seen out of sight (tested; with
the active sheet made up in the test, since none is painted yet, the intact
painting shows). The art lint finds nothing new (the same 39 findings as
main) and checks the painted mines' footprint and drift; native frames of a
worked and an idle mine on summer, winter and wasteland were looked at. The
fingerprint and contract are unchanged. The painter is now handed a canvas
of the sheet's own shape: OpenRouter's model re-laid a portrait sheet out on
its default 3:2, eight mines instead of four.

**Blocked on a painter for the active look.** Codex, which also runs the
vision judge, is out of credits until 24 September; OpenRouter answered 402
(its credit is spent) after the two intact paintings (about $0.07 each). The
intact painting was judged by eye against the stand-ins instead: the judge
runs when Codex is back. What unblocks it: either painter again.
`tools/restyle.py --mines --looks active dump|render|cut DIR`, then `check`.

## WB-039 — A quieter selection

Ilya, 2026-09-18: a chime on every selection is perhaps too much. Every
selection that picks anything plays the `select` cue (`GameScene.select`
has a `quiet` flag, but no caller passes it): a click, a drag, Tab to an
idle peasant, a recalled group, a portrait click. In a fight that is a cue
every second or two, and it is the brightest one there is. Humans hear two
rising notes, E5 to A5 (`sound.select`); elves two bells, D6 to A6; dwarves
an anvil strike with two high rings (`warband/voices.py`). Only the orcs'
thump is dull.

There are two options. Selection can make no sound at all, because the
selection ring and the panel already answer. Or it can play one short, soft,
low tick well under the order cues, once however fast the selections come.
The order cues stay, because they confirm that something happened.

**Done when:** Ilya chooses after hearing the candidates beside today's cue
(a listening page like the one made for the death cries), and selection in
all four race voices is what was chosen. A test pins it: the new cue's level is
under the order cue's (or there is no sound), and a burst of selections
plays one sound. `SOUND_VERSION` is bumped so cached WAVs are made again,
and Ilya has heard it in a match. Presentation only.

**Candidates ready 2026-09-19; blocked on Ilya's choice.** The listening page
([Warband Selection Sound](https://claude.ai/artifact/ACNyp1fbcJBzSUF7BDusBK))
plays each race's order cue, today's selection cue and two candidates, singly
and as a burst of five selections in a second: A, silence; B, one soft wooden
tick for every race; C, a soft tick in each race's timbre (a muted pluck, a
drum tap, a low bell, a muffled anvil). Both ticks peak about 8 dB under the
order cues and would sound once however fast the selections come. The
generators and levels are in `docs/evidence/wb039/` on the machine that made
them. What unblocks it: Ilya's A, B or C.

## WB-041 — Folders for the source tree

Ilya, 2026-09-18: the package has no folder structure, so group what
belongs together, the way a person would. `warband/` holds 43 modules side
by side, from 17 lines to 2,887. Four of them hold nearly half of its 18,900
lines:
`model.py` (2,887), `scene.py` (2,398), `textures.py` (2,215) and
`pro_ai.py` (1,148). The imports already fall into layers, so the folders
can follow them. A proposal, not a decision:

```
warband/
  sim/     rules, races, model, path, mapgen, settlement, worker_ai, worker_knowledge
  online/  authority (the server's game), online_ai (a headless player)
  ai/      ai, pro_ai, archetypes
  arena/   arena, balance, telemetry
  player/  profile, scores, replay
  art/     textures, effects, ambience, production, visual_lint
  audio/   sound, voices, music, instruments, pieces, combat_sound, deaths, wreckage
  ui/      scene, view, title, multiplayer, profile_scene, replay_scene, score_scene, tutorial, style, icons
```

`sim/` is today's authoritative closure: `tools/ci_compatibility.py`
hashes `authority` and everything it imports. A test keeps the layers
honest, either an AST walk or `import-linter`: `sim` imports nothing above
it; `ai`, `arena` and `player` never import `art`, `audio` or `ui`; and
`art` and `audio` never import `ui`. After the move, split the four giants
along their seams, each split its own pure move: `model` into orders,
movement, combat, economy, construction and vision; `scene` into the match,
the HUD, overlays and input; `textures` into terrain, units, buildings and
painted sheets; `pro_ai` into economy, military and memory.

What moves with it:

* Imports in the package, the tools and the 79 test files (the tests can
  mirror the new tree), and the hidden imports in `tools/package.py`. 58
  docs name `warband/<module>.py` paths; `make check-links` catches links
  but not paths written in prose.
* The authoritative contract hashes file paths, and saga-online names
  `warband.authority:ONLINE` in 11 places and `warband.online_ai` in 4. So
  the move changes the contract and ships with a server rollout. The next
  rules series (WB-024, WB-016, WB-037) is the natural one. Saves and
  replays are JSON, with no pickles, so no stored class paths need
  migrating.
* Every open branch conflicts with a tree move (the campaign, `fast-sim`,
  rules work). Do it right after they land and tell the running sessions
  first. Make the move one mechanical commit, `git mv` plus import rewrites
  and nothing else, so history and blame follow the files.

**Done when:** `warband/` holds only `__init__.py`, `__main__.py` and the
subpackages, and the layer test is in the suite. The simulation
fingerprint and the replay tests are unchanged by the move, since it is
only a move. The suite, fuzz, a packaged native build and the online smoke
pass; saga-online's references are updated and the rollout is done.
AGENTS.md describes the tree and says where new code goes.

## WB-042 — Tests through public accessors, and property tests

Left from WB-040: 172 lines in 26 test files still reach into private members,
most often `view._trees` (22), `scene._card` (17), `_page_tile` (10),
`_blocked` (10), `_portraits` (9), `effects._items` (9) and `_ground_keys` (8).
Each is a missing public accessor or a test of internals: give the view and
the scene what the tests need to read, or test through what the player sees.
Then try `hypothesis` for the model and pathfinding, a few examples in the
fast tier and more in the slow one: every order atomic from any state, save,
load and replay round-trip from any seed and moment, paths keep their
invariants.

**Done when:** no test reads a private member of `warband/`, or each that does
says why; the property tests that earn their keep run in the tiers, and the
rest are recorded here with what they found.

**Done 2026-09-19:** merged as `13db600` (branch `public-tests`), published
as 0.2.63. Private reads in the tests went from 172 lines in 26 files to 67
in 13, each with its reason beside it: a staged state (a unit or building
removed without the fight, water or a gate carved as map generation would),
a brain's own questions (`test_ai`, `test_pro_ai`), the C twins held to the
private loops they replace (`test_fastsim`, `test_sight_discs`), the true id
counter a snapshot must not tell, and what Saga2D 0.3.8 does not offer (its
effects list, read in one helper; the mock's players and image count; the
camera's edge speed). The view and the scene offer the rest as properties:
tree and ground sprites, ground keys, water still to paint, smoke, fires and
shots; the fog and minimap images and chunk classification; the command card
and its buttons, portraits, page tile and page, queue hits, next autosave,
ghost and key hints; New game's preview world and picture. Trees are planted
through `flat_world(trees=...)`, and the checkpoint test goes through
`ONLINE["warband-v2"]`.

`tests/warband/test_properties.py` states four properties with Hypothesis (a
dev dependency), each with a few examples in the fast tier and many in the
slow one. A path steps legally and is the shortest there is, checked against
Dijkstra on 3 to 14 tile grids; an unreachable goal ends as near as anything
reachable. Two loads of a save play on alike. An order the rules refuse
leaves no trace, and only a RuleError refuses one (24 orders, any ids,
points, tiles and types). A recording with orders of any kind and value,
given among two brains' at any moments, plays back through JSON to its match
bit for bit. What they found, none of it worth more than recording:

* An order for a seat out of range raises IndexError (for -1, it acts for
  the last seat). Nothing online can send one: the authority gives each
  seat's orders with that seat's own index.
* A load is not bit-exact with the world saved. A load brings sight up to
  date with where the units stand, and a unit's path, replanning clock and
  progress watchdog are not saved, so a peasant walking when the match was
  saved plans afresh. Replays play from the start and the order log, and the
  online authority is the one world there is, so nothing depends on it.
* A few seeds in a thousand make no fair map, and the New game screen
  crashed on one: WB-046.

Saga2D offers no public list of a scene's live effects, nor the mock
backend's players and images; the tests read those in three places and say
so, which is not a game need that would earn an engine change.

## WB-044 — Hold the push that comes with a rush tower; strike faster on Hard

What WB-037 left of its acceptance. Against `pro-rush` the defender now stops
the tower or kills it within a minute of standing in 38 and 39 of 40 games for
Master's postures, and loses no more than three peasants to it in 37 of 40.
But the rusher's first push arrives as the tower stands, while the
defender's peasants are coming back from the strike, and the defender keeps
70% of its gold in only about half the games where a frame went up. Traced on
seed 7002: the tower died 21 s after it stood, then five to nine soldiers
overran a defender with one or two and 1,600 to 2,000 gold banked unspent.
Hard strikes with its nine peasants and a soldier or two, and in eight of 40
games against the placed tower that took more than a minute (43 to 83 s).

**Done when:** on 20 fresh seeds over all five layouts, both corners,
measured as WB-037 counts them (`docs/evidence/wb037/rush_answers.py`, to
become a tool), Master's postures and Hard hold all three of WB-037's counts
in nine games of ten against `pro-rush`, and Hard does against the placed
tower. The ladder shows no loss against ordinary opponents. If Hard's
handicaps (thinking every second and a half, six peasants a mine, one
barracks) are what keep it short, the numbers go to Ilya before any
handicap is touched.

**Measured 2026-09-19** on main after WB-036, WB-014 and WB-045 (branch
`rush-push`, evidence under `docs/evidence/wb044/`), on WB-037's tuning seeds
(5000, 20 seeds, both corners): against `pro-rush` all three counts hold in
35, 37 and 27 of 40 games for the Vanguard, the Warden and Hard, and against
the placed tower in 40, 38 and 31. The Warden meets nine in ten, the
Vanguard is a game short, Hard well short (WB-037's fresh seeds from 7000 had
given the Vanguard 32 and the Warden 31). Traced (Vanguard, seed 5016, corner
1): the tower died 22 s after it stood, but the defender had no soldier until
170 s and had struck the frame with ten peasants for 25 s that took nothing
off it (ten a second against its growth of ten), and the rusher's push then
met an empty bank. Striking the frame 6 or 12 s before it stands instead of
25 changed nothing (35 or 36, 37, 25 or 25). Hard with each handicap lifted
alone, against the rush and the placed tower: thinking as fast as Master 27
and 32, ten workers a mine 15 and 27, two barracks 29 and 34: no single
handicap is what keeps it short, and closing the gap would make it a
different brain. **Blocked** on Ilya: whether Hard is to meet the rush bar
at all (and with which handicaps), and whether the defence against a push
that arrives with a tower is worth an AI project of its own for Master's
last game or two.

## WB-046 — A seed the game chose that makes no fair map

Found by WB-042's replay property: `mapgen.generate` refuses a few seeds in a
thousand with `NoFairMap` at some settings. Of the first 300 seeds, Small with
two seats fails on 67 (Forest, "roads too straight") and Medium with three on
33, 53, 109 and 213 (Crossings); none of 20,000 fails at the title backdrop's
Medium with two. The local game does not catch it. Pressing R on the New game
screen onto such a seed ends in a traceback, and so does changing the size,
seats, race or layout onto one, New game after a match (the next seed), and
hosting a LAN match. An online room is refused with advice to choose a larger
map, where the next seed would do.

**Done when:** wherever the game chooses the seed, it plays the first seed
from its choice that makes a fair map of the settings. That covers the title's
backdrop, New game's draw and reroll, New game after a match, a LAN or online
room from the multiplayer menu, and the command line's lobby without
`--seed`. The New game screen shows that seed and previews the map Start
plays. A seed the player gives (`--seed`) still fails with the clear
`NoFairMap`. Each path has a test from a seed known to be unfair; the backdrop
goes through the same function and has no test of its own, since no unfair
seed is known there. The authoritative contract is unchanged, so no server
rollout.
