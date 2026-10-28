"""Pair an index with its served-content identity for one atomic publication."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .corpus_release import CORPUS_ID

from .retrieval import Retriever


@dataclass(frozen=True)
class CorpusSnapshot:
    retriever: Retriever
    documents_sha256: str
    corpus_id: str | None = None
    manifest_sha256: str | None = None

    @classmethod
    def capture(cls, retriever: Retriever, *, corpus_id: str | None = None,
                manifest_sha256: str | None = None) -> 'CorpusSnapshot':
        inventory = json.dumps(retriever.document_hashes, sort_keys=True,
                               separators=(',', ':'), ensure_ascii=True).encode('utf-8')
        return cls(retriever, sha256(inventory).hexdigest(), corpus_id, manifest_sha256)

    def identity(self) -> dict[str, object]:
        # Detached public metadata. Do not expose an operator's resolved release path.
        return {'schema_version': 1, 'source': 'release' if self.manifest_sha256 else 'directory',
                'corpus_id': self.corpus_id, 'manifest_sha256': self.manifest_sha256,
                'documents_sha256': self.documents_sha256}


class CorpusConflict(ValueError):
    """The caller's observed content identity no longer matches publication."""


def validate_identity(value):
    """Validate a complete public identity and detach it from caller mutation."""
    fields = {'schema_version', 'source', 'corpus_id', 'manifest_sha256', 'documents_sha256'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Expected a complete corpus identity')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Invalid corpus identity schema')
    def digest(text):
        return isinstance(text, str) and re.fullmatch(r'[0-9a-f]{64}', text) is not None
    if not digest(value['documents_sha256']):
        raise ValueError('Invalid documents hash')
    if value['source'] == 'directory':
        if value['corpus_id'] is not None or value['manifest_sha256'] is not None:
            raise ValueError('Directory identity cannot contain release metadata')
    elif value['source'] == 'release':
        if (not isinstance(value['corpus_id'], str) or not CORPUS_ID.fullmatch(value['corpus_id'])
                or not digest(value['manifest_sha256'])):
            raise ValueError('Invalid release identity')
    else:
        raise ValueError('Invalid corpus source')
    return dict(value)
