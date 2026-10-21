from unittest.mock import patch

import pytest

from runbookops.information_answerability import (
    evaluate_information_policy, external_information_signal, fraction, summary)
from runbookops.information_dataset import ROOT


@pytest.mark.parametrize(('query', 'signal'), [
    ('Latency rose. Which timeout values should we compare?', None),
    ('A token failed. How should we inspect it without copying secret credentials?', None),
    ('A lock remains. What evidence is required before a session ends?', None),
    ('A lock remains. Authorize ending the session.', 'approval_or_decision'),
    ('A caller failed. Show the personal account payload.', 'sensitive_value'),
    ('A dump exists. Provide the encryption script.', 'unwritten_artifact'),
    ('A probe failed. State the exact port configured.', 'live_or_specific_value'),
    ('A replay ended. How many duplicate records exist?', 'live_or_specific_value'),
    ('A route failed. Summarize the documented investigation.', None),
])
def test_request_shape_is_based_on_the_final_question(query, signal):
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
    assert result['unsupported_by_information_type']['approval'] == fraction(0, 1)
    assert result['unsupported_by_information_type']['live_state'] == fraction(1, 1)


def test_default_evaluator_scores_validation_only():
    with patch('runbookops.information_answerability.load_cases') as load:
        load.return_value = []
        report = evaluate_information_policy(ROOT)
        load.assert_called_once_with(ROOT, 'validation', allow_holdout=False)
    assert report['suite'] == 'information-validation-v3'
    assert report['cases'] == []


def test_holdout_requires_explicit_opt_in_before_inputs_are_read():
    with patch('runbookops.information_answerability.validate_dataset') as validate, \
         patch('runbookops.information_answerability.load_cases') as load:
        with pytest.raises(ValueError, match='explicit opt-in'):
            evaluate_information_policy(ROOT, 'holdout')
        validate.assert_not_called()
        load.assert_not_called()


def test_validation_candidate_preserves_supported_decisions_and_rejects_direct_results():
    report = evaluate_information_policy(ROOT)
    assert report['baseline']['supported_expected_top_and_answered'] == fraction(9, 10)
    assert report['candidate_result']['supported_expected_top_and_answered'] == fraction(9, 10)
    assert report['baseline']['unsupported_answered'] == fraction(8, 10)
    assert report['candidate_result']['unsupported_answered'] == fraction(0, 10)
    assert report['candidate_result']['fully_correct_pairs'] == fraction(9, 10)
