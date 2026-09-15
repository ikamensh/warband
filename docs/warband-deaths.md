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

- `<race>_cry_<n>.wav`: three or four takes, 2 s requested, each from its own prompt
  describing a dying warrior of that race. The same prompt with four seeds gave four
  near-identical takes; different wording per take is what makes them vary.
- `<race>_weapon_<n>.wav`, `<race>_body_<n>.wav`, `<race>_settle_<n>.wav`: two takes
  each, 1.6 s requested, one prompt per stage and race (a sword on stone and mail
  settling for humans, an axe and a shield for orcs, a bow and a quiver for elves, a
  hammer and a helmet for dwarves).

Trimming: cries lose leading and trailing quiet below −42 dB, keep a 60 ms tail and are
band-limited to 90 Hz–9 kHz. Stages are cut to their first impact (from the onset until
250 ms of quiet below 3.5 % of the peak, 0.25–1 s), high-passed at 30 Hz and low-passed
at 9 kHz. Two kinds of failed generation were rejected: a near-silent clip (one elf cry)
and a clip whose energy sat mostly above 9 kHz, a click rather than an impact (one human
settle). Pieces are stored mono, 16-bit, 44.1 kHz, cries at 0.72 peak and stages at 0.8.

## The cue

`deaths.death(race, take)` places cry *take* at zero, the weapon `FALL_START` seconds
from the end of the cry (negative: as the voice cuts off), the body `WEAPON_TO_BODY`
later and the settle `BODY_TO_SETTLE` after that, with the gains in `GAINS`, and
normalises the mix to `PEAK`. The body take is rotated against the others so no two cues
share a whole fall. The constants are the pilot sound board's defaults, not yet tuned
by ear; the board's sliders are the place to tune them, then copy the values here and
bump `SOUND_VERSION` so the cache regenerates.

## Remaking a piece

The generator is not in this repository. Clone `Stability-AI/stable-audio-3`, run
`optimized/mlx/install.sh -y --download medium`, then for a stage:

```bash
./sa3 --dit medium --decoder same-l --seconds 1.6 --steps 8 --seed SEED --prompt "PROMPT" --out piece.wav
```

with the prompt and seed from the manifest (cries use `--seconds 2`), trim as above,
replace the file and update the manifest entry. Small SFX is faster but diverged on
1.6 s clips in the pilot; Medium was stable at every setting tried. Keep the checks in
`tests/warband/test_deaths.py` and `test_sound.py` green: they hold the fall after the
cry, the level, the length and the absence of clicks.
