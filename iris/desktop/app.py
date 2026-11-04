"""Standalone Windows window owning the local IRIS server lifecycle."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
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
from iris.desktop.instance import AlreadyRunning, instance_guard

TITLE = 'I.R.I.S. — Personal Intelligence'
LOG = logging.getLogger('iris.desktop')


@contextmanager
def single_instance():
    """A per-checkout, per-Windows-session mutex, released even on launch failure."""
    if os.name != 'nt':
        raise RuntimeError('The standalone launcher requires Windows. Use browser mode on other systems.')
    with instance_guard(ROOT):
        yield


def local_navigation(url, origin):
    """Only the owned loopback origin can replace the embedded app document."""
    try:
        parsed, expected = urlsplit(url), urlsplit(origin)
        return (parsed.scheme == expected.scheme == 'http' and
                parsed.hostname == expected.hostname and expected.hostname in ('127.0.0.1','localhost') and
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



def allow_visual_activation(window):
    """After a non-activating initial Show, allow ordinary keyboard focus on click."""
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    get_style=user32.GetWindowLongW
    get_style.argtypes=[wintypes.HWND,ctypes.c_int];get_style.restype=ctypes.c_long
    set_style=user32.SetWindowLongW
    set_style.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_long];set_style.restype=ctypes.c_long
    handle=int(window.native.Handle.ToInt64())
    style=get_style(handle,-20)
    # Only the owned secondary window is changed, on its WinForms thread.
    window.focus=True
    set_style(handle,-20,style & ~0x08000000)


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
        if hasattr(runtime, 'close'):
            runtime.close()
        raise RuntimeError('No available IRIS port. Close the earlier instance and try again.')
    server.desktop_window = True
    thread = threading.Thread(target=server.serve_forever, name='IRIS local server', daemon=True)
    thread.start()
    previous_open = webbrowser.open
    tray = None
    visual_controller = None
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
        window = webview.create_window(TITLE, server.bootstrap_url(), width=1240, height=820, min_size=(720, 620),
                                       background_color='#050d15', text_select=True)
        from iris.desktop.visual_window import VisualWindowController
        def dispatch_visual(callback):
            from System import Action
            window.native.BeginInvoke(Action(callback))
        def create_visual():
            child=webview.create_window('I.R.I.S. — Visual Workspace',server.visual_bootstrap_url(),
                width=1080,height=780,min_size=(640,520),resizable=True,focus=False,
                background_color='#050d15',text_select=True)
            if child is None:raise RuntimeError('Visual window was not created.')
            try:
                guard_navigation(child,f'http://localhost:{server.server_address[1]}/visual')
                allow_visual_activation(child)
            except Exception:
                child.destroy()
                raise
            return child
        visual_controller=VisualWindowController(dispatch_visual,create_visual,server.revoke_visual,
            refresh=lambda child:child.load_url(server.visual_bootstrap_url()))
        runtime.visual_window=visual_controller
        def prepare_window():
            nonlocal tray
            guard_navigation(window, url)
            window.native.FormClosed += lambda sender,event: visual_controller.shutdown_on_ui()
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
        if visual_controller is not None:
            try:visual_controller.dispose()
            except Exception:server.revoke_visual()
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
