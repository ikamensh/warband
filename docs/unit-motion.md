# Unit motion: why the footman shuffled and poked, and what a real swing takes

Design note for the animation of units, written when the painted sprites (see
`../sagaforge/docs/restyle.md`) made the timid motion impossible to ignore. Part one is
the diagnosis, part two what went in (commit `a7e1a38` and the sheets after it), part
three what "cinematic" would still take, in order of payoff.

## 1. Diagnosis: the painter was innocent

The image model copies the keys it is given. Every weakness below was in the rig and the
view before a single sprite was painted.

**Walk: two keys and a metronome.**
- The only difference between `walk1` and `walk2` was the legs swung ±0.11 model units
  (`_legs`), plus a 0.02 bob on one of them. Torso, arms, shield, sword and head were
  identical in both keys.
- The view toggled the two keys at a fixed 5 Hz (`int(time * 5) % 2`) whatever the
  unit's speed. A footman at 2.4 tiles/s covered 0.48 tiles per frame change, a knight
  nearly a tile: the feet slid over the ground. A unit blocked in place kept "walking".
- The camera is a steep 3/4 view (55° elevation, square tile footprints). Legs sit under
  the body, so the one thing that did move was the thing least visible. From the
  player's seat the walk was a two-frame flicker of the boots.

**Attack: one key, after the fact.**
- One `attack` key: the blade pitched from −12° to −85°. Nothing else moved: no lean, no
  twist, no lunge, the shield stayed put.
- The view showed it for the first 0.3 s of the cooldown, that is *after* the model had
  already landed the blow. There was no anticipation at all, and the pose was held rather
  than passing through. The result read as "stick up, stick down".

**Impact: a flash.** The victim got a white flash and a 6 px wobble; no displacement,
no contact effect for melee.

## 2. What went in

The classical principles that matter for 8-direction sprites at 45–95 px are
anticipation, follow-through, weight (a body that moves its mass before its limbs),
exaggeration (poses must read at sprite size, so they are pushed past realistic), and
timing (fast where force is applied, slow where it is gathered or dissipated). Each of
these now has a concrete carrier in the rig or the view.

**Rig (`textures.py`): nine frames per facing instead of four.**
- Walk cycle `walk1..walk4`: contact, passing, contact, passing. Stride ±0.19 (was 0.11),
  the trailing foot lifts 0.11 on the passing frames, the body rises 0.05 on them (bob),
  the upper body sways ±0.035 over the planted foot and twists ±10° at the shoulders,
  and the sword arm swings against the shield arm (±0.09 forward, pitch −28°/+4°). From
  the top-down camera the helmet, plume and weapon now trace visible arcs even though the
  legs are hidden.
- Blow `wind, strike, follow, recover`. Wind-up: sword raised behind the shoulder
  (pitch +55°, yawed out 15°), torso twisted −22° and leaning back 8°, weight back 0.04,
  shield forward. Strike: a 0.16-tile lunge, 14° forward lean, 12° twist, crouch −0.04,
  blade pitched −100° and driven 0.16 forward, shield tucked. Follow-through: blade
  swept across (yaw −50°, pitch −70°), torso twisted +30°. Recover: settling to guard.
- One `Pose` table (lean, twist, sway, lunge) applies to every unit's upper body about
  the hip, so archers, clerics and peasants got body motion for free; riders bob on their
  mounts instead of leaning (a leaning horse lifts its hooves), the catapult recoils
  instead of lunging. Weapon-specific tables carry the sword, the axe, the bow raise, the
  lance couch, the catapult arm.
- The stand-ins were also made honest where they misled the painter: the stone rides in
  a sling basket, the peasant holds the logs from below and cradles the sack.

**View (`view.py`): distance and the cooldown clock.**
- The walk frame is chosen by distance covered (`STRIDE` = 0.22 tiles per frame): feet
  stay planted, a knight steps faster than a peasant, a held unit holds its frame.
- The blow phases read off the model's own cooldown: `wind` during the last 0.2 s
  before the cooldown runs out (anticipation for the blow the model is about to land),
  then `strike` 0.10 s, `follow` 0.16 s, `recover` 0.16 s after it. No rules changed,
  nothing was delayed; the wind-up simply uses the timer that already existed.

**Impact (`scene.py`).** The victim flinches away from the striker (a 3 px shove when it
was standing, a 9 px wobble otherwise) and melee hits burst five sparks at the contact
point. Deaths already toppled the body and shook the camera.

Painted sheets carry all nine frames for every unit of every race (36 sheets), each
prompt naming the frames and their purpose so the model keeps the poses distinct.

## 3. What "cinematic" would still take, in order of payoff

1. **In-betweens and a smear on the strike.** Eight blow frames instead of four: two
   wind-up holds, a smear frame (the blade drawn as an arc) for the strike, two
   follow-through frames, two recover. The smear is what makes a 100 ms swing read as
   fast rather than as a jump between two poses. Cost: two more rows per sheet, the
   Codex output cap (about 1.5 MP) means splitting walk and blow onto separate sheets.
2. **Hit-stop and shake scaled to the blow.** Freeze striker and victim for 50–80 ms at
   contact (drop the sprite update, not the simulation) and shake the camera by damage;
   knights and ogres should land like they weigh something. Cheap, view-only.
3. **Signature attacks per unit type.** The footman's cut is one shape; a knight should
   lower the lance over half a second and hit at a gallop, an archer should draw, hold,
   release with a visible string, the catapult arm should snap, the frame rock and dust
   rise, the ogre should smash both-handed with a ground ripple. The pose tables already
   allow different keys per unit; this is authoring time.
4. **Secondary motion.** Plumes, cloaks, tabards and the archer's quiver lagging a frame
   behind the body sell weight more than the body itself. Cheapest route: extra keys in
   the rig with the cloth offset against the motion; the painter follows.
5. **Turning.** Facing snaps between eight directions. Interpolating the sprite facing
   over 80–120 ms through the neighbouring facings (the sheets already have them)
   removes the pop when a unit changes target.
6. **Gaits.** One walk for every speed. A run cycle (longer stride, forward lean 12°, arms
   pumping) for scouts and charging knights, and a trudge for laden peasants.
7. **Idle life.** A breathing bob and an occasional look-around every few seconds keep
   a standing army from looking like a screenshot.
8. **Death per facing.** The topple is a rotated sprite; painted fall keys (stagger, fall,
   lie) per facing would let the body land where it stood.
9. **Effects tied to the frames.** Footstep dust on contact frames, a weapon trail on the
   strike frame, a shield spark on a blocked hit. These key off frame names, which the
   view now knows.
10. **A style anchor between sheets.** Passing an approved sheet alongside a new one
    should stop the drift in horse and armour styles between units.

Items 1, 2 and 5 are a day; 3 and 4 are authoring, a day per race; 6–9 are polish that
can go in one unit at a time.
