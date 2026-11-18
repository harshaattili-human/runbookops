"""Validation-only threshold probe over the pinned v5 baseline receipt."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform

from .information_dataset import ROOT, load_cases, validate_dataset
from .passage_validation import digest, summarize, verify_response

RECEIPT = 'reports/passage-validation-v5-baseline.json'
RECEIPT_SHA256 = 'db9098dda34c56370eeab3ac21cfa2c322e4d9d4cf835654102a9cc1225495f4'


def gated_rows(rows, scores, threshold):
    """Apply an additional gate, never promoting a baseline abstention."""
    if len(rows) != len(scores) or not math.isfinite(threshold):
        raise ValueError('Invalid score vector or threshold')
    result = copy.deepcopy(rows)
    for row, score in zip(result, scores):
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Coverage must be finite and within [0, 1]')
        retained = row['answered'] and score >= threshold
        row['answered'] = retained
        row['expected_top_and_answered'] = retained and row['expected_top_and_answered']
        row['evidence_supported_and_answered'] = retained and row['evidence_supported_and_answered']
    return result


def sweep(rows, scores):
    # Every distinct decision boundary, including equality and reject-all. No grid
    # resolution can hide a narrow feasible interval. These are selection results.
    thresholds = sorted({0.0, *(math.nextafter(score, math.inf) for score in scores)})
    baseline = summarize(rows)
    observations = []
    for threshold in thresholds:
        metrics = summarize(gated_rows(rows, scores, threshold))
        preserves = all(metrics[name]['numerator'] >= baseline[name]['numerator'] for name in (
            'supported_expected_top_and_answered', 'evidence_supported_and_answered'))
        observations.append({'threshold': threshold, 'metrics': metrics,
                             'preserves_supported_metrics': preserves})
    feasible = [row for row in observations if row['preserves_supported_metrics']]
    best = min(feasible, key=lambda row: (row['metrics']['unsupported_answered']['numerator'],
                                         row['threshold']))
    useful = best['metrics']['unsupported_answered']['numerator'] < baseline['unsupported_answered']['numerator']
    return {'baseline': baseline, 'thresholds': observations, 'best_preserving': best,
            'validation_eligible': useful}


def evaluate_probe(root=ROOT, *, split='validation'):
    if split != 'validation':
        raise ValueError('This probe supports validation only')
    if digest(root / RECEIPT) != RECEIPT_SHA256:
        raise ValueError('Pinned baseline receipt changed')
    receipt = json.loads((root / RECEIPT).read_text())
    for group in [receipt['baseline']['sha256'], receipt['evaluator_sha256']]:
        for name, expected in group.items():
            if digest(root / name) != expected:
                raise ValueError(f'Pinned code or training data changed: {name}')
    validate_dataset(root, version='v5')
    cases = load_cases(root, version='v5')
    rows = receipt['cases']
    if len(cases) != len(rows) or any(
            any(row.get(key) != value for key, value in case.items())
            for case, row in zip(cases, rows)):
        raise ValueError('Receipt annotations differ from frozen validation')
    # Existing runtime tokenization/IDF; no service import, training or inference.
    from .retrieval import Retriever
    from .information_answerability_v4 import request_clause
    retriever = Retriever(root / 'data/runbooks')
    scores = {'whole_query': [], 'request_clause': []}
    decisions = []
    for row in rows:
        response = row['response']
        verify_response(response, retriever.documents)
        body = response['answer'] if row['answered'] else ''
        clause = request_clause(row['query'])
        values = {'whole_query': retriever.weighted_coverage(row['query'], body),
                  'request_clause': retriever.weighted_coverage(clause, body)}
        for name, value in values.items():
            scores[name].append(value)
        decisions.append({'id': row['id'], 'request_clause': clause, 'coverage': values,
                          'baseline_answered': row['answered'],
                          'baseline_evidence_supported_and_answered': row['evidence_supported_and_answered']})
    return {'suite': 'information-validation-v5', 'status': 'validation-only threshold selection',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'baseline_receipt': {'path': RECEIPT, 'sha256': RECEIPT_SHA256},
            'probe_sha256': digest(root / 'backend/runbookops/passage_probe.py'),
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'scikit-learn']}},
            'protocol': 'Keep ranking and answers fixed; apply score >= threshold after all baseline gates. '
                        'Minimize unsupported answers with no loss of expected-top or evidence-supported answers; '
                        'break ties by smallest threshold. Enumerate every distinct decision boundary.',
            'variants': {name: sweep(rows, values) for name, values in scores.items()},
            'cases': decisions, 'holdout_queries_scored': 0,
            'limitations': ['Same-author AI-assisted synthetic validation, 10 paired contexts / 20 queries.',
                'Offline post-processing of saved responses, not fresh inference or runtime integration.',
                'Lexical coverage does not establish entailment; final-clause parsing can misidentify the request.',
                'Repeated thresholds are model selection, not independent evaluation; no holdout claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing receipt')
    report = evaluate_probe()
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: {'validation_eligible': result['validation_eligible'],
                            'best_preserving': result['best_preserving']}
                      for name, result in report['variants'].items()}, indent=2))


if __name__ == '__main__':
    main()
