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
section; git history keeps the record. The last ID given is **WB-035**; a new
item takes the next one and updates this line.

Done and removed 2026-09-18, every one merged into main (whose code is live as
Warband 0.2.30): WB-001 to WB-009, WB-015, WB-017 to WB-023 and WB-025 to
WB-034. Their acceptance and evidence are in
[the backlog at `1a6e08b`](https://github.com/ikamensh/warband/blob/1a6e08b73872cb595756a9d4ba7bc96c685c5ef0/BACKLOG.md).

| ID | Priority | Status | Task | Origin |
|---|---|---|---|---|
| WB-010 | Later | proposed | Smooth online movement and make connection problems understandable | Suggested |
| WB-011 | Later | proposed | Keep fog-hidden state out of opponents' network snapshots | Suggested |
| WB-012 | Later | proposed | Support three- and four-human online FFA | Suggested |
| WB-013 | Next | blocked | Turn fresh-player and cross-platform playtests into reproducible fixes | Suggested |
| WB-014 | Next | proposed | Revalidate difficulty and race balance after recovered branch work | Suggested |
| WB-016 | Next | in progress | Assess and recover the six-mission Thornwood campaign | Recovered branch |
| WB-024 | Next | proposed | Plan fewer paths in a melee: the world step's largest cost is attackers replanning after every shuffle | WB-009 |
| WB-035 | Later | proposed | Open a match on a small map without margins beside it on a large canvas | WB-021 measurement |

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
