"""Check measurement denominators and fingerprints, not a synthetic latency target."""
import importlib.util
from pathlib import Path
import sys
import unittest

scripts = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('http_characterization', scripts / 'http_characterization.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
sys.path.pop(0)


class MeasurementTest(unittest.TestCase):
    def test_rejections_have_separate_denominators_and_do_not_inflate_success_rate(self):
        samples = [{'status': 200, 'milliseconds': value, 'valid': True} for value in (10, 20)]
        samples += [{'status': 503, 'milliseconds': 1, 'valid': True},
                    {'status': 'transport_error', 'milliseconds': 100, 'valid': False}]
        report = probe.summarize(samples, 2)
        self.assertEqual(report['attempts_per_second'], 2)
        self.assertEqual(report['successful_responses_per_second'], 1)
        self.assertEqual(report['outcomes']['200'], {'count': 2, 'p50_ms': 10, 'p95_ms': 20, 'max_ms': 20})
        self.assertEqual(report['invalid_responses'], 1)
        self.assertIsNone(probe.percentile([], .95))

    def test_fingerprint_ignores_only_request_diagnostics(self):
        baseline = {'answer': 'evidence', 'corpus': {'documents_sha256': 'a'},
                    'request_id': 'one', 'duration_ms': 5}
        changed = {**baseline, 'request_id': 'two', 'duration_ms': 50}
        self.assertEqual(probe.fingerprint(baseline), probe.fingerprint(changed))
        for field, value in [('answer', 'different'), ('corpus', {'documents_sha256': 'b'})]:
            self.assertNotEqual(probe.fingerprint(baseline), probe.fingerprint({**changed, field: value}))

    def test_equal_work_and_counterbalanced_positions(self):
        for concurrency in probe.LEVELS:
            requests = [i for worker in range(concurrency) for i in range(worker, probe.REQUESTS, concurrency)]
            self.assertEqual(sorted(requests), list(range(probe.REQUESTS)))
        orders = [probe.LEVELS[n:] + probe.LEVELS[:n] for n in range(len(probe.LEVELS))]
        for position in range(len(probe.LEVELS)):
            self.assertEqual({order[position] for order in orders}, set(probe.LEVELS))


if __name__ == '__main__':
    unittest.main()
