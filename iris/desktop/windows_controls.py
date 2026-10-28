"""Small, host-owned Windows actions; no shell, arbitrary app or model arguments.

App launches are not reported as completed merely because CreateProcess worked.
Volume uses Microsoft's IAudioEndpointVolume and reads back the resulting state.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time
import uuid


APPS = {
    'chrome': ('Google Chrome', 'chrome.exe'),
    'obsidian': ('Obsidian', 'Obsidian.exe'),
    'notepad': ('Notepad', 'notepad.exe'),
    'calculator': ('Calculator', 'calc.exe'),
    'explorer': ('File Explorer', 'explorer.exe'),
}


class ControlUnavailable(RuntimeError):
    """A bounded action could not be completed or verified."""


def _windows_directory():
    buffer = ctypes.create_unicode_buffer(32768)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetWindowsDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetWindowsDirectoryW.restype = wintypes.UINT
    size = kernel.GetWindowsDirectoryW(buffer, len(buffer))
    if not size or size >= len(buffer):
        raise ControlUnavailable('Windows installation directory is unavailable.')
    return Path(buffer.value)


def _registered_path(filename):
    import winreg
    key = 'Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\' + filename
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as entry:
                    value, kind = winreg.QueryValueEx(entry, None)
                    if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str) and '\0' not in value:
                        yield os.path.expandvars(value).strip().strip('"')
            except OSError:
                continue


def find_app(alias):
    """Resolve only a fixed app filename in installation locations/App Paths."""
    if alias not in APPS:
        raise ValueError('Choose one of the supported applications.')
    if os.name != 'nt':
        raise ControlUnavailable('Computer controls require the Windows desktop app.')
    filename = APPS[alias][1]
    windows = _windows_directory()
    candidates = []
    if alias in ('notepad', 'calculator'):
        candidates.append(windows / 'System32' / filename)
    elif alias == 'explorer':
        candidates.append(windows / filename)
    else:
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            root = os.environ.get(variable)
            if not root:
                continue
            base = Path(root)
            if alias == 'chrome':
                candidates.append(base / 'Google/Chrome/Application/chrome.exe')
            else:
                candidates.extend((base / 'Obsidian/Obsidian.exe', base / 'Programs/Obsidian/Obsidian.exe'))
        candidates.extend(Path(value) for value in _registered_path(filename))
    for candidate in candidates:
        # Registry values containing command arguments, URLs, UNC shares, or an
        # unrelated binary never become executable commands.
        if (candidate.is_absolute() and not candidate.drive.startswith('\\\\')
                and candidate.name.casefold() == filename.casefold() and candidate.is_file()):
            return candidate
    raise ControlUnavailable(f'{APPS[alias][0]} was not found in its installation locations.')


def visible_app_window(executable):
    """Read window ownership only; never inspect titles or interact with a UI."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    expected = os.path.normcase(os.path.abspath(executable))
    found = False

    @callback_type
    def inspect(handle, _):
        nonlocal found
        if not user.IsWindowVisible(handle):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        process = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not process:
            return True
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                found = os.path.normcase(os.path.abspath(buffer.value)) == expected
        finally:
            kernel.CloseHandle(process)
        return not found

    user.EnumWindows(inspect, 0)
    return found


class GUID(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _com_method(pointer, index, result, *arguments):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *arguments)(table[index])


def _check_hresult(value):
    if value < 0:
        raise ControlUnavailable('Windows could not access the default speaker volume.')


class CoreAudio:
    """Per-call COM lifetime, safe to use from independent request threads."""
    @contextmanager
    def endpoint(self):
        if os.name != 'nt':
            raise ControlUnavailable('System volume requires Windows.')
        ole = ctypes.WinDLL('ole32')
        hresult = ctypes.c_int32
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole.CoInitializeEx.restype = hresult
        ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole.CoCreateInstance.restype = hresult
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        initialized = ole.CoInitializeEx(None, 0)  # MTA; an existing STA is usable too.
        if initialized not in (0, 1, -2147417850):  # RPC_E_CHANGED_MODE
            _check_hresult(initialized)
        enumerator, device, endpoint = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            clsid = GUID.parse('BCDE0395-E52F-467C-8E3D-C4579291692E')
            iid = GUID.parse('A95664D2-9614-4F35-A746-DE8DB63617E6')
            _check_hresult(ole.CoCreateInstance(ctypes.byref(clsid), None, 1,
                                               ctypes.byref(iid), ctypes.byref(enumerator)))
            get_default = _com_method(enumerator, 4, hresult, ctypes.c_int, ctypes.c_int,
                                      ctypes.POINTER(ctypes.c_void_p))
            _check_hresult(get_default(enumerator, 0, 1, ctypes.byref(device)))  # render, multimedia
            volume_iid = GUID.parse('5CDF2C82-841E-4546-9722-0CF74078229A')
            activate = _com_method(device, 3, hresult, ctypes.POINTER(GUID), wintypes.DWORD,
                                   ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
            _check_hresult(activate(device, ctypes.byref(volume_iid), 23, None, ctypes.byref(endpoint)))
            yield endpoint
        finally:
            for pointer in (endpoint, device, enumerator):
                if pointer:
                    _com_method(pointer, 2, wintypes.ULONG)(pointer)
            if initialized in (0, 1):
                ole.CoUninitialize()

    def volume(self, percent=None, muted=None):
        with self.endpoint() as endpoint:
            hresult = ctypes.c_int32
            if percent is not None:
                setter = _com_method(endpoint, 7, hresult, ctypes.c_float, ctypes.c_void_p)
                _check_hresult(setter(endpoint, percent / 100, None))
            if muted is not None:
                setter = _com_method(endpoint, 14, hresult, wintypes.BOOL, ctypes.c_void_p)
                _check_hresult(setter(endpoint, muted, None))
            scalar, mute = ctypes.c_float(), wintypes.BOOL()
            getter = _com_method(endpoint, 9, hresult, ctypes.POINTER(ctypes.c_float))
            _check_hresult(getter(endpoint, ctypes.byref(scalar)))
            getter = _com_method(endpoint, 15, hresult, ctypes.POINTER(wintypes.BOOL))
            _check_hresult(getter(endpoint, ctypes.byref(mute)))
            return {'percent': round(scalar.value * 100), 'muted': bool(mute.value)}


class WindowsControls:
    def __init__(self, *, resolver=find_app, launcher=subprocess.Popen, observer=visible_app_window,
                 audio=None, sleep=time.sleep, folder_check=None):
        self.resolver, self.launcher, self.observer = resolver, launcher, observer
        self.audio, self.sleep = audio or CoreAudio(), sleep
        self.folder_check = folder_check

    def open_app(self, alias):
        if type(alias) is not str or alias not in APPS:
            raise ValueError('Choose one of the supported applications.')
        executable = self.resolver(alias)
        try:
            self.launcher([str(executable)], shell=False, close_fds=True)
        except OSError:
            raise ControlUnavailable(f'Windows could not launch {APPS[alias][0]}.') from None
        visible = False
        for attempt in range(6):
            try:
                visible = bool(self.observer(executable))
            except OSError:
                break
            if visible:
                break
            if attempt < 5:
                self.sleep(.2)
        name = APPS[alias][0]
        detail = (f'{name} has a visible window.' if visible else
                  f'Windows accepted the request to open {name}; I could not verify its window yet.')
        return {'action': 'open_app', 'app': alias, 'name': name, 'detail': detail,
                'state': 'visible' if visible else 'requested', 'verified': visible}

    def open_folder(self, path):
        """For host-configured directories only; not an arbitrary model path API."""
        directory = Path(path)
        if not directory.is_absolute() or str(directory).startswith(('\\\\', '//')):
            raise ValueError('A configured local absolute directory is required.')
        if self.folder_check is not None:
            self.folder_check(directory)
        else:
            if os.name != 'nt':
                raise ControlUnavailable('Computer controls require the Windows desktop app.')
            from iris.tools.windows_paths import check_directory
            check_directory(directory)
        executable = self.resolver('explorer')
        try:
            self.launcher([str(executable), str(directory)], shell=False, close_fds=True)
        except OSError:
            raise ControlUnavailable('Windows could not open the configured folder.') from None
        # A generic Explorer window does not prove this particular folder opened.
        return {'action': 'open_folder', 'path': str(directory), 'state': 'requested', 'verified': False,
                'detail': 'Sent the folder to File Explorer; its location was not verified.'}

    def volume(self, percent=None, muted=None):
        if percent is not None and (type(percent) is not int or not 0 <= percent <= 100):
            raise ValueError('Volume must be a whole number from 0 to 100.')
        if muted is not None and type(muted) is not bool:
            raise ValueError('Mute must be on or off.')
        result = self.audio.volume(percent=percent, muted=muted)
        if (type(result.get('percent')) is not int or not 0 <= result['percent'] <= 100
                or type(result.get('muted')) is not bool):
            raise ControlUnavailable('Windows did not return a valid volume reading.')
        verified = ((percent is None or abs(result['percent'] - percent) <= 1)
                    and (muted is None or result['muted'] == muted))
        return {'action': 'volume', **result, 'verified': verified,
                'state': 'verified' if verified else 'mismatch',
                'detail': f"System volume is {result['percent']}%, {'muted' if result['muted'] else 'unmuted'}."}
