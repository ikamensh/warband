"""Build native packages and validate their evidence before release publication.

The validation command uses only the standard library, so the Linux release
job can check both native runners' archives without loading the game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("windows-x64", "darwin-arm64")
PACKAGES = ("numpy", "Pillow", "pyglet", "websockets", "pyinstaller", "pyinstaller-hooks-contrib")
ONLINE_CHECKS = ("create_join", "authoritative_movement", "foreign_order_rejected", "private_seat_rejoin",
                 "global_production", "automatic_plan_builder", "cancel_plans", "assembly_point")
NATIVE_CHECKS = ("native_multiplayer_input", "native_clipboard_join", "live_match_menu", "native_settlement_planning")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_file(directory: Path, name: str) -> Path:
    require(bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name,
            f"Evidence must name a local file: {name}")
    path = directory / name
    require(path.is_file() and not path.is_symlink(), f"Missing or linked evidence file: {name}")
    return path


def locked_packages(identity: dict) -> dict:
    lock = ROOT / "uv.lock"
    require(sha256(lock) == identity["lock_sha256"], "Release identity differs from the committed lock")
    versions = {item["name"]: item["version"] for item in tomllib.loads(lock.read_text())["package"]}
    require(versions["saga2d"] == identity["saga2d_version"], "Engine identity differs from the lock")
    return {name: versions[name.lower()] for name in (*PACKAGES, "saga2d", "sagaforge")}


def validate(directory: Path, identity: dict, target: str) -> dict:
    """Accept only complete native evidence for these exact release inputs and bytes."""
    require(target in TARGETS, f"Unsupported release target: {target}")
    evidence = {}

    def record(name: str) -> Path:
        path = local_file(directory, name)
        evidence[name] = sha256(path)
        return path

    inputs = read_json(record("build-inputs.json"))
    require(inputs["identity"] == identity and inputs["target"] == target, "Build inputs differ from release identity/target")
    versions = locked_packages(identity)
    require(inputs["packages"] == versions, "Installed dependencies differ from the lock")
    regression = read_json(record("regression.json"))
    require(regression["identity"] == identity and regression["exit_code"] == 0
            and regression["command"] == ["-m", "pytest", "-q"], "Full regression suite did not pass for this identity")
    require(sha256(record("regression.log")) == regression["log_sha256"], "Regression log differs from its receipt")
    manifest = read_json(record("build-manifest.json"))
    require(manifest["game"] == "warband" and manifest["product"] == "Warband", "Wrong game package")
    require(manifest["working_tree_dirty"] is False, "Dirty sources cannot be released")
    require(manifest["python"] == identity["python"], "Build Python differs from release identity")
    require(manifest["packages"] == {name: versions[name] for name in PACKAGES}, "Frozen build tools/runtime differ from the lock")
    require(manifest["architecture"].lower() in ({"amd64", "x86_64"} if target == "windows-x64" else {"arm64"}),
            "Build architecture differs from release target")
    require(manifest["platform"].startswith("Windows" if target == "windows-x64" else ("macOS", "Darwin")),
            "Build platform differs from release target")

    def same_release(receipt: dict) -> None:
        require(receipt["source_commit"] == identity["source_commit"] and receipt["version"] == identity["version"],
                "Stale or mixed source/version in package evidence")

    same_release(manifest)
    prefix = f"Warband-{identity['version']}-{target}"
    portable = f"{prefix}-portable.zip"
    installed = f"{prefix}-setup.exe" if target == "windows-x64" else f"{prefix}-app.zip"
    artifacts = manifest["artifacts"]
    require(len(artifacts) == 2 and {item["file"] for item in artifacts} == {portable, installed},
            "Package must contain exactly the portable and installed artifacts")
    for item in artifacts:
        path = local_file(directory, item["file"])
        require(path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"],
                f"Artifact bytes differ from the manifest: {path.name}")
    checksums = "".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts)
    require(record("SHA256SUMS").read_text(encoding="ascii") == checksums, "SHA256SUMS differs from the manifest")

    def executable_digest(archive: str, member: str) -> str:
        with zipfile.ZipFile(directory / archive) as bundle:
            require(bundle.namelist().count(member) == 1, f"Missing or duplicate archived executable: {member}")
            with bundle.open(member) as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

    portable_digest = executable_digest(portable, "Warband/Warband.exe" if target == "windows-x64" else "Warband/Warband")
    app_digest = portable_digest if target == "windows-x64" else executable_digest(installed, "Warband.app/Contents/MacOS/Warband")
    report = read_json(record("verification.json"))
    same_release(report)
    require(report["passed"] is True, "Package verification did not pass")

    def receipt(name: str, executable: str, *, native=False) -> None:
        result = report[name]
        same_release(result)
        require(result["passed"] is True and result["executable_sha256"] == executable,
                f"{name} receipt does not accept the archived executable")
        if native:
            require(result["backend"] == "pyglet" and all(result[key] is True for key in NATIVE_CHECKS),
                    f"Incomplete native checks: {name}")
            require(bool(result["images"]), f"Missing captured images: {name}")
            for image in result["images"]:
                path = local_file(directory / "verification", image)
                require(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), f"Invalid captured PNG: {image}")
                evidence[f"verification/{image}"] = sha256(path)
        else:
            require(result["frozen"] is True and result["bundled_fonts"] is True
                    and all(result["online"][key] is True for key in ONLINE_CHECKS), f"Incomplete socket checks: {name}")

    receipt("portable", portable_digest)
    receipt("installed", app_digest)
    receipt("native", portable_digest, native=True)
    if target == "windows-x64":
        require(report["install_shortcut_uninstall"] is True, "Windows shortcut/uninstall checks did not pass")
    else:
        receipt("app_native", app_digest, native=True)
    return {"schema_version": 1, "identity": identity, "target": target, "artifacts": artifacts, "evidence": evidence}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validator = commands.add_parser("validate")
    validator.add_argument("--identity", type=Path, required=True)
    validator.add_argument("--directory", type=Path, required=True)
    validator.add_argument("--target", choices=TARGETS, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.directory, read_json(args.identity), args.target), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
