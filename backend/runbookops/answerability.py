"""Compare the extractive baseline with a lexical evidence-coverage policy."""

import argparse
import json
from pathlib import Path

from .benchmark import fraction, load_suites, sha256
from .retrieval import Retriever
from .service import ROOT


def answerability_summary(cases: list[dict], decision: str) -> dict:
    supported = [case for case in cases if case['kind'] == 'supported']
    unsupported = [case for case in cases if case['kind'] != 'supported']
    answered_supported = [case for case in supported if case[decision]]
    summary = {
        'supported_answer_rate': fraction(len(answered_supported), len(supported)),
        'supported_top_document_success': fraction(sum(
            case[decision] and case['top_document'] == case['expected_document']
            for case in supported), len(supported)),
        'unsupported_answer_rate': fraction(sum(case[decision] for case in unsupported),
                                            len(unsupported)),
    }
    for kind in ('near_unsupported', 'unrelated'):
        subset = [case for case in unsupported if case['kind'] == kind]
        summary[kind + '_answer_rate'] = fraction(sum(case[decision] for case in subset),
                                                  len(subset))
    return summary


def evaluate_answerability(root: Path = ROOT, split: str = 'validation') -> dict:
    split_keys = {'validation': 'validation', 'holdout': 'answerability_holdout'}
    if split not in split_keys:
        raise ValueError('Select validation or holdout')
    manifest, suites = load_suites(root)
    answerability_manifest = manifest['answerability_v2']
    retriever = Retriever(root / 'data/runbooks')
    results = []
    for case in suites[split_keys[split]]:
        hits = retriever.search(case['query'])
        coverage = hits[0]['document_coverage'] if hits else None
        baseline_answered = bool(hits)
        policy_answered = bool(hits and coverage >= retriever.minimum_document_coverage)
        results.append({
            **case,
            'top_document': hits[0]['document'] if hits else None,
            'top_source_id': hits[0]['id'] if hits else None,
            'document_coverage': coverage,
            'baseline_answered': baseline_answered,
            'coverage_policy_answered': policy_answered,
        })
    code = sorted((root / 'backend/runbookops').glob('*.py'))
    return {
        'suite': ('validation-v1' if split == 'validation' else 'answerability-holdout-v2'),
        'provenance': answerability_manifest['provenance'],
        'protocol': answerability_manifest['protocol'],
        'holdout_frozen_commit': answerability_manifest['holdout_frozen_commit'],
        'policy': {
            'method': 'IDF-weighted fraction of distinct query terms present in the top document',
            'minimum_document_coverage': retriever.minimum_document_coverage,
            'selection': ('Threshold selected on validation-v1 to retain all supported cases while '
                          'reducing unsupported answers. The v2 holdout was frozen before scoring.'),
        },
        'frozen_inputs_sha256': answerability_manifest['sha256'],
        'code_sha256': {str(path.relative_to(root)): sha256(path) for path in code},
        'baseline': answerability_summary(results, 'baseline_answered'),
        'coverage_policy': answerability_summary(results, 'coverage_policy_answered'),
        'cases': results,
        'limitations': [
            'Authored synthetic cases for ten small runbooks; not real incident performance.',
            'The same author created validation and holdout cases, so this is not blinded or external.',
            'Coverage measures lexical presence anywhere in a document, not passage entailment.',
            'The policy can pass a request whose critical missing terms are outweighed by topical overlap.',
            'Irrelevant query terms can lower coverage enough to suppress otherwise useful evidence.',
            'No live LLM, calibrated probability or operational risk study is included.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['validation', 'holdout'], default='validation')
    args = parser.parse_args()
    report = evaluate_answerability(split=args.split)
    path = ROOT / f'reports/answerability-{args.split}-v2.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'suite': report['suite'],
        'baseline': report['baseline'],
        'coverage_policy': report['coverage_policy'],
    }, indent=2))


if __name__ == '__main__':
    main()
