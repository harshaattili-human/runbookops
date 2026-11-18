import copy
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from runbookops.passage_probe import evaluate_probe, gated_rows, sweep


class PassageProbeTest(unittest.TestCase):
    def rows(self):
        return [
            {'pair_id': 'one', 'kind': 'supported', 'answered': True,
             'expected_top_and_answered': True, 'evidence_supported_and_answered': True},
            {'pair_id': 'one', 'kind': 'unsupported', 'answered': True,
             'expected_top_and_answered': True, 'evidence_supported_and_answered': False,
             'information_type': 'live_state'},
            {'pair_id': 'two', 'kind': 'supported', 'answered': True,
             'expected_top_and_answered': True, 'evidence_supported_and_answered': False},
            {'pair_id': 'two', 'kind': 'unsupported', 'answered': False,
             'expected_top_and_answered': False, 'evidence_supported_and_answered': False,
             'information_type': 'live_state'}]

    def test_equality_is_retained_and_baseline_abstention_never_promoted(self):
        rows = self.rows()
        original = copy.deepcopy(rows)
        result = gated_rows(rows, [.5, .49, .5, 1.0], .5)
        self.assertEqual([row['answered'] for row in result], [True, False, True, False])
        self.assertFalse(result[1]['expected_top_and_answered'])
        self.assertFalse(result[2]['evidence_supported_and_answered'])
        self.assertEqual(rows, original)

    def test_sweep_finds_narrow_interval_and_preserves_wrong_passage_positive(self):
        result = sweep(self.rows(), [.50001, .5, .50001, 0.0])
        self.assertTrue(result['validation_eligible'])
        best = result['best_preserving']
        self.assertEqual(best['threshold'], math.nextafter(.5, math.inf))
        self.assertEqual(best['metrics']['supported_expected_top_and_answered']['numerator'], 2)
        self.assertEqual(best['metrics']['evidence_supported_and_answered']['numerator'], 1)
        self.assertEqual(best['metrics']['unsupported_answered']['numerator'], 0)
        self.assertTrue(any(row['metrics']['supported_answered']['numerator'] == 0
                            for row in result['thresholds']))

    def test_equal_scores_cannot_be_separated_and_ties_choose_smallest_threshold(self):
        result = sweep(self.rows(), [.5, .5, .5, 0.0])
        self.assertFalse(result['validation_eligible'])
        self.assertEqual(result['best_preserving']['threshold'], 0.0)

    def test_invalid_scores_are_rejected(self):
        for score in [float('nan'), float('inf'), -.01, 1.01]:
            with self.subTest(score=score), self.assertRaises(ValueError):
                gated_rows(self.rows(), [score] * 4, .5)
        with self.assertRaises(ValueError):
            gated_rows(self.rows(), [0.5], .5)
        with self.assertRaises(ValueError):
            gated_rows(self.rows(), [.5] * 4, float('nan'))

    def test_holdout_rejected_before_any_read(self):
        with patch.object(Path, 'read_bytes') as read:
            with self.assertRaisesRegex(ValueError, 'validation only'):
                evaluate_probe(split='holdout')
            read.assert_not_called()

    def test_changed_receipt_rejected_before_dataset_loading(self):
        with patch('runbookops.passage_probe.digest', return_value='changed'), \
                patch('runbookops.passage_probe.validate_dataset') as validate:
            with self.assertRaisesRegex(ValueError, 'receipt changed'):
                evaluate_probe()
            validate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
