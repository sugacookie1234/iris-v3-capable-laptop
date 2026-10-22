import io
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from iris.automation.models import AutomationRunStatus
from iris.automation.worker import AutomationWorker, AutomationWorkerConfig, load_worker_config, main, run


class Commands:
    def __init__(self, values=()):
        self.values = list(values)

    def poll(self, timeout):
        if self.values:
            value = self.values.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        raise EOFError


class AutomationWorkerTests(unittest.TestCase):
    def test_config_interval_validation(self):
        with self.assertRaises(ValueError):
            AutomationWorkerConfig(0)
        with self.assertRaises(ValueError):
            load_worker_config({"IRIS_AUTOMATION_INTERVAL_SECONDS": "not-a-number"})
        self.assertEqual(load_worker_config({}).interval_seconds, 60)

    def test_immediate_check_and_status_stop(self):
        scheduler = Mock()
        scheduler.store.list.return_value = ()
        scheduler.store.pending_approvals.return_value = ()
        scheduler.run_once.return_value = ()
        output = []
        worker = AutomationWorker(scheduler, AutomationWorkerConfig(1), output.append,
                                   clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        run(worker, Commands(["/automation-status", "/automation-stop"]), monotonic=lambda: 0)
        scheduler.run_once.assert_called_once()
        self.assertIn("Local automation started.", output[0])
        self.assertTrue(any("Automation: running" in value for value in output))
        self.assertEqual(output[-1], "Local automation stopped.")

    def test_due_outcomes_are_reported_and_pending_is_not_executed(self):
        scheduler = Mock()
        scheduler.run_once.return_value = (
            Mock(status=AutomationRunStatus.SUCCESS, schedule_id="s1", occurrence="o1", run=Mock(workflow_name="green")),
            Mock(status=AutomationRunStatus.PENDING_APPROVAL, schedule_id="s2", occurrence="o2", run=Mock(workflow_name="red")),
            Mock(status=AutomationRunStatus.TIMEOUT, schedule_id="s3", occurrence="o3", run=Mock(workflow_name="slow")),
        )
        output = []
        worker = AutomationWorker(scheduler, AutomationWorkerConfig(1), output.append,
                                   clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        worker.check()
        self.assertEqual(scheduler.run_once.call_count, 1)
        self.assertTrue(any("success" in value for value in output))
        self.assertTrue(any("pending_approval" in value for value in output))
        self.assertTrue(any("timeout" in value for value in output))

    def test_eof_and_interrupt_stop_cleanly(self):
        for signal in (EOFError(), KeyboardInterrupt()):
            output = []
            scheduler = Mock()
            scheduler.run_once.return_value = ()
            worker = AutomationWorker(scheduler, AutomationWorkerConfig(1), output.append,
                                       clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
            run(worker, Commands([signal]), monotonic=lambda: 0)
            self.assertFalse(worker.running)
            self.assertEqual(output[-1], "Local automation stopped.")

    def test_help_does_not_build_worker(self):
        with patch("iris.automation.worker._build_worker", side_effect=AssertionError("must not build")):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
