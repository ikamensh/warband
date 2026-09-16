"""Prepare the immutable inputs shared by native CI package builds.

    python tools/ci_release.py prepare --run-id 35100000123 --output dist/identity.json

Preparation needs only Python's standard library and Git, before installing
dependencies. It never publishes, tags, or changes the source checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib

from ci_compatibility import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def prepare(root: Path, run_id: str) -> dict:
    """Bind a clean committed checkout and its locked dependencies to one CI run."""
    root = root.resolve()
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("run ID must be a positive integer")
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()
    if Path(top).resolve() != root:
        raise ValueError("root must be the game repository root")
    dirty = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=root, text=True)
    if dirty:
        raise ValueError("Release preparation requires a clean source checkout")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    if project["name"] != "warband" or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", project["version"]):
        raise ValueError("Warband must declare a MAJOR.MINOR.PATCH base version")
    engine_pins = [item.removeprefix("saga2d==") for item in project["dependencies"] if item.startswith("saga2d==")]
    if len(engine_pins) != 1:
        raise ValueError("Warband must pin exactly one saga2d release")
    lock_bytes = (root / "uv.lock").read_bytes()
    lock = tomllib.loads(lock_bytes.decode("utf-8"))
    engines = [item for item in lock["package"] if item["name"] == "saga2d"]
    if (len(engines) != 1 or engines[0]["version"] != engine_pins[0]
            or engines[0]["source"] != {"registry": "https://pypi.org/simple"}):
        raise ValueError("The saga2d lock must match the declared PyPI release")
    pins = json.loads((root / ".github/release-pins.json").read_text())
    if set(pins) != {"sagaforge_commit", "python", "uv", "inno_setup"}:
        raise ValueError("Release pins must contain sagaforge_commit, python, uv and inno_setup")
    if not isinstance(pins["sagaforge_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", pins["sagaforge_commit"]):
        raise ValueError("Sagaforge must be pinned to a full commit SHA")
    for tool in ("python", "uv", "inno_setup"):
        if not isinstance(pins[tool], str) or not re.fullmatch(r"\d+\.\d+\.\d+", pins[tool]):
            raise ValueError(f"{tool} must be pinned to an exact version")
    version = f"{project['version']}-preview.{run_id}"
    return {
        "schema_version": 1, "game": "warband", "version": version,
        "tag": f"v{version}", "run_id": int(run_id), "source_commit": commit,
        "saga2d_version": engine_pins[0], "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "compatibility": fingerprint(root),
        **pins,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--root", type=Path, default=ROOT)
    command.add_argument("--run-id", required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identity = prepare(args.root, args.run_id)
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous["run_id"] == identity["run_id"] and previous != identity:
            raise ValueError("A CI run cannot change its release identity")
    encoded = json.dumps(identity, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(args.output)
    print(encoded, end="")


if __name__ == "__main__":
    main()
