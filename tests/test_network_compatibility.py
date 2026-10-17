"""The release compatibility review describes the actual inputs it approves."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/network_compatibility.py'


@pytest.fixture
def source(tmp_path):
    for name in ('uv.lock',):
        shutil.copyfile(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / '.github', tmp_path / '.github')
    shutil.copytree(ROOT / 'warband', tmp_path / 'warband', ignore=shutil.ignore_patterns('assets', '__pycache__'))
    shutil.copytree(ROOT / 'warband/assets/constants', tmp_path / 'warband/assets/constants')
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


@pytest.mark.parametrize('effect,new_id,allowed', [
    ('compatible', 'warband-v3', False),
    ('breaking', 'warband-v2', False),
    ('breaking', 'warband-v4', False),
    ('breaking', 'warband-v3', True),
])
def test_only_a_recorded_break_can_advance_the_network_identity(source, effect, new_id, allowed):
    """A release number cannot accidentally drop old clients; an actual break has an explicit new identity."""
    path = source / 'warband/online/protocol.py'
    path.write_text(path.read_text().replace('warband-v2', new_id) + '\n# reviewed edit\n')
    ledger = source / '.github/network-compatibility.json'
    original = ledger.read_bytes()
    result = run(source, 'record', '--effect', effect, '--reason', 'A deliberate protocol decision.')
    assert (result.returncode == 0) == allowed, result.stderr
    if allowed:
        assert run(source, 'check').returncode == 0
        assert json.loads(run(source, 'matrix').stdout) == {'include': []}
    else:
        assert ledger.read_bytes() == original


@pytest.mark.parametrize('name', ['warband/online/snapshot.py', 'warband/ui/multiplayer.py',
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

    assert list(ONLINE) == [GAME_ID] and GAME_ID == HUMAN_ID == AI_ID
    assert TRANSPORT == PROTOCOL


@pytest.mark.parametrize('declaration', ['protocol', 'title'])
def test_a_historical_client_cannot_be_relabelled_as_a_new_epoch(source, declaration):
    """Overriding the game ID sent by the probe cannot manufacture old-client compatibility."""
    if declaration == 'title':
        (source / 'warband/online/protocol.py').unlink()
        (source / 'warband/ui/title.py').write_text('MatchSetupMenu("Warband", "warband-v2", None, None)\n')
    result = subprocess.run([
        sys.executable, '-c',
        'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
        'from check_retained_clients import client_contract; '
        'client_contract(Path(sys.argv[2]), {"game_id": "warband-v3", "saga2d_version": "0.3.18"})',
        str(ROOT / 'tools'), str(source),
    ], capture_output=True, text=True)
    assert result.returncode != 0 and 'uses warband-v2, not warband-v3' in result.stderr


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
