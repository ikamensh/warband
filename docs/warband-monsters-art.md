# Warband — the neutral creatures

`warband/art/monsters.py` holds the monsters that belong to nobody: a **troll**, a **giant
spider** that spits venom, a **golem** of stone, and a **wolf** that is parked (see below).
They are art only.  The rules, the map generator and the computer players know nothing about
them yet; this module exists so that the agent who adds them has the pictures waiting.

They are drawn the way every other figure in the game is drawn: low-poly meshes through
`sagaforge.render3d`, the same `Projection.front(32, 50°)` camera, the same `UNIT_SCALE`, the
same nine frames per facing (stand, a four-step walk, a four-phase blow) posed by the same
`textures.POSES` table, and the same `_prop` canvas with `DROP_UNIT` below the feet.  Nothing in
`textures.py` was changed; this module imports from it.

## Distinctness is an acceptance criterion

The first roster was a wolf, a bear and an ogre — and all three were already in the game.
`warband/sim/races.py`: the **orc knight is an Ogre** ("Two-headed brute; thin armour, all
frenzy"), the **orc scout is a Wolf Rider**, the **dwarf knight is a Bear Rider** on a war bear,
and the elves and dwarves ride stags and rams besides.  A neutral creature is never
team-recoloured, so at 32 px the only thing separating "neutral bear" from "dwarf Bear Rider" is
a rider and a team panel — a few pixels either way.  The roster was changed to three shapes
nobody else owns, and `parade-1x.png` now stands each creature next to the unit it must not be
taken for.

## The three, and the one that is parked

| Creature | What it is | Rig it reuses |
|---|---|---|
| **Troll** | the flagship: the tallest thing in the game, hunched, bare-skinned and bare-handed, with arms that hang past its knees, a small head thrust forward on a horizontal neck, and a ridge of pale bone spines down its spine — biggest over the shoulders. Its blow is a two-handed overhand rake, both claws up and back then driven down. Cold mossy blue-green hide, pale belly, near-black limbs: nothing like the orcs' warm yellow-green. High hit points and no armour, so it has to look like meat that keeps coming | the humanoid rig — `_legs`' stride tables, `_unit_rod` limbs, the shared `Pose` about a hip of its own at 0.94 |
| **Spider** | a dark chitin spitter: bulbous abdomen behind, eight legs kneed **above** its back, palps and bone fangs, a small violet hourglass on its crown. It rears on its back legs to spit and a violet droplet leaves the fangs on the follow-through. Low and wide, which nothing else in the game is | none — invented here, on a planted rig of its own |
| **Golem** | a slow stone brute: granite slabs stacked slightly out of true, a slab of shoulders far wider than its hips, no neck, short column legs, pale quartz seams. Its walk lumbers rather than strides, and its blow is a two-fisted overhead slam whose fists land on the ground in front of its feet, where the splash will be drawn | the humanoid rig again, with `Creature.carry` damping the pose (below) |
| *Wolf* (parked) | a lean, low, long-legged pack predator with a ruff, pale eyes and a jaw that opens; its blow is a crouch, a lunge and a snap. Complete and rendered, but it is the orc scout's mount without a rider, so it is nobody's to ship until the orchestrator decides it reads clearly enough at 1× | the four-legged rig of `textures._mount`'s orc branch, with the saddle, reins, bridle and team panel taken off |

**Neutral means neutral.** No mesh here takes a player or a team colour, `monster_image` has no
`player` argument, and `tests/warband/test_monsters.py` holds every face of every frame to a
palette containing none of the four team hues.  The spitter's venom is **violet** for the same
reason: Azure, Crimson, Viridian and Amber leave purple unclaimed.

## The rig

Each creature declares a `Creature(mesh, hip, bob, carry)`:

* `hip=None` is a **planted** rig — everything at or below `PLANTED` (z = 0.2) stays on the
  ground and the body bobs over it, the branch `textures._posed` takes for a mount.  The spider
  and the wolf use it; the spider with `bob=0` because a spider's body does not bounce.
* a `hip` value is a **hipped** rig: everything above it leans, twists and sways per the shared
  `Pose`.  The troll's hip is at 0.94 and the golem's at 0.50, against the humanoid `HIP` of
  0.28 — a troll is half again a knight's height, and pivoting it at a footman's waist bent it
  at the shins.
* `carry` scales how much of that shared `Pose` a hipped creature takes.  The golem is at 0.35:
  the table is authored for a man, and leaning a golem's wide shoulder slab fourteen degrees
  over a low hip threw the whole mass off its feet — it face-planted on every `strike`.
* A planted rig only bobs and lunges, so **the blow has to be the body**.  The wolf's front half
  pitches about its hips with an opening jaw and forelegs that reach ahead of where they stand;
  the spider rears about its back legs.  Without that, `wind`/`strike`/`follow`/`recover` were
  the `stand` frame with a 0.16-unit shuffle, which nobody would see.
* `_carry_low_faces` carries a limb that hangs below the hip — a troll's knuckles, a golem's
  fists — with the body it belongs to, because the shared pose moves only what is above the hip.

## The API the rules agent wants

```python
from warband.art.monsters import Monster, monster_image, warm_monsters, monster_portrait_image, DEATH_OUTCOME

monster_image(game, Monster.TROLL, facing, frame)  # -> an asset key; textures.placements[key] has its size/drop
warm_monsters(game)                                # a generator of every key, one render per step
monster_portrait_image(game, Monster.GOLEM)        # the selection panel's picture
DEATH_OUTCOME[Monster.GOLEM]                       # "wreck": effects.death_outcome knows only the game's own mounts
```

A caller that has added a `UnitType` per creature reaches the art with `Monster(unit.type.value)`,
because the enum values are exactly `"troll"`, `"spider"`, `"golem"` and `"wolf"`.

## Verification

```sh
uv run python tools/verify_monsters.py docs/evidence/monsters      # the sheets, the parade and the lint
uv run pytest -q tests/warband/test_monsters.py --slow
```

`tools/verify_monsters.py` writes, per creature, a contact sheet of all eight facings and all
nine frames on the game's own painted grass (two captures stacked, because eight rows of a
creature do not fit on one screen without treading on each other), plus `parade-1x.png`: the
creatures beside the orc Ogre, the orc Wolf Rider, the dwarf Bear Rider and a footman **at the
real game zoom**, and each creature's nine frames in a strip, unmagnified.  That last picture is
the one that decides whether a silhouette reads; a creature that is handsome at 4× and a blob at
32 px has failed.  It then runs the art lint over all 288 frames.

`tests/warband/test_monsters.py` keeps one facing of each creature in the fast tier (the nine
frames render at the size their placement promises, with solid content the canvas does not clip,
and no two frames alike) and all eight facings in the slow tier, through `visual_lint`.  The
lint's `hop` and `slide` are left out of that assertion — they fire on the lunge and stride
`POSES` gives every figure, and the game's own procedural units raise between 12 and 60 of them
apiece — and `turn-slide` is budgeted at 12 px, against the 10.1 px the game's own footman
shows: the check reads the centre of a figure's lowest quarter, and a creature standing on four
or eight feet puts its nearest foot at a corner of its stance.  What the budget is there to
catch is a body so long that turning swings it off its anchor: the wolf's first draft, twice as
long as the one in the file, slid 18.2 px.

## What codex was asked for, and what had to be fixed by hand

The meshes were authored with `codex exec`, five passes, each one fed the rendered sheets from
the last (`codex exec -i <png>`).  It was given the real idiom to work in — the helpers'
source, `textures._mount` as the four-legged pattern, the humanoid rig, the colour constants,
the coordinate conventions and the pose machinery — and asked for mesh functions in that style,
nothing else.  What it wrote was a draft every time:

* **Pass 1** produced all four creatures.  The spider was right the first time and has barely
  changed.  The wolf was a dachshund 1.6 units long, the bear a single-tone brown potato whose
  r = 0.42 body swallowed its legs, and the ogre a featureless column.
* **Pass 2**, given those renders, shortened the wolf, gave the bear three tones and the golem-
  to-be a waist, and shrank the spider's violet marking from a whole abdomen to an hourglass.
  By hand: its ogre stood *behind* its anchor (feet at y = -0.26), so the sprite floated 1.8 px
  above the ground it was placed on.
* **Pass 3** gave the wolf its lunge-and-snap.  Its bear rear-and-swipe and its plum ogre
  palette were discarded with the roster.
* **Pass 4** turned the ogre into the troll and the bear into the golem.  By hand: `Creature.carry`,
  because the golem took a man's lean and fell over; `DEATH_OUTCOME[GOLEM]` is `"wreck"`, not
  the `"topple"` it chose — a stone golem breaks where it stands.
* **Pass 5** put mass on the troll and stopped the golem folding in half.

Every pass was reviewed line by line before it landed, and every pass was rendered in all eight
facings and all nine frames and looked at, zoomed and at 1×, before the next brief was written.
