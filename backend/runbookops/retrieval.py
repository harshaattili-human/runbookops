"""Small, inspectable hybrid retriever. No network or embedding download."""

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) > 1 and t not in ENGLISH_STOP_WORDS]


@dataclass(frozen=True)
class Chunk:
    id: str
    document: str
    title: str
    section: str
    start_line: int
    end_line: int
    text: str


class Retriever:
    # Fixed before smoke evaluation; not a calibrated probability threshold.
    minimum_cosine = 0.09
    # Selected on validation-v1 before answerability-holdout-v2 was scored.
    minimum_document_coverage = 0.33

    def __init__(self, directory: Path):
        self.documents = {p.stem: p.read_text(encoding='utf-8')
                          for p in sorted(directory.glob('*.md'))}
        # Hash the indexed text, including trailing newlines, not a later disk read.
        self.document_hashes = {slug: sha256(text.encode('utf-8')).hexdigest()
                                for slug, text in self.documents.items()}
        self.chunks: list[Chunk] = []
        for slug, content in self.documents.items():
            lines = content.splitlines()
            title = lines[0].removeprefix('# ')
            starts = [i for i, line in enumerate(lines) if line.startswith('## ')]
            for n, start in enumerate(starts):
                end = starts[n + 1] if n + 1 < len(starts) else len(lines)
                self.chunks.append(Chunk(f'{slug}:{n+1}', slug, title,
                    lines[start].removeprefix('## '), start + 1, end,
                    '\n'.join(lines[start:end]).strip()))
        if not self.chunks:
            raise ValueError('At least one runbook with ## sections is required')
        corpus = [f'{c.title}\n{c.text}' for c in self.chunks]
        self.vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2),
                                         sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(corpus)
        self.bags = [tokens(t) for t in corpus]
        self.lengths = np.array([len(t) for t in self.bags])
        self.average_length = float(self.lengths.mean())
        self.df: dict[str, int] = {}
        for bag in self.bags:
            for term in set(bag):
                self.df[term] = self.df.get(term, 0) + 1

    def document_coverage(self, query: str, document: str) -> float:
        """Return IDF-weighted query-term coverage in one complete document."""
        if document not in self.documents:
            return 0.0
        return self.weighted_coverage(query, self.documents[document])

    def weighted_coverage(self, query: str, evidence: str) -> float:
        """Return IDF-weighted query-term coverage in arbitrary evidence text."""
        query_terms = set(tokens(query))
        if not query_terms:
            return 0.0
        evidence_terms = set(tokens(evidence))
        weights = {
            term: np.log(1 + (len(self.chunks) - self.df.get(term, 0) + .5)
                         / (self.df.get(term, 0) + .5))
            for term in query_terms
        }
        total = sum(weights.values())
        return float(sum(weights[t] for t in query_terms & evidence_terms) / total)

    def search(self, query: str, limit: int = 4, *, ranking: str = 'hybrid') -> list[dict]:
        if ranking not in {'hybrid', 'bm25', 'tfidf'}:
            raise ValueError('Unknown ranking method')
        query_terms = set(tokens(query))
        cosine = (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()
        # Require two non-stopword overlaps so one generic word cannot create evidence.
        eligible = np.array([len(query_terms & set(bag)) >= 2 for bag in self.bags])
        if not np.any(eligible & (cosine >= self.minimum_cosine)):
            return []
        bm25 = np.zeros(len(self.chunks))
        for term in query_terms:
            freq = np.array([bag.count(term) for bag in self.bags], dtype=float)
            df = self.df.get(term, 0)
            idf = np.log(1 + (len(self.chunks) - df + .5) / (df + .5))
            denominator = freq + 1.5 * (.25 + .75 * self.lengths / self.average_length)
            bm25 += idf * freq * 2.5 / denominator
        normalized = bm25 / max(float(bm25.max()), 1e-12)
        # Evaluation variants change ranking only; every variant uses the same gate.
        scores = {'hybrid': .65 * cosine + .35 * normalized,
                  'bm25': normalized, 'tfidf': cosine}[ranking]
        candidates = [int(i) for i in np.argsort(-scores, kind='stable')
                      if eligible[i] and cosine[i] >= self.minimum_cosine]
        results = []
        for i in candidates[:limit]:
            results.append({**asdict(self.chunks[i]), 'score': round(float(scores[i]), 4),
                            'cosine': round(float(cosine[i]), 4),
                            'document_hash': self.document_hashes[self.chunks[i].document],
                            'document_coverage': round(
                                self.document_coverage(query, self.chunks[i].document), 4),
                            'matched_terms': sorted(query_terms & set(self.bags[i]))})
        return results
