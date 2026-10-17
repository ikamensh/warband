"""Exercise retained clients against this release's authority before packaging.

    python tools/check_retained_clients.py

Historical sources come from Git; each side runs its own exact Python and
locked Saga2D dependency closure. Temporary sources and environments are
removed on success or failure. No game installation or sibling checkout is
needed. ``--work-dir`` selects the parent for these temporary files.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from ci_compatibility import fingerprint
from network_compatibility import ROOT, check as check_ledger, identity, supported_clients

CLIENT_PATHS = ('warband/__init__.py', 'warband/sim', 'warband/online',
                'warband/ui/multiplayer.py', 'warband/ui/title.py',
                'warband/assets/constants', '.github/release-pins.json', 'uv.lock')


def client_contract(source: Path, client: dict) -> dict:
    """Verify the historical client's own identity before offering it to the server.

    Older releases declared GAME_ID in their multiplayer scene, or passed a
    literal to MatchSetupMenu in the title scene (the retained 0.2.232 client).
    Passing a newer ID to their transport must never count as compatibility.
    """
    protocol = source / 'warband/online/protocol.py'
    path = protocol if protocol.is_file() else source / 'warband/ui/multiplayer.py'
    tree = ast.parse(path.read_text())
    declarations = [node.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'GAME_ID' for target in node.targets)]
    if not declarations and not protocol.is_file():
        title = ast.parse((source / 'warband/ui/title.py').read_text())
        declarations = [node.args[1] for node in ast.walk(title) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == 'MatchSetupMenu'
                        and len(node.args) >= 2]
    if len(declarations) != 1:
        raise ValueError('Unsupported historical game identity declaration')
    game_id = ast.literal_eval(declarations[0])
    if game_id != client['game_id']:
        raise ValueError(f"Retained client uses {game_id}, not {client['game_id']}")
    contract = fingerprint(source)
    if contract['packages']['saga2d'] != client['saga2d_version']:
        raise ValueError('Retained client Saga2D pin differs from its lock')
    return contract


def runtime(contract: dict, directory: Path) -> Path:
    """Install exactly the runtime recorded by this source's release inputs."""
    subprocess.run(['uv', 'venv', '--python', contract['python'], str(directory)],
                   cwd=directory.parent, stdout=sys.stderr, check=True)
    python = directory / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    subprocess.run(['uv', 'pip', 'install', '--python', str(python), '--no-deps',
                    *(f'{name}=={version}' for name, version in contract['packages'].items())],
                   cwd=directory.parent, stdout=sys.stderr, check=True)
    return python


def check(root: Path, work_dir: Path | None = None) -> list[dict]:
    """Run every pinned client sharing the current reviewed network identity."""
    root = root.resolve()
    ledger = check_ledger(root)
    current = identity(root)
    clients = supported_clients(ledger)
    if not clients:
        return []
    reports = []
    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='warband-retained-clients-', dir=work_dir) as name:
        temporary = Path(name).resolve()
        server_python = runtime(fingerprint(root), temporary / 'server-runtime')
        for index, client in enumerate(clients):
            source = temporary / f'client-{index}'
            source.mkdir()
            archive = temporary / f'client-{index}.tar'
            with archive.open('wb') as output:
                subprocess.run(['git', 'archive', '--format=tar', client['source_commit'],
                                '--', *CLIENT_PATHS], cwd=root, stdout=output, check=True)
            with tarfile.open(archive) as bundle:
                bundle.extractall(source, filter='data')
            contract = client_contract(source, client)
            client_python = runtime(contract, temporary / f'client-runtime-{index}')
            result = subprocess.run(
                [str(server_python), str(root / 'tools/check_network_client.py'),
                 '--client-source', str(source), '--client-python', str(client_python),
                 '--client-saga2d', client['saga2d_version'], '--game-id', client['game_id']],
                cwd=root, stdout=subprocess.PIPE, text=True, check=True,
            )
            report = json.loads(result.stdout)
            if (report['transport_protocol'] != current['protocol']
                    or report['game_id'] != client['game_id']
                    or report['saga2d_version'] != client['saga2d_version']):
                raise ValueError('Retained client exercised a different network identity or engine')
            reports.append({'source_commit': client['source_commit'], **report})
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--work-dir', type=Path, help='parent directory for owned temporary files')
    args = parser.parse_args()
    print(json.dumps({'clients': check(args.root, args.work_dir)}, sort_keys=True))


if __name__ == '__main__':
    main()
