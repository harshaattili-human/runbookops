"""Synthetic local-operator protocol and process checks, not a rollout test."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from threading import Event

import pytest
from fastapi.testclient import TestClient

from runbookops import corpus_control as control
from runbookops import api, service as service_module
from runbookops.corpus_release import create_release, verify_release
from runbookops.service import TriageService
from test_corpus_startup import _server, _http
from test_source_versions import data, DOCUMENT

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Operator channel requires POSIX Unix sockets')


@contextmanager
def socket_path():
    # Unix pathname limits are small; pytest's nested temp paths can exceed them.
    with tempfile.TemporaryDirectory(prefix='rbc-') as directory:
        path = Path(directory)
        path.chmod(0o700)
        yield path / 'control.sock'


async def exchange(path, value):
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write(value)
        await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(), 3))
    finally:
        writer.close()
        await writer.wait_closed()


def request(release, digest):
    return json.dumps({'release': str(release), 'manifest_sha256': digest}).encode() + b'\n'


def test_pinned_refresh_and_rejection_keep_detached_identity(data, tmp_path):
    service = TriageService(data)
    old = service.snapshot.identity()
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Compare'))
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'next')
    pin = verify_release(release).manifest_hash

    async def scenario(path):
        async with control.serve_control(service, path):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            failed = await exchange(path, request(release, '0' * 64))
            assert failed == {'status': 'refresh_failed'}
            assert service.snapshot.identity() == old
            result = await asyncio.to_thread(control.refresh, path, release, pin)
            assert result == {'status': 'ok', 'corpus': service.snapshot.identity()}
            assert result['corpus']['manifest_sha256'] == pin
            assert result['corpus']['documents_sha256'] != old['documents_sha256']
            assert str(release) not in json.dumps(result)
            result['corpus'].clear()
            assert service.snapshot.identity()['manifest_sha256'] == pin
        assert not path.exists()

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_framing_schema_timeout_and_disconnect_never_dispatch(monkeypatch):
    class Service:
        def refresh_runbooks_release(self, *args, **kwargs):
            pytest.fail('Invalid command reached index construction')

    monkeypatch.setattr(control, 'READ_SECONDS', .05)

    async def scenario(path):
        async with control.serve_control(Service(), path) as server:
            for raw in (b'{}\n', b'[]\n', b'{"release":"/a","release":"/b","manifest_sha256":"' + b'a'*64 + b'"}\n',
                        b'{"release":"relative","manifest_sha256":"' + b'a'*64 + b'"}\n',
                        b'{"release":"/a","manifest_sha256":true}\n', b'\xff\n',
                        b' ' * (control.MAX_REQUEST_BYTES + 1) + b'\n', b'{'):
                assert await exchange(path, raw) == {'status': 'invalid_request'}
            reader, writer = await asyncio.open_unix_connection(path)
            writer.close()
            await writer.wait_closed()
            for _ in range(100):
                if not server.active and not server.tasks:
                    break
                await asyncio.sleep(.01)
            assert not server.active
            assert await exchange(path, b'{}\n') == {'status': 'invalid_request'}

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_one_lease_covers_upload_and_worker_and_release_after_failure(monkeypatch):
    entered, release = Event(), Event()

    class Service:
        calls = 0

        def refresh_runbooks_release(self, *args, **kwargs):
            self.calls += 1
            entered.set()
            assert release.wait(5)
            raise ValueError('Synthetic failure with a private path')

    service = Service()

    async def scenario(path):
        async with control.serve_control(service, path) as server:
            reader, writer = await asyncio.open_unix_connection(path)
            writer.write(b'{')
            await writer.drain()
            for _ in range(100):
                if server.active:
                    break
                await asyncio.sleep(.01)
            assert await exchange(path, b'ignored') == {'status': 'busy'}
            assert service.calls == 0
            writer.close()
            await writer.wait_closed()
            for _ in range(100):
                if not server.active:
                    break
                await asyncio.sleep(.01)
            assert not server.active
            pending = asyncio.create_task(exchange(path, request('/synthetic', 'a' * 64)))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                assert await exchange(path, b'ignored') == {'status': 'busy'}
                assert service.calls == 1
            finally:
                release.set()
            assert await pending == {'status': 'refresh_failed'}
            assert await exchange(path, b'{}\n') == {'status': 'invalid_request'}

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_api_keeps_serving_old_snapshot_during_operator_rebuild(data, tmp_path, monkeypatch):
    service = TriageService(data)
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Compare'))
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'next')
    pin = verify_release(release).manifest_hash
    entered, proceed = Event(), Event()
    original = service_module.Retriever

    def held_index(*args, **kwargs):
        entered.set()
        assert proceed.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, 'TriageService', lambda: service)
    monkeypatch.setattr(service_module, 'Retriever', held_index)
    monkeypatch.delenv('RUNBOOKOPS_CORPUS_RELEASE', raising=False)
    monkeypatch.delenv('RUNBOOKOPS_CORPUS_SHA256', raising=False)
    with socket_path() as path:
        monkeypatch.setenv('RUNBOOKOPS_CONTROL_SOCKET', str(path))
        with TestClient(api.app) as client, ThreadPoolExecutor(max_workers=1) as pool:
            old = client.get('/api/runbooks/database').json()
            pending = pool.submit(control.refresh, path, release, pin)
            try:
                assert entered.wait(3)
                assert client.get('/healthz').json()['corpus'] == old['corpus']
                assert client.get('/api/runbooks/database').json() == old
                assert client.post('/api/triage', json={'query': 'database connection timeout'}).json()['corpus'] == old['corpus']
            finally:
                proceed.set()
            result = pending.result(timeout=3)
            assert result['status'] == 'ok'
            assert client.get('/healthz').json()['corpus'] == result['corpus']
            assert client.get('/api/runbooks/database', params={'expected_hash': old['content_hash']}).status_code == 409


@pytest.mark.parametrize('fails', [False, True])
def test_shutdown_joins_worker_despite_repeated_cancellation(fails):
    entered, release, finished = Event(), Event(), Event()

    class Service:
        def refresh_runbooks_release(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            finished.set()
            if fails:
                raise ValueError('synthetic build failure')
            return {'corpus': {'manifest_sha256': 'a' * 64}}

    async def scenario(path):
        context = control.serve_control(Service(), path)
        server = await context.__aenter__()
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(request('/synthetic', 'a' * 64))
        await writer.drain()
        assert await asyncio.to_thread(entered.wait, 3)
        handler = next(iter(server.tasks))
        shutdown = asyncio.create_task(context.__aexit__(None, None, None))
        try:
            await asyncio.sleep(.02)
            handler.cancel()
            handler.cancel()
            await asyncio.sleep(.02)
            assert not shutdown.done() and server.active and path.exists()
            assert not finished.is_set()
        finally:
            release.set()
        await asyncio.wait_for(shutdown, 3)
        assert finished.is_set() and not server.active and not path.exists()
        writer.close()
        await writer.wait_closed()

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_private_directory_existing_path_and_replacement_cleanup():
    async def scenario(path):
        for mode in (0o755, 0o770):
            path.parent.chmod(mode)
            with pytest.raises(ValueError, match='0700'):
                async with control.serve_control(None, path):
                    pytest.fail('Unsafe parent accepted')
        path.parent.chmod(0o700)
        path.write_text('existing operator file')
        with pytest.raises(OSError):
            async with control.serve_control(None, path):
                pytest.fail('Existing path replaced')
        assert path.read_text() == 'existing operator file'
        path.unlink()
        alias = path.parent / 'alias'
        alias.symlink_to(path.parent, target_is_directory=True)
        with pytest.raises(ValueError, match='aliases'):
            async with control.serve_control(None, alias / 'other.sock'):
                pytest.fail('Aliased parent accepted')
        async with control.serve_control(None, path):
            # Only test-owned files; cleanup must not remove a replacement.
            path.unlink()
            path.write_text('replacement operator file')
        assert path.read_text() == 'replacement operator file'
        for value in ('', 'relative.sock'):
            with pytest.raises(ValueError):
                async with control.serve_control(None, value):
                    pytest.fail('Relative/empty path accepted')

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_real_api_and_cli_refresh_without_restart(data, tmp_path):
    releases = tmp_path / 'releases'
    first = create_release(data / 'runbooks', releases, 'first')
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Compare'))
    second = create_release(data / 'runbooks', releases, 'second')
    a, b = verify_release(first), verify_release(second)
    root = tmp_path / 'app'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'incidents.json').write_bytes((data / 'incidents.json').read_bytes())
    with socket_path() as path:
        env = {**os.environ, 'RUNBOOKOPS_ROOT': str(root), 'RUNBOOKOPS_CORPUS_RELEASE': str(first),
               'RUNBOOKOPS_CORPUS_SHA256': a.manifest_hash, 'RUNBOOKOPS_CONTROL_SOCKET': str(path),
               'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'backend')}
        def cli(pin):
            return subprocess.run([sys.executable, '-m', 'runbookops.corpus_control', '--socket', str(path),
                '--release', str(second), '--sha256', pin], env=env, capture_output=True, text=True, timeout=10)
        with _server(env) as base:
            old = _http(base, '/api/runbooks/database')
            assert old['corpus']['manifest_sha256'] == a.manifest_hash
            rejected = cli('0' * 64)
            assert rejected.returncode == 1 and json.loads(rejected.stdout) == {'status': 'refresh_failed'}
            assert _http(base, '/healthz')['corpus'] == old['corpus']
            accepted = cli(b.manifest_hash)
            assert accepted.returncode == 0, accepted.stderr
            identity = json.loads(accepted.stdout)['corpus']
            assert identity['manifest_sha256'] == b.manifest_hash
            assert _http(base, '/healthz')['corpus'] == identity
            assert _http(base, '/api/overview')['corpus'] == identity
            _http(base, '/api/runbooks/database?expected_hash=' + old['content_hash'], expected=409)
        assert not path.exists()


def test_guarded_refresh_rejects_stale_identity_before_reading_release(data, tmp_path, monkeypatch):
    service = TriageService(data)
    old = service.snapshot.identity()
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'same-content')
    pin = verify_release(release).manifest_hash

    async def scenario(path):
        async with control.serve_control(service, path):
            accepted = await asyncio.to_thread(control.refresh, path, release, pin, expected_corpus=old)
            current = service.snapshot.identity()
            assert accepted == {'status': 'ok', 'corpus': current}
            # Same documents, different release metadata must still conflict.
            assert current['documents_sha256'] == old['documents_sha256']
            def forbidden(*args, **kwargs):
                pytest.fail('Stale request read the candidate release')
            monkeypatch.setattr(service_module, 'verify_release', forbidden)
            rejected = await asyncio.to_thread(control.refresh, path, '/missing', pin, expected_corpus=old)
            assert rejected == {'status': 'conflict'}
            assert service.snapshot.identity() == current

    with socket_path() as path:
        asyncio.run(scenario(path))


def test_guard_schema_rejects_null_partial_and_inconsistent_identities():
    identity = {'schema_version': 1, 'source': 'directory', 'corpus_id': None,
                'manifest_sha256': None, 'documents_sha256': 'a' * 64}
    malformed = [None, {}, {**identity, 'schema_version': True},
                 {**identity, 'schema_version': 1.0}, {**identity, 'source': 'unknown'},
                 {**identity, 'manifest_sha256': 'b' * 64},
                 {**identity, 'documents_sha256': 'A' * 64},
                 {**identity, 'source': 'release'}, {**identity, 'extra': 1}]
    for expected in malformed:
        raw = json.dumps({'release': '/synthetic', 'manifest_sha256': 'a' * 64,
                          'expected_corpus': expected}).encode() + b'\n'
        with pytest.raises(ValueError):
            control._request(raw)
    raw = json.dumps({'release': '/synthetic', 'manifest_sha256': 'a' * 64,
                      'expected_corpus': identity}).encode() + b'\n'
    assert control._request(raw)[2] == identity


def test_guarded_cli_conflict_and_explicit_recovery(data, tmp_path):
    first = create_release(data / 'runbooks', tmp_path / 'releases', 'first')
    second = create_release(data / 'runbooks', tmp_path / 'releases', 'second')
    a, b = verify_release(first), verify_release(second)
    saved = tmp_path / 'observed.json'
    env = {**os.environ, 'RUNBOOKOPS_ROOT': str(data.parent),
           'RUNBOOKOPS_CORPUS_RELEASE': str(first), 'RUNBOOKOPS_CORPUS_SHA256': a.manifest_hash,
           'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'backend')}
    # This fixture's data directory need not be named data.
    root = tmp_path / 'app'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'incidents.json').write_bytes((data / 'incidents.json').read_bytes())
    env['RUNBOOKOPS_ROOT'] = str(root)
    with socket_path() as path:
        env['RUNBOOKOPS_CONTROL_SOCKET'] = str(path)
        def cli():
            return subprocess.run([sys.executable, '-m', 'runbookops.corpus_control', '--socket', str(path),
                '--release', str(second), '--sha256', b.manifest_hash, '--expected-corpus', str(saved)],
                env=env, capture_output=True, text=True, timeout=10)
        with _server(env) as base:
            old = _http(base, '/healthz')['corpus']
            saved.write_text(json.dumps(old))
            first_result = cli()
            assert first_result.returncode == 0, first_result.stderr
            current = json.loads(first_result.stdout)['corpus']
            assert current['corpus_id'] == 'second'
            stale = cli()
            assert stale.returncode == 1 and json.loads(stale.stdout) == {'status': 'conflict'}
            assert _http(base, '/healthz')['corpus'] == current
            saved.write_text(json.dumps(current))
            assert cli().returncode == 0
