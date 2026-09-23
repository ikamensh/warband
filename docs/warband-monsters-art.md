# Warband — the neutral creatures

`warband/art/monsters.py` holds the monsters that belong to nobody: a **troll**, a **giant
spider** that spits venom, a **golem** of stone and a **wolf**.  They are art only.  The rules,
the map generator and the computer players know nothing about them yet; this module exists so
that the agent who adds them has the pictures waiting.

Their **meshes** are drawn the way every other figure in the game is drawn: low-poly meshes
through `sagaforge.render3d`, the same `Projection.front(32, 50°)` camera, the same `UNIT_SCALE`,
the same nine frames per facing (stand, a four-step walk, a four-phase blow) posed by the same
`textures.POSES` table, and the same `_prop` canvas with `DROP_UNIT` below the feet.  Nothing in
`textures.py` was changed; this module imports from it.

Those meshes are now the **stand-ins**.  What the game draws is the painted sheet each creature
has under `warband/assets/restyled/`, made by `tools/restyle.py --monsters` through an image
model, the same way every unit and building in the game is painted — see
[what was painted and how](#what-was-painted-and-how) below.

## Distinctness is an acceptance criterion

The first roster was a wolf, a bear and an ogre — and all three were already in the game.
`warband/sim/races.py`: the **orc knight is an Ogre** ("Two-headed brute; thin armour, all
frenzy"), the **orc scout is a Wolf Rider**, the **dwarf knight is a Bear Rider** on a war bear,
and the elves and dwarves ride stags and rams besides.  A neutral creature is never
team-recoloured, so at 32 px the only thing separating "neutral bear" from "dwarf Bear Rider" is
a rider and a team panel — a few pixels either way.  The roster was changed to three shapes
nobody else owns, and `parade-1x.png` now stands each creature next to the unit it must not be
taken for.

## The four

| Creature | What it is | Rig it reuses |
|---|---|---|
| **Troll** | the flagship: the tallest thing in the game, hunched, bare-skinned and bare-handed, with arms that hang past its knees, a small head thrust forward on a horizontal neck, and a ridge of pale bone spines down its spine — biggest over the shoulders. Its blow is a two-handed overhand rake, both claws up and back then driven down. Cold mossy blue-green hide, pale belly, near-black limbs: nothing like the orcs' warm yellow-green. High hit points and no armour, so it has to look like meat that keeps coming | the humanoid rig — `_legs`' stride tables, `_unit_rod` limbs, the shared `Pose` about a hip of its own at 0.94 |
| **Spider** | a dark chitin spitter: bulbous abdomen behind, eight legs kneed **above** its back, palps and bone fangs, a small violet hourglass on its crown. It rears on its back legs to spit and a violet droplet leaves the fangs on the follow-through. Low and wide, which nothing else in the game is | none — invented here, on a planted rig of its own |
| **Golem** | a slow stone brute: granite slabs stacked slightly out of true, a slab of shoulders far wider than its hips, no neck, short column legs, pale quartz seams. Its walk lumbers rather than strides, and its blow is a two-fisted overhead slam whose fists land on the ground in front of its feet, where the splash will be drawn | the humanoid rig again, with `Creature.carry` damping the pose (below) |
| **Wolf** | a lean, low, long-legged pack predator with a ruff, pale eyes and a jaw that opens; its blow is a crouch, a lunge and a snap. It was parked for a year of this file's life because head-on its stand-in is a grey lump and the orc scout already rides a grey wolf; painting settled it (below) | the four-legged rig of `textures._mount`'s orc branch, with the saddle, reins, bridle and team panel taken off |

**Neutral means neutral.** No mesh here takes a player or a team colour, `monster_image` has no
`player` argument, and `tests/warband/test_monsters.py` holds every face of every frame to a
palette containing none of the four team hues.  The spitter's venom is **violet** for the same
reason: Azure, Crimson, Viridian and Amber leave purple unclaimed.  The painted sheets carry the
same rule the other way round: every unit prompt names blue as the team colour *to keep*, and a
creature's forbids it outright, along with every banner, sash, saddle, harness and rider that
would say somebody owns it.  `tests/warband/test_painted_monsters.py::test_nothing_recolours_a_creature`
paints a synthetic sheet wearing the first player's colour and checks that the pixel reaches the
game untouched: there is no player to recolour a creature for, so there is no recolour step.

There is no hue check over the *painted* pixels, and there should not be: a russet wolf is inside
the red-orange band `restyle.recolor` would move, and so is a golem's warm quartz seam.  Nothing
recolours them, so the band means nothing; what a painted creature is held to is the parade at
1×, where a wild animal must not read as somebody's mount.

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
uv run python tools/verify_monsters.py docs/evidence/monsters                  # the sheets, the comparisons, the parade, the lint
uv run python tools/verify_monsters.py docs/evidence/monsters --procedural     # the same from the stand-ins, as -standin files
uv run pytest -q tests/warband/test_monsters.py tests/warband/test_painted_monsters.py --slow
```

`tools/verify_monsters.py` writes, per creature, a contact sheet of all eight facings and all
nine frames on the game's own painted grass (two captures stacked, because eight rows of a
creature do not fit on one screen without treading on each other), plus `parade-1x.png`: the
creatures beside the orc Ogre, the orc Wolf Rider, the dwarf Bear Rider and a footman **at the
real game zoom**, and each creature's nine frames in a strip, unmagnified.  That last picture is
the one that decides whether a silhouette reads; a creature that is handsome at 4× and a blob at
32 px has failed.  It also writes `compare-<creature>.png`, every facing's nine stand-in frames
directly above its nine painted ones on a shared cell, anchor and scale — how a painting is judged
against what it was painted from — and `--procedural` draws the whole set from the stand-ins
instead, as `-standin` files, so the two can be laid side by side.  It then runs the art lint over
all 288 frames: on the painted sheets it reports no `empty`, `clipped`, `chroma`, `floating` or
`identical` finding on any creature frame.

`tests/warband/test_monsters.py` keeps one facing of each creature in the fast tier (the nine
frames render at the size their placement promises, with solid content the canvas does not clip,
and no two frames alike) and all eight facings in the slow tier, through `visual_lint`.  The
lint's `hop` and `slide` are left out of that assertion — they fire on the lunge and stride
`POSES` gives every figure, and the game's own procedural units raise between 12 and 60 of them
apiece — and `turn-slide` is budgeted at 12 px, against the 10.1 px the game's own footman
shows: the check reads the centre of a figure's lowest quarter, and a creature standing on four
or eight feet puts its nearest foot at a corner of its stance.  The golem carries an allowance of
its own at 18 px (`TURN_SLIDE_BUDGETS`), because it stands off its anchor before anybody paints
it: at facings 5 and 7 its stand-in measures 8.6 px, the worst of the four, and its painting 15.6
and 15.9 — three separate Codex rolls gave 16.4, 14.1 and 15.9, so it is the rig, not the roll.
Its chest is turned 5° and its shoulder slabs 7°, on purpose, and the painting only makes that
lean solid.  Standing it back over its anchor is a change to the mesh and a repaint, and is filed
rather than smuggled into the number.  What the budget is there to catch at all is a body so long
that turning swings it off its anchor: the wolf's first draft, twice as long as the one in the
file, slid 18.2 px.

`tests/warband/test_painted_monsters.py` is the painted half, built on synthetic sheets the way
`test_restyled_buildings.py` is: a creature draws every facing and frame off its sheet, placed by
the sheet's own cell and anchor; a sheet missing a frame warns and falls back to the render; a
creature without a sheet renders its stand-in; the portrait comes off the painting; and **nothing
recolours a creature** — the synthetic sheet wears the first player's colour and that pixel has to
reach the game untouched, which is the one thing a unit's sheet would not do.  Its slow tier holds
the committed sheets to no strays and no residue, and pins the layout `figure_sheet` builds for a
unit beside the one it builds for a creature, because the committed sheets were cut to those cells
and anchors.

## What was painted and how

Every unit and building in the game is a painted sheet; the creatures were the last art still
drawn from its stand-ins, and beside a painted footman they looked unfinished.  They are painted
the same way, and `tools/restyle.py --monsters` is the mode that does it — modelled on `--mines`,
because a creature is the gold mine's kind of subject and not a unit's: **nobody's, and never
team-recoloured**.

```sh
uv run python tools/restyle.py --monsters refresh DIR         # dump, render (Codex), cut, preview
uv run python tools/restyle.py --monsters --creatures golem render DIR --force   # one of them again
uv run python tools/restyle.py --monsters check DIR           # the vision judge, cell by cell
```

One creature is one subject: eight facings across, nine frames down, 72 cells on one sheet, at
the same `SCALE = 2` a unit is painted at, with every frame's feet on the same point of its cell.
The runtime half is `monsters.restyled_monster` (an `lru_cache` over `textures._painted`, so a
sheet that no longer holds every frame warns and is ignored, and `WARBAND_ART=procedural` keeps
the renders), `monsters.monster_heads` for what a health bar would hang over, and
`monster_image`, which registers the painted cell **as it is**.  There is no `_recoloured` call
in this module and no `player` to make one with.

What the prompts had to say that a unit's does not:

* **No team colour at all.** A unit's prompt names blue as the team colour to keep; a creature's
  forbids blue and every banner, pennant, sash, tabard, emblem, saddle, harness, rein, bridle,
  barding, armour, weapon and rider.
* **Its own names for the four attack rows.** The shared `FRAME_NAMES` call them a weapon drawn
  back, driven at the enemy and swept across the body.  A creature has no weapon, and the first
  render was stopped when the row text was read back: the troll rakes with both arms, the spider
  rears to spit, the golem slams two fists down, the wolf springs and bites, and each creature
  now names its own rows (`MONSTER_ATTACK`).
* **A russet wolf.** See the verdict below.
* **A stance the golem may not widen.** Its stand-in is already within a pixel of the two tiles a
  sprite may span, and a painter that spreads the feet breaks that and swings the figure's lowest
  band off its anchor as it turns.  Saying so in `MONSTER_FIXES` fixed the width.

**Driving Codex.**  `render` with the default provider, four sheets concurrently, about two
minutes each; then `check`, which lays two rows by four columns of stand-ins-above-paintings into
a review image and asks Codex to compare them cell by cell against `MONSTER_JUDGE` (a
`MINE_JUDGE`-shaped prompt that counts legs and refuses a saddle).  **All four sheets came back
0 of 72 cells questioned on the first judge pass**, so no `--fix` or `--patch` round was needed.
The golem was rendered three times all the same, for geometry rather than content: roll 1 drew it
wider than the two tiles a sprite may span, roll 2 was a plain re-roll and did it again, and roll
3 — the one installed — came back inside the width once the stance line went into its
`MONSTER_FIXES`.  What three rolls did *not* move is its turn-slide, which is how that came to be
read as the rig rather than the painting.

**One thing the cut left behind.**  `restyle.cut` clears the key's faint field first and removes
strays after, because a stray can hide a sliver of field — and the reverse is true too.  The
creature sheets showed both halves: a halo of twenty to fifty pixels around a stray the cut had
taken off, and a thread of the grid line that the registration's own shift slid in from the next
cell once the field around it was gone.  `settled()` in the tool runs one more
`declutter(clear_residue(...))` over every cut before it is installed; a second pass then finds
nothing, and `tests/warband/test_painted_monsters.py` holds the committed sheets to no strays and
no residue.

### The wolf: kept

The wolf was finished but parked, because head-on its stand-in is a grey lump and the orc scout
already rides a **great grey wolf** — and a neutral creature has no team colour to tell it from
somebody's mount.  The question was whether painting would make it read as its own animal.  It
does, and it is kept.

Two things decided it.  The first is `compare-wolf.png`, which puts each facing's stand-in row
directly above its painted row: the grey lump becomes a lean animal with a readable head, ruff,
brush tail and four legs on the ground, and in the strike row a gaping jaw — in the same pose, at
the same size, on the same ground.  The second is `parade-1x.png` at `TILE = 32`, where the bare
wolf stands two columns from the orc Wolf Rider.  They are not the same animal at that size: the
wild one is **russet-brown with a pale throat and belly**, alone and low; the orc's is grey and
carries a green rider in red and blue with a blue cape and a spear, nearly twice the height.  The
coat is deliberate — the prompt asks for russet precisely because the orc's mount is grey, and
that one word is what a creature has instead of a team panel.

Had it not read, the file, the registry entry, the tests and the sheet would have gone; the draft
is recoverable from the `wb-monster-art` branch.  It read.

## The dens

Each creature names a den (`monsters.LairKind`, `lair_kind_for_roster`): a boulder-ringed **wolf
den** with a skull and bone spines, a low **spider nest** of earth under silk drapes with cream egg
sacs and violet venom at its slit mouth, a tall mossy **troll mound** with a ribcage arch over its
mouth, and a stepped **stone cairn** with quartz seams and a skull on its cap.  Same 3×3 footprint,
same dark mouth facing the camera, same bone-white mark — one camp language, four silhouettes.
The wolf den is the old shared den untouched; the other three are new meshes in the same helpers
and colours, each with a damaged look (crown toppled, mark knocked down, rubble at the foot) that
keeps the footprint.

They are painted like the mines, because like a mine a den is nobody's and never recoloured:
`tools/restyle.py --lairs` (`Lairs` in the tool) paints `lair.intact` — four cells on one sheet at
building scale — from the stand-ins, then `lair.damaged` from the installed intact painting.
Rendered with the OpenRouter provider (Gemini 3.1 Flash Image, about fifteen cents a sheet): intact
cut at 0 of 4 flagged; damaged took three rolls, the first two filling the cells' backgrounds with
dirt instead of the key, fixed by telling the damaged prompt the damage stays on the den itself.
The vision judge questioned 1 of 8 cells, the troll's moss for reading blue — kept as a false
alarm, since the teal is the troll's own hide colour, nothing recolours a den, and there is no
banner to confuse it with.  The runtime (`monsters.restyled_lair`) prefers the painting per look
and falls back to the render per kind, exactly as the mines do.

```sh
uv run python tools/restyle.py --lairs --looks intact dump DIR        # the stand-in sheet and its prompt
uv run python tools/restyle.py --lairs refresh DIR --provider openrouter   # intact, then damaged, then previews
uv run python tools/restyle.py --lairs check DIR                      # the vision judge, cell by cell
```

## Landscape coats

The wilds wear the ground they stand on.  Summer is the painted sheet (or the stand-in) as it
stands; winter and the wasteland are procedural coats over it — per-channel gains plus a blend
towards a landscape colour, masked by brightness so a cave mouth, a nose or dark chitin stays
dark on every landscape while the coat takes the weather (`monsters.COATS` for the creatures,
`monsters.LAIR_COATS` for the dens, `ambience.landscape_halo` for the breath).  The same coat
tints the stand-in render where there is no sheet, so both paths agree, and the silhouette never
moves: only the palette does.  Summer keeps the sheet's own asset key; the other landscapes are
suffixed (`.winter`, `.wasteland`), so every landscape's coat is its own registered image and the
view, the warm-up and the selection cards all draw the world's own.

| landscape | wolf | spider | troll | golem | dens |
|---|---|---|---|---|---|
| Summer | russet, as painted | dark chitin, violet venom | mossy blue-green | granite grey | as painted |
| Winter | snow wolf: pale grey-white | frost-pale chitin, venom kept violet | ice troll: pale, cold | snow dust on the slabs | snow-dusted crowns, cool tint |
| Wasteland | dune wolf: sandy blonde | sun-bleached chitin | sand troll: dusty | sandstone slabs | sand drifted at the stones, warm tint |

A wolf reads as a wolf everywhere; what changes is the weather on it.  The coats keep clear of
the team hues the same way the meshes do, the bone-white marks and dark mouths survive every
landscape (a test holds the mouths dark), and the names, rosters, minimap mark and ambience
anchors do not vary at all — the dens are told apart by silhouette and coat, never renamed.

No repaint was needed and none was run: the coats are procedural tints over the committed
sheets, so there are no per-landscape sheets for `tools/restyle.py` to paint.  (The pipeline is
there if a coat ever wants a painter's hand instead of arithmetic: `--monsters`/`--lairs` dump
the stand-ins and their prompts without a model.)  Roster variants per landscape — ice trolls
with different rules from sand trolls — were deferred deliberately: they would be a sim change
(new kinds or per-theme rosters, fingerprint and balance surface included) for no gameplay, and
the creep gate holds on every landscape today precisely because the theme never enters the sim.

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
