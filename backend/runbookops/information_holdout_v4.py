"""Explicit reproduction of the one-shot v4 holdout comparison; never run by CI."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform

from .information_answerability_v4 import external_information_signal, sha256, summary
from .information_dataset import ROOT, load_cases, validate_dataset
from .retrieval import Retriever


CANDIDATE_COMMIT = 'edcada1089c663aa7466109aa01f4114b43d7a83'
FROZEN_CODE = {
    'backend/runbookops/information_answerability_v4.py':
        'b55abd02ac2a5249823b8b4a0b1502faa87fdcd45e46bc22cde47d4fa08f10ce',
    'backend/runbookops/retrieval.py':
        '789bebbc9f98aec3d10cb10ab97b9b5d49069ead98b88539ccd088f974c73b3b',
}


def evaluate_holdout(root: Path = ROOT, *, allow_holdout: bool = False) -> dict:
    if not allow_holdout:
        raise ValueError('Holdout scoring requires explicit opt-in after candidate publication')
    for name, expected in FROZEN_CODE.items():
        if sha256(root / name) != expected:
            raise ValueError(f'Published candidate/ranking changed: {name}')
    manifest, _ = validate_dataset(root, version='v4')
    cases = load_cases(root, 'holdout', version='v4', allow_holdout=True)
    retriever = Retriever(root / 'data/runbooks')
    results = []
    for case in cases:
        hits = retriever.search(case['query'])
        coverage = hits[0]['document_coverage'] if hits else None
        baseline = bool(hits and coverage >= retriever.minimum_document_coverage)
        signal = external_information_signal(case['query'])
        results.append({**case,
            'top_document': hits[0]['document'] if hits else None,
            'top_source_id': hits[0]['id'] if hits else None,
            'document_coverage': coverage,
            'baseline_answered': baseline,
            'candidate_answered': baseline and signal is None,
            'candidate_signal': signal,
        })
    baseline = summary(results, 'baseline_answered')
    candidate = summary(results, 'candidate_answered')
    eligible = (candidate['unsupported_answered']['numerator']
                < baseline['unsupported_answered']['numerator']
                and candidate['supported_expected_top_and_answered']['numerator']
                >= baseline['supported_expected_top_and_answered']['numerator'])
    return {
        'suite': 'information-holdout-v4',
        'status': 'exposed after first joint score; never tune on these cases',
        'candidate_commit': CANDIDATE_COMMIT,
        'scored_at_utc': datetime.now(timezone.utc).isoformat(),
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
            'scikit-learn': importlib.metadata.version('scikit-learn'),
            'numpy': importlib.metadata.version('numpy')},
        'command': 'PYTHONPATH=backend python -m runbookops.information_holdout_v4 --allow-holdout',
        'provenance': manifest['provenance'], 'protocol': manifest['protocol'],
        'frozen_inputs_sha256': manifest['sha256'], 'frozen_code_sha256': FROZEN_CODE,
        'evaluator_sha256': sha256(Path(__file__)),
        'baseline': baseline, 'candidate_result': candidate,
        'numeric_adoption_criterion_met': eligible,
        'runtime_status': 'unchanged; passing application integration required in addition to numeric criterion',
        'cases': results,
        'limitations': [
            '20 synthetic queries in 10 paired contexts, not 20 independent incidents.',
            'Same-author AI-assisted public labels; not blinded or externally reviewed.',
            'Fixed lexical request-target rules; no passage entailment or live LLM evaluation.',
            'Holdout is now exposed; reproduction is regression evidence, not another fresh evaluation.',
            'No production accuracy, calibration or operational risk claim.',
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-holdout', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/information-holdout-v4.json')
    args = parser.parse_args()
    # Never overwrite the first recorded result implicitly.
    if args.output.exists():
        parser.error('Output exists; select a new --output for an explicitly exposed reproduction')
    report = evaluate_holdout(allow_holdout=args.allow_holdout)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in (
        'suite', 'baseline', 'candidate_result', 'numeric_adoption_criterion_met')}, indent=2))


if __name__ == '__main__':
    main()
