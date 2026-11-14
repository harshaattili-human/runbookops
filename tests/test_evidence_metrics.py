"""Hand-constructed metric fixtures only: no evaluation dataset or retriever."""

import unittest

from runbookops.evidence_metrics import evidence_supported_and_answered


def source(identifier='a', document='expected', start=5, end=9):
    return {'id': identifier, 'document': document, 'start_line': start, 'end_line': end}


def response(sources=None, citations=None, mode='extractive', answer='Fixture answer'):
    return {'mode': mode, 'answer': answer,
            'sources': [source()] if sources is None else sources,
            'citations': ['a'] if citations is None else citations}


def covered(result, start=6, end=8):
    return evidence_supported_and_answered(
        result, 'expected', {'start_line': start, 'end_line': end})


class EvidenceMetricsTest(unittest.TestCase):
    def test_full_and_exact_coverage(self):
        self.assertTrue(covered(response()))
        self.assertTrue(covered(response(), 5, 9))

    def test_correct_document_wrong_passage(self):
        self.assertFalse(covered(response([source(start=10, end=15)])))

    def test_partial_coverage_is_not_enough(self):
        self.assertFalse(covered(response([source(start=5, end=7)])))
        self.assertFalse(covered(response([source(start=7, end=9)])))

    def test_uncited_matching_passage_does_not_count(self):
        self.assertFalse(covered(response(
            [source('a', start=10, end=15), source('b')], ['a'])))

    def test_wrong_document_does_not_count(self):
        self.assertFalse(covered(response([source(document='other')])))

    def test_abstention_and_empty_answer_do_not_count(self):
        self.assertFalse(covered(response(mode='abstained')))
        self.assertFalse(covered(response(answer='  ')))
        self.assertFalse(covered(response([], [], mode='abstained')))

    def test_adjacent_and_overlapping_intervals_merge_out_of_order(self):
        self.assertTrue(covered(response(
            [source('a', start=7, end=9), source('b', start=5, end=6)], ['a', 'b'])))
        self.assertTrue(covered(response(
            [source('a', start=7, end=9), source('b', start=5, end=7)], ['b', 'a'])))

    def test_disjoint_intervals_cannot_bridge_a_gap(self):
        self.assertFalse(covered(response(
            [source('a', start=5, end=6), source('b', start=8, end=9)], ['a', 'b'])))
        self.assertTrue(covered(response(
            [source('a', start=1, end=3), source('b', start=6, end=8)], ['a', 'b'])))

    def test_duplicate_citations_do_not_add_coverage(self):
        self.assertTrue(covered(response(citations=['a', 'a'])))
        self.assertFalse(covered(response([source(end=7)], ['a', 'a'])))

    def test_missing_or_ambiguous_citation_ids_fail(self):
        with self.assertRaisesRegex(ValueError, 'resolve'):
            covered(response(citations=['missing']))
        with self.assertRaisesRegex(ValueError, 'unique'):
            covered(response([source(), source(start=10, end=15)]))

    def test_invalid_intervals_fail_instead_of_counting(self):
        for start, end in [(0, 8), (8, 6), (True, 8), (6, 8.0)]:
            with self.subTest(start=start, end=end):
                with self.assertRaisesRegex(ValueError, 'integer'):
                    covered(response(), start, end)
                with self.assertRaisesRegex(ValueError, 'integer'):
                    covered(response([source(start=start, end=end)]))

    def test_local_generation_is_outside_this_protocol(self):
        with self.assertRaisesRegex(ValueError, 'extractive path'):
            covered(response(mode='local-llm'))


if __name__ == '__main__':
    unittest.main()
