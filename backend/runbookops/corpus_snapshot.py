"""Pair an index with its served-content identity for one atomic publication."""

from dataclasses import dataclass
from hashlib import sha256
import json

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
