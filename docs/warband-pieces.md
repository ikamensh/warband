# Generated sound pieces: combat impacts, unit deaths, presences and building wreckage

Four Warband sounds are not synthesised: a blow landing, a unit's death, a machine's or a
creature's presence and a building coming down. All are cues mixed by the game from committed
pieces (`warband/audio/pieces.py` reads them):

- `warband/audio/combat_sound.py`, from `warband/assets/impacts/`: every weapon (sword, axe,
  spear, lance, arrow, siege stone, hammer) on every material (flesh, armour, wood,
  stone), three takes each; the cue is the piece itself, cut so the blow lands as it
  starts. The scene picks weapon and material from the strike (`sound.impact_sound`),
  the bank rotates takes and adds a little pitch variation.

- `warband/audio/deaths.py`, from `warband/assets/deaths/`: one cue per **sound family** and
  take (`warband/audio/bodies.py`, WB-069). A unit type names its family on its row (`sound`);
  a race's people name none and die in their race's family: a cry, then the weapon hitting the
  ground, the body landing and the gear settling. The bodies have their own: a catapult's
  timbers splinter, a rope snaps and the frame crashes; a flying machine sputters, whistles
  down and crashes as its body lands; a wolf yelps and falls, a spider screeches and crunches,
  a troll bellows and falls heavily, a golem's stone grinds and breaks and the rubble settles,
  an Aether Elemental's crystal shatters and its light fades (WB-066; the same when its time runs out).
  Each race's own unit (WB-068) has one too: a gryphon screeches, its wings flail and it and
  its rider hit the ground as the screech dies away; a goblin sapper has two ends: spent, its keg
  goes up, a fuse's fizz and a powder blast a tenth of a second on with the debris raining down
  under its tail (`sapper_spent`: a spent sapper leaves no death event, so the scene plays it at
  the blast, for whoever sees the spot or owns the keg; an explosion, heard at a collapse's level
  and never dropped from a battle's crowd of blows), and shot down on its way, which makes no
  blast in the rules, it dies without one (`sapper_death`): a goblin's high cry, it and its keg
  hitting the dirt, and the fuse sputtering out; a treant splits, comes down as heavy timber and its leaves
  settle; a rune golem breaks as the wild golem does and its runes go out last in a fading hum.
  The bank plays `<family>_death` and picks a take, never the same one twice in a row; the
  scene asks for the dying unit's family, so an orc grunt dies in an orc's voice whoever the
  player is, and an orc's catapult in splintering timber.
- `warband/audio/presence.py`, from `warband/assets/presence/`: a machine answers its player's
  order (a catapult creaks and winches, a flying machine whirrs; a gryphon cries, a sapper's
  fuse fizzes or it giggles, a treant creaks, a rune golem's runes hum, an elemental hums), once
  a family however many were ordered and not again within 1.5 s; a creature is heard as its camp rouses (a wolf's
  snarl, a spider's hiss, a troll's roar, a golem's stony rumble), once a kind of guard each
  time it wakes, as the player first sees a guard of that kind: a camp woken from its far side
  roars as its guards charge into sight, one nobody of the player's sees wakes in silence.
  Presences play at half the sfx level.
- `warband/audio/wreckage.py`, from `warband/assets/wreckage/`: the structure cracks, the mass
  comes down, the debris settles; one cue per material (`wood`, `stone`) and take. The
  scene plays `<material>_collapse` for the building's material (`BUILDING_MATERIALS`
  there also decides which impact Foley a building takes); a site under construction is
  scaffolding, so wood. Collapses are the loudest cue on the field, at 75 % of the sfx
  level, deaths sit at 55 % under the alerts.

## The pieces

Every piece was generated with Stable Audio 3 Medium (Stability AI, Community License:
outputs are owned by the licensee and free to commercialise; the training data is
licensed) through the MLX build of the `Stability-AI/stable-audio-3` repository on an
M4 MacBook Air. `assets/deaths/manifest.json` records, per file, the prompt, the seed,
the requested length and steps, the trimming applied, the length and a SHA-256, so any
piece can be regenerated or challenged.

- The bodies' `<family>_<stage>_<n>.wav` (WB-069): three takes of the first stage, so three
  cues, and two of every other, each take its own sentence (`BODY_DEATHS` in the tool); a
  voice (a yelp, a screech, a bellow, the flyer's whistle) is the `voice` shape, a hit (a
  splinter, a snap, a sputter, a body falling, a crunch) the `impact` shape, and what keeps
  coming down (a frame crashing, stone grinding, rubble) the `collapse` shape. The presences,
  `<family>_<kind>_<n>.wav` under `assets/presence/`, three takes each (`PRESENCES`).
- `<race>_cry_<n>.wav`: four takes, 2 s requested, each from its own prompt
  describing a dying warrior of that race. The same prompt with four seeds gave four
  near-identical takes; different wording per take is what makes them vary.
- `<race>_weapon_<n>.wav`, `<race>_body_<n>.wav`, `<race>_settle_<n>.wav`: two takes
  each, 1.6 s requested, one prompt per stage and race (a sword on stone and mail
  settling for humans, an axe and a shield for orcs, a bow and a quiver for elves, a
  hammer and a helmet for dwarves).
- `<weapon>_<material>_<n>.wav` under `assets/impacts/`: three takes each, 1.6 s requested,
  the `impact` shape; each take is a different verb phrase for the weapon and one of two
  wordings for what it hits, since a shared prompt with three seeds gives three near-identical
  blows.
- `<material>_crack_<n>.wav`, `<material>_collapse_<n>.wav`, `<material>_debris_<n>.wav`
  under `assets/wreckage/`: two takes each. The crack is an `impact` (2 s requested);
  the collapse and the debris use foley's `collapse` shape (3 s requested, kept up to
  2.5 s), since masonry and timber keep coming down after the first crash.

Cutting and checks are `sagaforge.foley`'s: cries are the `voice` shape (everything between
the first and last loud moment, band 90 Hz–9 kHz), stages the `impact` shape (the first
event until 250 ms of quiet, 0.25–1 s, band 30 Hz–9 kHz); silent clips and clicks are
rejected, and two seeds were replaced for that. Pieces are stored mono, 16-bit, 44.1 kHz,
cries at 0.72 peak and stages at 0.8.

## The cues

`wreckage.collapse(material, take)` places the crack at zero, the collapse
`CRACK_TO_COLLAPSE` seconds later and the debris `COLLAPSE_TO_DEBRIS` seconds before the
collapse piece ends (negative: under its tail), with the debris take rotated against the
others, and normalises to `PEAK`.

`deaths.death(family, take)` places the family's stages (`bodies.FAMILIES`) in order: the
first at zero, each later one its `gap` after the stage before starts, or after it ends
(`after_end`; a negative gap starts it under that stage's tail), never before it, levelled to
its `gain`, and normalises the mix to `PEAK`. A race's death puts the weapon 0.15 s before the
cry ends, the body 0.18 s after the weapon and the settle 0.25 s after the body; a stage with
`rotate` takes the take one step on, so no two cues share every piece. The race gaps are the
pilot sound board's defaults, the bodies' first guesses read off their spectrograms; none has
been tuned by ear. Change them there and bump `SOUND_VERSION` so the cache regenerates.
`presence.presence(family, take)` is the piece itself, levelled.

## Remaking a piece

`tools/pieces.py` owns the prompts, seeds and styles for every folder (the bodies' stage names are
`bodies.FAMILIES`', which reads no file) and drives
`sagaforge.foley` (`../sagaforge/docs/foley.md` covers the runtime install and the
prompting lessons):

```bash
export STABLE_AUDIO_MLX=~/stable-audio-3/optimized/mlx
uv run python tools/pieces.py refresh           # generates what is missing or whose spec changed, all four folders
uv run python tools/pieces.py sampler /tmp/pieces   # impacts.wav, deaths.wav, presence.wav and wreckage.wav, every piece back to back
uv run python tools/pieces.py cues /tmp/cues     # the bodies' death and presence cues as mixed: WAV, spectrogram PNG, stats row
```

Change a prompt or a seed in the tool and refresh: only that piece is regenerated, the
manifest follows. A rejected generation (silent, or a click) is named at the end; give it a
new seed in `RESEEDED`. After a refresh bump `SOUND_VERSION` in `warband/audio/sound.py` so the
cached cues are mixed again, and keep `tests/warband/test_deaths.py` and `test_sound.py`
green, with `test_wreckage.py` and `test_combat_sound.py`: they hold the fall after the cry, the collapse longer than any one stage, armour ringing brighter than flesh and siege stones carrying more bass, the level, the length and the absence of clicks.
The same seed reproduces the same clip on the same machine, so the committed WAVs and the
tool agree; the manifest's hashes are the check.
