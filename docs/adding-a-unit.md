# Adding a unit

What a new unit type needs before it is done. Three times on 2026-09-24 a unit
was added (the flying machines, then the four unique units of WB-068) and each
time it came in with its race's sounds and the render's art, because nothing
asked for more. This is the list, and the tests named under each step fail
when a unit type skips it, so the next unit cannot.

## The row and its names

A row in `warband/assets/constants/units.toml` (or `neutrals.toml` for a
creature): its numbers, `living`, `flying`, its armour class and attack. Its
name and summary for every race that fields it in `races.toml`, and its plural
in `IRREGULAR_PLURALS` (`warband/ui/scene.py`) if it is not the name plus "s"
(`tests/warband/test_cancel_mode.py` lists every name). Its codex line; the
card and the tech tree read the row.

## Its art

Every unit type a race fields, and every creature, wears a painted sheet per
race (a creature one sheet), recoloured per team; the low-poly render is its
stand-in. `tests/warband/test_painted_sheets.py` fails for one with neither a
sheet nor a row in `textures.UNPAINTED_UNITS`, `{unit type: (reason, date)}`,
and for a row whose unit is painted. A row is written only when the painters
fail, with what they returned: procedural art is a debt, never a default.

1. **Render.** The rig (`textures._unit_mesh`, a creature's in
   `warband.art.monsters`) draws every frame of `textures.sheet_frames` in the
   eight facings: a frame that moves differs from its neighbours (a flyer's
   rotor turns across its walk frames), and where the camera sees it; a painter
   cannot keep a motion the stand-in hides (the goblin zeppelin's pusher prop
   sat under its bag, 0.5 % of the figure moved from frame to frame, until it
   became a great tail propeller). The team's colour is on the parts that say
   whose it is and nowhere else, at least `visual_lint.TEAM_MARK` pixels.
   `test_every_unit_pose_fits_the_unit_canvas` holds the poses to the canvas.
2. **Describe.** In `tools/restyle.py`: a `SUBJECTS` line for every race that
   fields it, naming the team colour; `FIXES` or `RACE_FIXES` for what the rig
   gets wrong; an `INVENTORY` line the judge counts. Rows that are no walk and
   no blow get their own names (the flyers' `ROTOR_ROWS`, `WING_ROWS`).
3. **Paint.** `uv run python tools/restyle.py --race R --units U dump DIR`,
   read `DIR/R.U.prompt.txt`, then `render DIR`, one race after another (one
   painting job at a time). The painter that worked on 2026-09-24 is Codex's
   image tool through the ChatGPT app's own CLI:
   `PATH=/Applications/ChatGPT.app/Contents/Resources:$PATH` in front of the
   command (the Homebrew `codex` 0.153 is refused the model its configuration
   names, "not supported when using Codex with a ChatGPT account"; the judge
   needs the same). The second is OpenRouter (`render --provider openrouter`,
   Gemini 3.1 Flash Image, 2K canvases work: $0.10 a picture, $12.50 of credit
   left that day); the stored OpenAI and Google keys are dead.
4. **Cut.** `cut DIR` keys out the magenta, registers the whole sheet at one
   scale and shift, and installs it under `warband/assets/restyled/`; more
   than two flagged cells rejects it: re-render rather than patch.
5. **Judge.** `check DIR` has Codex count each painted cell's parts beside its
   stand-in (`--patch` re-renders only the rows it questions). One or two false
   alarms a sheet are usual.
6. **Look.** `preview DIR OUT` writes the stand-ins above the painting through
   the walk and the blow; then a real frame in play (`tools/verify.py DIR` or
   `saga2d.testing.render_scene`): on the map, on the card, several frames of
   its animation, and a second player's colour.
7. **Lint.** `tools/visual_lint.py --no-screens --evidence DIR` clean: a
   painted figure off its render (drift), a recolour that did not take, the
   key's fringe or strays, two frames of one motion that are one picture; then
   `uv run pytest -q --slow tests/warband/test_painted_sheets.py`. Art is no
   rule: `tools/sim_fingerprint.py --check` stays green.

## Its sounds

A death is the body's, not the race's. The row names the unit's **sound
family**, `sound = "…"` (`UnitInfo.sound`); a row without one dies in the
voice of the race that fields it, which is right only for a race's people (a
peasant, a footman, an archer, a knight, a cleric). A machine, a creature, a
rider on a beast, a walking tree or a construct names a family of its own.
The families are `FAMILIES` in `warband/audio/bodies.py`, data like the row:

- **its death**: the stages in order (`Stage`: the kind of piece, its gain,
  and where it starts from the stage before), so a catapult is timbers
  splintering, a rope snapping, the frame crashing, and a wolf a yelp and a
  body falling. The cue has a take for every piece of the first stage: give it
  three, and every stage at least two.
- **its presence**, where it has one: the kind of piece it answers with when
  its player orders it (one answer a family however many were ordered, not
  again within `ANSWER_GAP`), or makes as its camp rouses (once a kind of
  guard a waking, as the player first sees one: `GameScene._hear_camps`). A
  race's people have none; the race's order cue speaks for them.
- **its material**, where its body decides what a blow lands on (a machine's
  `wood`, a golem's `stone`); without one its armour decides, flesh or armour.
  What it strikes *with* is `_WEAPONS` in `warband/audio/sound.py`.

The pieces are generated with Stable Audio 3 through `sagaforge.foley`: write
a prompt per take in `tools/pieces.py` (`BODY_DEATHS`, `PRESENCES`; a
different sentence per take, since seeds alone give near-identical takes),
then `tools/pieces.py refresh` (one generation job at a time: it is heavy),
bump `SOUND_VERSION`, and look at the cues before anyone listens:
`tools/pieces.py cues DIR --families NAME` writes each cue's WAV, a
spectrogram and a stats row (`docs/warband-pieces.md`). A generation the tool
rejects gets a new seed in `RESEEDED`; never a synthesised stand-in.

`tests/warband/test_bodies.py` holds every unit type in `UnitType`, playable
or creature, to a death of its own body with at least two takes on disk, for
every race that could field it; a unit type outside `SOLDIERS` (the race's
people) that resolves to a race's family fails, and so does a creature or a
machine without a presence. `tests/warband/test_deaths.py` holds every family's
cues to their level, length and clean ends, and the bodies to their physical
contrasts. Sound is no rule: the fingerprint stays where it was.

## Its brains

Who trains it and when, what it is sent at, and what answers it: a test on a
staged world for each decision, and `tools/arena.py` or `tools/race_report.py`
before and after (`docs/ai-ladder.md`, `docs/balance.md`).

## Its checks

`tools/visual_lint.py` over the new screens and sprites, `tools/fuzz.py`, the
fingerprint and `tools/sim_bench.txt` refreshed in the same commit, and a frame
of it in play looked at.
