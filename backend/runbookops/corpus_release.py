"""Create and verify manifest-pinned runbook release directories."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any


SCHEMA_VERSION = 1
MANIFEST_NAME = 'manifest.json'
CORPUS_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
FILE_NAME = re.compile(r'[a-z0-9][a-z0-9_-]*\.md\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class CorpusReleaseError(ValueError):
    """The release cannot establish the declared runbook snapshot."""


@dataclass(frozen=True)
class CorpusRelease:
    corpus_id: str
    release_path: Path
    manifest_hash: str
    documents: dict[str, str]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusReleaseError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _read_documents(directory: Path) -> dict[str, str]:
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise CorpusReleaseError(f'Cannot read release directory: {exc}') from exc
    markdown = [path for path in entries if path.suffix == '.md']
    if not markdown:
        raise CorpusReleaseError('Release must contain at least one Markdown runbook')
    documents: dict[str, str] = {}
    for path in markdown:
        if not FILE_NAME.fullmatch(path.name):
            raise CorpusReleaseError(f'Invalid runbook filename: {path.name}')
        if path.is_symlink() or not path.is_file():
            raise CorpusReleaseError(f'Runbook must be a regular file: {path.name}')
        try:
            # Universal newline handling matches Retriever's indexed-text contract.
            with path.open('r', encoding='utf-8', newline=None) as source:
                documents[path.name] = source.read()
        except (OSError, UnicodeError) as exc:
            raise CorpusReleaseError(f'Cannot read {path.name}: {exc}') from exc
    return documents


def _hash_text(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest()


def _manifest_payload(corpus_id: str, documents: dict[str, str]) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'corpus_id': corpus_id,
        'documents': [
            {'file': name, 'sha256': _hash_text(text)}
            for name, text in sorted(documents.items())
        ],
    }


def _manifest_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode('utf-8')


def verify_release(path: Path) -> CorpusRelease:
    """Resolve one release and return only texts matching its complete manifest."""
    try:
        release_path = path.resolve(strict=True)
    except OSError as exc:
        raise CorpusReleaseError(f'Cannot resolve release directory: {exc}') from exc
    if not release_path.is_dir():
        raise CorpusReleaseError('Release path must resolve to a directory')
    manifest_path = release_path / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CorpusReleaseError('Release manifest must be a regular file')
    try:
        manifest_bytes = manifest_path.read_bytes()
        payload = json.loads(manifest_bytes, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusReleaseError(f'Cannot read release manifest: {exc}') from exc
    if not isinstance(payload, dict) or set(payload) != {
            'schema_version', 'corpus_id', 'documents'}:
        raise CorpusReleaseError('Manifest fields do not match schema version 1')
    if payload['schema_version'] != SCHEMA_VERSION:
        raise CorpusReleaseError('Unsupported release manifest schema')
    corpus_id = payload['corpus_id']
    if not isinstance(corpus_id, str) or not CORPUS_ID.fullmatch(corpus_id):
        raise CorpusReleaseError('Invalid corpus_id')
    declared = payload['documents']
    if not isinstance(declared, list) or not declared:
        raise CorpusReleaseError('Manifest documents must be a nonempty list')
    hashes: dict[str, str] = {}
    for item in declared:
        if not isinstance(item, dict) or set(item) != {'file', 'sha256'}:
            raise CorpusReleaseError('Invalid manifest document entry')
        name, digest = item['file'], item['sha256']
        if not isinstance(name, str) or not FILE_NAME.fullmatch(name):
            raise CorpusReleaseError('Invalid manifest runbook filename')
        if name in hashes:
            raise CorpusReleaseError(f'Duplicate manifest runbook: {name}')
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise CorpusReleaseError(f'Invalid SHA-256 for {name}')
        hashes[name] = digest
    if list(hashes) != sorted(hashes):
        raise CorpusReleaseError('Manifest runbooks must be sorted by filename')
    documents = _read_documents(release_path)
    if set(documents) != set(hashes):
        raise CorpusReleaseError('Release inventory does not match manifest')
    allowed = set(hashes) | {MANIFEST_NAME}
    unexpected = sorted(path.name for path in release_path.iterdir()
                        if path.name not in allowed)
    if unexpected:
        raise CorpusReleaseError(
            f'Unexpected release entries: {", ".join(unexpected)}')
    for name, text in documents.items():
        if _hash_text(text) != hashes[name]:
            raise CorpusReleaseError(f'Runbook hash does not match manifest: {name}')
    return CorpusRelease(
        corpus_id=corpus_id,
        release_path=release_path,
        manifest_hash=sha256(manifest_bytes).hexdigest(),
        documents={Path(name).stem: text for name, text in documents.items()},
    )


def create_release(source: Path, releases: Path, corpus_id: str) -> Path:
    """Validate and atomically publish a new, never-overwritten release directory."""
    if not CORPUS_ID.fullmatch(corpus_id):
        raise CorpusReleaseError('Invalid corpus_id')
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / corpus_id
    if target.exists() or target.is_symlink():
        raise CorpusReleaseError(f'Release already exists: {target}')
    try:
        source_path = source.resolve(strict=True)
    except OSError as exc:
        raise CorpusReleaseError(f'Cannot resolve source directory: {exc}') from exc
    documents = _read_documents(source_path)
    # Import here so integrity-only verification does not import the ML stack.
    from .retrieval import Retriever
    Retriever(documents={Path(name).stem: text for name, text in documents.items()})
    temporary = Path(tempfile.mkdtemp(prefix=f'.{corpus_id}.', dir=releases))
    try:
        for name, text in documents.items():
            (temporary / name).write_text(text, encoding='utf-8', newline='\n')
        manifest = _manifest_bytes(_manifest_payload(corpus_id, documents))
        (temporary / MANIFEST_NAME).write_bytes(manifest)
        verify_release(temporary)
        os.rename(temporary, target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Publish a validated, manifest-pinned runbook release directory.')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--releases', type=Path, required=True)
    parser.add_argument('--corpus-id', required=True)
    args = parser.parse_args()
    release = create_release(args.source, args.releases, args.corpus_id)
    verified = verify_release(release)
    print(json.dumps({
        'corpus_id': verified.corpus_id,
        'release_path': str(verified.release_path),
        'manifest_sha256': verified.manifest_hash,
        'documents': len(verified.documents),
    }, sort_keys=True))


if __name__ == '__main__':
    main()
