"""Synthetic metric fixtures; integration reads validation only."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runbookops.passage_probe import stable_coverage
from runbookops.sentence_probe import evidence_units, evaluate_sentence_probe, sentence_scores


class SentenceProbeTest(unittest.TestCase):
    def test_punctuation_newlines_and_empty_units(self):
        self.assertEqual(evidence_units('  Alpha beta. Gamma!\n\n- Delta? Epsilon  '),
                         ['Alpha beta.', 'Gamma!', '- Delta?', 'Epsilon'])
        self.assertEqual(evidence_units(' \n '), [])
        self.assertEqual(evidence_units('limit 1.5; host.example'), ['limit 1.5; host.example'])

    def test_terms_in_separate_units_cannot_combine_into_full_support(self):
        retriever = SimpleNamespace(chunks=[None] * 10, df={'alpha': 1, 'beta': 1})
        units = evidence_units('Alpha. Beta.')
        result = sentence_scores(retriever, 'alpha beta', units)
        self.assertEqual(result, {'units': [.5, .5], 'maximum': .5})
        self.assertEqual(stable_coverage(retriever, 'alpha beta', ' '.join(units)), 1.0)
        self.assertEqual(sentence_scores(retriever, 'alpha beta', ['Alpha beta.'])['maximum'], 1.0)
        self.assertEqual(sentence_scores(retriever, 'alpha beta', [])['maximum'], 0.0)
        self.assertEqual(sentence_scores(retriever, '', units)['maximum'], 0.0)

    def test_holdout_rejected_before_any_read(self):
        with patch.object(Path, 'read_bytes') as read:
            with self.assertRaisesRegex(ValueError, 'validation only'):
                evaluate_sentence_probe(split='holdout')
            read.assert_not_called()

    def test_validation_scores_cannot_exceed_whole_answer_coverage(self):
        result = evaluate_sentence_probe()
        from runbookops.passage_probe import evaluate_probe
        original = evaluate_probe()
        for row, whole in zip(result['cases'], original['cases']):
            self.assertEqual(row['id'], whole['id'])
            for name, scores in row['coverage'].items():
                self.assertLessEqual(scores['maximum'], whole['coverage'][name])
                self.assertEqual(len(scores['units']), len(row['evidence_units']))
            if not row['baseline_answered']:
                self.assertEqual(row['evidence_units'], [])
        self.assertEqual(result['holdout_queries_scored'], 0)
        self.assertEqual(result['whole_answer_comparison'], original['variants'])


if __name__ == '__main__':
    unittest.main()
