import json
import shutil

import pytest

from runbookops.benchmark import benchmark, fraction, load_suites, retrieval_summary, service_summary, sha256
from runbookops.retrieval import Retriever
from runbookops.service import ROOT


def test_metrics_use_their_own_denominators_and_keep_failed_cases():
    cases = [
        {'kind': 'supported', 'rank': 1, 'abstained': False},
        {'kind': 'supported', 'rank': 2, 'abstained': False},
        {'kind': 'supported', 'rank': None, 'abstained': True},
        {'kind': 'near_unsupported', 'rank': None, 'abstained': False},
        {'kind': 'unrelated', 'rank': None, 'abstained': True},
    ]
    result = retrieval_summary(cases)
    assert result['top1_document_hit'] == fraction(1, 3)
    assert result['hit_within_4_chunks'] == fraction(2, 3)
    assert result['mean_reciprocal_document_rank'] == .5
    assert result['unsupported_false_match'] == fraction(1, 2)
    assert result['near_unsupported_false_match'] == fraction(1, 1)
    assert result['unrelated_false_match'] == fraction(0, 1)
    assert retrieval_summary([])['top1_document_hit']['rate'] is None


def test_routing_abstention_does_not_hide_an_unsupported_answer():
    base = {'kind': 'supported', 'expected_category': 'database', 'expected_document': 'database-pool',
            'category': 'database', 'top_document': 'database-pool', 'needs_review': False, 'mode': 'extractive'}
    cases = [base, {**base, 'category': 'messaging'},
             {**base, 'category': 'needs-review', 'needs_review': True},
             {**base, 'kind': 'near_unsupported', 'needs_review': True}]
    result = service_summary(cases)
    assert result['supported_route_coverage'] == fraction(2, 3)
    assert result['selective_route_accuracy'] == fraction(1, 2)
    assert result['joint_route_and_top1_success'] == fraction(1, 3)
    assert result['unsupported_query_answer_rate'] == fraction(1, 1)
    assert result['unsupported_route_acceptance'] == fraction(0, 1)
    assert service_summary([])['selective_route_accuracy']['rate'] is None


def test_frozen_inputs_reject_changed_content(tmp_path):
    shutil.copytree(ROOT / 'data', tmp_path / 'data')
    path = tmp_path / 'data/runbooks/database-pool.md'
    path.write_text(path.read_text() + '\nChanged evidence.\n')
    with pytest.raises(ValueError, match='Frozen input changed'):
        load_suites(tmp_path)


def test_split_integrity_rejects_duplicates_even_with_updated_hash(tmp_path):
    shutil.copytree(ROOT / 'data', tmp_path / 'data')
    path = tmp_path / 'data/evaluation/holdout-v1.json'
    holdout = json.loads(path.read_text())
    validation = json.loads((tmp_path / 'data/evaluation/validation-v1.json').read_text())
    holdout[0]['scenario'] = validation[0]['scenario']
    path.write_text(json.dumps(holdout))
    manifest_path = tmp_path / 'data/evaluation/manifest-v1.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['sha256']['data/evaluation/holdout-v1.json'] = sha256(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Repeated ID, scenario or query'):
        load_suites(tmp_path)


def test_default_benchmark_never_scores_holdout_queries(monkeypatch):
    _, suites = load_suites(ROOT)
    allowed = {case['query'] for case in suites['validation']}
    original = Retriever.search
    calls = []

    def tracked(self, query, *args, **kwargs):
        assert query in allowed
        calls.append(query)
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(Retriever, 'search', tracked)
    result = benchmark()
    assert result['suite'] == 'validation-v1'
    assert set(calls) == allowed
    for value in result['rankings'].values():
        assert len(value['cases']) == len(allowed)
    assert len(result['service']['cases']) == len(allowed)


def test_ranking_variants_preserve_the_shared_gate_and_source_references():
    retriever = Retriever(ROOT / 'data/runbooks')
    query = 'HikariPool pending database connections grow while active connections are at maximum.'
    assert retriever.search(query) == retriever.search(query, ranking='hybrid')
    for ranking in ('hybrid', 'bm25', 'tfidf'):
        assert retriever.search('xylophone nebula', ranking=ranking) == []
        hits = retriever.search(query, ranking=ranking)
        assert 0 < len(hits) <= 4
        for hit in hits:
            assert len(hit['matched_terms']) >= 2
            assert hit['cosine'] >= retriever.minimum_cosine
            lines = retriever.documents[hit['document']].splitlines()
            assert '\n'.join(lines[hit['start_line'] - 1:hit['end_line']]).strip() == hit['text']
    with pytest.raises(ValueError, match='Unknown ranking'):
        retriever.search(query, ranking='typo')
