"""Standalone Windows window owning the local IRIS server lifecycle."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import logging
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

from iris.desktop.browser import ChromeBrowser
from iris.desktop.runtime import DesktopRuntime, ROOT
from iris.desktop.server import DesktopServer
from iris.desktop.tray import install_tray

TITLE = 'I.R.I.S. — Personal Intelligence'
LOG = logging.getLogger('iris.desktop')


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def single_instance():
    """A per-checkout, per-Windows-session mutex, released even on launch failure."""
    if os.name != 'nt':
        raise RuntimeError('The standalone launcher requires Windows. Use browser mode on other systems.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    identifier = hashlib.sha256(str(ROOT.resolve()).lower().encode()).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, False, 'Local\\IRIS-' + identifier)
    if not handle:
        raise OSError('Could not reserve the IRIS application instance.')
    try:
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            raise AlreadyRunning('IRIS is already open. Select its window on the taskbar.')
        yield
    finally:
        kernel.CloseHandle(handle)


def local_navigation(url, origin):
    """Only the owned loopback origin can replace the embedded app document."""
    try:
        parsed, expected = urlsplit(url), urlsplit(origin)
        return (parsed.scheme == expected.scheme == 'http' and
                parsed.hostname == expected.hostname == '127.0.0.1' and
                parsed.port == expected.port and not parsed.username and not parsed.password)
    except (ValueError, TypeError):
        return False


def guard_navigation(window, origin):
    # before_show runs on the WinForms thread, before the first document loads.
    control = window.native.webview

    def navigating(sender, event):
        if not local_navigation(str(event.Uri), origin):
            event.Cancel = True

    control.NavigationStarting += navigating


def run_window(webview, runtime, port=8766):
    """Keep server ownership explicit; no browser is opened and no orphan remains."""
    server = None
    for candidate in range(port, min(port + 10, 65536)):
        try:
            server = DesktopServer(('127.0.0.1', candidate), runtime)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError('No available IRIS port. Close the earlier instance and try again.')
    server.desktop_window = True
    thread = threading.Thread(target=server.serve_forever, name='IRIS local server', daemon=True)
    thread.start()
    previous_open = webbrowser.open
    tray = None
    try:
        url = f'http://127.0.0.1:{server.server_address[1]}/'
        # pywebview delegates target=_blank links to this function. Replace it
        # only in this app process so failed Chrome launches cannot try Edge.
        webbrowser.open = ChromeBrowser().open
        webview.settings.update({
            'ALLOW_FILE_URLS': False, 'ALLOW_DOWNLOADS': False,
            'OPEN_EXTERNAL_LINKS_IN_BROWSER': True,
            'IGNORE_SSL_ERRORS': False, 'REMOTE_DEBUGGING_PORT': None,
        })
        # App-local settings keep standby active and allow previously permitted
        # audio to resume on launch. Microphone permission is still required.
        flags = os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '').split()
        for flag in ('--disable-background-timer-throttling', '--autoplay-policy=no-user-gesture-required'):
            if not any(value.split('=')[0] == flag.split('=')[0] for value in flags):
                flags.append(flag)
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = ' '.join(flags)
        window = webview.create_window(TITLE, url, width=1240, height=820, min_size=(720, 620),
                                       background_color='#050d15', text_select=True)
        def prepare_window():
            nonlocal tray
            guard_navigation(window, url)
            try:
                tray = install_tray(window, ROOT)
            except Exception as exc:
                # Without a usable tray, preserve the ordinary close-to-exit
                # behavior rather than hiding a window the user cannot reopen.
                LOG.warning('Tray unavailable; closing the window exits IRIS: %s', type(exc).__name__)

        window.events.before_show += prepare_window
        window.events.loaded += lambda: LOG.info('IRIS desktop interface loaded on port %s', server.server_address[1])
        webview.start(gui='edgechromium', debug=False, private_mode=False,
                      storage_path=str(Path(runtime.data_dir) / 'webview'))
    finally:
        if tray is not None:
            try:
                tray.dispose()
            except Exception as exc:
                LOG.warning('Tray cleanup failed: %s', type(exc).__name__)
        webbrowser.open = previous_open
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        LOG.info('IRIS desktop stopped')


def notify_error(message):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, message, 'IRIS', 0x10)
    elif sys.stderr:
        print(message, file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open IRIS in its own Windows desktop window.')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    logging.basicConfig(filename=local / 'desktop.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('pywebview').setLevel(logging.ERROR)
    try:
        with single_instance():
            import webview
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IRIS.CapableLaptop.3')
            run_window(webview, DesktopRuntime(), args.port)
    except AlreadyRunning as exc:
        notify_error('IRIS is already running. Open it from its icon in the Windows notification area or taskbar.')
        return 0
    except Exception as exc:
        # Log the category, not provider responses/configuration or credentials.
        LOG.error('Desktop startup failed: %s', type(exc).__name__)
        notify_error('IRIS could not open its desktop window. Run setup.bat to update dependencies.\n\n'
                     'The desktop app requires Microsoft WebView2 Runtime. See docs/DESKTOP-APP.md.\n'
                     'You can also use start-iris-browser.bat to open IRIS in Google Chrome.\n\n'
                     'Diagnostic category: ' + type(exc).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
