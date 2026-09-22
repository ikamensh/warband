"""The package's folders keep to their layers (WB-041): each imports only the folders its row allows, the simulation
nothing but itself, and ``warband/`` holds nothing but its two entry modules, its assets and the folders."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "warband"
FOLDERS = {"sim", "brains", "records", "league", "online", "art", "audio", "ui", "story"}
MAY_IMPORT = {
    "sim": {"sim"},  # what the online authority runs: the contract hashes it all
    "brains": {"sim", "brains"},
    "records": {"sim", "records"},
    "league": {"sim", "brains", "league"},
    "online": {"sim", "brains", "online"},
    "art": {"sim", "art"},
    "audio": {"sim", "audio"},
    "ui": FOLDERS,
    "story": FOLDERS,
}


def imported_folders(path: Path, folder: str) -> set[str]:
    """The folders a module imports from, at its top or inside a function."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 1:
            found.add(folder)
            continue
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module] if node.module != "warband" else [f"warband.{alias.name}" for alias in node.names]
        else:
            assert not isinstance(node, ast.ImportFrom), f"{path.name}:{node.lineno}: an import from above the folder"
            continue
        found.update(module.split(".")[1] for module in modules if module.startswith("warband."))
    return found


def test_the_package_holds_its_entry_modules_its_assets_and_the_folders() -> None:
    assert {p.name for p in PACKAGE.iterdir() if p.name != "__pycache__"} == {"__init__.py", "__main__.py", "assets",
                                                                            "constants"} | FOLDERS


@pytest.mark.parametrize("folder", sorted(FOLDERS))
def test_a_folder_imports_only_what_its_row_allows(folder: str) -> None:
    wrong = {path.name: sorted(imported - MAY_IMPORT[folder])
             for path in sorted((PACKAGE / folder).glob("*.py")) if (imported := imported_folders(path, folder)) - MAY_IMPORT[folder]}
    assert not wrong, f"warband/{folder} may import {sorted(MAY_IMPORT[folder])} only"


@pytest.mark.parametrize("init", ["__init__.py", *(f"{folder}/__init__.py" for folder in sorted(FOLDERS))])
def test_an_init_is_its_docstring_alone(init: str) -> None:
    """The contract hashes the package's and the simulation's and server's folders' own __init__.py, and the compiled
    simulation is attached after the folders are imported, so none of them imports anything."""
    body = ast.parse((PACKAGE / init).read_text(encoding="utf-8")).body
    assert len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant), init
