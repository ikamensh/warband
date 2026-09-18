"""The builds carry Warband's own picture (WB-026)."""
import importlib.util
from pathlib import Path

from saga2d.packaging import icon

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_names_a_picture_the_engine_accepts():
    """The release build refuses a picture that is not square or under 1024 px; a replaced file fails here first."""
    spec = importlib.util.spec_from_file_location("package", ROOT / "tools" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PACKAGE.icon == ROOT / "packaging" / "icon.png"
    icon.load(module.PACKAGE.icon)
