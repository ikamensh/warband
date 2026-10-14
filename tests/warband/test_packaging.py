"""The frozen diagnostic and package description, checked before anything is built."""
import importlib.util
import json
import subprocess
import sys

import pytest

from saga2d.packaging.verify import local_server
from tools.package import PACKAGE


def package_check():
    spec = importlib.util.spec_from_file_location("package_check", PACKAGE.check)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def test_package_names_existing_entry_documents_and_diagnostics():
    assert PACKAGE.check.is_file()
    assert (PACKAGE.root / PACKAGE.package / "__main__.py").is_file()
    for origin in PACKAGE.documents.values():
        assert (PACKAGE.root / origin).is_file(), origin


@pytest.mark.slow
def test_shipped_smoke_accepts_authority_movement_and_seat_rejoin():
    """The exact frozen diagnostic uses production room rules and both real clients.

    The shipped smoke runs its whole online journey against a real server, over a second: the slow tier."""
    with local_server(PACKAGE.online) as endpoint:
        result = package_check().online_smoke(endpoint)
    assert result == {"create_join": True, "foreign_order_rejected": True, "authoritative_movement": True,
                      "private_seat_rejoin": True, "ranked_identity": True, "global_production": True,
                      "automatic_plan_builder": True, "assembly_point": True, "cancel_plans": True}


NATIVE_JOURNEY = """\
import faulthandler
import importlib.util
import json
import sys
from pathlib import Path
print("[DEBUG-native-timeout] traceback timer armed", flush=True)
faulthandler.dump_traceback_later(90, repeat=True)
root, check, frames, report, endpoint = sys.argv[1:6]
sys.path.insert(0, root)
spec = importlib.util.spec_from_file_location("package_check", check)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
info = {"source_commit": "source-check", "version": "0.0-source",
        "executable": "source-native-check", "executable_sha256": "source"}
result = checker.native_journey(Path(frames), endpoint, info)
faulthandler.cancel_dump_traceback_later()
Path(report).write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
"""


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "darwin", reason="source native smoke needs an awake Mac display")
def test_native_clipboard_smoke_creates_a_casual_room(tmp_path):
    """The single-profile clipboard journey must stay casual: a rated room refuses its second seat.

    Real pyglet inputs drive the packaged journey from source (with declared placeholder build
    metadata) against a real loopback authority in a separate process, since the journey compiles
    the simulation globally: needs an awake display and about a minute, so the slow tier, Mac only
    (other native CI checks the frozen app itself)."""
    with local_server(PACKAGE.online) as endpoint:
        frames, report = tmp_path / "native.png", tmp_path / "native.json"
        process = subprocess.run(
            [sys.executable, "-c", NATIVE_JOURNEY,
             str(PACKAGE.root), str(PACKAGE.check), str(frames), str(report), endpoint],
            cwd=PACKAGE.root, capture_output=True, text=True, timeout=280)
    assert process.returncode == 0, (process.stdout + process.stderr)[-3000:]
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["passed"] is True
    for key in ("native_multiplayer_input", "native_clipboard_join", "live_match_menu",
                "native_settlement_planning", "start_after_resize", "compiled_simulation",
                "native_campaign", "campaign_autosave_load"):
        assert result[key] is True
    assert result["source_commit"] == "source-check" and result["backend"] == "pyglet"
    for name in result["images"]:
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), name
