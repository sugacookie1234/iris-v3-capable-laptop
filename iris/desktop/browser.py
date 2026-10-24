"""Explicit Chrome launcher; never silently opens a different browser."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit


def chrome_path():
    for variable, default in (
        ('ProgramFiles', 'C:/Program Files'),
        ('ProgramFiles(x86)', 'C:/Program Files (x86)'),
        ('LOCALAPPDATA', ''),
    ):
        root = os.environ.get(variable, default)
        if root:
            candidate = Path(root) / 'Google/Chrome/Application/chrome.exe'
            if candidate.is_file():
                return str(candidate)
    for name in ('chrome', 'google-chrome'):
        candidate = shutil.which(name)
        if candidate:
            return candidate
    return None


def open_chrome(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only ordinary HTTP or HTTPS links can open in Chrome.')
    executable = chrome_path()
    if not executable:
        raise RuntimeError('Google Chrome was not found. Install Chrome to use browser mode or source links.')
    subprocess.Popen([executable, '--new-window', url], close_fds=True)
    return True


class ChromeBrowser:
    """Adapter for pywebview's external-link handler, scoped to this process."""
    def open(self, url, new=0, autoraise=True):
        try:
            return open_chrome(url)
        except (ValueError, RuntimeError, OSError):
            return False

