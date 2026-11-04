"""Process-local admission limits. Counts attempts, never claims provider billing."""
from collections import deque
from contextlib import contextmanager
import threading
import time

class UsageLimitError(ValueError):
    pass

class UsageLimits:
    def __init__(self, settings=None, clock=time.monotonic):
        settings = settings or {}
        self.clock = clock
        self.lock = threading.Lock()
        self.events = {}
        self.active = {}
        self.total = {}
        self.policy = {}
        for name, defaults in {'chat':(30,2,500), 'voice':(60,2,1000),
                'transcribe':(30,1,500), 'jobs':(10,2,100), 'database':(60,4,2000),
                'http':(240,8,20000)}.items():
            values=[]
            for suffix,default in zip(('PER_MINUTE','CONCURRENT','PER_SESSION'),defaults):
                raw=settings.get('IRIS_LIMIT_'+name.upper()+'_'+suffix,default)
                if isinstance(raw,bool) or not str(raw).isascii() or not str(raw).isdigit() or not 1 <= int(raw) <= 100000:
                    raise ValueError('Invalid local usage limit configuration.')
                values.append(int(raw))
            self.policy[name]=tuple(values)

    @contextmanager
    def reserve(self, name):
        with self.lock:
            now=self.clock()
            events=self.events.setdefault(name,deque())
            while events and now-events[0]>=60:
                events.popleft()
            minute,concurrent,session=self.policy[name]
            if len(events)>=minute or self.active.get(name,0)>=concurrent or self.total.get(name,0)>=session:
                raise UsageLimitError('Local '+name+' usage limit reached. Wait for capacity or review your configured limits. No automatic retry was made.')
            events.append(now)
            self.total[name]=self.total.get(name,0)+1
            self.active[name]=self.active.get(name,0)+1
        try:
            yield
        finally:
            with self.lock:
                self.active[name]-=1
