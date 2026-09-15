# Generated sound pieces: unit deaths and building wreckage

Two Warband sounds are not synthesised: a unit's death and a building coming down.
Both are cues mixed by the game from committed pieces (`warband/pieces.py` reads them):

- `warband/deaths.py`, from `warband/assets/deaths/`: a cry, then the weapon hitting the
  ground, the body landing and the gear settling; one cue per race and take. The bank
  plays `<race>_death` and picks a take, never the same one twice in a row; the scene
  asks for the dying unit's own race, so an orc grunt dies in an orc's voice whoever
  the player is.
- `warband/wreckage.py`, from `warband/assets/wreckage/`: the structure cracks, the mass
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

- `<race>_cry_<n>.wav`: four takes, 2 s requested, each from its own prompt
  describing a dying warrior of that race. The same prompt with four seeds gave four
  near-identical takes; different wording per take is what makes them vary.
- `<race>_weapon_<n>.wav`, `<race>_body_<n>.wav`, `<race>_settle_<n>.wav`: two takes
  each, 1.6 s requested, one prompt per stage and race (a sword on stone and mail
  settling for humans, an axe and a shield for orcs, a bow and a quiver for elves, a
  hammer and a helmet for dwarves).
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

`deaths.death(race, take)` places cry *take* at zero, the weapon `FALL_START` seconds
from the end of the cry (negative: as the voice cuts off), the body `WEAPON_TO_BODY`
later and the settle `BODY_TO_SETTLE` after that, with the gains in `GAINS`, and
normalises the mix to `PEAK`. The body take is rotated against the others so no two cues
share a whole fall. The constants are the pilot sound board's defaults, not yet tuned
by ear; the board's sliders are the place to tune them, then copy the values here and
bump `SOUND_VERSION` so the cache regenerates.

## Remaking a piece

`tools/pieces.py` owns the prompts, seeds and styles for both folders and drives
`sagaforge.foley` (`../sagaforge/docs/foley.md` covers the runtime install and the
prompting lessons):

```bash
export STABLE_AUDIO_MLX=~/stable-audio-3/optimized/mlx
uv run python tools/pieces.py refresh           # generates what is missing or whose spec changed, both folders
uv run python tools/pieces.py sampler /tmp/pieces   # deaths.wav and wreckage.wav, every piece back to back
```

Change a prompt or a seed in the tool and refresh: only that piece is regenerated, the
manifest follows. A rejected generation (silent, or a click) is named at the end; give it a
new seed in `RESEEDED`. After a refresh bump `SOUND_VERSION` in `warband/sound.py` so the
cached cues are mixed again, and keep `tests/warband/test_deaths.py` and `test_sound.py`
green, with `test_wreckage.py`: they hold the fall after the cry, the collapse longer than any one stage, the level, the length and the absence of clicks.
The same seed reproduces the same clip on the same machine, so the committed WAVs and the
tool agree; the manifest's hashes are the check.
