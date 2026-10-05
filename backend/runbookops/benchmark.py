"""Score fixed query suites without fitting on queries or selecting thresholds."""

import argparse
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import sklearn

from .classifier import IncidentClassifier
from .retrieval import Retriever
from .service import ROOT, TriageService

RANKINGS = ('hybrid', 'bm25', 'tfidf')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_suites(root: Path) -> tuple[dict, dict]:
    manifest = json.loads((root / 'data/evaluation/manifest-v1.json').read_text())
    for name, expected in manifest['sha256'].items():
        if sha256(root / name) != expected:
            raise ValueError(f'Frozen input changed: {name}; version the dataset before evaluating')
    answerability_manifest = json.loads(
        (root / 'data/evaluation/answerability-manifest-v2.json').read_text())
    for name, expected in answerability_manifest['sha256'].items():
        if sha256(root / name) != expected:
            raise ValueError(f'Frozen input changed: {name}; version the dataset before evaluating')
    runbooks = {str(p.relative_to(root)) for p in (root / 'data/runbooks').glob('*.md')}
    frozen_runbooks = {name for name in manifest['sha256'] if name.startswith('data/runbooks/')}
    if runbooks != frozen_runbooks:
        raise ValueError('Runbook corpus differs from the frozen manifest')
    documents = {Path(name).stem for name in runbooks}
    training = json.loads((root / 'data/incidents.json').read_text())
    categories = {r['category'] for r in training}
    seen_queries = {' '.join(r['text'].lower().split()) for r in training}
    seen_queries.update(' '.join(r['query'].lower().split()) for r in
                        json.loads((root / 'data/evaluation/retrieval.json').read_text()))
    seen_scenarios = {r['scenario'] for r in training}
    seen_ids = set()
    suites = {}
    suite_files = {
        'validation': 'validation-v1.json',
        'holdout': 'holdout-v1.json',
        'answerability_holdout': 'answerability-holdout-v2.json',
    }
    for split, filename in suite_files.items():
        cases = json.loads((root / 'data/evaluation' / filename).read_text())
        for case in cases:
            query = ' '.join(case['query'].lower().split())
            if case['id'] in seen_ids or case['scenario'] in seen_scenarios or query in seen_queries:
                raise ValueError('Repeated ID, scenario or query across evaluation/training data')
            if case['kind'] not in {'supported', 'near_unsupported', 'unrelated'} or not case['rationale'].strip():
                raise ValueError('Every case needs a supported kind and label rationale')
            if case['kind'] == 'supported':
                if case['expected_document'] not in documents or case['expected_category'] not in categories:
                    raise ValueError('Supported case references an unknown document or category')
            elif case['expected_document'] is not None or case['expected_category'] is not None:
                raise ValueError('Unsupported cases must not have positive target labels')
            seen_ids.add(case['id'])
            seen_scenarios.add(case['scenario'])
            seen_queries.add(query)
        if not any(c['kind'] == 'supported' for c in cases) or not any(c['kind'] != 'supported' for c in cases):
            raise ValueError('Each split must include supported and unsupported cases')
        suites[split] = cases
    manifest['answerability_v2'] = answerability_manifest
    return manifest, suites


def fraction(numerator: int, denominator: int) -> dict:
    return {'count': numerator, 'total': denominator,
            'rate': numerator / denominator if denominator else None}


def retrieval_summary(cases: list[dict]) -> dict:
    positives = [r for r in cases if r['kind'] == 'supported']
    negatives = [r for r in cases if r['kind'] != 'supported']
    summary = {
        'top1_document_hit': fraction(sum(r['rank'] == 1 for r in positives), len(positives)),
        'hit_within_4_chunks': fraction(sum(r['rank'] is not None for r in positives), len(positives)),
        'mean_reciprocal_document_rank': (sum(1 / r['rank'] if r['rank'] else 0 for r in positives)
                                          / len(positives) if positives else None),
        'unsupported_false_match': fraction(sum(not r['abstained'] for r in negatives), len(negatives)),
    }
    for kind in ('near_unsupported', 'unrelated'):
        subset = [r for r in negatives if r['kind'] == kind]
        summary[kind + '_false_match'] = fraction(sum(not r['abstained'] for r in subset), len(subset))
    return summary


def service_summary(cases: list[dict]) -> dict:
    positives = [r for r in cases if r['kind'] == 'supported']
    accepted = [r for r in positives if not r['needs_review']]
    negatives = [r for r in cases if r['kind'] != 'supported']
    return {
        'supported_route_coverage': fraction(len(accepted), len(positives)),
        'selective_route_accuracy': fraction(sum(r['category'] == r['expected_category'] for r in accepted), len(accepted)),
        'joint_route_and_top1_success': fraction(sum(
            r['category'] == r['expected_category'] and r['top_document'] == r['expected_document']
            for r in accepted), len(positives)),
        'unsupported_query_answer_rate': fraction(sum(r['mode'] != 'abstained' for r in negatives), len(negatives)),
        'unsupported_route_acceptance': fraction(sum(not r['needs_review'] for r in negatives), len(negatives)),
    }


def benchmark(root: Path = ROOT, split: str = 'validation') -> dict:
    if split not in {'validation', 'holdout'}:
        raise ValueError('Select validation or holdout')
    manifest, suites = load_suites(root)
    service = TriageService(root / 'data')
    comparisons = {}
    for ranking in RANKINGS:
        results = []
        for case in suites[split]:
            hits = service.retriever.search(case['query'], ranking=ranking)
            documents = list(dict.fromkeys(hit['document'] for hit in hits))
            expected = case['expected_document']
            results.append({**case, 'retrieved_documents': documents,
                            'source_ids': [hit['id'] for hit in hits],
                            'rank': documents.index(expected) + 1 if expected in documents else None,
                            'abstained': not bool(hits)})
        comparisons[ranking] = {'summary': retrieval_summary(results), 'cases': results}
    service_cases = []
    for case in suites[split]:
        result = service.triage(case['query'], use_llm=False)
        service_cases.append({**case, 'category': result['routing']['category'],
                              'needs_review': result['routing']['needs_review'], 'mode': result['mode'],
                              'top_document': result['sources'][0]['document'] if result['sources'] else None})
    code = [p for p in sorted((root / 'backend/runbookops').glob('*.py'))]
    return {
        'suite': split + '-v1', 'provenance': manifest['provenance'],
        'protocol': manifest['protocol'], 'frozen_inputs_sha256': manifest['sha256'],
        'code_sha256': {str(p.relative_to(root)): sha256(p) for p in code},
        'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'scikit_learn': sklearn.__version__},
        'configuration': {'maximum_chunks': 4, 'minimum_cosine': Retriever.minimum_cosine,
                          'minimum_term_overlap': 2, 'hybrid_cosine_weight': .65, 'hybrid_bm25_weight': .35,
                          'classifier_score_threshold': IncidentClassifier.threshold,
                          'classifier_minimum_margin': IncidentClassifier.minimum_margin,
                          'gate_shared_across_rankings': True},
        'rankings': comparisons,
        'service': {'summary': service_summary(service_cases), 'cases': service_cases},
        'limitations': [
            'Twenty authored synthetic queries per split; not real incident performance.',
            'Holdout is not blinded or external and becomes exposed after first inspection.',
            'Shared eligibility gate isolates ranking; BM25 variant still uses the cosine gate.',
            'Document labels do not establish passage relevance, answer entailment or calibrated confidence.',
            'Unsupported false matches count returned passages, not hallucinated claims.',
            'Service measurements use the full-data classifier and extractive path, not grouped CV or a live LLM.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['validation', 'holdout'], default='validation')
    args = parser.parse_args()
    report = benchmark(split=args.split)
    path = ROOT / f'reports/retrieval-{args.split}-v1.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'suite': report['suite'],
                      'rankings': {name: value['summary'] for name, value in report['rankings'].items()},
                      'service': report['service']['summary']}, indent=2))


if __name__ == '__main__':
    main()
