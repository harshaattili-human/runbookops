"""Record the frozen v5 validation baseline. Holdout inference is not supported."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

from .evidence_metrics import evidence_supported_and_answered
from .information_dataset import ROOT, load_cases, validate_dataset


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_response(response, documents):
    """Check retained source coordinates/text against the already verified corpus."""
    if response['mode'] not in {'extractive', 'abstained'}:
        raise ValueError('Only extractive baseline responses are allowed')
    for source in response['sources']:
        text = documents[source['document']]
        start, end = source['start_line'], source['end_line']
        lines = text.splitlines()
        if (type(start) is not int or type(end) is not int
                or not 1 <= start <= end <= len(lines)):
            raise ValueError('Source interval is outside the frozen document')
        if source['document_hash'] != hashlib.sha256(text.encode('utf-8')).hexdigest():
            raise ValueError('Source document hash differs')
        if source['text'] != '\n'.join(lines[start - 1:end]).strip():
            raise ValueError('Source text differs from its frozen line interval')
    if response['mode'] == 'abstained':
        if response['sources'] or response['citations']:
            raise ValueError('Abstention must not retain answer evidence')
    else:
        if not response['sources']:
            raise ValueError('Extractive answer requires a source')
        best = response['sources'][0]
        if (response['citations'] != [best['id']]
                or response['answer'] != best['text'].split('\n', 1)[-1].strip()):
            raise ValueError('Extractive answer differs from the cited passage body')


def fraction(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': numerator / denominator if denominator else None}


def summarize(rows):
    pairs = {}
    for row in rows:
        kind = row['kind']
        if kind not in {'supported', 'unsupported'}:
            raise ValueError('Unknown case kind')
        pair = pairs.setdefault(row['pair_id'], {})
        if kind in pair:
            raise ValueError('Duplicate pair member')
        pair[kind] = row
    if not pairs or any(set(pair) != {'supported', 'unsupported'} for pair in pairs.values()):
        raise ValueError('Every pair needs both members')
    supported = [pair['supported'] for pair in pairs.values()]
    unsupported = [pair['unsupported'] for pair in pairs.values()]
    result = {name: fraction(sum(row[field] for row in supported), len(supported))
              for name, field in [('supported_answered', 'answered'),
                  ('supported_expected_top_and_answered', 'expected_top_and_answered'),
                  ('evidence_supported_and_answered', 'evidence_supported_and_answered')]}
    result['unsupported_answered'] = fraction(sum(row['answered'] for row in unsupported), len(unsupported))
    result['fully_correct_pairs'] = fraction(sum(
        pair['supported']['evidence_supported_and_answered'] and not pair['unsupported']['answered']
        for pair in pairs.values()), len(pairs))
    result['unsupported_by_information_type'] = {
        name: fraction(sum(row['answered'] for row in unsupported
                           if row['information_type'] == name), count)
        for name, count in sorted(Counter(row['information_type'] for row in unsupported).items())}
    return result


def evaluate_validation(root=ROOT, *, split='validation'):
    if split != 'validation':
        raise ValueError('This runner supports validation only; holdout inference is unavailable')
    pin = json.loads((root / 'data/evaluation/passage-baseline-code-v5.json').read_text())
    for name, expected in pin['sha256'].items():
        if digest(root / name) != expected:
            raise ValueError(f'Frozen baseline changed: {name}')
    manifest, _ = validate_dataset(root, version='v5')
    cases = load_cases(root, version='v5')
    # Import only after split, baseline code and frozen input checks succeed.
    from .service import TriageService
    service = TriageService(root / 'data')
    documents = service.snapshot.retriever.documents
    rows = []
    for case in cases:
        response = service.triage(case['query'], use_llm=False)
        verify_response(response, documents)
        answered = response['mode'] == 'extractive' and bool(response['answer'].strip())
        top = response['sources'][0]['document'] if response['sources'] else None
        evidence = (evidence_supported_and_answered(response, case['expected_document'], case['evidence'])
                    if case['kind'] == 'supported' else False)
        rows.append({**case, 'response': response, 'answered': answered,
                     'top_document': top,
                     'expected_top_and_answered': answered and top == case['expected_document'],
                     'evidence_supported_and_answered': evidence})
    return {'suite': 'information-validation-v5', 'status': 'baseline-only',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'baseline': pin, 'frozen_inputs_sha256': manifest['sha256'],
            'evaluator_sha256': {name: digest(root / name) for name in (
                'backend/runbookops/passage_validation.py', 'backend/runbookops/evidence_metrics.py',
                'backend/runbookops/information_dataset.py')},
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                'packages': {name: importlib.metadata.version(name) for name in (
                    'scikit-learn', 'numpy', 'fastapi', 'httpx2')}},
            'provenance': manifest['provenance'], 'holdout_queries_scored': 0,
            'metrics': summarize(rows), 'cases': rows,
            'limitations': ['Same-author synthetic validation; not independent or real-incident evidence.',
                'Span coverage is not semantic entailment. No candidate or improvement claim.',
                'Timestamps, request IDs and durations vary; receipt bytes are not reproducible.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing receipt')
    report = evaluate_validation()
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'suite': report['suite'], 'metrics': report['metrics'],
                      'holdout_queries_scored': 0}, indent=2))


if __name__ == '__main__':
    main()
