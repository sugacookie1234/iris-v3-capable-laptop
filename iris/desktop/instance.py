"""One owner per checkout, shared by desktop and browser launchers."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def instance_guard(root):
    root = Path(root).resolve()
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        identifier = hashlib.sha256(str(root).lower().encode()).hexdigest()[:24]
        handle = kernel.CreateMutexW(None, False, 'Local\\IRIS-' + identifier)
        if not handle:
            raise OSError('Could not reserve the IRIS application instance.')
        try:
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                raise AlreadyRunning('IRIS is already running for this checkout.')
            yield
        finally:
            kernel.CloseHandle(handle)
    else:
        # Keep browser mode available on systems without Windows mutexes.
        # The lock file stays in place; unlinking it could create two owners.
        import fcntl
        directory = root / '.local'
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'instance.lock').open('a+b') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AlreadyRunning('IRIS is already running for this checkout.') from None
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
