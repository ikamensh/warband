"""Record compatibility decisions separately from exact server deployment inputs.

    python tools/network_compatibility.py check
    python tools/network_compatibility.py record --effect compatible --reason 'Why old clients still work'
    python tools/network_compatibility.py matrix

This tool uses only the standard library, so CI can check a review before
installing the game. Source hashes identify what was reviewed; they do not
decide whether two releases can play together.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ci_compatibility import fingerprint

ROOT = Path(__file__).resolve().parents[1]
LEDGER = '.github/network-compatibility.json'
# The authority's closure already includes rules, content, snapshots and save
# decoders. Also review the code that sends commands or consumes snapshots.
CLIENT_FILES = (
    'warband/online/online_ai.py', 'warband/ui/multiplayer.py',
    'warband/ui/match.py', 'warband/ui/observer.py', 'warband/ui/scene.py',
    'warband/ui/view.py', 'warband/ui/controls.py', 'warband/ui/spellbar.py',
    'warband/ui/tech.py',
)


def identity(root: Path) -> dict:
    """Read literal identities without importing the engine or game."""
    tree = ast.parse((root / 'warband/online/protocol.py').read_text())
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    game_id, protocol = values['GAME_ID'], values['PROTOCOL']
    if not isinstance(game_id, str) or not re.fullmatch(r'warband-v[1-9]\d*', game_id):
        raise ValueError('GAME_ID must be warband-vN')
    if type(protocol) is not int or protocol < 1:
        raise ValueError('PROTOCOL must be a positive integer')
    return {'game_id': game_id, 'protocol': protocol}


def inputs(root: Path) -> dict:
    """The exact reviewed authority/runtime and client consumers."""
    return {'authority': fingerprint(root)['sha256'], 'client': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in CLIENT_FILES}}


def validate(ledger: dict) -> None:
    """History records each decision and retains representatives of old releases."""
    if set(ledger) != {'schema_version', 'clients', 'reviews'} or ledger['schema_version'] != 1:
        raise ValueError('Unsupported network compatibility ledger')
    reviews = ledger['reviews']
    if not isinstance(reviews, list) or not reviews:
        raise ValueError('A compatibility baseline is required')
    previous = None
    for review in reviews:
        if set(review) != {'game_id', 'protocol', 'effect', 'reason', 'inputs'}:
            raise ValueError('Invalid compatibility review')
        if not isinstance(review['reason'], str) or not review['reason'].strip():
            raise ValueError('Explain why this change preserves or breaks old clients')
        current = {key: review[key] for key in ('game_id', 'protocol')}
        if not isinstance(current['game_id'], str) or not re.fullmatch(r'warband-v[1-9]\d*', current['game_id']):
            raise ValueError('Invalid reviewed game id')
        if type(current['protocol']) is not int or current['protocol'] < 1:
            raise ValueError('Invalid reviewed transport protocol')
        if previous is None:
            if review['effect'] != 'baseline':
                raise ValueError('The first compatibility review must be a baseline')
        elif review['effect'] == 'compatible':
            if current != previous:
                raise ValueError('A compatible change must keep the game id and transport protocol')
        elif review['effect'] == 'breaking':
            if int(current['game_id'].split('-v')[1]) != int(previous['game_id'].split('-v')[1]) + 1:
                raise ValueError('A breaking change must advance GAME_ID by one')
            if current['protocol'] < previous['protocol']:
                raise ValueError('The transport protocol cannot go backwards')
        else:
            raise ValueError('Choose compatible or breaking for each change')
        reviewed = review['inputs']
        if (set(reviewed) != {'authority', 'client'} or not reviewed['client']
                or not all(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest)
                           for digest in [reviewed['authority'], *reviewed['client'].values()])):
            raise ValueError('Invalid reviewed input hashes')
        previous = current
    if not isinstance(ledger['clients'], list) or not ledger['clients']:
        raise ValueError('At least one pinned historical client is required')
    for client in ledger['clients']:
        if (set(client) != {'source_commit', 'saga2d_version', 'game_id', 'protocol'}
                or not re.fullmatch(r'[0-9a-f]{40}', client['source_commit'])
                or not re.fullmatch(r'\d+\.\d+\.\d+', client['saga2d_version'])
                or not any(all(client[key] == review[key] for key in ('game_id', 'protocol')) for review in reviews)):
            raise ValueError('Invalid pinned historical client')
    if (reviews[-1]['effect'] != 'breaking'
            and not any(all(client[key] == previous[key] for key in ('game_id', 'protocol')) for client in ledger['clients'])):
        raise ValueError('Pin a client source and engine for the current network identity')


def check(root: Path, base: str | None = None) -> dict:
    ledger = json.loads((root / LEDGER).read_text())
    validate(ledger)
    latest = ledger['reviews'][-1]
    if any(latest[key] != value for key, value in identity(root).items()) or latest['inputs'] != inputs(root):
        raise ValueError('Unreviewed network inputs: record a compatible or breaking decision with a reason')
    if base and set(base) != {'0'}:
        names = subprocess.check_output(['git', 'ls-tree', '--name-only', base, '--', LEDGER], cwd=root, text=True)
        if names.strip():
            old = json.loads(subprocess.check_output(['git', 'show', f'{base}:{LEDGER}'], cwd=root, text=True))
            if ledger['reviews'][:len(old['reviews'])] != old['reviews'] or ledger['clients'][:len(old['clients'])] != old['clients']:
                raise ValueError('Compatibility history and historical clients must be retained unchanged')
    return ledger


def record(root: Path, effect: str, reason: str) -> dict:
    path = root / LEDGER
    ledger = json.loads(path.read_text())
    review = {**identity(root), 'effect': effect, 'reason': reason, 'inputs': inputs(root)}
    if review['inputs'] == ledger['reviews'][-1]['inputs']:
        raise ValueError('No network inputs changed since the last review')
    ledger['reviews'].append(review)
    validate(ledger)
    path.write_text(json.dumps(ledger, indent=2) + '\n')
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    checking = commands.add_parser('check')
    checking.add_argument('--base', help='Git ref whose review history must be preserved')
    recording = commands.add_parser('record')
    recording.add_argument('--effect', choices=('compatible', 'breaking'), required=True)
    recording.add_argument('--reason', required=True)
    commands.add_parser('matrix')
    args = parser.parse_args()
    if args.command == 'record':
        result = record(args.root, args.effect, args.reason)
    else:
        ledger = check(args.root, getattr(args, 'base', None))
        current = identity(args.root)
        clients = [client for client in ledger['clients'] if all(client[key] == value for key, value in current.items())]
        result = {'include': clients} if args.command == 'matrix' else {
            **current, 'effect': ledger['reviews'][-1]['effect'], 'historical_clients': len(clients)}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
