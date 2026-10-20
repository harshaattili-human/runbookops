"""Validate the frozen contrastive dataset without running retrieval or inference."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'data/evaluation/information-manifest-v3.json'
SPLITS = {split: f'data/evaluation/information-{split}-v3.json'
          for split in ('validation', 'holdout')}
HISTORY = ('data/incidents.json', 'data/evaluation/retrieval.json',
           'data/evaluation/validation-v1.json', 'data/evaluation/holdout-v1.json',
           'data/evaluation/answerability-holdout-v2.json')
INFORMATION_TYPES = {'configuration_value', 'live_state', 'approval',
                     'sensitive_value', 'unwritten_procedure'}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def normalized(text: str) -> str:
    return ' '.join(text.casefold().split())


def _read_json(path: Path):
    def unique_keys(items):
        result = {}
        for key, value in items:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys)


def _fields(value, fields: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == fields, f'Invalid fields: {label}')


def _text(value, label: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f'Missing text: {label}')


def validate_dataset(root: Path = ROOT) -> tuple[dict, dict]:
    """Read labels for integrity checks only; no model or retriever is imported."""
    manifest = _read_json(root / MANIFEST)
    _fields(manifest, {'version', 'created', 'status', 'baseline_commit', 'provenance',
                       'protocol', 'sha256'}, 'manifest')
    require(manifest.get('version') == 'information-v3', 'Unknown dataset version')
    for field in ('provenance', 'protocol', 'baseline_commit'):
        _text(manifest.get(field), field)
    corpus = {str(p.relative_to(root)) for p in (root / 'data/runbooks').glob('*.md')}
    expected = corpus | set(HISTORY) | set(SPLITS.values())
    require(set(manifest.get('sha256', {})) == expected, 'Frozen input inventory differs')
    for name, digest in manifest['sha256'].items():
        require(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest,
                f'Frozen input changed: {name}')

    documents = {Path(name).stem: (root / name).read_text(encoding='utf-8').splitlines()
                 for name in corpus}
    seen_ids, seen_scenarios, seen_queries = set(), set(), set()
    for filename in HISTORY:
        for case in _read_json(root / filename):
            seen_ids.add(case.get('id'))
            seen_scenarios.add(case.get('scenario'))
            seen_queries.add(normalized(case.get('query', case.get('text', ''))))

    suites = {}
    for split, filename in SPLITS.items():
        pairs = _read_json(root / filename)
        require(isinstance(pairs, list) and bool(pairs), 'Empty or invalid split')
        document_counts = Counter()
        for pair in pairs:
            _fields(pair, {'id', 'scenario', 'document', 'context', 'supported', 'unsupported'}, 'pair')
            for key in ('id', 'scenario', 'document', 'context'):
                _text(pair[key], key)
            require(pair['id'] not in seen_ids and pair['scenario'] not in seen_scenarios,
                    'Repeated ID or scenario across splits/history')
            seen_ids.add(pair['id'])
            seen_scenarios.add(pair['scenario'])
            require(pair['document'] in documents, 'Unknown topic document')
            document_counts[pair['document']] += 1
            positive, negative = pair['supported'], pair['unsupported']
            _fields(positive, {'request', 'evidence', 'rationale'}, 'supported')
            _fields(negative, {'request', 'information_type', 'missing_information'}, 'unsupported')
            _text(positive['rationale'], 'supported rationale')
            _text(negative['missing_information'], 'missing information')
            require(isinstance(negative['information_type'], str)
                    and negative['information_type'] in INFORMATION_TYPES, 'Unknown information type')
            for kind, case in (('supported', positive), ('unsupported', negative)):
                _text(case['request'], 'request')
                case_id = pair['id'] + '-' + kind
                require(case_id not in seen_ids, 'Repeated case ID')
                seen_ids.add(case_id)
                query = pair['context'] + ' ' + case['request']
                require(len(query) <= 2000, 'Query exceeds API character limit')
                key = normalized(query)
                require(key not in seen_queries, 'Repeated normalized query across splits/history')
                seen_queries.add(key)
            evidence = positive['evidence']
            _fields(evidence, {'start_line', 'end_line', 'quote'}, 'evidence')
            start, end = evidence['start_line'], evidence['end_line']
            lines = documents[pair['document']]
            require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines),
                    'Invalid evidence line range')
            _text(evidence['quote'], 'evidence quote')
            require('\n'.join(lines[start - 1:end]) == evidence['quote'], 'Evidence quote differs')
            require(any(line.strip() and not line.startswith('#') for line in lines[start - 1:end]),
                    'Evidence cannot consist only of headings or whitespace')
        # This version deliberately covers every runbook once per split, in pairs.
        require(document_counts == Counter({name: 1 for name in documents}),
                'Each split needs one contrast pair per frozen runbook')
        suites[split] = pairs
    return manifest, suites


def load_cases(root: Path = ROOT, split: str = 'validation', *, allow_holdout: bool = False) -> list[dict]:
    """Default development input is validation; holdout access requires an explicit opt-in."""
    require(split in SPLITS, 'Select validation or holdout')
    require(split != 'holdout' or allow_holdout, 'Holdout requires explicit opt-in after candidate freeze')
    _, suites = validate_dataset(root)
    cases = []
    for pair in suites[split]:
        for kind in ('supported', 'unsupported'):
            cases.append({
                'id': pair['id'] + '-' + kind, 'pair_id': pair['id'], 'scenario': pair['scenario'],
                'query': pair['context'] + ' ' + pair[kind]['request'], 'kind': kind,
                'expected_document': pair['document'] if kind == 'supported' else None,
                'topic_document': pair['document'], **{k: v for k, v in pair[kind].items() if k != 'request'},
            })
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    _, suites = validate_dataset(args.root)
    print(json.dumps({'version': 'information-v3', 'operation': 'integrity-check-only',
        'splits': {split: {'pairs': len(pairs), 'supported': len(pairs), 'unsupported': len(pairs),
                           'missing_information_types': dict(Counter(p['unsupported']['information_type'] for p in pairs))}
                   for split, pairs in suites.items()},
        'scored_queries': 0}, indent=2))


if __name__ == '__main__':
    main()
