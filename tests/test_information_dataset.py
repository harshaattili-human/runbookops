"""Dataset contract tests: no retrieval, fitting, or answer scoring."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runbookops.information_dataset import ROOT, MANIFEST, SPLITS, load_cases, validate_dataset


class InformationDatasetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'data', self.root / 'data')

    def rewrite(self, filename, value):
        """Rehash a mutated test fixture to exercise checks beyond the checksum."""
        path = self.root / filename
        path.write_text(json.dumps(value), encoding='utf-8')
        manifest = json.loads((self.root / MANIFEST).read_text())
        manifest['sha256'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root / MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')

    def pairs(self, split='validation'):
        return json.loads((self.root / SPLITS[split]).read_text())

    def test_frozen_inputs_and_default_validation_loader(self):
        _, suites = validate_dataset(self.root)
        self.assertEqual({name: len(pairs) for name, pairs in suites.items()},
                         {'validation': 10, 'holdout': 10})
        cases = load_cases(self.root)
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(c['kind'] == 'supported' for c in cases), 10)
        self.assertTrue(all(c['id'].startswith('information-validation-') for c in cases))
        for pair in suites['validation']:
            selected = [c for c in cases if c['pair_id'] == pair['id']]
            self.assertEqual(len(selected), 2)
            self.assertEqual(selected[0]['query'], pair['context'] + ' ' + pair['supported']['request'])
            self.assertIsNone(selected[1]['expected_document'])

    def test_holdout_requires_explicit_opt_in_before_reading(self):
        with patch('runbookops.information_dataset.validate_dataset') as read:
            with self.assertRaisesRegex(ValueError, 'explicit opt-in'):
                load_cases(self.root, 'holdout')
            read.assert_not_called()
        cases = load_cases(self.root, 'holdout', allow_holdout=True)
        self.assertEqual(len(cases), 20)
        self.assertTrue(all(c['id'].startswith('information-holdout-') for c in cases))
        with self.assertRaisesRegex(ValueError, 'Select validation'):
            load_cases(self.root, 'unknown')

    def test_changed_frozen_input_rejected(self):
        path = self.root / SPLITS['validation']
        path.write_text(path.read_text() + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
            validate_dataset(self.root)

    def test_corpus_inventory_changes_rejected(self):
        extra = self.root / 'data/runbooks/extra.md'
        extra.write_text('# Extra\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_dataset(self.root)
        extra.unlink()
        (self.root / 'data/runbooks/api-timeouts.md').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_dataset(self.root)

    def test_missing_manifest_entry_rejected(self):
        manifest = json.loads((self.root / MANIFEST).read_text())
        del manifest['sha256'][SPLITS['holdout']]
        (self.root / MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_dataset(self.root)

    def test_duplicate_id_and_scenario_rejected(self):
        original = self.pairs('holdout')
        for field in ('id', 'scenario'):
            with self.subTest(field=field):
                pairs = json.loads(json.dumps(original))
                pairs[0][field] = self.pairs()[0][field]
                self.rewrite(SPLITS['holdout'], pairs)
                with self.assertRaisesRegex(ValueError, 'Repeated ID or scenario'):
                    validate_dataset(self.root)

    def test_duplicate_normalized_query_rejected(self):
        pairs = self.pairs('holdout')
        validation = self.pairs()[0]
        pairs[0]['context'] = validation['context'].upper()
        pairs[0]['supported']['request'] = '  ' + validation['supported']['request']
        self.rewrite(SPLITS['holdout'], pairs)
        with self.assertRaisesRegex(ValueError, 'Repeated normalized query'):
            validate_dataset(self.root)

    def test_training_query_overlap_rejected(self):
        pairs = self.pairs()
        incident = json.loads((self.root / 'data/incidents.json').read_text())[0]['text']
        pairs[0]['context'], pairs[0]['supported']['request'] = incident.split(' ', 1)
        self.rewrite(SPLITS['validation'], pairs)
        with self.assertRaisesRegex(ValueError, 'Repeated normalized query'):
            validate_dataset(self.root)

    def test_evidence_ranges_and_quotes_rejected(self):
        original = self.pairs()
        heading = (self.root / 'data/runbooks/api-timeouts.md').read_text().splitlines()[0]
        for evidence in ({'start_line': True, 'end_line': 2, 'quote': 'x'},
                         {'start_line': 0, 'end_line': 2, 'quote': 'x'},
                         {'start_line': 1, 'end_line': 999, 'quote': 'x'},
                         {'start_line': 9, 'end_line': 11, 'quote': 'invented'},
                         {'start_line': 1, 'end_line': 1, 'quote': heading}):
            with self.subTest(evidence=evidence):
                pairs = json.loads(json.dumps(original))
                pairs[0]['supported']['evidence'] = evidence
                self.rewrite(SPLITS['validation'], pairs)
                with self.assertRaises(ValueError):
                    validate_dataset(self.root)

    def test_unexpected_schema_fields_rejected(self):
        pairs = self.pairs()
        pairs[0]['supported']['expected_score'] = 1.0
        self.rewrite(SPLITS['validation'], pairs)
        with self.assertRaisesRegex(ValueError, 'Invalid fields: supported'):
            validate_dataset(self.root)

    def test_invalid_labels_and_missing_rationales_rejected(self):
        original = self.pairs()
        for field, value in (('information_type', 'unknown'), ('information_type', []),
                             ('missing_information', ' '), ('request', 'x' * 2001)):
            with self.subTest(field=field, value=value):
                pairs = json.loads(json.dumps(original))
                pairs[0]['unsupported'][field] = value
                self.rewrite(SPLITS['validation'], pairs)
                with self.assertRaises(ValueError):
                    validate_dataset(self.root)

    def test_missing_pair_rejected(self):
        self.rewrite(SPLITS['validation'], self.pairs()[:-1])
        with self.assertRaisesRegex(ValueError, 'one contrast pair'):
            validate_dataset(self.root)

    def test_duplicate_json_keys_rejected(self):
        (self.root / MANIFEST).write_text('{"version":1,"version":2}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            validate_dataset(self.root)

    def test_integrity_cli_does_not_import_models_or_write_results(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        probe = (
            'import sys; from runbookops.information_dataset import main; main(); '
            'assert not ({"runbookops.service", "runbookops.retrieval", "sklearn", "httpx"} & set(sys.modules))'
        )
        result = subprocess.run([sys.executable, '-c', probe, '--root', str(self.root)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['scored_queries'], 0)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
