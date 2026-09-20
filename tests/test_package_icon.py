"""Warband's own picture: what the builds carry, and what the running game wears (WB-026)."""
import importlib.util
from pathlib import Path

from saga2d.packaging import icon

ROOT = Path(__file__).resolve().parents[1]


def test_the_package_names_a_picture_the_engine_accepts():
    """The release build refuses a picture that is not square or under 1024 px; a replaced file fails here first."""
    spec = importlib.util.spec_from_file_location("package", ROOT / "tools" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PACKAGE.icon == ROOT / "warband" / "assets" / "icon.png"
    icon.load(module.PACKAGE.icon)


def test_the_running_game_wears_the_same_picture():
    """It lives in the package's assets, which a built game carries: the Dock and the taskbar draw it too."""
    from warband.__main__ import ICON

    assert ICON == ROOT / "warband" / "assets" / "icon.png"
    icon.load(ICON)
