from unittest.mock import patch

import pytest

from runbookops.information_answerability_v4 import (
    evaluate_validation_candidate, external_information_signal, fraction, summary)
from runbookops.information_dataset import ROOT


@pytest.mark.parametrize(('query', 'signal'), [
    ('Active connections are at the maximum and pending requests keep rising.', None),
    ('Use a representative request ID to trace the chain.', None),
    ('Inspect the heap dump only in an approved environment.', None),
    ('Current five-minute p99 latency and failure rate for every hop.', 'live_state'),
    ('An accepted raw bearer token for this caller.', 'sensitive_value'),
    ('Terminate database session 481 now.', 'approval_or_action'),
    ('Pool maximum: 80 connections on each replica.', 'literal_configuration'),
    ('Encryption and upload command for the approved store.', 'unwritten_artifact'),
    ('Production replay for every failed event is approved.', 'approval_or_action'),
    ('Use /ready on port 9080 with a 45-second initial delay.', 'literal_configuration'),
    ('The customer account number stored in process variables.', 'sensitive_value'),
    ('Exact API command to repair variables manually.', 'unwritten_artifact'),
])
def test_request_target_signals_cover_fragments_without_rejecting_incidents(query, signal):
    assert external_information_signal(query) == signal


def test_metric_denominators_and_pairs_remain_explicit():
    cases = [
        {'pair_id': 'a', 'kind': 'supported', 'decision': True,
         'top_document': 'one', 'expected_document': 'one'},
        {'pair_id': 'a', 'kind': 'unsupported', 'decision': False,
         'information_type': 'approval'},
        {'pair_id': 'b', 'kind': 'supported', 'decision': False,
         'top_document': 'two', 'expected_document': 'two'},
        {'pair_id': 'b', 'kind': 'unsupported', 'decision': True,
         'information_type': 'live_state'},
    ]
    result = summary(cases, 'decision')
    assert result['supported_answered'] == fraction(1, 2)
    assert result['unsupported_answered'] == fraction(1, 2)
    assert result['fully_correct_pairs'] == fraction(1, 2)


def test_evaluator_loads_only_v4_validation():
    with patch('runbookops.information_answerability_v4.load_cases') as load:
        load.return_value = []
        report = evaluate_validation_candidate(ROOT)
        load.assert_called_once_with(ROOT, 'validation', version='v4')
    assert report['suite'] == 'information-validation-v4'
    assert 'no holdout query was sent to retrieval' in report['candidate']['holdout_status']
    assert report['cases'] == []


def test_validation_candidate_preserves_supported_decisions_and_rejects_direct_results():
    report = evaluate_validation_candidate(ROOT)
    assert report['baseline']['supported_expected_top_and_answered'] == fraction(9, 10)
    assert report['candidate_result']['supported_expected_top_and_answered'] == fraction(9, 10)
    assert report['baseline']['unsupported_answered'] == fraction(8, 10)
    assert report['candidate_result']['unsupported_answered'] == fraction(0, 10)
    assert report['candidate_result']['fully_correct_pairs'] == fraction(9, 10)
