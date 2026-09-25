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
   pumping) for charging knights, and a trudge for laden peasants.
7. **Idle life.** A breathing bob and an occasional look-around every few seconds keep
   a standing army from looking like a screenshot.
8. **Death per facing.** The fall is still the one sprite turned about its feet, but since
   WB-005 it has weight: a lurch with the blow, a topple that gathers pace, a landing that
   bounces and raises dust, always away from the killer; mounts fold into a low heap and
   siege engines break where they stand (`effects.UnitDeath`, `tools/verify_deaths.py`).
   Painted fall keys (stagger, fall, lie) per facing would let the body change shape as it
   goes down.
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

**Turning.** `UnitInfo.turn` is a rate in radians per second (infantry 360°/s,
knights 270°/s, catapults 150°/s). `World._turn_toward` pivots a unit toward a
point at that rate, whether it is walking a path or squaring up to a target; a blow
starts only once the unit faces its target. A footman struck from behind spends half a
second turning before it answers; a catapult wheels round in over a second.

**Wind-up.** `UnitInfo.windup` (0.25–0.35 s for soldiers, 0.8 s for a catapult) is the
time from the decision to strike to the blow landing. `Unit.windup` counts it down; the
view shows `wind` for exactly that long. The blow at the end lands if the target is still
within reach plus `WINDUP_SLACK` (half a tile) and costs the cooldown either way, so a
swing at air is a swing lost. A shooter stands through its wind-up; a melee unit with an
attack order keeps closing on its target meanwhile, or a knight after a fleeing peasant
would swing at air forever. A new order breaks a wind-up off, and so do Stop and the fall of
the target it was drawn back at: a blow is never kept for the next foe, which is faced and
drawn back at afresh. The period between blows is
`UnitInfo.period` = wind-up + cooldown, which is what the AI's strength maths divides by.

**Shots.** `World.projectiles` holds every arrow, axe, bolt and stone in the air
(`Projectile`: shooter, kind, start, aim, target, launch time, flight, damage). An arrow
follows its mark at `ARROW_SPEED` and strikes when it arrives; if the mark died meanwhile
it lands on nothing. A siege stone is fired at a point on the ground (`_aim_point`): the
nearest wall of a building, or a marching unit's position led by the stone's flight along
its current velocity, clamped to the engine's reach. When it comes down (`_land_stone`)
everything within `DIRECT_HIT` of the point takes the full blow and everything out to the
splash radius `SPLASH_FRACTION` of it, friend and foe alike, plus the enemy's buildings.
A crew firing on its own judgement (an automatic or attack-move target) weighs the trade
before it lets a stone go (`_aim_trade`): the enemies under the landing point score
`SIEGE_WORTH` each (archers 2, clerics and catapults 3, anyone else 1, in full within
`DIRECT_HIT` and at `SPLASH_FRACTION` out to the splash) against `FRIENDLY_WORTH` — two — for
each of our own under it (`_friendly_cost`), and the crew throws the point that comes out
furthest ahead, or holds when none does. A friend counts where it comes nearest: where it
stands, where its velocity carries it before the stone lands, where the move it is under
orders to make carries it, or at arm's length of the enemy it is walking up to fight (a
soldier after an archer that steps back between its shots) — and `FRIENDLY_MARGIN` further
out than the splash on top, because all of that is a guess. A crew the player ordered fires:
it prefers a point clear of our own side and takes the target's own ground when there is
none, and the player answers for the splash. Catapults cannot throw inside `min_range` (two
tiles). A crew picks *what* to throw at by the same trade (`_siege_choice`, WB-052): every
visible enemy within its reach plus `SIEGE_STEP` tiles, a walk to reach it counting against
it; buildings only when no unit can be struck. It may drop the stone a tile beyond a unit,
where the splash still catches it: a soldier locked with the crew's own line is struck that
way, and a crew whose target is in reach but has no stone worth throwing rolls closer until
one comes down ahead, stopping two splashes outside its minimum range. It looks again every
quarter second while its target has no stone worth throwing or stands inside the minimum
range, and backs straight away from one inside it when there is nothing else. A crew on Hold
chooses the same way among what it can throw at from where it stands, nothing inside its
minimum range, and looks again as often. Before WB-052 a crew locked on the soldier in front
of its own line and threw one stone in a whole clash; until the trade replaced a flat veto it
threw one every thirty-one seconds against a reload of under four, which is
[the balance note](balance.md). Saves carry the shots in flight.

**View.** Each shot has a sprite moved every frame, between model steps too (the view
keeps `_since_tick`), on a flat arc for arrows and a high lob for stones (`projectile_point`);
behind it a fading trail (`TRAIL` seconds long), under a stone its shadow on the ground
and, on visible ground, a ring where it will come down (the owner's colour for the
player's own stones, red for the enemy's, so a player can step out from under one). The
blow's sound and flinch come with the `hit` event, which is now raised when the shot
lands; a stone that found nothing raises `impact` for its dust and thud.

The model's `kind` says only how a shot behaves: an `arrow` follows its mark, a `stone`
comes down on the ground. What it looks and sounds like is its striker's, chosen on the
client from `Projectile.source_type` (`view.SHOT_LOOKS`, as `sound.impact_sound` picks the
Foley), so a new look is never a rules change. A healer's weak blow (WB-051) is an `arrow`
in the model and a mote of light on the map: it is first seen `STAFF_REACH` before the
healer, where the staff is held, flies straight with a short warm tail, goes out in a
`Flare` with a few sparks on whatever it strikes, body or wall, and draws no blood. It is
heard as `mote_<material>`, the one impact family synthesised (`sound.mote`, the glass of
the heal falling instead of rising) rather than cut from Foley pieces.

## 5. Standing at ease (2026-09-16)

A group sent somewhere used to arrive as one stack, every unit touching its neighbours
(a body apart, `UnitInfo.radius` each), and stand like that until the next order: sixteen
footmen were one overlapping mass of blue. Real troops loosen up when nothing is happening.
Two things now happen in the model, both only for units *at ease*: neither fighting (an
`Attack`, `Heal` or `Hold` order, a wind-up, or the `attack` state), nor working (a peasant
harvesting, delivering, building or repairing). Everything else — standing, or walking a
`Move`, `AttackMove` or `Patrol` — counts.

**Elbow room (`_separate`).** Besides pushing overlapping bodies apart, the crowd step gives
a unit at ease a soft push away from any neighbour closer than touching plus `SPACING`
(0.2 tiles), at `SPACING_WEIGHT` of the missing clearance per step, so it is gentler than the
overlap push and a marching column loosens rather than scatters. The push moves the unit
that wants room, never the one it is making room for: a peasant idling against a footman
hitting a wall steps back, the footman keeps its reach. Fights, mining queues and building
sites are untouched; `unit_at`, weapon reach and the melee positioning all measure from the
same body, `UnitInfo.radius`.

**Stepping away (`_ease`, `_elbow_room`).** A standing unit with a neighbour's centre closer
than its own two bodies and `EASE_SPACE` (0.3 tiles) is crowded, so a catapult asks for the
room a catapult takes. Every `EASE_EVERY` ticks it rolls `EASE_CHANCE`
(about once every two seconds) and, when the roll comes up, picks a spot `EASE_STEP` give or
take `EASE_STEP_VARIANCE` away from the weighted middle of its close neighbours, veered by
up to `EASE_JITTER` either side so the crowd does not explode radially. The spot must be on
open ground on a clear line, and must offer `EASE_GAIN` more room than where the unit
stands, so nobody steps into somebody else and a unit boxed in on all sides waits for the
outside to loosen first. The step is a real short walk through `_steer`: the unit turns,
takes a stride or two (the view's distance-driven walk cycle plays), and stops. It is not an
order: the unit stays idle to the AI, to Tab and `.` and to the player; the target of the
step is `Unit.ease`, cleared by any order and carried in saves. Held units never step (Hold
is handled before idling), and an enemy in sight still takes precedence every fifth tick.

The rolls come from `World.rng`, so lockstep play and replays stay bit-exact; the recorded
`tools/sim_fingerprint.txt` moved with this change. Sixteen footmen sent fifteen tiles now
finish the order in 17 s where the tight crowd took 19 (the looser arrival lets more of
them stop inside `SETTLE_WITHIN`), and stand with their nearest neighbours 0.9–1.0 tiles
apart in a blob of radius 2.9 tiles instead of 1.8. `tests/warband/test_spacing.py` holds
the four properties above; the frames this was judged on are under
`docs/evidence/spacing/`. This is the cheap half of part 3's item 7, idle life; the
breathing bob and look-around are still open.

## 6. The marching line (WB-050, 2026-09-19)

A move or attack-move that sends two or more formation units (every race's footman but
the orc grunt) further than `FORMATION_MARCH` (4 tiles) gives each a slot: a line across
the march, `FORMATION_SPACING` apart and `FORMATION_WIDTH` (8) a row, the foremost in
front and each keeping its side (`World._line_slots`; the order's `offset` from the shared
target, so the group's pace still holds). A slot in the trees or across the water is
dropped, and that unit goes to the target itself. On the way (`World._march`) each heads
for its place as the line stands `FORMATION_LOOKAHEAD` (3 tiles) ahead of the line's
middle, walking straight at it while the way is clear, so the line re-forms as soon as it
is past what split it; otherwise, and at the end, it follows a path to its final slot
(a path to a moving place would be planned anew every step and zigzags in the woods).
A unit more than `FORMATION_SLACK` ahead of its row's laggard walks at `FORMATION_HOLD`;
rows dress on themselves, because the front row slowing for the back is what blocks the
back. A formation unit wears `FORMATION_ARMOR` more for a comrade at each side
(`World.flanks`). Found on the way: a waypoint within `ARRIVE` of a unit counted as reached
and snapped the unit onto it, so every unit slower than 2.4 tiles/s was sped up at each
waypoint; now only the end of a walk does.

## 7. A body per unit type (2026-09-20)

Every unit used to fill the same 0.35 tiles, so a catapult and a peasant were the same
thing to the crowd, to a stone's splash and to a click, and the drawn figures stood
inside each other. `UnitInfo.radius` is now a body per unit type.

**How the numbers were measured.** The shipped art is the painted sheet under
`warband/assets/restyled/`, one cell per facing and frame, anchored at the figure's feet
(`restyle.Sheet.origin`, `scale`; `TILE` is 32 logical pixels to the tile). For the
`stand` frame of all eight facings of all four races, the silhouette (alpha ≥ 64) is read
as a column histogram, and the body is the half-span holding the **central 90 % of the
opaque pixels** — the figure's mass, not the lance or the raised axe one thin column of it
holds out. Averaged over facings and races:

| unit | drawn body | widest point | radius | share of the body |
|------|-----------:|-------------:|-------:|------------------:|
| peasant  | 0.419 | 0.95 | 0.36 | 0.86 |
| cleric   | 0.431 | 0.85 | 0.38 | 0.88 |
| footman  | 0.488 | 1.01 | 0.42 | 0.86 |
| archer   | 0.492 | 0.94 | 0.42 | 0.85 |
| knight   | 0.652 | 1.20 | 0.56 | 0.86 |
| catapult | 0.733 | 1.14 | 0.62 | 0.85 |

The chosen radius is a flat ~0.86 of the drawn body: close to the figure, a little less,
so bodies nearly touch rather than interpenetrate. The races are drawn at noticeably
different sizes (an orc footman's body measures 0.62, an elf's 0.36), but one role is one
body: a per-race radius would be a race balance change, and the rulebook reads better with
seven numbers than twenty-eight.  The flying machine's 0.45 is no body on the ground: it is what
a click on the machine drawn in the air picks, and the room flyers keep from each other.

**What the body is.** The radius is what the crowd keeps clear (`World._separate`), what a
reach is measured to (`World._gap` is edge to edge, so `MELEE` and a weapon's `range` are
gaps between bodies and a bigger body reaches further in centre distance), what a stone's
splash measures from (`_land_stone`), and the ring the player sees and clicks
(`view.MapView`). It is **not** terrain clearance: a walker is a point against the blocked
grid, so a catapult 1.24 tiles wide still goes through a one-tile gate, and the bodies of
the units at a tree or a wall overlap the tiles they are working.

A search that must not miss a unit whose *body* reaches into it pads its bucket scan with
`rules.MAX_UNIT_RADIUS`, the largest body there is, and then tests the exact distance
against that neighbour's own radius. There is no one-size `UNIT_RADIUS` any more: every
place that used it was one of these two things.

The gatherers are untouched by all of it: twelve peasants on a mine and a wood, over three
minutes and five seeds, bring in 11,400 gold and 5,000 lumber where they brought 11,500 and
4,800. The crowd step costs more, because a peasant now has to look two bucket cells out
rather than one to find the catapult that might be leaning on it: 600 steps of a
160-unit march take 1.61 s against 1.37 s from source, and nine whole arena matches run at
0.073 ms a step compiled against 0.058. Frames are unmoved -- `tools/perf.py` gives p95
31.9 ms against 32.1 on the same loaded machine.

**What it cost the catapult** (measured with `tools/battle_bench.py`, 60 fights a pairing,
half from each side, against the same tool run from `main` at f5ec5b1). Mirror armies are
unmoved: footman, archer and knight compositions win the same half of their fights and the
winner keeps within a few points of what it kept. Two catapults are not:

| pairing | main | with bodies |
|---|---|---|
| `footman:7,catapult:2` vs `footman:10` | 90.0 % won, 4 draws | 26.7 % won, 21 draws |
| `footman:4,catapult:4` vs `archer:11` | 98.3 % won | 98.3 % won |
| `footman:7` vs `footman:10` (no engines) | 0.0 % won | 0.0 % won |

So the melee arithmetic is unchanged and shelling a standing line is unchanged; what fell
away is the catapult *behind its own line*. Two things move it, one a little and one a lot:

* a stone catches a unit whose *body* is inside the splash, so the caught disc grows with
  the body — +9 % of area for a footman, +17 % for the full-damage disc — but at rest the
  bodies stand `2r + SPACING` apart instead of 0.90 tiles, which is 25 % less dense. Net,
  about a sixth fewer units under a stone, and the measured damage per stone bears it out
  (41 against 47);
* and the crew holds fire far more often, because `_clear_of_friends` (now `_friendly_cost`,
  part 4) measures to a
  friend's body too. This is the big one, and `FRIENDLY_MARGIN` is its dial. Over twelve
  seeds of a seven-footmen-and-two-catapults clash:

  | margin | stones thrown | damage on the enemy | damage on our own | our units left |
  |-------:|--------------:|--------------------:|------------------:|---------------:|
  | 0.30 | 6.8 | 371 | 1.8 | 4.6 |
  | 0.40 | 7.1 | 327 | 0.0 | 3.0 |
  | 0.45 | 7.2 | 308 | 0.0 | 1.1 |
  | 0.50 | 5.1 | 209 | 0.0 | 0.2 |

  The margin cannot simply go back down: at 0.3 the new bodies put stones on our own
  footmen in five of the twelve clash seeds of `test_siege_judgement` (the shipped
  0.35-tile bodies did it in two — the test's first six seeds were lucky) and 0.4 in one,
  so 0.45 is the least that is clean on all twelve.

Rebalancing the catapult was deliberately not done here: its cost and damage were left as
they were, and the numbers above were the starting point. What was done with them, the same
day, is [the balance note](balance.md): the crew's veto became a trade, which is where nearly
all of the 90.0 % had gone, and the catapult was then priced for the player who aims it,
whose stones were never subject to the veto in the first place.

## 8. As near as the crowd allows (2026-09-21)

A walk ends where the unit reaches its point, and a point holds one body. Order twenty soldiers
to a muster and nineteen of them cannot stand on it, so nineteen keep an order they can never
finish — which is a soldier standing in the crowd for the rest of the match, taking no further
part in it. Both brains carried a patch for that: `release_arrived` let go of any Move whose
target was within `ARRIVED_WITHIN` (1.5 tiles) by re-ordering the unit to where it already stood.
`ProBrain._send_to_muster` then sent a soldier after its post again beyond `MUSTERED` (1.0). A
soldier the crowd held **between** those two numbers was cancelled and re-ordered twice a second:
it walked two ticks towards its post, was released, drifted eight ticks back on the crowd's push,
and was sent again, for as long as the match lasted. `tools/fuzz.py --games 8 --monkey 0 --seed 85`
caught it on seed 92 — footman 164 of player 3, a tile and a bit from a muster post a knight was
standing on, in the same place twenty seconds later. Left alone it would have walked in and
arrived in 1.6 s; it was the two rules fighting, not the crowd, that pinned it.

Both sides now ask the world the one question, `World.stands_at(unit, point)`: **is the unit at
that point, or as near it as the crowd standing in the way allows?** It walks the line from the
unit to the point in steps no wider than the unit's own body, and asks of each step whether a
body is standing on it. The unit is there when every step of the way in is held by somebody who
is not going anywhere. That is how a pile twenty deep is answered as readily as a single knight
on the spot — the old test, a fixed `SETTLE_WITHIN` beyond the unit's own body, only ever
described the innermost ring, and it takes two bodies to make the gap, not one.

Two things deliberately do not answer it:

* **ground the map blocks.** That is the planner's business, and it walks the unit round. Counting
  a wall as "the way is full" made a queue at a one-tile gate give up at the back of itself
  (`test_twice_the_crowd_through_the_same_gate_still_clears`).
* **a unit walking an order of its own.** It will move on, so waiting behind it is not arriving.
  The settling cascades from the front instead: whoever arrives first stops, and becomes the wall
  the one behind it settles against.

`World._follow` ends a settling walk on this answer once the progress watchdog says the unit is
going nowhere (`STUCK_AFTER`), so a fresh order still walks the whole way; `_send_to_muster` asks
it before ordering another walk, and `_march` asks it before taking the marching line's shortcut. `release_arrived`, `ARRIVED_WITHIN` and `MUSTERED` are gone: a
soldier is never sent where the simulation would stop it at once, which no pair of numbers either
side of a walk can promise. It is also the human player's army that is fixed — `release_arrived`
only ever ran for a brain.

Measured: nine whole arena matches run at 0.058 ms a step against 0.057 before, and the staged
150-unit battle of `tools/step_bench.py` at a mean 0.38 ms a step against 0.37, so the walk costs
nothing measurable — `stands_at` is asked about 200 times in a whole match. What moves is the
matches themselves: they run about 7 % longer in simulated time, and 48 ladder matches of
`hard` against `pro` went 75.0 % to `pro` where they went 68.8 %, all 48 decided where one was
not. `tools/sim_fingerprint.txt` and `tools/sim_bench.txt` moved with the rules change.

**The shortcut that marched a unit back out of its slot.** The first landing of this went in and came
straight back out: CI was red on Linux, where the gate queue of `tests/warband/test_stuck_units.py`
wedged a footman for the last three minutes of the run. The scenario is bit-identical on macOS with and
without the change, so the divergence was the Linux runtime's own rounding taking that crowd of
sixty-six somewhere this Mac never goes — which is what the note at the top of this file about glibc
rounding sines differently in the last bit looks like from the other end. A Linux container reproduced
it in eight seconds and the trace was unambiguous.

It was not the crowd at all. A unit in a marching line heads for the place `FORMATION_LOOKAHEAD` ahead
of the line's middle, and once it has walked in to its slot at the end of the march that place is
*behind* it: the shortcut cleared its plan (`_steer` drops `path`, `path_goal` and `exact`) and walked
it a tile and a half back out, the next step planned the way in again, and it stepped between the two
with a period of 1.3 seconds. Its stragglers were still queueing at the wall, so the line's middle never
caught up and the shortcut never switched off. Worse, each turn reset the progress watchdog, so
`u.progress` sat at 0.00 for ever and the settling walk could never end: the footman finished at rest
*exactly on its slot*, in the move state, holding an order it had already completed.

`_along_its_route` (part of WB-050's own fix, b68271eb) is meant to refuse a shortcut that undoes the
route the unit is walking, but it answers "nothing to undo" for a unit with no path — which is precisely
the unit that has just arrived. So `_march` now asks `stands_at` first: **a unit already standing at its
slot never takes the shortcut**, because there is nothing left to march to. It costs nothing measurable
(the staged 150-unit battle runs a shade faster with it, on fewer wasted replans).
`tests/warband/test_off_course.py` holds the step-out itself, staged from that run's own five marchers,
their offsets and the wall that holds them back; the twenty-second wedge stays the gate queue's job.

## 9. A hard core, and a crowd no slower than its members (2026-09-24)

Bodies were soft all the way in. `_separate` pushes overlapping units apart at a share of the overlap per
step, capped at `MAX_PUSH`, so anything walking into a crowd simply walked into it: twelve knights through
a gate stood with their centres a tenth of a body apart, and a mixed column down a one-tile corridor a
fiftieth. From above that is the heap of shields and helmets a player sees at a choke.

**The core.** Every step a unit walks (`_follow`, `_steer`) and every shove it is given (`_shove`) now goes
through `World._keep_clear`, one unit at a time: no centre comes nearer another's than `CORE` (0.7,
`behavior.toml`) of their two radii. A step that would cut into a core stops at its edge and keeps its
sideways part, so the unit slides round the body in its way; a pair that is already inside (a pile spawned
on one spot, a unit set down while it was off the map) may only draw apart. Beyond the core the body stays
soft, and the crowd step still spaces units out to their full radius over a few ticks. 0.7 is as big as the
core can be while the two biggest bodies still pass each other: two catapults head-on in a one-tile
corridor need their centres 0.87 tiles apart across it, and a walker's centre can use the whole tile.
Where a slide lands exactly on another core's edge, rounding must not read it as a hair inside on the next
look (`CORE_TOLERANCE`): that once froze an archer in front of a gate with nobody in it.

**Efficiency.** `tests/warband/test_crowd_flow.py` draws scenarios from a seed: a gate or corridor of one
to three tiles, one to eight deep, or none at all; three to twelve units of one kind or a mix; move or
attack-move; sometimes friends idling in the gate. Each is played as a group and once per member alone.
The group must finish no later than its members would one after another (the sum of the solo times), and
no later than the slowest member alone plus twice the time the group takes to file past a point, bodies
touching. The core is watched every step. On `main` as it was, 59 of 60 draws broke the core, 7 left units
stranded and most missed the second bound. The faults behind that, each with a case of its own:

1. **Soft bodies** (above).
2. **A vortex round a shared waypoint.** Sixteen knights on one path: four of them circled the first tile
   centre for good, each heading at the middle the others held and sidestepping round them. `_follow` now
   passes a waypoint whose successor is a step away in a clear line, judged by the same tile rule as the
   off-course check (a diagonal past a blocked corner is not a step), or the next plan undoes the skip and
   the unit alternates between the two.
3. **Arriving through the rock.** `stands_at` looked along the straight line to the spot, so a unit held
   back by the pile past a gate counted as arrived on the near side of the wall. Across blocked ground the
   way in is now the unit's route, ending where the route ends when the spot is out of reach (a base walled
   in by its own buildings, a target across the map).
4. **A row dressing in a corridor.** A marcher ahead of its row walked at `FORMATION_HOLD` until the row
   caught up; down a corridor the row can never form, so the front held the whole file at 60 %: 45 s where
   peasants took 16. The hold now applies only on the line's straight walk to its place (`dressing`).
5. **Giving up at a crowd.** A stalled unit plans again around units standing about; when they fill a gate
   there is no such way, the search returned the nearest tile it reached, and walking that out ended the
   order there. An around-units plan that falls short of the goal now presses on through them.
6. **A shortcut into the wall.** A marching line's place ahead lies straight across a wall whose gate is
   ten tiles aside; the shortcut walked each footman at the rock and its path walked it back, ten seconds
   lost on a twenty-second march. The route is now planned first and kept while on the shortcut, which is
   taken only within `ROUTE_CONE` (45°) of the way the route goes.

Two of these came from the fixes themselves, and the matches caught them. Judging the waypoint skip by a clear
line from the unit's exact spot, not by the tile rule, let a footman graze a rock corner that the next plan
refused: fuzz seed 81, twenty seconds between the two. And with hard bodies nobody reaches the spot a
knight already stands on, so a crowd sent at a target across a walled-in base kept pressing for good until
`stands_at` measured the way in only as far as the route goes. `test_no_unit_is_wedged_in_a_played_match`
and `test_no_two_bodies_come_inside_each_others_core_in_a_played_match` play those matches.

Measured against `main` at f7f0939, compiled: the staged 150-unit battle of `tools/step_bench.py` runs at a
mean 0.41 ms a step against 0.36; `_keep_clear` scans its buckets inline, as `_separate` does, because a
list per call cost twice that. The nine arena matches of `tools/sim_bench.py` run at 0.072 ms a step against
0.068, over matches that are no longer the same ones. `tools/sim_fingerprint.txt` and `tools/sim_bench.txt`
moved with the rules change.

## 10. Flight (WB-064, 2026-09-24)

A unit type with `flying = true` in `units.toml` is in the air; the flying machine is the first. Everything
below reads that one flag (`UnitInfo.flying`, copied onto `Unit.flying` because the crowd's loops ask it of
every neighbour), so the next flyer is a row and its art.

- **It is never routed.** `_approach` and `_steer` hand a flyer to `_fly_to`/`_fly_step`: straight at the
  point over trees, water, rock and buildings, clamped to the map, with the same progress watchdog a walk
  keeps, so a settling flight ends where the flyers already hovering there leave room (`stands_at` counts
  only the unit's own layer). `_plan` refuses a flyer: no nav grid, no A*.
- **It has no body on the ground.** `_keep_clear` neither holds it back nor holds anybody back for it, and
  `_separate`, the ease step and `stands_at` count walkers against walkers and flyers against flyers, so
  flyers keep their elbow room from each other alone. Placement, regrowth, siege spots, work routes, the
  around-units plan and a marching line's pace pass it by; `test_crowd_flow.py`'s core watcher leaves it
  out, and its drawn groups put a flyer where the scout rider used to be, so the walkers are held to going
  through as fast with one in their midst.
- **Only a shot reaches it.** `World.can_strike` is the one answer: anything armed strikes the ground; a flyer
  only by a striker with `UnitInfo.strikes_air` (damage, a range of a tile or more, not siege: archers, the
  cleric's bolt, spiders) or a tower. Auto-acquire, the hold, retaliation, towers and the brains ask
  `_nearest_enemy(air=...)`; an attack order that none of the group can carry out is a `RuleError` the HUD
  shows, and a mixed group sends its shooters and walks the rest along. Stones and their splash come down
  beneath it.
- **It is drawn above everything.** The view lifts it `view.FLIGHT` over its ground point on the `EFFECTS`
  layer, bobbing, its rotor or wings always turning, with a shadow and the selection ring on the ground
  below; the pointer and a dragged box take the body drawn in the air (`MapView.body_point`). A shot climbs
  to it, and a kill drops it out of the air ("crash").

## 11. Through the forest (WB-068, 2026-09-24)

A unit type with `forest = true` (the elves' treant) walks through trees: tree tiles are open ground to it, water,
rock and buildings are not. It is a walker in every other way — it has a body, keeps the hard core, is routed by A* —
only on a grid of its own. `World.ground_of(u)` is that answer, asked wherever a walk reads the static grid: `_plan`
(and its regions, `_regions_of`, for the nearest reachable goal), `_follow`, `_steer`, the shove (`_nudge`/`_shove`)
and `stands_at`. A walker gets the map's `_blocked`, so none of those changed for anybody else, and the fingerprint
on a treant-free match did not move.

- **Built only when asked.** `World.forest_ground()` copies `_blocked` with its tree tiles opened the first time a
  forest walker asks, so a match without a treant never pays for it (a brain asking whether a forest route pays
  builds it too).
- **Kept in step by the buildings alone.** A building stands only on grass, so the forest grid differs from the
  map's exactly on the tree tiles; felling a tree turns a tree tile into grass and a regrown tree turns it back, and
  both are open to a treant either way. Only placing and removing a building (`_set_blocked`) changes it, and that
  is where it is kept. `tools/fuzz.py` checks it against the terrain and the buildings every simulated second once
  it exists, beside the map's own grid. A write to `_blocked` anywhere else (mapgen carves before any unit exists)
  would need the same care.
- **No shared trunks.** A group's march shares one corridor per target on the map's grid (`_join_march`); a treant
  plans alone, so a treant in an army takes the wood where the rest take the road.
- **Standing in the trees.** A treant among trees mends (`regen_in_trees`: its tile or a neighbour a tree),
  out of combat only, as the troll does: regeneration during a fight puts a floor under the damage needed to kill
  it at all (an archer takes 3.6 a second off it, under the 4 it would mend). `_regrow` does not grow a tree under it.
