"""Evaluate a request-shape answerability candidate on the frozen v3 pairs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .information_dataset import ROOT, load_cases, validate_dataset
from .retrieval import Retriever


# Ordered, inspectable request shapes. These operate on the final question only;
# neither runbook names nor evaluation labels enter the decision.
GUIDANCE_SHAPES = (
    re.compile(r'\b(?:how|what|which)\b[^?]*\b(?:should|must|need to|required|applies|belong)\b'),
)
EXTERNAL_INFORMATION_SHAPES = (
    ('approval_or_decision', re.compile(r'^(?:approve|authorize|decide|choose)\b')),
    ('sensitive_value', re.compile(
        r'^(?:show|print|return|give|provide)\b[^?]*\b'
        r'(?:token|secret|credential|personal|account|payload)\b')),
    ('unwritten_artifact', re.compile(
        r'^(?:give|provide|write|generate)\b[^?]*\b(?:commands?|scripts?|procedure)\b')),
    ('live_or_specific_value', re.compile(
        r'\b(?:currently|right now|latest|last hour|exact|precise|maximum|percentage|'
        r'how many|stored|configured|deployed)\b')),
)


def request_clause(query: str) -> str:
    """Return the final sentence, the API's only available proxy for the request."""
    parts = [part.strip() for part in re.split(r'(?<=[.!?])\s+', query.strip()) if part.strip()]
    return parts[-1].rstrip('?').strip().casefold() if parts else ''


def external_information_signal(query: str) -> str | None:
    """Detect request forms that ask for an external result rather than guidance."""
    request = request_clause(query)
    if any(pattern.search(request) for pattern in GUIDANCE_SHAPES):
        return None
    for name, pattern in EXTERNAL_INFORMATION_SHAPES:
        if pattern.search(request):
            return name
    return None


def fraction(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'rate': round(numerator / denominator, 4) if denominator else None}


def summary(cases: list[dict], decision: str) -> dict:
    supported = [case for case in cases if case['kind'] == 'supported']
    unsupported = [case for case in cases if case['kind'] == 'unsupported']
    pairs = {case['pair_id'] for case in cases}
    result = {
        'supported_answered': fraction(sum(case[decision] for case in supported), len(supported)),
        'supported_expected_top_and_answered': fraction(sum(
            case[decision] and case['top_document'] == case['expected_document']
            for case in supported), len(supported)),
        'unsupported_answered': fraction(sum(case[decision] for case in unsupported), len(unsupported)),
        'fully_correct_pairs': fraction(sum(
            any(case['kind'] == 'supported' and case[decision]
                and case['top_document'] == case['expected_document'] for case in cases
                if case['pair_id'] == pair_id)
            and any(case['kind'] == 'unsupported' and not case[decision] for case in cases
                    if case['pair_id'] == pair_id)
            for pair_id in pairs), len(pairs)),
    }
    result['unsupported_by_information_type'] = {
        information_type: fraction(sum(
            case[decision] for case in unsupported
            if case['information_type'] == information_type), count)
        for information_type, count in sorted(Counter(
            case['information_type'] for case in unsupported).items())
    }
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_information_policy(root: Path = ROOT, split: str = 'validation', *,
                                allow_holdout: bool = False) -> dict:
    if split not in {'validation', 'holdout'}:
        raise ValueError('Select validation or holdout')
    if split == 'holdout' and not allow_holdout:
        raise ValueError('Holdout scoring requires explicit opt-in after candidate publication')
    manifest, _ = validate_dataset(root)
    cases = load_cases(root, split, allow_holdout=allow_holdout)
    retriever = Retriever(root / 'data/runbooks')
    results = []
    for case in cases:
        hits = retriever.search(case['query'])
        coverage = hits[0]['document_coverage'] if hits else None
        baseline_answered = bool(hits and coverage >= retriever.minimum_document_coverage)
        signal = external_information_signal(case['query'])
        results.append({
            **case,
            'top_document': hits[0]['document'] if hits else None,
            'top_source_id': hits[0]['id'] if hits else None,
            'document_coverage': coverage,
            'baseline_answered': baseline_answered,
            'candidate_answered': baseline_answered and signal is None,
            'candidate_signal': signal,
        })
    code = sorted((root / 'backend/runbookops').glob('*.py'))
    return {
        'suite': f'information-{split}-v3',
        'status': 'validation-development' if split == 'validation' else 'holdout-first-score',
        'provenance': manifest['provenance'],
        'protocol': manifest['protocol'],
        'candidate': {
            'name': 'request-shape guard',
            'input': 'final sentence of the incident query; no labels, IDs or retrieved text',
            'guidance_precedence': [pattern.pattern for pattern in GUIDANCE_SHAPES],
            'external_information_shapes': {
                name: pattern.pattern for name, pattern in EXTERNAL_INFORMATION_SHAPES
            },
            'decision': ('answer only when the existing 0.33 document-coverage policy answers '
                         'and no external-information request shape is detected'),
            'production_status': ('adopted unchanged in TriageService after the preregistered '
                                  'holdout criterion passed; this evaluator remains separate'),
        },
        'frozen_inputs_sha256': manifest['sha256'],
        'code_sha256': {str(path.relative_to(root)): sha256(path) for path in code},
        'baseline': summary(results, 'baseline_answered'),
        'candidate_result': summary(results, 'candidate_answered'),
        'cases': results,
        'limitations': [
            'Same-author AI-assisted synthetic pairs; not blinded, external or real-incident evidence.',
            'Rules were developed against validation requests and can reflect their authored grammar.',
            'The final-sentence proxy can misread multi-question, fragmentary or reordered incident text.',
            'Request shape does not prove entailment; an answer can still omit or distort requested guidance.',
            'The candidate does not inspect source propositions and may reject answerable numeric or live-data procedures.',
            'No live LLM, calibration, production traffic or operational risk study is included.',
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['validation', 'holdout'], default='validation')
    parser.add_argument('--allow-holdout', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    report = evaluate_information_policy(args.root, args.split, allow_holdout=args.allow_holdout)
    path = args.root / 'reports' / f'information-{args.split}-v3.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'suite': report['suite'], 'baseline': report['baseline'],
                      'candidate_result': report['candidate_result']}, indent=2))


if __name__ == '__main__':
    main()
