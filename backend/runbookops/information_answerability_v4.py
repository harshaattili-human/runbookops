"""Evaluate the fixed v4 request-target candidate on validation only."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .information_dataset import ROOT, load_cases, validate_dataset
from .retrieval import Retriever


# Ordered, inspectable request-target signals. They inspect only the final sentence
# or fragment supplied to the API, never labels, IDs, runbook names or retrieved text.
APPROVAL_OR_ACTION = re.compile(
    r'^(?:approve|authorize|decide|choose|terminate)\b|\b(?:is|are|was|were)\s+approved\b')
UNWRITTEN_ARTIFACT = re.compile(
    r'\b(?:exact|encryption|upload|repair|manual)\b[^?]*\b(?:commands?|scripts?|procedure)\b')
SENSITIVE_VALUE = re.compile(
    r'(?:\b(?:show|print|return|give|provide)\b[^?]*\b'
    r'(?:tokens?|secrets?|credentials?|payload|account\s+numbers?)\b|'
    r'\b(?:accepted\s+raw|stored)\b[^?]*\b(?:tokens?|account\s+numbers?|credentials?)\b|'
    r'\b(?:tokens?|account\s+numbers?|credentials?)\b[^?]*\bstored\b)')
LIVE_STATE = re.compile(
    r'\b(?:current|latest|right now|last hour|how many)\b')
LITERAL_CONFIGURATION = re.compile(
    r'(?:\b(?:exact|precise)\b[^?]*\b(?:port|timeout|limit|maximum|percentage|value)\b|'
    r'\b(?:port|timeout|delay|maximum)\b[^?]*\b\d+(?:\.\d+)?(?:-\w+)?\b|'
    r'/[a-z0-9._~!$&\'()*+,;=:@%/-]+[^?]*\b(?:port|delay|timeout)\b)')


def request_clause(query: str) -> str:
    """Return the last sentence or fragment as the request proxy."""
    parts = [part.strip() for part in re.split(r'(?<=[.!?])\s+', query.strip()) if part.strip()]
    return parts[-1].rstrip('?').strip().casefold() if parts else ''


def external_information_signal(query: str) -> str | None:
    """Classify direct result targets that the local corpus cannot supply."""
    request = request_clause(query)
    for name, pattern in (
        ('approval_or_action', APPROVAL_OR_ACTION),
        ('unwritten_artifact', UNWRITTEN_ARTIFACT),
        ('sensitive_value', SENSITIVE_VALUE),
        ('live_state', LIVE_STATE),
        ('literal_configuration', LITERAL_CONFIGURATION),
    ):
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


def evaluate_validation_candidate(root: Path = ROOT) -> dict:
    """Score only v4 validation; this candidate has no holdout entry point."""
    manifest, _ = validate_dataset(root, version='v4')
    cases = load_cases(root, 'validation', version='v4')
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
        'suite': 'information-validation-v4',
        'status': 'validation-development; holdout unscored',
        'provenance': manifest['provenance'],
        'protocol': manifest['protocol'],
        'candidate': {
            'name': 'request-target guard',
            'input': 'final sentence or fragment; no labels, IDs, runbook names or retrieved text',
            'ordered_signals': {
                'approval_or_action': APPROVAL_OR_ACTION.pattern,
                'unwritten_artifact': UNWRITTEN_ARTIFACT.pattern,
                'sensitive_value': SENSITIVE_VALUE.pattern,
                'live_state': LIVE_STATE.pattern,
                'literal_configuration': LITERAL_CONFIGURATION.pattern,
            },
            'decision': ('answer only when the existing 0.33 document-coverage policy answers '
                         'and no external-information target is detected'),
            'production_status': 'experiment only; TriageService is unchanged',
            'holdout_status': ('integrity-checked only; no holdout query was sent to retrieval '
                               'or answerability scoring'),
        },
        'frozen_inputs_sha256': manifest['sha256'],
        'code_sha256': {str(path.relative_to(root)): sha256(path) for path in code},
        'baseline': summary(results, 'baseline_answered'),
        'candidate_result': summary(results, 'candidate_answered'),
        'cases': results,
        'limitations': [
            'Same-author AI-assisted synthetic validation pairs; not blinded, external or real-incident evidence.',
            'Rules were developed against v4 validation requests and can reflect their authored grammar.',
            'The final-clause proxy can misread multi-request, reordered or punctuation-free incident text.',
            'Request targets do not prove passage entailment or generated-answer correctness.',
            'Literal and lexical rules can reject answerable requests or miss novel external-information phrasing.',
            'V4 holdout is read only for integrity; no holdout retrieval or answerability score is included.',
            'No live LLM, calibration, production traffic or operational risk study is included.',
        ],
    }


def main() -> None:
    report = evaluate_validation_candidate()
    path = ROOT / 'reports/information-validation-v4.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'suite': report['suite'], 'baseline': report['baseline'],
                      'candidate_result': report['candidate_result'],
                      'holdout_status': report['candidate']['holdout_status']}, indent=2))


if __name__ == '__main__':
    main()
