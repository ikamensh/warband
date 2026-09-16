"""CI release preparation through its CLI and real Git checkouts."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "ci_release.py"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Release test")
    git(root, "config", "user.email", "release@example.test")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "warband"\nversion = "1.2.3"\ndependencies = ["saga2d==0.3.2"]\n')
    (root / "uv.lock").write_text(
        '[[package]]\nname = "saga2d"\nversion = "0.3.2"\nsource = {registry = "https://pypi.org/simple"}\n')
    (root / ".github").mkdir()
    (root / ".github/release-pins.json").write_text(json.dumps({
        "sagaforge_commit": "a" * 40, "python": "3.13.2", "uv": "0.12.10", "inno_setup": "6.7.1",
    }))
    (root / "warband").mkdir()
    (root / "warband/__init__.py").write_text('"""A release fixture."""\n')
    (root / ".gitignore").write_text("dist/\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


def prepare(root, run_id="35100000123"):
    return subprocess.run([sys.executable, str(CLI), "prepare", "--root", str(root),
                           "--run-id", run_id, "--output", str(root / "dist/identity.json")],
                          text=True, capture_output=True)


def test_retry_reuses_one_identity_and_another_run_gets_a_new_version(checkout):
    """A release is bound to its Git commit, locked engine and sibling pin across attempts."""
    first = prepare(checkout)
    assert first.returncode == 0, first.stderr
    path = checkout / "dist/identity.json"
    original = path.read_bytes()
    identity = json.loads(original)
    assert identity["source_commit"] == git(checkout, "rev-parse", "HEAD")
    assert identity["sagaforge_commit"] == "a" * 40
    assert identity["saga2d_version"] == "0.3.2"
    assert identity["version"] == "1.2.3-preview.35100000123"
    assert prepare(checkout).returncode == 0
    assert path.read_bytes() == original
    assert prepare(checkout, "35100000124").returncode == 0
    assert json.loads(path.read_text())["version"] != identity["version"]


def test_dirty_source_is_rejected_without_replacing_an_accepted_identity(checkout):
    """An uncommitted source edit cannot be mislabeled with the previous commit's release identity."""
    assert prepare(checkout).returncode == 0
    path = checkout / "dist/identity.json"
    original = path.read_bytes()
    (checkout / "warband/__init__.py").write_text('"""Changed without a commit."""\n')
    result = prepare(checkout)
    assert result.returncode != 0 and "clean" in result.stderr
    assert path.read_bytes() == original


def test_one_run_cannot_be_rebound_to_another_commit(checkout):
    """A retry must never reuse a published version for newly committed source bytes."""
    assert prepare(checkout).returncode == 0
    path = checkout / "dist/identity.json"
    original = path.read_bytes()
    (checkout / "warband/__init__.py").write_text('"""A later commit."""\n')
    git(checkout, "add", "warband/__init__.py")
    git(checkout, "commit", "-qm", "later source")
    result = prepare(checkout)
    assert result.returncode != 0 and "identity" in result.stderr
    assert path.read_bytes() == original


@pytest.mark.parametrize("problem,message", [
    ("engine_mismatch", "lock must match"),
    ("moving_sibling", "full commit SHA"),
    ("untracked_source", "clean source checkout"),
])
def test_inconsistent_or_uncommitted_inputs_do_not_produce_an_identity(checkout, problem, message):
    """The first CI step rejects an unlocked sibling, stale engine lock or untracked game code."""
    if problem == "engine_mismatch":
        path = checkout / "pyproject.toml"
        path.write_text(path.read_text().replace("saga2d==0.3.2", "saga2d==9.9.9"))
    elif problem == "moving_sibling":
        path = checkout / ".github/release-pins.json"
        pins = json.loads(path.read_text())
        pins["sagaforge_commit"] = "main"
        path.write_text(json.dumps(pins))
    else:
        (checkout / "warband/untracked.py").write_text("UNCOMMITTED = True\n")
    if problem != "untracked_source":
        git(checkout, "add", ".")
        git(checkout, "commit", "-qm", "invalid release input")
    result = prepare(checkout)
    assert result.returncode != 0 and message in result.stderr
    assert not (checkout / "dist/identity.json").exists()
