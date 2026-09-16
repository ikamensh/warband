# Warband — agent notes

A Warcraft 2-style real-time strategy game, the second reference game of the
Saga stack (`~/saga/`, see `../AGENTS.md`). Saga2D is a pinned PyPI release;
its source lives in `../saga2d`. Upgrade it deliberately in `pyproject.toml`
and `uv.lock`, then run this suite. Procedural assets come from `../sagaforge`
as an editable path dependency, so run this suite after changing that library.
The hosted server and website live in `../saga-online`.

## Commands

```bash
uv sync --extra dev
uv run warband --seed 3                          # play (python -m warband works too)
uv run pytest -q                                 # headless suite, about four minutes
uv run python -u tools/fuzz.py --games 2 --monkey 0 --seed 81   # AI matches with invariants + monkey input (needs -u)
uv run python tools/verify.py DIR                # a match through real pyglet events, frames saved to look at
uv run python tools/verify_profile.py DIR        # title card, profile, rating on the results, leave confirmations, a replay: frames to look at
uv run python tools/visual_lint.py --evidence DIR   # visual defects in the art and on every screen; PNGs of what it flags (--screens NAME, --no-images)
uv run python tools/perf.py                      # frame times of a 150-unit battle on the real backend (p95 < 16 ms)
uv run python tools/step_bench.py --repeat 3     # model step times of the same battle without a window, with --profile
uv run python tools/ai_report.py --seeds 3 --decide 0   # difficulties against a scripted opening (the default report is about a minute)
uv run python tools/arena.py ladder --agents hard,pro --seeds 40   # rate agents against each other, in parallel
uv run python tools/arena.py report --seeds 24                     # 1v1, free-for-all and jittered-balance ladders
uv run python tools/tune.py --rounds 12 --games 48                 # hill-climb a ProProfile's numbers
uv run python tools/sim_fingerprint.py --check tools/sim_fingerprint.txt   # the simulation is bit-for-bit unchanged
uv run python tools/music.py render DIR          # WAV, spectrogram and stats per track
uv run python tools/pieces.py refresh            # regenerate the impact, death and wreckage pieces with Stable Audio 3 (needs STABLE_AUDIO_MLX; see docs/warband-pieces.md)
uv run python tools/restyle.py refresh DIR          # painted unit and building sprites: the whole procedure; see ../sagaforge/docs/restyle.md
uv run --extra package python tools/package.py build --version 0.1.0   # standalone build; verify DIR / install too
```

Never time frames under a profiler or tracemalloc; `tools/perf.py` gives the
real breakdown.

## Layout

- `warband/model.py` — the 20 Hz fixed-step simulation (orders, harvesting,
  construction, supply, upgrades, towers, fog, elimination, JSON saves); no
  saga2d dependency, so rules are tested directly. A blow turns, winds up and
  lands; shots are `Projectile`s that land later, stones on the ground they
  were fired at (`docs/unit-motion.md` part 4). `rules.py` holds the tables,
  `races.py` the four races' names, numbers and arts, `path.py` bounded A*,
  `mapgen.py` the five map layouts, their symmetry and audit, `ai.py` a Brain
  per player for the lower difficulties (`PROFILES`) plus `make_brain`, which
  is what every caller should use — Hard and Master are `pro_ai.ProBrain`, not
  a Brain, and Master draws one of two postures (`PRO_VANGUARD`, `PRO_WARDEN`)
  from the map seed and the player's slot — and `DIFFICULTY_ELO`, the measured
  ratings the New game screen shows; `pro_ai.py` a stronger
  `ProBrain` driven by a `ProProfile` of knobs, `arena.py` the ladder that
  rates them (1v1, free-for-all placements, jittered rulebooks,
  Bradley-Terry ratings on the Elo scale), `worker_ai.py`/`worker_knowledge.py` the
  automatic gatherers, `settlement.py`/`production.py` building plans and the
  command card, `scores.py` the local top ten, `profile.py` the player's name,
  results and Glicko-updated rating on the ladder's Elo scale plus the
  standing rule for leaving a match, `replay.py` the recording of a match (the
  start world plus the order log `@recorded` fills in `model.py`), its playback
  and the replay store.
- `warband/textures.py` renders ground, props, buildings and units through
  `sagaforge.render3d`; units have nine frames per facing (stand, a four-step
  walk, a four-phase blow) posed by one `Pose` table. A unit whose subject has a
  painted sheet under `warband/assets/restyled/` (made by `tools/restyle.py`
  through `sagaforge.restyle`; every unit of every race) gets that frame
  recoloured to its team instead, and so does a building whose race has a
  painted sheet (`<race>.buildings.<look>`: `intact`, `active` while it trains
  or researches, `damaged` under half its hit points; `view.building_look`
  picks the look, a missing look shows the intact one). Portraits use the
  painted frame too. `WARBAND_ART=procedural` keeps the renders; a sheet whose
  frames no longer match `FRAMES` or the building types warns and is ignored.
  `view.py` keeps sprites in step (units, buildings, shots in the air with
  their trails) and draws fog, minimap and water; `effects.py` transient
  animations and lingering bodies. `visual_lint.py`
  finds visual defects: in every registered image (empty, clipped, chroma
  fringe, a painted frame off its render, a team recolour that did not take)
  and in what a scene drew on the mock backend with approximate font metrics (text
  over text or off screen, labels narrower than their text, panels over each
  other, sprites drawn over what they stand behind); `tools/visual_lint.py`
  runs it over representative screens at 1280×800 and 1200×680, and checks
  actual native layout metrics when writing evidence. Long runs default to
  `--cpu-percent 25`; native frames are paced at 30 FPS.
- `warband/sound.py`, `voices.py`, `ambience.py`, `instruments.py`, `music.py` —
  synthesised with `sagaforge.synth`; `music.Director` maps moods to tracks; the bank
  composes in a background thread. `combat_sound.py`, `deaths.py` and `wreckage.py` are
  generated instead: weapon-on-material impacts, each race's death and each material's
  building collapse, from pieces committed under `warband/assets/impacts/`, `deaths/` and
  `wreckage/` (Stable Audio 3 through `sagaforge.foley`; `pieces.py` reads them;
  provenance in each folder's manifest, the procedure in `docs/warband-pieces.md`).
- `warband/scene.py`, `title.py`, `tutorial.py`, `icons.py`, `style.py`,
  `score_scene.py`, `profile_scene.py`, `replay_scene.py` — the saga2d scenes
  (the title carries the player's card; `LeaveScene` in `scene.py` is the
  confirmation every way out of an undecided rated match goes through;
  `ReplayScene` plays a recording back). `multiplayer.py` is the LAN/online
  match; its `ONLINE` table registers `warband-v2` with `saga2d.server`.
  `online_ai.py` is the headless AI client that can sit in a room.
- `packaging/package_check.py` — the diagnostics the frozen app runs.
- `docs/` — Early Access criteria and progress (`warband-early-access-*.md`),
  design notes per feature (`unit-motion.md`: why units looked timid, the nine-frame
  rig and its timing, what cinematic motion still needs), the play-together and Windows guides, and
  `docs/hive/` plans for the hive orchestrator (`iteration-plan.toml` is the
  hive's working file at the root).

## Rules

- Game code imports from `saga2d` and `sagaforge` only, never from
  `saga2d.backends`. Framework changes belong in `../saga2d` and need a
  concrete game need.
- Visual changes must be looked at (render a frame with
  `saga2d.testing.render_scene` or `tools/verify.py` and open the PNG). Mock
  tests prove logic, not pixels. The display must be awake for pyglet.
  After a HUD, overlay or art change run `tools/visual_lint.py`; the screens
  it walks are kept clean by `tests/warband/test_visual_lint.py`, and a
  finding there is something to look at, not a number to tune away.
- After changing rules, the AI or scene input, run `tools/fuzz.py`; a bug
  found by fuzz gets a regression test built from the seed's exact tiles and
  unit positions (synthetic geometries kept passing on old code).
- A change that is meant to be only a speed change must leave
  `tools/sim_fingerprint.py --check` alone: lockstep online play needs the
  simulation reproducible to the float bit. A deliberate rules or AI change
  moves it, and the recorded hash is refreshed in the same commit.
- Claims about an AI being stronger are settled by `tools/arena.py`, not by
  watching a match. The same two brains on the same twelve seeds swing
  between seven and eleven wins on the random stream alone, so nothing under
  a few dozen games means anything; see `docs/ai-ladder.md`.
- Check what the player can reach through the UI, not only what the rules
  allow (the build card once offered four of nine buildings while the model
  tests passed).
- Every order a player or brain gives the world goes through a `@recorded`
  World method, never a direct mutation or a helper called on the world from
  outside, or replays stop reproducing the match; `tests/warband/test_replay.py`
  checks playback to the bit on several seeds.
- Tests use the mock backend (`game`/`backend` fixtures from
  `saga2d.testing.fixtures`), public behaviour only; fixtures use
  `save_dir=tmp_path / "saves"` because `data_dir` is its parent.
- Run at most one expensive local job at a time; long CLIs default to
  `--cpu-percent 25`. Evidence you produce goes under `docs/evidence/`
  (git-ignored); the pre-split evidence lives in the archived monorepo.
- Clear exceptions over silent fallbacks. Delete rather than deprecate.
  Commit each working increment.
