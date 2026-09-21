"""Which build of Warband is running, as the screens show it.

A released build carries its identity in ``release/build-info.json``, written
when it was frozen: the version CI published and the commit it came from.  A
source checkout has no published version — the number is only decided by the
run that publishes it — so it names its commit instead, with a ``+`` when the
working tree has changes the commit does not.  A player reading a version off
the title screen and an agent reading one off a screenshot both want the same
thing: enough to say exactly which build this is.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import subprocess
from typing import Any, Mapping

from saga2d.release import build_info

ROOT = Path(__file__).resolve().parents[2]  # the repository, when the game runs from a checkout


def describe(info: Mapping[str, Any] | None, commit: str | None) -> str:
    """The label for a build frozen as *info* (``None`` for a checkout) sitting at *commit*."""
    if info is not None:
        label = f"v{info['version']} · {info['source_commit'][:7]}"
        return f"{label} · modified" if info["working_tree_dirty"] else label
    return f"checkout · {commit}" if commit else "checkout"


def checkout_commit() -> str | None:
    """The commit the checkout stands at, ``+`` if the tree has changes; ``None`` when there is no checkout to ask."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()

    try:
        return git("rev-parse", "--short=7", "HEAD") + ("+" if git("status", "--porcelain") else "")
    except (OSError, subprocess.CalledProcessError):
        return None  # installed without its repository, or without git


@lru_cache(maxsize=1)
def running_build() -> str:
    """This build's label: asked once, since neither the frozen identity nor the commit changes while the game runs.

    A frozen build is never asked for a commit: it carries its own, and there is no checkout under it to ask."""
    info = build_info()
    return describe(info, None if info is not None else checkout_commit())
