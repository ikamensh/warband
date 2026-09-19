"""CI release preparation through its CLI and real Git checkouts.

A process and a repository per test: the slow tier.
"""
import json
import os
import shutil
import textwrap
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow

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
        "sagaforge_commit": "a" * 40, "python": "3.13.2", "uv": "0.12.10", "inno_setup": "6.7.1", "version_run_base": 25,
    }))
    (root / "warband/online").mkdir(parents=True)
    (root / "warband/__init__.py").write_text('"""A release fixture."""\n')
    (root / "warband/online/__init__.py").write_text('"""The server game of the fixture."""\n')
    (root / "warband/online/authority.py").write_text("ONLINE = {}\n")
    (root / ".gitignore").write_text("dist/\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root


def prepare(root, run_id="35100000123", run_number="26"):
    return subprocess.run([sys.executable, str(CLI), "prepare", "--root", str(root),
                           "--run-id", run_id, "--run-number", run_number, "--output", str(root / "dist/identity.json")],
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
    assert identity["version"] == "1.2.4"
    assert identity["run_number"] == 26 and identity["run_id"] == 35100000123
    expected = subprocess.check_output([sys.executable, str(ROOT / "tools/ci_compatibility.py"),
                                        "--root", str(checkout)], text=True)
    assert identity["compatibility"] == json.loads(expected)
    assert prepare(checkout).returncode == 0
    assert path.read_bytes() == original
    assert prepare(checkout, "35100000124", "27").returncode == 0
    assert json.loads(path.read_text())["version"] == "1.2.5"


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


@pytest.mark.parametrize("number", ["0", "-1", "24", "not-a-number"])
def test_invalid_or_pre_anchor_counter_cannot_allocate_a_version(checkout, number):
    """Bad counters cannot create a version or replace an accepted identity."""
    assert prepare(checkout).returncode == 0
    path = checkout / "dist/identity.json"
    original = path.read_bytes()
    assert prepare(checkout, run_number=number).returncode != 0
    assert path.read_bytes() == original


def test_retry_cannot_change_its_native_counter(checkout):
    """The same run ID cannot acquire a different patch version on retry."""
    assert prepare(checkout).returncode == 0
    path = checkout / "dist/identity.json"
    original = path.read_bytes()
    assert prepare(checkout, run_number="27").returncode != 0
    assert path.read_bytes() == original


@pytest.mark.skipif(os.name == "nt", reason="Executes a Linux workflow bash step")
def test_linux_workflow_resolves_pins_without_a_native_release_counter(checkout, tmp_path):
    """Execute the actual test-workflow setup: its own counter is not the native release counter."""
    scripts = checkout / "tools"
    scripts.mkdir()
    for name in ("ci_release.py", "ci_compatibility.py"):
        shutil.copyfile(ROOT / "tools" / name, scripts / name)
    git(checkout, "add", "tools")
    git(checkout, "commit", "-qm", "release tooling")
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    block = workflow.split("        run: |\n", 1)[1].split("      - ", 1)[0]
    output = tmp_path / "outputs"
    result = subprocess.run(["bash", "-e", "-c", textwrap.dedent(block)], cwd=checkout,
                            env={**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output),
                                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_NUMBER": "1"},
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
        "sagaforge_commit": "a" * 40, "python": "3.13.2", "uv": "0.12.10"}
