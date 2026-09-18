"""The compiled simulation is the simulation: matches played by it hash to the recorded fingerprint, to the bit."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from warband import fastsim

ROOT = Path(__file__).resolve().parents[2]


def test_the_compiled_simulation_plays_the_recorded_fingerprint() -> None:
    build = fastsim.build()
    script = ("import sys; sys.path.insert(0, '.')\n"
              "import warband.model, warband.pro_ai\n"
              f"assert warband.model.__file__.startswith({str(build)!r}), warband.model.__file__\n"
              f"assert warband.pro_ai.__file__.startswith({str(build)!r}), warband.pro_ai.__file__\n"
              "from tools.sim_fingerprint import fingerprint\n"
              "print(fingerprint())\n")
    env = {k: v for k, v in os.environ.items() if k != fastsim.OPT_OUT} | {fastsim.ENV: str(build)}
    done = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == (ROOT / "tools" / "sim_fingerprint.txt").read_text().strip()


def test_a_build_of_other_sources_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ImportError, match="other sources"):
        fastsim.attach(tmp_path / "0123456789abcdef0123")
