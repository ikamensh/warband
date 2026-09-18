"""The simulation compiled to C by mypyc, for the tools that play many matches.

    uv run python -m warband.fastsim        # build it now (the tools build it on first use) and say where

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
a minute or less.

What the compiler asks in return is that the annotations are true.  A value
of the wrong type reaching compiled code (a ``KnownMine`` where a ``Building``
was promised) raises ``TypeError`` there, where the interpreter would have
carried on; ``mypy`` over :data:`MODULES` must stay clean for a build to exist.

:func:`activate` is called by ``tools/arena.py``, ``tune.py``,
``balance_report.py``, ``ai_report.py``, ``race_report.py``, ``sim_bench.py``
and ``step_bench.py`` when they run as programs, before they import the
simulation, and again in the worker processes they spawn, which run the same
script as ``__mp_main__`` and take the parent's build from ``WARBAND_FASTSIM``.
A process that only imports one of them as a library stays as it was.  The
game itself, the online authority, the tests and everything else run the
source.  ``WARBAND_INTERPRETED=1`` makes :func:`activate` a no-op.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
BUILDS = PACKAGE.parent / "build" / "fastsim"
MODULES = ("rules", "races", "path", "worker_knowledge", "model", "mapgen", "worker_ai", "ai", "pro_ai")
NATIVE = "_native.c"  # the loops written twice, in C, built alongside; see its opening comment
RECIPE = "2"  # bumped when the build itself changes, so that no build made the old way is reused
ENV = "WARBAND_FASTSIM"  # the build a process activated, for the worker processes it starts
OPT_OUT = "WARBAND_INTERPRETED"


def key() -> str:
    """The name of the build these sources make on this interpreter."""
    digest = hashlib.sha256()
    for name in (*(f"{module}.py" for module in MODULES), NATIVE):
        digest.update(name.encode() + b"\0" + (PACKAGE / name).read_bytes() + b"\0")
    digest.update(f"{RECIPE}|{sys.implementation.cache_tag}|{sysconfig.get_platform()}".encode())
    return digest.hexdigest()[:20]


def build() -> Path:
    """The compiled modules for the current sources, compiling them first if no build has them yet."""
    target = BUILDS / key()
    if target.is_dir():
        return target
    BUILDS.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{target.name}-", dir=BUILDS))
    config = {"paths": [f"warband/{name}.py" for name in MODULES], "native": f"warband/{NATIVE}",
              "cache": str(staging / "mypy"), "c": str(staging / "c"), "out": str(staging), "obj": str(staging / "obj")}
    script = f"""
import json, sys
from setuptools import Extension, setup
from mypyc.build import mypycify
config = json.loads({json.dumps(config)!r})
modules = mypycify(["--cache-dir=" + config["cache"], "--follow-imports=silent", *config["paths"]], target_dir=config["c"])
modules.append(Extension("warband._native", [config["native"]]))
if sys.platform != "win32":
    for module in modules:  # no fused multiply-add: every float operation rounds on its own, as Python's do
        module.extra_compile_args.append("-ffp-contract=off")
setup(name="warband-fastsim", packages=[], py_modules=[], ext_modules=modules,
      script_args=["build_ext", "--build-lib", config["out"], "--build-temp", config["obj"]])
"""
    print(f"compiling the simulation with mypyc into {target} (once per change to its sources)...", file=sys.stderr, flush=True)
    done = subprocess.run([sys.executable, "-c", script], cwd=PACKAGE.parent, capture_output=True, text=True)
    if done.returncode:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(f"mypyc could not compile the simulation (python -m mypy warband/{{{','.join(MODULES)}}}.py "
                           f"shows why):\n{done.stdout[-4000:]}\n{done.stderr[-4000:]}")
    for scratch in ("mypy", "c", "obj"):
        shutil.rmtree(staging / scratch)
    try:
        staging.rename(target)
    except OSError:  # another process finished the same build first; theirs is as good
        shutil.rmtree(staging)
    return target


def attach(path: str | os.PathLike[str]) -> None:
    """Import :data:`MODULES` from the build at *path* from now on; it must match the current sources."""
    root = Path(path)
    if root.name != key():
        raise ImportError(f"the compiled simulation {root.name} was built from other sources: the current ones "
                          f"make {key()}")
    import warband

    compiled = str(root / "warband")
    if compiled in warband.__path__:
        return
    loaded = sorted(name for name in sys.modules if name.startswith("warband.") and name[8:] in MODULES)
    if loaded:
        raise RuntimeError(f"the compiled simulation must be activated before it is imported; already loaded: {loaded}")
    warband.__path__.insert(0, compiled)  # a compiled module is found before its source
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


if __name__ == "__main__":
    print(build())
