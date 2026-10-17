"""Historical clients against a current authoritative server, over real sockets and processes."""

import json
from importlib.metadata import version
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/check_network_client.py"


@pytest.fixture
def client_source(tmp_path):
    """A separate source tree: it cannot accidentally inherit the current package's decoder."""
    package = tmp_path / "client/warband"
    package.mkdir(parents=True)
    shutil.copyfile(ROOT / "warband/__init__.py", package / "__init__.py")
    shutil.copytree(ROOT / "warband/sim", package / "sim", ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd"))
    shutil.copytree(ROOT / "warband/assets/constants", package / "assets/constants")
    return package.parent


def probe(source, *arguments):
    return subprocess.run([sys.executable, str(CLI), "--client-source", str(source), *arguments],
                          cwd=ROOT, capture_output=True, text=True, timeout=45)


@pytest.mark.slow
def test_separate_client_source_plays_watches_and_resumes(client_source):
    """A copied decoder reads the live server through all supported roles.

    A dedicated server plus client process and movement on the real clock need the slow tier.
    """
    model = client_source / "warband/sim/model.py"
    model.write_text(model.read_text() + '\n'
                     '_original_from_dict_for_probe = World.from_dict\n'
                     'def _marked_decode_for_probe(cls, data):\n'
                     '    from pathlib import Path\n'
                     '    Path(__file__).with_name("decoded-by-fixture").write_text("decoded")\n'
                     '    return _original_from_dict_for_probe(data)\n'
                     'World.from_dict = classmethod(_marked_decode_for_probe)\n')

    result = probe(client_source, "--client-python", sys.executable, "--client-saga2d", version("saga2d"))

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert Path(report["client_model"]) == model
    assert model.with_name("decoded-by-fixture").read_text() == "decoded"
    assert set(report["checks"]) == {"create", "join", "move", "observe", "resume", "events"}
    assert report["game_id"] == "warband-v2"
    assert report["saga2d_version"] == version("saga2d")
    from saga2d.online import PROTOCOL
    assert report["transport_protocol"] == PROTOCOL
    assert report["resumed_tick"] >= report["moved_tick"] > 0
    assert "resume_token" not in result.stdout


@pytest.mark.slow
def test_incompatible_historical_world_decoder_fails_the_check(client_source):
    """A decoder that cannot consume the payload must fail the CLI, rather than borrowing today's decoder.

    It starts a real server and separate historical client process, so needs the slow tier.
    """
    model = client_source / "warband/sim/model.py"
    model.write_text(model.read_text() + '\n'
                     'def _incompatible_decode_for_probe(cls, data):\n'
                     '    raise ValueError("historical world decoder rejected current payload")\n'
                     'World.from_dict = classmethod(_incompatible_decode_for_probe)\n')

    result = probe(client_source)

    assert result.returncode != 0
    assert "historical world decoder rejected current payload" in result.stderr
    assert not result.stdout


@pytest.mark.slow
def test_event_fields_unknown_to_a_historical_client_fail_the_check(client_source):
    """A real public event must reach the old event constructor, including newly added fields.

    It plays a real server match through a historical client subprocess, so needs the slow tier.
    """
    model = client_source / "warband/sim/model.py"
    model.write_text(model.read_text() + '\n@dataclass\nclass Event:\n    kind: str\n    pos: Point\n')

    result = probe(client_source)

    assert result.returncode != 0
    assert "unexpected keyword argument" in result.stderr
    assert not result.stdout


@pytest.mark.slow
@pytest.mark.parametrize('edit,error', [
    ('BUFFS.pop("bleeding")', 'unknown Buff values: bleeding'),
    ('BUFFS["retired_condition"] = BUFFS["bleeding"]', 'removed Buff values: retired_condition'),
])
def test_content_catalogs_stay_compatible_in_both_directions(client_source, edit, error):
    """A new buff can break later gameplay even when the initial map carries no conditions.

    It runs the CLI's server and historical client subprocesses, so needs the slow tier.
    """
    rules = client_source / "warband/sim/rules.py"
    rules.write_text(rules.read_text() + '\n' + edit + '\n')

    result = probe(client_source)

    assert result.returncode != 0
    assert error in result.stderr
    assert not result.stdout


@pytest.mark.slow
def test_historical_transport_pin_is_checked_in_the_client_process(client_source):
    """The probe must never silently test a newer transport instead of the historical pinned one.

    It starts the real server and historical interpreter, so needs the slow tier.
    """
    result = probe(client_source, "--client-saga2d", "0.0.0")

    assert result.returncode != 0
    assert f"historical client requires Saga2D 0.0.0, found {version('saga2d')}" in result.stderr
    assert not result.stdout
