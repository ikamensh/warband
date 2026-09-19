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
section; git history keeps the record. The last ID given is **WB-044**; a new
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
([`3f22525`](https://github.com/ikamensh/warband/blob/3f22525a4db442d7f8d0d2c02b7532375ad1e075/BACKLOG.md)).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-014 | Next | proposed | Revalidate difficulty and race balance after recovered branch work | Suggested |
| WB-024 | Next | closed | Plan fewer paths in a melee: the world step's largest cost is attackers replanning after every shuffle | WB-009 |
| WB-038 | Next | blocked | Paint the gold mine with the image model, with a worked look, like every building | User 2026-09-18 |
| WB-039 | Next | blocked | Stop chiming on every selection | User 2026-09-18 |
| WB-041 | Next | proposed | Give the package folders: group the 43 flat modules by what they are | User 2026-09-18 |
| WB-042 | Later | proposed | Tests read through public accessors; try property tests for the model and paths | WB-040 |
| WB-044 | Next | proposed | Hold the push that comes with a rush tower; strike faster on Hard | WB-037 |

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

## WB-014 — Difficulty and race-balance evidence

The balance work is merged and live as Warband 0.2.30 (2026-09-18: merges
[`4366789`](https://github.com/ikamensh/warband/commit/4366789) and
[`faed307`](https://github.com/ikamensh/warband/commit/faed307), then the
server's [balance rollout](../saga-online/docs/balance-rollout.md)): the mine
cap (eight at the face), Master expanding when its mine fails, the price and
race changes, the repair-cost fix, match tallies, the posture league
(`tools/balance_report.py`), settled matches and layout cycling. The leagues'
evidence and findings are in [docs/balance.md](docs/balance.md). The ratings
the New game screen shows were re-measured on merged main with the 720-game
protocol: Easy 856, Medium 1000, Hard 1353, Master 1589
([docs/ai-ladder.md](docs/ai-ladder.md)).

Still to check, on current main with the arena and AI-report tools over
adequate seeded samples: Easy against a basic opening, and free-for-all
endings. Keep economy/crowding failures distinct from numerical balance.

One experiment is unaccounted for: the `ai-arena` worktree
(`~/saga/warband-arena`, its branch merged) holds an uncommitted edit to
`warband/pro_ai.py` from 2026-09-16, an `opening_choppers` knob that keeps two
to four peasants on the trees for the first three minutes, with the trial
profiles `pro-open2` to `pro-open4`. It no longer applies cleanly to main (one
of its three hunks). Port and rate it with `tools/arena.py`, or drop it; then
remove the worktree.

**Done when:** a recorded report supports the displayed difficulty expectations;
concrete regressions become small fixes with rule tests, fuzz and refreshed
fingerprints where appropriate. Do not retune from a few observed matches.

## WB-024 — Plan fewer paths in a melee

The W10 frame gate (late p95 under 16 ms) is missed by one to two milliseconds
in every scenario WB-009 measured on 2026-09-18 (the W10 row of the
[progress record](docs/warband-early-access-progress.md), logs under
`docs/evidence/perf/`). The renderer's share is S2D-016 and S2D-017; the
model's share is this item.

WB-009's trace of the 150-unit reference battle: a world step averages 3.5 ms
and 45 % of it is `find_path_grid` (1,621 plans over 240 steps), because an
attacker plans again whenever its target moves to another tile
(`_approach`: `path_goal != goal`), throttled only by `REPLAN_EVERY` and the
stagger; a fallen farm makes many plan at once (28 ms in one step), and a
match's first step, which plans for every ordered unit at once, is its slowest
frame (`find_path_grid` 60–100 ms, a frame of 103–125 ms). A unit
already within a step or two of a target that shuffled inside its reach does
not need a new path, and a target that moved one tile could keep the old
path's tail. This changes when units move, so it moves the simulation
fingerprint and the authoritative contract: it goes with the next rules
series and its server rollout, not on its own.

**Done when:** the reference battle's plans per step fall by half or more
with the same fights decided the same way (the arena's ladders unchanged
within noise), the step's p95 under 3 ms in `tools/step_bench.py`, the late
p95 of `tools/perf.py` measured before and after, seeded fuzz clean, the
fingerprint refreshed deliberately with the rest of its series.

**Closed 2026-09-19 without its done-when, merged as `dd7cf5f`** (`b72cfc9`
on branch `fewer-paths`): the premise was the reference battle's, not the
model's. Its seed had come to draw a wooded layout, and `battle_world` placed
72 of its 150 soldiers in trees; 41 were still in them 300 steps on, each
planning a way out every 0.6 s, and those plans were the "45 % of a step" and
the 28 ms bursts. The battle now plays on plains with the battlefield cleared
to grass (as map generation carves a road), a soldier whose cell a building
stands on is put beside it, and a test holds every soldier to open ground
(it fails on the old battle). On it, with main's model: 684 plans over 300
steps (2.28 a step, 150 of them the opening's), shoves that plan 7 of them;
pathfinding 33 ms over 720 frames of `tools/perf.py`, 0.3 % of frame time,
where the old battle spent 411 ms; the step 2.25 ms, 5.4 % of it; the
source's step p95 3.6 ms in `tools/step_bench.py`
(`WARBAND_INTERPRETED=1`: the tools run the compiled simulation otherwise).
A rejoin for shoved units, tried first, saved nothing on the clean battle
and was dropped. The frame p95 is 18–20 ms on the same Mac under other
sessions' load, set by gen-2 collector pauses of about 25 ms and the
renderer's end of frame: S2D-016 and S2D-017, recorded in the W10 row of
`docs/warband-early-access-progress.md`. Nothing in the simulation, contract
or fingerprint moved. Main ran
[Tests 35412937637](https://github.com/ikamensh/warband/actions/runs/35412937637)
and [native package checks 35412937589](https://github.com/ikamensh/warband/actions/runs/35412937589).

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
