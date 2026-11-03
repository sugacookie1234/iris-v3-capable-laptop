import unittest
from iris.generalist.evaluation import score, summary


class EvaluationTests(unittest.TestCase):
    def test_gate_rejects_regression_missing_duplicate_skipped_and_baseline_failure(self):
        good = [{'id': 'safety', 'passed': True}, {'id': 'task', 'passed': True}]
        self.assertTrue(score(good, good)['passed'])
        bad = [{'id': 'safety', 'passed': False}, good[1]]
        self.assertEqual(score(good, bad)['regressions'], ['safety'])
        for baseline, candidate in ((good, bad), (bad, good), (good, good[:1]),
                                    (good, good + [good[0]]), ([], [])):
            self.assertFalse(score(baseline, candidate)['passed'])

    def test_summary_names_failure_without_claiming_improvement(self):
        base = [{'id': 'permission-test', 'passed': True}]
        candidate = [{'id': 'permission-test', 'passed': False}]
        report = {'baseline': base, 'candidate': candidate, 'gate': score(base, candidate),
                  'finding': 'No improvement demonstrated.', 'scope': 'Synthetic only.'}
        output = summary(report)
        self.assertIn('FAIL', output)
        self.assertIn('permission-test', output)
        self.assertIn('No improvement', output)
