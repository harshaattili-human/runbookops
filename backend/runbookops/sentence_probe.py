"""Validation-only sentence-local coverage over verified, retained v5 responses."""

import argparse
import json
from pathlib import Path
import re

from .information_dataset import ROOT
from .passage_probe import (RECEIPT, evaluate_probe, pair_sensitivity,
                            stable_coverage, sweep)
from .passage_validation import digest


def evidence_units(text):
    """Deterministic punctuation/newline units, not a linguistic sentence parser."""
    return [part.strip() for part in re.split(r'\n+|(?<=[.!?])\s+', text) if part.strip()]


def sentence_scores(retriever, query, units):
    scores = [stable_coverage(retriever, query, unit) for unit in units]
    return {'units': scores, 'maximum': max(scores, default=0.0)}


def evaluate_sentence_probe(root=ROOT, *, split='validation'):
    # Reuse the baseline code/data/response checks before reading saved responses.
    # This also rejects a holdout argument before any file read.
    original = evaluate_probe(root, split=split)
    rows = json.loads((root / RECEIPT).read_text())['cases']
    from .retrieval import Retriever
    from .information_answerability_v4 import request_clause
    retriever = Retriever(root / 'data/runbooks')
    vectors = {'whole_query': [], 'request_clause': []}
    decisions = []
    for row in rows:
        units = evidence_units(row['response']['answer']) if row['answered'] else []
        queries = {'whole_query': row['query'], 'request_clause': request_clause(row['query'])}
        values = {name: sentence_scores(retriever, query, units) for name, query in queries.items()}
        for name, value in values.items():
            vectors[name].append(value['maximum'])
        decisions.append({'id': row['id'], 'queries': queries, 'evidence_units': units,
                          'coverage': values, 'baseline_answered': row['answered']})
    return {'suite': original['suite'], 'status': 'validation-only sentence-local threshold selection',
            'created_at': original['created_at'], 'environment': original['environment'],
            'baseline_receipt': original['baseline_receipt'],
            'code_sha256': {name: digest(root / name) for name in (
                'backend/runbookops/sentence_probe.py', 'backend/runbookops/passage_probe.py',
                'backend/runbookops/passage_validation.py', 'backend/runbookops/evidence_metrics.py',
                'backend/runbookops/retrieval.py', 'backend/runbookops/information_answerability_v4.py')},
            'protocol': original['protocol'] + ' Score the maximum deterministic IDF coverage '
                'over punctuation/newline units from the unchanged extractive answer. '
                'Do not concatenate terms across units or use annotation spans to choose evidence.',
            'whole_answer_comparison': original['variants'],
            'variants': {name: sweep(rows, scores) for name, scores in vectors.items()},
            'pair_sensitivity': {name: pair_sensitivity(rows, scores) for name, scores in vectors.items()},
            'cases': decisions, 'holdout_queries_scored': 0,
            'limitations': original['limitations'] + [
                'Punctuation splitting mishandles abbreviations and wrapped prose; this is not linguistic segmentation.',
                'A sentence can mention the requested terms without supplying the requested fact.',
                'The gate cannot repair an already incorrect returned passage or promote a baseline abstention.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing receipt')
    report = evaluate_sentence_probe()
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: result['best_preserving'] for name, result in report['variants'].items()}, indent=2))


if __name__ == '__main__':
    main()
