"""Reproduce a grouped classification benchmark and retrieval smoke checks."""

import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import sklearn
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

from .classifier import make_pipeline
from .retrieval import Retriever
from .service import ROOT


def evaluate(root: Path = ROOT) -> dict:
    raw = (root / 'data/incidents.json').read_bytes()
    rows = json.loads(raw)
    x = np.array([r['text'] for r in rows])
    y = np.array([r['category'] for r in rows])
    groups = np.array([r['scenario'] for r in rows])
    predictions = np.empty(len(y), dtype=object)
    folds = []
    for train, test in StratifiedGroupKFold(3, shuffle=True, random_state=42).split(x, y, groups):
        assert not set(groups[train]) & set(groups[test])
        model = make_pipeline().fit(x[train].tolist(), y[train])
        predictions[test] = model.predict(x[test].tolist())
        folds.append({'train_scenarios': sorted(set(groups[train])),
                      'test_scenarios': sorted(set(groups[test])),
                      'train_samples': len(train), 'test_samples': len(test)})
    labels = sorted(set(y))
    retriever = Retriever(root / 'data/runbooks')
    cases = json.loads((root / 'data/evaluation/retrieval.json').read_text())
    results = []
    for case in cases:
        hits = retriever.search(case['query'])
        documents = list(dict.fromkeys(hit['document'] for hit in hits))
        expected = case['expected_document']
        rank = documents.index(expected) + 1 if expected in documents else None
        results.append({**case, 'retrieved_documents': documents, 'rank': rank,
                        'abstained': not bool(hits)})
    positives = [r for r in results if r['expected_document']]
    negatives = [r for r in results if not r['expected_document']]
    return {
        'dataset': {'kind': 'synthetic, AI-assisted, illustrative only',
                    'samples': len(rows), 'scenarios': len(set(groups)),
                    'sha256': hashlib.sha256(raw).hexdigest()},
        'environment': {'python': platform.python_version(), 'scikit_learn': sklearn.__version__},
        'classifier': {'split': '3-fold stratified scenario-grouped cross-validation',
                       'macro_f1': float(f1_score(y, predictions, average='macro')),
                       'labels': labels, 'confusion_matrix': confusion_matrix(y, predictions, labels=labels).tolist(),
                       'per_class': classification_report(y, predictions, output_dict=True, zero_division=0),
                       'folds': folds,
                       'errors': [{'id': r['id'], 'text': r['text'], 'expected': r['category'], 'predicted': str(p)}
                                  for r, p in zip(rows, predictions) if r['category'] != p]},
        'retrieval': {'positive_cases': len(positives), 'negative_cases': len(negatives),
                      'hit_rate_at_4_chunks': sum(r['rank'] is not None for r in positives) / len(positives),
                      'mean_reciprocal_document_rank': sum(1 / r['rank'] if r['rank'] else 0 for r in positives) / len(positives),
                      'negative_abstention_rate': sum(r['abstained'] for r in negatives) / len(negatives),
                      'cases': results},
        'limitations': ['Small synthetic corpus; no estimate of real incident performance.',
                       'Retrieval questions are a hand-authored smoke set, not an external holdout.',
                       'Classification scores are not calibrated probabilities.',
                       'Live LLM generation is not evaluated by this benchmark.'],
    }


if __name__ == '__main__':
    report = evaluate()
    destination = ROOT / 'reports/evaluation.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'macro_f1': report['classifier']['macro_f1'],
                      'retrieval_hit_rate': report['retrieval']['hit_rate_at_4_chunks'],
                      'negative_abstention': report['retrieval']['negative_abstention_rate']}, indent=2))
