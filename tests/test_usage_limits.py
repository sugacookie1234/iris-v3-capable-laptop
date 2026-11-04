import threading
import unittest
from iris.desktop.limits import UsageLimits, UsageLimitError

class UsageLimitsTests(unittest.TestCase):
    def test_burst_recovery_and_failed_attempts(self):
        now=[0]
        limits=UsageLimits({'IRIS_LIMIT_CHAT_PER_MINUTE':'2'},clock=lambda:now[0])
        with self.assertRaises(RuntimeError):
            with limits.reserve('chat'):raise RuntimeError('synthetic provider failure')
        with limits.reserve('chat'):pass
        with self.assertRaises(UsageLimitError):
            with limits.reserve('chat'):pass
        now[0]=60
        with limits.reserve('chat'):pass
        self.assertEqual(limits.total['chat'],3)
        self.assertEqual(limits.active['chat'],0)
    def test_parallel_reservation_cannot_bypass_limit(self):
        limits=UsageLimits({'IRIS_LIMIT_CHAT_CONCURRENT':'1'})
        outcomes=[]
        def contender():
            try:
                with limits.reserve('chat'):outcomes.append('accepted')
            except UsageLimitError:outcomes.append('blocked')
        with limits.reserve('chat'):
            threads=[threading.Thread(target=contender) for _ in range(20)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
        self.assertEqual(outcomes,['blocked']*20)
        with limits.reserve('chat'):pass
    def test_session_ceiling_and_restart_semantics(self):
        settings={'IRIS_LIMIT_CHAT_PER_SESSION':'1'}
        limits=UsageLimits(settings)
        with limits.reserve('chat'):pass
        with self.assertRaises(UsageLimitError):
            with limits.reserve('chat'):pass
        with UsageLimits(settings).reserve('chat'):pass
    def test_invalid_configuration_fails_closed(self):
        for value in ('0','-1','unlimited',True,'100001'):
            with self.assertRaises(ValueError):UsageLimits({'IRIS_LIMIT_CHAT_PER_MINUTE':value})
