# Warband music

Warband's music is composed, not recorded: fifteen original pieces synthesised
by `warband/music.py` with the orchestra in `warband/instruments.py` on top of
`saga2d.synth`.  Nothing is downloaded or licensed; the WAVs are rendered on the
player's machine and cached under `~/.warband/music/` (about 170 MB for the
whole catalogue).

## The catalogue

| Race | At peace (alternate at their loop points) | In battle |
|---|---|---|
| Humans | **Hearth** — lute under a flute, horns answering, a hand drum (A aeolian, 96) · **Banners** — a field-snare march, horns on the theme, strings and choir (D dorian, 104) | **Clash** — timpani and snare, a low-string ostinato, brass stabs, choir at the height (D aeolian, 132) |
| Orcs | **Bonfire** — a horn drone, slow taiko, rattles, a chant circling the flat second (D phrygian, 84) · **Warpath** — drums on every beat, toms, growling horns, shouted chant (108) | **Bloodrush** — war drums and toms in eighths, a carnyx ostinato on the flat second, shrieking pipes (140) |
| Elves | **Moonlight** — harp arpeggios under a whistle, bells on the bar, strings breathing (D lydian, 76) · **Starfall** — choir on a slow lydian tide, harp sixteenths, chimes, flute (88) | **Wildhunt** — a harp ostinato in sixteenths, hand drums running, strings and horns calling (D dorian, 128) |
| Dwarves | **Deepforge** — anvils on the beat, low horns, hammered dulcimer over male voices (E aeolian, 80) · **Stonehall** — a reed drone and chanter tune, dulcimer, a hall of voices (E dorian, 92) | **Ironwall** — an anvil ostinato, kick and snare, hammering low strings, horns and timpani (124) |
| Title | **Vigil** — the night watch: low strings, a bell, distant voices, a harp in the small hours (D aeolian, 66) | |
| Endings | **Victory** — a D-major horn fanfare over timpani, held by strings · **Defeat** — cellos falling stepwise to the low root, a bell, one last drum | |

Every race has its own motif (a short phrase in scale degrees) that the `line`
layer develops through each piece: the plain shape, a sequence on the chord's
third, its inversion on the fifth, then a version that rests on the root.  The
same motif carries a race's peaceful and battle pieces, so the music changes
character without changing identity.  Peaceful pieces run 32 bars in four
eight-bar sections (a sparse opening, the theme, an answer with a counter-line,
a release that leads back round); battle pieces keep the drums going and build
to a choir.  Loops wrap their tails round to the first bar; the room's reverb
wraps too, so no loop has a seam.

## How it plays

`warband.music.Director` turns a **mood** into track changes, and the scenes
report their mood through `sound.play_music(mood, race)`:

- `"title"` on the title screen.
- `"peace"` while the player builds and `"battle"` from three blows struck by
  or on the player's forces within three seconds, held for ten seconds past
  the last blow (`GameScene.mood`).  A battle piece plays at least twelve
  seconds once begun so a skirmish does not flap the music.
- `"victory"` / `"defeat"` when the match ends; the ending plays once and the
  music stops.

Every change crossfades through `AudioManager.play_music(..., fade=...)`:
about a second into a battle, three seconds back to peace, four seconds
between the two peaceful pieces, which alternate whenever one has played
through.

## Generation and caching

Effects (117 short cues) are generated before the first window opens.
The music takes about 25 seconds of synthesis in total, so `sound.install`
composes it in a background thread in `COMPOSE_ORDER` — the title piece first,
then each race's suite (opener, battle piece, second piece), then the endings.
When a match asks for its race's music, that suite jumps to the front of the
queue, so a first-launch match hears its opener within a few seconds.  A piece
wanted before it is ready starts, with its fade, the moment the composer
finishes it; a `Game.every` timer polls for that.  Files are written under a
temporary name and renamed, so a cached track is whole or absent, and a new
`SOUND_VERSION` discards the whole cache.  `--selftest` and the packaged build
check wait for the entire catalogue.

While the composer works (the first launch only, or after a version bump) the
game keeps running: measured on the real backend, median frame time rose from
5.4 ms to about 6 ms and the 95th percentile from 8.8 to about 10 ms, with the
paced 30 FPS loop dipping to roughly 18–25 FPS during the heaviest pieces.

## Looking and listening

```bash
uv run python tools/music_warband.py render /tmp/warband-music     # WAV + spectrogram PNG + stats per piece
uv run python tools/music_warband.py sampler /tmp/warband-music    # 12 s of every piece in one WAV (and M4A)
uv run python tools/verify_warband_music.py /tmp/warband-music     # the director on the real backend, silent driver
uv run python -m pytest tests/warband/test_music.py -q
```

The verifier composes into its own directory, shows the title, starts a
dwarven match, scripts a fight and an elimination, and checks every change on
the native players: the opener within twelve seconds of the match, two
players during each crossfade, one after, none once the ending has played.

The stats table reports loudness, crest factor, spectral centroid, the share
of energy below 120 Hz and above 6 kHz, and the seam jump.  Mastering measures
loudness above 200 Hz so a heavy drum cannot push the melody down; the test
suite holds every piece to a common loudness window, a bounded low-end share,
a real stereo image and a quiet seam.  Waveform checks establish balance and
continuity, not taste: listen to the sampler before shipping a change.
