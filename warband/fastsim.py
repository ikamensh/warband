"""The simulation compiled to C by mypyc, for the tools that play many matches.

    uv run python -m warband.fastsim        # build it now (the tools build it on first use) and say where

The modules in :data:`MODULES` (the world, its pathfinding and worker policy,
the rule tables and both kinds of brain) are compiled from their own source,
so a compiled match is the interpreted match: mypyc keeps Python's integer and
float semantics and every operation's order, and ``tools/sim_fingerprint.py``
checks the two to the bit (``tests/warband/test_fastsim.py``).  A build is
filed under a hash of the sources it was made from, so an edited source is
never run as an old build: the next activation compiles it again, which
takes a minute or less.

What the compiler asks in return is that the annotations are true.  A value
of the wrong type reaching compiled code (a ``KnownMine`` where a ``Building``
was promised) raises ``TypeError`` there, where the interpreter would have
carried on; ``mypy`` over :data:`MODULES` must stay clean for a build to exist.

:func:`activate` is called by ``tools/arena.py``, ``tune.py``,
``balance_report.py``, ``ai_report.py``, ``race_report.py``, ``sim_bench.py``
and ``step_bench.py`` before they import the simulation; worker processes they
spawn follow through the ``WARBAND_FASTSIM`` variable (see
``warband/__init__.py``).  The game itself, the tests and everything else run
the source.  ``WARBAND_INTERPRETED=1`` makes :func:`activate` a no-op.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
BUILDS = PACKAGE.parent / "build" / "fastsim"
MODULES = ("rules", "races", "path", "worker_knowledge", "model", "worker_ai", "ai", "pro_ai")
ENV = "WARBAND_FASTSIM"  # the build a parent process activated, for the processes it starts
OPT_OUT = "WARBAND_INTERPRETED"


def key() -> str:
    """The name of the build these sources make on this interpreter."""
    digest = hashlib.sha256()
    for name in MODULES:
        digest.update(name.encode() + b"\0" + (PACKAGE / f"{name}.py").read_bytes() + b"\0")
    digest.update(f"{sys.implementation.cache_tag}|{sysconfig.get_platform()}".encode())
    return digest.hexdigest()[:20]


def build() -> Path:
    """The compiled modules for the current sources, compiling them first if no build has them yet."""
    target = BUILDS / key()
    if target.is_dir():
        return target
    BUILDS.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{target.name}-", dir=BUILDS))
    paths = [f"warband/{name}.py" for name in MODULES]
    script = (
        "from setuptools import setup\n"
        "from mypyc.build import mypycify\n"
        f"setup(name='warband-fastsim', packages=[], py_modules=[],"
        f" ext_modules=mypycify({[f'--cache-dir={staging / 'mypy'}', *paths]!r},"
        f" target_dir={str(staging / 'c')!r}),"
        f" script_args=['build_ext', '--build-lib', {str(staging)!r}, '--build-temp', {str(staging / 'obj')!r}])\n"
    )
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
        raise ImportError(f"{ENV} names the compiled simulation {root.name}, but the sources now make {key()}: "
                          f"the process that set it ran other sources")
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
    """Run the compiled simulation in this process and every process it starts; its build path, or None when opted out."""
    if os.environ.get(OPT_OUT):
        return None
    root = build()
    attach(root)
    return root


if __name__ == "__main__":
    print(build())
