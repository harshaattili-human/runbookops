"""v5 freeze guards; retrieval and answer scoring are deliberately absent."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from runbookops.information_dataset import DATASETS, ROOT, load_cases, validate_dataset


class InformationDatasetV5Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'data', self.root / 'data')
        self.dataset = DATASETS['v5']

    def rewrite(self, filename, value):
        path = self.root / filename
        path.write_text(json.dumps(value), encoding='utf-8')
        manifest_path = self.root / self.dataset['manifest']
        manifest = json.loads(manifest_path.read_text())
        manifest['sha256'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

    def test_frozen_pairs_load_validation_without_scoring(self):
        manifest, suites = validate_dataset(self.root, version='v5')
        self.assertEqual(manifest['status'], 'frozen-unscored')
        self.assertEqual({name: len(pairs) for name, pairs in suites.items()},
                         {'validation': 10, 'holdout': 10})
        cases = load_cases(self.root, version='v5')
        self.assertEqual(len(cases), 20)
        self.assertTrue(all('-v5-' in case['id'] for case in cases))

    def test_holdout_guard_runs_before_integrity_read(self):
        with patch('runbookops.information_dataset.validate_dataset') as read:
            with self.assertRaisesRegex(ValueError, 'explicit opt-in'):
                load_cases(self.root, 'holdout', version='v5')
            read.assert_not_called()
        self.assertEqual(len(load_cases(self.root, 'holdout', allow_holdout=True, version='v5')), 20)

    def test_v4_query_reuse_is_rejected_even_after_rehash(self):
        validation_name = self.dataset['splits']['validation']
        pairs = json.loads((self.root / validation_name).read_text())
        v4 = json.loads((self.root / 'data/evaluation/information-validation-v4.json').read_text())[0]
        pairs[0]['context'] = v4['context']
        pairs[0]['supported']['request'] = v4['supported']['request']
        self.rewrite(validation_name, pairs)
        with self.assertRaisesRegex(ValueError, 'Repeated normalized query'):
            validate_dataset(self.root, version='v5')


    def test_evidence_alignment_is_checked_even_after_rehash(self):
        filename = self.dataset['splits']['holdout']
        pairs = json.loads((self.root / filename).read_text())
        pairs[0]['supported']['evidence']['quote'] = 'Invented source evidence'
        self.rewrite(filename, pairs)
        with self.assertRaisesRegex(ValueError, 'Evidence quote differs'):
            validate_dataset(self.root, version='v5')

    def test_v4_history_bytes_remain_pinned(self):
        path = self.root / 'data/evaluation/information-holdout-v4.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            validate_dataset(self.root, version='v5')


if __name__ == '__main__':
    unittest.main()
