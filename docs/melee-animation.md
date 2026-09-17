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
