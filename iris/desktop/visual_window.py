"""Coalesced native window lifecycle. UI operations run only via host dispatch."""
import threading

class VisualWindowController:
    def __init__(self,dispatch,create,revoke):
        self.dispatch,self.create,self.revoke=dispatch,create,revoke
        self.lock=threading.RLock();self.window=None;self.desired=False
        self.scheduled=False;self.disposed=False;self.manually_closed=False
        self.state='closed';self.visual_id=None;self.revision=0
    def request(self,visual_id=None,revision=0,*,action='update'):
        with self.lock:
            if self.disposed:return
            changed=visual_id is not None and visual_id!=self.visual_id
            if visual_id is not None:
                if not changed and revision<self.revision:return
                self.visual_id,self.revision=visual_id,revision
            if action=='close':self.desired=False;self.manually_closed=True
            elif action=='open' or changed:self.desired=True;self.manually_closed=False
            elif not self.manually_closed:self.desired=True
            if not self.scheduled:
                self.scheduled=True
                try:self.dispatch(self._drain)
                except Exception:
                    self.scheduled=False;self.state='closed';self.manually_closed=True
                    raise
    def _drain(self):
        with self.lock:
            self.scheduled=False
            if self.disposed or not self.desired:
                if self.window is not None:
                    self.state='closing';window=self.window;self.window=None
                    self.revoke();window.destroy()
                self.state='closed';return
            if self.window is not None:self.state='open';return
            self.state='opening'
            try:
                window=self.create()
                self.window=window
                window.events.closed += lambda: self.closed(window)
                self.state='open'
            except Exception:
                self.window=None;self.state='closed';self.desired=False
                self.manually_closed=True;self.revoke()
    def closed(self,window):
        with self.lock:
            if self.window is not window:return
            self.window=None;self.desired=False;self.manually_closed=True
            self.state='closed';self.revoke()
    def dispose(self):
        with self.lock:
            self.disposed=True;self.desired=False;self.revoke()
            if self.window is not None and not self.scheduled:self.scheduled=True;self.dispatch(self._drain)

    def shutdown_on_ui(self):
        with self.lock:
            self.disposed=True;self.desired=False;self.revoke()
            self._drain()
