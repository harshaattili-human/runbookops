from collections import Counter
import json

from runbookops.evaluate import evaluate
from runbookops.service import ROOT


def test_scenario_splits_cover_every_sample_without_leaking_groups():
    report = evaluate()
    seen = set()
    total = 0
    for fold in report['classifier']['folds']:
        train, test = set(fold['train_scenarios']), set(fold['test_scenarios'])
        assert not train & test
        assert not seen & test
        seen |= test
        total += fold['test_samples']
    assert total == report['dataset']['samples']
    assert len(seen) == report['dataset']['scenarios']
    assert sum(sum(row) for row in report['classifier']['confusion_matrix']) == total
    assert report['retrieval']['negative_cases'] > 0
    baseline = report['classifier']['baseline']
    assert sum(sum(row) for row in baseline['confusion_matrix']) == total
    rows = json.loads((ROOT / 'data/incidents.json').read_text())
    predictions = {r['id']: r['predicted'] for r in baseline['predictions']}
    for fold in report['classifier']['folds']:
        counts = Counter(r['category'] for r in rows if r['scenario'] in fold['train_scenarios'])
        expected = sorted(counts, key=lambda category: (-counts[category], category))[0]
        assert fold['dummy_prediction'] == expected
        assert {predictions[r['id']] for r in rows if r['scenario'] in fold['test_scenarios']} == {expected}
