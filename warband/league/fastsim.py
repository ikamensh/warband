"""The simulation compiled to C by mypyc, for the game and the tools that play many matches.

    uv run python -m warband.league.fastsim        # build it now (the tools build it on first use) and say where

The modules in :data:`MODULES` (the world, its pathfinding and worker policy,
the map generator, the rule tables and both kinds of brain) are compiled from
their own source, so a compiled match is the interpreted match: mypyc keeps
Python's integer and float semantics and every operation's order, and ``tools/sim_fingerprint.py``
checks the two to the bit (``tests/warband/test_fastsim.py``).  A few loops are
written twice, because mypyc cannot keep their scores, heaps and grids out of
Python objects: :data:`NATIVE` does them in C (its opening comment lists each
with the Python function it copies), and the Python hands them over when the
module is there.  The Python stays the reference, and the test holds the two
to the same answers on random inputs.  ``model.hypot`` is CPython's own
``math.hypot`` written out, so that the compiled modules call it without going
through the ``math`` module; the source keeps calling ``math.hypot``.  A build
is filed under a hash of the sources it was made from, so an edited source is
never run as an old build: the next activation compiles it again, which takes
a minute or less, and removes the builds no process has started on for three
days (:func:`prune`).

What the compiler asks in return is that the annotations are true.  A value
of the wrong type reaching compiled code (a ``KnownMine`` where a ``Building``
was promised) raises ``TypeError`` there, where the interpreter would have
carried on; ``mypy`` over :data:`MODULES` must stay clean for a build to exist.

:func:`activate` is called by ``tools/arena.py``, ``tune.py``,
``balance_report.py``, ``ai_report.py``, ``race_report.py``, ``sim_bench.py``,
``step_bench.py`` and ``fuzz.py`` when they run as programs, before they import the
simulation, and again in the worker processes they spawn, which run the same
script as ``__mp_main__`` and take the parent's build from ``WARBAND_FASTSIM``.
A process that only imports one of them as a library stays as it was.  The
game calls :func:`activate_for_game` first thing in ``warband.__main__.main``:
a checkout compiles on the first launch after its sources change, and a
frozen app carries the build it was frozen with (``tools/package.py`` puts it
under :data:`SHIPPED`), so a player needs no compiler.  The online authority,
the tests and everything else run the source.  ``WARBAND_INTERPRETED=1`` makes
both activations a no-op.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

from warband.sim import config as balance_config

PACKAGE = Path(__file__).resolve().parents[1]  # warband/, whose subpackages hold the modules
BUILDS = PACKAGE.parent / "build" / "fastsim"
SHIPPED = PACKAGE / "assets" / "fastsim"  # a frozen app's one build, which tools/package.py puts there to be frozen with it
MODULES = ("sim.rules", "sim.races", "sim.path", "sim.worker_knowledge", "sim.model", "sim.camps", "sim.mapgen", "sim.worker_ai",
           "brains.unique", "brains.ai", "brains.pro_profiles", "brains.pro_force", "brains.magic", "brains.pro_core", "brains.pro_economy", "brains.pro_ai")
NATIVE = "sim/_native.c"  # the loops written twice, in C, built alongside; see its opening comment
#: mypy's options for the compile: no configuration file is read, the repository's or the user's, for no key hashes one
MYPY = ("--config-file=", "--follow-imports=silent")
ENV = "WARBAND_FASTSIM"  # the build a process activated, for the worker processes it starts
OPT_OUT = "WARBAND_INTERPRETED"
NO_TOOLCHAIN = 3  # the compiling process's exit status when this machine cannot compile at all
#: How long a build nobody has attached stays under BUILDS: longer than a run of many hours, nights asleep included,
#: for a run's workers attach when it starts (see :func:`prune`).  Some four builds a day make it a dozen, 85 MB.
STALE_AFTER = 3 * 24 * 3600


class NoToolchain(RuntimeError):
    """This machine cannot compile the simulation: mypyc or a C compiler is missing.  The message says which."""


def source(module: str) -> str:
    """The file of a module of :data:`MODULES`, under ``warband/``."""
    return module.replace(".", "/") + ".py"


def source_key() -> str:
    """The identity of everything the compile reads but the balance tables and the toolchain: every source of the
    packages :data:`MODULES` are in (all they import, for ``tests/warband/test_layers.py`` keeps ``sim`` and ``brains``
    to themselves), the package's ``__init__.py``, this recipe and the interpreter."""
    folders = dict.fromkeys(module.partition(".")[0] for module in MODULES)
    files = sorted(path for folder in folders for path in (PACKAGE / folder).rglob("*")
                   if path.suffix in (".py", ".pyi", ".c"))
    digest = hashlib.sha256()
    for path in (PACKAGE / "__init__.py", PACKAGE / "league/fastsim.py", *files):
        digest.update(path.relative_to(PACKAGE).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    digest.update(f"{sys.implementation.cache_tag}|{sysconfig.get_platform()}".encode())
    return digest.hexdigest()[:20]


def _key(sources: dict[str, str]) -> str:
    return hashlib.sha256((source_key() + json.dumps(sources, sort_keys=True)).encode()).hexdigest()[:20]


def key() -> str:
    """A build's identity covers both its code and this process's frozen balance inputs."""
    return _key(balance_config.sources())


def build() -> Path:
    """The compiled modules for the current sources, compiling them first if no build has them yet."""
    target = BUILDS / key()
    if target.is_dir():
        return target
    BUILDS.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{target.name}-", dir=BUILDS))
    config = {"paths": [f"warband/{source(name)}" for name in MODULES], "native": f"warband/{NATIVE}", "mypy": MYPY,
              "cache": str(staging / "mypy"), "c": str(staging / "c"), "out": str(staging), "obj": str(staging / "obj")}
    script = f"""
import json, sys
from pathlib import Path
from setuptools import Extension, setup
config = json.loads({json.dumps(config)!r})
try:
    from mypyc.build import mypycify
except ImportError:
    print("mypyc is not installed (uv sync --extra dev installs it)", file=sys.stderr)
    sys.exit({NO_TOOLCHAIN})
probe = Path(config["obj"], "probe.c")
probe.parent.mkdir(parents=True)
probe.write_text("#include <Python.h>\\nPyMODINIT_FUNC PyInit_probe(void) {{ return NULL; }}\\n")  # MSVC links its PyInit_ too
try:  # before mypyc spends its minute: setup() turns a missing C compiler into SystemExit("error: ...")
    setup(name="probe", packages=[], py_modules=[], ext_modules=[Extension("probe", [str(probe)])],
          script_args=["build_ext", "--build-lib", str(probe.parent), "--build-temp", str(probe.parent)])
except SystemExit as failed:
    print("no C compiler (" + " ".join(str(failed).split()) + ")", file=sys.stderr)
    sys.exit({NO_TOOLCHAIN})
modules = mypycify([*config["mypy"], "--cache-dir=" + config["cache"], *config["paths"]], target_dir=config["c"])
modules.append(Extension("warband.sim._native", [config["native"]]))
if sys.platform != "win32":
    for module in modules:  # no fused multiply-add: every float operation rounds on its own, as Python's do
        module.extra_compile_args.append("-ffp-contract=off")
setup(name="warband-fastsim", packages=[], py_modules=[], ext_modules=modules,
      script_args=["build_ext", "--build-lib", config["out"], "--build-temp", config["obj"]])
"""
    print(f"compiling the simulation with mypyc into {target}, once per change to its sources (a minute or so)...",
          file=sys.stderr, flush=True)
    done = subprocess.run([sys.executable, "-c", script], cwd=PACKAGE.parent, capture_output=True, text=True)
    if done.returncode:
        shutil.rmtree(staging, ignore_errors=True)
        if done.returncode == NO_TOOLCHAIN:
            raise NoToolchain(done.stderr.strip().splitlines()[-1])
        raise RuntimeError(f"mypyc could not compile the simulation (python -m mypy {' '.join(f'warband/{source(m)}' for m in MODULES)} "
                           f"shows why):\n{done.stdout[-4000:]}\n{done.stderr[-4000:]}")
    for scratch in ("mypy", "c", "obj"):
        shutil.rmtree(staging / scratch)
    (staging / "constants.json").write_text(json.dumps(balance_config.sources(), sort_keys=True), encoding="utf-8")
    try:
        staging.rename(target)
    except OSError:  # another process finished the same build first; theirs is as good
        shutil.rmtree(staging)
    prune(keep=target)
    return target


def prune(keep: Path) -> None:
    """Remove what no process has attached for :data:`STALE_AFTER` from :data:`BUILDS`: old builds and the staging
    folders of interrupted ones, never *keep* or the build this process runs (``WARBAND_FASTSIM``).

    Every activation touches its build, a spawned worker's too, so the age is the time since a process last started
    on it.  A run's workers start with it, and a process that has loaded its modules no longer needs their files
    (macOS, Linux; Windows refuses to move them while it holds them).  A build is renamed out of its key before it is
    removed, so a removal that stops half way never leaves a folder that ``build()`` would take for a whole build."""
    spared = {keep.name, Path(os.environ.get(ENV, keep)).name}
    now = time.time()
    for entry in BUILDS.iterdir():
        if entry.name in spared:
            continue
        try:
            if now - entry.stat().st_mtime < STALE_AFTER:
                continue
            doomed = entry if entry.name.endswith(".pruned") else entry.rename(entry.with_name(entry.name + ".pruned"))
        except OSError:  # another process pruned it meanwhile, or a running one holds it (Windows)
            continue
        shutil.rmtree(doomed, ignore_errors=True)  # what a running process still holds stays for the next prune


def attach(path: str | os.PathLike[str]) -> None:
    """Import :data:`MODULES` from the build at *path* from now on; it must match the current sources.

    A frozen app has no sources to hash: it was frozen with the build it carries, and checks that build's balance
    tables against its own."""
    root = Path(path)
    if not root.is_dir():
        raise ImportError(f"the compiled simulation {root.name} is missing or was built from other sources")
    sources = json.loads((root / "constants.json").read_text(encoding="utf-8"))
    if getattr(sys, "frozen", False):
        if sources != balance_config.read_sources():
            raise ImportError(f"the compiled simulation {root.name} carries other balance tables than this app's")
    elif root.name != _key(sources):
        raise ImportError(f"the compiled simulation {root.name} was built from other sources: the current ones "
                          f"make {_key(sources)}")
    else:
        os.utime(root)  # in use: prune() spares it for STALE_AFTER from now (a frozen app's own copy may be read-only)
    # The build holds no __init__.py, so each source package stays the package, with the build's directory first
    # on its path; the packages' own __init__.py import none of MODULES.
    packages = {name: importlib.import_module(f"warband.{name}") for name in dict.fromkeys(m.partition(".")[0] for m in MODULES)}
    if all(str(root / "warband" / name) in package.__path__ for name, package in packages.items()):
        return
    loaded = sorted(name for name in sys.modules if name.startswith("warband.") and name[8:] in MODULES)
    if loaded:
        raise RuntimeError(f"the compiled simulation must be activated before it is imported; already loaded: {loaded}")
    balance_config.install(sources)
    for name, package in packages.items():
        package.__path__.insert(0, str(root / "warband" / name))  # a compiled module is found before its source
    sys.path.insert(0, str(root))  # mypyc's shared library of the whole group
    os.environ[ENV] = str(root)


def activate() -> Path | None:
    """Run the compiled simulation in this process and every process it starts; its build path, or None when opted out.

    A worker process takes the build its parent activated, never one of its own: sources edited since
    the parent started are refused rather than compiled again in every worker.
    """
    if os.environ.get(OPT_OUT):
        return None
    inherited = os.environ.get(ENV)
    root = Path(inherited) if inherited else build()
    attach(root)
    return root


def activate_for_game() -> Path | None:
    """Run the game on the compiled simulation, before anything imports it; its build path, or None on the source.

    A frozen app attaches the build it was frozen with (:data:`SHIPPED`).  A checkout compiles its sources on the
    first launch after they change, as the tools do.  A machine that cannot compile them (no mypyc, no C compiler)
    runs the source, and says so, as :data:`OPT_OUT` does.
    """
    if os.environ.get(OPT_OUT):
        print(f"warband: running the simulation from source ({OPT_OUT} is set)", file=sys.stderr)
        return None
    if getattr(sys, "frozen", False):
        builds = list(SHIPPED.iterdir()) if SHIPPED.is_dir() else []
        if len(builds) != 1:
            raise ImportError(f"a frozen Warband carries one compiled simulation under {SHIPPED}, this one {len(builds)}")
        root = builds[0]
    else:
        try:
            root = build()
        except NoToolchain as missing:
            print(f"warband: running the simulation from source, several times slower in large matches: {missing}",
                  file=sys.stderr)
            return None
    attach(root)
    return root


def compiled() -> bool:
    """Whether this process runs the compiled simulation (the world's module came from a build)."""
    from warband.sim import model

    return model.__file__.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))


if __name__ == "__main__":
    print(build())
