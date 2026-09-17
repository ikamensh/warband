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

The scene records visible-unit positions immediately before each local model
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

The clear-ground trace also records an actual model-speed dip at tile centers:
the footman normally moves 0.12 tiles per tick, then only 0.04 for the remainder
of a one-tile segment. `_walk_to` snaps to the waypoint and returns, discarding
the unused part of that tick's distance. Interpolation faithfully displays that
slower interval (0.427 px/frame instead of 1.28 at 60 FPS). A constant-speed
assertion would therefore be testing a false premise about the baseline model.
WB-017 records this rules-affecting issue with its own acceptance; the current
presentation change preserves it.

## Remaining acceptance

WB-003 is not complete: inspect procedural art, diagonal motion, turns,
start/stop, crowds/obstructions and zooms; check pause, reset and presented
picking/overlays; apply the local stepping policy to replay playback; measure
the online snapshot case and retain its transport policy under WB-010. The
first-increment checks above pass; repeat relevant verification as subsequent
fixes require, then integrate the completed item into main. No motion change has
been published from this branch.
