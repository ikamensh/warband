# Unit deaths: generated cries and falls

A unit's death is the first Warband sound that is not synthesised. `warband/deaths.py`
mixes a cue per race and take from committed pieces under `warband/assets/deaths/`:
a cry, then the weapon hitting the ground, the body landing and the gear settling.
The bank plays `<race>_death` and picks a take, never the same one twice in a row;
the scene asks for the dying unit's own race, so an orc grunt dies in an orc's voice
whoever the player is.

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

Cutting and checks are `sagaforge.foley`'s: cries are the `voice` shape (everything between
the first and last loud moment, band 90 Hz–9 kHz), stages the `impact` shape (the first
event until 250 ms of quiet, 0.25–1 s, band 30 Hz–9 kHz); silent clips and clicks are
rejected, and two seeds were replaced for that. Pieces are stored mono, 16-bit, 44.1 kHz,
cries at 0.72 peak and stages at 0.8.

## The cue

`deaths.death(race, take)` places cry *take* at zero, the weapon `FALL_START` seconds
from the end of the cry (negative: as the voice cuts off), the body `WEAPON_TO_BODY`
later and the settle `BODY_TO_SETTLE` after that, with the gains in `GAINS`, and
normalises the mix to `PEAK`. The body take is rotated against the others so no two cues
share a whole fall. The constants are the pilot sound board's defaults, not yet tuned
by ear; the board's sliders are the place to tune them, then copy the values here and
bump `SOUND_VERSION` so the cache regenerates.

## Remaking a piece

`tools/deaths.py` owns the prompts, seeds and styles and drives `sagaforge.foley`
(`../sagaforge/docs/foley.md` covers the runtime install and the prompting lessons):

```bash
export STABLE_AUDIO_MLX=~/stable-audio-3/optimized/mlx
uv run python tools/deaths.py refresh                 # generates what is missing or whose spec changed
uv run python tools/deaths.py sampler /tmp/deaths.wav # every piece back to back, to listen once
```

Change a prompt or a seed in the tool and refresh: only that piece is regenerated, the
manifest follows. A rejected generation (silent, or a click) is named at the end; give it a
new seed in `RESEEDED`. After a refresh bump `SOUND_VERSION` in `warband/sound.py` so the
cached cues are mixed again, and keep `tests/warband/test_deaths.py` and `test_sound.py`
green: they hold the fall after the cry, the level, the length and the absence of clicks.
The same seed reproduces the same clip on the same machine, so the committed WAVs and the
tool agree; the manifest's hashes are the check.
