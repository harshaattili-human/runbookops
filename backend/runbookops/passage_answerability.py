"""Compare the current document gate with a localized passage-coverage gate."""

import argparse
import json
from pathlib import Path

from .answerability import answerability_summary
from .benchmark import load_suites, sha256
from .retrieval import Retriever
from .service import ROOT

# Selected on validation-v1: just below its lowest supported passage score (0.2702)
# and above its highest unsupported passage score (0.2528).
MINIMUM_PASSAGE_COVERAGE = 0.27


def evaluate_passage_policy(root: Path = ROOT, split: str = 'validation') -> dict:
    split_keys = {'validation': 'validation', 'exposed-v2': 'answerability_holdout'}
    if split not in split_keys:
        raise ValueError('Select validation or exposed-v2')
    manifest, suites = load_suites(root)
    retriever = Retriever(root / 'data/runbooks')
    results = []
    for case in suites[split_keys[split]]:
        hits = retriever.search(case['query'])
        document_coverage = hits[0]['document_coverage'] if hits else None
        passage_coverage = (round(retriever.weighted_coverage(
            case['query'], f"{hits[0]['title']}\n{hits[0]['text']}"), 4) if hits else None)
        document_policy_answered = bool(
            hits and document_coverage >= retriever.minimum_document_coverage)
        compound_policy_answered = bool(
            document_policy_answered and passage_coverage >= MINIMUM_PASSAGE_COVERAGE)
        results.append({
            **case,
            'top_document': hits[0]['document'] if hits else None,
            'top_source_id': hits[0]['id'] if hits else None,
            'document_coverage': document_coverage,
            'top_passage_coverage': passage_coverage,
            'document_policy_answered': document_policy_answered,
            'compound_policy_answered': compound_policy_answered,
        })
    code = sorted((root / 'backend/runbookops').glob('*.py'))
    return {
        'suite': 'validation-v1' if split == 'validation' else 'answerability-holdout-v2-exposed',
        'provenance': manifest['answerability_v2']['provenance'],
        'protocol': (
            'Select the passage threshold on validation-v1. Compare against the current '
            'document policy. The v2 suite is already exposed and is used only as a regression '
            'check, not as a fresh holdout or tuning set.'),
        'policy': {
            'document_minimum': retriever.minimum_document_coverage,
            'passage_minimum': MINIMUM_PASSAGE_COVERAGE,
            'passage': 'top retrieved chunk text plus its document title',
            'decision': 'both document and top-passage coverage must meet their thresholds',
            'production_status': 'experiment only; the service still uses document coverage',
        },
        'frozen_inputs_sha256': manifest['answerability_v2']['sha256'],
        'code_sha256': {str(path.relative_to(root)): sha256(path) for path in code},
        'document_policy': answerability_summary(results, 'document_policy_answered'),
        'compound_policy': answerability_summary(results, 'compound_policy_answered'),
        'cases': results,
        'limitations': [
            'Authored synthetic cases for ten small runbooks; not real incident performance.',
            'The validation threshold separates two nearby observed scores and may be overfit.',
            'Lexical overlap within a passage does not establish that it answers the request.',
            'The v2 regression suite was visible before this experiment and is not a new holdout.',
            'No production decision, live LLM behavior or security control changed.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['validation', 'exposed-v2'], default='validation')
    args = parser.parse_args()
    report = evaluate_passage_policy(split=args.split)
    filename = ('passage-validation-v1.json' if args.split == 'validation'
                else 'passage-exposed-v2.json')
    path = ROOT / 'reports' / filename
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'suite': report['suite'],
        'document_policy': report['document_policy'],
        'compound_policy': report['compound_policy'],
    }, indent=2))


if __name__ == '__main__':
    main()
