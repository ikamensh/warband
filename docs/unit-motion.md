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

**View (`view.py`): distance and the model's clocks.**
- The walk frame is chosen by distance covered (`STRIDE` = 0.22 tiles per frame): feet
  stay planted, a knight steps faster than a peasant, a held unit holds its frame.
- The blow phases read off the model: `wind` while the model has the weapon drawn back
  (`Unit.windup`, see part 4), then `strike` 0.10 s, `follow` 0.16 s, `recover` 0.16 s
  after the blow, read off the cooldown. Before part 4 the wind-up was guessed as the
  last 0.2 s of the cooldown, so the first blow of a fight had none.

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
5. **Turning.** Done in the model instead (part 4): a unit pivots at its turn rate, so
   the sprite passes through the neighbouring facings on its way round.
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

Items 1 and 2 are a day; 3 and 4 are authoring, a day per race; 6–9 are polish that
can go in one unit at a time.

## 4. Turning, the wind-up and shots in the air (2026-09-16)

The rules now spend time on a blow, so the motion above has something real to show and
the balance follows from it (`rules.py` has the table; `docs/evidence/combat-timing/`
the frames this was checked on).

**Turning.** `UnitInfo.turn` is a rate in radians per second (infantry 360°/s, scouts
450°/s, knights 270°/s, catapults 150°/s). `World._turn_toward` pivots a unit toward a
point at that rate, whether it is walking a path or squaring up to a target; a blow
starts only once the unit faces its target. A footman struck from behind spends half a
second turning before it answers; a catapult wheels round in over a second.

**Wind-up.** `UnitInfo.windup` (0.25–0.35 s for soldiers, 0.8 s for a catapult) is the
time from the decision to strike to the blow landing. `Unit.windup` counts it down; the
view shows `wind` for exactly that long. The blow at the end lands if the target is still
within reach plus `WINDUP_SLACK` (half a tile) and costs the cooldown either way, so a
swing at air is a swing lost. A shooter stands through its wind-up; a melee unit with an
attack order keeps closing on its target meanwhile, or a knight after a fleeing peasant
would swing at air forever. A new order breaks a wind-up off. The period between blows is
`UnitInfo.period` = wind-up + cooldown, which is what the AI's strength maths divides by.

**Shots.** `World.projectiles` holds every arrow, axe, bolt and stone in the air
(`Projectile`: shooter, kind, start, aim, target, launch time, flight, damage). An arrow
follows its mark at `ARROW_SPEED` and strikes when it arrives; if the mark died meanwhile
it lands on nothing. A siege stone is fired at a point on the ground (`_aim_point`): the
nearest wall of a building, or a marching unit's position led by the stone's flight along
its current velocity, clamped to the engine's reach. When it comes down (`_land_stone`)
everything within `DIRECT_HIT` of the point takes the full blow and everything out to the
splash radius `SPLASH_FRACTION` of it, friend and foe alike, plus the enemy's buildings.
A crew firing on its own judgement (an automatic or attack-move target) holds fire while
its own side stands within the splash plus `FRIENDLY_MARGIN` of where the stone would
fall; a crew the player ordered fires, and the player answers for it. Catapults cannot
throw inside `min_range` (two tiles), pick their own targets beyond it, and back straight
away from a target inside it to get range. Saves carry the shots in flight.

**View.** Each shot has a sprite moved every frame, between model steps too (the view
keeps `_since_tick`), on a flat arc for arrows and a high lob for stones (`projectile_point`);
behind it a fading trail (`TRAIL` seconds long), under a stone its shadow on the ground
and, on visible ground, a ring where it will come down (the owner's colour for the
player's own stones, red for the enemy's, so a player can step out from under one). The
blow's sound and flinch come with the `hit` event, which is now raised when the shot
lands; a stone that found nothing raises `impact` for its dust and thud.
