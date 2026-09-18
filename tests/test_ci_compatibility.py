"""Compatibility follows authoritative inputs, independent of visual/client changes."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/ci_compatibility.py"


def contract(root):
    return subprocess.run([sys.executable, str(CLI), "--root", str(root)], capture_output=True, text=True)


@pytest.fixture
def source(tmp_path):
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / ".github", tmp_path / ".github")
    shutil.copytree(ROOT / "warband", tmp_path / "warband", ignore=shutil.ignore_patterns("assets", "__pycache__"))
    return tmp_path


def test_contract_covers_simulation_without_loading_client_scenes(source):
    """The dedicated server entry point runs independently of the game view; its inputs are inspectable offline."""
    result = subprocess.run([sys.executable, "-c",
                             "import sys; from warband.authority import ONLINE; "
                             "assert 'warband.scene' not in sys.modules; assert list(ONLINE) == ['warband-v2']; "
                             "from tools.package import PACKAGE; assert PACKAGE.online == 'warband.authority:ONLINE'"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = contract(source)
    assert result.returncode == 0, result.stderr
    original = json.loads(result.stdout)
    files = set(original["files"])
    assert {"warband/authority.py", "warband/model.py", "warband/mapgen.py", "warband/rules.py",
            "warband/races.py", "warband/settlement.py", "warband/worker_ai.py", "warband/path.py"} <= files
    assert "warband/scene.py" not in files and "warband/textures.py" not in files
    (source / "warband/textures.py").write_text("raise RuntimeError('Artwork need not import for compatibility')\n")
    assert json.loads(contract(source).stdout) == original


@pytest.mark.parametrize("snippet", [
    "import importlib; importlib.import_module('warband.rules')",
    "__import__('warband.rules')",
    "exec('import warband.rules')",
    "eval('123')",
    "RULES = open('balance.json').read()",
    "from pathlib import Path; RULES = Path('balance.json').read_text()",
    "from saga2d import SaveManager; RULES = SaveManager().load('balance')",
    "import unpinned_simulation_library",
])
def test_untracked_authoritative_inputs_are_rejected(source, snippet):
    """Dynamic code, file-backed rules and untracked imports require explicit contract support."""
    path = source / "warband/authority.py"
    path.write_text(path.read_text() + "\n" + snippet + "\n")
    result = contract(source)
    assert result.returncode != 0 and "Unsupported authoritative" in result.stderr
    assert not result.stdout


@pytest.mark.slow
def test_every_authoritative_source_byte_and_runtime_pin_affects_identity(source):
    """A reviewed baseline cannot silently survive changes to rules, orders, maps, workers or runtime.

    It rehashes the contract once per source file and pin, over a second: the slow tier."""
    original = json.loads(contract(source).stdout)
    for name in original["files"]:
        path = source / name
        data = path.read_bytes()
        path.write_bytes(data + b"\n# A changed authoritative input.\n")
        assert json.loads(contract(source).stdout)["sha256"] != original["sha256"], name
        path.write_bytes(data)
    pins_path = source / ".github/release-pins.json"
    data = pins_path.read_bytes()
    pins = json.loads(data)
    pins["python"] = "3.13.3"
    pins_path.write_text(json.dumps(pins))
    assert json.loads(contract(source).stdout)["sha256"] != original["sha256"]
    pins_path.write_bytes(data)
    lock = source / "uv.lock"
    text = lock.read_text()
    assert 'name = "websockets"\nversion = "17.1"' in text
    lock.write_text(text.replace('name = "websockets"\nversion = "17.1"', 'name = "websockets"\nversion = "17.2"'))
    assert json.loads(contract(source).stdout)["sha256"] != original["sha256"]


def test_new_local_imports_and_package_initializers_join_contract_automatically(source):
    """Nested imports, relative imports and function-local imports all add source dependencies without a file list."""
    path = source / "warband/rules.py"
    path.write_text(path.read_text() + "\nfrom warband.balance import bonus\n")
    package = source / "warband/balance"
    package.mkdir()
    (package / "__init__.py").write_text("from .bonus import bonus\n")
    (package / "bonus.py").write_text("def bonus():\n    from .. import tuning\n    return tuning.VALUE\n")
    tuning = source / "warband/tuning.py"
    tuning.write_text("VALUE = 1\n")
    original = json.loads(contract(source).stdout)
    assert {"warband/balance/__init__.py", "warband/balance/bonus.py", "warband/tuning.py"} <= original["files"].keys()
    tuning.write_text("VALUE = 2\n")
    assert json.loads(contract(source).stdout)["sha256"] != original["sha256"]


def test_import_resolution_prefers_a_package_over_a_same_named_module(source):
    """Python loads the package when both exist; hashing only the old module would miss active rules."""
    package = source / "warband/rules"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n")
    result = contract(source)
    assert result.returncode == 0, result.stderr
    files = json.loads(result.stdout)["files"]
    assert "warband/rules/__init__.py" in files and "warband/rules.py" not in files
