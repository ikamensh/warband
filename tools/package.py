"""Build, verify and install the standalone Warband app.

    uv run --extra package python tools/package_warband.py build --version 0.1.0 --installer
    uv run --extra package python tools/package_warband.py verify dist/warband --native
    uv run --extra package python tools/package_warband.py install
"""
from pathlib import Path

from saga2d.packaging import GamePackage, main

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = GamePackage(
    game="warband", product="Warband", package="warband", online="warband.multiplayer:ONLINE",
    bundle_id="org.saga2d.warband", installer_id="{B51768BC-40A4-4705-BE86-D55131C7B414}",
    hiddenimports=("saga2d.backends.pyglet_backend", "warband.textures", "warband.sound", "websockets.asyncio.client"),
    documents={"windows-warband.md": "docs/windows-warband.md", "warband-play-together.md": "docs/warband-play-together.md"},
    root=ROOT, check=ROOT / "packaging" / "warband_package_check.py",
)

if __name__ == "__main__":
    main(PACKAGE)
