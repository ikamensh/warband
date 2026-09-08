"""Release smoke logic crosses real sockets before it is run inside PyInstaller."""
import argparse
import importlib.util
import os
from pathlib import Path

import pytest

from tools.build_warband import version
from tools.verify_warband_package import isolated_environment, local_server


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
