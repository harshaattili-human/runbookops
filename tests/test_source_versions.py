"""Evidence must identify the document snapshot behind its line numbers."""

from hashlib import sha256
import json

from fastapi.testclient import TestClient
import pytest

from runbookops import api
from runbookops.retrieval import Retriever
from runbookops.service import TriageService


QUERY = 'database connection timeout'
DOCUMENT = ('# Database pool\n\n## Symptoms\n'
            'Database connection timeout — café client.\n\n## Investigation\n'
            'Review database connection timeout metrics.\n')


@pytest.fixture
def data(tmp_path):
    runbooks = tmp_path / 'runbooks'
    runbooks.mkdir()
    (runbooks / 'database.md').write_text(DOCUMENT, encoding='utf-8')
    (runbooks / 'queue.md').write_text(
        '# Queue\n\n## Symptoms\nKafka consumer lag is rising.\n', encoding='utf-8')
    # Three synthetic classes exercise the real service without the benchmark corpus.
    (tmp_path / 'incidents.json').write_text(json.dumps([
        {'text': QUERY, 'category': 'database'},
        {'text': 'Kafka consumer lag', 'category': 'messaging'},
        {'text': 'Expired certificate handshake', 'category': 'network'},
    ]), encoding='utf-8')
    return tmp_path


@pytest.fixture
def configured_app(data, monkeypatch):
    monkeypatch.setattr(api, 'TriageService', lambda: TriageService(data))
    return api.app


@pytest.mark.parametrize('ranking', ['hybrid', 'bm25', 'tfidf'])
def test_each_passage_identifies_the_complete_document(data, ranking):
    retriever = Retriever(data / 'runbooks')
    sources = retriever.search(QUERY, ranking=ranking)
    assert len(sources) == 2
    for source in sources:
        assert source['document_hash'] == sha256(DOCUMENT.encode('utf-8')).hexdigest()
        lines = DOCUMENT.splitlines()[source['start_line'] - 1:source['end_line']]
        assert '\n'.join(lines).strip() == source['text']


def test_hash_uses_served_text_not_filesystem_location_or_line_endings(data, tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'database.md').write_bytes(DOCUMENT.replace('\n', '\r\n').encode('utf-8'))
    first = Retriever(data / 'runbooks').search(QUERY)[0]
    second = Retriever(other).search(QUERY)[0]
    assert first['document_hash'] == second['document_hash']


def test_edit_is_visible_only_after_index_rebuild(data):
    original = Retriever(data / 'runbooks')
    old_source = original.search(QUERY)[0]
    path = data / 'runbooks' / 'database.md'
    # A change outside the matched section still changes the full-document hash.
    path.write_text(DOCUMENT + '\n## Owner\nContact the service team.\n', encoding='utf-8')
    assert original.search(QUERY)[0] == old_source
    fresh = Retriever(data / 'runbooks').search(QUERY)[0]
    assert fresh['id'] == old_source['id']
    assert fresh['text'] == old_source['text']
    assert fresh['document_hash'] != old_source['document_hash']


def test_unrelated_document_edit_keeps_source_hash(data):
    before = Retriever(data / 'runbooks').search(QUERY)[0]['document_hash']
    (data / 'runbooks' / 'queue.md').write_text(
        '# Queue\n\n## Checks\nInspect Kafka consumer lag metrics.\n', encoding='utf-8')
    after = Retriever(data / 'runbooks').search(QUERY)[0]['document_hash']
    assert after == before


def test_api_source_and_document_hash_agree(configured_app):
    with TestClient(configured_app) as client:
        response = client.post('/api/triage', json={'query': QUERY})
        assert response.status_code == 200
        source = response.json()['sources'][0]
        path = '/api/runbooks/' + source['document']
        checked = client.get(path, params={'expected_hash': source['document_hash']})
        assert checked.status_code == 200
        body = checked.json()
        assert body['content_hash'] == source['document_hash']
        assert sha256(body['content'].encode('utf-8')).hexdigest() == body['content_hash']
        # Existing callers can still fetch without specifying a version.
        assert client.get(path).json() == body


def test_source_from_before_restart_is_rejected_after_edit(configured_app, data):
    with TestClient(configured_app) as client:
        source = client.post('/api/triage', json={'query': QUERY}).json()['sources'][0]
    (data / 'runbooks' / 'database.md').write_text(
        DOCUMENT.replace('Review', 'Compare'), encoding='utf-8')
    with TestClient(configured_app) as client:
        response = client.get('/api/runbooks/database',
                              params={'expected_hash': source['document_hash']})
        assert response.status_code == 409
        assert response.json() == {'detail': 'Runbook version changed; run triage again.'}
        current = client.get('/api/runbooks/database')
        assert current.status_code == 200
        assert current.json()['content_hash'] != source['document_hash']


def test_removed_document_is_not_served_after_restart(configured_app, data):
    with TestClient(configured_app) as client:
        source = client.post('/api/triage', json={'query': QUERY}).json()['sources'][0]
    (data / 'runbooks' / 'database.md').unlink()
    with TestClient(configured_app) as client:
        response = client.get('/api/runbooks/database',
                              params={'expected_hash': source['document_hash']})
        assert response.status_code == 404


@pytest.mark.parametrize('expected_hash', ['', 'not-a-hash', '0' * 64])
def test_mismatched_hash_never_returns_document(configured_app, expected_hash):
    with TestClient(configured_app) as client:
        response = client.get('/api/runbooks/database', params={'expected_hash': expected_hash})
        assert response.status_code == 409
        assert 'content' not in response.json()
