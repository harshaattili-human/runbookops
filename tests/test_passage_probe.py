import copy
import math
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch

from runbookops.passage_probe import evaluate_probe, gated_rows, sweep, stable_coverage, pair_sensitivity


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

    def test_stable_coverage_empty_full_partial_and_term_order(self):
        retriever = SimpleNamespace(chunks=[None] * 10, df={'alpha': 1, 'beta': 5})
        self.assertEqual(stable_coverage(retriever, '', 'alpha'), 0.0)
        self.assertEqual(stable_coverage(retriever, 'alpha beta', 'gamma'), 0.0)
        self.assertEqual(stable_coverage(retriever, 'alpha beta', 'beta alpha'), 1.0)
        value = stable_coverage(retriever, 'alpha beta', 'alpha')
        self.assertGreater(value, .5)  # The rarer matched term has more weight.
        self.assertLess(value, 1.0)
        self.assertEqual(value, stable_coverage(retriever, 'beta alpha alpha', 'alpha'))

    def test_full_probe_scores_and_sweeps_are_identical_across_hash_seeds(self):
        root = Path(__file__).resolve().parents[1]
        code = ("import json; from runbookops.passage_probe import evaluate_probe; "
                "r=evaluate_probe(); print(json.dumps({'cases':r['cases'], "
                "'variants':r['variants']},sort_keys=True))")
        outputs = []
        for seed in ['1', '2', '3', '4']:
            result = subprocess.run([sys.executable, '-c', code], cwd=root,
                env={**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(root / 'backend')},
                text=True, capture_output=True, timeout=60, check=True)
            outputs.append(json.loads(result.stdout))
        for output in outputs[1:]:
            self.assertEqual(output, outputs[0])

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

    def test_pair_sensitivity_selects_without_either_omitted_member(self):
        rows = self.rows()
        original = copy.deepcopy(rows)
        result = pair_sensitivity(rows, [.6, .5, .4, 0.0])
        first, second = result['folds']
        self.assertEqual(first['omitted_pair'], 'one')
        self.assertEqual(first['threshold'], 0.0)
        self.assertEqual(second['threshold'], math.nextafter(.5, math.inf))
        # Selection on pair one removes the supported member of omitted pair two.
        self.assertEqual(second['omitted_selected']['supported_answered']['numerator'], 0)
        self.assertEqual(result['omitted_pair_aggregate']['supported_answered']['denominator'], 2)
        self.assertEqual(result['omitted_pair_aggregate']['supported_answered']['numerator'], 1)
        self.assertEqual(rows, original)
        self.assertEqual(result, pair_sensitivity(list(reversed(rows)), [0.0, .4, .5, .6]))

    def test_pair_sensitivity_rejects_incomplete_or_single_pair_and_bad_scores(self):
        for rows, scores in [(self.rows()[:2], [.5, .5]),
                             (self.rows()[:3], [.5] * 3),
                             (self.rows(), [.5]),
                             (self.rows(), [float('nan')] * 4)]:
            with self.subTest(rows=len(rows), scores=scores), self.assertRaises(ValueError):
                pair_sensitivity(rows, scores)

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
