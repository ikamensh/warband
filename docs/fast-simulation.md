# The fast simulation

The tools that play many matches (ladders, leagues, tuning, the balance and AI
reports) spend nearly all their time in `World.step` and the brains. They run
the simulation compiled: `warband/league/fastsim.py` builds the simulation modules
with mypyc, and a few of their loops have C twins in `warband/sim/_native.c`. A
match costs about a tenth of what it did and plays out exactly as before, to
the float bit. The game runs it too (below); the online authority and the
tests run the source, and CI runs the tests on the compiled simulation as well.

## What it bought

`tools/sim_bench.py` plays nine arena matches (Master mirrors, Hard and Medium
pairings, a four-player free-for-all; 78 840 steps). Processor time on an
Apple-silicon Mac, the original source and the compiled simulation run in
alternation so that both meet the same load:

| | nine matches | per step |
|---|---|---|
| source before this work | 34.3–36.9 s | 0.44 ms |
| compiled | 3.2–3.6 s | 0.041 ms |

The three pairs measured 10.3×, 10.9× and 10.7×. A parallel ladder of six
matches on two workers takes 1 s instead of 8, process start-up included. The
digest of the nine results is the same in both runs, and so is
`tools/sim_fingerprint.py`'s.

## Why not numpy

The first idea was to hold the units in numpy arrays and update them in bulk.
It does not fit this simulation:

- A match has 30 to 100 units. A numpy call costs about a microsecond before it
  does anything, which is the whole cost of most per-unit updates here.
  Vectorising pays at thousands of elements, not dozens.
- A unit's update is a state machine (orders, wind-ups, paths, trips to the
  mine, construction), not one formula applied to every unit.
- Units update one after another, and each sees what the units before it did
  in the same step: separation, target choice and blocking all depend on it.
  A bulk update computes every unit from the state at the start of the step,
  which is a different simulation. Lockstep online play and replays need this
  one reproduced exactly.
- numpy's reductions (pairwise summation, SIMD) round differently from the
  loops they would replace.

Compiling the same source keeps every one of those properties.

## How it stays exact

- mypyc compiles the source as written: the same operations in the same order,
  with Python's integer and float semantics. It trusts the annotations, so a
  wrong one is a `TypeError` in a compiled run; mypy over `fastsim.MODULES`
  stays clean.
- `math.hypot` is the one library function the compiled code does not call.
  `model.hypot` is CPython 3.13's own algorithm written out, so that compiled
  modules call it on unboxed floats. Where the port's arithmetic would not be
  exact (zeros, infinities, NaN, and very large, very small or very unequal
  magnitudes) it hands over to `math.hypot`. The source keeps calling
  `math.hypot`, and the tests compare the port with it on three million pairs,
  specials included.
- The built-in `sum` over floats is not the same operation compiled: since
  Python 3.12 CPython adds floats with compensated (Neumaier) summation, and
  mypyc turns `sum(generator)` into plain additions, so the two part in the
  last bit, and a decision can go either way on it (a marching line's middle,
  WB-050; a computer player's choice in fuzz match 84). So no module of
  `MODULES` calls `sum`: floats add in `model.plain_sum`, a plain loop, and
  integers in `model.int_sum`, whose annotation keeps floats out;
  `tests/warband/test_sums.py` refuses a bare `sum(`.
- The C twins perform the same floating-point operations in the same order
  (built with `-ffp-contract=off`, so no multiply-add is fused), relax
  neighbours and pop the frontier in the same order, and draw the same random
  numbers. The Python is the reference; `tests/warband/test_fastsim.py` holds
  the two to the same answers on random inputs.
- Checks: the fingerprint, compiled and from source on the same machine (in
  the test); the bench's digest of nine whole results
  (`--check tools/sim_bench.txt`); the twin tests.
- Exact means the same bits as the source *on the same platform*. The
  simulation calls libm's `sin`, `cos` and `atan2`, and Apple's libm, glibc
  and the Windows runtime round a fraction of a percent of arguments
  differently in the last bit (in two fingerprint matches, about 0.6% of the
  distinct sines and cosines differ between macOS and Linux). So the source
  itself hashes differently on each platform, and the recorded fingerprint and
  bench digest are macOS's. The test compares compiled with source wherever it
  runs: macOS, Linux and Windows in CI.
- A build is filed under a hash of its sources, so an edited source is never
  run as an old build. Worker processes take their parent's build and refuse
  one made from other sources.

## The game

Late in a large match the interpreted step cost the render thread about 7 ms
of every frame (`~/saga/evidence/warband/large-map-frame-budget/`), so the
game runs the simulation compiled too. `warband.__main__.main` calls
`fastsim.activate_for_game()` before anything imports the simulation:

- **A checkout** attaches the build of its sources, compiling it on the first
  launch after they change: 45 s of processor time, 49 s at a load of 20 and
  three minutes under a load of 78 from parallel sessions. Most pulls change
  it (49 of 125 commits in five days touched a compiled module, `config.py`,
  `_native.c` or a balance table). The wait is not moved to the background,
  because a process cannot swap the simulation it has imported: the first
  match after a pull, the one a player starts to see what changed, would run
  from source. Compiling in parallel does not shorten it either: the modules
  are one extension, one 19 MB C file, and setuptools compiles an extension's
  files one after another (mypyc's `multi_file` with `-j 10` measured the
  same).
- **A machine that cannot compile** (plain `uv sync` without the `dev` extra
  has no mypyc; a Mac without Xcode's command line tools has no compiler)
  prints one line naming what is missing and runs the source. The build
  probes the compiler on a one-line C file before mypyc spends its minute.
  `WARBAND_INTERPRETED=1` runs the source and says so.
- **A frozen app** carries the build it was frozen with: players have no
  compiler. `tools/package.py` (and `tools/ci_package.py` on each native CI
  runner, whose regression suite has just compiled it) copies the build into
  `warband/assets/fastsim/` for the freeze and removes it after; it is
  git-ignored. The package ships its assets folder whole, and PyInstaller
  reclassifies the extension modules in it as binaries, so they land in
  `Contents/Frameworks` and are signed. The app has no sources to hash, so it
  checks the build's balance tables against its own instead. Both packaged
  self-checks report `compiled_simulation`, and `ci_package.py validate`
  refuses a package whose executables ran the source.
- **Replays and saves** reproduce as before: compiled and source agree to the
  bit on one OS, so a replay recorded by either plays on either there. Across
  OSes they never did (above).

Running the suite compiled (`pytest --compiled`) found three crashes that the
tools never met, because only the game's own code hands the simulation such
values: a save with a queued order (`vars()` of a compiled dataclass; now
`model.field_values`), every online snapshot (a rival's hidden alarm arrives
as `None` in a `float` field) and the online client's world refresh
(`__dict__.update`; now through `__getstate__`, which both kinds of object
have). A LAN host runs the authority inside the game, so its event
serialisation had the same `vars()`. A test that inspects the source itself
is marked `source_only` and is left out of the compiled run.

## What the compiler rewards

These rules were learned by profiling the compiled simulation with macOS
`sample`. The Python-level profilers mislead once the code is compiled.

- **Constants are `Final`.** A plain module global is a dictionary lookup and
  an unbox at every read. A `Final` number is inlined, even across modules, and
  a `Final` table is a static. Worth 2% on its own.
- **Narrow an `int | None` before comparing it.** `b.player == player` goes
  through Python's `==`. `b.player is not None and b.player == player` compares
  two machine integers. A building's owner is optional (a gold mine has none).
- **Don't allocate in hot loops.** Every tuple or float that escapes is an
  allocation, and on Python 3.13 under macOS each allocation also costs a
  thread-local lookup. Compare a `(threat, distance)` key part by part instead
  of building it, and keep containers alive between steps (one bucket list per
  tile) rather than making new ones.
- **Calls into Python objects box their arguments.** A C-extension function,
  a module attribute (`_native.any_lit`) and `math.atan2` are all generic
  calls. Look a function up once into a `Final` when it is called dozens of
  times a step. `math.sin`, `cos`, `sqrt` and `math.pi` are native already.
- **Walking a dict costs a `PyDict_Next` per item**, about 9% of the time now,
  mostly brains asking `player_units` and `player_buildings` again and again.
- A generator's variables share one environment: a name reused with two types
  in one generator breaks the C build.
- `vars()` and `__dict__` do not work on compiled classes, a dataclass's
  `__init__` stays interpreted, and an import inside a function costs a lookup
  at every call.

## Where the time goes now

The step is about three quarters of a compiled match, and the brains a little
under a fifth. The interpreted match loop, telemetry included, is a few percent.
Inside the step, harvesting and worker routing take about 15%, vision with each
player's map memory 12%, separation 9% and path following 8%. The largest
single costs are the walk over the unit buckets (`units_near`, 5%) and dict
iteration. If more speed is wanted, the next step is per-player unit and
building lists kept in the dicts' order. That is a structural change, and it
has to be kept in step with every place that adds, removes or re-owns an
entity.

## The server

The contract the online server is checked against
(`tools/ci_compatibility.py`) hashes the simulation's source and balance TOMLs, so a speed change
like this one moves it and needs a server rollout even though every result is
the same. `fastsim.py` and `_native` stay out of the authority's import
closure: the server runs the source.

Balance TOMLs are read once per run, not compiled into Python source. The
compiled build key includes the loader and its exact startup inputs; the build
keeps those inputs in `constants.json`. `attach` installs that snapshot before
loading any compiled rule tables. Spawned workers therefore keep their parent's
balance even after the authoring files change. Source-code changes still cause
an inherited build to be refused.
