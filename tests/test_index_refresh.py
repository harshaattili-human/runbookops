"""Refresh publication must not mix source generations or discard a working index."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
import pytest

from runbookops import service as service_module
from runbookops.service import TriageService
from test_source_versions import data, configured_app, DOCUMENT, QUERY


def test_refresh_changes_api_versions_without_restarting(configured_app, data):
    with TestClient(configured_app) as client:
        old = client.post('/api/triage', json={'query': QUERY}).json()['sources'][0]
        path = data / 'runbooks' / 'database.md'
        path.write_text(DOCUMENT.replace('Review', 'Compare'), encoding='utf-8')
        receipt = configured_app.state.triage.refresh_runbooks()
        assert client.get('/api/runbooks/database', params={
            'expected_hash': old['document_hash']}).status_code == 409
        fresh = client.post('/api/triage', json={'query': QUERY}).json()['sources'][0]
        assert fresh['document_hash'] == receipt['database'] != old['document_hash']
        assert client.get('/api/runbooks/database', params={
            'expected_hash': fresh['document_hash']}).status_code == 200
        receipt.clear()  # The receipt does not expose the live hash mapping.
        assert configured_app.state.triage.retriever.document_hashes
        path.unlink()
        configured_app.state.triage.refresh_runbooks()
        assert client.get('/api/runbooks/database').status_code == 404
        assert client.get('/api/overview').json()['documents'] == 1


def test_failed_rebuild_preserves_working_snapshot(data):
    service = TriageService(data)
    original = service.retriever
    for path in (data / 'runbooks').glob('*.md'):
        path.write_text('# No sections\n', encoding='utf-8')
    with pytest.raises(ValueError):
        service.refresh_runbooks()
    assert service.retriever is original
    assert service.triage(QUERY)['sources'][0]['document_hash'] == original.document_hashes['database']
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT, encoding='utf-8')
    service.refresh_runbooks()
    assert service.retriever is not original


def test_rebuild_does_not_block_reads_and_refreshes_serialize(data, monkeypatch):
    service = TriageService(data)
    original = service.retriever
    entered, release, second_started = Event(), Event(), Event()
    factory = service_module.Retriever
    calls = []

    def build(path):
        calls.append(len(calls))
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return factory(path)

    def second():
        second_started.set()
        return service.refresh_runbooks()

    monkeypatch.setattr(service_module, 'Retriever', build)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(service.refresh_runbooks)
        try:
            assert entered.wait(5)
            next_refresh = pool.submit(second)
            assert second_started.wait(5)
            result = pool.submit(service.triage, QUERY).result(timeout=5)
            assert service.retriever is original
            assert result['sources'][0]['document_hash'] == original.document_hashes['database']
            assert calls == [0]
        finally:
            release.set()
        first.result(timeout=5)
        next_refresh.result(timeout=5)
    assert calls == [0, 1]
    assert service.retriever is not original


def test_inflight_answer_keeps_old_search_and_threshold(data, monkeypatch):
    service = TriageService(data)
    original = service.retriever
    entered, release = Event(), Event()
    search = original.search

    def paused(query):
        entered.set()
        assert release.wait(5)
        return search(query)

    monkeypatch.setattr(original, 'search', paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        answer = pool.submit(service.triage, QUERY)
        try:
            assert entered.wait(5)
            (data / 'runbooks' / 'database.md').unlink()
            service.refresh_runbooks()
            # Distinct threshold exposes an accidental second snapshot read.
            monkeypatch.setattr(service.retriever, 'minimum_document_coverage', 1.1)
        finally:
            release.set()
        result = answer.result(timeout=5)
    assert result['mode'] == 'extractive'
    assert result['answerability']['threshold'] == original.minimum_document_coverage
    assert result['sources'][0]['document_hash'] == original.document_hashes['database']
    assert service.triage(QUERY)['mode'] == 'abstained'
