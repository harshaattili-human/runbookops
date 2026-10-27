"""An explicit startup release must not silently fall back to the bundled corpus."""

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from fastapi.testclient import TestClient
import pytest

from runbookops import api
from runbookops.corpus_release import CorpusReleaseError, create_release, verify_release
from runbookops.service import TriageService
from test_source_versions import data, DOCUMENT, QUERY


@pytest.mark.parametrize('release,digest', [
    ('missing', None), (None, 'a' * 64), ('', 'a' * 64), ('missing', ''),
])
def test_partial_environment_prevents_api_startup(monkeypatch, release, digest):
    for key, value in [('RUNBOOKOPS_CORPUS_RELEASE', release), ('RUNBOOKOPS_CORPUS_SHA256', digest)]:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match='Set both RUNBOOKOPS_CORPUS'):
        with TestClient(api.app):
            pytest.fail('Partial release settings must not start the API')


def test_service_requires_a_pin_and_can_start_without_bundled_runbooks(data, tmp_path):
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'selected')
    verified = verify_release(release)
    for kwargs in ({'runbook_release': release}, {'expected_manifest_hash': verified.manifest_hash}):
        with pytest.raises(ValueError, match='supplied together'):
            TriageService(data, **kwargs)
    (data / 'runbooks').rename(data / 'unused-runbooks')
    service = TriageService(data, runbook_release=release, expected_manifest_hash=verified.manifest_hash)
    assert service.retriever.documents == verified.documents
    with pytest.raises(CorpusReleaseError, match='does not match expected'):
        TriageService(data, runbook_release=release, expected_manifest_hash='0' * 64)


@contextmanager
def _server(env, *, expected_failure=None):
    # Inherit a bound socket so another process cannot take the test's port.
    # This process-level check targets POSIX, matching the hosted Linux runner.
    with socket.socket() as listener, tempfile.TemporaryFile(mode='w+') as log:
        listener.bind(('127.0.0.1', 0))
        base = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'runbookops.api:app', '--fd', str(listener.fileno())],
            env=env, pass_fds=(listener.fileno(),), stdout=log, stderr=log)
        try:
            if expected_failure is not None:
                assert server.wait(timeout=20) != 0
                log.seek(0)
                output = log.read()
                assert expected_failure in output, output
                assert 'Application startup complete' not in output, output
            else:
                deadline = time.monotonic() + 20
                while True:
                    if server.poll() is not None:
                        log.seek(0)
                        pytest.fail(f'API exited during startup: {log.read()}')
                    try:
                        _http(base, '/healthz')
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            log.seek(0)
                            pytest.fail(f'API did not become ready: {log.read()}')
                        time.sleep(.05)
            yield base
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


def _http(base, path, body=None, expected=200):
    request = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=1)
    except HTTPError as exc:
        response = exc
    with response:
        assert response.status == expected
        return json.load(response)


@pytest.mark.skipif(os.name != 'posix', reason='Inherited-socket process check targets POSIX')
def test_restart_requires_the_manifest_pin_for_the_new_alias_target(data, tmp_path):
    releases = tmp_path / 'releases'
    first = create_release(data / 'runbooks', releases, 'first')
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT.replace('Review', 'Compare'), encoding='utf-8')
    second = create_release(data / 'runbooks', releases, 'second')
    a, b = verify_release(first), verify_release(second)
    alias = tmp_path / 'current'
    alias.symlink_to(first, target_is_directory=True)
    root = tmp_path / 'application'
    (root / 'data').mkdir(parents=True)
    # There is deliberately no fallback runbooks directory in this application root.
    (root / 'data' / 'incidents.json').write_bytes((data / 'incidents.json').read_bytes())
    env = {**os.environ, 'RUNBOOKOPS_ROOT': str(root), 'RUNBOOKOPS_CORPUS_RELEASE': str(alias),
           'RUNBOOKOPS_CORPUS_SHA256': a.manifest_hash,
           'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'backend')}
    old_hash = sha256(a.documents['database'].encode()).hexdigest()
    new_hash = sha256(b.documents['database'].encode()).hexdigest()
    with _server(env) as base:
        assert _http(base, '/healthz')['corpus']['manifest_sha256'] == a.manifest_hash
        assert _http(base, '/api/runbooks/database')['content_hash'] == old_hash
        replacement = tmp_path / 'replacement'
        replacement.symlink_to(second, target_is_directory=True)
        replacement.replace(alias)
        # An alias edit never refreshes a running process implicitly.
        assert _http(base, '/api/triage', {'query': QUERY})['sources'][0]['document_hash'] == old_hash
    with _server(env, expected_failure='Release manifest does not match expected SHA-256'):
        pass
    env['RUNBOOKOPS_CORPUS_SHA256'] = b.manifest_hash
    with _server(env) as base:
        assert _http(base, '/healthz')['corpus']['manifest_sha256'] == b.manifest_hash
        assert _http(base, '/api/runbooks/database')['content_hash'] == new_hash != old_hash
        assert _http(base, '/api/triage', {'query': QUERY})['sources'][0]['document_hash'] == new_hash
        _http(base, '/api/runbooks/database?expected_hash=' + old_hash, expected=409)
    # Matching manifest bytes alone do not excuse a later source edit.
    (second / 'database.md').write_text('unexpected edit', encoding='utf-8')
    with _server(env, expected_failure='Runbook hash does not match manifest'):
        pass
