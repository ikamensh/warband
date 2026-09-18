"""Describe authoritative simulation inputs without importing or executing the game."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "warband.authority:ONLINE"
# Deliberately narrow: a new I/O, loader or third-party dependency needs review
# of how its inputs enter this contract. This is a source convention, not a
# sandbox for hostile Python; code review still owns reflective/dynamic tricks.
STDLIB = {"__future__", "collections", "copy", "dataclasses", "enum", "functools",
          "heapq", "inspect", "itertools", "math", "random", "typing"}
ENGINE_IMPORTS = {"saga2d": {"CommandError"},
                  "saga2d.server.games": {"GameSpec", "option_choice", "option_int", "option_keys", "option_seed"}}
UNTRACKED = {"__import__", "eval", "exec", "open", "read_bytes", "read_text", "import_module"}


def fingerprint(root: Path) -> dict:
    """Hash the static game import closure and the locked server runtime."""
    def module_file(module):
        path = root.joinpath(*module.split("."))
        if (path / "__init__.py").is_file():
            return path / "__init__.py"
        if path.with_suffix(".py").is_file():
            return path.with_suffix(".py")
        raise ValueError(f"Missing authoritative module: {module}")

    pending = [REGISTRY.split(":")[0]]
    files = {}
    while pending:
        module = pending.pop()
        path = module_file(module)
        name = path.relative_to(root).as_posix()
        if name in files:
            continue
        source = path.read_bytes()
        files[name] = hashlib.sha256(source).hexdigest()
        parts = module.split(".")
        pending.extend(".".join(parts[:i]) for i in range(1, len(parts)))
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for node in ast.walk(ast.parse(source, filename=name)):
            if ((isinstance(node, ast.Name) and node.id in UNTRACKED)
                    or (isinstance(node, ast.Attribute) and node.attr in UNTRACKED)):
                raise ValueError(f"Unsupported authoritative input in {name}:{node.lineno}: {ast.unparse(node)}")
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                imports = [base]
                # In `from package import module`, names can be modules or attributes.
                for alias in node.names:
                    child = root.joinpath(*base.split("."), alias.name)
                    if child.with_suffix(".py").is_file() or (child / "__init__.py").is_file():
                        imports.append(base + "." + alias.name)
            else:
                continue
            for item in imports:
                if item == "warband" or item.startswith("warband."):
                    pending.append(item)
                elif item.split(".")[0] in STDLIB:
                    continue
                elif (isinstance(node, ast.ImportFrom) and item in ENGINE_IMPORTS
                      and {alias.name for alias in node.names} <= ENGINE_IMPORTS[item]):
                    continue
                else:
                    raise ValueError(f"Unsupported authoritative import in {name}:{node.lineno}: {ast.unparse(node)}")

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = {}
    pending = ["saga2d"]
    while pending:
        name = pending.pop()
        if name in packages:
            continue
        matches = [item for item in lock["package"] if item["name"] == name]
        if len(matches) != 1 or matches[0]["source"] != {"registry": "https://pypi.org/simple"}:
            raise ValueError(f"Authoritative runtime must have one exact PyPI lock: {name}")
        item = matches[0]
        packages[name] = item["version"]
        pending.extend(dependency["name"] for dependency in item.get("dependencies", []))
    result = {"schema_version": 1, "registry": REGISTRY, "files": dict(sorted(files.items())),
              "python": json.loads((root / ".github/release-pins.json").read_text())["python"],
              "packages": dict(sorted(packages.items()))}
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    return {**result, "sha256": hashlib.sha256(encoded).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(fingerprint(args.root), sort_keys=True, indent=2))
