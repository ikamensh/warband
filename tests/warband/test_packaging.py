"""Release smoke logic crosses real sockets before it is run inside PyInstaller."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from tools.build_warband import version
from tools.verify_warband_package import isolated_environment, local_server, mesa_test_context, verify


def test_shipped_online_smoke_accepts_authority_movement_and_seat_rejoin():
    """The exact frozen diagnostic uses production room rules and both real clients."""
    path = Path(__file__).resolve().parents[2] / "packaging" / "warband_package_check.py"
    spec = importlib.util.spec_from_file_location("warband_package_check", path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    with local_server() as endpoint:
        result = checker.online_smoke(endpoint)
    assert result == {"create_join": True, "foreign_order_rejected": True, "authoritative_movement": True, "private_seat_rejoin": True}


def test_isolated_package_profile_preserves_windows_dll_environment(tmp_path):
    """A clean launch removes user Python overrides without deleting OS configuration."""
    original = {**os.environ, "SystemRoot": "C:\\Windows", "PYTHONPATH": "unrelated-checkout", "PYTHONHOME": "developer-python"}
    clean = isolated_environment(tmp_path, original)
    assert clean["SystemRoot"] == original["SystemRoot"]
    assert clean["USERPROFILE"] == str(tmp_path)
    assert "PYTHONPATH" not in clean and "PYTHONHOME" not in clean
    assert original["PYTHONPATH"] == "unrelated-checkout"


@pytest.mark.parametrize("value", ("", "latest", "1.2", "1.2.3/other", "65536.0.0", "1.2.3;echo"))
def test_release_identity_rejects_unsafe_or_non_numeric_installer_versions(value):
    """An explicit release version must fit both the artifact filename and Windows metadata."""
    with pytest.raises(argparse.ArgumentTypeError):
        version(value)


def test_public_acceptance_cannot_succeed_without_an_installer(tmp_path):
    """An explicit installed-client check must not silently become a portable-only run."""
    archive = tmp_path / "Warband-portable.zip"
    archive.write_bytes(b"fixture")
    manifest = {"artifacts": [{"file": archive.name, "bytes": archive.stat().st_size,
                               "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
    (tmp_path / "build-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="requires the Windows installer"):
        verify(tmp_path, public_server="wss://games.tachyon-ai.eu/play")


def test_public_acceptance_requires_tls(tmp_path):
    """Public acceptance must exercise TLS rather than accidentally testing loopback."""
    with pytest.raises(ValueError, match="TLS endpoint"):
        verify(tmp_path, public_server="ws://127.0.0.1/play")


def test_mesa_context_is_temporary_and_preserves_the_shipping_executable(tmp_path):
    """A failed native check must still remove only its test DLLs and keep app bytes."""
    installed, mesa = tmp_path / "installed", tmp_path / "mesa"
    installed.mkdir()
    mesa.mkdir()
    executable = installed / "Warband.exe"
    executable.write_bytes(b"shipping executable")
    for name in ("opengl32.dll", "libgallium_wgl.dll"):
        (mesa / name).write_bytes(name.encode())
    with pytest.raises(RuntimeError, match="native failure"):
        with mesa_test_context(executable, mesa) as receipt:
            assert set(receipt["dll_sha256"]) == {"opengl32.dll", "libgallium_wgl.dll"}
            assert (installed / "opengl32.dll").read_bytes() == (mesa / "opengl32.dll").read_bytes()
            raise RuntimeError("native failure")
    assert list(installed.iterdir()) == [executable]
    assert executable.read_bytes() == b"shipping executable"
