"""Local synthetic rollout and partial-failure recovery, not distributed atomicity."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from runbookops import corpus_control as control, corpus_rollout as rollout
from runbookops.corpus_release import create_release, verify_release
from runbookops.service import TriageService
from test_corpus_control import socket_path
from test_corpus_startup import _http, _server
from test_source_versions import data, DOCUMENT


def plan_for(release, expected, addresses):
    return {'release': str(release), 'manifest_sha256': verify_release(release).manifest_hash,
            'workers': [{'id': f'w{i}', 'socket': str(path), 'expected_corpus': expected}
                        for i, path in enumerate(addresses)]}


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_preflight_and_existing_journal_cannot_send_commands(data, tmp_path, monkeypatch):
    old = TriageService(data).snapshot.identity()
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'target')
    plan = plan_for(release, old, [tmp_path / 'one.sock', tmp_path / 'two.sock'])
    def forbidden(*args, **kwargs):
        pytest.fail('Rejected preflight contacted a worker')
    monkeypatch.setattr(rollout, 'refresh', forbidden)
    journal = tmp_path / 'journal.jsonl'
    duplicate = {**plan, 'workers': [plan['workers'][0], plan['workers'][0]]}
    with pytest.raises(ValueError, match='Duplicate'):
        rollout.run(json.dumps(duplicate).encode(), journal)
    assert not journal.exists()
    stale_pin = {**plan, 'manifest_sha256': '0' * 64}
    with pytest.raises(ValueError):
        rollout.run(json.dumps(stale_pin).encode(), journal)
    assert not journal.exists()
    journal.write_text('retained evidence\n')
    with pytest.raises(FileExistsError):
        rollout.run(json.dumps(plan).encode(), journal)
    assert journal.read_text() == 'retained evidence\n'
    for raw in (b' ' * (rollout.MAX_PLAN_BYTES + 1), b'{"workers":[],"workers":[]}'):
        with pytest.raises(ValueError):
            rollout.prepare(raw)


@pytest.mark.parametrize('failure', ['conflict', 'lost_reply'])
def test_partial_rollout_stops_without_retry_or_rollback(data, tmp_path, monkeypatch, failure):
    old = TriageService(data).snapshot.identity()
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'target')
    raw = json.dumps(plan_for(release, old, [tmp_path / f'{i}.sock' for i in range(3)])).encode()
    _, target = rollout.prepare(raw)
    calls = []
    def refresh(address, release, pin, *, expected_corpus):
        assert expected_corpus == old
        calls.append(address)
        if len(calls) == 1:
            return {'status': 'ok', 'corpus': target}
        if failure == 'lost_reply':
            raise TimeoutError('synthetic post-commit lost reply')
        return {'status': 'conflict'}
    monkeypatch.setattr(rollout, 'refresh', refresh)
    journal = tmp_path / 'partial.jsonl'
    assert not rollout.run(raw, journal)
    recorded = events(journal)
    assert len(calls) == 2
    assert [e['phase'] for e in recorded] == ['planned', 'apply', 'apply', 'stopped']
    assert recorded[2]['result'] == {'status': 'ambiguous' if failure == 'lost_reply' else 'conflict'}
    assert recorded[-1]['workers_acknowledged'] == 1
    assert journal.stat().st_mode & 0o777 == 0o600


def test_post_apply_observation_detects_intervening_change(data, tmp_path, monkeypatch):
    old = TriageService(data).snapshot.identity()
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'target')
    raw = json.dumps(plan_for(release, old, [tmp_path / 'one.sock'])).encode()
    _, target = rollout.prepare(raw)
    monkeypatch.setattr(rollout, 'refresh', lambda *a, **k: {'status': 'ok', 'corpus': target})
    monkeypatch.setattr(rollout, 'inspect_corpus', lambda *a, **k: {'status': 'ok', 'corpus': old})
    journal = tmp_path / 'changed.jsonl'
    assert not rollout.run(raw, journal)
    recorded = events(journal)
    assert recorded[-2]['result']['status'] == 'identity_mismatch'
    assert recorded[-1] == {**recorded[-1], 'phase': 'stopped', 'workers_acknowledged': 1}
    assert not any(e['phase'] == 'complete' for e in recorded)


def test_journal_failure_stops_before_next_worker(data, tmp_path, monkeypatch):
    old = TriageService(data).snapshot.identity()
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'target')
    raw = json.dumps(plan_for(release, old, [tmp_path / 'one.sock', tmp_path / 'two.sock'])).encode()
    _, target = rollout.prepare(raw)
    calls = []
    monkeypatch.setattr(rollout, 'refresh', lambda *a, **k: calls.append(a[0]) or {'status': 'ok', 'corpus': target})
    original = os.fsync
    flushes = []
    def fail_after_apply(fd):
        flushes.append(fd)
        if len(flushes) == 2:
            raise OSError('synthetic journal storage failure')
        original(fd)
    monkeypatch.setattr(rollout.os, 'fsync', fail_after_apply)
    with pytest.raises(OSError):
        rollout.run(raw, tmp_path / 'failed-storage.jsonl')
    assert len(calls) == 1  # First might have published; never advance with unrecorded progress.


@pytest.mark.skipif(os.name != 'posix', reason='Local control sockets require POSIX')
def test_three_real_workers_partial_conflict_then_explicit_recovery(data, tmp_path):
    first = create_release(data / 'runbooks', tmp_path / 'releases', 'a')
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Compare'))
    target = create_release(data / 'runbooks', tmp_path / 'releases', 'b')
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Inspect'))
    other = create_release(data / 'runbooks', tmp_path / 'releases', 'c')
    root = tmp_path / 'app'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'incidents.json').write_bytes((data / 'incidents.json').read_bytes())
    env = {**os.environ, 'RUNBOOKOPS_ROOT': str(root), 'RUNBOOKOPS_CORPUS_RELEASE': str(first),
           'RUNBOOKOPS_CORPUS_SHA256': verify_release(first).manifest_hash,
           'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'backend')}
    with socket_path() as parent_socket, ExitStack() as processes:
        addresses = [parent_socket.parent / f'w{i}.sock' for i in range(3)]
        bases = [processes.enter_context(_server({**env, 'RUNBOOKOPS_CONTROL_SOCKET': str(address)}))
                 for address in addresses]
        old = _http(bases[0], '/api/runbooks/database')
        plan = plan_for(target, old['corpus'], addresses)
        # Another trusted operator changes worker 1 after the rollout plan was observed.
        assert control.refresh(addresses[1], other, verify_release(other).manifest_hash)['status'] == 'ok'
        plan_file = tmp_path / 'plan.json'
        plan_file.write_text(json.dumps(plan))
        def cli(journal):
            return subprocess.run([sys.executable, '-m', 'runbookops.corpus_rollout', '--plan', str(plan_file),
                '--journal', str(journal)], env=env, capture_output=True, text=True, timeout=30)
        partial = tmp_path / 'partial.jsonl'
        result = cli(partial)
        assert result.returncode == 1 and json.loads(result.stdout) == {'status': 'stopped'}, result.stderr
        assert [_http(base, '/healthz')['corpus']['corpus_id'] for base in bases] == ['b', 'c', 'a']
        assert events(partial)[2]['result'] == {'status': 'conflict'}
        _http(bases[0], '/api/runbooks/database?expected_hash=' + old['content_hash'], expected=409)
        assert _http(bases[2], '/api/runbooks/database')['content_hash'] == old['content_hash']
        for worker in plan['workers']:
            worker['expected_corpus'] = control.inspect_corpus(worker['socket'])['corpus']
        plan_file.write_text(json.dumps(plan))
        final = tmp_path / 'recovery.jsonl'
        result = cli(final)
        assert result.returncode == 0 and json.loads(result.stdout) == {'status': 'complete'}, result.stderr
        identities = [_http(base, '/healthz')['corpus'] for base in bases]
        assert identities == [identities[0]] * 3 and identities[0]['corpus_id'] == 'b'
        assert [e['phase'] for e in events(final)] == ['planned'] + ['apply'] * 3 + ['verify'] * 3 + ['complete']
        inspected = subprocess.run([sys.executable, '-m', 'runbookops.corpus_control', '--socket', str(addresses[0]),
            '--inspect'], env=env, capture_output=True, text=True, timeout=10)
        assert inspected.returncode == 0 and json.loads(inspected.stdout)['corpus'] == identities[0]
