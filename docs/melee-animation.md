# WB-004 — Melee animation acceptance and diagnosis

Started 2026-09-17 on `codex/wb004-melee-motion`, from main `7655d0e`.
WB-003 is published and its public Windows/Mac download checks passed.

Begin with a native capture of two human footmen fighting at gameplay scale,
with both painted and procedural art. Record pose, facing, wind-up, cooldown,
health, sprite position and actual model hit events at 60 display frames/s.
Inspect the first complete wind/strike/follow/recover cycle and its full-speed
clip before choosing a presentation change.

Acceptance:

1. A normal-zoom infantry swing visibly reads as anticipation, fast weapon
   travel/contact, follow-through and recovery. Compare the same reproducible
   scene before/after, inspecting each affected facing and both art paths.
   Begin with one weapon; expand only after that prototype has a convincing
   silhouette and timing at gameplay size.
2. Impact feedback and sound coincide with actual damaging hit events. A miss,
   cancelled wind-up or vanished target must not fake contact. Moving targets
   and crowded fights keep attacker and victim readable; no obscuring global
   shake, excessive flashes or overlapping full-screen effects.
3. Preserve authoritative combat timing, damage, reach, orders, pathfinding,
   save/replay state and the existing simulation fingerprint. Any intentional
   rules change needs separate acceptance. Presentation stays truthful while
   paused, resuming, changing target, hiding/revealing through fog, replaying and
   receiving network snapshots.
4. Full-speed native close fights and crowded battles show the improvement at
   normal/near/far zoom. Check slow/fast attacks and affected races/types before
   claiming coverage; leave explicit follow-ups for untouched categories.
5. Add behavior regressions at the scene/view seam for demonstrated timing or
   event errors, then run relevant tests, the complete game suite, input fuzz
   if scene input/rules change, the fingerprint and native visual lint. Inspect
   real frames; green logic tests alone do not prove visual quality. Record
   measured rendering cost if the chosen effects add meaningful per-frame work.

The criteria above were drafted before implementation, during WB-003
publication. WB-004 starts with the unchanged combat implementation.

Prototype constraints after the first captures:

- Start with the human footman's sword, keep the existing authoritative wind-up
  and contact times, and compare the same two-unit fight before/after.
- Recover contact displacement without letting an effect restore a stale world
  position when a victim receives a movement order during the reaction. Repeated
  hits, death/removal and pause must not leave offsets behind. Presentation
  should compose with the interpolated base position instead of fighting it.
- Evaluate a continuous body-weight shift and a brief weapon arc that corresponds
  to the actual attack phase/facing. A cosmetic trail must also be truthful on
  a missed swing; impact feedback needs a damaging hit. Reject the prototype
  if it merely adds busy particles while the swing stays unreadable.
- Do not assume hit-stop is beneficial: the current contact pose already holds
  for 0.10 s. Compare real-speed clips before adding another hold.
- Keep a clear distinction between world position, presented ground position
  and temporary body reaction. Do not add multiplayer or model changes merely
  to animate an attack whose existing clocks already align with damage.

## Initial evidence

Recorded against untouched main `2e31cda`, while its WB-003 publication ran.
No game implementation change yet. Real native 60-frame/s captures, three and
a half simulated seconds each, are in `docs/evidence/melee/before-painted-normal/`,
`before-painted-near/` and `before-procedural-near/`. Full wind/strike PNGs were
inspected. The first cycle strips use a bad vertical crop (part of the wind-up
blade is cut off); rely on the full PNGs and video. The capture script now
anchors future strips to the feet instead of the padded sprite position.

The blue footman's first strike begins at model time 0.35 s, exactly when the
red victim loses health; subsequent attacks at 1.65 and 2.95 s agree. The red
unit's counter-hits at 0.55, 1.85 and 3.15 s also agree. All four named attack
poses render. This baseline does not support an event/strike timing bug.

Initial ranked visual hypotheses: poses insufficiently distinct at gameplay
size; weapon motion hidden by shields/opponent overlap; contact feedback too
brief or not applied. Close zoom does not reveal a dramatic cut, and both art
paths inherit similar small silhouettes. Do not blame the painter without
further pose/weapon comparison.

**First demonstrated contact fault:** every captured unit has exactly one
sprite position for the entire fight, despite three damaging hits apiece and
stationary model positions. The installed Saga2D 0.3.2 `HitReaction.advance`
writes its knockback to sprite.position. `GameScene.update` advances effects,
then `MapView.sync` immediately writes the ordinary position over that change.
The intended 3-pixel shove therefore never reaches a drawn frame. Rotation
still applies; this is not proof that all hit feedback is missing.

A red-capable baseline check, run and failed:

```
uv run python docs/evidence/melee/assert_recoil.py docs/evidence/melee/before-painted-normal
AssertionError: Unit 3: 3 damaging hits, but maximum rendered recoil is 0.000px
```

A real scene/view regression should cover this observable contact behavior,
then a presentation prototype must still improve the actual swing. Fixing only
this bug is insufficient to call the whole melee-animation item done.

## First bounded increment — visible contact recoil

The real scene regression reproduced zero drawn recoil after `game.tick`, using
matched target poses with and without incoming damage. The view now owns the
short response and adds it to the current presented ground position each frame;
it never restores a captured old position. Simultaneous hits keep one bounded
response per unit. Hidden, removed, released and reset units clear that state.
F3 freezes the view clock; a separate red test caught the reaction continuing
while the simulation was paused before that fix.

Native normal-zoom capture (`docs/evidence/melee/recoil-painted-normal/`) shows
**2.986 pixels peak displacement** for both footmen, versus zero in the baseline.
The full contact frame and four-phase strip were inspected; the corrected crop
keeps the wind-up blade in frame. This restores contact response, but does not
make the current sword arc strong enough to finish WB-004.

Verification for this increment:

- 82 relevant scene/view/movement/melee tests passed in 25.89 seconds. The three
  new scene checks cover actual contact, pause, and movement during recovery;
  the lifecycle check also verifies bodies finish and are removed. Final checks
  after simplifying rotation updates pass (`recoil-*-tests.log`).
- Two 500-input fuzz journeys, seeds 83 and 84, passed (`recoil-fuzz.log`).
- Simulation fingerprint is still
  `1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`.
- Eight native layout checks (army/damaged selection, battle and forest battle
  at 1280×800 and 1200×680) report zero findings. Battle and damaged-selection
  PNGs were opened. These are layout checks, not proof of a stronger swing.

The weapon/body-motion prototype, broader native combat matrix and final full
suite remain open. No engine, authoritative rule or network contract changed.

## Human-footman sword prototype

The first weapon now loads its body back by up to three logical pixels, drives
forward by five at contact and settles through the existing recovery clock.
The offset composes with movement and recoil; it never changes the unit's
ground position, reach or orders. A short afterimage follows the authored
sword grip, pitch, torso twist and projection. It appears only after a released
swing, including a genuine miss, and fades over 0.09 seconds. Damaging hit
events still exclusively drive victim recoil, sparks and impact audio.

The first wide ribbon looked like a translucent fan in the native frame and
was rejected. The narrower version makes the cut easier to read from the side
and diagonals; a cut toward the camera remains naturally foreshortened. Normal,
near (2×) and far (0.7×) captures include four duels with both combatants,
covering all eight facings in painted and procedural art. The first near matrix
put two duels partly behind the HUD; the final capture moves those duels into
the playable area. Evidence and full-speed 60-frame/s clips are under
`docs/evidence/melee/sword-cached-*` (the earlier `sword-*-matrix` directories
retain the polygon version for comparison). Inspecting the cached version
caught clipping: rear-facing tips reach above its original 128-pixel canvas,
and one side-facing tip touched the edge. A failing image regression now checks
the whole trail has a clear margin in all eight facings. Each image uses its
projected bounds, with its ground offset preserved. The final one-second native
cycles at all three zooms are in `sword-bounded-painted` and
`sword-bounded-procedural`; they show the complete arcs again.

The new scene regression first failed because the attacker never drew back.
Six melee scene checks now cover weight without model movement, real incoming
recoil, pause, moving during recoil, cancelled wind-up and a released miss.
The latter two distinguish a swing from actual contact: cancellation leaves
no cut; a committed miss can leave a cut without moving or damaging the victim.
The same pause/cancellation assertions survive replacing drawn polygons with
an image. Those six checks plus the image-margin regression pass. The relevant
scene/view/movement suite before the margin correction passed 85 tests in
25.90 s (`sword-cached-tests.log`). The final complete suite passes **924 tests,
12 skips** in 189.84 s, with only the deliberate stale-sheet warning test
(`sword-full-tests.log`). The simulation fingerprint remains
`1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`.
Four native battle/forest-battle layout checks at 1280×800 and 1200×680 report
zero findings; the normal battle and small forest-battle PNGs were inspected
(`sword-lint.log`). No additional input fuzz is required for this art/view-only
increment; the preceding recoil/scene change already passed seeds 83 and 84.

### Rendering cost and remaining scope

A deliberately synchronized 150-footman native stress scene compared 312 warmed
frames per version, using the same world, orders, CPU budget and fixed steps.
All runs ended with 150 units and 5,260 combined hit points. This is a stress
comparison, not the standard mixed-army W10 benchmark; these are single-run
measurements, not confidence intervals.

| View | Frame p50 / p95 | Mean view sync / draw |
|---|---|---|
| Recoil baseline `90f9f3d` | 7.49 / 18.08 ms | 1.01 / 0.013 ms |
| Body plus immediate polygons | 8.27 / 24.32 ms | 1.66 / 0.433 ms |
| Body plus cached trail image | 7.72 / 20.69 ms | 1.29 / 0.126 ms |
| Cached image with complete projected bounds (final) | 7.90 / 22.40 ms | 1.29 / 0.216 ms |

The polygon version made many native draw calls during simultaneous cuts.
The final version shares eight small atlas images and issues one image drawing
per active trail. Body movement and recoil also write one composed position
per frame. This reduces the measured overhead, but does not establish zero
performance cost or a 16 ms stress-test pass. The final bounds correction was
also measured; run-to-run timing varies, and its p95 remains above the baseline.
Logs, JSON timings and native crowd frames are in
`docs/evidence/melee/sword-perf-{before,after,cached,bounded}`. The ordinary
mixed-army gate and any needed cost reduction remain part of WB-004 acceptance.

This is still the **human-footman prototype**, not completion of WB-004.
Other races' weapons, workers and mounted/heavy melee need their own treatment
and native review. Final coverage also includes fog, target changes, replay,
network snapshots and the standard mixed-army performance check. No public
engine interface, simulation rule, save schema or network contract changed.

## All four infantry weapons

Acceptance before extending the prototype:

- Human footman, orc grunt, elf sentinel and dwarf axeman all show the same
  readable load/drive/recover phases, driven by their own combat clocks.
  Preserve the accepted human treatment and every race's combat numbers.
- Trace each race's actual sword/cleaver/curved blade/axe tip through the shared
  hand-weapon rig, including that race's width and height. A generic human-sized
  arc on every figure is insufficient. Cache each race/facing image and retain
  the clear-margin regression that caught rear-facing clipping.
- Compare native baseline and candidate infantry fights. Inspect all eight
  facings in painted and procedural art at gameplay size, with near/far checks
  for overlap, clipping and a trail that obscures the body. Check cancellation,
  misses, pause, and the body following its current ground point for every race.
- Run the affected scene/view tests and simulation fingerprint; record the
  verification and limits before committing. This completes infantry coverage
  only: workers, mounted/heavy melee, the remaining scene modes and the normal
  mixed-army performance gate still belong to WB-004.

The extension follows the actual outer cleaver corner, curved blade point and
axe edge, then applies each race's width/height to the shared weapon and torso
transforms. It keeps the human prototype's timing and weight curve. The
per-race/facing images use the same bounded cache and one drawing per active
cut; no additional primitive loop runs during combat.

Baseline native normal-zoom matrices for orcs, elves and dwarves are recorded
in `docs/evidence/melee/{orc,elf,dwarf}-before`. The body-weight regression
failed for all three races while passing for humans (`infantry-red.log`).
The extended checks pass for every race: **28 tests** cover visible damage,
weight without model movement, cancelled wind-up, released miss, pause,
moving during recoil and unclipped images in all eight directions.
The wider scene/view/movement/race/combat-timing set passes **135 tests** in
30.21 s (`infantry-relevant-tests.log`). An independent asset comparison also
confirms all eight human trail images match `63b01fc` pixel for pixel. The
simulation fingerprint remains unchanged (`infantry-fingerprint.log`), and
four native battle/forest-battle layout checks report no findings
(`infantry-lint.log`).

Candidate native cycles are in
`docs/evidence/melee/infantry-{painted,procedural}-{orc,elf,dwarf}`, each with
normal, 2× and 0.7× frames, a 60-frame/s clip and model/sprite trace. Normal-zoom
phase matrices and the near/far contact comparisons were opened and inspected
for all three races, including the counterattacker's four opposite facings.
The taller orc arcs and shorter dwarf cuts retain their complete tips. Side
and diagonal cuts read most clearly; toward-camera cuts are foreshortened,
with body weight and victim recoil carrying the contact.

Infantry presentation coverage is verified. Workers, mounted/heavy melee and
the remaining whole-item gates are still open; this does not mark WB-004 done.

## Workers in combat

Acceptance before implementation:

- First capture empty-handed, gold-carrying and lumber-carrying workers in a
  real fight. Source inspection shows cargo sprites omit the axe; verify the
  visible failure before deciding how to show the combat tool.
- Workers of every race must show anticipation, an axe cut and recovery at
  gameplay size, using the existing worker grip/swing and combat clocks. Keep
  harvesting/chopping, repair and ordinary cargo travel unchanged.
- If the combat pose puts cargo away to show the tool, retain the exact payload
  and show the cargo again on leaving combat. Verify a real command sequence,
  including successful delivery afterward; drawing a weapon must not discard
  resources or change recorded orders.
- Check all eight facings in both art paths, plus near/far contact frames and
  cargo transitions. Extend the scene regressions for pause, cancellation,
  missed swings and movement as appropriate. Keep the simulation fingerprint,
  run affected checks, and inspect native frames before recording acceptance.

The three human baseline captures (`docs/evidence/melee/worker-before-{none,gold,lumber}`)
confirm the fault: empty-handed workers swing an axe, but laden workers attack
with their sack or logs still in both hands and no tool. The worker rigs already
contain an axe and four combat poses; choosing those existing images fixes the
missing tool without repainting art. During `attack` the view selects the
unladen image. The model's cargo stays intact, and leaving combat immediately
restores the carried-load image.

Workers now use the same continuous body-weight curve as infantry, driven by
their shorter existing wind-up. Their cached ribbon follows the actual worker
axe's upper cutting edge, grip and wind/strike pitches, then the common torso
pose, race dimensions and camera projection. Harvest/chop and repair states do
not enter this combat path. The shared trail renderer still draws one image
per active cut; worker/facing/race images extend the bounded cache to 64 shapes.

The real harvesting regression failed for all eight race/resource combinations
before the fix (`worker-cargo-red.log`). It now harvests gold or lumber, carries
it to a fight, draws the axe, lands a hit, stops with the load visible, and
delivers exactly that load to the town hall. Separate red runs demonstrated the
missing worker weight shift and released-miss trail (`worker-weight-red.log`,
`worker-trail-red.log`). The melee suite now covers both workers and infantry
of all four races: **64 checks**, including cargo, all eight trail bounds,
damage/recoil, weight without model movement, pause, cancellation, misses and
movement during recoil. The affected scene/view/worker/movement/race/timing set
passes **194 tests** in 33.42 s (`worker-relevant-tests.log`).

Native candidate cycles are in
`docs/evidence/melee/workers-{painted,procedural}-{human,orc,elf,dwarf}`.
Each includes normal, 2× and 0.7× captures, a 60-frame/s clip and a trace.
Human/orc fixtures carry gold; elf/dwarf fixtures carry lumber. The eight
normal-zoom phase matrices and all near/far contact comparisons were opened
and inspected. Both sides explicitly receive attack orders because workers
do not automatically counterattack; this exercises all eight facings. The
last phase stops both fighters and shows their cargo again. Across all 24
captures the traces confirm the unchanged ten-resource payload, unladen
weapon poses during wind-up and restored cargo images after stopping.
The shorter worker arc stays intact at every facing; side/diagonal contact
reads most strongly, while forward/back cuts retain the existing perspective.

The simulation fingerprint remains `1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`
(`worker-fingerprint.log`). Native battle/forest-battle layout checks at
1280×800 and 1200×680 report zero findings (`worker-lint.log`); the large battle
and small forest frames were opened. Worker combat is verified. Mounted/heavy
weapons and the remaining whole-item scene, performance and release gates
are still open; WB-004 remains in progress.

## Mounted and heavy melee

Acceptance before implementation:

- Capture the current scout spear, knight lance, dwarf rider's hammer and orc
  ogre's club in real native fights. Distinguish their authored weapon motion
  and silhouettes before choosing a weight shift or trail. Start with a scout
  prototype; a mounted spear must not inherit the worker axe's rig or torso
  bend. The ogre is a ground-based body despite sharing the knight role.
- Show a readable preparation, release/contact and recovery through each
  role's existing combat clocks. Preserve model positions, reach, damage,
  attack periods and movement. Keep the accepted infantry and worker results.
- Project any weapon afterimage from that weapon's actual grip, moving edge
  and body pose, including race dimensions. Avoid large opaque fans covering
  the rider or opponent. Cache bounded images; retain whole-arc margins in
  every facing. If the existing poses prove inadequate, change both art paths
  deliberately instead of improving only the procedural rig.
- Verify pause, cancellation, released misses and moving victims through the
  real scene for the added roles. Inspect normal/near/far native fights in all
  eight facings for all four races, including slower heavy attacks and faster
  scouts. Run the affected tests, fingerprint and native layout checks.
- This covers melee unit presentation only. Final fog/target/replay/network
  checks, ordinary mixed-army performance, full-suite and release verification
  remain necessary before WB-004 can be marked done.

### Scout prototype

Native baselines are recorded in
`docs/evidence/melee/mounted-before-{human-scout,human-knight,orc-knight,dwarf-knight}`.
The scout lowers its spear through contact, but the rider and mount show little
preparatory weight. The load/drive regression fails for scouts of all four
races (`scout-weight-red.log`); the released-miss check also confirms that no
spear afterimage is drawn (`scout-trail-red.log`).

The prototype adds the existing weight curve to the scout's own combat clocks.
The spear's grip, point and pitch are shared with its mesh. Its trail uses the
mounted bob and forward lunge, without the infantry torso twist or lean. A
one-off comparison against `7a7779d` verifies that every scout mesh face,
colour and vertex is unchanged for all four races and every animation frame
(`scout-mesh-comparison.log`, maximum coordinate difference **0.0**).
No new sprite poses or combat rules are introduced. The role/race/facing cache
now holds at most 96 ribbons, still drawn as one image per active weapon.

The extended melee suite passes **92 tests** in 9.40 s (`scout-tests.log`),
covering infantry, workers and scouts of every race. The wider scene/view/
worker/movement/race/timing checks pass **222 tests** in 35.63 s
(`scout-relevant-tests.log`). The simulation fingerprint is unchanged
(`scout-fingerprint.log`). Four native battle/forest-battle layout checks report
zero findings (`scout-lint.log`); the small battle and large forest frames were
opened.

Native cycles in `docs/evidence/melee/scouts-{painted,procedural}-{human,orc,elf,dwarf}`
cover all eight facings at normal, 2× and 0.7× zoom. All normal phase matrices
and near/far contact comparisons were opened and inspected. The human trace
before the first incoming hit measures **−2.875 px load-back / +5.0 px drive**,
versus **0 / 0 px** in the baseline, with one unchanged authoritative position
in each capture. The higher spear arcs retain their margins and do not cover
the mount with an opaque fan. As with infantry, cuts toward the camera are
foreshortened.

Review also found thin horizontal lines above painted wolf riders. They are
present in the existing `orc.scout.png`, which this change does not modify.
That separate art/extraction defect is recorded as **WB-019**, including a
future visual-lint regression; the current layout checks do not detect it.
Scout combat presentation is verified. Knights, the ogre and the remaining
whole-item gates are still open; WB-004 remains in progress.

### Heavy weapons: prerequisite art correction

The native heavy baselines and a direct look at `dwarf.knight.png` confirm
that the painted bear rider carries a lance, while its procedural rig has a
hammer. The asset recipe in `tools/restyle.py` incorrectly asks for a lance;
the rig, combat Foley and race/audio documentation agree on a blunt hammer.
A trail based on the hammer would visibly disagree with the painted weapon.

Acceptance before correcting the recipe or installed art:

- Make the bear-rider subject, weapon inventory and pose instructions agree
  on one short-handled war hammer. Keep its existing bronze armour, blue team
  cloth, armoured bear, camera, facing order, frame order and ground anchors.
- Preserve all nine animation frames in every facing, including the original
  distinction between wind-up, contact, follow-through and recovery. The
  hammer follows the existing procedural grip and pitch; do not alter combat
  timing or damage to fit new artwork.
- Keep the current asset until a candidate has passed cell extraction and
  geometric checks and has been inspected beside the procedural reference.
  Check all 72 cells for the intended weapon, one rider and one bear, correct
  facing, clear borders and team recolouring. Reject misplaced or duplicated
  figures, lost poses and new guide-line fragments.
- Inspect native gameplay at normal/near/far zoom with the corrected art and
  the eventual hammer trail. Verify the unchanged simulation fingerprint,
  affected scene/art tests and native visual lint before accepting the change.

### Heavy-unit implementation and art provenance

The load/drive regression failed for all four knight races: each body's
horizontal displacement stayed exactly zero before the opponent's counter-hit.
Heavy bodies now load back by up to 4 logical pixels and drive forward by 6,
using their existing longer wind-up and cooldown. Lance, hammer and club trails
use the actual weapon grip, edge, pitch and authored body bob. Hammer/club
edges are slightly wider to remain visible when foreshortened. These are
presentation changes; all 36 procedural knight meshes compare exactly equal
to `fead4b7`, including face colours and vertex coordinates.

The bear-rider recipe now requests one hammer and its matching pose. A second
prompt bug appended the worker's axe description to every non-worker; that
suffix is now limited to workers. The installed bear-rider PNG was edited with
the built-in image-generation tool, using the old painted sheet for identity
and the procedural sheet for the hammer's position and animation. The original
generated RGBA sheet, exact prompt, references and extraction report are in
`docs/evidence/melee/bear-hammer-art/`. The output's transparent background was
composited over the pipeline's chroma key, then passed through the existing
`sagaforge.restyle.cut` registration and extraction. No weapon pixels were
hand-painted or changed by a script.

All 72 cells passed extraction: global scale 1.00763 and shift
(-0.879, -1.538) pixels, with zero flagged cells. The existing sheet metadata,
frame order and anchors are unchanged. All cells and red-team combat frames
were inspected; they retain one dwarf, one bear, one hammer (occluded where
appropriate), the shield, blue/red cloth and separate movement/combat poses.
Native captures in `heavy-{painted,procedural}-{race}` cover every facing at
1.0, 2.0 and 0.7 zoom. All eight normal matrices and the near/far contact
comparisons were opened. The corrected hammer and compact trails keep the
combat silhouettes readable.

The native human-knight trace shows -3.846 pixels of anticipation and +6.0
pixels of drive before an incoming hit, compared with 0/0 in the baseline;
the model retains exactly one ground position. All 120 melee regressions pass,
including all knight races, and the broader scene/view/combat/art selection
passes **215 tests** in 26.06 s (one deliberate stale-sheet warning).
`heavy-tests.log` and `heavy-fingerprint.log` record the results; the simulation
fingerprint remains `1baac5542386b900d86ff2485ab4982db19d1faf2030870bcebdf12aefe5eccb`.
Every corrected art cell passes empty/clipping/chroma/recolour checks and the
runtime centroid-drift threshold (`bear-hammer-art/runtime-lint.log`). Four
native battle/forest layouts report zero findings (`heavy-layout.log`); the
small battle and large forest images were opened. This completes the heavy
weapon milestone; final fog/target/replay/network, ordinary mixed-army
performance, full-suite and publication gates remain open for WB-004.

## Final scene and release gates

Before accepting the complete item:

- Change target during wind-up and remove a target before release: the old
  target must receive neither damage nor a hit reaction from a cancelled blow.
- Hide a reacting enemy through fog, reveal it and reload a world: invisible
  bodies/trails and stale contact offsets must not survive those transitions.
- Replay an actual recorded fight through `ReplayScene`, including pause and
  changed playback speed; preserve the final simulation digest and visible
  contact. Receive actual authority snapshots through the multiplayer scene:
  hits produce recoil once, repeated event history must not restart it, and
  rejected/unreceived orders cannot create a predicted impact.
- Run the ordinary 150-unit mixed-army benchmark on the native backend with
  the existing W10 p95 <16 ms gate. Measure without a profiler and record the
  source, resolution and pacing. Investigate a miss before accepting a release.
- Run the full suite and unchanged fingerprint, inspect crowded native combat,
  then publish through the established main-push pipeline and verify the
  resulting downloadable builds/catalog before marking WB-004 done.
