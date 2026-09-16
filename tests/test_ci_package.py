"""Consume native CI evidence through the public CLI using real files and ZIPs.

The tiny archives are format fixtures, not executable smoke-test evidence.
The native build command must still run the actual packaged game on each OS.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/ci_package.py"
ONLINE = ("create_join", "authoritative_movement", "foreign_order_rejected", "private_seat_rejoin",
          "global_production", "automatic_plan_builder", "cancel_plans", "assembly_point")


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def candidate(tmp_path):
    directory = tmp_path / "package"
    directory.mkdir()
    lock = (ROOT / "uv.lock").read_bytes()
    pins = json.loads((ROOT / ".github/release-pins.json").read_text())
    identity = {"schema_version": 1, "game": "warband", "source_commit": "a" * 40,
                "version": "0.2.0-preview.123", "tag": "v0.2.0-preview.123", "run_id": 123,
                "saga2d_version": "0.3.2", "lock_sha256": digest(lock), **pins}
    write_json(tmp_path / "identity.json", identity)
    versions = {item["name"]: item["version"] for item in tomllib.loads(lock.decode())["package"]}
    packages = {name: versions[name.lower()] for name in
                ("numpy", "Pillow", "pyglet", "websockets", "pyinstaller", "pyinstaller-hooks-contrib")}
    write_json(directory / "build-inputs.json", {
        "identity": identity, "target": "darwin-arm64",
        "packages": {**packages, "saga2d": versions["saga2d"], "sagaforge": versions["sagaforge"]},
    })
    log = b"845 passed, 12 skipped\n"
    (directory / "regression.log").write_bytes(log)
    write_json(directory / "regression.json", {
        "identity": identity, "command": ["-m", "pytest", "-q"], "exit_code": 0,
        "log_sha256": digest(log),
    })
    executable = b"A deliberately non-executable package format fixture.\n"
    artifacts = []
    for suffix, member in (("portable", "Warband/Warband"),
                           ("app", "Warband.app/Contents/MacOS/Warband")):
        archive = directory / f"Warband-{identity['version']}-darwin-arm64-{suffix}.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(member, executable)
        artifacts.append({"file": archive.name, "bytes": archive.stat().st_size,
                          "sha256": digest(archive.read_bytes())})
    write_json(directory / "build-manifest.json", {
        "product": "Warband", "game": "warband", "source_commit": identity["source_commit"],
        "version": identity["version"], "working_tree_dirty": False, "python": pins["python"],
        "platform": "macOS-15.0-arm64", "architecture": "arm64", "packages": packages,
        "artifacts": artifacts,
    })
    (directory / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts))
    receipt = {"passed": True, "source_commit": identity["source_commit"], "version": identity["version"],
               "executable_sha256": digest(executable)}
    smoke = {**receipt, "frozen": True, "bundled_fonts": True, "online": dict.fromkeys(ONLINE, True)}
    native = {**receipt, "backend": "pyglet", "native_multiplayer_input": True,
              "native_clipboard_join": True, "live_match_menu": True,
              "native_settlement_planning": True, "images": ["native.png"]}
    (directory / "verification").mkdir()
    (directory / "verification/native.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    write_json(directory / "verification.json", {
        "passed": True, "source_commit": identity["source_commit"], "version": identity["version"],
        "portable": smoke, "native": native, "installed": smoke, "app_native": native,
    })
    return directory


def validate(directory, target="darwin-arm64"):
    return subprocess.run([sys.executable, str(CLI), "validate", "--identity",
                           str(directory.parent / "identity.json"), "--directory", str(directory),
                           "--target", target], capture_output=True, text=True)


def test_verified_package_is_bound_to_identity_and_archive_bytes(candidate):
    """The consumer accepts complete evidence and returns exact downloadable file digests."""
    result = validate(candidate)
    assert result.returncode == 0, result.stderr
    accepted = json.loads(result.stdout)
    assert accepted["target"] == "darwin-arm64"
    assert accepted["identity"]["source_commit"] == "a" * 40
    assert len(accepted["artifacts"]) == 2
    for artifact in accepted["artifacts"]:
        assert digest((candidate / artifact["file"]).read_bytes()) == artifact["sha256"]


@pytest.mark.parametrize("problem", ["archive", "regression_log", "stale_receipt", "missing_app",
                                     "failed_native", "changed_dependency", "dirty_source"])
def test_incomplete_stale_or_changed_evidence_is_rejected(candidate, problem):
    """None of the build, regression, archive or native gates can be bypassed by a green summary."""
    if problem == "archive":
        path = next(candidate.glob("*-portable.zip"))
        path.write_bytes(path.read_bytes() + b"changed after verification")
    elif problem == "regression_log":
        (candidate / "regression.log").write_text("Tests were not run\n")
    elif problem in ("stale_receipt", "missing_app", "failed_native"):
        path = candidate / "verification.json"
        value = json.loads(path.read_text())
        if problem == "stale_receipt":
            value["installed"]["source_commit"] = "b" * 40
        elif problem == "missing_app":
            del value["app_native"]
        else:
            value["native"]["native_settlement_planning"] = False
        write_json(path, value)
    elif problem == "changed_dependency":
        path = candidate / "build-inputs.json"
        value = json.loads(path.read_text())
        value["packages"]["saga2d"] = "0.0.0"
        write_json(path, value)
    else:
        path = candidate / "build-manifest.json"
        value = json.loads(path.read_text())
        value["working_tree_dirty"] = True
        write_json(path, value)
    result = validate(candidate)
    assert result.returncode != 0
    assert not result.stdout.strip(), "Rejected packages must not emit an accepted candidate"


def test_replacing_archive_and_checksums_does_not_reuse_old_native_receipts(candidate):
    """A different executable remains unacceptable even after regenerating its artifact checksums."""
    archive = next(candidate.glob("*-app.zip"))
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Warband.app/Contents/MacOS/Warband", b"An unverified executable")
    path = candidate / "build-manifest.json"
    manifest = json.loads(path.read_text())
    item = next(item for item in manifest["artifacts"] if item["file"] == archive.name)
    item.update(bytes=archive.stat().st_size, sha256=digest(archive.read_bytes()))
    write_json(path, manifest)
    (candidate / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest["artifacts"]))
    result = validate(candidate)
    assert result.returncode != 0 and "archived executable" in result.stderr


def test_windows_candidate_requires_the_installer_and_shortcut_uninstall_receipt(candidate):
    """Windows acceptance includes the installed program and cleanup, beyond the portable launch."""
    path = candidate / "build-inputs.json"
    inputs = json.loads(path.read_text())
    inputs["target"] = "windows-x64"
    write_json(path, inputs)
    prefix = f"Warband-{inputs['identity']['version']}-windows-x64"
    portable = candidate / f"{prefix}-portable.zip"
    with zipfile.ZipFile(next(candidate.glob("*-portable.zip"))) as archive:
        executable = archive.read("Warband/Warband")
    with zipfile.ZipFile(portable, "w") as archive:
        archive.writestr("Warband/Warband.exe", executable)
    installer = candidate / f"{prefix}-setup.exe"
    installer.write_bytes(b"A non-executable installer format fixture")
    for archive in candidate.glob("*-darwin-arm64-*.zip"):
        archive.unlink()
    path = candidate / "build-manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(platform="Windows-10", architecture="AMD64", artifacts=[
        {"file": item.name, "bytes": item.stat().st_size, "sha256": digest(item.read_bytes())}
        for item in (portable, installer)])
    write_json(path, manifest)
    (candidate / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest["artifacts"]))
    path = candidate / "verification.json"
    report = json.loads(path.read_text())
    del report["app_native"]
    report["install_shortcut_uninstall"] = True
    write_json(path, report)
    result = validate(candidate, "windows-x64")
    assert result.returncode == 0, result.stderr
    report["install_shortcut_uninstall"] = False
    write_json(path, report)
    result = validate(candidate, "windows-x64")
    assert result.returncode != 0 and "shortcut/uninstall" in result.stderr
