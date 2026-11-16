import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runbookops.passage_validation import evaluate_validation, summarize, verify_response


class PassageValidationTest(unittest.TestCase):
    def fixture(self):
        text = '# Fixture\n## Steps\nRead evidence.\n'
        source = {'id': 'fixture:1', 'document': 'fixture', 'start_line': 2, 'end_line': 3,
                  'text': '## Steps\nRead evidence.',
                  'document_hash': hashlib.sha256(text.encode()).hexdigest()}
        return {'mode': 'extractive', 'sources': [source], 'citations': ['fixture:1'],
                'answer': 'Read evidence.'}, {'fixture': text}

    def test_retained_text_and_hash_are_checked(self):
        response, documents = self.fixture()
        verify_response(response, documents)
        for field, value in [('text', 'invented'), ('document_hash', '0' * 64), ('end_line', 99)]:
            with self.subTest(field=field):
                altered = copy.deepcopy(response)
                altered['sources'][0][field] = value
                with self.assertRaises(ValueError):
                    verify_response(altered, documents)

    def test_citation_and_extracted_answer_must_match(self):
        response, documents = self.fixture()
        for field, value in [('citations', ['wrong']), ('answer', 'invented'), ('mode', 'local-llm')]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    verify_response({**response, field: value}, documents)
        verify_response({'mode': 'abstained', 'sources': [], 'citations': []}, documents)
        with self.assertRaises(ValueError):
            verify_response({**response, 'mode': 'abstained'}, documents)

    def test_pair_metrics_keep_wrong_passage_separate_from_right_document(self):
        rows = []
        for pair, evidence, negative in [('a', True, False), ('b', False, False), ('c', False, True)]:
            rows.extend([
                {'pair_id': pair, 'kind': 'supported', 'answered': True,
                 'expected_top_and_answered': True, 'evidence_supported_and_answered': evidence},
                {'pair_id': pair, 'kind': 'unsupported', 'answered': negative,
                 'information_type': 'live_state'}])
        result = summarize(rows)
        self.assertEqual(result['supported_expected_top_and_answered']['numerator'], 3)
        for name in ['evidence_supported_and_answered', 'fully_correct_pairs', 'unsupported_answered']:
            self.assertEqual(result[name]['numerator'], 1)
            self.assertEqual(result[name]['denominator'], 3)
        self.assertEqual(result['unsupported_by_information_type']['live_state']['numerator'], 1)
        with self.assertRaisesRegex(ValueError, 'both members'):
            summarize(rows[:-1])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            summarize(rows + [rows[0]])

    def test_holdout_rejected_before_reading_files(self):
        with patch.object(Path, 'read_text') as read:
            with self.assertRaisesRegex(ValueError, 'validation only'):
                evaluate_validation(split='holdout')
            read.assert_not_called()

    def test_changed_baseline_rejected_before_dataset_or_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data/evaluation').mkdir(parents=True)
            (root / 'baseline.py').write_text('changed')
            (root / 'data/evaluation/passage-baseline-code-v5.json').write_text(
                json.dumps({'sha256': {'baseline.py': '0' * 64}}))
            with patch('runbookops.passage_validation.validate_dataset') as validate:
                with self.assertRaisesRegex(ValueError, 'Frozen baseline changed'):
                    evaluate_validation(root)
                validate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
