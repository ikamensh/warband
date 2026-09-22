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
uv run pytest -q                                 # the fast tier, about 20 s on four workers: after every change (a named file or test runs in one process)
uv run pytest -q --slow                          # both tiers, about 80 s: before pushing rules, AI, replays, art, audio or CI tools; CI runs both on every push
uv run pytest -q --slow -m slow                  # the slow tier alone; -n0 runs any selection in one process
gh run list --limit 6                            # CI after every push: Tests, Native package checks and, on main, the publication (make ci at the stack root)
uv run python -u tools/fuzz.py --games 2 --monkey 0 --seed 81   # AI matches with invariants + monkey input (needs -u)
uv run python tools/verify.py DIR                # a match through real pyglet events, frames saved to look at
uv run python tools/verify_profile.py DIR        # title card, profile, rating on the results, leave confirmations, a replay: frames to look at
uv run python tools/verify_campaign.py DIR       # the campaign's screens rendered by the real backend; uv run warband --mission ID plays one
uv run python tools/verify_deaths.py DIR         # one death per unit category from both sides and a mass-casualty scene, as montages to look at (--zoom 2 for near)
uv run python tools/verify_camp.py DIR           # a creature camp on the map, an army walking up to it, the fight, and each creature's card
uv run python tools/visual_lint.py --evidence DIR   # visual defects in the art and on every screen; PNGs of what it flags (--screens NAME, --no-images)
uv run python tools/perf.py                      # frame times of a 150-unit battle on the real backend (p95 < 16 ms); --scenario four-player|pan-zoom|deaths|restarts, --csv, --gc
uv run python tools/step_bench.py --repeat 3     # model step times of the same battle without a window, with --profile
uv run python tools/step_bench.py --scenario seats --seats 16 --steps 12000   # a real sixteen-seat match, step and brains timed apart
uv run python tools/perf.py --scenario sixteen-player           # frames with sixteen armies on the biggest map that seats them
uv run python tools/sim_bench.py --check tools/sim_bench.txt   # processor time of nine whole arena matches, and their results unchanged
uv run python -m warband.league.fastsim          # compile the simulation with mypyc now (the match-running tools do it on first use)
uv run python tools/ai_report.py --seeds 3 --decide 0   # difficulties against a scripted opening (the default report is about a minute)
uv run python tools/creep_report.py --agents pro,pro --seeds 12   # can the brains clear a creature camp? camps cleared against units fed to one
uv run python tools/arena.py ladder --agents hard,pro --seeds 40   # rate agents against each other, in parallel
uv run python tools/arena.py report --seeds 24                     # 1v1, free-for-all and jittered-balance ladders
uv run python tools/tune.py --rounds 12 --games 48                 # hill-climb a ProProfile's numbers
uv run python tools/evolve.py run --race orc --out DIR             # breed a brain for a race on the ladder; macro, best, trial, export: docs/ai-ladder.md
uv run python tools/battle_bench.py --left marksmanship            # set-piece battles: what a unit behaviour is worth
uv run python tools/sim_fingerprint.py --check tools/sim_fingerprint.txt   # the simulation is bit-for-bit unchanged
uv run python tools/music.py render DIR          # WAV, spectrogram and stats per track
uv run python tools/pieces.py refresh            # regenerate the impact, death and wreckage pieces with Stable Audio 3 (needs STABLE_AUDIO_MLX; see docs/warband-pieces.md)
uv run python tools/restyle.py refresh DIR          # painted unit and building sprites: the whole procedure; see ../sagaforge/docs/restyle.md
uv run --extra package python tools/package.py build --version 0.1.0   # standalone build; verify DIR / install too
uv run python tools/make_icon.py schematic       # the app icon: schematic, then `paint DIR` (image model) and `install CANDIDATE` write warband/assets/icon.png
```

Never time frames under a profiler or tracemalloc; `tools/perf.py` gives the
real breakdown.

## Layout

`warband/` holds `__init__.py`, `__main__.py` (the entry point of
`python -m warband`, the frozen app and `--selftest`), `assets/`,
`assets/constants/` (the tunable numbers as TOML: units, buildings, upgrades,
races, economy, combat, behaviour) and nine
folders, lowest first. `tests/warband/test_layers.py` holds each folder to
what it may import: `sim` nothing but itself; `brains`, `records`, `art` and
`audio` only `sim`; `league` and `online` `sim` and `brains`; `ui` and
`story` anything. A folder's `__init__.py` is its docstring alone: the
authoritative contract hashes those of the package, `sim` and `online`, and
the compiled simulation attaches after they load.

- `warband/sim/` — the rules and the simulation, everything the online
  authority runs. `model.py` is the 20 Hz fixed-step simulation (orders,
  harvesting, construction, supply, upgrades, towers, fog, elimination, JSON
  saves); no saga2d dependency, so rules are tested directly. A blow turns,
  winds up and lands; shots are `Projectile`s that land later, stones on the
   ground they were fired at (`docs/unit-motion.md` part 4). `rules.py` holds
   the tables, `races.py` the four races' names, numbers and arts — both
   loaded once from `warband/assets/constants/` by `sim/config.py`. Edit TOML
   and restart: there is no generation step. Unit files and each race's
   units/buildings use `defaults` plus overrides (`docs/balance.md`) — `path.py`
  bounded A* on a budget that grows with the map, `mapgen.py` the five map
  layouts, the grid of congruent cells that deals two to sixteen seats one each,
  and the audit (`grid`, `dimensions`, `refusal`, `offered`, `sizes_for` and
  `layouts_for` say which size, seat count and layout make a fair map together;
  a map bigger than the shipped three also gets an endless five-tile gold seam
  in the shared ground on Plains, Crossings and Bastion, which `build` treats as
  a wish rather than a fault: `docs/warband-maps.md`).  A gold deposit is a
  building whose `BuildingInfo.mine` is set (`rules.MineInfo`: its trip, its
  places at the face, whether it runs out); a seam's `gold` is nothing at all,
  so what is worth mining is `Building.has_gold` and `KnownMine.spent`,
  `worker_ai.py`/`worker_knowledge.py` the automatic gatherers (placed when
  idle, and the split looked at again every five seconds: `Harvest.placed`
  marks the policy's own jobs, an ordered harvest stays its player's, and a
  worker its player lately had in hand is left alone the longer the further
  from a depot it stands, `manual_hold`: `docs/worker-hands-off.md`),
  `settlement.py` building plans.  `camps.py` holds the neutral creature camps:
  a lair with its guards posted round it, which rouse as one, leash to the camp
  and put themselves back together when left alone, and which mapgen places
  beside every *contested* deposit (a third mine or the seam, never a seat's own
  mine and never its natural).  They belong to the wilds, the one seat past
  `World.seats` (`Player.neutral`): everything that means "a seat in the match"
  counts `world.seats`, never `len(world.players)`, and the wilds are out of
  victory, elimination, fog, supply, the league's tallies and the authority's
  own seats.  `docs/warband-monsters.md`. `_native.c` holds C twins of a few loops of
  the compiled simulation (`docs/fast-simulation.md`).
- `warband/brains/` — the computer players. `ai.py` holds a Brain per player
  for the lower difficulties (`PROFILES`) plus `make_brain`, which is what
  every caller should use — Hard and Master are `pro_ai.ProBrain`, not a
  Brain, and Master draws one of three postures (`PRO_VANGUARD`,
  `PRO_WARDEN`, the tower rush `PRO_RUSH`) from the map seed and the player's
  slot — and `DIFFICULTY_ELO`, the measured ratings the New game screen
  shows; `pro_ai.py` the stronger `ProBrain` driven by a `ProProfile` of knobs,
  and `RaceBrain`, which plays a posture of its race's own: Grandmaster, from
  `bred.py`, the table `tools/evolve.py export` writes (bred again, never
  edited by hand).
- `warband/league/` — what plays many matches to measure the game.
  `arena.py` is the ladder that rates brains (1v1, free-for-all placements,
  jittered rulebooks, Bradley-Terry ratings on the Elo scale); `balance.py`
  reads the balance league, `archetypes.py` holds its postures and
  `telemetry.py` its tallies; `evolve.py` is the genetic search that breeds
  brains (genes grouped by behaviour, judged by ladder matches on fresh seeds;
  `docs/ai-ladder.md`); `fastsim.py` compiles `sim` and `brains` with
  mypyc for the tools that play many matches.
- `warband/records/` — what is kept of a player's matches: `profile.py` the
  player's name, results and Glicko-updated rating on the ladder's Elo scale
  plus the standing rule for leaving a match, `scores.py` the local top ten,
  `replay.py` the recording of a match (the start world plus the order log
  `@recorded` fills in `model.py`), its playback and the replay store.
- `warband/online/` — `authority.py` holds the authoritative match, and its
  `ONLINE` table registers `warband-v2` with `saga2d.server` (the server
  loads `warband.online.authority:ONLINE`); `online_ai.py` is the headless AI
  client that can sit in a room.
- `warband/art/` — `textures.py` renders ground, props, buildings and units
  through `sagaforge.render3d`; units have nine frames per facing (stand, a
  four-step walk, a four-phase blow) posed by one `Pose` table. A unit whose
  subject has a painted sheet under `warband/assets/restyled/` (made by
  `tools/restyle.py` through `sagaforge.restyle`; every unit of every race)
  gets that frame recoloured to its team instead, and so does a building
  whose race has a painted sheet (`<race>.buildings.<look>`: `intact`,
  `active` while it trains or researches, `damaged` under half its hit
  points, and while it goes up `founded` for the first half and `raised`
  for the second; `view.building_look` picks the look, a missing look
  shows the intact one, a missing site look the plain site). `ambience.py`
  draws a site's builder hammering at its corner, with dust and sparks.
  The gold mine is nobody's and never recoloured: four of its stand-ins are painted (`mine.<look>`, `tools/restyle.py --mines`), `active`
  while a peasant works inside. Portraits use the painted frame too.
  `WARBAND_ART=procedural` keeps the renders; a sheet whose frames no longer
  match `FRAMES` or the building types warns and is ignored. `effects.py`
  holds transient animations and lingering bodies, `ambience.py` the life
  around visible buildings, `production.py` the command card's portraits and
  emblems. `visual_lint.py` finds visual defects: in every registered image
  (empty, clipped, chroma fringe, a painted frame off its render, a team
  recolour that did not take) and in what a scene drew on the mock backend
  with approximate font metrics (text over text or off screen, labels
  narrower than their text, panels over each other, sprites drawn over what
  they stand behind); `tools/visual_lint.py` runs it over representative
  screens at 1280×800 and 1200×680, and checks actual native layout metrics
  when writing evidence. Long runs default to `--cpu-percent 25`; native
  frames are paced at 30 FPS.
- `warband/audio/` — `sound.py`, `voices.py`, `instruments.py` and
  `music.py` are synthesised with `sagaforge.synth`; `music.Director` maps
  moods to tracks; the bank composes in a background thread.
  `combat_sound.py`, `deaths.py` and `wreckage.py` are generated instead:
  weapon-on-material impacts, each race's death and each material's building
  collapse, from pieces committed under `warband/assets/impacts/`, `deaths/`
  and `wreckage/` (Stable Audio 3 through `sagaforge.foley`; `pieces.py` reads
  them; provenance in each folder's manifest, the procedure in
  `docs/warband-pieces.md`). One impact family is synthesised in `sound.py`
  instead: a healer's blow lands as `mote_<material>`, light rather than steel.
- `warband/ui/` — the saga2d scenes. `scene.py` is the match with its HUD
  and command card, pause, help and results (`LeaveScene` is the
  confirmation every way out of an undecided rated match goes through);
  `view.py` keeps sprites in step (units, buildings, shots in the air with
  their trails; a shot's look is its striker's, `SHOT_LOOKS`, so the model's
  `arrow` from a healer is drawn as a mote of light and a new look is no
  rules change) and draws fog, minimap and water; ground out of sight shows
  what the player last saw there (`view.Sighting` per building, saved as the
  scene's `seen`; trees and the minimap's terrain follow the model's own
  per-player memory, `World.worker_knowledge`), and the selection panel reads
  the sighting, never a rival's live building. `title.py` holds the title
  (which carries the player's card) and New game, `multiplayer.py` the
  LAN/online scenes, `profile_scene.py`, `score_scene.py` and
  `replay_scene.py` (`ReplayScene` plays a recording back) their screens,
  `tutorial.py` the first match's objectives, `style.py` and `icons.py` the
  look of the HUD. `version.py` names the build that is running — a published
  build's version and commit, or a checkout's commit — which the title screen,
  the pause panel and `--version` show, so a report or a screenshot says which
  build it came from. `tech.py` reads what needs what from the rules the other
  way round: what a catalogue item still lacks and whether it is on its way
  (the card greys out and refuses what nobody is making), and the codex's tech
  tree. `controls.py` holds the three control schemes (Classic,
  Grid, Modal; `docs/controls.md`): a card command has a letter and a slot,
  and the scheme picks which is its key; the scene resolves a key as a
  control group, a Ctrl chord, the card's command, then the scheme's global
  keys.
- `warband/story/` — the campaign. `campaign.py` is its engine: speakers,
  lines and choices, objectives and triggers, `Run` (a mission in play, saved
  beside the world), `Progress`/`ProgressStore` (the small cross-version
  progress file); the rules for keeping it playable across versions are in
  `docs/warband-campaign.md`. `missions.py` is the content (The Thornwood
  War, six missions), `dialog.py` the dialogue overlay, `mission_scene.py` a
  mission as a match with its result and loader, `campaign_scene.py` the
  campaign screen. `World.scripted` worlds never declare a winner or
  surrender: the mission decides.
- `packaging/package_check.py` — the diagnostics the frozen app runs.
  `warband/assets/icon.png` is the picture the builds carry and the running
  game wears in the Dock and the taskbar (`Game(icon=...)`; the engine shapes
  it per platform); `packaging/icon-schematic.png` is the composition
  `tools/make_icon.py` draws and the image model painted it from.
- `docs/` — Early Access criteria and progress (`warband-early-access-*.md`),
  design notes per feature (`unit-motion.md`: why units looked timid, the nine-frame
  rig and its timing, what cinematic motion still needs), the play-together and Windows guides, and
  `docs/hive/` plans for the hive orchestrator (`iteration-plan.toml` is the
  hive's working file at the root).

New code goes in the lowest folder whose imports it needs: a rule, or
anything the server must run, in `sim`; a computer player's decision in
`brains`; what a player keeps between matches in `records`; a tool's engine
that plays many matches in `league`; the server's game in `online`; images
in `art` and sounds in `audio`; scenes and the HUD in `ui`; the campaign in
`story`. A new folder, or a new row in `test_layers.py`'s table, is a design
decision of its own.

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
  moves it, and the recorded hash is refreshed in the same commit (and
  `tools/sim_bench.txt` with it). Both records are macOS's: glibc and the
  Windows runtime round some sines, cosines and arctangents differently in the
  last bit, so the same source hashes differently there.
- The tools that play many matches (`arena`, `tune`, `balance_report`,
  `ai_report`, `race_report`, `sim_bench`, `step_bench`) run the simulation
  compiled by mypyc from its own source (`warband/league/fastsim.py`, built on first
  use under `build/fastsim/`, `WARBAND_INTERPRETED=1` to opt out), about ten
  times faster; the game, the online authority and the tests run the source.
  The compiler trusts the annotations of `fastsim.MODULES`: keep mypy over them
  clean, because a value of the wrong type is a `TypeError` in a compiled run
  where the interpreter carried on. Their module constants are `Final` and are
  never bound again (compiled code inlines them; tables are patched in place,
  as the rulebook variants do). A few loops have a C twin in `warband/sim/_native.c`
  (its opening comment lists them): the Python stays the reference, a change
  goes into both, and `tests/warband/test_fastsim.py` holds them to the same
  answers on random inputs and plays the fingerprint compiled. What the
  compiler rewards and punishes is in `docs/fast-simulation.md`.
- A camp is only a feature if every side can use one. `tools/creep_report.py`
  is the gate: lairs cleared per match against units lost to the wilds per lair
  (`trickle`). A brain that feeds soldiers into a camp a few at a time is
  pouring them into a sink, because a camp mends its wounded and calls its dead
  back out of the den; that failure is what the number is for.
- Claims about an AI being stronger are settled by `tools/arena.py`, not by
  watching a match. The same two brains on the same twelve seeds swing
  between seven and eleven wins on the random stream alone, so nothing under
  a few dozen games means anything; see `docs/ai-ladder.md`.
- A push is not done until its CI is green: run `gh run list` (or `make ci` at
  the stack root) after pushing and fix or revert a red run before moving on.
  `tests/warband/test_startup.py` starts the game on the windows players
  actually get (clipped under a taskbar, maximised, a 4K desktop, fullscreen
  toggled between matches) and the packaged native check starts a match
  after a resize; a report from a real desktop adds its window to that
  matrix before the fix.
- Check what the player can reach through the UI, not only what the rules
  allow (the build card once offered four of nine buildings while the model
  tests passed).
- Every order a player or brain gives the world goes through a `@recorded`
  World method, never a direct mutation or a helper called on the world from
  outside, or replays stop reproducing the match; `tests/warband/test_replay.py`
  checks playback to the bit on several seeds.
- A World order checks all it has to check before it changes anything and
  refuses with a `RuleError`: the online authority gives orders straight to
  the running world, so a half-applied group order would be a match nobody
  asked for. A new order, or a new way to refuse one, gets a row in
  `tests/warband/test_order_atomicity.py`. What a player can pile up is
  bounded (`rules.MAX_PLANS`, `MAX_QUEUED_ORDERS`). The HUD gives orders
  through `GameScene.attempt`, which turns a refusal into the status line's
  warning; never call `order` from a button or a key.
- What the authority sends a seat (`WarbandMatch.snapshot`) is the match as
  that seat may know it, not the save: all of its own; of the rest only what
  it sees now (strangers without orders, route or work), ground and mines out
  of sight as it remembers them, and the news it saw, its own affairs and the
  public news (`PRIVATE_EVENTS`, `PUBLIC_EVENTS`), for five seconds. Never the
  random stream or another seat's memory, purse, research or plans. The
  checkpoint is the whole match. A test about one seat's state reads that
  seat's own snapshot.
- Tests use the mock backend (`game`/`backend` fixtures from
  `saga2d.testing.fixtures`), public behaviour only; fixtures use
  `save_dir=tmp_path / "saves"` because `data_dir` is its parent. What a
  test needs to read, the view or scene offers as a property; a test that
  still reads a private member says why beside it (a staged state, a brain's
  own question, a C twin held to its loop, what the engine does not offer).
  `tests/warband/test_properties.py` states properties over generated inputs
  (paths, saves, refused orders, replays) with Hypothesis.
- The suite has two tiers. A test goes in the fast tier unless it cannot:
  each fast test takes under half a second on the Mac, and CI fails one whose
  setup, call or teardown takes over 3 s (`--budget`; four workers on a runner
  run a test about four times slower). A test that needs a whole match or minutes of one, a real
  server, socket or process, every race's art or every window size is marked
  `@pytest.mark.slow`, and its docstring (or its module's) says why: collection
  refuses one that does not. A matrix keeps representative cases in the fast
  tier (one race per unit type, the shortest window) and the rest in the slow
  one. A test that waits for a state ticks in tenths (`game.tick(0.1)`), not in
  sixtieths, unless the frames themselves are what it checks. What never
  changes is built once per session (painted ground: `ground_painted_once`
  in `tests/conftest.py`); nothing mutable is shared between tests.
- Run at most one expensive local job at a time; long CLIs default to
  `--cpu-percent 25`. Iterate verification in a temporary directory; retain only
  useful final output in `~/saga/evidence/warband/<topic>/`, replacing older output
  for that topic. Pass output paths explicitly, regardless of older CLI defaults.
  Follow `~/saga/AGENTS.md` for retention and worktree cleanup.
- Clear exceptions over silent fallbacks. Delete rather than deprecate.
  Commit each working increment.
