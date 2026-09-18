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
section; git history keeps the record. The last ID given is **WB-041**; a new
item takes the next one and updates this line.

Done and removed 2026-09-18, every one merged into main (whose code is live as
Warband 0.2.30): WB-001 to WB-009, WB-015, WB-017 to WB-023 and WB-025 to
WB-034. Their acceptance and evidence are in
[the backlog at `1a6e08b`](https://github.com/ikamensh/warband/blob/1a6e08b73872cb595756a9d4ba7bc96c685c5ef0/BACKLOG.md).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-040 | First | proposed | A fast test suite by default; slow tests on demand and in CI; better tests on the way | User 2026-09-18 |
| WB-010 | Next | in progress | Smooth online movement and make connection problems understandable | Suggested |
| WB-011 | Next | in progress | Keep fog-hidden state out of opponents' network snapshots | Suggested |
| WB-012 | Later | proposed | Support three- and four-human online FFA | Suggested |
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-014 | Next | proposed | Revalidate difficulty and race balance after recovered branch work | Suggested |
| WB-016 | Next | in progress | Assess and recover the six-mission Thornwood campaign | Recovered branch |
| WB-024 | Next | proposed | Plan fewer paths in a melee: the world step's largest cost is attackers replanning after every shuffle | WB-009 |
| WB-035 | Later | proposed | Open a match on a small map without margins beside it on a large canvas | WB-021 measurement |
| WB-036 | Next | proposed | Try a tower-rush posture; if it rates higher, Hard plays it now and then and Master often | User 2026-09-18 |
| WB-037 | Next | proposed | Answer a tower rush without stopping the economy: one tower by the mine now halts Master's gold | User 2026-09-18 |
| WB-038 | Next | proposed | Paint the gold mine with the image model, with a worked look, like every building | User 2026-09-18 |
| WB-039 | Next | proposed | Stop chiming on every selection | User 2026-09-18 |
| WB-041 | Next | proposed | Give the package folders: group the 43 flat modules by what they are | User 2026-09-18 |

## WB-010 — Online responsiveness and connection feedback

The online path publishes world snapshots at 10 Hz; distinguish that
cadence from local 20 Hz simulation and frame pacing. Measure command-to-visible
response and jitter under controlled latency; evaluate bounded presentation
interpolation separately from prediction. Keep hit/death events synchronized,
and show useful reconnect/stall status while avoiding unbounded queued orders.

WB-003's real-socket capture reproduces 49/59 stationary display intervals at
60 FPS, then jumps up to 7.68 px for infantry/workers and 10.88 px for knights
at normal zoom (`docs/evidence/movement/online-trace/`). Local interpolation
does not fix this separate path; see [the diagnosis](docs/movement-diagnosis.md).

**Done when:** two real clients under delay/disconnection/rejoin have measured,
improved movement and correct orders/events, with no stale motion after resume.
Use S2D-010 for genuinely shared transport/rate work.

**Started 2026-09-18** (Ilya: "later is now"), branch `online-motion`
(worktree `../warband-motion`). Where it starts: `NetworkGameScene` never
records the positions it presents. Its motion fraction comes from the local
step accumulator, which a network scene never fills, and each snapshot is
applied with `view.sync()` at fraction one. So a unit stands still between
snapshots and jumps when one lands. Orders during a disconnection are already
refused: the engine's `OnlineClient.submit` refuses them while the seat is
not ready and bounds its outgoing queue, and since WB-030 the HUD shows the
refusal. This change is to the client only (`multiplayer.py`, `view.py`), so
it publishes without a server rollout.

**Acceptance (recorded 2026-09-18 before implementation):**

1. Measured before and after: `tools/verify_movement.py --scenario online`
   (real loopback socket, 20 Hz host, 10 Hz publication) gains uneven arrival
   (snapshots held back by a seeded jitter) and records, for a walking worker,
   footman and knight at normal zoom, the stationary display intervals and
   the largest jump between frames. The WB-003 baseline is 49/59 stationary
   intervals, with jumps up to 7.68 px and 10.88 px.
2. Presentation: in steady travel, at most 3 of 59 intervals are stationary,
   regular or jittered, and no jump exceeds twice the unit's steady travel per
   frame. A unit in sight moves on screen from where it was drawn towards
   where the latest snapshot puts it, over the measured interval between
   snapshots (clamped to 50–250 ms). What the model says is the snapshot's:
   selection, orders, fog, hit points.
3. No stale motion: a unit that appears or comes into sight is placed, not
   slid. After a gap of more than half a second (a stall, the partner's pause,
   a reconnect or a resume), units are placed where the snapshot says.
4. Events: hits and deaths show once, as before; repeated snapshots never
   replay them.
5. Connection status: when a ready session has had no new snapshot for more
   than a second, the status line says so and for how long. Reconnecting and
   waiting keep their messages. An order given while the seat is not ready is
   refused with the reason, and a test pins that.
6. Two real clients over a socket, with held-back snapshots and a
   disconnection and rejoin: movement is measured, orders and events are
   correct, nothing slides after the resume. The suite passes, and native
   frames of a walk are looked at.

## WB-011 — Player-specific network visibility

Since WB-031, `WarbandMatch.snapshot(player)` leaves out the server's random
stream and the other seat's explored ground and remembered map. It still sends
every unit, building and player record (orders, loads, the other seat's
economy and research) and every recent event, whatever the fog hides from that
seat: the client hides it (since WB-027 buildings too), but the data is all
there. Before public
competitive play, send only the information that player is allowed to know,
including safe event payloads and remembered discoveries. Rendering fog over a
complete snapshot does not protect hidden information.

**Done when:** serialized snapshots/events cannot reveal unexplored enemy units,
orders, economy or research; exploration, remembered buildings, combat and
reconnection still work in real two-client tests. Keep this separate from
compression and from claims of comprehensive anti-cheat.

**Started 2026-09-18** (Ilya: "later is now"), branch `visibility` (worktree
`../warband-visibility`). It ships in one server rollout with WB-016.

**Acceptance (recorded 2026-09-18 before implementation):**

1. Units and buildings: a seat's snapshot carries all of its own, and of
   everyone else's only what its units and buildings see now, including a
   player's last holdings once the rules expose them. An enemy unit out of
   sight or inside a mine or building is absent. One in sight carries its
   position, type, hit points, facing, motion and pose, but no orders, route,
   home or automatic-work state. An enemy building in sight carries its
   footprint, hit points, construction and abandonment, but no queue,
   research or rally point. Out of sight it is absent, and the client shows
   it as last seen (WB-027).
2. Economy: the other seat's gold, lumber, upgrades, statistics, last alert
   and assembly point are blank until the match is decided, and its
   settlement plans are absent. The world's id counter tells nothing beyond
   the entities sent.
3. Ground: out of sight it is as the seat remembers it, so trees felled or
   grown back there are not news; ground never seen is as the map began. A
   mine out of sight carries the gold the seat last saw; a mine never seen is
   absent. A shot in the air travels when the seat can see where it is.
4. Events: a seat hears of what it saw happen, of its own affairs (units it
   trained, research, refusals, deposits, alarms and plunder, told to it
   alone) and of the match's public news (victory, elimination, surrender,
   resignation, exposure). Who saw an event is decided when it happens, not
   when a snapshot is sent, and the checkpoint carries it.
5. Proof: a test sends a snapshot as JSON and looks for every hidden fact:
   a unit in unexplored ground, the enemy's gold, research and orders, its
   plans, a tree felled and a mine mined under fog, an event in fog. It fails
   on the old code. Exploration, remembered buildings, combat and
   reconnection work between two real clients over a socket. The suite passes
   and the simulation fingerprint does not move (only the authority changes).
6. Compatibility: the previous release's client loads the new snapshots,
   checked in the rollout rehearsal. A checkpoint written by the previous
   server restores. It has no record of who saw what, so its last five
   seconds of events are told to both seats once, and its terrain at restore
   stands for the map's beginning.

## WB-012 — Three-/four-human online FFA

Local skirmish supports two to four players; current hosted rooms and
WarbandMatch are two-seat. Generalize seats, lobby/race choices, ready/start,
disconnect/rejoin and results through S2D-011, then adapt the game. Reuse the
free-for-all resignation rules (`World.resign`: the player's buildings stay,
abandoned). Spectators, teams and ranked matchmaking can wait.

**Done when:** three and four actual clients complete seeded matches, recover a
disconnection and handle a resignation without premature victory or seat leaks.
Require WB-011 before presenting this as public competitive play.

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

## WB-016 — Assess the Thornwood campaign

The retained `campaign` branch at `9dbc98f` contains four unique commits: a
six-mission campaign, scripted outcomes, briefings, dialogue, choices and saved
progress. Review its product fit and playability before adoption. Integrate
against the current profile/title UI and the pinned engine; preserve ordinary
skirmish and replay behavior. Keep durable campaign progress in the player's
data folder beside the profile ([storage guide](docs/warband-profile.md)).

**Done when:** each mission's start, objectives, win and loss paths are verified;
choices and unlocked missions survive a new process and an upgrade; the title
and briefing screens fit supported resolutions and have inspected native frames.
Run the full suite and test scripted outcomes separately from normal elimination.
Record whether the campaign is accepted or retained with specific remaining
issues, and clean up the branch only after its work is safely accounted for.

**Assessed 2026-09-18** (branch `campaign` at `9dbc98f`, worktree
`~/saga/warband-campaign`): four commits on top of `d24446a` add the campaign
(`campaign.py`, `missions.py`, `dialog.py`, `mission_scene.py`,
`campaign_scene.py`, `docs/warband-campaign.md`, `tools/verify_campaign.py`,
`tests/warband/test_campaign.py`: 2,415 lines in 17 files) and touch the
model (`World.scripted`, `clear_player`), the scene (a mission's pause menu
and objectives panel), the title (the Campaign entry, a tighter menu at 720
tall) and the layout test. Its own 14 campaign tests pass on the branch. By
the evening of 2026-09-18, after the balance merge, main had moved 266 commits
past `d24446a`, and a test merge conflicts in six files, fourteen hunks:
`model.py` (four), `scene.py` (four), `title.py` (three),
`tests/warband/test_layout.py`, `AGENTS.md`, and `tests/warband/test_model.py`,
where both sides appended tests. The hunks are small, so a rebase is an
afternoon's work, not a rewrite. Two things follow from it: the model change
moves the authoritative contract, so the rebased campaign can only be
published with a server rollout, and the natural place is the next rules
series with WB-024; and the missions are tuned by scripted play only, so
they need the human playtests of WB-013 before the campaign is called
accepted. Nothing in the branch is lost: the worktree and branch stay until
the decision.

**Adopted 2026-09-18** (Ilya: "we don't have a better one"). Main is merged
into `campaign` rather than the branch rebased, so its four commits stay as
they are. It ships with WB-011's server rollout instead of waiting for WB-024,
which nobody has started. Two things main added since the branch began matter
here. `mapgen.generate` draws a layout from the seed when none is named, so the
missions' hand-placed setups would land on a random river or rock ring. And
every `GameScene` is ranked (recorded and rated) unless it says otherwise.

**Acceptance (recorded 2026-09-18 before implementation):**

1. On today's main: the six conflicting files resolved keeping both sides'
   intent. A mission is unranked: never recorded as a replay, rated or put on
   the leaderboard, and leaving one asks no rated-match question. The suite
   passes on the pinned engine; skirmish play is unchanged
   (`tools/sim_fingerprint.py --check`, or refreshed deliberately if the save's
   new `scripted` key is part of what it hashes).
2. Maps: every mission names its layout and none draws one from its seed. The
   ford (Greywater Ford, Greywater Retaken) is Crossings, the Court of Thorns
   Forest, the others Plains, the nearest to the one generator the missions
   were written for. Each setup fits its map (placement raises when it does
   not), and a native frame of each of the six starts is looked at: bands,
   camps and goals where the story puts them.
3. Every mission both ways: a test per mission starts it as the campaign
   screen does, checks its first objectives, plays its win and every way it
   can be lost, and checks what the campaign records: the next mission, the
   flags (truce, powder, burn) and the epilogue's lines. A second process
   reads the progress file and offers the same next mission and flags.
4. Screens: the title with its Campaign entry, the campaign screen (fresh,
   under way, finished), a briefing, the objectives panel, a line, a
   question, both results and the mission menu fit at 1280×800, 1280×720 and
   1200×680 (`tests/warband/test_layout.py`); `tools/verify_campaign.py`
   frames at 1280×800 and 1200×680 are looked at; `tools/visual_lint.py` is
   clean.
5. Rules: `test_model.py` covers a scripted world (no winner declared, no
   surrender, `clear_player` quiet and undone by the side's next unit or
   building); `tools/fuzz.py` with its monkey is clean.
6. Shipped: merged into main with Tests and Native package checks green.
   `model.py` moves the authoritative contract, so the release is promoted
   after the server rollout it shares with WB-011. The missions' tuning stays
   for people to judge (WB-013), and the campaign doc's "Not yet" says so.

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

## WB-035 — A small map fills a large window

Found 2026-09-18 while WB-021 was measured on the 4K Windows desktop
(`docs/evidence/win4k/candidate-150/`): at 150 % scaling the canvas is 2480
units wide and a Small map at zoom 1 is narrower, so the match shows
earth-dark margins beside the map, as it already does on any 2560×1440
desktop at 100 %. The window is right; the camera's starting zoom is what
leaves the margins.

**Done when:** a match on a Small map opens without margins beside the map on
those canvases while other map sizes and the 1280×800 window open as today;
native frames of both are looked at. Presentation only: the simulation
fingerprint is unchanged.

## WB-036 — A tower rush for Hard and Master

Ilya asked on 2026-09-18 for a "cannon rush" brain: if it lifts the rating,
Hard plays it with a small chance and Master with a medium one. Warband has
no cannons. Its static defence is the Guard Tower: 700 gold and 250 lumber,
400 hit points, armour 3, two tiles square, 35 s to build, needs a
barracks, and shoots 8 damage every 1.5 s at six tiles. The rush is an early
peasant walking to the enemy's gold mine and raising one or two towers
beside it.

The ai-2000 push tried it once and dropped it without a rating: the
builder's order died on arrival after a forty-second walk, five times a game
([the scout that never left](docs/ai-ladder.md#the-scout-that-never-left)).
First find out why the order dies and fix that. Then give `ProProfile` the
knobs (how many towers, when, where, how many builders) and register the
posture for `tools/arena.py`. Hard's version keeps Hard's handicaps
(`PRO_HARD`: slow thinking, six workers a mine), so Hard stays below Master.

Rate it only after WB-037. Against today's answers, a finished tower by the
mine stops Master's gold for minutes (WB-037's measurement), so a rush would
win on that bug rather than on play that also beats a human. Build the
posture first as the opponent WB-037 iterates against; rate it once those
answers are in.

`make_brain` picks a difficulty's posture from `PRO_FOR` by
`(seed + player) % len(postures)`, which gives every posture an equal share. A small or medium
share needs a weighted draw that still depends only on the seed and the
player, so every client of an online match and every replay agree. Start
from one Hard game in eight and one Master game in three.

**Done when:** the rush posture is rated after WB-037 with `tools/arena.py
ladder` against `pro-hard`, `pro-vanguard` and `pro-warden`, on fresh seeds
over all five layouts, at least 96 games a pairing. If it scores above the
postures it would join, Hard and Master draw it at the chosen shares; a test
pins the draw to the seed and player and checks its shares over many seeds;
the New game screen's ratings are re-measured with the 720-game protocol and
its notes mention the rush; the fingerprint is refreshed deliberately. If it
does not, its numbers go into [docs/ai-ladder.md](docs/ai-ladder.md) and the
knobs are deleted. The brains are outside the authoritative contract
(`warband/ai.py` and `pro_ai.py` are not in its import closure), so no
server rollout is needed.

## WB-037 — Answer a tower rush without stopping the economy

Ilya asked on 2026-09-18 whether the computer players stop all mining when
a tower goes up by their mine, which is strictly worse than any real answer.
They do. It was measured the same day (script and log in
`docs/evidence/tower-rush/`): Master played a player with no brain on ten
seeds, and a finished enemy tower was placed 2–3 tiles behind Master's main
mine at 150 s. In the next minute Master's gold fell to 0–1,400, against
6,400–7,600 without the tower. In seven seeds the tower still stood at
330 s. Master had 0–1 soldiers (12–22 without the tower) and 3–11 peasants
(15–24 without), and its gold still came in at 0–2,300 a minute. In the
other three seeds its army killed the tower within about a minute and mining
resumed.

The code shows three causes:

* The automatic worker policy blocks every tile within the tower's range
  plus 1.5 (7.5 tiles from its footprint) for automatic harvest and deposit
  trips (`warband/worker_ai.py`, `_navigation`). A tower within about four
  tiles of a mine covers every tile the mine is worked from, so no automatic
  peasant goes to any face, even one the tower cannot reach. A tower that
  also covers the hall's edge leaves peasants holding gold they cannot
  deliver. The computer players' peasants are automatic, and so are a
  human's.
* Master defends only against enemy *units* within nine tiles of its
  buildings (`ProBrain._threats`). A tower is a building, and a
  peasant raising one is inside the construction, so no defence is called.
  The soldiers meet the tower only when they wander into its range, a few
  at a time, and they die a few at a time.
* Orders the brain gives itself (`world.harvest` in `_chop`, builds) are not
  automatic, so they path over plain ground, through the tower's fire. Where
  the peasants actually die is still to be traced.

Answers to iterate on, against WB-036's rushing posture:

* A tower going up by the mine or hall is a threat. The army kills the
  builder or the frame while its hit points are still low (`shell_hp`
  starts it at a tenth), and peasants do it when there is no army.
* A finished tower is attacked by a force that gathers out of its range and
  is big enough to kill it, not by soldiers arriving one by one. Catapults
  (seven tiles) outrange it.
* The peasants keep working what is out of range: faces the tower cannot
  reach, another known mine, the trees. None stands idle while safe work
  exists, and none carries gold it cannot deliver.
* `_defend` keeps peasants out of fights because calling them measured about
  35 Elo worse. That was against soldiers; whether peasants should help
  against a lone tower is to be measured, not assumed.

The worker policy is part of the model. Changing its margin, or checking the
faces one by one, moves the authoritative contract, so that part ships with
the next rules series and its server rollout (with WB-024 and the model
changes of WB-016). The brain's answers are client-side and need no rollout.

**Done when:** on twenty or more seeds over all five layouts, against
WB-036's rush posture and the evidence script's placed tower, Master and
Hard stop the tower or kill it within a minute of its completion in nine
games of ten, lose no more than three peasants to it, and bring in at least
70 % of their unrushed gold over the three minutes after it appears. The
placed tower becomes a regression test: gold resumes and the army does not
die piecemeal. The fingerprint is refreshed deliberately, and the ladder
confirms that Master's rating against ordinary opponents did not drop.

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

## WB-040 — A fast suite by default; slow tests on demand and in CI

Ilya, 2026-09-18, high priority: make the test suite dramatically faster.
Split it into fast tests that run by default and slow ones that run on
demand and in CI, write the agent instructions for both, and improve the
tests on the way (merge them, state properties, think long term).

Where it stands: 1,284 tests in 79 files, 13,300 lines of tests for 25,000
lines of game and tools. CI runs them all in one process: 508 s on the last
green run (1,272 passed, 12 skipped). AGENTS.md says about four minutes
locally. No test is marked slow, nothing runs in parallel, and no Saga repo
has a split yet. The code shows the expensive kinds: whole matches (arena
tests play up to 20 minutes, some twice to check the settled rule;
`test_pro_ai.py` plays a six-minute four-player match), matrices that build
a scene per case (146 layout cases, 129 melee-presentation cases), and art
and audio generation. Start with `pytest --durations=0` on a quiet machine
to see where the time actually goes.

The split:

* `uv run pytest -q` runs the fast tier, which an agent runs after every
  change. Aim for about 30 s for the whole tier on the Mac, with a per-test
  budget (half a second, say).
* `@pytest.mark.slow` marks the rest, and `--slow` (a conftest option) runs
  them. The default run lists them as deselected, not skipped, so nobody
  forgets they exist. A slow test's docstring says why it cannot be fast.
* CI runs both tiers on every push, the slow tier in parallel with
  `pytest-xdist` (the repo is public, so its runners have four cores). CI
  also fails when an unmarked test goes over the budget, so the fast tier
  cannot slow down unnoticed.

Faster, not only split:

* Expensive things that never change (generated maps, loaded painted
  sheets, synthesized clips) are built once per session, not once per
  parametrized case. Nothing mutable is shared between tests.
* A test of the arena's machinery (determinism, placements, the settled
  rule) plays the shortest match on the smallest map that shows the
  property. How strong an AI is gets settled by `tools/arena.py`, not by
  the suite.
* Only valid cases are generated: the 12 skipped tests are production-UI
  cases for another race's art.

Better, not only faster:

* The three kinds of test that earn their keep: executability (every
  module and screen runs), properties (every World order is atomic, save
  and load and replay round-trip from any seed and moment, maps are fair
  over seeds, layouts and player counts, paths keep their invariants), and
  regressions (the fuzz-seed tests stay). For the model and pathfinding,
  try `hypothesis` with few examples locally and more in CI.
* Near-duplicate tests merge into one property whose failure message names
  the failing case.
* Tests check behaviour through public interfaces. Today 206 lines in 38
  files touch private members. The most common, `game._teardown()` (42),
  shows the engine's test support has no public way to make a second game,
  which is an S2D item. Each of the rest is a missing public accessor or a
  test of internals.
* Tests that pin tuning constants go (`PRO_WARDEN.towers_early == 1`): they
  break on every balance change and catch nothing.

The guard: measure coverage of `warband/` before and after
(`uv run --with coverage`). The full suite's coverage must not drop, and the
fast tier alone should cover about 85 % of the lines the full suite covers,
so it is a real check rather than a smoke test.

AGENTS.md's Commands and Rules say which tier runs when: the fast one after
every change; the slow one on demand, before pushing a change to rules, AI,
replays, art or audio, and always in CI. They also say what counts as slow,
where a new test goes, and what the budget is. The stack root's "every repo:
`uv run pytest -q`" stays true. Once a second Saga game wants the same
split, the option and the budget check move into `saga2d.testing`, where
the fixtures already live.

Other sessions edit tests all the time, so do this on a branch in its own
worktree. Land the mechanism first as one small commit (marker, option, CI,
AGENTS.md), then improve the files a few at a time, rebasing often.

**Done when:** the fast tier runs in about 30 s on the Mac and the whole
suite in under four minutes in CI (from 8½). The budget check fails CI when
a test goes over. Coverage before and after is recorded here and meets the
guard. The suite passes three runs in a row under `pytest -n auto`, and
AGENTS.md documents both tiers.

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
