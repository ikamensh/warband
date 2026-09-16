"""Build native packages and validate their evidence before release publication.

The validation command uses only the standard library, so the Linux release
job can check both native runners' archives without loading the game.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata, util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
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


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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
    if target == "windows-x64":
        require(inputs["inno_setup"] == identity["inno_setup"], "Installer compiler differs from the release pin")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", inputs["inno_setup_sha256"])), "Missing installer compiler digest")
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


def native_inputs(identity: dict, *, iscc: Path | None = None) -> dict:
    """Check the actual interpreter, installed packages and editable source checkouts."""
    from ci_release import prepare

    require(prepare(ROOT, str(identity["run_id"])) == identity, "Checkout differs from release identity")
    require(platform.python_version() == identity["python"], "Use the pinned build Python")
    uv = subprocess.check_output(["uv", "--version"], text=True).split()[1]
    require(uv == identity["uv"], "Use the pinned uv executable on PATH")
    host = (platform.system(), platform.machine().lower())
    if host == ("Darwin", "arm64"):
        target = "darwin-arm64"
    elif host[0] == "Windows" and host[1] in ("amd64", "x86_64"):
        target = "windows-x64"
    else:
        raise ValueError(f"Native packaging requires Windows x64 or Apple Silicon macOS, got {host}")
    for name, root in (("warband", ROOT), ("sagaforge", ROOT.parent / "sagaforge")):
        require(Path(util.find_spec(name).origin).resolve() == (root / name / "__init__.py").resolve(),
                f"Installed {name} must use the intended checkout")
        require(not subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=root, text=True).strip(),
                f"The {name} source checkout must be clean")
        if name == "sagaforge":
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            require(commit == identity["sagaforge_commit"], "Sagaforge checkout differs from the release pin")
    require(metadata.distribution("saga2d").read_text("direct_url.json") is None,
            "Use the locked Saga2D PyPI release, not a path/editable install")
    packages = {name: metadata.version(name) for name in (*PACKAGES, "saga2d", "sagaforge")}
    require(packages == locked_packages(identity), "Installed build dependencies differ from the lock")
    result = {"identity": identity, "target": target, "packages": packages}
    if target == "windows-x64":
        require(iscc is not None and iscc.is_file(), "Windows builds require an explicit Inno Setup compiler")
        compiler_version = subprocess.check_output([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-Item -LiteralPath $env:WARBAND_ISCC).VersionInfo.ProductVersion",
        ], env={**os.environ, "WARBAND_ISCC": str(iscc.resolve())}, text=True).strip()
        require(compiler_version == identity["inno_setup"], "Installed Inno Setup compiler differs from the release pin")
        result.update(inno_setup=compiler_version, inno_setup_sha256=sha256(iscc))
    return result


def verify_mac_app(directory: Path, report: dict) -> None:
    """Archive, extract and launch the app that Mac players will actually download."""
    from package import PACKAGE
    from saga2d.packaging.verify import authority, executable_smoke

    manifest_path = directory / "build-manifest.json"
    manifest = read_json(manifest_path)
    archive = directory / f"Warband-{manifest['version']}-darwin-arm64-app.zip"
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    str(directory / "Warband.app"), str(archive)], check=True)
    with tempfile.TemporaryDirectory(prefix="installed-warband-") as temporary, authority(PACKAGE) as endpoint:
        applications = Path(temporary) / "Applications"
        applications.mkdir()
        subprocess.run(["ditto", "-x", "-k", str(archive), str(applications)], check=True)
        app = applications / "Warband.app"
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        executable = app / "Contents/MacOS/Warband"
        evidence = directory / "verification"
        report["installed"] = executable_smoke(executable, endpoint, evidence / "installed.json", manifest)
        report["app_native"] = executable_smoke(executable, endpoint, evidence / "app-native.json", manifest, native=True)
    manifest["artifacts"].append({"file": archive.name, "bytes": archive.stat().st_size, "sha256": sha256(archive)})
    write_json(manifest_path, manifest)
    (directory / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest["artifacts"]), encoding="ascii")
    write_json(directory / "verification.json", report)


def build(identity: dict, directory: Path, *, iscc: Path | None = None, mesa_dir: Path | None = None) -> dict:
    """Run the suite, freeze the game, verify both distributions and seal their evidence."""
    inputs = native_inputs(identity, iscc=iscc)
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    require(not any(directory.iterdir()), "Use an empty output directory; preserve or explicitly remove earlier evidence")
    write_json(directory / "build-inputs.json", inputs)
    command = ["-m", "pytest", "-q"]
    print("Running the full regression suite; output is in regression.log", flush=True)
    with (directory / "regression.log").open("w", encoding="utf-8") as log:
        process = subprocess.run([sys.executable, *command], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    write_json(directory / "regression.json", {"identity": identity, "command": command,
                                               "exit_code": process.returncode,
                                               "log_sha256": sha256(directory / "regression.log")})
    process.check_returncode()
    require(native_inputs(identity, iscc=iscc) == inputs, "Build inputs changed during regression checks")
    from package import PACKAGE
    from saga2d.packaging import build as freeze
    from saga2d.packaging.verify import verify

    windows = inputs["target"] == "windows-x64"
    freeze(PACKAGE, identity["version"], output=directory, installer=windows, iscc=iscc, require_clean=True)
    report = verify(PACKAGE, directory, native=True, mesa_dir=mesa_dir)
    if not windows:
        verify_mac_app(directory, report)
    require(native_inputs(identity, iscc=iscc) == inputs, "Build inputs changed during package verification")
    accepted = validate(directory, identity, inputs["target"])
    write_json(directory / "candidate.json", accepted)
    return accepted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validator = commands.add_parser("validate")
    validator.add_argument("--identity", type=Path, required=True)
    validator.add_argument("--directory", type=Path, required=True)
    validator.add_argument("--target", choices=TARGETS, required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--identity", type=Path, required=True)
    builder.add_argument("--directory", type=Path, required=True)
    builder.add_argument("--iscc", type=Path)
    builder.add_argument("--mesa-dir", type=Path)
    args = parser.parse_args()
    identity = read_json(args.identity)
    if args.command == "build":
        accepted = build(identity, args.directory, iscc=args.iscc, mesa_dir=args.mesa_dir)
    else:
        accepted = validate(args.directory, identity, args.target)
    print(json.dumps(accepted, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
