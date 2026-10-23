"""Manifest-pinned releases prevent mixed runbook generations at refresh."""

import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event

import pytest

from runbookops import corpus_release
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


def test_expected_digest_pins_manifest_bytes_before_reading_documents(tmp_path, monkeypatch):
    release = create_release(_source(tmp_path), tmp_path / 'releases', 'pinned')
    digest = verify_release(release).manifest_hash
    assert verify_release(release, expected_manifest_hash=digest).corpus_id == 'pinned'
    # Even harmless formatting changes require an explicit new manifest pin.
    manifest = release / 'manifest.json'
    manifest.write_bytes(manifest.read_bytes() + b'\n')

    def unexpected_read(_):
        pytest.fail('A rejected manifest must not read runbooks')

    monkeypatch.setattr(corpus_release, '_read_documents', unexpected_read)
    with pytest.raises(CorpusReleaseError, match='does not match expected'):
        verify_release(release, expected_manifest_hash=digest)
    for invalid in ('', 'a' * 63, 'A' * 64, True):
        with pytest.raises(CorpusReleaseError, match='64 lowercase hex'):
            verify_release(release, expected_manifest_hash=invalid)


def test_schema_requires_an_integer_even_with_a_matching_pin(tmp_path):
    release = create_release(_source(tmp_path), tmp_path / 'releases', 'schema')
    manifest = release / 'manifest.json'
    payload = json.loads(manifest.read_bytes())
    for invalid in (True, 1.0, '1', 2):
        payload['schema_version'] = invalid
        raw = json.dumps(payload).encode()
        manifest.write_bytes(raw)
        with pytest.raises(CorpusReleaseError, match='Unsupported release manifest schema'):
            verify_release(release, expected_manifest_hash=sha256(raw).hexdigest())


def test_alias_change_during_refresh_keeps_the_resolved_release(tmp_path, monkeypatch):
    first = create_release(_source(tmp_path / 'first'), tmp_path / 'releases', 'first')
    second = create_release(_source(tmp_path / 'second', DOCUMENT.replace('Review', 'Compare')),
                            tmp_path / 'releases', 'second')
    first_pin, second_pin = verify_release(first), verify_release(second)
    alias = tmp_path / 'current'
    alias.symlink_to(first, target_is_directory=True)
    service = TriageService(_service_data(tmp_path))
    entered, resume = Event(), Event()
    read = corpus_release._read_documents

    def paused(path):
        assert path == first.resolve()
        entered.set()
        assert resume.wait(5)
        return read(path)

    with monkeypatch.context() as patch:
        patch.setattr(corpus_release, '_read_documents', paused)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(service.refresh_runbooks_release, alias,
                                  expected_manifest_hash=first_pin.manifest_hash)
            try:
                assert entered.wait(5)
                replacement = tmp_path / 'next'
                replacement.symlink_to(second, target_is_directory=True)
                replacement.replace(alias)
            finally:
                resume.set()
            receipt = pending.result(timeout=5)
    assert receipt['corpus_id'] == 'first'
    assert service.retriever.documents == first_pin.documents
    original = service.retriever
    with pytest.raises(CorpusReleaseError, match='does not match expected'):
        service.refresh_runbooks_release(alias, expected_manifest_hash=first_pin.manifest_hash)
    assert service.retriever is original
    service.refresh_runbooks_release(alias, expected_manifest_hash=second_pin.manifest_hash)
    assert service.retriever.documents == second_pin.documents


def test_matching_manifest_cannot_publish_an_unbuildable_index(tmp_path):
    service = TriageService(_service_data(tmp_path))
    original = service.retriever
    release = create_release(_source(tmp_path / 'candidate'), tmp_path / 'releases', 'no-chunks')
    manifest = release / 'manifest.json'
    payload = json.loads(manifest.read_bytes())
    for item in payload['documents']:
        text = '# Title without sections\n'
        (release / item['file']).write_text(text, encoding='utf-8')
        item['sha256'] = sha256(text.encode()).hexdigest()
    raw = json.dumps(payload).encode()
    manifest.write_bytes(raw)
    with pytest.raises(ValueError, match='At least one runbook'):
        service.refresh_runbooks_release(release, expected_manifest_hash=sha256(raw).hexdigest())
    assert service.retriever is original
    assert service.triage(QUERY)['sources'][0]['document_hash'] == original.document_hashes['database']
