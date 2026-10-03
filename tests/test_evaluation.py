from runbookops.evaluate import evaluate


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
