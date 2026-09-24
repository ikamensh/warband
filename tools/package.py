"""Build, verify and install the standalone Warband app.

    uv run --extra package python tools/package.py build --version 0.1.0 --installer
    uv run --extra package python tools/package.py verify dist/warband --native
    uv run --extra package python tools/package.py install

A build carries the compiled simulation of its sources (``warband.league.fastsim``), compiled here, since a
player has no compiler: see :func:`compiled_simulation`.
"""
from contextlib import contextmanager
from pathlib import Path
import shutil
import sys
from typing import Iterator

from saga2d.packaging import GamePackage, main
from warband.league import fastsim

ROOT = Path(__file__).resolve().parents[1]

PACKAGE = GamePackage(
    game="warband", product="Warband", package="warband", online="warband.online.authority:ONLINE",
    bundle_id="org.saga2d.warband", installer_id="{B51768BC-40A4-4705-BE86-D55131C7B414}",
    hiddenimports=("saga2d.backends.pyglet_backend", "warband.art.textures", "warband.audio.sound", "websockets.asyncio.client"),
    documents={"windows-warband.md": "docs/windows-warband.md", "warband-play-together.md": "docs/warband-play-together.md"},
    root=ROOT, check=ROOT / "packaging" / "package_check.py", icon=ROOT / "warband" / "assets" / "icon.png",
)


@contextmanager
def compiled_simulation() -> Iterator[Path]:
    """The compiled simulation of these sources in the package's assets while it is frozen, where the frozen app
    finds it (``fastsim.SHIPPED``): the freeze ships the assets folder whole, and PyInstaller signs the extension
    modules in it as the binaries they are.  The checkout's copy goes again afterwards (it is git-ignored)."""
    build = fastsim.build()
    if fastsim.SHIPPED.exists():  # left by a freeze that was interrupted
        shutil.rmtree(fastsim.SHIPPED)
    shipped = shutil.copytree(build, fastsim.SHIPPED / build.name)
    try:
        yield shipped
    finally:
        shutil.rmtree(fastsim.SHIPPED)


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        with compiled_simulation():
            main(PACKAGE)
    else:
        main(PACKAGE)
