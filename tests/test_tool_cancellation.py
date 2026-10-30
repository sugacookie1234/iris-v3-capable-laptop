"""Real stoppable workers with synthetic local handlers; no provider access."""
from dataclasses import replace
import multiprocessing
import threading
import time
import unittest
from unittest.mock import patch

from iris.tools import (Approval, AuthorityContext, AuthorityLevel, FailureCode,
    RequestOrigin, ResultStatus, ToolCall, ToolExecutor, ToolRegistry, ToolSpec)


def sleeping_read():
    time.sleep(10)
    return {'value': 'late data'}


def immediate_read():
    return {'value': 'local data'}


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.spec = ToolSpec('read_fixture', 'Read a synthetic fixture', AuthorityLevel.GREEN,
                             True, (), ('fixture.read',), 10, local_only=True)
        self.authority = AuthorityContext(True, frozenset({'fixture.read'}))
        self.call = ToolCall('read_fixture', {}, RequestOrigin.USER)

    def executor(self, handler=sleeping_read, **changes):
        registry = ToolRegistry()
        registry.register(replace(self.spec, **changes), handler)
        return ToolExecutor(registry)

    def test_running_worker_stops_promptly_and_leaves_no_child(self):
        executor = self.executor()
        cancel = threading.Event()
        result = []
        before = {process.pid for process in multiprocessing.active_children()}
        worker = threading.Thread(target=lambda: result.append(executor.execute(
            self.call, authority=self.authority, cancelled=cancel.is_set)))
        worker.start()
        # Confirm a real child exists before requesting cancellation, so this
        # cannot pass merely because an unstarted worker was skipped.
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if {p.pid for p in multiprocessing.active_children()} - before:
                break
            time.sleep(.01)
        else:
            cancel.set()
            worker.join(2)
            self.fail('The synthetic worker did not start.')
        stopped_at = time.monotonic()
        cancel.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertLess(time.monotonic() - stopped_at, 2)
        self.assertEqual(result[0].failure.code, FailureCode.CANCELLED)
        self.assertIsNone(result[0].value)
        self.assertFalse({p.pid for p in multiprocessing.active_children()} - before)

    def test_early_cancellation_never_starts_a_worker_and_authority_still_applies(self):
        executor = self.executor()
        with patch('iris.tools.executor.multiprocessing.get_context') as context:
            result = executor.execute(self.call, authority=self.authority, cancelled=lambda: True)
            denied = executor.execute(self.call, authority=AuthorityContext(), cancelled=lambda: True)
        self.assertEqual(result.failure.code, FailureCode.CANCELLED)
        self.assertEqual(denied.failure.code, FailureCode.AUTHORITY_DENIED)
        context.assert_not_called()

    def test_cancel_after_approval_does_not_run_approved_handler(self):
        executor = self.executor(authority=AuthorityLevel.YELLOW)
        cancel = threading.Event()
        def approve(plan):
            cancel.set()
            return Approval(plan.id, True)
        with patch('iris.tools.executor.multiprocessing.get_context') as context:
            result = executor.execute(self.call, authority=self.authority,
                                      approve=approve, cancelled=cancel.is_set)
        self.assertEqual(result.failure.code, FailureCode.CANCELLED)
        context.assert_not_called()

    def test_false_cancellation_does_not_bypass_approval_or_timeout(self):
        executor = self.executor(authority=AuthorityLevel.YELLOW)
        missing = executor.execute(self.call, authority=self.authority, cancelled=lambda: False)
        self.assertEqual(missing.failure.code, FailureCode.APPROVAL_REQUIRED)
        timed_out = self.executor(timeout=.1).execute(self.call, authority=self.authority, cancelled=lambda: False)
        self.assertEqual(timed_out.failure.code, FailureCode.TIMEOUT)

    def test_cancellation_after_received_payload_wins_over_success(self):
        # Simulate a transport boundary at which cancellation arrives with the
        # result. This covers the exact race without timing sleeps.
        cancel = threading.Event()
        class Receiver:
            def poll(self, timeout): return True
            def recv_bytes(self):
                cancel.set()
                return b'{"value":{"private":"do not return"}}'
            def close(self): pass
        class Sender:
            def close(self): pass
        class Process:
            def start(self): pass
            def is_alive(self): return False
            def join(self, timeout=None): pass
            def close(self): pass
        class Context:
            def Pipe(self, duplex): return Receiver(), Sender()
            def Process(self, **kwargs): return Process()
        with patch('iris.tools.executor.multiprocessing.get_context', return_value=Context()):
            result = self.executor(immediate_read).execute(self.call, authority=self.authority, cancelled=cancel.is_set)
        self.assertEqual(result.failure.code, FailureCode.CANCELLED)
        self.assertIsNone(result.value)

    def test_invalid_or_failed_host_signal_fails_closed_without_sensitive_error(self):
        def broken(): raise RuntimeError('private exception details')
        for callback in (broken, lambda: 'not boolean'):
            with self.subTest(callback=callback), patch('iris.tools.executor.multiprocessing.get_context') as context:
                result = self.executor().execute(self.call, authority=self.authority, cancelled=callback)
                self.assertEqual(result.failure.code, FailureCode.EXECUTION_FAILED)
                self.assertNotIn('private exception', str(result))
                context.assert_not_called()


if __name__ == '__main__':
    unittest.main()
