from pathlib import Path

from runbookops.answerability import answerability_summary, evaluate_answerability
from runbookops.benchmark import fraction, load_suites
from runbookops.passage_answerability import evaluate_passage_policy
from runbookops.retrieval import Retriever
from runbookops.service import ROOT, TriageService


def test_summary_keeps_supported_and_unsupported_denominators_separate():
    cases = [
        {'kind': 'supported', 'expected_document': 'a', 'top_document': 'a',
         'baseline': True, 'policy': True},
        {'kind': 'supported', 'expected_document': 'b', 'top_document': 'b',
         'baseline': True, 'policy': False},
        {'kind': 'near_unsupported', 'expected_document': None, 'top_document': 'a',
         'baseline': True, 'policy': False},
        {'kind': 'unrelated', 'expected_document': None, 'top_document': None,
         'baseline': False, 'policy': False},
    ]
    result = answerability_summary(cases, 'policy')
    assert result['supported_answer_rate'] == fraction(1, 2)
    assert result['supported_top_document_success'] == fraction(1, 2)
    assert result['unsupported_answer_rate'] == fraction(0, 2)
    assert result['near_unsupported_answer_rate'] == fraction(0, 1)
    assert result['unrelated_answer_rate'] == fraction(0, 1)
    assert answerability_summary([], 'policy')['supported_answer_rate']['rate'] is None


def test_document_coverage_counts_missing_terms_with_corpus_idf():
    retriever = Retriever(ROOT / 'data/runbooks')
    supported = ('Requests cancelled by the caller leave HikariPool connections checked out. '
                 'Pending database requests grow while idle connections stay at zero.')
    unsupported = ('Redis cache keys disappear under memory pressure. How do I inspect and '
                   'change its eviction policy?')
    supported_hit = retriever.search(supported)[0]
    unsupported_hit = retriever.search(unsupported)[0]
    assert supported_hit['document'] == 'database-pool'
    assert supported_hit['document_coverage'] >= retriever.minimum_document_coverage
    assert unsupported_hit['document'] == 'memory-pressure'
    assert unsupported_hit['document_coverage'] < retriever.minimum_document_coverage
    assert retriever.document_coverage('xylophone nebula', 'unknown') == 0


def test_service_withholds_related_but_insufficient_source(monkeypatch):
    service = TriageService()
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError('generation must not run without sufficient evidence')

    monkeypatch.setattr(service, '_generate', fail_if_called)
    result = service.triage(
        'Redis cache keys disappear under memory pressure. How do I inspect and change its eviction policy?',
        use_llm=True,
    )
    assert result['mode'] == 'abstained'
    assert result['sources'] == []
    assert result['routing']['needs_review']
    assert result['answerability']['status'] == 'insufficient'
    assert result['answerability']['candidate_source_id'] == 'memory-pressure:3'
    assert not called


def test_supported_source_still_uses_the_extractive_path():
    result = TriageService().triage(
        'HikariPool timeout waiting for a database connection; pending connections are rising.'
    )
    assert result['mode'] == 'extractive'
    assert result['sources'][0]['document'] == 'database-pool'
    assert result['answerability']['status'] == 'sufficient'
    assert result['answerability']['coverage'] >= result['answerability']['threshold']


def test_default_answerability_evaluation_never_scores_v2_holdout(monkeypatch):
    _, suites = load_suites(ROOT)
    allowed = {case['query'] for case in suites['validation']}
    original = Retriever.search
    calls = []

    def tracked(self, query, *args, **kwargs):
        assert query in allowed
        calls.append(query)
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(Retriever, 'search', tracked)
    report = evaluate_answerability()
    assert report['suite'] == 'validation-v1'
    assert set(calls) == allowed
    assert len(report['cases']) == len(allowed)


def test_v2_holdout_is_frozen_and_balanced_without_scoring_it():
    _, suites = load_suites(Path(ROOT))
    cases = suites['answerability_holdout']
    assert len(cases) == 26
    assert sum(case['kind'] == 'supported' for case in cases) == 12
    assert sum(case['kind'] == 'near_unsupported' for case in cases) == 12
    assert sum(case['kind'] == 'unrelated' for case in cases) == 2


def test_weighted_coverage_can_measure_a_single_passage():
    retriever = Retriever(ROOT / 'data/runbooks')
    query = 'JWT expiry and clock skew'
    relevant = 'Check token expiry and clock skew without recording raw bearer tokens.'
    assert retriever.weighted_coverage(query, relevant) > .7
    assert retriever.weighted_coverage(query, 'Compare database transaction age.') == 0
    assert retriever.weighted_coverage('', relevant) == 0


def test_passage_experiment_defaults_to_validation(monkeypatch):
    _, suites = load_suites(ROOT)
    allowed = {case['query'] for case in suites['validation']}
    original = Retriever.search
    calls = []

    def tracked(self, query, *args, **kwargs):
        assert query in allowed
        calls.append(query)
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(Retriever, 'search', tracked)
    report = evaluate_passage_policy()
    assert report['suite'] == 'validation-v1'
    assert set(calls) == allowed
    assert report['document_policy']['supported_answer_rate'] == fraction(10, 10)
    assert report['document_policy']['unsupported_answer_rate'] == fraction(1, 10)
    assert report['compound_policy']['supported_answer_rate'] == fraction(10, 10)
    assert report['compound_policy']['unsupported_answer_rate'] == fraction(0, 10)
