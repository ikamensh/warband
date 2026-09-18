# WB-003 — Movement diagnosis and acceptance

Started 2026-09-17 from `1a6def9` on `codex/wb003-movement`.
The earlier [motion design](unit-motion.md) describes intended behavior; it is
not evidence that current motion looks right. This work begins with captures
from the actual model, MapView and native renderer.

## Acceptance recorded before implementation

1. Capture infantry, workers and mounted units moving straight, diagonally,
   turning, starting/stopping and arriving in crowds or against an obstruction.
   Inspect painted and procedural art at normal, near and far zoom. Include
   offline rendering and the online snapshot cadence; keep network buffering
   work under WB-010 if it requires its own transport policy.
2. Record frame time, simulation tick, model/render position, facing, traveled
   distance and selected pose. Identify the dominant visible faults with a
   repeatable comparison that fails on the baseline. Separate pose/art faults
   from timing, displacement, turning, crowd movement and rendering stalls.
3. Fix the demonstrated movement faults in bounded increments. Native
   before/after recordings and frame strips at gameplay scale must show the
   improvement. Stopped units hold still, continuous travel looks continuous,
   turns follow the shortest direction without oscillation, and cadence follows
   speed. Inspection includes slow workers and fast mounted units.
4. Presentation changes preserve authoritative positions, orders, timings,
   saved/replayed state and the simulation fingerprint. Fog, selection markers,
   attached indicators and sprites agree; scene reset/rejoin and removal do not
   reuse stale motion. Pausing freezes motion. Record any deliberate rule change
   separately before implementing it.
5. Regression tests exercise actual scene/view journeys. Run the relevant view,
   online and replay checks, the full suite, visual lint and the simulation
   fingerprint. Inspect real native frames, including a crowded battle, and
   record any remaining art/framework/network issue as a separate backlog item
   with evidence instead of treating it as fixed.

## Evidence

Captures and temporary diagnostic traces go in
`docs/evidence/movement/` (ignored by Git). Keep a small reusable capture command
in `tools/` if it earns its place by reproducing the before/after comparison.
## First reproduced fault: simulation-rate sprite movement

`tools/verify_movement.py` drives a real `GameScene` on clear ground with a
worker, footman and knight. It records an MP4, gameplay PNG, eight consecutive
native frame crops and a JSON trace of the model and sprite on every frame.
Its mock mode uses the same scene for a fast feedback loop. Both modes use an
isolated temporary player directory. The default cooperative CPU budget is 25%.

Baseline commands (before the interpolation edit):

```sh
uv run python tools/verify_movement.py docs/evidence/movement/before-trace --backend mock --seconds 2
caffeinate -u -t 180
uv run python tools/verify_movement.py docs/evidence/movement/before-painted --seconds 2
```

During the second second of straight travel, **39 of 59 frame intervals were
stationary** for all three units. Workers/footmen jumped up to **3.84 px**, the
knight **5.44 px**, at normal zoom. The mock and real native traces agreed;
native median frame cost was 5.35 ms, excluding capture/encoding. The inspected
eight-frame strip repeated positions in groups of three. This is simulation-rate
judder, not evidence of a renderer that cannot sustain the requested frame rate.

Ranked hypotheses were direct 20 Hz position copying, pose-driven flicker, and
render/asset stalls. The first is confirmed: the local scene ticks the model at
20 Hz but the old view copied its current positions unchanged on every display
frame. The one-command regression was:

```sh
uv run pytest -q tests/warband/test_movement_presentation.py
# Before the fix: AssertionError: Steady travel froze on 39 of 59 intervals
```

## First bounded fix, still under WB-003 acceptance

The scene records non-hidden unit positions immediately before each local model
step; the view interpolates between that pair using the scene's actual fixed-step
accumulator. This presents the previous simulation interval (at most 50 ms of
delay at normal speed), without predicting or altering the model. Walk cadence
now measures presented travel, and selection rings/health bars share the presented
ground position. A view reset clears its position and distance history.

The same two-second native capture after the fix has **0/59 stationary intervals**.
Maximum steps are **1.28 px** for worker/footman and **1.81 px** for the knight.
The actual before/after gameplay PNGs and consecutive frame strips were inspected.
Evidence is under `after-painted/` and `interpolated-trace/` beside the baseline.
Nine scene regressions cover the three subjects at 30, 60 and 144 FPS; all pass.
The existing view suite also passed before expanding to those nine combinations.

First-increment verification on macOS 26.6.2 / arm64, Python 3.13.2, released
Saga2D 0.3.2:

- Full suite: **910 passed, 12 skipped**, one expected stale-sheet warning,
  193.61 seconds (`first-fix-tests.log`).
- Simulation fingerprint: `1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`,
  exactly matching the recorded baseline (`first-fix-fingerprint.log`).
- Native visual lint: army selection, damaged selection, battle and forest
  battle at 1280×800 and 1200×680, **zero findings**. Representative native PNGs
  from all four cases were opened and inspected (`first-fix-lint/`). These are
  layout/layering checks; the motion matrix below still needs completion.
- Stack Markdown links: 390 files, zero broken links.

The old walk-cycle test spawned its soldier into an obstructed part of seed 5.
It oscillated around (8.5, 8.5), accumulating small displacement, and never
traveled its ordered route. The replacement verifies actual distance covered,
every walk pose, a positive displacement on each display frame and a maximum
step bounded by the unit's real speed. It keeps the observable behavior assertion
without depending on an invalid spawn or a particular interpolation formula.

## Separate finding: travel budget lost at waypoints

Resolved 2026-09-18 as WB-017: `_follow` carries the tick's leftover travel
through waypoints, and `_next_waypoint` goes straight to the exact spot from
anywhere on its tile instead of the tile centre first (which walked past and
back). The straight trace has no short ticks left; see the backlog entry.

The clear-ground trace also records an actual model-speed dip at tile centers:
the footman normally moves 0.12 tiles per tick, then only 0.04 for the remainder
of a one-tile segment. `_walk_to` snaps to the waypoint and returns, discarding
the unused part of that tick's distance. Interpolation faithfully displays that
slower interval (0.427 px/frame instead of 1.28 at 60 FPS). A constant-speed
assertion would therefore be testing a false premise about the baseline model.
WB-017 records this rules-affecting issue with its own acceptance; the current
presentation change preserves it.

## Interaction, replay and save follow-up

Scene regressions reproduced three more presentation faults: replay scenes
still jumped at 20 Hz; repeated loads depended on the previous scene's leftover
fractional tick; click and box selection picked authoritative points ahead of
the visible units. Replays now share the same interpolation boundary, load resets
the accumulator, and selection/hover/attack/repair use presented ground points.
Replay pause preserves both position and pose; skipping to the end shows the
exact recorded final positions. The terminal local match also shows its final
authoritative positions.

The relevant scene/view/replay/socket suites pass **101 tests**
(`interaction-tests.log`). The new socket journey checks explicit empty ground,
enemy, mine and damaged-building targets, queued movement, and atomic rejection
of malformed/missing targets. A context order at the moving enemy's future point
also survives JSON recording and faithful playback. These are implementation
checks, not yet native or hosted acceptance of this increment.

The complete suite subsequently passed **917 tests, 12 skips**, with the one
expected stale-sheet warning, in 193.46 seconds (`interaction-full-tests.log`).
Two 500-input monkey journeys (seeds 81 and 82) finished without exceptions or
invariant failures (`interaction-fuzz.log`). The simulation fingerprint still
matches `1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`
exactly (`interaction-fingerprint.log`). This verifies unchanged default model
stepping; the new explicit pointer intent remains a compatibility-contract change.

### Presented pointer intent (acceptance before the protocol edit)

The scene regression also reproduces the inverse picking error: right-clicking
empty ground just ahead of a displayed knight attacks its newer model position.
Resolving a positive enemy hit to an attack ID alone does not fix this. Smart
orders must preserve the displayed target identity, including an explicit empty
ground result, instead of picking again after the click. Existing callers and
recordings that omit this intent retain their current model-point behavior.
Verify positive and negative pointer hits, resource/building actions, queued
orders, replay fidelity and the authoritative command path. Reject invalid
target types without changing the match. The simulation fingerprint must stay
identical. This adds an optional command field, so publishing requires a reviewed
server compatibility update; it cannot use the previous client-only baseline.

### Expanded capture matrix

`tools/verify_movement.py` now includes `turns`, `crowd`, `obstruction` and
`online` scenarios beside `straight`. Turns schedule diagonal orders, reversals,
stops and restarts. Crowds issue one group move to 18 mixed units. Obstructions
put a real rock barrier with a two-tile opening into the terrain before world
construction. Online uses a real loopback socket, 20 Hz host stepping and 10 Hz
publication, rendered by `NetworkGameScene`; it does not simulate internet
jitter. Every capture records unit IDs, scheduled orders, source state, engine,
art style, zoom and per-second native PNGs, alongside the original trace/video.

Planned native matrix: painted turns at 2×, painted crowd at 0.75×, painted
obstruction at 1×; procedural turns at 1×, procedural crowd at 0.75× and
procedural obstruction at 2×. The normal-zoom straight before/after above remains
the baseline comparison. The online baseline will be traced separately for
WB-010. The eight-second mock turn trace already shows stable stand poses during
both stopped intervals and bounded displacement for all three subjects.

The painted 2× turn capture (`painted-turns-near/`) is now recorded and its
diagonal, stop/restart and final-standing PNGs were inspected. Each subject has
exactly one presented position and the stand pose throughout frames 255–299
and 405–479 (after the final partial movement interval settles). The maximum
normalized heading step is 0.3142 radians for worker/footman and 0.2356 for the
knight; the trace crosses ±π continuously. Median native frame cost is 5.51 ms.
Two earlier framing trials are retained under `*-framing/`: their routes moved
subjects under the HUD, so the final route stays within the playable viewport.
The original fixed-height close-zoom strip cropped the mounted unit; the tool
now sizes frame crops from the actual sprite and zoom.

The procedural normal-zoom turn capture (`procedural-turns-normal/`) is also
recorded. Its diagonal and stopped native PNGs and the complete mounted frame
strip were inspected. It shows the same bounded travel and stationary stand
poses in both stopped intervals, with 5.71 ms median frame cost. Switching art
does not reintroduce the 20 Hz displacement pattern. The painted sheets have
more silhouette detail, but both currently use the same four-pose walk cycle.

The real-socket 10 Hz baseline (`online-trace/`) remains visibly stepped:
**49/59 stationary intervals**, with maximum jumps of **7.68 px** for worker/
footman and **10.88 px** for the knight at normal zoom. Its median mock scene
cost is 0.58 ms. This verifies a separate snapshot-cadence problem rather than
local simulation or draw cost; WB-010 owns buffering, latency and rejoin policy.

The procedural 0.75× crowd capture (`procedural-crowd-far/`) issues one move to
18 mixed units. Its approach and arrival frames were inspected; all 18 have
reached idle by the end of ten seconds. Median native frame cost is 7.33 ms.
Crowd pushes produce larger authoritative displacement than solo walking
(maximum presented step 3.69 world pixels), so the solo speed bound is not a
valid crowd-motion assertion. The trace preserves that model behavior.
This also exposes an existing HUD defect: the large selection's portrait row
extends under the command card at 1280×800. WB-018 records it separately.
The matching painted crowd capture (`painted-crowd-far/`) was inspected too:
all 18 units finish idle, the same maximum displacement is recorded, and median
native frame cost is 7.53 ms. The portrait overflow occurs with both art styles.
Idle at the final frame does not mean the whole approach was stationary: some
units are still displaced by arriving neighbours during the last second. That
authoritative push behavior is preserved, rather than hidden by interpolation.

Both obstruction captures (`painted-obstruction-normal/` and
`procedural-obstruction-near/`) were inspected at the gap and after arrival.
Worker, footman and knight all traverse the two-tile opening and finish idle
at their exact destinations on the far side by twelve seconds. Median native
frame costs are 5.85 and 5.65 ms respectively. The barrier is in the actual
collision terrain, not a visual prop that units could walk through.

The native pointer journey (`check_native_input.py`, `native-input/`) dispatches
real pyglet mouse and F3 events. Clicking the trailing edge selects the displayed
footman, right-clicking empty ground ahead of the displayed enemy produces a
move, and clicking the enemy's trailing edge produces an attack on its exact ID.
F3 freezes the tick, displayed point and walk pose. The selected, attack and
paused native screenshots were opened and inspected with ordinary fog enabled.
The corresponding repeatable regressions remain in the game test suite.

## Completed acceptance — 2026-09-17

The native matrix and pointer journey are complete. `35b851f` passed
[the game tests](https://github.com/ikamensh/warband/actions/runs/35210630104)
and [Windows/Mac native package checks](https://github.com/ikamensh/warband/actions/runs/35210630105),
including final artifact validation. The server compatibility rollout is now
accepted as `99e28517…54609f7`, and its baseline is integrated in Saga Online main
`89fe348`. The [rollout record](../../saga-online/docs/warband-movement-rollout.md)
contains Linux preparation, private retained-campaign restore/rejoin, actual
public pointer commands and all three downloaded Mac client checks. The final
server suite passed 135 tests in 89.94 seconds. The three retained campaigns and
the website pointer stayed intact through activation.

Main `2e31cda` passed [native build 35214358368](https://github.com/ikamensh/warband/actions/runs/35214358368),
[publisher 35215555895](https://github.com/ikamensh/warband/actions/runs/35215555895)
and [website promotion 35215726975](https://github.com/ikamensh/saga-online/actions/runs/35215726975).
Immutable release **0.2.0-preview.35214358368** is live; Saga Online catalog commit
`6b3c952` records its four package links. The public page points to those exact
packages, and the downloaded manifest's compatibility contract matches the live
server (`main-release/site-acceptance.json`).

[Public download run 35215886199](https://github.com/ikamensh/saga-online/actions/runs/35215886199)
passed on Windows and Mac. The anonymous downloads match the accepted archives,
source/version, frozen executable identity and bundled fonts. Both pass all eight
public online checks: create/join, movement, ownership rejection, private-seat
rejoin, production, automatic building, cancellation and assembly points. The
Mac app archive hash is `8cb7afa4…0669af`; Windows portable is `d516f6b1…8db76`.
Receipts are retained under Saga Online's
`docs/evidence/movement-rollout/public-downloads/` in the isolated rollout stack.

WB-003 is done. WB-010 owns the demonstrated 10 Hz network stepping, WB-017 the
waypoint budget, and WB-018 the large selection HUD. These have not been hidden
by, or claimed fixed through, the local/replay presentation change.
