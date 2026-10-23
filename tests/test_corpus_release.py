"""Manifest-pinned releases prevent mixed runbook generations at refresh."""

import json
from pathlib import Path

import pytest

from runbookops.corpus_release import (
    CorpusReleaseError, create_release, verify_release)
from runbookops.service import TriageService
from test_source_versions import DOCUMENT, QUERY


def _source(root: Path, document: str = DOCUMENT) -> Path:
    source = root / 'source'
    source.mkdir(parents=True)
    (source / 'database.md').write_text(document, encoding='utf-8')
    (source / 'queue.md').write_text(
        '# Queue backlog\n\n## Inspect\nCheck consumer lag and retries.\n',
        encoding='utf-8')
    return source


def _service_data(root: Path) -> Path:
    data = root / 'data'
    (data / 'runbooks').mkdir(parents=True)
    (data / 'runbooks' / 'database.md').write_text(DOCUMENT, encoding='utf-8')
    (data / 'incidents.json').write_text(json.dumps([
        {'text': 'database query lock timeout', 'category': 'database', 'group': 'db'},
        {'text': 'queue consumer lag retry', 'category': 'messaging', 'group': 'queue'},
    ]), encoding='utf-8')
    return data


def test_release_round_trip_and_manifest_receipt(tmp_path):
    release = create_release(_source(tmp_path), tmp_path / 'releases', 'ops-2026-10-23')
    verified = verify_release(release)
    assert verified.corpus_id == 'ops-2026-10-23'
    assert set(verified.documents) == {'database', 'queue'}
    assert len(verified.manifest_hash) == 64
    with pytest.raises(CorpusReleaseError, match='already exists'):
        create_release(_source(tmp_path / 'again'), tmp_path / 'releases',
                       'ops-2026-10-23')


def test_refresh_publishes_verified_snapshot_and_receipt_is_detached(tmp_path):
    service = TriageService(_service_data(tmp_path))
    original_hash = service.retriever.document_hashes['database']
    changed = DOCUMENT.replace('Review', 'Compare')
    release = create_release(_source(tmp_path / 'next', changed),
                             tmp_path / 'releases', 'ops-next')
    receipt = service.refresh_runbooks_release(release)
    assert receipt['corpus_id'] == 'ops-next'
    assert receipt['document_hashes']['database'] != original_hash
    assert service.triage(QUERY)['sources'][0]['document_hash'] == \
        receipt['document_hashes']['database']
    receipt['document_hashes'].clear()
    assert service.retriever.document_hashes


@pytest.mark.parametrize('change', ['edit', 'add', 'remove'])
def test_changed_release_is_rejected_without_replacing_index(tmp_path, change):
    service = TriageService(_service_data(tmp_path))
    original = service.retriever
    release = create_release(_source(tmp_path / 'candidate'),
                             tmp_path / 'releases', 'ops-candidate')
    if change == 'edit':
        (release / 'database.md').write_text('changed', encoding='utf-8')
    elif change == 'add':
        (release / 'extra.md').write_text('# Extra\n\n## Check\nText\n', encoding='utf-8')
    else:
        (release / 'queue.md').unlink()
    with pytest.raises(CorpusReleaseError):
        service.refresh_runbooks_release(release)
    assert service.retriever is original
    assert service.triage(QUERY)['sources'][0]['document_hash'] == \
        original.document_hashes['database']


def test_manifest_contract_rejects_duplicates_paths_and_symlinks(tmp_path):
    release = create_release(_source(tmp_path), tmp_path / 'releases', 'ops-valid')
    manifest = release / 'manifest.json'
    original = manifest.read_text(encoding='utf-8')
    manifest.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(CorpusReleaseError, match='Duplicate JSON key'):
        verify_release(release)
    manifest.write_text(original.replace('database.md', '../database.md'), encoding='utf-8')
    with pytest.raises(CorpusReleaseError, match='filename'):
        verify_release(release)
    manifest.write_text(original, encoding='utf-8')
    (release / 'queue.md').unlink()
    (release / 'queue.md').symlink_to(release / 'database.md')
    with pytest.raises(CorpusReleaseError, match='regular file'):
        verify_release(release)


def test_invalid_candidate_never_creates_release(tmp_path):
    source = _source(tmp_path, '# No sections\n')
    (source / 'queue.md').write_text('# Still no sections\n', encoding='utf-8')
    releases = tmp_path / 'releases'
    with pytest.raises(ValueError, match='At least one runbook'):
        create_release(source, releases, 'invalid')
    assert not (releases / 'invalid').exists()
    assert not list(releases.glob('.invalid.*'))
