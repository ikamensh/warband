"""The release compatibility review describes the actual inputs it approves."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from warband.online.protocol import GAME_ID

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/network_compatibility.py'


@pytest.fixture
def source(tmp_path):
    for name in ('uv.lock',):
        shutil.copyfile(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / '.github', tmp_path / '.github')
    shutil.copytree(ROOT / 'warband', tmp_path / 'warband', ignore=shutil.ignore_patterns('assets', '__pycache__'))
    shutil.copytree(ROOT / 'warband/assets/constants', tmp_path / 'warband/assets/constants')
    ledger_path = tmp_path / '.github/network-compatibility.json'
    ledger = json.loads(ledger_path.read_text())
    unsupported = {entry['source_commit'] for entry in ledger.pop('historical_incompatibilities', [])}
    ledger['clients'] = [client for client in ledger['clients'] if client['source_commit'] not in unsupported]
    ledger_path.write_text(json.dumps(ledger))
    return tmp_path


def run(root, *args):
    return subprocess.run([sys.executable, str(CLI), '--root', str(root), *args], capture_output=True, text=True)


def test_changed_rules_need_a_review_but_a_compatible_review_keeps_old_clients(source):
    """A source change requires an explanation; accepting it does not retire the pinned old client."""
    ledger = source / '.github/network-compatibility.json'
    before = json.loads(ledger.read_text())
    path = source / 'warband/sim/model.py'
    path.write_text(path.read_text() + '\n# An internal fix without a wire change.\n')
    result = run(source, 'check')
    assert result.returncode != 0 and 'unreviewed' in result.stderr.lower()
    recorded = run(source, 'record', '--effect', 'compatible', '--reason', 'Internal fix; snapshots and orders keep their meaning.')
    assert recorded.returncode == 0, recorded.stderr
    assert run(source, 'check').returncode == 0
    after = json.loads(ledger.read_text())
    assert after['clients'] == before['clients']
    assert after['reviews'][:-1] == before['reviews']
    assert after['reviews'][-1]['game_id'] == before['reviews'][-1]['game_id']


@pytest.mark.parametrize('effect,advance,allowed', [
    ('compatible', 1, False),
    ('breaking', 0, False),
    ('breaking', 2, False),
    ('breaking', 1, True),
])
def test_only_a_recorded_break_can_advance_the_network_identity(source, effect, advance, allowed):
    """A release number cannot accidentally drop old clients; an actual break has an explicit new identity."""
    path = source / 'warband/online/protocol.py'
    new_id = f"warband-v{int(GAME_ID.removeprefix('warband-v')) + advance}"
    path.write_text(path.read_text().replace(GAME_ID, new_id) + '\n# reviewed edit\n')
    ledger = source / '.github/network-compatibility.json'
    original = ledger.read_bytes()
    result = run(source, 'record', '--effect', effect, '--reason', 'A deliberate protocol decision.')
    assert (result.returncode == 0) == allowed, result.stderr
    if allowed:
        assert run(source, 'check').returncode == 0
        assert json.loads(run(source, 'matrix').stdout) == {'include': []}
    else:
        assert ledger.read_bytes() == original


@pytest.mark.parametrize('name', ['warband/online/snapshot.py', 'warband/ui/multiplayer.py', 'warband/__main__.py',
                                  'warband/assets/constants/units.toml', '.github/release-pins.json'])
def test_wire_content_consumers_and_runtime_cannot_change_without_review(source, name):
    """Both sides of the wire, content catalogs, and Python/runtime pins are review inputs."""
    path = source / name
    if name.endswith('.json'):
        pins = json.loads(path.read_text())
        pins['python'] = '3.13.3'
        path.write_text(json.dumps(pins))
    else:
        path.write_text(path.read_text() + '\n# changed input\n')
    result = run(source, 'check')
    assert result.returncode != 0 and 'Unreviewed' in result.stderr


def test_art_and_release_counter_changes_do_not_require_a_network_break(source):
    """Pure presentation and package numbering are independent of network compatibility."""
    (source / 'warband/art/textures.py').write_text('# Different art\n')
    path = source / '.github/release-pins.json'
    pins = json.loads(path.read_text())
    pins['version_run_base'] += 1
    path.write_text(json.dumps(pins))
    assert run(source, 'check').returncode == 0


def test_runtime_clients_and_authority_share_the_reviewed_identity():
    """The public registry, human clients, AI clients and installed transport agree."""
    from saga2d.online import PROTOCOL
    from warband.online.authority import ONLINE
    from warband.online.protocol import GAME_ID, PROTOCOL as TRANSPORT
    from warband.online.online_ai import GAME_ID as AI_ID
    from warband.ui.multiplayer import GAME_ID as HUMAN_ID
    from warband.__main__ import GAME_ID as CLI_ID

    assert list(ONLINE) == [GAME_ID] and GAME_ID == HUMAN_ID == AI_ID == CLI_ID
    assert TRANSPORT == PROTOCOL


def test_cli_follows_a_new_network_identity_without_loading_the_simulation(source):
    """The next breaking release must move CLI players with menu players, before simulation selection."""
    protocol = source / 'warband/online/protocol.py'
    future_id = f"warband-v{int(GAME_ID.removeprefix('warband-v')) + 1}"
    protocol.write_text(protocol.read_text().replace(GAME_ID, future_id))
    result = subprocess.run([
        sys.executable, '-c',
        'import sys; from warband.__main__ import GAME_ID; '
        'assert "warband.sim" not in sys.modules; print(GAME_ID)',
    ], cwd=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == future_id


@pytest.mark.parametrize('declaration', ['protocol', 'title'])
def test_a_historical_client_cannot_be_relabelled_as_a_new_epoch(source, declaration):
    """Overriding the game ID sent by the probe cannot manufacture old-client compatibility."""
    if declaration == 'title':
        (source / 'warband/online/protocol.py').unlink()
        (source / 'warband/ui/title.py').write_text(f'MatchSetupMenu("Warband", "{GAME_ID}", None, None)\n')
    future_id = f"warband-v{int(GAME_ID.removeprefix('warband-v')) + 1}"
    result = subprocess.run([
        sys.executable, '-c',
        'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
        'from check_retained_clients import client_contract; '
        'client_contract(Path(sys.argv[2]), {"game_id": sys.argv[3], "saga2d_version": "0.3.18"})',
        str(ROOT / 'tools'), str(source), future_id,
    ], capture_output=True, text=True)
    assert result.returncode != 0 and f'uses {GAME_ID}, not {future_id}' in result.stderr


@pytest.mark.slow
def test_a_git_comparison_keeps_the_review_and_client_history(source):
    """Real Git history protects old decisions and retained clients; committing a repository needs a process."""
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()

    git('init', '-q')
    git('config', 'user.name', 'Compatibility test')
    git('config', 'user.email', 'compatibility@example.test')
    git('add', '.')
    git('commit', '-qm', 'baseline')
    base = git('rev-parse', 'HEAD')
    path = source / 'warband/sim/model.py'
    path.write_text(path.read_text() + '\n# compatible internal change\n')
    assert run(source, 'record', '--effect', 'compatible', '--reason', 'No wire change.').returncode == 0
    assert run(source, 'check', '--base', base).returncode == 0
    ledger = source / '.github/network-compatibility.json'
    changed = json.loads(ledger.read_text())
    changed['reviews'][0]['reason'] = 'Rewritten history'
    ledger.write_text(json.dumps(changed))
    result = run(source, 'check', '--base', base)
    assert result.returncode != 0 and 'retained unchanged' in result.stderr


@pytest.mark.slow
def test_only_a_pre_policy_break_can_correct_a_historical_support_claim(source):
    """Real Git chronology admits a false initial baseline correction, never a future client retirement."""
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()

    path = source / '.github/network-compatibility.json'
    ledger = json.loads(path.read_text())
    path.unlink()
    git('init', '-q')
    git('config', 'user.name', 'Compatibility test')
    git('config', 'user.email', 'compatibility@example.test')
    git('add', '.')
    git('commit', '-qm', 'original client release')
    original = git('rev-parse', 'HEAD')
    marker = source / 'wire-history.txt'
    marker.write_text('A server break before compatibility tracking.\n')
    git('add', str(marker))
    git('commit', '-qm', 'historical incompatible server')
    historical_break = git('rev-parse', 'HEAD')
    representative = ledger['clients'][-1]
    old_client = {**representative, 'source_commit': original}
    supported_client = {**representative, 'source_commit': historical_break}
    ledger['clients'] = [old_client, supported_client]
    path.write_text(json.dumps(ledger))
    git('add', str(path))
    git('commit', '-qm', 'begin compatibility policy')
    policy = git('rev-parse', 'HEAD')

    correction = {'source_commit': original, 'first_incompatible_commit': historical_break,
                  'reason': 'The original client could not decode a camp introduced before tracking began.'}
    ledger['historical_incompatibilities'] = [correction]
    path.write_text(json.dumps(ledger))
    result = run(source, 'check')
    assert result.returncode == 0, result.stderr
    assert json.loads(run(source, 'matrix').stdout) == {'include': [supported_client]}
    assert json.loads(path.read_text())['clients'] == [old_client, supported_client]
    ledger['historical_incompatibilities'] = [{**correction, 'first_incompatible_commit': original}]
    path.write_text(json.dumps(ledger))
    result = run(source, 'check')
    assert result.returncode != 0 and 'client must precede' in result.stderr
    ledger['historical_incompatibilities'] = [correction]
    path.write_text(json.dumps(ledger))
    git('add', str(path))
    git('commit', '-qm', 'correct the historical support claim')
    corrected = git('rev-parse', 'HEAD')

    ledger['historical_incompatibilities'] = [{**correction, 'reason': 'Rewritten history'}]
    path.write_text(json.dumps(ledger))
    result = run(source, 'check', '--base', corrected)
    assert result.returncode != 0 and 'retained unchanged' in result.stderr

    marker.write_text('A future server break needs a new game identity.\n')
    git('add', str(marker))
    git('commit', '-qm', 'future server change')
    future = git('rev-parse', 'HEAD')
    for incompatible in (policy, future):
        ledger['historical_incompatibilities'] = [{**correction, 'first_incompatible_commit': incompatible}]
        path.write_text(json.dumps(ledger))
        result = run(source, 'check')
        assert result.returncode != 0 and 'before compatibility tracking' in result.stderr

    model = source / 'warband/sim/model.py'
    model.write_text(model.read_text() + '\n# A compatible internal change.\n')
    before = path.read_bytes()
    result = run(source, 'record', '--effect', 'compatible', '--reason', 'No wire change.')
    assert result.returncode != 0 and 'before compatibility tracking' in result.stderr
    assert path.read_bytes() == before
