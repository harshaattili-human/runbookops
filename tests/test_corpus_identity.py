"""Served identity follows the captured index, never a later filesystem read."""

from hashlib import sha256
import json

from fastapi.testclient import TestClient
import pytest

from runbookops.corpus_release import CorpusReleaseError, create_release, verify_release
from runbookops.service import TriageService
from test_source_versions import data, configured_app, DOCUMENT, QUERY


def test_api_identity_agrees_across_routes_and_changes_only_on_publication(configured_app, data):
    with TestClient(configured_app) as client:
        result = client.post('/api/triage', json={'query': QUERY}).json()
        identity = result['corpus']
        assert identity['source'] == 'directory'
        assert identity['corpus_id'] is None and identity['manifest_sha256'] is None
        hashes = {p.stem: sha256(p.read_text().encode()).hexdigest()
                  for p in (data / 'runbooks').glob('*.md')}
        assert identity['documents_sha256'] == sha256(json.dumps(
            hashes, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        for path in ('/healthz', '/api/overview', '/api/runbooks/database'):
            assert client.get(path).json()['corpus'] == identity
        (data / 'runbooks' / 'queue.md').write_text('# Queue\n\n## Inspect\nNew consumer lag guidance.\n')
        assert client.get('/healthz').json()['corpus'] == identity
        configured_app.state.triage.refresh_runbooks()
        changed = client.get('/api/overview').json()['corpus']
        assert changed['documents_sha256'] != identity['documents_sha256']
        # A different document changed the corpus, while this source remains the same.
        source = client.get('/api/runbooks/database').json()
        assert source['content_hash'] == result['sources'][0]['document_hash']
        assert source['corpus'] == changed
        changed.clear()
        assert client.get('/healthz').json()['corpus']['schema_version'] == 1
        assert str(data) not in json.dumps(identity)


def test_release_identity_is_pinned_retained_on_failure_and_cleared_by_directory_refresh(data, tmp_path):
    release = create_release(data / 'runbooks', tmp_path / 'releases', 'reviewed-release')
    verified = verify_release(release)
    service = TriageService(data, runbook_release=release, expected_manifest_hash=verified.manifest_hash)
    identity = service.snapshot.identity()
    assert identity['source'] == 'release' and identity['corpus_id'] == 'reviewed-release'
    assert identity['manifest_sha256'] == verified.manifest_hash
    assert service.triage(QUERY)['corpus'] == identity
    (release / 'database.md').write_text(DOCUMENT + 'tampered\n')
    with pytest.raises(CorpusReleaseError):
        service.refresh_runbooks_release(release, expected_manifest_hash=verified.manifest_hash)
    assert service.snapshot.identity() == identity
    assert str(release) not in json.dumps(identity)
    service.refresh_runbooks()
    current = service.snapshot.identity()
    assert current['source'] == 'directory'
    assert current['corpus_id'] is None and current['manifest_sha256'] is None
    assert current['documents_sha256'] == identity['documents_sha256']


def test_same_content_different_releases_share_content_identity_not_manifest_identity(data, tmp_path):
    service = TriageService(data)
    original = service.snapshot.identity()
    observed = []
    for name in ('first', 'second'):
        release = create_release(data / 'runbooks', tmp_path / 'releases', name)
        receipt = service.refresh_runbooks_release(release)
        observed.append(service.snapshot.identity())
        assert observed[-1]['manifest_sha256'] == receipt['manifest_sha256']
        assert observed[-1]['documents_sha256'] == original['documents_sha256']
        receipt.clear()
        assert service.triage(QUERY)['corpus'] == observed[-1]
    assert observed[0]['manifest_sha256'] != observed[1]['manifest_sha256']
