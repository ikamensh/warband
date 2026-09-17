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
No movement implementation has changed at this checkpoint.
