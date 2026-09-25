"""A build of the compiled simulation is filed under a key of everything the compile reads (``fastsim.key``), so that
no edited source ever runs as an old build, locally or restored from CI's cache, which keys on it too.

The compile reads the compiled modules, every Warband module they import (``settlement.py`` and ``bred.py`` are not
compiled, and the C twins' ``_native.pyi`` and ``_native.c`` are not Python), the packages around them and its own
recipe; mypy would also read a configuration file, so the compile tells it to read none."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

from mypy.main import process_options

from warband.league import fastsim

PACKAGE = fastsim.PACKAGE


def read_by_the_compile() -> set[Path]:
    """The files under ``warband/`` the compile reads: :data:`fastsim.MODULES`, what they import of Warband's, on and
    on, a C extension's stub and source, the packages around each, and the recipe."""
    todo, seen, files = [f"warband.{module}" for module in fastsim.MODULES], set(), {PACKAGE / "league/fastsim.py"}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if "." in name:
            todo.append(name.rpartition(".")[0])  # its package
        base = PACKAGE.parent / name.replace(".", "/")
        found = [path for path in (base.with_suffix(".py"), base.with_suffix(".pyi"), base.with_suffix(".c"),
                                   base / "__init__.py") if path.is_file()]
        files.update(found)
        for path in (path for path in found if path.suffix != ".c"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]  # a module or a name
                else:
                    continue
                todo.extend(name for name in names if name.startswith("warband."))
    return files


def test_the_build_key_moves_with_every_file_the_compile_reads(tmp_path: Path, monkeypatch) -> None:
    copy = tmp_path / "warband"
    for path in read_by_the_compile():
        target = copy / path.relative_to(PACKAGE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    monkeypatch.setattr(fastsim, "PACKAGE", copy)
    before = fastsim.key()
    read = sorted(path.relative_to(PACKAGE) for path in read_by_the_compile())
    assert {"sim/settlement.py", "brains/bred.py", "sim/_native.pyi", "sim/_native.c"} <= {str(path) for path in read}
    for name in read:
        original = (copy / name).read_bytes()
        (copy / name).write_bytes(original + b"\n")
        assert fastsim.key() != before, f"an edited {name} would run as the old build"
        (copy / name).write_bytes(original)
    assert fastsim.key() == before


def test_the_compile_reads_no_mypy_configuration(tmp_path: Path, monkeypatch) -> None:
    """A ``[tool.mypy]`` section, a ``mypy.ini`` or the user's own file could change what mypyc makes, and no key
    hashes them: the compile's options leave every configuration file unread."""
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\ndisallow_untyped_defs = true\n", encoding="utf-8")
    (tmp_path / "m.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert process_options(["m.py"], mypyc=True)[1].disallow_untyped_defs  # read, without them
    assert not process_options([*fastsim.MYPY, "m.py"], mypyc=True)[1].disallow_untyped_defs
