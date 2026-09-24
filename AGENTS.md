# Warband — agent notes

A Warcraft 2-style real-time strategy game, the Saga stack's playable release
(`~/saga/`, see `../AGENTS.md`). Saga2D is a pinned PyPI release, its source in
`../saga2d`: upgrade it deliberately in `pyproject.toml` and `uv.lock`, then run
this suite. Procedural assets come from `../sagaforge`, an editable path
dependency, so run this suite after changing that library too. The hosted
server and website live in `../saga-online`.

## Commands

```bash
uv sync --extra dev
uv run warband --seed 3                          # play (python -m warband works too; --mission ID plays a campaign mission)
uv run pytest -q                                 # the fast tier, about 20 s on four workers: after every change (-n0 runs in one process)
uv run pytest -q --slow                          # both tiers, about 80 s: before pushing rules, AI, replays, art, audio or CI tools; CI runs both on every push
gh run list --limit 6                            # CI after every push: Tests, Native package checks and, on main, the publication
uv run python -u tools/fuzz.py --games 2 --monkey 0 --seed 81   # AI matches with invariants + monkey input (needs -u)
uv run python tools/sim_fingerprint.py --check tools/sim_fingerprint.txt   # the simulation is bit-for-bit unchanged
uv run python tools/sim_bench.py --check tools/sim_bench.txt   # processor time of nine arena matches, and their results unchanged
uv run python tools/verify.py DIR                # a match through real pyglet events, frames saved to look at
uv run python tools/visual_lint.py --evidence DIR   # visual defects in the art and on every screen, PNGs of what it flags
uv run python tools/perf.py                      # frame times of a 150-unit battle on the real backend (p95 < 16 ms); never time under a profiler
uv run python tools/step_bench.py --repeat 3     # model step times without a window
uv run python tools/arena.py ladder --agents hard,pro --seeds 40   # rate agents against each other, in parallel
uv run --extra package python tools/package.py build --version 0.1.0   # standalone build; verify DIR / install too
```

Every other tool's module docstring says what it is for: `verify_*` for other
screens and effects, reports (`ai_report`, `creep_report`, `race_report`,
`balance_report`, `map_report`, `battle_bench`), AI search (`tune`, `evolve`),
asset makers (`music`, `pieces`, `restyle`, `make_icon`) and `soak`.

## Layout

`warband/` holds the entry point `__main__.py` (`python -m warband`, the frozen
app, `--selftest`), `assets/` (the tunable numbers as TOML in
`assets/constants/`: edit and restart, there is no generation step;
`docs/balance.md`) and nine folders, lowest first.
`tests/warband/test_layers.py` holds each folder to what it may import: `sim`
nothing but itself; `brains`, `records`, `art` and `audio` only `sim`; `league`
and `online` `sim` and `brains`; `ui` and `story` anything. A folder's
`__init__.py` is its docstring alone: the authoritative contract hashes those
of the package, `sim` and `online`.

- `sim/` — the rules and the 20 Hz fixed-step simulation, everything the
  online authority runs, with no saga2d dependency. `model.py` (the World:
  orders, harvesting, construction, fog, saves), `rules.py` and `races.py`
  (tables that `config.py` loads from TOML), `path.py`, `mapgen.py` (layouts,
  a cell per seat, the fairness audit, the endless gold seam, the ley rifts
  aether is drawn from: `docs/warband-maps.md`; aether itself:
  `docs/warband-magic.md`), `worker_ai.py` (the automatic gatherers:
  `docs/worker-hands-off.md`), `settlement.py`, `camps.py` (neutral creature
  camps: `docs/warband-monsters.md`), `_native.c` (C twins of a few loops).
- `brains/` — the computer players (`docs/ai-ladder.md`). Build one with
  `ai.make_brain`: Hard and Master are `pro_ai.ProBrain`, not a `Brain`, and
  Grandmaster is a `RaceBrain` playing `bred.py`, the table
  `tools/evolve.py export` writes (never edited by hand). `DIFFICULTY_ELO`
  holds the measured ratings New game shows.
- `league/` — what plays many matches: `arena.py` (the rating ladder),
  `balance.py`, `evolve.py` (the genetic search), `fastsim.py` (mypyc).
- `records/` — `profile.py` (the player's rating and the rule for leaving a
  match), `scores.py`, `replay.py` (the start world plus the `@recorded` order
  log).
- `online/` — `authority.py`, the authoritative match; its `ONLINE` table
  registers `warband-v2` (the server loads `warband.online.authority:ONLINE`);
  `online_ai.py`, a headless AI client that can sit in a room.
- `art/` — `textures.py` renders through `sagaforge.render3d` (nine frames per
  facing from one `Pose` table); painted sheets under `assets/restyled/`
  (`tools/restyle.py`) replace frames, recoloured per team
  (`docs/warband-art.md`). `WARBAND_ART=procedural` keeps the renders; a sheet
  that no longer matches `FRAMES` or the building types warns and is ignored,
  but for the buildings the sheets were made without (`textures.UNPAINTED`,
  the Aether Vault), which are drawn low-poly beside them.
  `effects.py`, `ambience.py` and `production.py` hold transient effects, the
  life around buildings and the card's portraits; `visual_lint.py` finds
  visual defects.
- `audio/` — `sound.py`, `voices.py` and `music.py` synthesise with
  `sagaforge.synth` (`music.Director` maps moods to tracks); impacts, deaths
  and collapses (`combat_sound.py`, `deaths.py`, `wreckage.py`) play generated
  pieces committed under `assets/` (`docs/warband-pieces.md`).
- `ui/` — the saga2d scenes: `scene.py` (the match, HUD, command card),
  `view.py` (sprites, shots, fog, minimap), `title.py`, `multiplayer.py`,
  `controls.py` (three control schemes: `docs/controls.md`), `tech.py` (what a
  catalogue item still lacks; the codex's tech tree), `version.py` (which build
  is running), `style.py` and `icons.py` (the HUD's look) and the profile,
  score, replay and tutorial screens.
- `story/` — the campaign: `campaign.py` (the engine, `Run`, the progress
  file), `missions.py` (the content) and their scenes; keeping it playable
  across versions: `docs/warband-campaign.md`.
- `packaging/package_check.py` — the frozen app's diagnostics;
  `warband/assets/icon.png` is the app icon (`tools/make_icon.py`).
- `docs/` — a design note per feature, Early Access criteria and progress, the
  play-together and Windows guides; `docs/hive/` and `iteration-plan.toml` are
  the hive orchestrator's.

New code goes in the lowest folder whose imports it needs: a rule, or anything
the server must run, in `sim`; a computer player's decision in `brains`; what a
player keeps between matches in `records`; a tool's engine that plays many
matches in `league`; the server's game in `online`; images in `art` and sounds
in `audio`; scenes and the HUD in `ui`; the campaign in `story`. A new folder,
or a new row in `test_layers.py`'s table, is a design decision of its own. How
a feature works belongs in its `docs/` note or module docstring; this file
keeps where code goes and the rules below.

## Rules

- Game code imports from `saga2d` and `sagaforge`, never from
  `saga2d.backends`. Framework changes belong in `../saga2d` and need a
  concrete game need.
- Visual changes must be looked at: render a frame with
  `saga2d.testing.render_scene` or `tools/verify.py` and open the PNG (pyglet
  needs an awake display: `caffeinate -u`). Mock tests prove logic, not pixels.
  After a HUD, overlay or art change run `tools/visual_lint.py`; the screens it
  walks are kept clean by `tests/warband/test_visual_lint.py`, and a finding
  there is something to look at, not a number to tune away.
- Check what the player can reach through the UI, not only what the rules
  allow (the build card once offered four of nine buildings while the model
  tests passed).
- After changing rules, the AI or scene input, run `tools/fuzz.py`; a bug
  found by fuzz gets a regression test built from the seed's exact tiles and
  unit positions (synthetic geometries kept passing on old code).
- A change meant only for speed must leave `tools/sim_fingerprint.py --check`
  alone: lockstep online play needs the simulation reproducible to the float
  bit. A deliberate rules or AI change moves it, and the recorded hash is
  refreshed in the same commit, with `tools/sim_bench.txt`. Both records are
  macOS's: glibc and Windows round some trigonometry differently in the last
  bit.
- Every order a player or brain gives the world goes through a `@recorded`
  World method, never a direct mutation or a helper called on the world from
  outside, or replays stop reproducing the match; `tests/warband/test_replay.py`
  checks playback to the bit.
- A World order checks all it has to check before it changes anything and
  refuses with a `RuleError`: the online authority gives orders straight to the
  running world, so a half-applied group order would be a match nobody asked
  for. A new order, or a new way to refuse one, gets a row in
  `tests/warband/test_order_atomicity.py`. What a player can pile up is bounded
  (`rules.MAX_PLANS`, `MAX_QUEUED_ORDERS`). The HUD gives orders through
  `GameScene.attempt`, which turns a refusal into the status line's warning;
  never call `order` from a button or a key.
- What the authority sends a seat (`WarbandMatch.snapshot`) is the match as
  that seat may know it, not the save: all of its own; of the rest only what it
  sees now (strangers without orders, route or work), ground and mines out of
  sight as it remembers them, and for five seconds the news it saw: its own
  affairs and the public news (`PRIVATE_EVENTS`, `PUBLIC_EVENTS`). Never the
  random stream or another seat's memory, purse, research or plans. The
  checkpoint is the whole match. A test about one seat's state reads that
  seat's own snapshot. The HUD is as honest: out of sight it shows the
  player's last sighting (`view.Sighting`), never a rival's live building.
- The neutral creatures are one player past `World.seats` (`Player.neutral`):
  whatever means "a seat in the match" counts `world.seats`, never
  `len(world.players)`, and the wilds stay out of victory, elimination, fog,
  supply, the league's tallies and the authority's seats. A seam's `gold` is
  zero and always was: ask `has_gold` (of the `Building`, or of the
  `KnownMine` a player remembers) what is worth mining.
- A unit type with `flying = true` is in the air (`docs/unit-motion.md` part
  10): never routed (`_plan` refuses it), no body on the ground (flyers keep
  their room from each other alone), and whether a blow can land is
  `World.can_strike`, the one answer orders, the model and the brains ask. The
  flying machines are drawn by the render, not painted
  (`textures.PROCEDURAL_UNITS`).
- A shot's look is its striker's (`view.SHOT_LOOKS`), so a new look is no rules
  change. Every way out of an undecided rated match goes through `LeaveScene`.
  A `World.scripted` world never declares a winner or surrenders: the mission
  decides.
- The tools that play many matches (`arena`, `tune`, `balance_report`,
  `ai_report`, `race_report`, `sim_bench`, `step_bench`) run the simulation
  compiled by mypyc (`league/fastsim.py`, built on first use under
  `build/fastsim/`; `WARBAND_INTERPRETED=1` opts out), about ten times faster;
  the game, the online authority and the tests run the source. Keep mypy clean
  over `fastsim.MODULES`: a value of the wrong type is a `TypeError` in a
  compiled run where the interpreter carried on. Their module constants are
  `Final` and never bound again (tables are patched in place). They call no
  bare `sum()`: floats add in `model.plain_sum`, integers in `model.int_sum`
  (`tests/warband/test_sums.py`). A C twin in
  `sim/_native.c` (its opening comment lists them) changes with its Python
  reference, and `tests/warband/test_fastsim.py` holds them to the same
  answers. `docs/fast-simulation.md` says what the compiler rewards and
  punishes.
- Claims about an AI being stronger are settled by `tools/arena.py`, not by
  watching a match: the same two brains on the same twelve seeds swing between
  seven and eleven wins on the random stream alone, so nothing under a few
  dozen games means anything. A camp is a feature only if every side can clear
  one; `tools/creep_report.py` is the gate (a brain that feeds soldiers in a
  few at a time pours them into a sink: a camp mends its wounded and calls its
  dead back).
- Tests use the mock backend (`game`/`backend` fixtures from
  `saga2d.testing.fixtures`), public behaviour only; fixtures use
  `save_dir=tmp_path / "saves"` because `data_dir` is its parent. What a test
  needs to read, the view or scene offers as a property; a test that still
  reads a private member says why beside it. `tests/warband/test_properties.py`
  states properties over generated inputs with Hypothesis.
- The suite has two tiers. A test goes in the fast tier unless it cannot: it
  takes under half a second on the Mac, and CI fails any setup, call or
  teardown over 3 s (`--budget`; runners are about four times slower). A test
  that needs a whole match, a real server, socket or process, every race's art
  or every window size is `@pytest.mark.slow`, and its docstring (or its
  module's) says why: collection refuses one that does not. A matrix keeps
  representative cases fast and the rest slow. A test that waits for a state
  ticks in tenths (`game.tick(0.1)`) unless the frames are what it checks.
  What never changes is built once per session (`tests/conftest.py`); nothing
  mutable is shared between tests.
- A push is done when its CI is green (`make ci` at the stack root).
  `tests/warband/test_startup.py` starts the game on the windows players
  actually get (clipped under a taskbar, maximised, 4K, fullscreen toggled
  between matches) and the packaged native check starts a match after a
  resize; a report from a real desktop adds its window to that matrix before
  the fix.
- Retain verification output only in `~/saga/evidence/warband/<topic>/`, under
  the stack's retention rules (`../AGENTS.md`), and pass output paths to tools
  explicitly. One expensive local job at a time; long CLIs default to
  `--cpu-percent 25`.
- `backlog_intake.txt` is Ilya's inbox of requests, edited and committed by
  Ilya at any time. A change to it in a checkout is Ilya's, not another
  session's work in progress, and it never holds up other work, a merge or a
  push. Never revert, stash or rewrite that text; when a fast-forward or merge
  needs the file clean, commit the edit as it stands.
